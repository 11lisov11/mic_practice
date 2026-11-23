@echo off
cd /d "%~dp0"
if not exist "load_bench\config.local.json" copy "load_bench\config.template.json" "load_bench\config.local.json" >nul
python -X utf8 -m load_bench ui --config load_bench\config.local.json
if errorlevel 1 pause
