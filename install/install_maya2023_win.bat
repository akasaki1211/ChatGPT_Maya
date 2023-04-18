@echo off

set MayaVersion=2023
set ModuleName=chatmaya

set CurrentPath=%~dp0
set A=%CurrentPath:~0,-2%
for %%A in (%A%) do set RootPath=%%~dpA

set MayaPy="%ProgramFiles%\Autodesk\Maya%MayaVersion%\bin\mayapy.exe"

:: pip upgrade
%MayaPy% -m pip install -U pip

:: install site-packages
%MayaPy% -m pip install -U -r %CurrentPath%\requirements.txt -t %UserProfile%\Documents\maya\%MayaVersion%\scripts\site-packages

:: install module
robocopy %RootPath%\%ModuleName% %UserProfile%\Documents\maya\%MayaVersion%\scripts\%ModuleName% /MIR