@echo off
cd /d C:\dev\hk50-bot\execucao
if exist diario.csv (start "" diario.csv) else (echo Ainda nao ha diario: o robo nao fez nenhuma acao. & pause)