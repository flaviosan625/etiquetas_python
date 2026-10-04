@echo off
REM Completa o vigia desta maquina: instala o PyMuPDF no Python da tarefa.
REM Com ele o registro de producao ganha a medida da pagina e o aviso de
REM "nao cabe" passa a funcionar. NAO liga o giro.
REM
REM Sem acentos de proposito: .bat depende da pagina de codigo do console
REM e caractere acentuado vira lixo na tela.
title DOCAN - completar o vigia (PyMuPDF)
chcp 65001 >nul
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0instalar_pymupdf.ps1"
echo.
pause
