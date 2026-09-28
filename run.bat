@echo off
cd /d "%~dp0"
py window.py
if errorlevel 1 pause
