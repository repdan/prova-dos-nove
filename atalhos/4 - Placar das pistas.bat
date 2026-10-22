@echo off
title Placar das pistas
cd /d C:\dev\hk50-bot
.venv\Scripts\python.exe -m acompanhamento.acompanhar
echo.
pause