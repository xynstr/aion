@echo off
chcp 65001 >nul
cd /d "%~dp0"
title AION CLI
python aion_cli.py
pause
