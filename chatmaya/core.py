# -*- coding: utf-8 -*-
import os
import json
import re
import time
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
import queue

import openai
openai.api_key = os.getenv("OPENAI_API_KEY")

from maya import cmds, OpenMayaUI
from PySide2 import QtWidgets, QtCore, QtGui
from shiboken2 import wrapInstance

from .info import (
    TITLE,
    VERSION,
    ABOUT_TXT,
    USER_SETTINGS_DIR,
    USER_SETTINGS_INI,
    USER_SETTINGS_JSON,
    LOG_DIR
)
from .prompts import (
    SYSTEM_TEMPLATE_PY,
    SYSTEM_TEMPLATE_MEL
)
from .retry import retry_decorator
from .voice import VoiceGenerator

DEFAULT_GEOMETORY = (200, 300, 800, 600)

class ChatMaya(QtWidgets.QMainWindow):

    def __init__(self, parent=None, *args, **kwargs):
        super(ChatMaya, self).__init__(parent, *args, **kwargs)

        self._exit_flag = False

        self.voice_generator = VoiceGenerator()

        self.q_voice_synthesis = queue.Queue()
        self.q_voice_play = queue.Queue()

        self.executor = ThreadPoolExecutor(max_workers=2)
        self.executor.submit(self.voice_synthesis_thread)
        self.executor.submit(self.voice_play_thread)
        
        self.init_variables()
        
        # User Prefs
        self.user_settings_ini = QtCore.QSettings(str(USER_SETTINGS_INI), QtCore.QSettings.IniFormat)
        self.user_settings_ini.setIniCodec('utf-8')

        # Build UI
        self.init_ui()
        self.get_user_prefs()
        
    def init_variables(self, *args):
        self.session_id = datetime.now().strftime('session_%y%m%d_%H%M%S')
        self.session_log_dir = Path(LOG_DIR / self.session_id)
        if not self.session_log_dir.is_dir():
            self.session_log_dir.mkdir(parents=True)
        self.messages = [{"role":"system", "content":SYSTEM_TEMPLATE_PY}]
        self.code_list = []

    def decompose_response(self, txt:str):
        pattern = r"```python([\s\S]*?)```"
        
        code_list = re.findall(pattern, txt)
        for i in range(int(len(code_list))):
            code_list[i] = re.sub('\A[\r?\n]', '', code_list[i])
            code_list[i] = re.sub('[\r?\n]\Z', '', code_list[i])
        
        comment = re.sub(pattern, '', txt)
        comment = re.sub('[\r?\n]+', '\n', comment)
        comment = re.sub('[\r?\n]\Z', '', comment)
        
        return comment, code_list

    def new_chat(self, *args):
        self.init_variables()
        self.update_scripts()
        cmds.cmdScrollFieldExecuter(self.script_editor, e=True, clear=True)
        self.chat_history_model.removeRows(0, self.chat_history_model.rowCount())
        self.statusBar().showMessage("New Chat")

    def send_message(self):
        user_message = self.user_input.toPlainText()
        if not user_message:
            return
        
        self.statusBar().showMessage("Send")
        
        self.chat_history_model.insertRow(self.chat_history_model.rowCount())
        self.chat_history_model.setData(
            self.chat_history_model.index(self.chat_history_model.rowCount() - 1), 
            user_message)
        self.user_input.clear()
        
        message_text = ""
        sentence = ""
        sentence_end_chars = "。！？"
        backquote_count = 0
        is_code_block = False
        
        self.messages.append({"role": "user", "content": user_message})
        
        self.chat_history_model.insertRow(self.chat_history_model.rowCount())
        
        self.statusBar().showMessage("Completion...")

        # APIコール
        try:
            for content in self.completion():
                message_text += content
                self.chat_history_model.setData(
                    self.chat_history_model.index(self.chat_history_model.rowCount() - 1), 
                    message_text)
                self.chat_history_view.scrollToBottom()
                cmds.refresh()
                
                for char in content:
                    sentence += char

                    if char == "`":
                        backquote_count += 1
                    else:
                        backquote_count = 0
                        
                    if backquote_count == 3:
                        is_code_block = not is_code_block
                        backquote_count = 0
                        sentence = ""

                    if char in sentence_end_chars:
                        if not is_code_block:
                            self.q_voice_synthesis.put(sentence.strip())
                            backquote_count = 0
                        sentence = ""

        except Exception as e:
            cmds.error(str(e))
            return

        # 最後の文が句読点で終わっていない場合
        if sentence.strip():
            if not is_code_block:
                self.q_voice_synthesis.put(sentence.strip())

        # 返答を分解
        comment, self.code_list = self.decompose_response(message_text)

        # Pythonコード以外の部分を表示
        self.chat_history_model.setData(
                    self.chat_history_model.index(self.chat_history_model.rowCount() - 1), 
                    comment)
        self.chat_history_view.scrollToBottom()

        # Scriptsプルダウンを更新
        self.update_scripts()

        # Pythonコードの1つ目をscript_fieldに表示
        if self.code_list:
            cmds.cmdScrollFieldExecuter(self.script_editor, e=True, t=self.code_list[0])
        else:
            cmds.cmdScrollFieldExecuter(self.script_editor, e=True, clear=True)

        self.statusBar().showMessage("Completion Finish. (Log files:{})".format(self.session_log_dir))

        self.export_log()
        self.export_scripts()

    @retry_decorator
    def completion(self):
        
        result = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=self.messages, 
            stream=True
        )
        
        message_text = "" 
        for chunk in result:
            if chunk:
                content = chunk['choices'][0]['delta'].get('content')
                if content:
                    message_text += content
                    yield content
        else:
            self.messages.append({'role': 'assistant', 'content': message_text})

    def voice_synthesis_thread(self):

        while not (self._exit_flag and self.q_voice_synthesis.empty()):
            try:
                text = self.q_voice_synthesis.get(timeout=1)
            except queue.Empty:
                continue
            
            wav_path = self.voice_generator.text2voice(text, 
                                str(time.time()), 
                                path=os.getenv('TEMP'), 
                                speaker=47,
                                speed=1.1,
                                pitch=0,
                                intonation=1, 
                                volume=1,
                                post=0.1)
        
            if wav_path:
                self.q_voice_play.put(wav_path)

            self.q_voice_synthesis.task_done()

    def voice_play_thread(self):
        
        while not (self._exit_flag and self.q_voice_play.empty()):
            try:
                wav_path = self.q_voice_play.get(timeout=1)
            except queue.Empty:
                continue

            self.voice_generator.play_wave(wav=wav_path, delete=True)

            self.q_voice_play.task_done()

    # UserPrefs
    def get_user_prefs(self, *args):
        self.user_settings_ini.beginGroup('MainWindow')
        self.restoreGeometry(self.user_settings_ini.value('geometry'))
        self.user_settings_ini.endGroup()

    def save_user_prefs(self, *args):
        self.user_settings_ini.beginGroup('MainWindow')
        self.user_settings_ini.setValue('geometry', self.saveGeometry())
        self.user_settings_ini.endGroup()
        self.user_settings_ini.sync()

    def reset_user_prefs(self, *args):
        x, y, w, h = DEFAULT_GEOMETORY
        self.setGeometry(x, y, w, h)
    
    def init_ui(self, *args):
        self.reset_user_prefs()
        self.setWindowTitle('{0} {1}'.format(TITLE, VERSION))

        # Actions
        reset_user_prefsAction = QtWidgets.QAction("Reset Window Pos/Size", self)
        reset_user_prefsAction.setShortcut("Ctrl+R")
        reset_user_prefsAction.triggered.connect(self.reset_user_prefs)

        # Exit Action
        exitAction = QtWidgets.QAction("Exit", self)
        exitAction.setShortcut("Ctrl+Q")
        exitAction.triggered.connect(self.close)

        # Settings Action
        
        # About Action
        aboutAction = QtWidgets.QAction('About', self)
        aboutAction.triggered.connect(self.about)

        # menu bar
        menuBar = self.menuBar()

        fileMenu = menuBar.addMenu("File")
        fileMenu.addAction(reset_user_prefsAction)
        fileMenu.addSeparator()
        fileMenu.addAction(exitAction)
        
        """ settingsMenu = menuBar.addMenu("Settings")
        settingsMenu.addAction(voiceAction) """
        
        helpMenu = menuBar.addMenu("Help")
        helpMenu.addAction(aboutAction)
        
        # statusBar
        self.statusBar().showMessage("Ready.")

        # Chat field
        self.new_button = QtWidgets.QPushButton('New Chat')
        self.new_button.clicked.connect(self.new_chat)

        self.chat_history_model = QtCore.QStringListModel()

        self.chat_history_view = QtWidgets.QListView()
        self.chat_history_view.setModel(self.chat_history_model)
        self.chat_history_view.setWordWrap(True)
        self.chat_history_view.setAlternatingRowColors(True)
        self.chat_history_view.setStyleSheet("""
            QListView::item { border-bottom: 0px solid; padding: 5px; }
            QListView::item { background-color: #2a2b36; }
            QListView::item:alternate { background-color: #434554; }
            """)

        # user input
        self.user_input = QtWidgets.QPlainTextEdit()
        self.user_input.setPlaceholderText("Send a message...")
        self.user_input.setFixedHeight(100)

        self.send_button = QtWidgets.QPushButton("Send")
        self.send_button.clicked.connect(self.send_message)

        vBoxLayout1 = QtWidgets.QVBoxLayout()
        vBoxLayout1.addWidget(self.new_button)
        vBoxLayout1.addWidget(self.chat_history_view)
        vBoxLayout1.addWidget(self.user_input)
        vBoxLayout1.addWidget(self.send_button)

        # script editor field
        self.script_editor = cmds.cmdScrollFieldExecuter(st='python', sln=True)
        script_editor_ptr = OpenMayaUI.MQtUtil.findControl(self.script_editor)
        script_editor_widget = wrapInstance(int(script_editor_ptr), QtWidgets.QWidget)

        self.choice_script = QtWidgets.QComboBox()
        self.choice_script.setEditable(False)
        self.choice_script.setMaximumSize(100, 30)
        self.choice_script.currentTextChanged.connect(self.change_script)

        self.execute_button = QtWidgets.QPushButton('Execute')
        self.execute_button.clicked.connect(self.execute_script)

        hBoxLayout2 = QtWidgets.QHBoxLayout()
        hBoxLayout2.addWidget(self.choice_script)
        hBoxLayout2.addWidget(self.execute_button)
        
        vBoxLayout2 = QtWidgets.QVBoxLayout()
        vBoxLayout2.addWidget(script_editor_widget)
        vBoxLayout2.addLayout(hBoxLayout2)

        main_layout = QtWidgets.QHBoxLayout(self)
        main_layout.setSizeConstraint(QtWidgets.QLayout.SetMinAndMaxSize)
        main_layout.addLayout(vBoxLayout1)
        main_layout.addLayout(vBoxLayout2)

        widget = QtWidgets.QWidget(self)
        widget.setLayout(main_layout)
        self.setCentralWidget(widget)
    
    def update_scripts(self, *args):
        self.choice_script.clear()
        for i in range(int(len(self.code_list))):
            self.choice_script.addItems(str(i+1))

    def change_script(self, item, *args):
        if item:
            cmds.cmdScrollFieldExecuter(self.script_editor, e=True, t=self.code_list[int(item)-1])

    def execute_script(self, *args):
        code = cmds.cmdScrollFieldExecuter(self.script_editor, q=True, t=True)
        if code:
            exec(code, {'__name__': '__main__'}, None)

    def export_log(self, *args):
        log_file_path = os.path.join(self.session_log_dir, 'messages.json')
        try:
            with open(log_file_path, 'w', encoding='utf-8-sig') as f:
                json.dump(self.messages, f, indent=4, ensure_ascii=False)
        except:
            pass

    def export_scripts(self, index=None, *args):
        export_code_list = []
        if index:
            export_code_list = [self.code_list[index]]
        else:
            export_code_list = self.code_list
        
        file_name_prefix = datetime.now().strftime('script_%H%M%S')
        for i, code in enumerate(export_code_list):
            code_file_path = os.path.join(self.session_log_dir, '{}_{}.py'.format(file_name_prefix, str(i).zfill(2)))
            try:
                with open(code_file_path, 'w', encoding='utf-8-sig') as f:
                    f.writelines(code)
            except:
                pass

    def about(self, *args):
        QtWidgets.QMessageBox.about(self, 'About ' + TITLE, ABOUT_TXT)

    def closeEvent(self, event):
        self.save_user_prefs()
        self._exit_flag = True
        self.statusBar().showMessage("Closing...")
        self.executor.shutdown(wait=True)

def showUI():
    ptr = OpenMayaUI.MQtUtil.mainWindow()
    mayaMainWindow = wrapInstance(int(ptr), QtWidgets.QMainWindow)
    window = ChatMaya(parent=mayaMainWindow)
    window.show()