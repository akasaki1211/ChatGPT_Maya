# -*- coding: utf-8 -*-
import os

from maya import cmds

from . import info, core, prompts, retry, voice
""" from importlib import reload
reload(info)
reload(core)
reload(prompts)
reload(retry)
reload(voice) """

def run():
    try:
        os.environ['OPENAI_API_KEY']
    except KeyError:
        cmds.error(u'環境変数 OPENAI_API_KEY が設定されていません。')
    else:
        core.showUI()