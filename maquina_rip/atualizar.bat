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

rem ---------------------------------------------------------------
rem  E ESTA a maquina do RIP?
rem
rem  Este .bat copia pra C:\RasterLink DA MAQUINA ONDE ELE RODA. Rodar
rem  no PC errado copia pra uma pasta que ninguem usa, e ainda assim
rem  mostra "TUDO CERTO" no fim, porque tudo que ele confere passa.
rem  Aconteceu em 22/09/2026: o deploy foi dado como feito e a UJV e a
rem  SWJ seguiram com a versao antiga, perdendo entrega do relatorio.
rem
rem  Quem diz qual e a maquina do RIP e o proprio vigia: ele grava o
rem  nome dela no sinal de vida, dentro da pasta da fila. Assim nao fica
rem  nome de PC escrito aqui, e continua valendo se a maquina mudar.
rem ---------------------------------------------------------------
echo   Este PC: %COMPUTERNAME%

set "SINAL="
for /d %%D in ("%USERPROFILE%\OneDrive\UNYCOMUNICACAO\FILA*MAQUINAS") do set "SINAL=%%~fD\_sinal_de_vida.json"

rem Sem pipe de proposito: dentro de aspas o ^ nao escapa nada, entao um
rem "^|" chegaria literal no PowerShell e quebraria o comando calado.
set "MAQUINA_RIP="
if defined SINAL if exist "%SINAL%" (
  for /f "usebackq delims=" %%M in (`powershell -NoProfile -Command "try{$s=Get-Content -Raw -LiteralPath '%SINAL%'; (ConvertFrom-Json $s).maquina}catch{''}"`) do set "MAQUINA_RIP=%%M"
)

rem Nada de parenteses no texto: um ")' solto fecha o bloco antes da hora
rem e os DOIS ramos do if rodam - aconteceu na primeira versao disto.
if not defined MAQUINA_RIP (
  echo   sem sinal de vida do RIP pra conferir a maquina; seguindo assim mesmo
) else (
  echo   Maquina do vigia do RIP, pelo sinal de vida: %MAQUINA_RIP%
  if /i not "%MAQUINA_RIP%"=="%COMPUTERNAME%" (
    echo.
    echo   PAREI: este PC e %COMPUTERNAME%, mas quem faz o vigia do RIP
    echo   e %MAQUINA_RIP%. Copiar aqui nao muda a UJV nem a SWJ.
    echo   Rode este mesmo .bat naquela maquina.
    echo.
    echo   Nada foi alterado. A fila continua exatamente como estava.
    goto :fim
  )
)
echo.

rem O arquivo pode estar no OneDrive como "Disponivel quando online":
rem so o marcador, sem o conteudo no disco. Ler ele forca o download.
rem SEM ISTO o deploy fica preso: o findstr PULA arquivo com atributo
rem offline e responde como se a marca nao estivesse la - o .bat dizia
rem "AINDA E O ANTIGO" e parava, toda vez, de 16 a 22/09/2026.
echo   Garantindo que o arquivo esta baixado no disco...
type "%ORIGEM%\rasterlink_hotfolder.py" >nul 2>&1

rem A conferencia mais importante do arquivo. O OneDrive demora, e as
rem vezes muito: ja mediu 10 minutos pra um PDF chegar aqui. Sem esta
rem linha, rodar cedo demais copiaria o arquivo ANTIGO por cima e
rem diria "pronto" - falha silenciosa, que e a pior de todas.
rem
rem /OFFLINE: nao pular arquivo que ainda e marcador do OneDrive.
rem
rem A marca procurada tem que ser da ULTIMA versao, nunca de uma que
rem ja esta instalada: com marca velha esta conferencia passa com o
rem arquivo antigo e deixa de servir. Trocar a cada deploy.
rem Hoje: conciliar_registro (registro que nao se perde, 16/09/2026).
findstr /m /offline /c:"conciliar_registro" "%ORIGEM%\rasterlink_hotfolder.py" >nul
if errorlevel 1 (
  echo.
  echo   PAREI: nao achei a marca da versao nova no arquivo de deploy.
  echo   Ou ele ainda e o antigo, ou o OneDrive nao conseguiu baixar.
  echo.
  echo   O que fazer: no Explorador, clique com o botao direito na pasta
  echo   de deploy e escolha "Manter sempre neste dispositivo". Espere o
  echo   verdinho de baixado e rode este .bat de novo.
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

rem Deixa a pasta de deploy sempre baixada NESTE PC, pra o proximo deploy
rem nao esbarrar de novo no arquivo que e so marcador na nuvem. O +P e o
rem "Manter sempre neste dispositivo" do OneDrive. Falhou, nao faz mal.
attrib +p "%ORIGEM%\*.*" >nul 2>&1

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

echo.
echo   O arquivo trocado so vale na proxima passada do vigia. Dentro de
echo   5 minutos o sinal de vida ja sai da versao nova - da pra conferir
echo   pela tela de Enviar para impressao, sem vir ate aqui.

:fim
echo.
pause
endlocal
