@echo off
REM Desfaz a tranca: o AnyDesk volta a receber as mensagens dele.
title AnyDesk - desfazer a tranca da propaganda
chcp 65001 >nul
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0anydesk_sem_propaganda.ps1" -Desfazer
echo.
pause
