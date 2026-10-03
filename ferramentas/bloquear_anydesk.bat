@echo off
REM Tranca as pastas onde o AnyDesk se instala. Pede administrador sozinho.
REM Pra desfazer: rode o desbloquear_anydesk.bat, ao lado deste.
title Bloquear o AnyDesk
chcp 65001 >nul
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0bloquear_anydesk.ps1"
echo.
pause
