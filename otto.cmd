@echo off
rem Otto's one command. Examples:  otto   otto voice   otto mic   otto speed 1.2   otto check   (see: otto help)
"%USERPROFILE%\.otto\venv\Scripts\python.exe" "%~dp0otto.py" %*
