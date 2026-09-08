# Instala a tarefa do Agendador que alimenta a DOCAN nesta máquina — a
# PRINCIPAL, onde roda o SAi Production Manager. Rode pelo
# instalar_tarefa.bat, ao lado deste arquivo.
#
# Por que existe uma tarefa SEPARADA da do RIP: as hot folders não estão
# no mesmo PC. As duas Mimaki são atendidas pelo RasterLink7 lá na
# máquina do RIP; a DOCAN é atendida pelo SAi, aqui. Cada vigia cuida do
# seu posto (--posto rip / --posto sai) e ignora em silêncio a pasta da
# máquina do outro. Sem isso, o vigia de lá procuraria a hot folder da
# DOCAN do lado errado e reclamaria dela de minuto em minuto, enquanto o
# arquivo mandado pra DOCAN ficaria encalhado esperando quem nunca vem.
#
# Diferenças em relação ao instalador da máquina do RIP:
#   - Aqui o script mora no próprio repositório (não é copiado do
#     OneDrive), e o Python é o do .venv do projeto.
#   - A trava, o log e o estado de avisos são POR POSTO, então os dois
#     vigias nunca se atrapalham nem se as duas tarefas rodarem no mesmo
#     PC um dia.
#
# O resto segue igual, e pelos mesmos motivos: passada de minuto em
# minuto que nasce, trabalha e morre (processo eterno já morreu calado
# três vezes, 2026-09-05), tarefa criada por XML e nunca clicando
# caixinha, Repetition sem <Duration> pra repetir pra sempre.

$ErrorActionPreference = "Stop"

$NOME_TAREFA = "Vigia DOCAN (SAi)"
$PASTA       = Split-Path -Parent $PSScriptRoot
$SCRIPT      = Join-Path $PASTA "rasterlink_hotfolder.py"
$PYTHONW     = Join-Path $PASTA ".venv\Scripts\pythonw.exe"
$PYTHON      = Join-Path $PASTA ".venv\Scripts\python.exe"
$LOG         = Join-Path $PASTA "rasterlink_hotfolder.log"
$POSTO       = "sai"

function Titulo($texto) {
    Write-Host ""
    Write-Host ("=" * 70) -ForegroundColor DarkGray
    Write-Host "  $texto" -ForegroundColor Cyan
    Write-Host ("=" * 70) -ForegroundColor DarkGray
}

function TraduzirResultado($codigo) {
    switch ([int64]$codigo) {
        0          { return "0 - deu certo" }
        1          { return "1 - o programa saiu com erro" }
        267008     { return "0x41300 - tarefa pronta, nunca rodou" }
        267009     { return "0x41301 - rodando agora" }
        267011     { return "0x41303 - nunca rodou ainda" }
        267014     { return "0x41306 - a tarefa foi ENCERRADA por alguém/algo" }
        2147942402 { return "0x80070002 - arquivo não encontrado (caminho errado na ação)" }
        2147942405 { return "0x80070005 - acesso negado" }
        3221225786 { return "0xC000013A - o processo foi MORTO (Ctrl+C, janela fechada ou logoff)" }
        default    { return "$codigo" }
    }
}

# ---------------------------------------------------------------- 1/6
Titulo "1/6  Conferindo o terreno antes de mexer em qualquer coisa"

# Conferido ANTES de tudo, e não lá na hora de registrar: nesta máquina
# o Register-ScheduledTask devolve "Acesso negado" (0x80070005) sem
# elevação — comprovado em 2026-09-07. Descobrir isso no fim faria o
# instalador rodar cinco passos pra morrer no sexto.
$souAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
            ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $souAdmin) {
    Write-Host ""
    Write-Host "  PAREI ANTES DE MEXER EM QUALQUER COISA." -ForegroundColor Red
    Write-Host ""
    Write-Host "  Criar tarefa no Agendador precisa de administrador nesta máquina." -ForegroundColor Yellow
    Write-Host "  Feche esta janela, clique com o BOTÃO DIREITO no instalar_tarefa.bat" -ForegroundColor Yellow
    Write-Host "  e escolha 'Executar como administrador'." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "  Nada foi alterado." -ForegroundColor Green
    exit 1
}

$problemas = @()
if (-not (Test-Path $SCRIPT))  { $problemas += "Não existe $SCRIPT." }
if (-not (Test-Path $PYTHONW)) { $problemas += "Não existe $PYTHONW (o .venv do projeto)." }

# A hot folder da DOCAN é o Setup do SAi, lido do PMSetups.ini dele.
# Confere ANTES: sem ela, toda passada vira erro alto e a tarefa fica
# gritando no log de minuto em minuto.
$hotFolder = & $PYTHON -c "import rasterlink_hotfolder as r; print(r._config_maquina(r.MAQUINAS['DOCAN'])[0])" 2>$null
if ([string]::IsNullOrWhiteSpace($hotFolder)) {
    $problemas += "Não consegui ler a hot folder da DOCAN do rasterlink_hotfolder.py."
} elseif (-not (Test-Path $hotFolder)) {
    $problemas += "A hot folder da DOCAN não existe: $hotFolder"
}

