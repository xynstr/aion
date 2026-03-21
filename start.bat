@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
title AION
cd /d "%~dp0"

REM ANSI Farben
for /f %%a in ('echo prompt $E^| cmd') do set "E=%%a"
set "RESET=%E%[0m"
set "BOLD=%E%[1m"
set "CYAN=%E%[96m"
set "GREEN=%E%[92m"
set "YELLOW=%E%[93m"
set "RED=%E%[91m"
set "WHITE=%E%[97m"
set "GRAY=%E%[90m"

REM Log
set "LOG=%~dp0aion_start.log"
echo ========================================== > "%LOG%"
echo  AION Start - %date% %time% >> "%LOG%"
echo ========================================== >> "%LOG%"

cls

echo.
echo %CYAN%%BOLD%  ====================================================%RESET%
echo %CYAN%%BOLD%  =                                                  =%RESET%
echo %CYAN%%BOLD%  =   AION  -  Autonomous Intelligent Operations    =%RESET%
echo %CYAN%%BOLD%  =                                                  =%RESET%
echo %CYAN%%BOLD%  ====================================================%RESET%
echo.
echo %GRAY%  Log: %LOG%%RESET%
echo.

echo %BOLD%  --- [1/4] Python ---------------------------------------------%RESET%
echo [S1] Python >> "%LOG%"
python --version >> "%LOG%" 2>&1
if errorlevel 1 (
    echo %RED%  [FEHLER]  Python nicht gefunden!%RESET%
    echo %YELLOW%           Bitte installieren: python.org/downloads%RESET%
    echo [FEHLER] Python nicht gefunden >> "%LOG%"
    echo. & pause & exit /b 1
)
for /f "tokens=*" %%v in ('python --version 2^>^&1') do (
    echo %GREEN%  [OK]  %%v%RESET%
    echo [OK] %%v >> "%LOG%"
)
echo.

echo %BOLD%  --- [2/4] Pakete ---------------------------------------------%RESET%
echo [S2] Pakete >> "%LOG%"
echo %GRAY%  ...  pip + requirements.txt%RESET%
python -m pip install --upgrade pip -q >> "%LOG%" 2>&1
python -m pip install -r requirements.txt -q >> "%LOG%" 2>&1
if errorlevel 1 (
    echo %RED%  [FEHLER]  requirements.txt fehlgeschlagen!%RESET%
    echo [FEHLER] requirements install >> "%LOG%"
    echo. & pause & exit /b 1
)
echo %GREEN%  [OK]  Kern-Pakete%RESET%
echo %GRAY%  ...  Optionale Pakete (google-genai, vosk, ...)%RESET%
python -m pip install google-genai -q       >> "%LOG%" 2>&1
python -m pip install requests -q           >> "%LOG%" 2>&1
python -m pip install duckduckgo-search -q  >> "%LOG%" 2>&1
python -m pip install vosk -q               >> "%LOG%" 2>&1
python -m pip install pyttsx3 -q            >> "%LOG%" 2>&1
echo %GREEN%  [OK]  Optionale Pakete%RESET%
echo [OK] Alle Pakete >> "%LOG%"
echo.

echo %BOLD%  --- [3/4] Konfiguration -------------------------------------%RESET%
echo [S3] .env >> "%LOG%"

if exist ".env" (
    echo %GREEN%  [OK]  .env gefunden%RESET%
    echo [OK] .env vorhanden >> "%LOG%"
    goto :env_check
)

echo %YELLOW%  [!]  .env fehlt - Setup-Wizard%RESET%
echo.
echo %CYAN%  AION benoetigt mindestens einen API-Key (OpenAI ODER Gemini).%RESET%
echo %GRAY%  Leere Eingabe = Feld ueberspringen.%RESET%
echo.

set "OPENAI_KEY="
set "GEMINI_KEY="
set "TG_TOKEN="
set "TG_CHAT="
set "AION_MODEL_INPUT="

