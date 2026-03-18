@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
title AION - Diagnose
cd /d "%~dp0"

echo ==========================================
echo  AION Diagnose - Schritt fuer Schritt
echo ==========================================
echo Alle Ausgaben werden auch in diagnose_log.txt gespeichert.
echo.

REM Alles in Log-Datei schreiben
set LOGFILE=diagnose_log.txt
echo AION Diagnose %date% %time% > %LOGFILE%

echo [1] Python pruefen...
echo [1] Python pruefen >> %LOGFILE%
python --version >> %LOGFILE% 2>&1
if errorlevel 1 (
    echo FEHLER: Python nicht gefunden!
    echo FEHLER: Python nicht gefunden >> %LOGFILE%
    goto :ende
)
python --version
echo OK: Python gefunden >> %LOGFILE%

echo.
echo [2] requirements.txt pruefen...
echo [2] requirements.txt >> %LOGFILE%
if not exist "requirements.txt" (
    echo FEHLER: requirements.txt nicht gefunden!
    echo FEHLER: requirements.txt fehlt >> %LOGFILE%
) else (
    echo OK: requirements.txt vorhanden
    type requirements.txt >> %LOGFILE%
)

echo.
echo [3] pip install requirements...
echo [3] pip install >> %LOGFILE%
python -m pip install -r requirements.txt -q >> %LOGFILE% 2>&1
if errorlevel 1 (
    echo FEHLER bei pip install requirements.txt - Details in diagnose_log.txt
    echo FEHLER: pip install fehlgeschlagen >> %LOGFILE%
) else (
    echo OK: requirements installiert
)

echo.
echo [4] Optionale Pakete...
echo [4] Optionale Pakete >> %LOGFILE%
python -m pip install google-genai -q >> %LOGFILE% 2>&1
echo    google-genai: %errorlevel%
python -m pip install requests -q >> %LOGFILE% 2>&1
echo    requests: %errorlevel%
python -m pip install duckduckgo-search -q >> %LOGFILE% 2>&1
echo    duckduckgo-search: %errorlevel%
python -m pip install vosk -q >> %LOGFILE% 2>&1
echo    vosk: %errorlevel%
python -m pip install pyttsx3 -q >> %LOGFILE% 2>&1
echo    pyttsx3: %errorlevel%

echo.
echo [5] .env pruefen...
echo [5] .env >> %LOGFILE%
if exist ".env" (
    echo OK: .env gefunden
    echo OK: .env vorhanden >> %LOGFILE%
) else (
    echo FEHLER: .env nicht gefunden!
    echo FEHLER: .env fehlt >> %LOGFILE%
    goto :ende
)

echo.
echo [6] API-Key pruefen...
echo [6] API-Key >> %LOGFILE%
python -c "from dotenv import load_dotenv; import os; load_dotenv(); ok = bool(os.getenv('OPENAI_API_KEY','').strip()) or bool(os.getenv('GEMINI_API_KEY','').strip()); print('Key OK' if ok else 'KEIN KEY'); exit(0 if ok else 1)" >> %LOGFILE% 2>&1
if errorlevel 1 (
    echo FEHLER: Kein API-Key in .env!
    echo FEHLER: Kein API-Key >> %LOGFILE%
    goto :ende
) else (
    echo OK: API-Key vorhanden
)

echo.
echo [7] aion.py Import-Test...
echo [7] aion.py Import >> %LOGFILE%
python -c "import aion; print('Import OK')" >> %LOGFILE% 2>&1
if errorlevel 1 (
    echo FEHLER: aion.py kann nicht importiert werden - Details in diagnose_log.txt
    echo FEHLER: aion.py import fehlgeschlagen >> %LOGFILE%
) else (
    echo OK: aion.py importierbar
)

echo.
echo [8] aion_web.py Import-Test...
echo [8] aion_web.py >> %LOGFILE%
python -c "import importlib.util; spec=importlib.util.spec_from_file_location('x','aion_web.py'); print('Datei gefunden')" >> %LOGFILE% 2>&1
if errorlevel 1 (
    echo FEHLER: aion_web.py Problem
) else (
    echo OK: aion_web.py gefunden
)

echo.
echo [9] Port 7000 Status...
echo [9] Port 7000 >> %LOGFILE%
netstat -ano | findstr ":7000 " >> %LOGFILE% 2>&1
netstat -ano | findstr ":7000 "
if errorlevel 1 echo    Port 7000 frei

echo.
echo [10] PowerShell Test...
echo [10] PowerShell >> %LOGFILE%
powershell -NoProfile -Command "Write-Host 'PowerShell OK'" >> %LOGFILE% 2>&1
if errorlevel 1 (
    echo FEHLER: PowerShell nicht verfuegbar
    echo FEHLER: PowerShell >> %LOGFILE%
) else (
    echo OK: PowerShell verfuegbar
)

echo.
echo ==========================================
echo  Diagnose abgeschlossen.
echo  Log gespeichert in: diagnose_log.txt
echo ==========================================
echo.

:ende
echo.
echo Druecke eine Taste zum Beenden...
pause >nul
endlocal
