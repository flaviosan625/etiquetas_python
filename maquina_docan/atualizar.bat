@echo off
REM Leva pra ESTA maquina a versao nova do vigia da DOCAN.
REM
REM Sem acentos de proposito: .bat depende da pagina de codigo do console
REM e caractere acentuado vira lixo na tela.
title DOCAN - atualizar o vigia desta maquina
chcp 65001 >nul
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0atualizar.ps1"
echo.
echo Se apareceu "Acesso negado", feche esta janela, clique com o botao
echo direito neste arquivo e escolha "Executar como administrador".
echo.
pause
