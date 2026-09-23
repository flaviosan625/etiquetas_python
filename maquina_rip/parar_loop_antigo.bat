@echo off
REM Para o vigia ANTIGO (o loop) que segura a trava na maquina do RIP.
REM Sem acentos aqui de proposito: .bat depende da pagina de codigo do console.
REM Sem chcp: quem cuida da codificacao e o .ps1 (Console::OutputEncoding).
title RasterLink - parar o loop antigo
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0parar_loop_antigo.ps1"
echo.
pause
