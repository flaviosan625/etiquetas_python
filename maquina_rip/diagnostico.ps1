# SÓ OLHA. Não muda nada, não cria nada, não apaga nada.
#
# Serve pra responder três perguntas que daqui da máquina principal são
# invisíveis:
#   1. a tarefa do Agendador é a nova, e está disparando?
#   2. o arquivo mandado pela fila chegou nesta máquina pelo OneDrive?
#   3. o vigia rodou e falou alguma coisa no log?

$ErrorActionPreference = "Continue"

$NOME_TAREFA = "RasterLink Hotfolder"
$PASTA       = "C:\RasterLink"
$SCRIPT      = Join-Path $PASTA "rasterlink_hotfolder.py"
$LOG         = Join-Path $PASTA "rasterlink_hotfolder.log"
$FILA        = "$env:USERPROFILE\OneDrive\UNYCOMUNICACAO\Fila de Impressao RasterLink"

function Titulo($texto) {
    Write-Host ""
    Write-Host ("=" * 72) -ForegroundColor DarkGray
    Write-Host "  $texto" -ForegroundColor Cyan
    Write-Host ("=" * 72) -ForegroundColor DarkGray
}

Write-Host ""
Write-Host "  Maquina: $env:COMPUTERNAME    Usuario: $env:USERNAME    Agora: $(Get-Date -Format 'dd/MM HH:mm:ss')"

# --------------------------------------------------------------------
Titulo "1  A TAREFA DO AGENDADOR"

$tarefa = Get-ScheduledTask -TaskName $NOME_TAREFA -ErrorAction SilentlyContinue
if ($null -eq $tarefa) {
    Write-Host "  NAO EXISTE tarefa com o nome '$NOME_TAREFA'." -ForegroundColor Red
    Write-Host "  >>> O instalador nao chegou a criar a tarefa." -ForegroundColor Red
} else {
    $info = Get-ScheduledTaskInfo -TaskName $NOME_TAREFA
    Write-Host "  Estado..............: $($tarefa.State)"
    Write-Host "  Configurada para....: $($tarefa.Settings.Compatibility)   <<< 'Vista' = tarefa ANTIGA; 'Win8' = a nova"
    Write-Host "  Ultima execucao.....: $($info.LastRunTime)"
    Write-Host "  Resultado da ultima.: $($info.LastTaskResult)   (0 = deu certo)"
    Write-Host "  Proxima execucao....: $($info.NextRunTime)"
    Write-Host "  Limite por execucao.: $($tarefa.Settings.ExecutionTimeLimit)"
    Write-Host ""
    Write-Host "  Gatilhos:"
    foreach ($g in $tarefa.Triggers) {
        $rep = "SEM REPETICAO  <<< se for este o caso, ela so dispara uma vez e nunca mais"
        if ($g.Repetition -and $g.Repetition.Interval) {
            $rep = "repete a cada $($g.Repetition.Interval), duracao '$($g.Repetition.Duration)'"
        }
        Write-Host "    - $($g.CimClass.CimClassName): $rep"
    }
    Write-Host ""
    Write-Host "  O que ela manda executar:"
    foreach ($a in $tarefa.Actions) {
        Write-Host "    $($a.Execute)"
        Write-Host "    $($a.Arguments)"
        Write-Host "    (pasta de trabalho: $($a.WorkingDirectory))"
    }
    Write-Host ""
    Write-Host "  >>> Tem que aparecer '--uma-vez' ou 'principal_uma_vez()' na linha acima." -ForegroundColor Yellow
}

# --------------------------------------------------------------------
Titulo "2  TEM ALGUM VIGIA RODANDO AGORA?"

$vigias = Get-CimInstance Win32_Process -Filter "Name = 'python.exe' OR Name = 'pythonw.exe'" -ErrorAction SilentlyContinue |
          Where-Object { $_.CommandLine -like "*rasterlink_hotfolder*" }
if ($null -eq $vigias -or @($vigias).Count -eq 0) {
    Write-Host "  Nenhum. (Normal no modo novo: ele nasce, trabalha 2s e morre.)"
} else {
    foreach ($v in @($vigias)) {
        Write-Host "  PID $($v.ProcessId) desde $($v.CreationDate): $($v.CommandLine)" -ForegroundColor Yellow
    }
    Write-Host "  >>> Se for o loop antigo, ele segura a trava e impede o modo novo de trabalhar." -ForegroundColor Yellow
}

# --------------------------------------------------------------------
Titulo "3  O SCRIPT QUE ESTA INSTALADO"

