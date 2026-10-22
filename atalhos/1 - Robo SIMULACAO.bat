@echo off
title Robo - SIMULACAO (nada e enviado)
cd /d C:\dev\hk50-bot
echo Robo em SIMULACAO: mostra o que faria, sem enviar ordens.
echo Para desligar: Ctrl+C, ou o atalho "3 - Parar robo".
echo.
.venv\Scripts\python.exe -m execucao.robo_demo
echo.
pause