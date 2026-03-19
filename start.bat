@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
title AION
cd /d "%~dp0"

REM ── ANSI Farben ─────────────────────────────────────────────────────────────
for /f %%a in ('echo prompt $E^| cmd') do set "E=%%a"
set "RESET=%E%[0m"
set "BOLD=%E%[1m"
set "DIM=%E%[2m"
set "CYAN=%E%[96m"
set "GREEN=%E%[92m"
set "YELLOW=%E%[93m"
set "RED=%E%[91m"
set "BLUE=%E%[94m"
set "MAGENTA=%E%[95m"
set "WHITE=%E%[97m"
set "GRAY=%E%[90m"

REM ── Log ─────────────────────────────────────────────────────────────────────
set "LOG=%~dp0aion_start.log"
echo ========================================== > "%LOG%"
echo  AION Start - %date% %time% >> "%LOG%"
echo ========================================== >> "%LOG%"

cls

REM ── Header ──────────────────────────────────────────────────────────────────
echo.
echo %CYAN%%BOLD%  ╔══════════════════════════════════════════╗%RESET%
echo %CYAN%%BOLD%  ║                                          ║%RESET%
echo %CYAN%%BOLD%  ║    %WHITE%██████  %CYAN%  █████  %WHITE%██████  %CYAN%███   ██    %CYAN%║%RESET%
echo %CYAN%%BOLD%  ║    %WHITE%██   ██ %CYAN% ██   ██ %WHITE%██   ██ %CYAN%████  ██    %CYAN%║%RESET%
echo %CYAN%%BOLD%  ║    %WHITE%███████ %CYAN% ██   ██ %WHITE%██   ██ %CYAN%██ ██ ██    %CYAN%║%RESET%
echo %CYAN%%BOLD%  ║    %WHITE%██   ██ %CYAN% ██   ██ %WHITE%██   ██ %CYAN%██  ████    %CYAN%║%RESET%
echo %CYAN%%BOLD%  ║    %WHITE%██   ██ %CYAN%  █████  %WHITE%██████  %CYAN%██   ███    %CYAN%║%RESET%
echo %CYAN%%BOLD%  ║                                          ║%RESET%
echo %CYAN%%BOLD%  ║  %GRAY%Autonomous AI Agent  ·  Web UI v2.0   %CYAN%║%RESET%
echo %CYAN%%BOLD%  ╚══════════════════════════════════════════╝%RESET%
echo.
echo %GRAY%  Log: %LOG%%RESET%
echo.

REM ── Hilfsmakros ─────────────────────────────────────────────────────────────
REM  step_ok  "Text"   →  grüner Haken
REM  step_warn "Text"  →  gelbes Ausrufezeichen
REM  step_fail "Text"  →  roter X + pause + exit
REM  (inline via goto da Batch keine echten Funktionen hat)

REM ══════════════════════════════════════════════════════════════════════════════
echo %BOLD%  ┌─ Schritt 1 / 6 ── Python ─────────────────────────┐%RESET%
echo [S1] Python >> "%LOG%"
python --version >> "%LOG%" 2>&1
if errorlevel 1 (
    echo %RED%  │  ✗  Python nicht gefunden!%RESET%
    echo %YELLOW%  │     Bitte installieren: python.org/downloads%RESET%
    echo %BOLD%  └────────────────────────────────────────────────────┘%RESET%
    echo [FEHLER] Python nicht gefunden >> "%LOG%"
    echo. & pause & exit /b 1
)
for /f "tokens=*" %%v in ('python --version 2^>^&1') do (
    echo %GREEN%  │  ✓  %%v%RESET%
    echo [OK] %%v >> "%LOG%"
)
echo %BOLD%  └────────────────────────────────────────────────────┘%RESET%
echo.

REM ══════════════════════════════════════════════════════════════════════════════
echo %BOLD%  ┌─ Schritt 2 / 6 ── Pakete ─────────────────────────┐%RESET%
echo [S2] Pakete >> "%LOG%"

echo %GRAY%  │  ·  pip upgrade...%RESET%
python -m pip install --upgrade pip -q >> "%LOG%" 2>&1

