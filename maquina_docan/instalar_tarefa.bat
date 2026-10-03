@echo off
REM Instala o vigia da DOCAN NESTA maquina - a da impressora, onde agora
REM roda o SAi Production Manager 22.0.
REM
REM Sem acentos de proposito: .bat depende da pagina de codigo do console
REM e caractere acentuado vira lixo na tela.
title DOCAN - instalar o vigia nesta maquina
chcp 65001 >nul
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0instalar_tarefa.ps1"
echo.
echo Se apareceu "Acesso negado", feche esta janela, clique com o botao
echo direito neste arquivo e escolha "Executar como administrador".
echo.
pause