if ($problemas.Count -gt 0) {
    Write-Host ""
    Write-Host "  PAREI ANTES DE MEXER EM QUALQUER COISA." -ForegroundColor Red
    foreach ($p in $problemas) { Write-Host "    - $p" -ForegroundColor Yellow }
    Write-Host ""
    Write-Host "  Nada foi alterado." -ForegroundColor Green
    exit 1
}

Write-Host "  Script......: $SCRIPT" -ForegroundColor Green
Write-Host "  Python......: $PYTHONW" -ForegroundColor Green
Write-Host "  Hot folder..: $hotFolder" -ForegroundColor Green

# Este script NÃO pode morar em pasta sincronizada: a trava e o log ficam
# ao lado dele, e num caminho sincronizado a tarefa e uma execução na mão
# travariam em arquivos DIFERENTES — as duas se achando sozinhas, pegando
# o mesmo arquivo, e o RIP criando job duplicado.
if ($PASTA -match "OneDrive") {
    Write-Host ""
    Write-Host "  PAREI: o projeto está dentro do OneDrive ($PASTA)." -ForegroundColor Red
    Write-Host "  Mova pra uma pasta local antes de agendar." -ForegroundColor Red
    exit 1
}
Write-Host "  Fora do OneDrive: ok" -ForegroundColor Green

# ---------------------------------------------------------------- 2/6
Titulo "2/6  Como a tarefa está HOJE"

$tarefaAntiga = Get-ScheduledTask -TaskName $NOME_TAREFA -ErrorAction SilentlyContinue
if ($null -eq $tarefaAntiga) {
    Write-Host "  Não existe tarefa com esse nome ainda — instalação nova." -ForegroundColor Yellow
} else {
    $infoAntiga = Get-ScheduledTaskInfo -TaskName $NOME_TAREFA
    Write-Host "  Estado...............: $($tarefaAntiga.State)"
    Write-Host "  Última execução......: $($infoAntiga.LastRunTime)"
    Write-Host "  Resultado da última..: $(TraduzirResultado $infoAntiga.LastTaskResult)"

    $backup = Join-Path $PSScriptRoot ("tarefa_antiga_{0:yyyyMMdd_HHmmss}.xml" -f (Get-Date))
    Export-ScheduledTask -TaskName $NOME_TAREFA | Out-File $backup -Encoding utf8
    Write-Host ""
    Write-Host "  Cópia da tarefa antiga guardada em: $backup" -ForegroundColor DarkGray
}

# ---------------------------------------------------------------- 3/6
Titulo "3/6  Testando se este pythonw consegue iniciar o script"

# Não é paranoia: na máquina do RIP o pythonw.exe NÃO inicia script por
# caminho de arquivo e falha em silêncio absoluto — nem chega na linha 1.
# O --autoteste escreve no log, então "funcionou" aqui é fato, não fé.
$antes = 0
if (Test-Path $LOG) { $antes = (Get-Item $LOG).Length }

$p = Start-Process -FilePath $PYTHONW `
                   -ArgumentList @("-m", "rasterlink_hotfolder", "--autoteste") `
                   -WorkingDirectory $PASTA -PassThru -Wait -WindowStyle Hidden

$depois = 0
if (Test-Path $LOG) { $depois = (Get-Item $LOG).Length }

if ($depois -le $antes) {
    Write-Host "  PAREI: o pythonw não conseguiu iniciar o script (saída $($p.ExitCode), nada no log)." -ForegroundColor Red
    Write-Host "  Nada foi alterado." -ForegroundColor Green
    exit 1
}
Write-Host "  -m (módulo): FUNCIONA (escreveu no log)" -ForegroundColor Green

$ARGUMENTOS = "-m rasterlink_hotfolder --uma-vez --posto $POSTO"
Write-Host "  Vou agendar assim: $ARGUMENTOS" -ForegroundColor Green

# ---------------------------------------------------------------- 4/6
Titulo "4/6  Criando a tarefa"

$USUARIO = $env:USERNAME
try {
    $daSessao = (Get-CimInstance Win32_ComputerSystem -ErrorAction Stop).UserName
    if ($daSessao) { $USUARIO = $daSessao }
} catch { }

$argXml = [System.Security.SecurityElement]::Escape($ARGUMENTOS)

