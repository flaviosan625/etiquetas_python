@echo off
REM So COPIA os arquivos de historico do programa da impressora pra esta
REM pasta (que esta no OneDrive). Nao apaga e nao muda nada.
title DOCAN - coletar o historico da impressora
chcp 65001 >nul
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0coletar_historico_byhx.ps1"
echo.
pause
