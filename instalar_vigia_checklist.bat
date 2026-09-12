@echo off
REM Instala a tarefa agendada do Vigia do Checklist de Producao.
REM
REM IMPORTANTE: clique com o BOTAO DIREITO neste arquivo e escolha
REM "Executar como administrador". Criar tarefa no Agendador precisa disso.
chcp 65001 >nul
set AQUI=%~dp0
powershell -NoProfile -ExecutionPolicy Bypass -File "%AQUI%instalar_vigia_checklist.ps1"
echo.
pause
