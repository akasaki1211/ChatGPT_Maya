# -*- coding: utf-8 -*-
from pathlib import Path

from maya import cmds

TITLE = 'ChatMaya'
VERSION = '1.2.1'

ABOUT_TXT = """
{} {}

Powerd by ChatGPT API.

Supported Maya:
 Maya 2023 (Python3.9.7)
 Maya 2024 (Python3.10.8)

(c) 2023 Hiroyuki Akasaki""".format(TITLE, VERSION)

USER_SETTINGS_DIR = Path(cmds.internalVar(userAppDir=True)) / TITLE
USER_SETTINGS_DIR.mkdir(parents=True, exist_ok=True)

USER_SETTINGS_INI = Path(USER_SETTINGS_DIR / 'userSettings.ini')
USER_SETTINGS_JSON = Path(USER_SETTINGS_DIR / 'userSettings.json')

LOG_DIR = Path(USER_SETTINGS_DIR / "log")
LOG_DIR.mkdir(parents=True, exist_ok=True)