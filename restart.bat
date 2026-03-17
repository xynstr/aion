@echo off
REM AION Web UI — Restart-Skript
REM ============================================

setlocal enabledelayedexpansion

REM Stoppe ggf. laufende Prozesse sauber
call stop.bat

REM Kleine Pause, damit Prozesse auch wirklich beendet werden
timeout /t 2 /nobreak >nul

REM Starte AION wie gewohnt neu
call start.bat

endlocal
