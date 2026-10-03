@echo off
REM Devolve as pastas do AnyDesk ao normal, pra poder instalar de novo.
title Desbloquear o AnyDesk
chcp 65001 >nul
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0bloquear_anydesk.ps1" -Desfazer
echo.
pause
