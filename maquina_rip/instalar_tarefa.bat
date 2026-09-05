@echo off
REM Roda o instalar_tarefa.ps1 que esta ao lado deste arquivo.
REM Sem acentos aqui de proposito: .bat depende da pagina de codigo do
REM console e caractere acentuado vira lixo na tela.
title RasterLink - consertar a tarefa do Agendador
chcp 65001 >nul
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0instalar_tarefa.ps1"
echo.
echo Se apareceu "Acesso negado", feche esta janela, clique com o botao
echo direito neste arquivo e escolha "Executar como administrador".
echo.
pause