echo %GRAY%  │  ·  requirements.txt...%RESET%
python -m pip install -r requirements.txt -q >> "%LOG%" 2>&1
if errorlevel 1 (
    echo %RED%  │  ✗  requirements.txt fehlgeschlagen!%RESET%
    echo %BOLD%  └────────────────────────────────────────────────────┘%RESET%
    echo [FEHLER] requirements install >> "%LOG%"
    echo. & pause & exit /b 1
)
echo %GREEN%  │  ✓  Kern-Pakete OK%RESET%

echo %GRAY%  │  ·  Optionale Pakete (google-genai, vosk, ...)%RESET%
python -m pip install google-genai -q    >> "%LOG%" 2>&1
python -m pip install requests -q        >> "%LOG%" 2>&1
python -m pip install duckduckgo-search -q >> "%LOG%" 2>&1
python -m pip install vosk -q            >> "%LOG%" 2>&1
python -m pip install pyttsx3 -q         >> "%LOG%" 2>&1
echo %GREEN%  │  ✓  Optionale Pakete OK%RESET%
echo [OK] Alle Pakete >> "%LOG%"
echo %BOLD%  └────────────────────────────────────────────────────┘%RESET%
echo.

REM ══════════════════════════════════════════════════════════════════════════════
echo %BOLD%  ┌─ Schritt 3 / 6 ── Konfiguration ──────────────────┐%RESET%
echo [S3] .env >> "%LOG%"

if exist ".env" (
    echo %GREEN%  │  ✓  .env gefunden%RESET%
    echo [OK] .env vorhanden >> "%LOG%"
    goto :env_check
)

REM .env fehlt — Setup-Wizard
echo %YELLOW%  │  !  .env fehlt — Setup-Wizard%RESET%
echo %BOLD%  └────────────────────────────────────────────────────┘%RESET%
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
echo %GREEN%  │  ✓  .env erstellt%RESET%
echo [OK] .env erstellt >> "%LOG%"
echo %BOLD%  └────────────────────────────────────────────────────┘%RESET%
echo.

:env_check
python -c "from dotenv import load_dotenv; import os; load_dotenv(); ok = bool(os.getenv('OPENAI_API_KEY','').strip()) or bool(os.getenv('GEMINI_API_KEY','').strip()); exit(0 if ok else 1)" >> "%LOG%" 2>&1
if errorlevel 1 (
    echo %RED%  │  ✗  Kein API-Key in .env gefunden!%RESET%
    echo %YELLOW%  │     Bitte .env oeffnen und Key eintragen.%RESET%
    echo [FEHLER] Kein API-Key >> "%LOG%"
    echo. & pause & exit /b 1
)
echo %GREEN%  │  ✓  API-Key vorhanden%RESET%
echo %BOLD%  └────────────────────────────────────────────────────┘%RESET%
echo.

REM ══════════════════════════════════════════════════════════════════════════════
echo %BOLD%  ┌─ Schritt 4 / 6 ── Modell ─────────────────────────┐%RESET%
echo [S4] Modell >> "%LOG%"
for /f %%m in ('python -c "from dotenv import load_dotenv; import os, json; load_dotenv(); cfg={}; open_ = open('config.json') if __import__('os').path.exists('config.json') else None; cfg=json.load(open_) if open_ else {}; open_ and open_.close(); print(cfg.get('model', os.getenv('AION_MODEL','gemini-2.0-flash')))" 2^>nul') do set "ACTIVE_MODEL=%%m"
if not defined ACTIVE_MODEL set "ACTIVE_MODEL=gemini-2.0-flash"
echo %GREEN%  │  ✓  Modell: %CYAN%%BOLD%%ACTIVE_MODEL%%RESET%
echo [OK] Modell: %ACTIVE_MODEL% >> "%LOG%"
echo %BOLD%  └────────────────────────────────────────────────────┘%RESET%
echo.

REM ══════════════════════════════════════════════════════════════════════════════
echo %BOLD%  ┌─ Schritt 5 / 6 ── Alte Instanzen beenden ─────────┐%RESET%
echo [S5] Cleanup >> "%LOG%"

