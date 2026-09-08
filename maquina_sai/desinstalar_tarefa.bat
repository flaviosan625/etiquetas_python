@echo off
REM Desfaz a instalacao do vigia da DOCAN nesta maquina.
REM Sem acentos aqui de proposito: .bat depende da pagina de codigo do
REM console e caractere acentuado vira lixo na tela.
title DOCAN - remover a tarefa do Agendador (posto SAi)
chcp 65001 >nul
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0desinstalar_tarefa.ps1"
echo.
echo Se apareceu "Acesso negado", feche esta janela, clique com o botao
echo direito neste arquivo e escolha "Executar como administrador".
echo.
pause
