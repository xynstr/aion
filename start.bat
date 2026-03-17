@echo off
REM AION - BULLETPROOF START
setlocal enabledelayedexpansion
chcp 65001 >nul
title AION Web UI

cls
echo.
echo ╔══════════════════════════════════════╗
echo ║ AION Web UI - START                  ║
echo ╚══════════════════════════════════════╝
echo.

REM 1. .env pruefen
echo [1/5] Pruefe .env...
if not exist ".env" (
echo FEHLER: .env fehlt!
pause
exit /b 1
)
echo OK: .env gefunden

REM 2. Key testen
echo [2/5] Pruefe API-Key...
python -c "from dotenv import load_dotenv; load_dotenv(); import os; assert os.getenv('OPENAI_API_KEY'), 'KEY FEHLT'"
if errorlevel 1 (
echo FEHLER: OPENAI_API_KEY fehlt oder falsch in .env!
pause
exit /b 1
)
echo OK: API-Key geladen

REM 3. Pakete installieren
echo [3/5] Installiere fehlende Pakete...
python -m pip install --user fastapi uvicorn openai httpx beautifulsoup4 rich python-dotenv python-telegram-bot -q
echo OK: Pakete bereit

REM 4. google-genai pruefen und installieren (fuer Gemini-Plugin)
echo [4/5] Pruefe google-genai...
python -c "import google.genai" >nul 2>&1
if errorlevel 1 (
echo Installiere google-genai...
python -m pip install --user google-genai -q
echo OK: google-genai installiert
) else (
echo OK: google-genai bereits vorhanden
)

REM 5. aion.py AUTO-FIX (schreibt __file__ an Zeile 1)
echo [5/5] Autofix aion.py...
python fix_aion.py
echo OK: aion.py gefixt

REM Start WebUI
echo.
echo Starte AION Web UI auf http://localhost:7000
echo Beenden: Strg+C
echo.
cd /d "%~dp0"
title AION Web UI - localhost:7000
python aion_web.py

echo.
echo AION gestoppt.
pause
endlocal