set /p "OPENAI_KEY=%CYAN%  OpenAI  API-Key  (sk-...):   %RESET%"
set /p "GEMINI_KEY=%CYAN%  Gemini  API-Key  (AIza...):  %RESET%"
set /p "TG_TOKEN=%CYAN%  Telegram Token   (optional): %RESET%"
set /p "TG_CHAT=%CYAN%  Telegram Chat-ID (optional): %RESET%"
set /p "AION_MODEL_INPUT=%CYAN%  Startmodell (leer = gemini-2.0-flash): %RESET%"

if "!OPENAI_KEY!"=="" if "!GEMINI_KEY!"=="" (
    echo.
    echo %RED%  FEHLER: Mindestens ein API-Key erforderlich!%RESET%
    echo [FEHLER] Kein Key eingegeben >> "%LOG%"
    pause & exit /b 1
)
if "!AION_MODEL_INPUT!"=="" set "AION_MODEL_INPUT=gemini-2.0-flash"

(
    echo # AION Konfiguration - generiert von start.bat
    if not "!OPENAI_KEY!"=="" echo OPENAI_API_KEY=!OPENAI_KEY!
    if not "!GEMINI_KEY!"=="" echo GEMINI_API_KEY=!GEMINI_KEY!
    if not "!TG_TOKEN!"=="" echo TELEGRAM_BOT_TOKEN=!TG_TOKEN!
    if not "!TG_CHAT!"=="" echo TELEGRAM_CHAT_ID=!TG_CHAT!
    echo AION_MODEL=!AION_MODEL_INPUT!
    echo AION_PORT=7000
) > .env
echo %GREEN%  [OK]  .env erstellt%RESET%
echo [OK] .env erstellt >> "%LOG%"
echo.

:env_check
python -c "from dotenv import load_dotenv; import os; load_dotenv(); k1=os.getenv('OPENAI_API_KEY','').strip(); k2=os.getenv('GEMINI_API_KEY','').strip(); exit(0 if k1 or k2 else 1)" >> "%LOG%" 2>&1
if errorlevel 1 (
    echo %RED%  [FEHLER]  Kein API-Key in .env gefunden!%RESET%
    echo %YELLOW%           Bitte .env oeffnen und Key eintragen.%RESET%
    echo [FEHLER] Kein API-Key >> "%LOG%"
    echo. & pause & exit /b 1
)
echo %GREEN%  [OK]  API-Key vorhanden%RESET%
echo.

echo %BOLD%  --- [4/4] Modell ---------------------------------------------%RESET%
echo [S4] Modell >> "%LOG%"
for /f %%m in ('python -c "import os,json; f='config.json'; cfg=json.load(open(f)) if os.path.exists(f) else {}; print(cfg.get('model', os.getenv('AION_MODEL','gemini-2.0-flash')))" 2^>nul') do set "ACTIVE_MODEL=%%m"
if not defined ACTIVE_MODEL set "ACTIVE_MODEL=gemini-2.0-flash"
echo %GREEN%  [OK]  Modell: %CYAN%%BOLD%!ACTIVE_MODEL!%RESET%
echo [OK] Modell: !ACTIVE_MODEL! >> "%LOG%"
echo.

:choose_mode
echo %CYAN%  ====================================================%RESET%
echo %CYAN%  =   Wie soll AION gestartet werden?               =%RESET%
echo %CYAN%  ====================================================%RESET%
echo.
echo   [1]  Web UI  --  Browser + localhost:7000
echo   [2]  CLI     --  Terminal-Chat
echo.
set "CHOICE="
set /p "CHOICE=%CYAN%%BOLD%  Eingabe (1/2, Standard: 1): %RESET%"
if "!CHOICE!"=="" set "CHOICE=1"
if "!CHOICE!"=="1" goto :start_web
if "!CHOICE!"=="2" goto :start_cli
echo %YELLOW%  Ungueltige Eingabe - bitte 1 oder 2 eingeben.%RESET%
echo.
goto :choose_mode


