@echo off
REM So olha o programa da impressora (BYHX). Nao muda nada, nao precisa de
REM administrador. Grava o resultado nesta pasta, que esta no OneDrive.
title DOCAN - diagnostico do programa da impressora
chcp 65001 >nul
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0diagnostico_byhx.ps1"
echo.
pause
