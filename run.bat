@echo off
cd /d "%~dp0"
if exist "dist\Vedika.exe" (
    start "" "dist\Vedika.exe"
) else (
    start pythonw main.py
)
exit
