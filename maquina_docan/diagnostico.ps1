try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch {}   # acentos na tela

# SÓ OLHA. Não muda nada, não cria nada, não apaga nada.
#
# Existe porque a máquina da DOCAN não é vista daqui do PC principal (nem
# ping, nem rede), e transcrever mensagem de tela a dois computadores de
# distância é lento e erra. Ele responde, de uma vez, o que o instalador
# precisa saber — e ESCREVE O RESULTADO NA PASTA DO ONEDRIVE, que é o
# único caminho que as duas máquinas enxergam.
#
# Não precisa de administrador: só lê.

$ErrorActionPreference = "Continue"

$NOME_TAREFA = "Vigia DOCAN (SAi)"
$PASTA       = "C:\VigiaDocan"
$SCRIPT      = Join-Path $PASTA "rasterlink_hotfolder.py"
$LOG         = Join-Path $PASTA "rasterlink_hotfolder.log"

$linhas = New-Object System.Collections.Generic.List[string]
function Diga($texto) {
    $linhas.Add($texto) | Out-Null
    Write-Host $texto
}
function Titulo($texto) {
    Diga ""
    Diga ("=" * 72)
    Diga "  $texto"
    Diga ("=" * 72)
}

Diga ""
Diga "  DIAGNOSTICO DO VIGIA DA DOCAN"
Diga "  Maquina: $env:COMPUTERNAME   Usuario: $env:USERNAME   Agora: $(Get-Date -Format 'dd/MM HH:mm:ss')"

# --------------------------------------------------------------------
Titulo "1  O PYTHON"

$encontrados = @()
foreach ($padrao in @(
    "$env:LOCALAPPDATA\Python\pythoncore-3.*\pythonw.exe",
    "$env:LOCALAPPDATA\Programs\Python\Python3*\pythonw.exe",
    "$env:ProgramFiles\Python3*\pythonw.exe",
    "${env:ProgramFiles(x86)}\Python3*\pythonw.exe",
    "C:\Python3*\pythonw.exe")) {
    $encontrados += @(Get-ChildItem -Path $padrao -ErrorAction SilentlyContinue)
}
if ($encontrados.Count -eq 0) {
    Diga "  NAO ACHEI Python instalado nos lugares de sempre."
} else {
    foreach ($e in $encontrados) { Diga "  achei: $($e.FullName)" }
}
$doPath = Get-Command pythonw.exe -ErrorAction SilentlyContinue
if ($doPath) {
    $tam = (Get-Item $doPath.Source).Length
    $aviso = ""
    if ($doPath.Source -match "WindowsApps" -or $tam -eq 0) { $aviso = "   <<< ATALHO DA LOJA, NAO SERVE" }
    Diga "  no PATH: $($doPath.Source) ($tam bytes)$aviso"
} else {
    Diga "  no PATH: nenhum pythonw"
}

$PYTHON = $null
if ($encontrados.Count -gt 0) {
    $PYTHON = ($encontrados | Sort-Object FullName -Descending | Select-Object -First 1).FullName -replace 'pythonw\.exe$', 'python.exe'
}

# --------------------------------------------------------------------
Titulo "2  O VIGIA COPIADO PRA $PASTA"

if (Test-Path $SCRIPT) {
    $f = Get-Item $SCRIPT
    Diga "  existe: $($f.Length) bytes, de $($f.LastWriteTime)"
} else {
    Diga "  NAO EXISTE $SCRIPT"
    Diga "  >>> o instalador parou antes de copiar, ou nem chegou a rodar."
}

# --------------------------------------------------------------------
Titulo "3  O QUE O VIGIA ENXERGA DESTA MAQUINA"

