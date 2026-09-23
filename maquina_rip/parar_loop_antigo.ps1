try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch {}   # acentos na tela
param([switch]$Simular)

# --------------------------------------------------------------------
#  Para o vigia ANTIGO (o loop do .pyw, anterior a 05/09/2026) que ficou
#  vivo na máquina do RIP e SEGURA A TRAVA.
#
#  Por que isso importa (descoberto em 22/09/2026): a tarefa agendada
#  roda a versão nova a cada minuto e termina com código 0 — mas sem
#  fazer nada, porque a trava de instância única está ocupada pelo loop
#  antigo. O arquivo novo estava instalado desde 16/09 e mesmo assim
#  quem trabalhava era o código velho. O sinal de vida provou: ele
#  chegava fresquinho e sem o campo 'registro_pendente'.
#
#  Este script: mostra o que vai parar, para, impede de voltar, roda uma
#  passada da versão nova e FICA OLHANDO o sinal de vida até ele mudar.
#  Confirmar é parte do trabalho — mensagem de script não é prova.
# --------------------------------------------------------------------

$PASTA = "C:\RasterLink"
$SCRIPT = Join-Path $PASTA "rasterlink_hotfolder.py"
$PYW = Join-Path $PASTA "rasterlink_hotfolder.pyw"

function Titulo($texto) {
    Write-Host ""
    Write-Host ("=" * 72) -ForegroundColor DarkGray
    Write-Host "  $texto" -ForegroundColor Cyan
    Write-Host ("=" * 72) -ForegroundColor DarkGray
}

Write-Host ""
Write-Host "  Maquina: $env:COMPUTERNAME    Usuario: $env:USERNAME    Agora: $(Get-Date -Format 'dd/MM HH:mm:ss')"
if ($Simular) { Write-Host "  (MODO SIMULACAO: nao para nem renomeia nada)" -ForegroundColor Yellow }

# ------------------------------------------------------- 1. quem está vivo
Titulo "1  VIGIA ANTIGO RODANDO AGORA"

# O da tarefa nova nasce, trabalha 2s e morre, e sempre traz '--uma-vez'.
# Qualquer outro python com 'rasterlink_hotfolder' na linha de comando é
# loop antigo — é ele que segura a trava a manhã inteira.
$loops = @(Get-CimInstance Win32_Process -Filter "Name = 'python.exe' OR Name = 'pythonw.exe'" -ErrorAction SilentlyContinue |
           Where-Object { $_.CommandLine -like "*rasterlink_hotfolder*" -and $_.CommandLine -notlike "*--uma-vez*" })

if ($loops.Count -eq 0) {
    Write-Host "  Nenhum loop antigo rodando. Nada pra parar aqui." -ForegroundColor Green
} else {
    foreach ($p in $loops) {
        Write-Host "  PID $($p.ProcessId)  desde $($p.CreationDate)" -ForegroundColor Yellow
        Write-Host "      $($p.CommandLine)"
    }
    Write-Host ""
    Write-Host "  Enquanto eles estiverem vivos, a tarefa nova roda e nao faz nada." -ForegroundColor Yellow
    if (-not $Simular) {
        $r = Read-Host "  Parar esses $($loops.Count) processo(s)? (S para parar)"
        if ($r -notmatch '^[SsYy]') {
            Write-Host "  Parei aqui. Nada foi alterado." -ForegroundColor Yellow
            return
        }
        foreach ($p in $loops) {
            try {
                Stop-Process -Id $p.ProcessId -Force -ErrorAction Stop
                Write-Host "  parado: PID $($p.ProcessId)" -ForegroundColor Green
            } catch {
                Write-Host "  NAO consegui parar o PID $($p.ProcessId): $_" -ForegroundColor Red
            }
        }
        Start-Sleep -Seconds 2
    }
}

# --------------------------------------------- 2. impedir que volte sozinho
Titulo "2  IMPEDIR QUE O LOOP ANTIGO VOLTE"

if (Test-Path $PYW) {
    $i = Get-Item $PYW
    Write-Host "  Existe o arquivo do loop antigo: $PYW"
    Write-Host "  $($i.Length) bytes, de $($i.LastWriteTime)"
    if (-not $Simular) {
        $desligado = "$PYW.desligado"
        if (Test-Path $desligado) { Remove-Item $desligado -Force -ErrorAction SilentlyContinue }
        try {
            Rename-Item $PYW "$([System.IO.Path]::GetFileName($PYW)).desligado" -ErrorAction Stop
            Write-Host "  Renomeado para ...pyw.desligado — nada consegue mais iniciar ele." -ForegroundColor Green
            Write-Host "  (o arquivo continua ali, e so renomear de volta se precisar)"
        } catch {
            Write-Host "  NAO consegui renomear: $_" -ForegroundColor Red
        }
    }
} else {
    Write-Host "  Nao existe $PYW — nada a desligar." -ForegroundColor Green
}

