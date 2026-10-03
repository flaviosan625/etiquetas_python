# Tranca as pastas onde o AnyDesk se instala, pra ele nao voltar sozinho.
#
# Pedido dele (03/10/2026), depois de desinstalar o programa: "bloquear as
# pastas do programa AnyDesk, nao deixar instalar nada que va gerar aquelas
# propagandas; mesmo com servico gratuito nao sou obrigado a ver propaganda".
#
# COMO FUNCIONA
# Cria as duas pastas VAZIAS e nega, pra Todos, o direito de escrever e de
# apagar. Instalador que tenta gravar ali falha — e negacao ganha de
# permissao no Windows, entao nem rodando como administrador ele passa.
#
# O QUE ISTO NAO FAZ (pra nao prometer o que nao cumpre)
#   - Nao impede o AnyDesk PORTATIL, que roda sem instalar, de outra pasta.
#   - Nao tira propaganda de um AnyDesk ja instalado noutro lugar: o anuncio
#     vem de dentro do proprio programa.
#   - Quem quer acesso remoto sem propaganda tem dois caminhos limpos: a
#     Area de Trabalho Remota do proprio Windows, ou o RustDesk, que e aberto
#     e sem anuncio.
#
# PRA DESFAZER: rode com -Desfazer. Ele devolve as pastas ao normal e
# apaga as que estiverem vazias.

param([switch]$Desfazer)

$ErrorActionPreference = "Continue"

# 'Todos' em qualquer idioma do Windows: o SID nao muda de nome.
$TODOS = "*S-1-1-0"
$PASTAS = @(
    "$env:ProgramFiles\AnyDesk",
    "${env:ProgramFiles(x86)}\AnyDesk",
    "$env:ProgramData\AnyDesk",
    "$env:APPDATA\AnyDesk",
    "$env:LOCALAPPDATA\AnyDesk"
)

function Titulo($t) {
    Write-Host ""
    Write-Host ("=" * 68) -ForegroundColor DarkGray
    Write-Host "  $t" -ForegroundColor Cyan
    Write-Host ("=" * 68) -ForegroundColor DarkGray
}

$souAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
            ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $souAdmin) {
    Write-Host ""
    Write-Host "  Preciso de administrador pra mexer nas permissoes. Vou pedir..." -ForegroundColor Yellow
    $args = @("-NoProfile","-ExecutionPolicy","Bypass","-File",$PSCommandPath)
    if ($Desfazer) { $args += "-Desfazer" }
    try { Start-Process powershell -ArgumentList $args -Verb RunAs | Out-Null } catch {
        Write-Host "  Permissao recusada. Nada foi alterado." -ForegroundColor Red
    }
    exit 0
}

if ($Desfazer) {
    Titulo "DESFAZENDO o bloqueio do AnyDesk"
    foreach ($p in $PASTAS) {
        if (-not (Test-Path $p)) { continue }
        icacls $p /remove:d $TODOS | Out-Null
        $vazia = -not (Get-ChildItem $p -Force -ErrorAction SilentlyContinue)
        if ($vazia) {
            Remove-Item $p -Force -ErrorAction SilentlyContinue
            Write-Host "  liberada e apagada (estava vazia): $p" -ForegroundColor Green
        } else {
            Write-Host "  liberada (tem arquivo dentro, deixei): $p" -ForegroundColor Yellow
        }
    }
    Write-Host ""
    Write-Host "  Pronto. O AnyDesk volta a poder ser instalado." -ForegroundColor Green
    exit 0
}

Titulo "1/3  O AnyDesk ainda esta instalado?"

$achados = @()
foreach ($r in @("HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*",
                 "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*",
                 "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*")) {
    $achados += @(Get-ItemProperty $r -ErrorAction SilentlyContinue | Where-Object { $_.DisplayName -like "*AnyDesk*" })
}
if ($achados.Count -gt 0) {
    Write-Host "  AINDA ESTA INSTALADO. Desinstale primeiro, senao o bloqueio" -ForegroundColor Red
    Write-Host "  tranca um programa que esta em uso:" -ForegroundColor Red
    foreach ($a in $achados) { Write-Host "    $($a.DisplayName) $($a.DisplayVersion)" -ForegroundColor Yellow }
    Write-Host ""
    Write-Host "  Pra desinstalar: " -ForegroundColor Cyan -NoNewline
    Write-Host '$e = @("$env:ProgramFiles\AnyDesk\AnyDesk.exe","${env:ProgramFiles(x86)}\AnyDesk\AnyDesk.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1; Start-Process $e -ArgumentList "--remove","--silent" -Verb RunAs -Wait'
    Write-Host ""
    Write-Host "  Nada foi alterado." -ForegroundColor Green
    exit 1
}
Write-Host "  Nao aparece em Programas e Recursos — pode trancar." -ForegroundColor Green

Titulo "2/3  Trancando as pastas"

foreach ($p in $PASTAS) {
    if (Test-Path $p) {
        $dentro = @(Get-ChildItem $p -Force -ErrorAction SilentlyContinue)
        if ($dentro.Count -gt 0) {
            Write-Host "  PULEI (tem $($dentro.Count) arquivo(s) dentro): $p" -ForegroundColor Yellow
            Write-Host "     esvazie na mao e rode de novo, pra eu nao apagar nada sem voce ver." -ForegroundColor DarkGray
            continue
        }
    } else {
        New-Item -ItemType Directory -Path $p -Force | Out-Null
    }
    # (OI)(CI) = vale pros arquivos e pastas que tentarem nascer dentro.
    # W = escrever, DE = apagar. Negacao ganha de permissao, inclusive
    # pra administrador — e e isso que faz o instalador falhar.
    icacls $p /deny "${TODOS}:(OI)(CI)(W,DE)" | Out-Null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  trancada: $p" -ForegroundColor Green
    } else {
        Write-Host "  NAO consegui trancar: $p" -ForegroundColor Red
    }
}

Titulo "3/3  Conferindo que a tranca pega"

$teste = Join-Path "${env:ProgramFiles(x86)}\AnyDesk" "teste_da_tranca.txt"
try {
    Set-Content -Path $teste -Value "x" -ErrorAction Stop
    Remove-Item $teste -Force -ErrorAction SilentlyContinue
    Write-Host "  ATENCAO: consegui escrever dentro da pasta — a tranca NAO pegou." -ForegroundColor Red
} catch {
    Write-Host "  Tentei criar um arquivo ali e o Windows recusou. A tranca pegou." -ForegroundColor Green
}

Write-Host ""
Write-Host "  Pronto. Instalador do AnyDesk vai falhar nessas pastas." -ForegroundColor Green
Write-Host "  Isto NAO impede a versao portatil (que roda sem instalar) nem tira" -ForegroundColor DarkGray
Write-Host "  propaganda de um AnyDesk instalado noutro lugar." -ForegroundColor DarkGray
Write-Host "  Pra desfazer: rode este mesmo arquivo com -Desfazer." -ForegroundColor Green
