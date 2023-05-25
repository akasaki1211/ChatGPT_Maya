# -*- coding: utf-8 -*-
import json
import re
import copy
from uuid import uuid4
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
import queue
import keyboard
import subprocess

from maya import cmds, OpenMaya, OpenMayaUI
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
    SYSTEM_TEMPLATE_MEL,
    USER_TEMPLATE,
    FIX_TEMPLATE
)
from .openai_utils import (
    num_tokens_from_text, 
    chat_completion_stream
)
from .voice import (
    text2voice, 
    play_wave
)
from .exec_code import (
    exec_mel,
    exec_py
)

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
        #self.last_user_message = ""
        self.last_error = None
        self.leave_codeblocks = False
        self.max_total_token = MAX_MESSAGES_TOKEN
        self.init_variables()
        
        # User Prefs
        self.user_settings_ini = QtCore.QSettings(str(USER_SETTINGS_INI), QtCore.QSettings.IniFormat)
        self.user_settings_ini.setIniCodec('utf-8')
        self.settings = Settings()
        self.apply_settings(self.settings.get_settings())

        # Build UI
        self.init_ui()
        self.get_user_prefs()
        
    def init_variables(self, *args):
        self.session_id = datetime.now().strftime('session_%y%m%d_%H%M%S')
        self.session_log_dir = Path(LOG_DIR / self.session_id)
        #print("log dir : {}".format(self.session_log_dir))

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

        """ user_prompt = USER_TEMPLATE.format(
            script_type="Maya Python" if self.script_type == "python" else "MEL", 
            questions=self.last_user_message)
        self.messages[-1] = {"role": "user", "content": user_prompt} """

        self.__stop_completion = False
        self.generate_message()

    def delete_last_message(self):
        self.chat_history_model.removeRows(self.chat_history_model.rowCount() - 2, 2)
        self.messages.pop(-1)
        self.messages.pop(-1)
        self.export_log()

    """ @retry_decorator
    def completion(self):
        
        result = openai.ChatCompletion.create(
            model=self.completion_model,
            temperature=self.completion_temperature,
            top_p=self.completion_top_p,
            presence_penalty=self.completion_presence_penalty,
            frequency_penalty=self.completion_frequency_penalty,
            messages=self.messages, 
            stream=True
        )
        
        for chunk in result:
            if chunk:
                content = chunk['choices'][0]['delta'].get('content')
                if content:
                    yield content """

    """ def num_tokens_from_text(self, text:str) -> int:
        encoding = tiktoken.encoding_for_model(self.completion_model)
        return len(encoding.encode(text)) """
    
    def shrink_messages(self, messages:list) -> list:
        messages.pop(1)
        content_list = [msg["content"] for msg in messages]
        prompt_tokens = num_tokens_from_text("".join(content_list))
        if prompt_tokens > self.max_total_token:
            messages = self.shrink_messages(messages)
        return messages

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
    
    def apply_settings(self, data:dict, *args):
        try:
            self.completion_model = data["completion"]["model"]
            self.completion_temperature = float(data["completion"]["temperature"])
            self.completion_top_p = float(data["completion"]["top_p"])
            self.completion_presence_penalty = float(data["completion"]["presence_penalty"])
            self.completion_frequency_penalty = float(data["completion"]["frequency_penalty"])
            self.voice_speakerid = int(data["voice"]["speakerid"])
            self.voice_speed = float(data["voice"]["speed"])
            self.voice_pitch = float(data["voice"]["pitch"])
            self.voice_intonation = float(data["voice"]["intonation"])
            self.voice_volume = float(data["voice"]["volume"])
            self.voice_post = float(data["voice"]["post"])
        except:
            self.completion_model = "gpt-3.5-turbo"
            self.completion_temperature = 0.7
            self.completion_top_p = 1
            self.completion_presence_penalty = 0
            self.completion_frequency_penalty = 0
            self.voice_speakerid = 47
            self.voice_speed = 1
            self.voice_pitch = 0
            self.voice_intonation = 1
            self.voice_volume = 1
            self.voice_post = 0.1
            cmds.error("Settings could not be applied. Use default settings.")

    def open_settings_dialog(self, *args):
        self.settings.update()
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
        hBoxLayout1.addWidget(self.script_type_rbtn_1)
        hBoxLayout1.addWidget(self.script_type_rbtn_2)

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

