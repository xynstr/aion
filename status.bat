@echo off
REM AION Web UI — Status-Skript
REM ============================================

setlocal enabledelayedexpansion

echo.
echo ╔════════════════════════════════════╗
echo ║     AION — Status                  ║
echo ╚════════════════════════════════════╝
echo.

REM Prüfe Port 7000
netstat -ano | findstr ":7000" >nul 2>&1
if errorlevel 1 (
    echo ❌ Server läuft NICHT
    echo.
    echo Zum Starten: start.bat ausführen
) else (
    echo ✓ Server läuft auf http://localhost:7000
    echo.
    for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":7000"') do (
        echo   PID: %%a
    )
)

echo.
pause
endlocal
