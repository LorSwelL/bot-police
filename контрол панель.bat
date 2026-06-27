@echo off
title UVD Bot Control

:menu
cls
echo ==========================
echo      UVD BOT CONTROL
echo ==========================
echo.
echo [1] Start bot
echo [2] Restart bot
echo [Q] Exit
echo.
choice /c 12Q /n /m "Select: "

if errorlevel 3 goto end
if errorlevel 2 goto restart
if errorlevel 1 goto startbot
goto menu

:startbot
cls
echo Starting bot...
cd /d "%~dp0"
start "UVD_BOT" cmd /k "title UVD_BOT && py main.py"
timeout /t 1 /nobreak >nul
goto menu

:restart
cls
echo Restarting bot...
taskkill /FI "WINDOWTITLE eq UVD_BOT" /T /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq UVD_BOT*" /T /F >nul 2>&1
timeout /t 1 /nobreak >nul

cd /d "%~dp0"
start "UVD_BOT" cmd /k "title UVD_BOT && py main.py"
timeout /t 1 /nobreak >nul
goto menu

:end
exit