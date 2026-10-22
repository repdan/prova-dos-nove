@echo off
title Robo - CONTA DEMO (enviando ordens)
cd /d C:\dev\hk50-bot
echo ATENCAO: este modo ENVIA ORDENS para a conta DEMO (lote 0,01).
echo Precisa do MetaTrader aberto, logado na demo, com o Algo Trading ligado.
echo.
set /p ok=Digite S e Enter para confirmar: 
if /i not "%ok%"=="S" (echo Cancelado. & pause & exit /b)
echo.
.venv\Scripts\python.exe -m execucao.robo_demo --valendo
echo.
pause