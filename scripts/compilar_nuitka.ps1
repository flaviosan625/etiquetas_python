[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [string]$EntryPoint = "main.py",

    [Parameter(Mandatory = $false)]
    [string]$OutputDir = "dist",

    [Parameter(Mandatory = $false)]
    [string]$CompanyName = "Comunicação Visual",

    [Parameter(Mandatory = $false)]
    [string]$ProductName = "AutoPrint Automation",

    [Parameter(Mandatory = $false)]
    [string]$FileVersion = "2.0.0",

    [Parameter(Mandatory = $false)]
    [string]$ProductVersion = "2.0.0",

    [Parameter(Mandatory = $false)]
    [string]$IconPath = "assets/icone.ico",

    [Parameter(Mandatory = $false)]
    [string]$DataDir = "assets=assets",

    [Parameter(Mandatory = $false)]
    [string]$Plugin = "pyside6",

    [Parameter(Mandatory = $false)]
    [bool]$DisableConsole = $true,

    [Parameter(Mandatory = $false)]
    [bool]$Standalone = $true,

    [Parameter(Mandatory = $false)]
    [switch]$Clean,

    [Parameter(Mandatory = $false)]
    [switch]$DryRun,

    [Parameter(Mandatory = $false)]
    [string[]]$ExtraFlags = @()
)

<#
.SYNOPSIS
    Script profissional de compilação nativa em C++ via Nuitka.
    AutoPrint Automation - Comunicação Visual (ISSUE-15).

.DESCRIPTION
    Realiza a compilação standalone nativa gerando código C++ otimizado,
    incorporando plugins Qt/PySide6, metadados corporativos da aplicação,
    ícone executável e diretórios de assets.
#>

$ErrorActionPreference = "Stop"

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host " AutoPrint Automation - Compilador Nativo C++ (Nuitka)   " -ForegroundColor Cyan
Write-Host " Versão do Produto: $ProductVersion                       " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# ---------------------------------------------------------------------
# 1. Localização e Validação do Ambiente Python
# ---------------------------------------------------------------------
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir

Set-Location -Path $ProjectRoot

$PythonExe = $null
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (Test-Path $VenvPython) {
    $PythonExe = $VenvPython
    Write-Host "[OK] Ambiente virtual Python detectado: $PythonExe" -ForegroundColor Green
} else {
    $SysPython = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($SysPython) {
        $PythonExe = $SysPython.Source
        Write-Host "[AVISO] Usando Python do sistema: $PythonExe" -ForegroundColor Yellow
    } else {
        Write-Error "Python não foi encontrado nem em .venv nem no PATH do sistema."
        exit 1
    }
}

# ---------------------------------------------------------------------
# 2. Verificação de Compilador C++ / MSVC
# ---------------------------------------------------------------------
Write-Host "`n--> Verificando compilador C++ / MSVC..." -ForegroundColor Cyan
$CompilerFound = $false
$CompilerDetails = ""

# Checa cl.exe (MSVC)
$ClCmd = Get-Command cl.exe -ErrorAction SilentlyContinue
if ($ClCmd) {
    $CompilerFound = $true
    $CompilerDetails = "MSVC (cl.exe detectado no PATH: $($ClCmd.Source))"
} else {
    # Procura via vswhere no diretório padrão do Visual Studio
    $VsWhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
    if (Test-Path $VsWhere) {
        $VsPath = & $VsWhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
        if ($VsPath) {
            $CompilerFound = $true
            $CompilerDetails = "MSVC Visual Studio instalado em: $VsPath"
        }
    }
}

# Fallback: GCC / Clang / MinGW64
if (-not $CompilerFound) {
    $GccCmd = Get-Command gcc.exe -ErrorAction SilentlyContinue
    if ($GccCmd) {
        $CompilerFound = $true
        $CompilerDetails = "GCC / MinGW detectado no PATH: $($GccCmd.Source)"
    }
}

if ($CompilerFound) {
    Write-Host "[OK] Compilador C++ detectado: $CompilerDetails" -ForegroundColor Green
} else {
    Write-Host "[AVISO] Compilador C++ (MSVC / cl.exe) não localizado no PATH imediato." -ForegroundColor Yellow
    Write-Host "        O Nuitka tentará detectar o Visual Studio instalado ou solicitará" -ForegroundColor Yellow
    Write-Host "        o download automático do MinGW64 oficial durante a primeira execução." -ForegroundColor Yellow
}

# ---------------------------------------------------------------------
# 3. Verificação do Nuitka no Ambiente
# ---------------------------------------------------------------------
Write-Host "`n--> Verificando instalação do Nuitka..." -ForegroundColor Cyan
$NuitkaInstalled = $false

try {
    $NuitkaCheck = & $PythonExe -c "import nuitka; print(nuitka.__version__)" 2>$null
    if ($LASTEXITCODE -eq 0 -and -not [string]::IsNullOrWhiteSpace($NuitkaCheck)) {
        $NuitkaInstalled = $true
        Write-Host "[OK] Nuitka instalado (versão: $NuitkaCheck)" -ForegroundColor Green
    }
} catch {
    $NuitkaInstalled = $false
}

if (-not $NuitkaInstalled) {
    Write-Host "[AVISO] Nuitka não encontrado no ambiente Python atual ($PythonExe)." -ForegroundColor Yellow
    Write-Host "        Para instalar o Nuitka e dependências de compilação:" -ForegroundColor Yellow
    Write-Host "        $PythonExe -m pip install nuitka zstandard ordered-set" -ForegroundColor Yellow
    if (-not $DryRun) {
        Write-Error "Nuitka é obrigatório para compilar. Execute o comando de instalação acima."
        exit 1
    }
}

