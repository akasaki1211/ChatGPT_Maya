# -*- coding: utf-8 -*-
import os
import re
import json
from datetime import datetime

import openai

from maya import cmds

openai.api_key = os.getenv("OPENAI_API_KEY")

EXPORT_LOG = True
LOG_DIR = os.getenv("TEMP")

#SYSTEM_SETTINGS = u"""質問に対して、MayaのPythonスクリプトを書いてください。
#スクリプト以外の文章は短めにまとめてください。
#pythonのコードブロックは必ず ```python で開始してください。
#ayaに標準でインストールされていないパッケージやモジュールは使用しないでください。
#スクリプトを書くために情報が不足している場合は適宜質問してください。"""

SYSTEM_SETTINGS = """Write a Maya Python script in response to the question.
All text other than the script should be short and written in Japanese.
Python code blocks should always start with ```python.
Do not use packages or modules that are not installed as standard in Maya.
If information is missing for writing scripts, ask questions as appropriate."""

class ChatGPT_Maya(object):

    def __init__(self):
        self.system_settings = SYSTEM_SETTINGS
        
        self.init_variables()
        self.create_window()
    
    def init_variables(self, *args):
        self.message_log = []
        self.session_id = datetime.now().strftime('session_%y%m%d_%H%M%S')
        self.code_list = []

    def completion(self, 
                new_message_text:str, 
                settings_text:str='', 
                stream=True):
        
        if len(self.message_log) == 0 and len(settings_text) != 0:
            system = {"role": "system", "content": settings_text}
            self.message_log.append(system)

        new_message = {"role": "user", "content": new_message_text}
        self.message_log.append(new_message)

        result = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=self.message_log, 
            stream=stream
        )
        
        message_text = "" 
        for chunk in result:
            if chunk:
                content = chunk['choices'][0]['delta'].get('content')
                if content:
                    message_text += content
                    yield message_text
        else:
            self.message_log.append({'role': 'assistant', 'content': message_text})
            return message_text

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

    def reset_session(self, *args):
        self.init_variables()
        
        self.update_scripts()

        cmds.scrollField(self.input_field, e=True, tx='')
        cmds.scrollField(self.ai_comment, e=True, tx='')
        cmds.cmdScrollFieldExecuter(self.script_field, e=True, t='')

    def show_log(self, *args):
        #print(json.dumps(self.message_log, indent=4, ensure_ascii=False))
        
        for log in self.message_log:
            print('--'*30)
            print(log['role'] + ' :\n')
            print(log['content'])
        print('--'*30)
    
    def export_log(self, *args):
        log_file_path = os.path.join(LOG_DIR, self.session_id + '.json')
        try:
            with open(log_file_path, 'w', encoding='utf-8-sig') as f:
                json.dump(self.message_log, f, indent=4, ensure_ascii=False)
        except:
            pass
    
        log_file_path = os.path.join(LOG_DIR, self.session_id + '.txt')
        try:
            with open(log_file_path, 'w', encoding='utf-8-sig') as f:
                for log in self.message_log:
                    f.write('--'*30 + '\n')
                    f.write(log['role'] + ' :\n\n')
                    f.write(log['content'] + '\n')
                f.write('--'*30 + '\n')
        except:
            pass
        

    def export_scripts(self, index=None, *args):
        export_code_list = []
        if index:
            export_code_list = [self.code_list[index]]
        else:
            export_code_list = self.code_list
        
        file_name_prefix = datetime.now().strftime('script_%y%m%d_%H%M%S')
        for i, code in enumerate(export_code_list):
            code_file_path = os.path.join(LOG_DIR, '{}_{}.py'.format(file_name_prefix, str(i).zfill(2)))
            try:
                with open(code_file_path, 'w', encoding='utf-8-sig') as f:
                    f.writelines(code)
            except:
                pass

    def update_scripts(self, *args):
        menu_items = cmds.optionMenu(self.scripts, q=True, ill=True)
        if menu_items:
            cmds.deleteUI(menu_items)
            
        for i in range(int(len(self.code_list))):
            cmds.menuItem(p=self.scripts, l=str(i+1))

    def change_script(self, item, *args):
        cmds.cmdScrollFieldExecuter(self.script_field, e=True, t=self.code_list[int(item)-1])

    def exec_script(self, *args):
        cmds.cmdScrollFieldExecuter(self.script_field, e=True, executeAll=True)

    def call(self, *args):
        user_input = cmds.scrollField(self.input_field, q=True, tx=True)

        # 入力をScriptEditorに出力
        print('//'*30)
        print(user_input)
        
        # APIコール
        for message_text in self.completion(user_input, '' if self.message_log else self.system_settings):
            cmds.scrollField(self.ai_comment, e=True, tx=message_text)
            cmds.refresh()
        
        # 返答全文をScriptEditorに出力
        print('//'*30)
        print(message_text)
        print('//'*30)

        # 返答を分解
        comment, self.code_list = self.decompose_response(message_text)

        if EXPORT_LOG:
            # ログ(JSON)出力
            self.export_log()
            # スクリプト保存
            self.export_scripts()
        
        # Pythonコード以外の部分をai_commentに表示
        cmds.scrollField(self.ai_comment, e=True, tx=comment)

        # Scriptsプルダウンを更新
        self.update_scripts()

        # Pythonコードの1つ目をscript_fieldに表示
        if self.code_list:
            cmds.cmdScrollFieldExecuter(self.script_field, e=True, t=self.code_list[0], executeAll=cmds.checkBox(self.auto_exec, q=True, v=True))
        else:
            cmds.cmdScrollFieldExecuter(self.script_field, e=True, t='')
    
    def create_window(self, *args):
        cmds.window(title=u'ChatGPTがPythonスクリプトを書くよ！', w=500, h=600, sizeable=True)

        cmds.paneLayout( configuration='horizontal3', paneSize=[[1,1,10], [2,100,30], [3,100,60]])

        pad = 5
        
        form1 = cmds.formLayout()
        
        self.reset_button = cmds.button(label=u'リセット', c=self.reset_session)
        self.show_log_button = cmds.button(label=u'ログ表示', c=self.show_log)
        self.input_field = cmds.scrollField(ed=True, ww=True, tx='', ec=self.call)
        self.send_button = cmds.button(label=u'送信', h=30, c=self.call)
        self.auto_exec = cmds.checkBox(label=u'スクリプト自動実行', v=True)
        
        cmds.formLayout(form1, e=True, 
            attachForm=[
                (self.reset_button, 'top', pad), (self.reset_button, 'left', pad),
                (self.show_log_button, 'top', pad), (self.show_log_button, 'right', pad), 
                (self.input_field, 'left', pad), (self.input_field, 'right', pad), 
                (self.send_button, 'left', pad), (self.send_button, 'bottom', pad), 
                (self.auto_exec, 'right', pad), (self.auto_exec, 'bottom', pad)
            ],
            attachControl=[
                (self.input_field, 'top', pad, self.reset_button), (self.input_field, 'bottom', pad, self.send_button)
            ],
            attachNone=[
                (self.send_button, 'top'), 
                (self.auto_exec, 'top')
            ],
            attachPosition=[
                (self.reset_button, 'right', pad, 50), 
                (self.show_log_button, 'left', pad, 50), 
                (self.send_button, 'right', pad, 75), 
                (self.auto_exec, 'left', pad, 75)
            ]
        )

        cmds.setParent('..')

        self.ai_comment = cmds.scrollField(ed=False, ww=True, tx='')
        
        cmds.setParent('..')

        form3 = cmds.formLayout()
        
        self.scripts = cmds.optionMenu(l='Scripts:', cc=self.change_script)
        self.script_field = cmds.cmdScrollFieldExecuter(st='python', sln=True)
        self.exec_button = cmds.button(label=u'スクリプト実行', h=30, c=self.exec_script)
        
        cmds.formLayout(form3, e=True, 
            attachForm=[
                (self.scripts, 'left', pad), (self.scripts, 'top', pad), 
                (self.script_field, 'left', pad), (self.script_field, 'right', pad), 
                (self.exec_button, 'left', pad), (self.exec_button, 'right', pad), (self.exec_button, 'bottom', pad)
            ],
            attachControl=[
                (self.script_field, 'top', pad, self.scripts), (self.script_field, 'bottom', pad, self.exec_button)
            ],
            attachNone=[
                (self.exec_button, 'top')
            ]
        )

        cmds.setParent('..')

        cmds.showWindow()

ChatGPT_Maya()