if (-not $PYTHON -or -not (Test-Path $SCRIPT)) {
    Diga "  (pulei: falta o Python ou o arquivo do vigia)"
} else {
    $codigo = @"
import rasterlink_hotfolder as r, os
print('fila: %s' % r.PASTA_FILA_ONEDRIVE)
print('fila existe: %s' % os.path.isdir(r.PASTA_FILA_ONEDRIVE))
for nome, cfg in r.maquinas_do_posto('sai').items():
    hot = r._config_maquina(cfg)[0]
    print('%s -> %s | existe: %s' % (nome, hot, os.path.isdir(hot)))
print('posto de outra maquina: %s' % (r.outro_vigia_no_posto(posto='sai') or 'ninguem'))
"@
    Push-Location $PASTA
    $saida = & $PYTHON -c $codigo 2>&1
    Pop-Location
    foreach ($l in $saida) { Diga "  $l" }
}

# --------------------------------------------------------------------
Titulo "4  ONDE O SAi GUARDA AS PASTAS DOS SETUPS"

# Quando a hot folder do cadastro nao existe, a resposta esta aqui: o SAi
# corta o nome da pasta em 12 letras e numera pela ORDEM em que os setups
# foram criados, entao 'Docan_1' nesta maquina pode ser outro setup.
$raizes = @(
    "$env:ProgramFiles\SAi\SAi Production Suite 22\Jobs and Settings\Jobs",
    "${env:ProgramFiles(x86)}\SAi\SAi Production Suite 22\Jobs and Settings\Jobs",
    "$env:ProgramFiles\SAi\SAi Production Suite\Jobs and Settings\Jobs"
)
$achou = $false
foreach ($raiz in $raizes) {
    if (Test-Path $raiz) {
        $achou = $true
        Diga "  $raiz"
        Get-ChildItem $raiz -Directory -Recurse -Depth 1 -ErrorAction SilentlyContinue |
            ForEach-Object { Diga "    $($_.FullName)" }
    }
}
if (-not $achou) { Diga "  NAO achei a pasta Jobs do SAi nos lugares de sempre." }

# --------------------------------------------------------------------
Titulo "5  A TAREFA DO AGENDADOR"

$tarefa = Get-ScheduledTask -TaskName $NOME_TAREFA -ErrorAction SilentlyContinue
if ($null -eq $tarefa) {
    Diga "  NAO EXISTE tarefa '$NOME_TAREFA' nesta maquina."
    Diga "  >>> o instalador nao chegou a cria-la."
} else {
    $info = Get-ScheduledTaskInfo -TaskName $NOME_TAREFA
    Diga "  Estado..............: $($tarefa.State)"
    Diga "  Ultima execucao.....: $($info.LastRunTime)"
    Diga "  Resultado da ultima.: $($info.LastTaskResult)   (0 = deu certo)"
    Diga "  Proxima execucao....: $($info.NextRunTime)"
    foreach ($a in $tarefa.Actions) { Diga "  Roda................: $($a.Execute) $($a.Arguments)" }
}

# --------------------------------------------------------------------
Titulo "6  O LOG DO VIGIA"

if (Test-Path $LOG) {
    Diga "  $LOG"
    Get-Content $LOG -Encoding UTF8 -Tail 15 -ErrorAction SilentlyContinue | ForEach-Object { Diga "    $_" }
} else {
    Diga "  ainda nao existe log: o vigia nunca rodou aqui."
}

# --------------------------------------------------------------------
Titulo "7  GRAVANDO O RESULTADO ONDE O OUTRO PC LE"

$destino = $PSScriptRoot
$arquivo = Join-Path $destino ("diagnostico_{0}.txt" -f $env:COMPUTERNAME)
try {
    $linhas -join "`r`n" | Out-File $arquivo -Encoding utf8
    Write-Host ""
    Write-Host "  Gravei em: $arquivo" -ForegroundColor Green
    Write-Host "  Deixe o OneDrive sincronizar e avise — do outro PC eu leio isto." -ForegroundColor Green
} catch {
    Write-Host "  Nao consegui gravar o resultado: $($_.Exception.Message)" -ForegroundColor Yellow
}
