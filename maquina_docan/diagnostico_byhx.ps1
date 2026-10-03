try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch {}

# SO OLHA o programa da impressora (BYHX Printer Manager). Nao muda nada,
# nao precisa de administrador.
#
# Por que (03/10/2026): ele perguntou o que da pra automatizar no programa
# da maquina. As respostas boas dependem de tres coisas que so se sabe
# olhando ESTA maquina:
#
#   1. o BYHX guarda HISTORICO do que imprimiu? Onde? (se guardar, o
#      relatorio de producao deixa de provar o que foi ENTREGUE e passa a
#      provar o que foi IMPRESSO, com os metros de verdade)
#   2. ele tem HOT FOLDER / carga automatica? (fecharia a ultima perna:
#      o .prt sai do SAi e entra na fila da impressora sozinho)
#   3. onde estao os .prt e quanto espaco sobra? (um .prt de lona de 14 m
#      pesa GIGAS, e disco cheio trava a maquina inteira)
#
# Grava tudo em diagnostico_byhx_<PC>.txt nesta mesma pasta, que esta no
# OneDrive — e o outro computador le dali, sem ninguem copiar nada.

$ErrorActionPreference = "Continue"
try { Start-Transcript -Path (Join-Path $PSScriptRoot ("diagnostico_byhx_{0}.txt" -f $env:COMPUTERNAME)) -Force | Out-Null } catch { }

function Titulo($t) {
    Write-Host ""
    Write-Host ("=" * 72)
    Write-Host "  $t"
    Write-Host ("=" * 72)
}

Write-Host ""
Write-Host "  O PROGRAMA DA IMPRESSORA, POR DENTRO"
Write-Host "  Maquina: $env:COMPUTERNAME   Agora: $(Get-Date -Format 'dd/MM HH:mm')"

Titulo "1  O programa esta rodando?"
$procs = Get-Process | Where-Object { $_.Name -match "byhx|printer.?manager|kmprint|hoson|ultra" }
if ($procs) {
    foreach ($p in $procs) {
        $caminho = ""
        try { $caminho = $p.Path } catch { $caminho = "(sem acesso ao caminho)" }
        Write-Host "  $($p.Name)  pid $($p.Id)"
        Write-Host "     $caminho"
    }
} else { Write-Host "  nenhum processo com cara de programa de impressora agora" }

Titulo "2  Onde ele esta instalado"
$raizes = @()
foreach ($b in @("$env:ProgramFiles", "${env:ProgramFiles(x86)}", "C:\", "D:\")) {
    if (-not (Test-Path $b)) { continue }
    $raizes += Get-ChildItem $b -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match "byhx|hoson|printer|konica|docan|km1024" }
}
# o atalho da area de trabalho costuma ser o caminho mais curto pra verdade
$sh = New-Object -ComObject WScript.Shell
foreach ($lnk in (Get-ChildItem "$env:USERPROFILE\Desktop","C:\Users\Public\Desktop" -Filter *.lnk -ErrorAction SilentlyContinue)) {
    try {
        $alvo = $sh.CreateShortcut($lnk.FullName).TargetPath
        if ($alvo -match "byhx|printer|hoson|konica") { Write-Host "  atalho '$($lnk.BaseName)' -> $alvo" }
    } catch { }
}
if ($raizes) { foreach ($r in $raizes) { Write-Host "  pasta: $($r.FullName)" } }
else { Write-Host "  nao achei pasta com nome obvio — veja o atalho acima" }

Titulo "3  Arquivos de configuracao e de HISTORICO"
# E aqui que mora a resposta: se existir .db/.xml/.csv/.log com o que foi
# impresso, da pra fechar o ciclo da comprovacao.
$pastas = @()
if ($procs) { foreach ($p in $procs) { try { if ($p.Path) { $pastas += Split-Path -Parent $p.Path } } catch { } } }
foreach ($r in $raizes) { $pastas += $r.FullName }
$pastas += "$env:APPDATA", "$env:LOCALAPPDATA", "$env:ProgramData"
$pastas = $pastas | Sort-Object -Unique

