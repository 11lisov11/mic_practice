@echo off
cd /d "%~dp0"
python "%~dp0rebuild.py" --interactive
if errorlevel 1 pause
