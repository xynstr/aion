@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
title AION - Start
cd /d "%~dp0"

cls
echo.
echo  ==========================================
echo       AION - Autonomous AI Agent
echo  ==========================================
echo.

REM ===========================================================================
REM  SCHRITT 1 - Python pruefen
REM ===========================================================================
echo  [1/4] Pruefe Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo  FEHLER: Python nicht gefunden!
    echo  Bitte Python 3.10+ installieren: https://www.python.org/downloads/
    echo  Sicherstellen dass "Add Python to PATH" aktiviert ist.
    echo.
    pause
    exit /b 1
)
for /f "tokens=*" %%v in ('python --version 2^>^&1') do echo  OK: %%v gefunden

REM ===========================================================================
REM  SCHRITT 2 - Pakete installieren
REM ===========================================================================
echo.
echo  [2/4] Installiere / aktualisiere Abhaengigkeiten...
echo        (Beim ersten Start kann das ein paar Minuten dauern)
echo.

python -m pip install --upgrade pip -q
if errorlevel 1 echo  Warnung: pip-Upgrade fehlgeschlagen, fahre trotzdem fort.

python -m pip install -r requirements.txt -q
if errorlevel 1 (
    echo  FEHLER: requirements.txt konnte nicht installiert werden.
    pause
    exit /b 1
)

REM Optionale Pakete (Gemini, Telegram)
python -m pip install google-genai -q
python -m pip install "python-telegram-bot>=20.0" -q
python -m pip install requests -q
python -m pip install duckduckgo-search -q

echo  OK: Alle Pakete bereit

REM ===========================================================================
REM  SCHRITT 3 - .env Setup
REM ===========================================================================
echo.
echo  [3/4] Pruefe Konfiguration...

if exist ".env" goto :env_ok

REM .env fehlt - Setup-Wizard
echo.
echo  .env nicht gefunden - Erster Start: Setup-Wizard
echo.
echo  AION benoetigt mindestens einen API-Key (OpenAI ODER Gemini).
echo  Leere Eingabe = Feld ueberspringen.
echo.

set "OPENAI_KEY="
set "GEMINI_KEY="
set "TG_TOKEN="
set "TG_CHAT="
set "AION_MODEL_INPUT="

set /p "OPENAI_KEY=  OpenAI API-Key   (sk-...):  "
set /p "GEMINI_KEY=  Gemini API-Key   (AIza...): "
set /p "TG_TOKEN=    Telegram Token   (optional): "
set /p "TG_CHAT=     Telegram Chat-ID (optional): "
set /p "AION_MODEL_INPUT= Startmodell (leer = gpt-4.1): "

if "!OPENAI_KEY!"=="" if "!GEMINI_KEY!"=="" (
    echo.
    echo  FEHLER: Mindestens ein API-Key erforderlich!
    echo  Starte start.bat erneut oder lege .env manuell an.
    pause
    exit /b 1
)

if "!AION_MODEL_INPUT!"=="" set "AION_MODEL_INPUT=gpt-4.1"

REM .env schreiben
(
    echo # AION Konfiguration - generiert von start.bat
    if not "!OPENAI_KEY!"=="" echo OPENAI_API_KEY=!OPENAI_KEY!
    if not "!GEMINI_KEY!"=="" echo GEMINI_API_KEY=!GEMINI_KEY!
    if not "!TG_TOKEN!"=="" echo TELEGRAM_BOT_TOKEN=!TG_TOKEN!
    if not "!TG_CHAT!"=="" echo TELEGRAM_CHAT_ID=!TG_CHAT!
    echo AION_MODEL=!AION_MODEL_INPUT!
    echo AION_PORT=7000
) > .env

echo.
echo  OK: .env erstellt
goto :env_check

:env_ok
echo  OK: .env gefunden

:env_check
REM Pruefen ob mindestens ein Key vorhanden ist
python -c "from dotenv import load_dotenv; import os; load_dotenv(); ok = bool(os.getenv('OPENAI_API_KEY','').strip()) or bool(os.getenv('GEMINI_API_KEY','').strip()); exit(0 if ok else 1)"
if errorlevel 1 (
    echo.
    echo  FEHLER: Weder OPENAI_API_KEY noch GEMINI_API_KEY in .env gesetzt!
    echo  Bitte .env oeffnen und mindestens einen API-Key eintragen.
    echo.
    pause
    exit /b 1
)
echo  OK: API-Key vorhanden

REM ===========================================================================
REM  SCHRITT 4 - AION starten
REM ===========================================================================
echo.
echo  [4/4] Starte AION Web UI...
echo.
echo  AION laeuft unter: http://localhost:7000
echo  Beenden: Strg+C
echo.

REM Ueberpruefe ob aion_web.py existiert
if not exist "aion_web.py" (
    echo.
    echo  FEHLER: aion_web.py nicht gefunden!
    echo  Du befindest dich wahrscheinlich im falschen Verzeichnis.
    echo.
    pause
    exit /b 1
)

echo.
echo  Starte Python-Server...
echo.

REM Alte AION-Prozesse beenden (verhindert Telegram 409 Conflict)
echo  Beende alte AION-Instanzen (falls vorhanden)...
set OLDPID=
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":7000 "') do (
    if not defined OLDPID set OLDPID=%%a
)
if defined OLDPID (
    taskkill /PID !OLDPID! /F >nul 2>&1
    echo  OK: Alte Instanz auf Port 7000 beendet.
)
for /f "tokens=2" %%a in ('tasklist /FI "IMAGENAME eq python.exe" /FO list ^| findstr "^PID"') do (
    set CHKPID=%%a
    wmic process where "ProcessId=!CHKPID!" get CommandLine 2^>nul | findstr /I "aion_web" >nul 2>&1
    if not errorlevel 1 (
        taskkill /PID !CHKPID! /F >nul 2>&1
        echo  OK: aion_web.py Prozess beendet.
    )
)
REM Warte 5s damit Telegrams Server die alte Verbindung als getrennt erkennt
REM (Long-Polling Verbindung bleibt serverseitig bis zu 30s offen)
echo  Warte 5s auf Telegram-Disconnect...
timeout /t 5 >nul

REM Browser nach kurzer Verzoegerung oeffnen (Python-Prozess startet zuerst)
start "" /b cmd /c "timeout /t 2 >nul && start http://localhost:7000"

REM Starte aion_web.py mit voller Error-Ausgabe
python aion_web.py
if errorlevel 1 (
    echo.
    echo  FEHLER: aion_web.py konnte nicht gestartet werden!
    echo  Siehe Fehlermeldung oben.
    echo.
    pause
    exit /b 1
)

echo.
echo  AION gestoppt.
pause
endlocal
