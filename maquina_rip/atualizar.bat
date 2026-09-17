@echo off
setlocal
rem ---------------------------------------------------------------
rem  Troca o vigia do RIP pela versao nova e CONFERE que pegou.
rem
rem  Nao mexe na tarefa do Agendador de propositio: ela so chama
rem  C:\RasterLink\rasterlink_hotfolder.py uma vez por minuto, entao
rem  trocar o arquivo ja basta. Tarefa que esta de pe nao se mexe.
rem
rem  Tudo em ASCII puro: .bat com acento depende da pagina de codigo
rem  do console e quebra sozinho (ver tests/test_scripts_powershell).
rem ---------------------------------------------------------------

echo.
echo   ATUALIZAR O VIGIA DO RIP
echo   =======================
echo.

set "DESTINO=C:\RasterLink"
set "ORIGEM="
for /d %%D in ("%USERPROFILE%\OneDrive\UNYCOMUNICACAO\IMPRESS*UJV*") do set "ORIGEM=%%~fD"

if not defined ORIGEM (
  echo   PAREI: nao achei a pasta de deploy no OneDrive.
  echo   Procurei por: %USERPROFILE%\OneDrive\UNYCOMUNICACAO\IMPRESS*UJV*
  goto :fim
)
echo   Pasta de deploy: %ORIGEM%

if not exist "%ORIGEM%\rasterlink_hotfolder.py" (
  echo   PAREI: a pasta existe mas nao tem rasterlink_hotfolder.py dentro.
  goto :fim
)

rem A conferencia mais importante do arquivo. O OneDrive demora, e as
rem vezes muito: ja mediu 10 minutos pra um PDF chegar aqui. Sem esta
rem linha, rodar cedo demais copiaria o arquivo ANTIGO por cima e
rem diria "pronto" - falha silenciosa, que e a pior de todas.
rem
rem A marca procurada tem que ser da ULTIMA versao, nunca de uma que
rem ja esta instalada: com marca velha esta conferencia passa com o
rem arquivo antigo e deixa de servir. Trocar a cada deploy.
rem Hoje: conciliar_registro (registro que nao se perde, 16/09/2026).
findstr /m /c:"conciliar_registro" "%ORIGEM%\rasterlink_hotfolder.py" >nul
if errorlevel 1 (
  echo.
  echo   PAREI: o arquivo na pasta de deploy AINDA E O ANTIGO.
  echo   O OneDrive provavelmente nao terminou de baixar.
  echo   Espere alguns minutos e rode este .bat de novo.
  echo.
  echo   Nada foi alterado. A fila continua exatamente como estava.
  goto :fim
)
echo   O arquivo da pasta de deploy JA E o novo. Pode copiar.
echo.

echo   ANTES:
if exist "%DESTINO%\rasterlink_hotfolder.py" (
  for %%F in ("%DESTINO%\rasterlink_hotfolder.py") do echo     %%~zF bytes, de %%~tF
) else (
  echo     (ainda nao existe)
)

if not exist "%DESTINO%" mkdir "%DESTINO%"
copy /Y "%ORIGEM%\rasterlink_hotfolder.py" "%DESTINO%\rasterlink_hotfolder.py" >nul
if errorlevel 1 (
  echo   FALHOU a copia para %DESTINO%.
  goto :fim
)

echo   DEPOIS:
for %%F in ("%DESTINO%\rasterlink_hotfolder.py") do echo     %%~zF bytes, de %%~tF
echo.

set "PY="
for %%P in (
  "%LOCALAPPDATA%\Python\pythoncore-3.14-64\python.exe"
  "%LOCALAPPDATA%\Python\pythoncore-3.13-64\python.exe"
) do if not defined PY if exist %%P set "PY=%%~fP"
if not defined PY for /f "delims=" %%P in ('where python.exe 2^>nul') do if not defined PY set "PY=%%P"

if not defined PY (
  echo   Copiei o arquivo, mas nao achei o python pra conferir.
  echo   O vigia deve funcionar; confira o log na proxima passada.
  goto :fim
)

echo   CONFERINDO com %PY%
echo.
cd /d "%DESTINO%"
"%PY%" -c "import rasterlink_hotfolder as r, pymupdf; ok = hasattr(r, '_assar_giro'); reg = hasattr(r, 'conciliar_registro'); sup = hasattr(pymupdf.TOOLS, '_insert_contents'); print('   giro novo instalado  :', ok); print('   registro nao se perde:', reg); print('   pymupdf desta maquina:', pymupdf.version[0]); print('   pymupdf sabe girar   :', sup); print(); print('   ' + ('TUDO CERTO. Toda entrega entra no relatorio, mesmo se o OneDrive falhar.' if ok and reg and sup else 'ATENCAO: avise o Flavio, faltou alguma coisa acima.'))"

:fim
echo.
pause
endlocal
