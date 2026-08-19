@echo off
setlocal

echo ============================================================
echo  Limpeza de arquivos temporarios - Gerador de Etiquetas
echo ============================================================
echo.
echo Isso vai apagar apenas:
echo   1. etiquetas_python_atualizacao.zip  (pacote de atualizacao antigo)
echo   2. a pasta __pycache__               (cache do Python, recriada sozinha)
echo.
echo Nenhum outro arquivo ou pasta sera tocado.
echo.
pause

cd /d "%~dp0"

echo.
if exist "etiquetas_python_atualizacao.zip" (
    del "etiquetas_python_atualizacao.zip"
    echo [OK] Apagado: etiquetas_python_atualizacao.zip
) else (
    echo [--] etiquetas_python_atualizacao.zip nao encontrado, nada a fazer.
)

if exist "__pycache__" (
    rmdir /s /q "__pycache__"
    echo [OK] Apagada: pasta __pycache__
) else (
    echo [--] __pycache__ nao encontrado, nada a fazer.
)

echo.
echo Pronto! Pasta limpa.
echo.
pause
