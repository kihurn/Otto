@echo off
rem Run one of Otto's tools. Examples:  .\tool label_tests    .\tool score    .\tool try_laya    .\tool voice_test
if "%~1"=="" (
  echo Tools: label_tests  score  try_laya  voice_test
  exit /b 1
)
pushd "%~dp0"
"%USERPROFILE%\.otto\venv\Scripts\python.exe" -m tools.%*
popd