foreach ($pasta in $pastas) {
    if (-not (Test-Path $pasta)) { continue }
    $achados = Get-ChildItem $pasta -Recurse -Depth 2 -File -ErrorAction SilentlyContinue |
        Where-Object { $_.Extension -match "^\.(ini|xml|db|sqlite|csv|log|dat|cfg|json)$" -and
                       ($_.FullName -match "byhx|hoson|printer|job|history|log|konica" ) } |
        Sort-Object LastWriteTime -Descending | Select-Object -First 12
    if ($achados) {
        Write-Host ""
        Write-Host "  em $pasta"
        foreach ($a in $achados) {
            Write-Host ("     {0,-52} {1,8:N0} KB  {2}" -f $a.Name, ($a.Length/1KB), $a.LastWriteTime.ToString("dd/MM HH:mm"))
        }
    }
}

Titulo "4  Tem HOT FOLDER / carga automatica configurada?"
# Procura a palavra nos .ini do programa — e o que diria se da pra o .prt
# entrar na fila sozinho quando o SAi terminar de ripar.
$achouChave = $false
foreach ($pasta in $pastas) {
    if (-not (Test-Path $pasta)) { continue }
    foreach ($ini in (Get-ChildItem $pasta -Recurse -Depth 2 -Include *.ini,*.xml,*.cfg -File -ErrorAction SilentlyContinue | Select-Object -First 40)) {
        $linhas = Select-String -Path $ini.FullName -Pattern "hot.?folder|auto.?load|auto.?print|watch.?dir|monitor.?path" -ErrorAction SilentlyContinue
        foreach ($l in $linhas) {
            $achouChave = $true
            Write-Host "  $($ini.Name): $($l.Line.Trim())"
        }
    }
}
if (-not $achouChave) { Write-Host "  nenhuma chave de hot folder encontrada nos arquivos de configuracao" }

Titulo "5  Os ripados (.prt) e o espaco em disco"
foreach ($p in @("$env:USERPROFILE\Desktop\RIPADOS", "D:\RIPADOS", "C:\RIPADOS")) {
    if (-not (Test-Path $p)) { continue }
    $arqs = Get-ChildItem $p -Recurse -File -ErrorAction SilentlyContinue
    $gb = [math]::Round(($arqs | Measure-Object Length -Sum).Sum / 1GB, 2)
    Write-Host "  $p : $($arqs.Count) arquivo(s), $gb GB"
    $arqs | Sort-Object LastWriteTime -Descending | Select-Object -First 5 | ForEach-Object {
        Write-Host ("     {0,-50} {1,7:N1} GB  {2}" -f $_.Name, ($_.Length/1GB), $_.LastWriteTime.ToString("dd/MM HH:mm"))
    }
}
foreach ($d in (Get-PSDrive -PSProvider FileSystem -ErrorAction SilentlyContinue | Where-Object { $_.Used })) {
    Write-Host ("  disco {0}: {1,6:N0} GB livres de {2,6:N0} GB" -f $d.Name, ($d.Free/1GB), (($d.Used + $d.Free)/1GB))
}

Titulo "6  A impressora responde na rede?"
# O BYHX fala com a placa da maquina por rede. Saber o IP dela abre a porta
# pra ler estado (tinta, erro) sem depender da janela aberta.
Get-NetIPConfiguration -ErrorAction SilentlyContinue | ForEach-Object {
    Write-Host "  $($_.InterfaceAlias): $($_.IPv4Address.IPAddress)"
}
Get-NetNeighbor -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object { $_.State -eq "Reachable" } | Select-Object -First 10 |
    ForEach-Object { Write-Host "  vizinho na rede: $($_.IPAddress)" }

Write-Host ""
Write-Host "  ---- fim ----"
try {
    Stop-Transcript | Out-Null
    Write-Host ""
    Write-Host "  Gravei em diagnostico_byhx_$env:COMPUTERNAME.txt, nesta pasta."
    Write-Host "  Deixe o OneDrive sincronizar — do outro PC da pra ler tudo isto."
} catch { }