# As escolhas aqui são as mesmas da tarefa do RIP, pelos mesmos motivos:
#   - DOIS gatilhos (logon e horário): um reinício estranho ou um logon
#     que não disparou não deixam a fila parada.
#   - Repetition SEM <Duration>: repete pra sempre. Com duração ela
#     acaba, e foi assim que o conserto anterior morreu calado.
#   - ExecutionTimeLimit PT30M: uma passada travada é morta em vez de
#     bloquear todas as próximas pelo IgnoreNew. Meia hora porque cópia
#     legítima pode demorar — o arquivo é montado FORA da hot folder e
#     entra por rename atômico, então ser morto no meio não estraga nada.
#   - IgnoreNew + a trava do próprio script: duas passadas juntas
#     pegariam o MESMO arquivo e o RIP criaria job duplicado.
#   - InteractiveToken: o SAi e o OneDrive precisam da sessão do usuário
#     de qualquer jeito, então rodar "conectado ou não" não faria sentido.
$xml = @"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>Manda pra hot folder do SAi (DOCAN) o que chegar na fila do OneDrive. Uma passada por minuto. Posto: $POSTO.</Description>
    <URI>\$NOME_TAREFA</URI>
  </RegistrationInfo>
  <Triggers>
    <LogonTrigger>
      <Enabled>true</Enabled>
      <Repetition>
        <Interval>PT1M</Interval>
        <StopAtDurationEnd>false</StopAtDurationEnd>
      </Repetition>
    </LogonTrigger>
    <TimeTrigger>
      <StartBoundary>2026-01-01T00:00:00</StartBoundary>
      <Enabled>true</Enabled>
      <Repetition>
        <Interval>PT1M</Interval>
        <StopAtDurationEnd>false</StopAtDurationEnd>
      </Repetition>
    </TimeTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <UserId>$USUARIO</UserId>
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <IdleSettings>
      <StopOnIdleEnd>false</StopOnIdleEnd>
      <RestartOnIdle>false</RestartOnIdle>
    </IdleSettings>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <UseUnifiedSchedulingEngine>true</UseUnifiedSchedulingEngine>
    <WakeToRun>false</WakeToRun>
    <ExecutionTimeLimit>PT30M</ExecutionTimeLimit>
    <Priority>7</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>$PYTHONW</Command>
      <Arguments>$argXml</Arguments>
      <WorkingDirectory>$PASTA</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"@

try {
    Register-ScheduledTask -TaskName $NOME_TAREFA -Xml $xml -Force | Out-Null
} catch {
    Write-Host "  PAREI ao criar a tarefa: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "  Se for acesso negado: feche, clique com o botão direito no" -ForegroundColor Red
    Write-Host "  instalar_tarefa.bat e escolha 'Executar como administrador'." -ForegroundColor Red
    exit 1
}
Write-Host "  Tarefa '$NOME_TAREFA' criada." -ForegroundColor Green

# ---------------------------------------------------------------- 5/6
Titulo "5/6  Atalho pra rodar uma passada na mão e VER acontecendo"

$atalho = Join-Path $PSScriptRoot "rodar_uma_vez.bat"
@"
@echo off
REM Uma passada na fila da DOCAN, com a saida na tela. E exatamente o
REM que a tarefa agendada faz de minuto em minuto.
chcp 65001 >nul
cd /d "$PASTA"
"$PYTHON" -m rasterlink_hotfolder --uma-vez --posto $POSTO
echo.
pause
"@ | Out-File $atalho -Encoding ascii
Write-Host "  $atalho" -ForegroundColor Green

# ---------------------------------------------------------------- 6/6
Titulo "6/6  Conferindo que ela roda de verdade"

Start-ScheduledTask -TaskName $NOME_TAREFA
Start-Sleep -Seconds 8

$tarefa = Get-ScheduledTask -TaskName $NOME_TAREFA
$info   = Get-ScheduledTaskInfo -TaskName $NOME_TAREFA
Write-Host "  Estado...............: $($tarefa.State)"
Write-Host "  Última execução......: $($info.LastRunTime)"
Write-Host "  Resultado da última..: $(TraduzirResultado $info.LastTaskResult)"
Write-Host "  Próxima execução.....: $($info.NextRunTime)"
foreach ($g in $tarefa.Triggers) {
    Write-Host "  Gatilho..............: $($g.CimClass.CimClassName) repetindo a cada $($g.Repetition.Interval)"
}

if (Test-Path $LOG) {
    Write-Host ""
    Write-Host "  Fim do log ($LOG):" -ForegroundColor DarkGray
    Get-Content $LOG -Encoding UTF8 -Tail 10 | ForEach-Object { Write-Host "    $_" -ForegroundColor DarkGray }
}

Write-Host ""
Write-Host "  Pronto. Daqui pra frente ela dispara sozinha de minuto em minuto." -ForegroundColor Green
Write-Host "  Pra desfazer TUDO isto: desinstalar_tarefa.bat, nesta mesma pasta." -ForegroundColor Green
