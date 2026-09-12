# Instala (ou conserta) a tarefa do Agendador que mantem o Checklist de
# Producao do Mercado Livre atualizado a cada movimento.
#
# O modelo e o mesmo do RasterLink (o confiavel daqui): NAO um processo
# eterno que morre calado, mas UMA PASSADA POR MINUTO que trabalha uns
# segundos e sai. Cada passada olha a pasta PRODUCAO e, se algo mudou
# (entrou, saiu, mudou de pasta), regenera o PDF do checklist em
# etiquetas_geradas. So leitura — NUNCA move nem organiza arquivo (a
# organizacao de producao segue congelada).
#
# Rode pelo instalar_vigia_checklist.bat: botao direito > "Executar como
# administrador". Criar tarefa no Agendador precisa de administrador.

$ErrorActionPreference = "Stop"

$NOME    = "Checklist Producao - Mercado Livre"
$PROJETO = $PSScriptRoot
$PYTHONW = Join-Path $PROJETO ".venv\Scripts\pythonw.exe"
$ARGS    = "-m vigia_checklist --uma-vez"

# 1/4 -- precisa de administrador. Sem isso o Register-ScheduledTask da
# "Acesso negado" (0x80070005) e nada e criado.
$souAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
            ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $souAdmin) {
    Write-Host ""
    Write-Host "  PAREI: criar tarefa no Agendador precisa de administrador." -ForegroundColor Red
    Write-Host "  Feche, clique com o BOTAO DIREITO no instalar_vigia_checklist.bat" -ForegroundColor Yellow
    Write-Host "  e escolha 'Executar como administrador'. Nada foi alterado." -ForegroundColor Yellow
    exit 1
}

# 2/4 -- o pythonw da venv tem que existir (e ele que tem as dependencias).
if (-not (Test-Path $PYTHONW)) {
    Write-Host "  PAREI: nao achei $PYTHONW" -ForegroundColor Red
    Write-Host "  Recrie a venv (uv venv --python 3.14 --clear) antes de instalar." -ForegroundColor Yellow
    exit 1
}
Write-Host "  Python da tarefa..: $PYTHONW" -ForegroundColor DarkGray
Write-Host "  Pasta do projeto..: $PROJETO" -ForegroundColor DarkGray

# 3/4 -- a tarefa e criada PARA quem esta logado: e a sessao dele que o
# LogonTrigger acompanha e o token dela que o InteractiveToken usa.
$usuario = (Get-CimInstance Win32_ComputerSystem).UserName
if (-not $usuario) { $usuario = "$env:USERDOMAIN\$env:USERNAME" }
Write-Host "  Usuario da tarefa.: $usuario" -ForegroundColor DarkGray

# Repeticao PT1M SEM <Duration> = repete pra sempre; com duracao ela acaba
# calada (foi assim que um conserto antigo morreu). Dois gatilhos (logon e
# horario) pra um reinicio estranho nao deixar o checklist parado.
# IgnoreNew: duas passadas juntas nao se atropelam. PT10M de teto: passada
# pendurada (OneDrive lento) e morta em vez de segurar o lugar pra sempre.
$xml = @"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>Vigia do Checklist de Producao (Mercado Livre 26). Uma passada por minuto: se a pasta PRODUCAO mudou, regenera o PDF do checklist em etiquetas_geradas. So leitura, nao organiza nada.</Description>
  </RegistrationInfo>
  <Triggers>
    <LogonTrigger><Enabled>true</Enabled><Repetition><Interval>PT1M</Interval><StopAtDurationEnd>false</StopAtDurationEnd></Repetition></LogonTrigger>
    <TimeTrigger><StartBoundary>2026-01-01T00:00:00</StartBoundary><Enabled>true</Enabled><Repetition><Interval>PT1M</Interval><StopAtDurationEnd>false</StopAtDurationEnd></Repetition></TimeTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author"><UserId>$usuario</UserId><LogonType>InteractiveToken</LogonType><RunLevel>LeastPrivilege</RunLevel></Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <IdleSettings><StopOnIdleEnd>false</StopOnIdleEnd><RestartOnIdle>false</RestartOnIdle></IdleSettings>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <UseUnifiedSchedulingEngine>true</UseUnifiedSchedulingEngine>
    <WakeToRun>false</WakeToRun>
    <ExecutionTimeLimit>PT10M</ExecutionTimeLimit>
    <Priority>7</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec><Command>$PYTHONW</Command><Arguments>$ARGS</Arguments><WorkingDirectory>$PROJETO</WorkingDirectory></Exec>
  </Actions>
</Task>
"@

# 4/4 -- cria, dispara uma vez e confere que rodou sem erro.
Register-ScheduledTask -TaskName $NOME -Xml $xml -Force | Out-Null
Write-Host ""
Write-Host "  Tarefa criada: $NOME" -ForegroundColor Green

Start-ScheduledTask -TaskName $NOME
Start-Sleep -Seconds 6
$info = Get-ScheduledTaskInfo -TaskName $NOME
Write-Host "  Ultima execucao...: $($info.LastRunTime)"
Write-Host "  Resultado.........: $($info.LastTaskResult)  (0 = deu certo)"
Write-Host "  Proxima execucao..: $($info.NextRunTime)"
Write-Host ""
Write-Host "  Pronto. A cada minuto ela olha a pasta e atualiza o PDF se algo mudou." -ForegroundColor Green
Write-Host "  Pra saber se esta viva: 'Ultima execucao' no Agendador sempre com menos de 1 min." -ForegroundColor Green