if (Test-Path $SCRIPT) {
    $i = Get-Item $SCRIPT
    Write-Host "  $SCRIPT"
    Write-Host "  $($i.Length) bytes, de $($i.LastWriteTime)"
    $temUmaVez = Select-String -Path $SCRIPT -Pattern "principal_uma_vez" -Quiet
    if ($temUmaVez) {
        Write-Host "  Versao NOVA (tem principal_uma_vez)." -ForegroundColor Green
    } else {
        Write-Host "  Versao VELHA (nao tem principal_uma_vez) — o instalador nao copiou." -ForegroundColor Red
    }
} else {
    Write-Host "  NAO EXISTE $SCRIPT" -ForegroundColor Red
}

# --------------------------------------------------------------------
Titulo "4  O ONEDRIVE ESTA ENTREGANDO OS ARQUIVOS NESTA MAQUINA?"

# Esta e a outra metade da duvida: se o arquivo nem chegou aqui, a
# tarefa pode estar perfeita e a fila continuaria parada do mesmo jeito.
if (-not (Test-Path $FILA)) {
    Write-Host "  NAO EXISTE a pasta da fila nesta maquina: $FILA" -ForegroundColor Red
} else {
    foreach ($sub in @("SWJ320A", "UJV 100 UNY CV")) {
        $p = Join-Path $FILA $sub
        if (-not (Test-Path $p)) { Write-Host "  $sub -> pasta nao existe aqui" -ForegroundColor Red; continue }
        $arqs = @(Get-ChildItem $p -File -ErrorAction SilentlyContinue)
        Write-Host "  $sub -> $($arqs.Count) arquivo(s) esperando"
        foreach ($a in $arqs) { Write-Host "      $($a.Name)" }
        $probe = Join-Path $p "Enviados\_sinal_de_vida_do_vigia_pode_apagar.txt"
        if (Test-Path $probe) { Write-Host "      (o .txt de sinal de vida chegou aqui)" -ForegroundColor DarkGray }
    }
}

$od = Get-Process OneDrive -ErrorAction SilentlyContinue
if ($od) { Write-Host "  OneDrive.exe rodando (PID $($od.Id))" } else { Write-Host "  OneDrive.exe NAO esta rodando!" -ForegroundColor Red }

# --------------------------------------------------------------------
Titulo "5  AS HOT FOLDERS DO RASTERLINK EXISTEM?"

foreach ($h in @("C:\MijCtrl\Hot\UJV 100 UNY CV", "C:\MijCtrl\Hot\SWJ320A")) {
    if (Test-Path $h) {
        $n = @(Get-ChildItem $h -File -ErrorAction SilentlyContinue).Count
        Write-Host "  OK  $h  ($n arquivo(s) dentro)" -ForegroundColor Green
    } else {
        Write-Host "  FALTA  $h" -ForegroundColor Red
    }
}

# --------------------------------------------------------------------
Titulo "6  O QUE O VIGIA ESCREVEU NO LOG"

if (Test-Path $LOG) {
    $i = Get-Item $LOG
    Write-Host "  $LOG (mexido pela ultima vez em $($i.LastWriteTime))"
    Write-Host ""
    Get-Content $LOG -Encoding UTF8 -Tail 25 | ForEach-Object { Write-Host "    $_" }
} else {
    Write-Host "  NAO EXISTE $LOG — o vigia nunca conseguiu nem escrever uma linha." -ForegroundColor Red
}

$crash = Join-Path $PASTA "rasterlink_hotfolder_crash.log"
if (Test-Path $crash) {
    Write-Host ""
    Write-Host "  ARQUIVO DE CRASH (fim dele):" -ForegroundColor Yellow
    Get-Content $crash -Encoding UTF8 -Tail 20 | ForEach-Object { Write-Host "    $_" -ForegroundColor Yellow }
}

# --------------------------------------------------------------------
Titulo "7  O HISTORICO DA TAREFA (o que o Windows achou dela)"

try {
    $eventos = Get-WinEvent -FilterHashtable @{
        LogName = 'Microsoft-Windows-TaskScheduler/Operational'
        StartTime = (Get-Date).AddHours(-3)
    } -ErrorAction Stop | Where-Object { $_.Message -like "*$NOME_TAREFA*" } | Select-Object -First 20

    if ($eventos) {
        foreach ($e in $eventos) {
            Write-Host ("  {0:HH:mm:ss}  id {1}  {2}" -f $e.TimeCreated, $e.Id, ($e.Message -split "`n")[0])
        }
    } else {
        Write-Host "  Nenhum evento nas ultimas 3 horas." -ForegroundColor Yellow
        Write-Host "  >>> Ou o historico do Agendador esta DESLIGADO, ou a tarefa nao disparou nenhuma vez." -ForegroundColor Yellow
    }
} catch {
    Write-Host "  Nao consegui ler o historico: $($_.Exception.Message)" -ForegroundColor Yellow
    Write-Host "  >>> Provavelmente o historico do Agendador esta desligado (Acoes > Habilitar Historico)." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "  ---- fim ----" -ForegroundColor DarkGray
