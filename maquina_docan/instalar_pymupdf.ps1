# Instala o PyMuPDF no Python que a TAREFA usa, nesta máquina. Rode pelo
# instalar_pymupdf.bat, ao lado deste arquivo.
#
# POR QUE (autorizado por ele em 04/10/2026: "vamos instalar e deixar completo")
# Sem o PyMuPDF o vigia entrega a arte normalmente, mas perde duas coisas:
#
#   1. A MEDIDA DA PÁGINA no registro de produção. Quando o nome do
#      arquivo não traz medida ("emendas_01_montado.pdf"), é dela que o
#      relatório tira o m² — e sem ela a linha sai "medida não lida",
#      sem jeito de recuperar depois, porque o arquivo sai de "Enviados"
#      em 15 dias.
#   2. O AVISO de arte que não cabe na máquina. Aviso, nunca barreira.
#
# O QUE ISTO **NÃO** LIGA: GIRO.
# "DOCAN só entrega" continua valendo (regra dele de 24/09/2026). Quem
# segura o giro é o campo "girar": False no cadastro das duas DOCAN, e
# não a falta da biblioteca — conferido no código (LimiteDaMaquina.
# decidir_giro devolve None quando não gira) e travado em teste. A arte
# continua chegando ao SAi byte a byte como saiu da fila.
#
# NÃO precisa de administrador: o Python daqui é instalado por usuário.

$ErrorActionPreference = "Stop"

try {
    Start-Transcript -Path (Join-Path $PSScriptRoot ("pymupdf_{0}.txt" -f $env:COMPUTERNAME)) -Force | Out-Null
} catch { }

$NOME_TAREFA = "Vigia DOCAN (SAi)"
$PASTA       = "C:\VigiaDocan"

function Fechar($codigo) {
    try { Stop-Transcript | Out-Null } catch { }
    exit $codigo
}

function Parar($linhas) {
    Write-Host ""
    Write-Host "  PAREI." -ForegroundColor Red
    foreach ($l in $linhas) { Write-Host "  $l" -ForegroundColor Yellow }
    Write-Host ""
    Fechar 1
}

# Rodar programa nativo com ErrorActionPreference = "Stop" derruba o
# script na primeira linha de stderr — e pip fala MUITO em stderr. Ver a
# mesma lição no atualizar.ps1 (04/10/2026).
function RodarPython($exe, $argumentos) {
    $console = $exe -replace "pythonw\.exe$", "python.exe"
    if (-not (Test-Path $console)) { $console = $exe }
    $ioAntigo = $env:PYTHONIOENCODING
    $env:PYTHONIOENCODING = "utf-8"
    $fSaida = Join-Path $env:TEMP "pymupdf_saida.txt"
    $fErro  = Join-Path $env:TEMP "pymupdf_erro.txt"
    try {
        $proc = Start-Process -FilePath $console -ArgumentList $argumentos `
                              -WorkingDirectory $PASTA -NoNewWindow -Wait -PassThru `
                              -RedirectStandardOutput $fSaida -RedirectStandardError $fErro
        $codigo = $proc.ExitCode
    } catch {
        return @{ saida = @("não consegui rodar o $console : $($_.Exception.Message)"); codigo = $null }
    } finally {
        $env:PYTHONIOENCODING = $ioAntigo
    }
    $linhas = @()
    foreach ($f in @($fSaida, $fErro)) {
        if (Test-Path $f) {
            $linhas += @(Get-Content $f -Encoding UTF8 -ErrorAction SilentlyContinue)
            Remove-Item $f -Force -ErrorAction SilentlyContinue
        }
    }
    return @{ saida = @($linhas | Where-Object { "$_".Trim() }); codigo = $codigo }
}

Write-Host ""
Write-Host "  COMPLETAR O VIGIA DESTA MÁQUINA (PyMuPDF)"
Write-Host "  Esta máquina: $env:COMPUTERNAME   Agora: $(Get-Date -Format 'dd/MM HH:mm')"
Write-Host ""

