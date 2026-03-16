@echo off
REM AION Web UI — Stop-Skript
REM ============================================

setlocal enabledelayedexpansion

echo.
echo ╔════════════════════════════════════╗
echo ║     AION Web UI — Stoppen          ║
echo ╚════════════════════════════════════╝
echo.

REM Versuche Port 7000 zu finden und zu killen
echo Suche AION-Server auf Port 7000…

for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":7000"') do (
    set PID=%%a
)

if defined PID (
    echo ✓ Server mit PID !PID! gefunden.
    echo.
    echo ⟳ Stoppe Server…
    taskkill /PID !PID! /F >nul 2>&1
    if errorlevel 1 (
        echo ❌ Fehler beim Stoppen. Versuche Alternative…
        taskkill /IM python.exe /F /FI "WINDOWTITLE eq*AION*" >nul 2>&1
    ) else (
        echo ✓ Server beendet.
    )
) else (
    echo ⚠️  Kein Server auf Port 7000 gefunden.
    echo.
    echo Falls der Server läuft, kann er manuell beendet werden:
    echo   taskkill /IM python.exe
)

echo.
pause
endlocal
