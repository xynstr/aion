@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
title AION Debug

cd /d "%~dp0"

echo.
echo ╔════════════════════════════════════════════╗
echo ║    AION Debug — Fehlersuche                ║
echo ╚════════════════════════════════════════════╝
echo.

echo [1] Python Version:
python --version
if errorlevel 1 (
    echo  FEHLER: Python nicht gefunden
    pause
    exit /b 1
)
echo.

echo [2] Importiere dotenv:
python -c "from dotenv import load_dotenv; print('  OK: dotenv geladen')"
if errorlevel 1 (
    echo  FEHLER: dotenv nicht installiert
    pause
    exit /b 1
)
echo.

echo [3] Importiere FastAPI:
python -c "import fastapi; print('  OK: fastapi geladen')"
if errorlevel 1 (
    echo  FEHLER: fastapi nicht installiert
    pause
    exit /b 1
)
echo.

echo [4] Importiere OpenAI:
python -c "from openai import AsyncOpenAI; print('  OK: openai geladen')"
if errorlevel 1 (
    echo  FEHLER: openai nicht installiert
    pause
    exit /b 1
)
echo.

echo [5] Prüfe .env:
if exist ".env" (
    echo  OK: .env gefunden
) else (
    echo  WARNUNG: .env nicht gefunden
    echo  Starte start.bat um .env zu erstellen
)
echo.

echo [6] Versuche aion_web.py zu importieren:
python -c "import sys; sys.path.insert(0, '.'); import aion_web; print('  OK: aion_web geladen')"
if errorlevel 1 (
    echo  FEHLER: aion_web konnte nicht geladen werden
    echo  Siehe Fehlermeldung oben
    pause
    exit /b 1
)
echo.

echo ╔════════════════════════════════════════════╗
echo ║  Alle Checks erfolgreich! ✓               ║
echo ║  Du kannst jetzt start.bat ausführen.     ║
echo ╚════════════════════════════════════════════╝
echo.

pause
endlocal