# 1. O Python é o DA TAREFA, não "um python qualquer do PATH".
#
# Instalar na biblioteca do Python errado é o jeito mais fácil de isto
# parecer funcionar e não mudar nada: o vigia continuaria sem enxergar a
# biblioteca, e o aviso "pymupdf não instalado" seguiria no log.
$exe = $null
try {
    $tarefa = Get-ScheduledTask -TaskName $NOME_TAREFA -ErrorAction Stop
    $exe = $tarefa.Actions[0].Execute
} catch { }
if (-not $exe -or -not (Test-Path $exe)) {
    Parar @("Não achei o Python da tarefa '$NOME_TAREFA'.",
            "O vigia precisa estar instalado aqui antes — rode o instalar_tarefa.bat.")
}
Write-Host "  Python da tarefa: $exe"

# 2. Já está instalado?
$r = RodarPython $exe @("-c", "import pymupdf,sys;print(pymupdf.__version__)")
if ($r.codigo -eq 0 -and $r.saida) {
    Write-Host "  Já estava instalado: PyMuPDF $($r.saida[-1])" -ForegroundColor Green
    Write-Host "  Nada a fazer." -ForegroundColor Green
    Fechar 0
}

# 3. Instalar.
Write-Host ""
Write-Host "  Instalando (são uns 20 MB; pode levar um minuto)..."
$r = RodarPython $exe @("-m", "pip", "install", "--disable-pip-version-check", "pymupdf")
foreach ($linha in $r.saida) { Write-Host "    $linha" }
if ($r.codigo -ne 0) {
    Parar @("O pip terminou com resultado $($r.codigo).",
            "Se falou de rede ou proxy, tente de novo; a mensagem acima diz o motivo.")
}

# 4. A PROVA: o Python da tarefa consegue ABRIR um PDF e medir.
#
# "pip install deu certo" não é prova de nada — o que o vigia faz é abrir
# o arquivo e medir a página. É isso que tem que funcionar.
Write-Host ""
Write-Host "  Conferindo do jeito que o vigia usa (abrir um PDF e medir)..."
$codigo = @"
import sys
sys.path.insert(0, r'$PASTA')
import pathlib, tempfile
import pymupdf
pt = 72 / 2.54
d = pymupdf.open()
d.new_page(width=215 * pt, height=140 * pt)
alvo = pathlib.Path(tempfile.gettempdir()) / '_conferencia_pymupdf.pdf'
d.save(str(alvo)); d.close()
import rasterlink_hotfolder as r
print('medida lida:', r.medida_da_pagina(alvo))
print('versao:', pymupdf.__version__)
alvo.unlink()
"@
$arquivo = Join-Path $env:TEMP "conferir_pymupdf.py"
Set-Content -LiteralPath $arquivo -Value $codigo -Encoding UTF8
$r = RodarPython $exe @($arquivo)
Remove-Item $arquivo -Force -ErrorAction SilentlyContinue
foreach ($linha in $r.saida) { Write-Host "    $linha" }

Write-Host ""
if ($r.codigo -eq 0 -and ($r.saida -join " ") -match "medida lida: \(2\.15") {
    Write-Host "  TUDO CERTO. O vigia já mede a página (2,15 x 1,40 m conferidos)." -ForegroundColor Green
    Write-Host "  Da próxima entrega em diante, a medida vai pro registro de produção" -ForegroundColor Green
    Write-Host "  e o aviso de 'não cabe' passa a funcionar nesta máquina." -ForegroundColor Green
    Write-Host "  O GIRO continua desligado: a arte segue byte a byte pro SAi." -ForegroundColor Green
} else {
    Write-Host "  Instalou, mas a conferência não deu o resultado esperado." -ForegroundColor Yellow
    Write-Host "  Mande as linhas acima pra quem cuida do vigia." -ForegroundColor Yellow
}

Write-Host ""
Fechar 0
