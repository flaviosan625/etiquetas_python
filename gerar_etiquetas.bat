@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ==========================================
echo   GERADOR DE ETIQUETAS
echo ==========================================
echo.

set /p CLIENTE="Nome do cliente: "
set /p PRODUTOR="Nome do produtor responsavel: "

echo.
echo Gerando etiquetas para %CLIENTE% (produtor: %PRODUTOR%)...
echo.

uv run main.py --pasta-entrada "entrada" --cliente "%CLIENTE%" --gerente "Flavio Santos" --produtor "%PRODUTOR%"

echo.
echo ==========================================
echo   Concluido. Confira a pasta etiquetas_geradas
echo ==========================================
pause
