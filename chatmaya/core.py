# -*- coding: utf-8 -*-
import json
import re
from uuid import uuid4
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
import queue
import keyboard
import subprocess

from maya import cmds, OpenMaya, OpenMayaUI
from PySide2 import QtWidgets, QtCore
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
    SYSTEM_TEMPLATE_MEL,
    USER_TEMPLATE,
    FIX_TEMPLATE
)
from .openai_utils import (
    num_tokens_from_text, 
    chat_completion_stream,
    DEFAULT_CHAT_MODEL
)
from .voice import (
    text2voice, 
    play_wave
)
from .exec_code import (
    exec_mel,
    exec_py
)
from .settings import Settings, SettingsData

MAX_MESSAGES_TOKEN = 2500
DEFAULT_GEOMETORY = (400, 300, 900, 600)

def maya_main_window():
    main_window_ptr = OpenMayaUI.MQtUtil.mainWindow()
    return wrapInstance(int(main_window_ptr), QtWidgets.QMainWindow)

def showUI():
    window = ChatMaya(parent=maya_main_window())
    window.show()

class ChatMaya(QtWidgets.QMainWindow):

    def __init__(self, parent=None, *args, **kwargs):
        super(ChatMaya, self).__init__(parent, *args, **kwargs)

        self._exit_flag = False

        # voice
        self.q_voice_synthesis = queue.Queue()
        self.q_voice_play = queue.Queue()
        self.voice_dir = Path.home() / 'AppData' / 'Local' / 'Temp'

        self.__stop_completion = False

        # thread
        self.executor = ThreadPoolExecutor(max_workers=2)
        self.executor.submit(self.voice_synthesis_thread)
        self.executor.submit(self.voice_play_thread)

        # settings
        self.script_type = "python"
        self.last_error = None
        self.leave_codeblocks = False
        self.max_total_token = MAX_MESSAGES_TOKEN
        self.init_variables()
        
        # User Prefs
        self.user_settings_ini = QtCore.QSettings(str(USER_SETTINGS_INI), QtCore.QSettings.IniFormat)
        self.user_settings_ini.setIniCodec('utf-8')
        self.completion_model = DEFAULT_CHAT_MODEL
        self.settings = Settings()
        self.apply_settings(self.settings.get_settings())

        # Build UI
        self.init_ui()
        self.get_user_prefs()
        
    def init_variables(self, *args):
        self.session_id = datetime.now().strftime('session_%y%m%d_%H%M%S')
        self.session_log_dir = Path(LOG_DIR / self.session_id)

        self.messages = [self.set_system_message(self.script_type)]
        self.code_list = []
        self.total_tokens = 0

    def set_system_message(self, type:str="python", *args):
        if type == "python":
            return {"role":"system", "content":SYSTEM_TEMPLATE_PY}
        elif type == "mel":
            return {"role":"system", "content":SYSTEM_TEMPLATE_MEL}

    def decompose_response(self, txt:str):
        if self.script_type == "python":
            pattern = r"```python([\s\S]*?)```"
        else:
            pattern = r"```mel([\s\S]*?)```"
        
        code_list = re.findall(pattern, txt)
        code_list = [code.strip() for code in code_list]
        
        comment = re.sub(pattern, '', txt)
        comment = re.sub('[\r?\n]+', '\n', comment)
        comment = comment.strip()
        
        return comment.strip(), code_list

    def new_chat(self, *args):
        self.init_variables()
        self.update_scripts()
        cmds.cmdScrollFieldExecuter(self.script_editor_py, e=True, clear=True)
        cmds.cmdScrollFieldExecuter(self.script_editor_mel, e=True, clear=True)
        self.fix_error_button.setEnabled(False)
        self.chat_history_model.removeRows(0, self.chat_history_model.rowCount())
        self.statusBar().showMessage("New Chat")

    def generate_message(self, *args):
        
        message_text = ""
        sentence = ""
        sentence_end_chars = "。！？:"
        backquote_count = 0
        is_code_block = False

        self.statusBar().showMessage("Completion... (Press Esc to stop)")

        # prompt tokens
        content_list = [msg["content"] for msg in self.messages]
        prompt_tokens = num_tokens_from_text("".join(content_list))

        if prompt_tokens > self.max_total_token:
            self.messages = self.shrink_messages(self.messages)

        content_list = [msg["content"] for msg in self.messages]
        prompt_tokens = num_tokens_from_text("".join(content_list))

        self.total_tokens += prompt_tokens

        # APIコール
        try:
            options = {
                "temperature": self.completion_temperature,
                "top_p": self.completion_top_p,
                "presence_penalty": self.completion_presence_penalty,
                "frequency_penalty": self.completion_frequency_penalty,
            }

            for content in chat_completion_stream(messages=self.messages, model=self.completion_model, **options):
                if keyboard.is_pressed('esc'):
                    self.__stop_completion = True
                    break
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
                            # ボイス合成キューに１文ずつ追加
                            self.q_voice_synthesis.put(sentence.strip())
                            backquote_count = 0
                        sentence = ""

        except Exception as e:
            cmds.error(str(e))
            self.messages.append({'role': 'assistant', 'content': ''})
            self.chat_history_model.setData(
                        self.chat_history_model.index(self.chat_history_model.rowCount() - 1), 
                        '')
            return
        
        self.messages.append({'role': 'assistant', 'content': message_text})

        # log出力
        self.export_log()

        # Escが押されたらここで終了
        if self.__stop_completion:
            self.statusBar().showMessage("Stop Completion.")
            return

        # completion tokens
        completion_tokens = num_tokens_from_text(message_text)
        self.total_tokens += completion_tokens

        # 最後の文が句読点で終わっていない場合
        if sentence.strip():
            if not is_code_block:
                self.q_voice_synthesis.put(sentence.strip())

        # 返答を分解
        comment, self.code_list = self.decompose_response(message_text)

        # スクリプト出力
        self.export_scripts()

        # Pythonコード以外の部分を表示
        if not self.leave_codeblocks:
            self.chat_history_model.setData(
                        self.chat_history_model.index(self.chat_history_model.rowCount() - 1), 
                        comment)
        self.chat_history_view.scrollToBottom()

        # Scriptsプルダウンを更新
        self.update_scripts()

        # コードの1つ目をscript_editorに表示
        if self.script_type == "python":
            editor = self.script_editor_py
        else:
            editor = self.script_editor_mel
        if self.code_list:
            cmds.cmdScrollFieldExecuter(editor, e=True, t=self.code_list[0])
        else:
            cmds.cmdScrollFieldExecuter(editor, e=True, clear=True)
        self.fix_error_button.setEnabled(False)

        self.statusBar().showMessage("Completion Finish. ({} prompt + {} completion = {} tokens) Total:{}".format(
            prompt_tokens,
            completion_tokens,
            prompt_tokens + completion_tokens,
            self.total_tokens
        ))

    def send_message(self):
        user_message = self.user_input.toPlainText()
        if not user_message:
            return
        
        self.chat_history_model.insertRow(self.chat_history_model.rowCount())
        self.chat_history_model.setData(
            self.chat_history_model.index(self.chat_history_model.rowCount() - 1), 
            user_message)
        self.user_input.clear()

        self.chat_history_model.insertRow(self.chat_history_model.rowCount())

        user_prompt = USER_TEMPLATE.format(
            script_type="Maya Python" if self.script_type == "python" else "MEL", 
            questions=user_message)
        self.messages.append({"role": "user", "content": user_prompt})
        #self.last_user_message = user_message

        self.__stop_completion = False
        self.generate_message()

    def send_fix_message(self):
        if self.last_error == 0:
            return
        
        prompt = FIX_TEMPLATE.format(error=self.last_error)
        self.messages.append({"role": "user", "content": prompt})

        self.chat_history_model.insertRow(self.chat_history_model.rowCount())
        self.chat_history_model.setData(
            self.chat_history_model.index(self.chat_history_model.rowCount() - 1), 
            prompt)
        self.user_input.clear()

        self.chat_history_model.insertRow(self.chat_history_model.rowCount())

        self.__stop_completion = False
        self.generate_message()

    def regenerate_message(self):
        if len(self.messages) < 2:
            return
        
        self.chat_history_model.setData(
            self.chat_history_model.index(self.chat_history_model.rowCount() - 1), 
            '')
        
        self.messages.pop(-1)

        self.__stop_completion = False
        self.generate_message()

    def delete_last_message(self):
        self.chat_history_model.removeRows(self.chat_history_model.rowCount() - 2, 2)
        self.messages.pop(-1)
        self.messages.pop(-1)
        self.export_log()
    
    def shrink_messages(self, messages:list) -> list:
        messages.pop(1)
        content_list = [msg["content"] for msg in messages]
        prompt_tokens = num_tokens_from_text("".join(content_list))
        if prompt_tokens > self.max_total_token:
            messages = self.shrink_messages(messages)
        return messages

    def execute_script(self, *args):
        cmds.cmdScrollFieldReporter(self.script_reporter, e=True, clear=True)

        if self.script_type == "python":
            code = cmds.cmdScrollFieldExecuter(self.script_editor_py, q=True, text=True)
            result = exec_py(code)
            if result != 0:
                OpenMaya.MGlobal.displayError(result)
        else:
            code = cmds.cmdScrollFieldExecuter(self.script_editor_mel, q=True, text=True)
            result = exec_mel(code)

        self.last_error = result

        self.fix_error_button.setEnabled(False if result == 0 else True)

    # voice
    def voice_synthesis_thread(self):

        while not (self._exit_flag and self.q_voice_synthesis.empty()):
            try:
                text = self.q_voice_synthesis.get(timeout=1)
            except queue.Empty:
                continue
            
            wav_path = text2voice(
                text, 
                str(uuid4()), 
                path=self.voice_dir, 
                speaker=self.voice_speakerid,
                speed=self.voice_speed,
                pitch=self.voice_pitch,
                intonation=self.voice_intonation, 
                volume=self.voice_volume,
                post=self.voice_post
            )

            if wav_path:
                self.q_voice_play.put(wav_path)

            self.q_voice_synthesis.task_done()

    def voice_play_thread(self):
        
        while not (self._exit_flag and self.q_voice_play.empty()):
            try:
                wav_path = self.q_voice_play.get(timeout=1)
            except queue.Empty:
                continue

            play_wave(wav=wav_path, delete=True)

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
    
    def apply_settings(self, data:SettingsData, *args):
        self.completion_temperature = float(data.completion.temperature)
        self.completion_top_p = float(data.completion.top_p)
        self.completion_presence_penalty = float(data.completion.presence_penalty)
        self.completion_frequency_penalty = float(data.completion.frequency_penalty)
        self.voice_speakerid = int(data.voice.speakerid)
        self.voice_speed = float(data.voice.speed)
        self.voice_pitch = float(data.voice.pitch)
        self.voice_intonation = float(data.voice.intonation)
        self.voice_volume = float(data.voice.volume)
        self.voice_post = float(data.voice.post)

    def open_settings_dialog(self, *args):
        self.settings.update(parent=maya_main_window())
        self.apply_settings(self.settings.get_settings())

    # UI
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
        settingsAction = QtWidgets.QAction('Open Settings Dialog', self)
        settingsAction.triggered.connect(self.open_settings_dialog)

        leaveCodeblocksAction = QtWidgets.QAction('Leave codeblocks in chat area', self)
        leaveCodeblocksAction.setCheckable(True)
        leaveCodeblocksAction.setChecked(self.leave_codeblocks)
        leaveCodeblocksAction.setStatusTip(u'コードブロックをチャット領域にも残しておく')
        leaveCodeblocksAction.toggled.connect(self.toggle_leave_codeblocks)
        
        # About Action
        aboutAction = QtWidgets.QAction('About', self)
        aboutAction.triggered.connect(self.about)

        # menu bar
        menuBar = self.menuBar()

        fileMenu = menuBar.addMenu("File")
        fileMenu.addAction(reset_user_prefsAction)
        fileMenu.addSeparator()
        fileMenu.addAction(exitAction)
        
        settingsMenu = menuBar.addMenu("Settings")
        settingsMenu.addAction(settingsAction)
        settingsMenu.addSeparator()
        settingsMenu.addAction(leaveCodeblocksAction)
        
        helpMenu = menuBar.addMenu("Help")
        helpMenu.addAction(aboutAction)
        
        # statusBar
        self.statusBar().showMessage("Ready.")

        # chat
        chat_model_cbx = QtWidgets.QComboBox()
        chat_model_cbx.addItems(['gpt-3.5-turbo', 'gpt-4'])
        chat_model_cbx.setCurrentText(DEFAULT_CHAT_MODEL)
        chat_model_cbx.currentTextChanged.connect(self.change_model)

        new_button = QtWidgets.QPushButton('New Chat')
        new_button.clicked.connect(self.new_chat)

        log_dir_button = QtWidgets.QPushButton('Log')
        log_dir_button.setMaximumWidth(50)
        log_dir_button.clicked.connect(self.open_log_dir)
        
        self.script_type_rbtn_1 = QtWidgets.QRadioButton("Python")
        self.script_type_rbtn_1.setChecked(True)
        self.script_type_rbtn_1.setMaximumWidth(80)
        self.script_type_rbtn_1.toggled.connect(self.toggle_script_type)

        self.script_type_rbtn_2 = QtWidgets.QRadioButton("MEL")
        self.script_type_rbtn_2.setMaximumWidth(80)

        hBoxLayout1 = QtWidgets.QHBoxLayout()
        hBoxLayout1.addWidget(new_button)
        hBoxLayout1.addWidget(log_dir_button)
        
        hBoxLayout3 = QtWidgets.QHBoxLayout()
        hBoxLayout3.addWidget(chat_model_cbx)
        hBoxLayout3.addWidget(self.script_type_rbtn_1)
        hBoxLayout3.addWidget(self.script_type_rbtn_2)

        # chat history
        self.chat_history_model = QtCore.QStringListModel()

        self.chat_history_view = QtWidgets.QListView()
        self.chat_history_view.setModel(self.chat_history_model)
        self.chat_history_view.setWordWrap(True)
        self.chat_history_view.setAlternatingRowColors(True)
        self.chat_history_view.setStyleSheet("""
            QListView::item { border-bottom: 0px solid; padding: 5px; }
            QListView::item { background-color: #27272e; }
            QListView::item:alternate { background-color: #363842; }
            """)

        # user input
        self.user_input = QtWidgets.QPlainTextEdit()
        self.user_input.setPlaceholderText("Send a message...")
        self.user_input.setFixedHeight(100)

        send_button = QtWidgets.QPushButton("Send")
        send_button.clicked.connect(self.send_message)

        regenerate_button = QtWidgets.QPushButton("Regenerate")
        regenerate_button.setMaximumWidth(120)
        regenerate_button.clicked.connect(self.regenerate_message)

        delete_last_button = QtWidgets.QPushButton("Delete last")
        delete_last_button.setMaximumWidth(80)
        delete_last_button.clicked.connect(self.delete_last_message)
        
        hBoxLayout2 = QtWidgets.QHBoxLayout()
        hBoxLayout2.addWidget(send_button)
        hBoxLayout2.addWidget(regenerate_button)
        hBoxLayout2.addWidget(delete_last_button)

        vBoxLayout1 = QtWidgets.QVBoxLayout()
        vBoxLayout1.addLayout(hBoxLayout3)
        vBoxLayout1.addLayout(hBoxLayout1)
        vBoxLayout1.addWidget(self.chat_history_view)
        vBoxLayout1.addWidget(self.user_input)
        vBoxLayout1.addLayout(hBoxLayout2)

        self.script_reporter = cmds.cmdScrollFieldReporter(clr=True)
        script_reporter_ptr = OpenMayaUI.MQtUtil.findControl(self.script_reporter)
        self.script_reporter_widget = wrapInstance(int(script_reporter_ptr), QtWidgets.QWidget)
        self.script_reporter_widget.setMaximumSize(1000000, 120)

        # script editor field
        self.script_editor_py = cmds.cmdScrollFieldExecuter(st="python", sln=True)
        script_editor_ptr_py = OpenMayaUI.MQtUtil.findControl(self.script_editor_py)
        self.script_editor_widget_py = wrapInstance(int(script_editor_ptr_py), QtWidgets.QWidget)
        
        self.script_editor_mel = cmds.cmdScrollFieldExecuter(st="mel", sln=True)
        script_editor_ptr_mel = OpenMayaUI.MQtUtil.findControl(self.script_editor_mel)
        self.script_editor_widget_mel = wrapInstance(int(script_editor_ptr_mel), QtWidgets.QWidget)

        self.stacked_widget = QtWidgets.QStackedWidget()
        self.stacked_widget.addWidget(self.script_editor_widget_py)
        self.stacked_widget.addWidget(self.script_editor_widget_mel)
        
        self.choice_script = QtWidgets.QComboBox()
        self.choice_script.setEditable(False)
        self.choice_script.setMaximumWidth(80)
        self.choice_script.currentTextChanged.connect(self.change_script)

        self.execute_button = QtWidgets.QPushButton('Execute')
        self.execute_button.clicked.connect(self.execute_script)

        self.fix_error_button = QtWidgets.QPushButton('Fix Error')
        self.fix_error_button.setMaximumWidth(100)
        self.fix_error_button.setEnabled(False)
        self.fix_error_button.clicked.connect(self.send_fix_message)

        hBoxLayout2 = QtWidgets.QHBoxLayout()
        hBoxLayout2.addWidget(self.choice_script)
        hBoxLayout2.addWidget(self.execute_button)
        hBoxLayout2.addWidget(self.fix_error_button)
        
        vBoxLayout2 = QtWidgets.QVBoxLayout()
        vBoxLayout2.addWidget(self.script_reporter_widget)
        vBoxLayout2.addWidget(self.stacked_widget)
        vBoxLayout2.addLayout(hBoxLayout2)

        main_layout = QtWidgets.QHBoxLayout(self)
        main_layout.setSizeConstraint(QtWidgets.QLayout.SetMinAndMaxSize)
        main_layout.addLayout(vBoxLayout1)
        main_layout.addLayout(vBoxLayout2)

        widget = QtWidgets.QWidget(self)
        widget.setLayout(main_layout)
        self.setCentralWidget(widget)
    
    def change_model(self, text, *args):
        self.completion_model = text

    def toggle_leave_codeblocks(self, flag, *args):
        self.leave_codeblocks = flag

    def toggle_script_type(self, *args):
        if self.script_type_rbtn_1.isChecked():
            self.script_type = "python"
            self.stacked_widget.setCurrentIndex(0)
        else:
            self.script_type = "mel"
            self.stacked_widget.setCurrentIndex(1)

        if self.messages:
            self.messages[0] = self.set_system_message(self.script_type)
        else:
            self.messages = [self.set_system_message(self.script_type)]

    def update_scripts(self, *args):
        self.choice_script.clear()
        for i in range(int(len(self.code_list))):
            self.choice_script.addItems(str(i+1))

    def change_script(self, item, *args):
        if item:
            if self.script_type == "python":
                editor = self.script_editor_py
            else:
                editor = self.script_editor_mel
            
            cmds.cmdScrollFieldExecuter(editor, e=True, t=self.code_list[int(item)-1])

    def about(self, *args):
        QtWidgets.QMessageBox.about(self, 'About ' + TITLE, ABOUT_TXT)

    def closeEvent(self, event):
        self.save_user_prefs()
        self._exit_flag = True
        self.executor.shutdown(wait=True)

    # export
    def export_log(self, *args):
        self.session_log_dir.mkdir(parents=True, exist_ok=True)
        log_file_path = Path(self.session_log_dir, 'messages.json')
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
        ext = '.py' if self.script_type == "python" else '.mel'

        for i, code in enumerate(export_code_list):
            code_file_path = Path(self.session_log_dir, '{}_{}{}'.format(file_name_prefix, str(i).zfill(2), ext))
            try:
                with open(code_file_path, 'w', encoding='utf-8-sig') as f:
                    f.writelines(code)
            except:
                pass

    def open_log_dir(self, *args):
        if self.session_log_dir.is_dir():
            subprocess.Popen('explorer {}'.format(self.session_log_dir))