Write-Host ""
Write-Host "  Quem costuma iniciar ele no logon:"
$achou = $false
$lugares = @(
    [Environment]::GetFolderPath('Startup'),
    [Environment]::GetFolderPath('CommonStartup')
)
foreach ($pasta in $lugares) {
    if (-not $pasta -or -not (Test-Path $pasta)) { continue }
    foreach ($f in @(Get-ChildItem $pasta -File -ErrorAction SilentlyContinue)) {
        $alvo = ""
        if ($f.Extension -eq ".lnk") {
            try { $alvo = (New-Object -ComObject WScript.Shell).CreateShortcut($f.FullName).TargetPath +
                          " " + (New-Object -ComObject WScript.Shell).CreateShortcut($f.FullName).Arguments } catch {}
        } else {
            try { $alvo = Get-Content $f.FullName -Raw -ErrorAction SilentlyContinue } catch {}
        }
        if ("$($f.Name) $alvo" -like "*rasterlink*") {
            $achou = $true
            Write-Host "    ATALHO: $($f.FullName)" -ForegroundColor Yellow
            Write-Host "            -> $alvo"
        }
    }
}
foreach ($chave in @("HKCU:\Software\Microsoft\Windows\CurrentVersion\Run",
                     "HKLM:\Software\Microsoft\Windows\CurrentVersion\Run")) {
    if (-not (Test-Path $chave)) { continue }
    $itens = Get-ItemProperty $chave
    foreach ($nome in $itens.PSObject.Properties.Name) {
        if ($nome -like "PS*") { continue }
        if ("$nome $($itens.$nome)" -like "*rasterlink*") {
            $achou = $true
            Write-Host "    REGISTRO: $chave -> $nome" -ForegroundColor Yellow
            Write-Host "              $($itens.$nome)"
        }
    }
}
if (-not $achou) {
    Write-Host "    Nada encontrado na inicializacao. Com o .pyw desligado, ele nao volta." -ForegroundColor Green
} else {
    Write-Host "    >>> Pode apagar o que esta marcado acima: quem cuida da fila agora e a" -ForegroundColor Yellow
    Write-Host "        tarefa 'RasterLink Hotfolder', que roda sozinha a cada minuto." -ForegroundColor Yellow
}

# ------------------------------------------------- 3. uma passada da nova
Titulo "3  UMA PASSADA COM A VERSAO NOVA"

if (-not (Test-Path $SCRIPT)) {
    Write-Host "  NAO EXISTE $SCRIPT — rode o atualizar.bat antes." -ForegroundColor Red
    return
}
if (-not (Select-String -Path $SCRIPT -Pattern "conciliar_registro" -Quiet)) {
    Write-Host "  O script instalado nao tem a marca da versao nova." -ForegroundColor Red
    Write-Host "  Rode o atualizar.bat antes deste." -ForegroundColor Red
    return
}
Write-Host "  O script instalado e o novo (tem conciliar_registro)." -ForegroundColor Green

$py = $null
foreach ($c in @("$env:LOCALAPPDATA\Python\pythoncore-3.14-64\python.exe",
                 "$env:LOCALAPPDATA\Python\pythoncore-3.13-64\python.exe")) {
    if (-not $py -and (Test-Path $c)) { $py = $c }
}
if (-not $py) { $py = (Get-Command python.exe -ErrorAction SilentlyContinue).Source }

if ($Simular) {
    Write-Host "  (simulacao: nao rodei a passada)" -ForegroundColor Yellow
} elseif (-not $py) {
    Write-Host "  Nao achei o python. A tarefa agendada roda sozinha no proximo minuto." -ForegroundColor Yellow
} else {
    Write-Host "  Rodando: $py -m rasterlink_hotfolder --uma-vez"
    Push-Location $PASTA
    & $py -m rasterlink_hotfolder --uma-vez
    Write-Host "  Codigo de saida: $LASTEXITCODE"
    Pop-Location
}

# ------------------------------------------------- 4. a prova: sinal de vida
Titulo "4  A PROVA: O SINAL DE VIDA"

# Mensagem de script nao prova nada. Quem diz que a versao nova esta
# trabalhando e o sinal de vida: so ela grava 'registro_pendente'.
$fila = Get-ChildItem "$env:USERPROFILE\OneDrive\UNYCOMUNICACAO" -Directory -Filter "Fila*RasterLink" -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $fila) {
    Write-Host "  Nao achei a pasta da fila no OneDrive desta maquina." -ForegroundColor Red
    return
}
$sinal = Join-Path $fila.FullName "_sinal_de_vida.json"
Write-Host "  Olhando $sinal"
Write-Host "  O sinal e reescrito a cada 5 minutos — espero ate 6." -ForegroundColor DarkGray

$fim = (Get-Date).AddMinutes(6)
$ok = $false
while ((Get-Date) -lt $fim) {
    if (Test-Path $sinal) {
        try {
            $dados = Get-Content -Raw -LiteralPath $sinal | ConvertFrom-Json
            $tem = $dados.PSObject.Properties.Name -contains "registro_pendente"
            $quando = [datetime]::Parse($dados.quando)
            if ($tem) {
                Write-Host ""
                Write-Host "  VERSAO NOVA CONFIRMADA. Sinal de $($quando.ToString('dd/MM HH:mm:ss'))," -ForegroundColor Green
                Write-Host "  entregas ainda fora do relatorio: $($dados.registro_pendente)" -ForegroundColor Green
                $ok = $true
                break
            }
        } catch {}
    }
    Write-Host "." -NoNewline
    Start-Sleep -Seconds 15
}
if (-not $ok) {
    Write-Host ""
    Write-Host "  O sinal ainda nao mudou de versao. Nao conclua nada agora:" -ForegroundColor Yellow
    Write-Host "  espere mais alguns minutos e rode o diagnostico.bat." -ForegroundColor Yellow
}
Write-Host ""
Write-Host "  ---- fim ----"
