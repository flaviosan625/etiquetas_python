@echo off
REM Tira o vigia da DOCAN DESTA maquina. A fila nao se perde: sem vigia,
REM o arquivo fica esperando na pasta do OneDrive ate alguem atender.
title DOCAN - tirar o vigia desta maquina
chcp 65001 >nul
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0desinstalar_tarefa.ps1"
echo.
pause
