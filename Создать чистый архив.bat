@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul

REM =====================================================
REM УПАКОВКА ЧИСТОГО АРХИВА ДЛЯ ОТПРАВКИ
REM Класть в корень проекта (рядом с main.py)
REM =====================================================

set "PROJECT_DIR=%~dp0"
if "%PROJECT_DIR:~-1%"=="\" set "PROJECT_DIR=%PROJECT_DIR:~0,-1%"

set "PROJECT_NAME=discord-bot-uvd"

REM Временная папка
set "TEMP_DIR=%TEMP%\uvd_pack_temp"

echo.
echo ==========================================
echo   Упаковка чистого архива проекта
echo ==========================================
echo Проект: %PROJECT_DIR%
echo.

REM === Дата/время для имени файла ===
for /f %%I in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd_HH-mm"') do set "STAMP=%%I"
set "OUT_NAME=%PROJECT_NAME%_%STAMP%.zip"
set "OUT_PATH=%PROJECT_DIR%\%OUT_NAME%"

REM === Очистка временной папки ===
if exist "%TEMP_DIR%" (
    echo [1/5] Очистка временной папки...
    rmdir /s /q "%TEMP_DIR%"
)
mkdir "%TEMP_DIR%"

REM === Копирование проекта ===
echo [2/5] Копирование проекта во временную папку...
xcopy "%PROJECT_DIR%\*" "%TEMP_DIR%\" /E /I /H /Y >nul
if errorlevel 1 (
    echo ❌ Ошибка копирования проекта.
    pause
    exit /b 1
)

REM === Удаление мусора ===
echo [3/5] Удаление лишних файлов...

REM Python cache
for /d /r "%TEMP_DIR%" %%D in (__pycache__) do (
    if exist "%%D" rmdir /s /q "%%D"
)
for /r "%TEMP_DIR%" %%F in (*.pyc) do if exist "%%F" del /q "%%F"
for /r "%TEMP_DIR%" %%F in (*.pyo) do if exist "%%F" del /q "%%F"

REM Logs
for /r "%TEMP_DIR%" %%F in (*.log) do if exist "%%F" del /q "%%F"

REM Databases (если не хочешь отправлять БД)
for /r "%TEMP_DIR%" %%F in (*.db) do if exist "%%F" del /q "%%F"
for /r "%TEMP_DIR%" %%F in (*.sqlite) do if exist "%%F" del /q "%%F"
for /r "%TEMP_DIR%" %%F in (*.sqlite3) do if exist "%%F" del /q "%%F"

REM Secrets
if exist "%TEMP_DIR%\.env" del /q "%TEMP_DIR%\.env"

REM Git internals (обычно не нужно отправлять)
if exist "%TEMP_DIR%\.git" rmdir /s /q "%TEMP_DIR%\.git"

REM Virtual environments
if exist "%TEMP_DIR%\venv" rmdir /s /q "%TEMP_DIR%\venv"
if exist "%TEMP_DIR%\.venv" rmdir /s /q "%TEMP_DIR%\.venv"
if exist "%TEMP_DIR%\env" rmdir /s /q "%TEMP_DIR%\env"

REM IDE folders
if exist "%TEMP_DIR%\.idea" rmdir /s /q "%TEMP_DIR%\.idea"
if exist "%TEMP_DIR%\.vscode" rmdir /s /q "%TEMP_DIR%\.vscode"

REM Сам упаковщик из архива можно убрать (по желанию)
if exist "%TEMP_DIR%\pack_for_chatgpt.bat" del /q "%TEMP_DIR%\pack_for_chatgpt.bat"

REM Старые архивы внутри папки проекта, если вдруг попали в копию
for /r "%TEMP_DIR%" %%F in (*.zip) do if exist "%%F" del /q "%%F"
for /r "%TEMP_DIR%" %%F in (*.rar) do if exist "%%F" del /q "%%F"
for /r "%TEMP_DIR%" %%F in (*.7z) do if exist "%%F" del /q "%%F"

REM === Создание архива ===
echo [4/5] Создание архива: %OUT_NAME%
powershell -NoProfile -Command "Compress-Archive -Path '%TEMP_DIR%\*' -DestinationPath '%OUT_PATH%' -Force"
if errorlevel 1 (
    echo ❌ Ошибка создания архива.
    pause
    exit /b 1
)

REM === Очистка временной папки ===
echo [5/5] Очистка временной папки...
rmdir /s /q "%TEMP_DIR%"

echo.
echo ✅ Готово!
echo Архив создан:
echo %OUT_PATH%
echo.
pause