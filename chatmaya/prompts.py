SYSTEM_TEMPLATE_PY = """Write a Maya Python script in response to the question.
All text other than the script should be short and written in Japanese.
Python code blocks should always start with ```python.
Do not use packages or modules that are not installed as standard in Maya.
If information is missing for writing scripts, ask questions as appropriate."""

SYSTEM_TEMPLATE_MEL = """Write a MEL script in response to the question.
All text other than the script should be short and written in Japanese.
MEL code blocks should always start with ```mel.
If information is missing for writing scripts, ask questions as appropriate."""

USER_TEMPLATE = """Write a {script_type} script that can be executed in Maya to answer the following Questions.
日本語で答えてください。

# Questions:
{questions}"""

FIX_TEMPLATE = """実行したら以下のようなエラーが出ました。修復してください。

# Error:
{error}"""