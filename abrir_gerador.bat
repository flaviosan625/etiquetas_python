@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo Abrindo o Gerador de Etiquetas...
echo.

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" main.py
) else (
    python main.py
)

if errorlevel 1 (
    echo.
    echo ============================================
    echo Ocorreu um erro ao rodar o programa.
    echo Veja as mensagens acima para entender o motivo.
    echo ============================================
)

echo.
pause