# ---------------------------------------------------------------------
# 4. Validação de Arquivos de Entrada e Assets
# ---------------------------------------------------------------------
$FullEntryPoint = Join-Path $ProjectRoot $EntryPoint
if (-not (Test-Path $FullEntryPoint)) {
    Write-Error "Ponto de entrada não encontrado: $FullEntryPoint"
    exit 1
}

$FullIconPath = Join-Path $ProjectRoot $IconPath
if (-not (Test-Path $FullIconPath)) {
    $FallbackIcon = Join-Path $ProjectRoot "assets\uny_cv.ico"
    if (Test-Path $FallbackIcon) {
        Write-Host "[INFO] Usando ícone de fallback: $FallbackIcon" -ForegroundColor Yellow
        $FullIconPath = $FallbackIcon
        $IconPath = "assets/uny_cv.ico"
    } else {
        Write-Host "[AVISO] Ícone não localizado em $FullIconPath. Prosseguindo sem ícone nativo." -ForegroundColor Yellow
        $FullIconPath = $null
    }
}

# ---------------------------------------------------------------------
# 5. Limpeza Prévia (quando solicitada)
# ---------------------------------------------------------------------
$FullOutputDir = Join-Path $ProjectRoot $OutputDir
if ($Clean) {
    Write-Host "`n--> Limpando diretórios de compilação anteriores..." -ForegroundColor Cyan
    $BuildDir = Join-Path $ProjectRoot "build"
    if (Test-Path $BuildDir) {
        Remove-Item -Path $BuildDir -Recurse -Force -ErrorAction SilentlyContinue
        Write-Host "[OK] Diretório build/ removido." -ForegroundColor Green
    }
    if (Test-Path $FullOutputDir) {
        Remove-Item -Path $FullOutputDir -Recurse -Force -ErrorAction SilentlyContinue
        Write-Host "[OK] Diretório $OutputDir/ removido." -ForegroundColor Green
    }
}

# ---------------------------------------------------------------------
# 6. Montagem dos Argumentos do Nuitka
# ---------------------------------------------------------------------
$NuitkaArgs = @(
    "-m", "nuitka"
)

if ($Standalone) {
    $NuitkaArgs += "--standalone"
}

if ($DisableConsole) {
    $NuitkaArgs += "--windows-disable-console"
}

if (-not [string]::IsNullOrWhiteSpace($Plugin)) {
    $NuitkaArgs += "--enable-plugin=$Plugin"
}

$NuitkaArgs += "--output-dir=$OutputDir"

if ($FullIconPath -and (Test-Path $FullIconPath)) {
    $NuitkaArgs += "--windows-icon-from-ico=$IconPath"
}

$NuitkaArgs += "--include-data-dir=$DataDir"

# Inclusão de schemas SQL do banco se existirem
$SqlSchema = Join-Path $ProjectRoot "banco\esquema.sql"
if (Test-Path $SqlSchema) {
    $NuitkaArgs += "--include-data-file=banco/esquema.sql=banco/esquema.sql"
}

# Metadados de versão e identificação empresarial do Windows
$NuitkaArgs += "--windows-company-name=""$CompanyName"""
$NuitkaArgs += "--windows-product-name=""$ProductName"""
$NuitkaArgs += "--windows-file-version=""$FileVersion"""
$NuitkaArgs += "--windows-product-version=""$ProductVersion"""

# Argumentos extras fornecidos pelo usuário
if ($ExtraFlags -and $ExtraFlags.Count -gt 0) {
    $NuitkaArgs += $ExtraFlags
}

# Arquivo de entrada principal
$NuitkaArgs += $EntryPoint

# ---------------------------------------------------------------------
# 7. Execução ou DryRun
# ---------------------------------------------------------------------
Write-Host "`n--> Comando de compilação montado:" -ForegroundColor Cyan
Write-Host "$PythonExe $($NuitkaArgs -join ' ')" -ForegroundColor White

if ($DryRun) {
    Write-Host "`n[DRY RUN] Validação do ambiente concluída com sucesso. Compilação não disparada." -ForegroundColor Green
    exit 0
}

Write-Host "`n--> Iniciando compilação nativa em C++ (isso pode levar alguns minutos)..." -ForegroundColor Cyan
$Stopwatch = [System.Diagnostics.Stopwatch]::StartNew()

& $PythonExe @NuitkaArgs

$Stopwatch.Stop()
$ElapsedTime = $Stopwatch.Elapsed

if ($LASTEXITCODE -eq 0) {
    Write-Host "`n==========================================================" -ForegroundColor Green
    Write-Host " Compilação Concluída com Sucesso!" -ForegroundColor Green
    Write-Host " Tempo decorrido: $($ElapsedTime.ToString('hh\:mm\:ss'))" -ForegroundColor Green
    Write-Host " Saída gerada em: $FullOutputDir" -ForegroundColor Green
    Write-Host "==========================================================" -ForegroundColor Green
    exit 0
} else {
    Write-Host "`n==========================================================" -ForegroundColor Red
    Write-Host " Falha na compilação do Nuitka (Exit Code: $LASTEXITCODE)" -ForegroundColor Red
    Write-Host "==========================================================" -ForegroundColor Red
    exit $LASTEXITCODE
}
