@echo off
REM AION Web UI — Start-Skript
REM ============================================

setlocal enabledelayedexpansion

echo.
echo ╔════════════════════════════════════╗
echo ║     AION Web UI — Starten          ║
echo ╚════════════════════════════════════╝
echo.

REM Prüfe ob OPENAI_API_KEY gesetzt ist (via .env oder Umgebungsvariable)
if not defined OPENAI_API_KEY (
    REM Versuche .env zu laden
    if exist ".env" (
        echo ℹ️  Lade API-Key aus .env-Datei…
    ) else (
        echo ⚠️  Fehler: OPENAI_API_KEY nicht gefunden
        echo.
        echo Bitte eine von diesen Optionen wählen:
        echo.
        echo Option 1 (empfohlen): .env-Datei erstellen
        echo   - Kopiere .env.example zu .env
        echo   - Öffne .env und setze deinen API-Key
        echo   - Starte dann das Skript erneut
        echo.
        echo Option 2: Umgebungsvariable setzen
        echo   set OPENAI_API_KEY=sk-...
        echo   start.bat
        echo.
        pause
        exit /b 1
    )
)

REM Prüfe Python-Installation
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Fehler: Python nicht gefunden. Bitte installieren Sie Python.
    pause
    exit /b 1
)

REM Prüfe pip-Pakete
echo ✓ Prüfe Abhängigkeiten…
python -m pip list | findstr "fastapi uvicorn openai httpx" >nul
if errorlevel 1 (
    echo.
    echo 📦 Installiere fehlende Pakete…
    python -m pip install fastapi uvicorn openai httpx beautifulsoup4 rich -q
    if errorlevel 1 (
        echo ❌ Fehler beim Installieren. Bitte manuell ausführen:
        echo    pip install fastapi uvicorn openai httpx beautifulsoup4 rich
        pause
        exit /b 1
    )
)

REM Starte den Server
echo.
echo 🚀 Starte AION Web UI…
echo.
cd /d "%~dp0"
start "" python aion_web.py

REM Warte bis Server antwortet
echo ⟳ Starte Server…
timeout /t 2 /nobreak >nul

echo ✓ Server läuft auf http://localhost:7000
echo.

REM Öffne im Standard-Browser
echo 🌐 Öffne Browser…
start http://localhost:7000

echo.
echo ✓ AION ist bereit!
echo.
echo 💡 Zum Beenden: stop.bat ausführen
echo.

endlocal
