# Instala (ou conserta) a tarefa do Agendador que alimenta o RasterLink7
# na máquina do RIP. Roda pelo instalar_tarefa.bat, ao lado deste arquivo.
#
# O QUE MUDA em relação ao jeito antigo:
#
#   Antes a tarefa acendia UM processo eterno (o loop do vigiar_fila) e
#   torcia pra ele continuar vivo. Ele morreu três vezes sem deixar
#   rastro (2026-09-05) e a fila ficou parada até alguém abrir o
#   Agendador e clicar em "Executar" na mão.
#
#   Agora a tarefa dispara de MINUTO EM MINUTO uma passada que trabalha
#   uns dois segundos e morre. Não existe mais "processo que morreu sem
#   ninguém ver": se parar, a coluna "Última execução" do Agendador
#   envelhece na cara de quem olha. E o pior estrago possível passa a
#   ser um minuto de atraso, não o dia inteiro.
#
# A tarefa é criada por XML, nunca clicando caixinha na tela: era numa
# caixinha dessas ("repetir a cada 5 minutos") que o conserto anterior
# se perdia sem avisar.

$ErrorActionPreference = "Stop"

$NOME_TAREFA = "RasterLink Hotfolder"
$PASTA       = "C:\RasterLink"
$SCRIPT      = Join-Path $PASTA "rasterlink_hotfolder.py"
$LOG         = Join-Path $PASTA "rasterlink_hotfolder.log"

function Titulo($texto) {
    Write-Host ""
    Write-Host ("=" * 70) -ForegroundColor DarkGray
    Write-Host "  $texto" -ForegroundColor Cyan
    Write-Host ("=" * 70) -ForegroundColor DarkGray
}

# ---------------------------------------------------------------- 1/7
Titulo "1/7  Trazendo a versão nova do script"

$origem = Get-ChildItem "$env:USERPROFILE\OneDrive\UNYCOMUNICACAO" -Directory -ErrorAction SilentlyContinue |
          Where-Object { $_.Name -like "IMPRESS*UJV*" } |
          Select-Object -First 1
# procurado por curinga de propósito: o nome da pasta tem "Ã" e caminho
# acentuado dentro de .bat depende da página de código do console

if ($null -eq $origem) {
    Write-Host "  Não achei a pasta de deploy no OneDrive. Copie o rasterlink_hotfolder.py na mão pra $PASTA." -ForegroundColor Yellow
} else {
    $arquivoNovo = Join-Path $origem.FullName "rasterlink_hotfolder.py"
    if (Test-Path $arquivoNovo) {
        if (-not (Test-Path $PASTA)) { New-Item -ItemType Directory -Path $PASTA | Out-Null }
        Copy-Item $arquivoNovo $SCRIPT -Force
        $info = Get-Item $SCRIPT
        Write-Host "  Copiado de: $($origem.FullName)"
        Write-Host "  Para:       $SCRIPT  ($($info.Length) bytes, de $($info.LastWriteTime))" -ForegroundColor Green
    } else {
        Write-Host "  A pasta existe mas não tem rasterlink_hotfolder.py dentro." -ForegroundColor Yellow
    }
}

if (-not (Test-Path $SCRIPT)) {
    Write-Host ""
    Write-Host "  PAREI: não existe $SCRIPT. Sem o script não tem o que agendar." -ForegroundColor Red
    exit 1
}

# ---------------------------------------------------------------- 2/7
Titulo "2/7  Como a tarefa está HOJE (antes de eu mexer)"

$tarefaAntiga = Get-ScheduledTask -TaskName $NOME_TAREFA -ErrorAction SilentlyContinue
if ($null -eq $tarefaAntiga) {
    Write-Host "  Não existe tarefa com esse nome ainda." -ForegroundColor Yellow
} else {
    $infoAntiga = Get-ScheduledTaskInfo -TaskName $NOME_TAREFA
    Write-Host "  Estado...............: $($tarefaAntiga.State)"
    Write-Host "  Última execução......: $($infoAntiga.LastRunTime)"
    Write-Host "  Resultado da última..: $($infoAntiga.LastTaskResult)"
    Write-Host "  Próxima execução.....: $($infoAntiga.NextRunTime)"
    Write-Host "  Gatilhos:"
    foreach ($g in $tarefaAntiga.Triggers) {
        $rep = "sem repetição"
        if ($g.Repetition -and $g.Repetition.Interval) {
            $rep = "repete a cada $($g.Repetition.Interval), duração '$($g.Repetition.Duration)'"
        }
        Write-Host "    - $($g.CimClass.CimClassName)  ->  $rep"
    }

    # guarda o XML antigo antes de sobrescrever: se por algum motivo o
    # jeito novo for pior, dá pra voltar com schtasks /create /xml
    $backup = Join-Path $PASTA ("tarefa_antiga_{0:yyyyMMdd_HHmmss}.xml" -f (Get-Date))
    Export-ScheduledTask -TaskName $NOME_TAREFA | Out-File $backup -Encoding utf8
    Write-Host ""
    Write-Host "  Cópia da tarefa antiga guardada em: $backup" -ForegroundColor DarkGray
}

