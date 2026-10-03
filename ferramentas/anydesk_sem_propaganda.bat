@echo off
REM Tranca o canal por onde a propaganda do AnyDesk entra, sem desinstalar
REM nada e sem precisar de administrador. Repita depois de reinstalar.
title AnyDesk sem propaganda
chcp 65001 >nul
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0anydesk_sem_propaganda.ps1"
echo.
pause
