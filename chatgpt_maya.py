# -*- coding: utf-8 -*-
import os
import re
import json

import openai

from maya import cmds

openai.api_key = os.getenv("OPENAI_API_KEY")

SYSTEM_SETTINGS = u"""質問に対して、MayaのPythonスクリプトを書いてください。
スクリプト以外の文章は短めにまとめてください。
"""

def completion(new_message_text:str, settings_text:str = '', past_messages:list = []):
    if len(past_messages) == 0 and len(settings_text) != 0:
        system = {"role": "system", "content": settings_text}
        past_messages.append(system)

    new_message = {"role": "user", "content": new_message_text}
    past_messages.append(new_message)

    result = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=past_messages
    )
    message_text = result.choices[0].message.content
    response_message = {"role": "assistant", "content": message_text}
    past_messages.append(response_message)
    
    return message_text, past_messages

def decompose_response(txt:str):
    pattern = r"```python([\s\S]*?)```"
    
    code_list = re.findall(pattern, txt)
    for i in range(int(len(code_list))):
        code_list[i] = re.sub('\A[\r?\n]', '', code_list[i])
        code_list[i] = re.sub('[\r?\n]\Z', '', code_list[i])
    
    comment = re.sub(pattern, '', txt)
    comment = re.sub('[\r?\n]+', '\n', comment)
    comment = re.sub('[\r?\n]\Z', '', comment)
    
    return comment, code_list

class ChatGPT_Maya(object):

    def __init__(self):
        self.system_settings = SYSTEM_SETTINGS
        self.message_log = []
        self.at_first = True

        self.code_list = []

        self.create_window()

    def reset_session(self, *args):
        self.message_log = []
        self.at_first = True
        self.code_list = []

        self.update_scripts()

        cmds.scrollField(self.input_field, e=True, tx='')
        cmds.scrollField(self.ai_comment, e=True, tx='')
        cmds.cmdScrollFieldExecuter(self.script_field, e=True, t='')

    def show_log(self, *args):
        print(json.dumps(self.message_log, indent=4, ensure_ascii=False))
        
        for log in self.message_log:
            print('--'*30)
            print(log['role'] + ' :\n')
            print(log['content'])
        print('--'*30)

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
        
        # APIコール
        if self.at_first:
            message_text, self.message_log = completion(user_input, self.system_settings, [])
            self.at_first = False
        else:
            message_text, self.message_log = completion(user_input, '', self.message_log)

        # 返答全文をScriptEditorに出力
        print('//'*30)
        print(message_text)
        print('//'*30)

        # 返答を分解
        comment, self.code_list = decompose_response(message_text)
        
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
        form = cmds.formLayout()
        
        self.reset_button = cmds.button(label=u'リセット', c=self.reset_session)
        self.show_log_button = cmds.button(label=u'ログ表示', c=self.show_log)
        self.input_field = cmds.scrollField(h=50, ed=True, ww=True, tx='', ec=self.call)
        self.send_button = cmds.button(label=u'送信', c=self.call)
        self.auto_exec = cmds.checkBox(label=u'自動実行', v=True)
        sep = cmds.separator(h=10, st='in')
        self.ai_comment = cmds.scrollField(h=200, ed=False, ww=True, tx='')
        self.scripts = cmds.optionMenu(l='Scripts:', cc=self.change_script)
        self.script_field = cmds.cmdScrollFieldExecuter(st='python')
        self.exec_button = cmds.button(label=u'スクリプト実行', h=30, c=self.exec_script)
        
        pad = 5
        cmds.formLayout(form, e=True, 
            attachForm=[
                (self.reset_button, 'top', pad), (self.reset_button, 'left', pad),
                (self.show_log_button, 'top', pad), (self.show_log_button, 'right', pad), 
                (self.input_field, 'left', pad), (self.input_field, 'right', pad), 
                (self.send_button, 'left', pad), 
                (self.auto_exec, 'right', pad),
                (sep, 'left', pad), (sep, 'right', pad), 
                (self.ai_comment, 'left', pad), (self.ai_comment, 'right', pad), 
                (self.scripts, 'left', pad), 
                (self.script_field, 'left', pad), (self.script_field, 'right', pad), 
                (self.exec_button, 'left', pad), (self.exec_button, 'right', pad), (self.exec_button, 'bottom', pad)
            ],
            attachControl=[
                (self.input_field, 'top', pad, self.reset_button),
                (self.send_button, 'top', pad, self.input_field),
                (self.auto_exec, 'top', pad, self.input_field),
                (sep, 'top', pad, self.send_button),
                (self.ai_comment, 'top', pad, sep),
                (self.scripts, 'top', pad, self.ai_comment),
                (self.script_field, 'top', pad, self.scripts), (self.script_field, 'bottom', pad, self.exec_button)
            ],
            attachNone=[(self.exec_button, 'top')],
            attachPosition=[
                (self.reset_button, 'right', pad, 50), 
                (self.show_log_button, 'left', pad, 50), 
                (self.send_button, 'right', pad, 75), 
                (self.auto_exec, 'left', pad, 75)
            ]
        )

        cmds.showWindow()

ChatGPT_Maya()