Write-Host ""
Write-Host "  >>> Se 'repete a cada' aparecer vazio acima, ACHAMOS o motivo:" -ForegroundColor Yellow
Write-Host "      a tarefa só disparava no logon, e nunca mais." -ForegroundColor Yellow

# ---------------------------------------------------------------- 3/7
Titulo "3/7  Derrubando o vigia antigo, se ainda tiver algum de pé"

# ISTO AQUI NÃO É LIMPEZA, É PRÉ-REQUISITO. O modo antigo era um
# processo eterno que segura a trava de instância única enquanto viver.
# Se sobrar um de pé, TODA passada nova do modo novo vai achar que já
# tem outro vigia rodando e sair sem fazer nada — e a fila continuaria
# exatamente como está hoje, agora com a tarefa "certa" e ninguém
# entendendo por quê. Trocar a tarefa não mata quem já está rodando.
if ($null -ne $tarefaAntiga) {
    Stop-ScheduledTask -TaskName $NOME_TAREFA -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
}

$vigias = Get-CimInstance Win32_Process -Filter "Name = 'python.exe' OR Name = 'pythonw.exe'" -ErrorAction SilentlyContinue |
          Where-Object { $_.CommandLine -like "*rasterlink_hotfolder*" }

if ($null -eq $vigias -or @($vigias).Count -eq 0) {
    Write-Host "  Nenhum vigia rodando. Caminho livre." -ForegroundColor Green
} else {
    foreach ($v in @($vigias)) {
        Write-Host "  Derrubando PID $($v.ProcessId): $($v.CommandLine)" -ForegroundColor Yellow
        Stop-Process -Id $v.ProcessId -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Seconds 2
    $sobrou = Get-CimInstance Win32_Process -Filter "Name = 'python.exe' OR Name = 'pythonw.exe'" -ErrorAction SilentlyContinue |
              Where-Object { $_.CommandLine -like "*rasterlink_hotfolder*" }
    if ($sobrou) {
        Write-Host "  PAREI: ainda sobrou vigia rodando. Reinicie a máquina e rode isto de novo." -ForegroundColor Red
        exit 1
    }
    Write-Host "  Derrubado." -ForegroundColor Green
}

# ---------------------------------------------------------------- 4/7
Titulo "4/7  Achando o Python desta máquina"

$candidatos = @(
    "$env:LOCALAPPDATA\Python\pythoncore-3.14-64\pythonw.exe",
    "$env:LOCALAPPDATA\Python\pythoncore-3.13-64\pythonw.exe",
    "$env:LOCALAPPDATA\Programs\Python\Python313\pythonw.exe",
    "$env:LOCALAPPDATA\Programs\Python\Python312\pythonw.exe"
)
$doPath = Get-Command pythonw.exe -ErrorAction SilentlyContinue
if ($doPath) { $candidatos += $doPath.Source }

$PYTHONW = $candidatos | Where-Object { Test-Path $_ } | Select-Object -First 1
if ($null -eq $PYTHONW) {
    Write-Host "  PAREI: não achei pythonw.exe em lugar nenhum." -ForegroundColor Red
    exit 1
}
Write-Host "  $PYTHONW" -ForegroundColor Green

# ---------------------------------------------------------------- 5/7
Titulo "5/7  Testando de que jeito este Python consegue iniciar o script"

# Nesta máquina o pythonw.exe NÃO inicia script por caminho de arquivo,
# e falha em silêncio absoluto — nem chega na linha 1. Por isso as duas
# formas abaixo são testadas de verdade, com o --autoteste escrevendo
# no log, em vez de eu escolher uma e torcer.
$prefixo = "import sys; sys.path.insert(0, r'$PASTA'); import rasterlink_hotfolder as r; "
$formas = @(
    @{
        nome      = "-m (módulo) "
        teste     = @("-m", "rasterlink_hotfolder", "--autoteste")
        paraValer = @("-m", "rasterlink_hotfolder", "--uma-vez")
    },
    @{
        nome      = "-c (código) "
        teste     = @("-c", ($prefixo + "r.logger_arquivo('info', 'autoteste ok - iniciei por: -c')"))
        paraValer = @("-c", ($prefixo + "r.principal_uma_vez()"))
    }
)

$escolhida = $null
foreach ($forma in $formas) {
    $antes = 0
    if (Test-Path $LOG) { $antes = (Get-Item $LOG).Length }

    try {
        $p = Start-Process -FilePath $PYTHONW -ArgumentList $forma.teste -WorkingDirectory $PASTA -PassThru -Wait -WindowStyle Hidden
        $codigo = $p.ExitCode
    } catch {
        $codigo = "não iniciou"
    }

    $depois = 0
    if (Test-Path $LOG) { $depois = (Get-Item $LOG).Length }

    if ($depois -gt $antes) {
        Write-Host "  $($forma.nome).: FUNCIONA (escreveu no log)" -ForegroundColor Green
        if ($null -eq $escolhida) { $escolhida = $forma }
    } else {
        Write-Host "  $($forma.nome).: NÃO funciona (saída $codigo, nada no log)" -ForegroundColor DarkGray
    }
}

if ($null -eq $escolhida) {
    Write-Host ""
    Write-Host "  PAREI: nenhuma das duas formas conseguiu iniciar o script." -ForegroundColor Red
    Write-Host "  Olhe $PASTA\rasterlink_hotfolder_crash.log" -ForegroundColor Red
    exit 1
}

$ARGUMENTOS = ($escolhida.paraValer | ForEach-Object {
    if ($_ -match '\s') { '"' + $_ + '"' } else { $_ }
}) -join " "
Write-Host ""
Write-Host "  Vou agendar assim: $ARGUMENTOS" -ForegroundColor Green

# ---------------------------------------------------------------- 6/7
Titulo "6/7  Recriando a tarefa"

# Escapa o que for texto meu dentro do XML — o argumento do -c tem
# aspas e sinais que quebrariam o XML se entrassem crus.
$argXml = [System.Security.SecurityElement]::Escape($ARGUMENTOS)

# Sobre as escolhas daqui:
#   - DOIS gatilhos: no logon e por horário. Qualquer um dos dois
#     sozinho já mantém a coisa de pé; juntos, um reinício estranho ou
#     um logon que não disparou não deixam a fila parada.
#   - Repetition sem <Duration> = repete PRA SEMPRE. Com duração, ela
#     acaba (foi assim que o conserto anterior morreu calado).
#   - ExecutionTimeLimit PT5M: passada travada (OneDrive pendurado) é
#     morta em 5 min em vez de segurar o lugar pra sempre e bloquear
#     todas as próximas por causa do IgnoreNew.
#   - IgnoreNew + a trava de instância única do próprio script: duas
#     passadas juntas pegariam o MESMO arquivo e o RIP criaria job
#     duplicado, que vira material impresso duas vezes.
#   - InteractiveToken: a conta desta máquina não tem senha, então
#     "executar estando o usuário conectado ou não" não funciona.
#   - StopIfGoingOnBatteries / DisallowStartIfOnBatteries falsos: o
#     padrão do Windows é PARAR a tarefa em bateria, e ninguém lembra
#     disso quando a fila some.
$xml = @"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>Manda pra hot folder do RasterLink7 o que chegar na fila do OneDrive. Uma passada por minuto.</Description>
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
      <UserId>$env:USERNAME</UserId>
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
    <ExecutionTimeLimit>PT5M</ExecutionTimeLimit>
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
Write-Host "  Tarefa criada." -ForegroundColor Green

# ---------------------------------------------------------------- 7/7
Titulo "7/7  Conferindo que ela roda de verdade"

Start-ScheduledTask -TaskName $NOME_TAREFA
Start-Sleep -Seconds 8

$tarefa = Get-ScheduledTask -TaskName $NOME_TAREFA
$info   = Get-ScheduledTaskInfo -TaskName $NOME_TAREFA
Write-Host "  Estado...............: $($tarefa.State)"
Write-Host "  Última execução......: $($info.LastRunTime)"
Write-Host "  Resultado da última..: $($info.LastTaskResult)   (0 = deu certo)"
Write-Host "  Próxima execução.....: $($info.NextRunTime)"
foreach ($g in $tarefa.Triggers) {
    Write-Host "  Gatilho..............: $($g.CimClass.CimClassName) repetindo a cada $($g.Repetition.Interval)"
}

if (Test-Path $LOG) {
    Write-Host ""
    Write-Host "  Fim do log ($LOG):" -ForegroundColor DarkGray
    Get-Content $LOG -Tail 12 | ForEach-Object { Write-Host "    $_" -ForegroundColor DarkGray }
}

$crash = Join-Path $PASTA "rasterlink_hotfolder_crash.log"
if (Test-Path $crash) {
    Write-Host ""
    Write-Host "  ATENÇÃO: existe arquivo de crash. Fim dele:" -ForegroundColor Yellow
    Get-Content $crash -Tail 15 | ForEach-Object { Write-Host "    $_" -ForegroundColor Yellow }
}

Write-Host ""
Write-Host "  Pronto. Daqui pra frente ela dispara sozinha de minuto em minuto." -ForegroundColor Green
Write-Host "  Pra saber se está viva: 'Última execução' no Agendador tem que estar" -ForegroundColor Green
Write-Host "  sempre com menos de 1 minuto." -ForegroundColor Green
