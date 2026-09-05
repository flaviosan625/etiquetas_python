@echo off
REM SO OLHA. Nao muda nada nesta maquina.
REM Sem acentos aqui de proposito: .bat depende da pagina de codigo do console.
title RasterLink - diagnostico (so olha)
chcp 65001 >nul
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0diagnostico.ps1"
echo.
echo Tire uma foto da tela ou role pra cima pra ler tudo.
echo.
pause
