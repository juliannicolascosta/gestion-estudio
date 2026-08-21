@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
  echo Falta preparar el entorno local de Gestor de documental.
  echo Consulte README.md para instalar las dependencias.
  pause
  exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" "run.py"
