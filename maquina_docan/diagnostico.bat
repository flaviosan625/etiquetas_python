@echo off
REM So olha. Nao muda nada, nao precisa de administrador.
REM No fim ele grava um diagnostico_<PC>.txt nesta mesma pasta, que esta
REM no OneDrive - e assim o outro computador consegue ler o resultado.
title DOCAN - diagnostico do vigia
chcp 65001 >nul
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0diagnostico.ps1"
echo.
pause
