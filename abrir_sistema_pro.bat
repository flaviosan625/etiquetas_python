@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo Abrindo o Sistema de Automacao Grafica Pro 2.0 (PySide6)...
echo.

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -m ui.app
) else (
    python -m ui.app
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