class Settings(object):

    def __init__(self):
        self.filepath = USER_SETTINGS_JSON
        
        self._data = self.__import_from_file()

        if not self._data:
            # default settings
            self._data = {
                "completion":{
                    "model": "gpt-3.5-turbo",
                    "temperature": 0.7,
                    "top_p": 1.0,
                    "presence_penalty": 0.0,
                    "frequency_penalty": 0.0
                },
                "voice":{
                    "speakerid": 47,
                    "speed": 1.1,
                    "pitch": 0.0,
                    "intonation": 1.0,
                    "volume": 1.0,
                    "post": 0.1
                }
            }
        
        self.__export_file()

    def get_settings(self, *args):
        return copy.deepcopy(self._data)
    
    def update(self, *args):
        data, accepted = SettingsDialog.set(parent=maya_main_window(), data=self._data)
        
        if not accepted:
            return

        self._data = data        
        self.__export_file()

    def __import_from_file(self, *args):
        if not self.filepath.is_file():
            return

        try:
            with open(self.filepath, 'r') as f:
                data = json.load(f)
            return data
        except:
            return

    def __export_file(self, *args):
        try:
            with open(self.filepath, 'w', encoding='utf-8') as f:
                json.dump(self._data, f, indent=4)
            return True
        except:
            return