set OLDPID=
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":7000 "') do (
    if not defined OLDPID set OLDPID=%%a
)
if defined OLDPID (
    taskkill /PID !OLDPID! /F >nul 2>&1
    echo %YELLOW%  │  ·  Port 7000 freigegeben (PID !OLDPID!)%RESET%
    echo [OK] Kill Port 7000 PID=!OLDPID! >> "%LOG%"
) else (
    echo %GREEN%  │  ✓  Port 7000 frei%RESET%
)

powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter 'name=''python.exe''' | Where-Object { $_.CommandLine -like '*aion_web*' -or $_.CommandLine -like '*aion.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" >> "%LOG%" 2>&1
echo [OK] Python-Cleanup abgeschlossen >> "%LOG%"
timeout /t 2 >nul

set OLDPID2=
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":7000 "') do (
    if not defined OLDPID2 set OLDPID2=%%a
)
if defined OLDPID2 (
    taskkill /PID !OLDPID2! /F >nul 2>&1
    echo %YELLOW%  │  ·  Zweiter Kill (PID !OLDPID2!)%RESET%
)

echo %GRAY%  │  ·  Warte 12s auf Telegram-Disconnect...%RESET%
echo [INFO] Warte 12s... >> "%LOG%"
timeout /t 12 >nul
echo %GREEN%  │  ✓  Bereit%RESET%
echo [OK] Cleanup fertig >> "%LOG%"
echo %BOLD%  └────────────────────────────────────────────────────┘%RESET%
echo.

REM ══════════════════════════════════════════════════════════════════════════════
echo %BOLD%  ┌─ Schritt 6 / 6 ── Start ──────────────────────────┐%RESET%
echo [S6] Start >> "%LOG%"

if not exist "aion_web.py" (
    echo %RED%  │  ✗  aion_web.py nicht gefunden!%RESET%
    echo [FEHLER] aion_web.py fehlt >> "%LOG%"
    echo %BOLD%  └────────────────────────────────────────────────────┘%RESET%
    echo. & pause & exit /b 1
)

echo %GREEN%  │  ✓  Alle Checks bestanden — starte Server...%RESET%
echo %BOLD%  └────────────────────────────────────────────────────┘%RESET%
echo.

echo %CYAN%%BOLD%  ╔══════════════════════════════════════════╗%RESET%
echo %CYAN%%BOLD%  ║  %GREEN%✓  AION laeuft                          %CYAN%║%RESET%
echo %CYAN%%BOLD%  ║                                          ║%RESET%
echo %CYAN%%BOLD%  ║  %WHITE%→  http://localhost:7000              %CYAN%║%RESET%
echo %CYAN%%BOLD%  ║  %WHITE%→  Modell: %-32s%CYAN%║%RESET%
echo %CYAN%%BOLD%  ║                                          ║%RESET%
echo %CYAN%%BOLD%  ║  %GRAY%Beenden: Strg+C                        %CYAN%║%RESET%
echo %CYAN%%BOLD%  ╚══════════════════════════════════════════╝%RESET%
echo.

start "" /b cmd /c "timeout /t 3 >nul && start http://localhost:7000"
echo [INFO] python aion_web.py startet >> "%LOG%"

python aion_web.py >> "%LOG%" 2>&1
set EXITCODE=%errorlevel%
echo [INFO] aion_web.py beendet, Code=%EXITCODE% >> "%LOG%"

if %EXITCODE% neq 0 (
    echo.
    echo %RED%%BOLD%  ╔══════════════════════════════════════════╗%RESET%
    echo %RED%%BOLD%  ║  ✗  AION beendet mit Fehlercode %EXITCODE%       ║%RESET%
    echo %RED%%BOLD%  ╚══════════════════════════════════════════╝%RESET%
    echo.
    echo %YELLOW%  Letzte Log-Zeilen:%RESET%
    echo %GRAY%  ─────────────────────────────────────────%RESET%
    powershell -NoProfile -Command "Get-Content '%LOG%' | Select-Object -Last 25 | ForEach-Object { Write-Host '  ' $_ }"
    echo %GRAY%  ─────────────────────────────────────────%RESET%
    echo %GRAY%  Vollstaendiger Log: %LOG%%RESET%
    echo.
    pause
    exit /b %EXITCODE%
)

echo.
echo %GRAY%  AION gestoppt.%RESET%
pause
endlocal
