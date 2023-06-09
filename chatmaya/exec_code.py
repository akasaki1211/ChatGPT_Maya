# -*- coding: utf-8 -*-
import sys
import traceback

from maya import mel

def exec_mel(code:str):

    try:
        mel.eval(code)
        return 0
    except Exception:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        return str(exc_value)

def exec_py(code:str):

    try:
        exec(code, {'__name__': '__main__'}, None)
        return 0
    except Exception:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        trace = traceback.format_exception(exc_type, exc_value, exc_traceback)
        return "{}: {}: {}".format(exc_type.__name__, trace[-2].strip(), exc_value)