class SettingsDialog(QtWidgets.QDialog):
    
    def __init__(self, parent=None, *args):
        super(SettingsDialog, self).__init__(parent, *args)
        self.data = {}
    
    def init_UI(self, *args):
        self.setWindowTitle('Settings')
        
        # Completion Settings group
        completion_group = QtWidgets.QGroupBox("ChatCompletion")
        completion_layout = QtWidgets.QFormLayout(completion_group)

        # model
        self.model_combobox = QtWidgets.QComboBox()
        self.model_combobox.addItem("gpt-3.5-turbo")
        self.model_combobox.addItem("gpt-4")
        self.model_combobox.setMinimumWidth(100)
        
        completion_layout.addRow("Model:", self.model_combobox)

        # temperature
        self.temperature_spinbox = QtWidgets.QDoubleSpinBox(self)
        self.temperature_spinbox.setRange(0.0, 2.0)
        self.temperature_spinbox.setSingleStep(0.1)
        self.temperature_spinbox.setMinimumWidth(100)
        completion_layout.addRow("Temperature:", self.temperature_spinbox)

        # top_p
        self.top_p_spinbox = QtWidgets.QDoubleSpinBox(self)
        self.top_p_spinbox.setRange(0.0, 2.0)
        self.top_p_spinbox.setSingleStep(0.1)
        self.top_p_spinbox.setMinimumWidth(100)
        completion_layout.addRow("Top P:", self.top_p_spinbox)

        # presence_penalty
        self.presence_penalty_spinbox = QtWidgets.QDoubleSpinBox(self)
        self.presence_penalty_spinbox.setRange(0.0, 2.0)
        self.presence_penalty_spinbox.setSingleStep(0.1)
        self.presence_penalty_spinbox.setMinimumWidth(100)
        completion_layout.addRow("Presence Penalty:", self.presence_penalty_spinbox)

        # frequency_penalty
        self.frequency_penalty_spinbox = QtWidgets.QDoubleSpinBox(self)
        self.frequency_penalty_spinbox.setRange(0.0, 2.0)
        self.frequency_penalty_spinbox.setSingleStep(0.1)
        self.frequency_penalty_spinbox.setMinimumWidth(100)
        completion_layout.addRow("Frequency Penalty:", self.frequency_penalty_spinbox)
        
        # Voice Settings group
        voice_group = QtWidgets.QGroupBox("VOICEVOX")
        voice_layout = QtWidgets.QFormLayout(voice_group)

        # speakerid
        self.speakerid_spinbox = QtWidgets.QSpinBox(self)
        self.speakerid_spinbox.setMinimumWidth(60)
        voice_layout.addRow("Speaker ID:", self.speakerid_spinbox)

        # speed
        self.speed_spinbox = QtWidgets.QDoubleSpinBox(self)
        self.speed_spinbox.setRange(0.5, 2.0)
        self.speed_spinbox.setSingleStep(0.1)
        self.speed_spinbox.setMinimumWidth(60)
        voice_layout.addRow("Speed:", self.speed_spinbox)

        # pitch
        self.pitch_spinbox = QtWidgets.QDoubleSpinBox(self)
        self.pitch_spinbox.setRange(-0.15, 0.15)
        self.pitch_spinbox.setSingleStep(0.01)
        self.pitch_spinbox.setMinimumWidth(60)
        voice_layout.addRow("Pitch:", self.pitch_spinbox)

        # intonation
        self.intonation_spinbox = QtWidgets.QDoubleSpinBox(self)
        self.intonation_spinbox.setRange(0.0, 2.0)
        self.intonation_spinbox.setSingleStep(0.1)
        self.intonation_spinbox.setMinimumWidth(60)
        voice_layout.addRow("Intonation:", self.intonation_spinbox)

        # volume
        self.volume_spinbox = QtWidgets.QDoubleSpinBox(self)
        self.volume_spinbox.setRange(0.0, 5.0)
        self.volume_spinbox.setSingleStep(0.1)
        self.volume_spinbox.setMinimumWidth(60)
        voice_layout.addRow("Volume:", self.volume_spinbox)

        # post
        self.post_spinbox = QtWidgets.QDoubleSpinBox(self)
        self.post_spinbox.setRange(0.0, 1.5)
        self.post_spinbox.setSingleStep(0.1)
        self.post_spinbox.setMinimumWidth(60)
        voice_layout.addRow("Post:", self.post_spinbox)

        # Buttons
        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel,
            QtCore.Qt.Horizontal,
            self
        )
        buttons.accepted.connect(self.save_and_accept)
        buttons.rejected.connect(self.reject)

        settings_layout = QtWidgets.QHBoxLayout()
        settings_layout.addWidget(completion_group)
        settings_layout.addWidget(voice_group)
        
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.addLayout(settings_layout)
        main_layout.addWidget(buttons)

    def set_UI_values(self, *args):
        try:
            self.model_combobox.setCurrentText(self.data["completion"]["model"])
            self.temperature_spinbox.setValue(self.data["completion"]["temperature"])
            self.top_p_spinbox.setValue(self.data["completion"]["top_p"])
            self.presence_penalty_spinbox.setValue(self.data["completion"]["presence_penalty"])
            self.frequency_penalty_spinbox.setValue(self.data["completion"]["frequency_penalty"])

            self.speakerid_spinbox.setValue(self.data["voice"]["speakerid"])
            self.speed_spinbox.setValue(self.data["voice"]["speed"])
            self.pitch_spinbox.setValue(self.data["voice"]["pitch"])
            self.intonation_spinbox.setValue(self.data["voice"]["intonation"])
            self.volume_spinbox.setValue(self.data["voice"]["volume"])
            self.post_spinbox.setValue(self.data["voice"]["post"])
        except:
            pass
    
    def save_and_accept(self):
        self.data["completion"] = {}
        self.data["voice"] = {}
        self.data["completion"]["model"] = self.model_combobox.currentText()
        self.data["completion"]["temperature"] = round(self.temperature_spinbox.value(), 2)
        self.data["completion"]["top_p"] = round(self.top_p_spinbox.value(), 2)
        self.data["completion"]["presence_penalty"] = round(self.presence_penalty_spinbox.value(), 2)
        self.data["completion"]["frequency_penalty"] = round(self.frequency_penalty_spinbox.value(), 2)
        self.data["voice"]["speakerid"] = self.speakerid_spinbox.value()
        self.data["voice"]["speed"] = round(self.speed_spinbox.value(), 2)
        self.data["voice"]["pitch"] = round(self.pitch_spinbox.value(), 2)
        self.data["voice"]["intonation"] = round(self.intonation_spinbox.value(), 2)
        self.data["voice"]["volume"] = round(self.volume_spinbox.value(), 2)
        self.data["voice"]["post"] = round(self.post_spinbox.value(), 2)

        self.accept() 
    
    @staticmethod
    def set(parent=None, data:dict={}, *args):
        dialog = SettingsDialog(parent)
        dialog.data = data
        dialog.init_UI()
        dialog.set_UI_values()
        result = dialog.exec_()

        return (dialog.data, result == QtWidgets.QDialog.Accepted)
