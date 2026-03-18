@echo off
REM AION Web UI — Stop-Skript
REM ============================================

setlocal enabledelayedexpansion

echo.
echo ╔════════════════════════════════════╗
echo ║     AION Web UI — Stoppen          ║
echo ╚════════════════════════════════════╝
echo.

REM 1) Prozess auf Port 7000 killen
echo Suche AION-Server auf Port 7000...

set PID=
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":7000 "') do (
    if not defined PID set PID=%%a
)

if defined PID (
    echo Gefunden: PID !PID! - beende...
    taskkill /PID !PID! /F >nul 2>&1
    echo OK: Port-7000-Prozess beendet.
) else (
    echo Kein Prozess auf Port 7000 gefunden.
)

REM 2) Alle weiteren aion_web.py Prozesse killen (verhindert Telegram 409)
echo Beende verbleibende aion_web.py Prozesse...
for /f "tokens=2" %%a in ('tasklist /FI "IMAGENAME eq python.exe" /FO list ^| findstr "^PID"') do (
    set CHKPID=%%a
    wmic process where "ProcessId=!CHKPID!" get CommandLine 2^>nul | findstr /I "aion_web" >nul 2>&1
    if not errorlevel 1 (
        echo Beende PID !CHKPID! (aion_web.py)
        taskkill /PID !CHKPID! /F >nul 2>&1
    )
)

echo.
echo Alle AION-Prozesse beendet.

echo.
pause
endlocal
