@echo off
rem Start Otto with its private Python. Examples:  .\otto    .\otto --voice    .\otto --speak    .\otto --dry-run
"%USERPROFILE%\.otto\venv\Scripts\python.exe" "%~dp0otto.py" %*
