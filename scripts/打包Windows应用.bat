@echo off
chcp 65001 >nul
rem Double-click to build the Windows version (installer + portable zip).
cd /d "%~dp0.."
where py >nul 2>nul
if %errorlevel%==0 (
  py -3 desktop\build_windows.py
) else (
  python desktop\build_windows.py
)
if errorlevel 1 pause