:start_web
echo.
echo [Modus] Web >> "%LOG%"
echo %BOLD%  --- Web UI : Port-Cleanup -------------------------------------%RESET%

set OLDPID=
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":7000 "') do (
    if not defined OLDPID set OLDPID=%%a
)
if not defined OLDPID goto :port_free
    taskkill /PID !OLDPID! /F >nul 2>&1
    echo %YELLOW%  [OK]  Port 7000 freigegeben (PID !OLDPID!)%RESET%
    echo [OK] Kill Port 7000 PID=!OLDPID! >> "%LOG%"
    goto :after_port_kill
:port_free
    echo %GREEN%  [OK]  Port 7000 frei%RESET%
    echo [OK] Port 7000 frei >> "%LOG%"
:after_port_kill

taskkill /F /IM python.exe >nul 2>&1
echo [OK] Python-Cleanup >> "%LOG%"
timeout /t 2 >nul

set OLDPID2=
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":7000 "') do (
    if not defined OLDPID2 set OLDPID2=%%a
)
if not defined OLDPID2 goto :port2_free
    taskkill /PID !OLDPID2! /F >nul 2>&1
    echo %YELLOW%  [OK]  Zweiter Kill (PID !OLDPID2!)%RESET%
:port2_free

timeout /t 3 >nul
echo %GREEN%  [OK]  Bereit%RESET%
echo [OK] Cleanup fertig >> "%LOG%"
echo.

if not exist "aion_web.py" (
    echo %RED%  [FEHLER]  aion_web.py nicht gefunden!%RESET%
    echo [FEHLER] aion_web.py fehlt >> "%LOG%"
    echo. & pause & exit /b 1
)

echo %CYAN%%BOLD%  ====================================================%RESET%
echo %CYAN%%BOLD%  =   AION Web UI startet                           =%RESET%
echo %CYAN%%BOLD%  =                                                  =%RESET%
echo %CYAN%%BOLD%  =   ->  http://localhost:7000                     =%RESET%
echo %CYAN%%BOLD%  =   ->  Modell: !ACTIVE_MODEL!                           =%RESET%
echo %CYAN%%BOLD%  =                                                  =%RESET%
echo %CYAN%%BOLD%  =   Beenden: Strg+C                               =%RESET%
echo %CYAN%%BOLD%  ====================================================%RESET%
echo.

start "" /b cmd /c "timeout /t 3 >nul && start http://localhost:7000"
echo [INFO] python aion_web.py startet >> "%LOG%"

python aion_web.py >> "%LOG%" 2>&1
set EXITCODE=%errorlevel%
echo [INFO] aion_web.py beendet, Code=%EXITCODE% >> "%LOG%"

if %EXITCODE% neq 0 (
    echo.
    echo %RED%%BOLD%  AION beendet mit Fehlercode %EXITCODE%%RESET%
    echo.
    echo %YELLOW%  Letzte Log-Zeilen:%RESET%
    powershell -NoProfile -Command "Get-Content '%LOG%' | Select-Object -Last 25 | ForEach-Object { Write-Host '  ' $_ }"
    echo %GRAY%  Vollstaendiger Log: %LOG%%RESET%
    echo.
    pause
    exit /b %EXITCODE%
)

echo.
echo %GRAY%  AION gestoppt.%RESET%
pause
endlocal
goto :eof


:start_cli
echo.
echo [Modus] CLI >> "%LOG%"

if not exist "aion_cli.py" (
    echo %RED%  [FEHLER]  aion_cli.py nicht gefunden!%RESET%
    echo [FEHLER] aion_cli.py fehlt >> "%LOG%"
    echo. & pause & exit /b 1
)

cls
python aion_cli.py

echo [INFO] aion_cli.py beendet >> "%LOG%"
echo.
echo %GRAY%  CLI-Sitzung beendet.%RESET%
pause
endlocal
goto :eof
