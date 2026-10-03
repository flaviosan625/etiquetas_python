# Instala o vigia da DOCAN NA MÁQUINA DA IMPRESSORA — aquela onde agora
# roda o SAi Production Manager 22.0. Rode pelo instalar_tarefa.bat, ao
# lado deste arquivo, com o botão direito > "Executar como administrador".
#
# POR QUE ESTE INSTALADOR EXISTE, SE JÁ HAVIA O DO PC PRINCIPAL
# Até 02/10/2026 o SAi ripava a DOCAN no PC principal: o vigia de lá
# entregava na hot folder, o .prt nascia no D: daquele PC e subia 13,8 GB
# pelo OneDrive pra máquina buscar. Com o Production Manager instalado
# aqui, o ripado já nasce do lado da impressora — e quem precisa pegar a
# fila do OneDrive passa a ser ESTA máquina.
#
# O QUE VIAJA PRA CÁ É UM ARQUIVO SÓ
# O rasterlink_hotfolder.py é feito pra andar sozinho: fora da biblioteca
# padrão do Python ele não precisa de nada (o PyMuPDF só entra quando há
# giro, e as DOCAN não giram — "DOCAN só entrega", regra de 24/09/2026).
# Então aqui não tem repositório nem .venv: o arquivo é copiado pra
# C:\VigiaDocan e a tarefa chama o Python do sistema.
#
# A PASTA NÃO PODE SER SINCRONIZADA
# A trava, o log e o estado de avisos moram ao lado do .py. Num caminho
# do OneDrive, a tarefa e uma execução na mão travariam em arquivos
# DIFERENTES — as duas se achando sozinhas, pegando o mesmo arquivo da
# fila, e o SAi ripando duas vezes.
#
# UM POSTO, UMA MÁQUINA
# Antes de instalar, este script confere o sinal de vida do posto 'sai'
# na fila do OneDrive. Se outro PC estiver atendendo, ele PARA e manda
# desligar lá primeiro: dois vigias no mesmo posto duplicam job e apagam
# linha do registro de produção (foi assim que 108 entregas sumiram entre
# 17 e 22/09/2026). O próprio vigia também se protege disso sozinho, mas
# descobrir aqui é melhor que descobrir pelo log depois.

$ErrorActionPreference = "Stop"

# TUDO O QUE ELE DIZ FICA GRAVADO, na própria pasta do kit — que está no
# OneDrive, o único caminho que as duas máquinas enxergam.
#
# Por que: a máquina da impressora não é vista do PC principal (nem ping,
# nem rede), e em 03/10/2026 passamos quase uma hora perguntando "o que
# apareceu na tela?" e recebendo "instalado" — enquanto o instalador
# parava numa conferência e ninguém sabia em qual. Transcrever mensagem a
# dois computadores de distância é lento e erra; o arquivo não.
try {
    Start-Transcript -Path (Join-Path $PSScriptRoot ("instalacao_{0}.txt" -f $env:COMPUTERNAME)) -Force | Out-Null
} catch { }

$NOME_TAREFA = "Vigia DOCAN (SAi)"
$PASTA       = "C:\VigiaDocan"
# O vigia vem ao lado deste instalador (é assim que a pasta do OneDrive é
# montada). Rodando de dentro do repositório, ele está uma pasta acima.
$ORIGEM      = Join-Path $PSScriptRoot "rasterlink_hotfolder.py"
if (-not (Test-Path $ORIGEM)) {
    $acima = Join-Path (Split-Path -Parent $PSScriptRoot) "rasterlink_hotfolder.py"
    if (Test-Path $acima) { $ORIGEM = $acima }
}
$SCRIPT      = Join-Path $PASTA "rasterlink_hotfolder.py"
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

function Fechar($codigo) {
    try { Stop-Transcript | Out-Null } catch { }
    exit $codigo
}

function Parar($motivos) {
    Write-Host ""
    Write-Host "  PAREI ANTES DE MEXER EM QUALQUER COISA." -ForegroundColor Red
    foreach ($m in $motivos) { Write-Host "    - $m" -ForegroundColor Yellow }
    Write-Host ""
    Write-Host "  Nada foi alterado." -ForegroundColor Green
    Write-Host "  (o que apareceu aqui ficou gravado em instalacao_$env:COMPUTERNAME.txt, nesta pasta)" -ForegroundColor DarkGray
    Fechar 1
}

# ---------------------------------------------------------------- 1/7
Titulo "1/7  Conferindo o terreno antes de mexer em qualquer coisa"

Write-Host "  Esta máquina: $env:COMPUTERNAME"

# ESTE KIT É PRA RODAR NA MÁQUINA DA IMPRESSORA.
#
# A pasta dele fica no OneDrive, que está sincronizado nos dois PCs — e os
# dois kits têm .bat de mesmo nome. Em 03/10/2026 ele rodou os dois aqui no
# PC principal sem perceber. Rodar o instalador no PC errado é pior do que
# não rodar: cria um segundo vigia pro mesmo posto, que é exatamente o que
# duplica job e apaga linha do registro.
#
# Quem denuncia o PC principal é o que só existe nele: a tarefa do
# Checklist de Produção e o repositório na área de trabalho.
$souOPrincipal = @()
if (Get-ScheduledTask -TaskName "Checklist de Producao" -ErrorAction SilentlyContinue) {
    $souOPrincipal += "a tarefa 'Checklist de Producao' está instalada aqui"
}
$repo = Join-Path $env:USERPROFILE "Desktop\etiquetas_python\rasterlink_hotfolder.py"
if (Test-Path $repo) { $souOPrincipal += "o projeto está em $(Split-Path -Parent $repo)" }

if ($souOPrincipal.Count -gt 0) {
    Write-Host ""
    Write-Host "  PAREI: esta parece ser a MÁQUINA PRINCIPAL, não a da impressora." -ForegroundColor Red
    foreach ($m in $souOPrincipal) { Write-Host "    - $m" -ForegroundColor Yellow }
    Write-Host ""
    Write-Host "  Este kit é pra rodar NA MÁQUINA DA DOCAN — a que tem o Production" -ForegroundColor Yellow
    Write-Host "  Manager do lado da impressora. Abra lá a mesma pasta do OneDrive" -ForegroundColor Yellow
    Write-Host "  (UNYCOMUNICACAO\INSTALAR NAS MAQUINAS\DOCAN) e rode por lá." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "  Se o que você quer é o CONTRÁRIO — trazer a DOCAN de volta pra esta" -ForegroundColor Cyan
    Write-Host "  máquina —, o instalador certo é:" -ForegroundColor Cyan
    Write-Host "      etiquetas_python\maquina_sai\instalar_tarefa.bat" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  Nada foi alterado." -ForegroundColor Green
    Fechar 1
}

# Criar tarefa no Agendador precisa de administrador. Em vez de mandar o
# usuário fechar e clicar com o botão direito — que foi onde isto travou a
# noite inteira de 03/10/2026, porque duplo clique é o gesto natural —, ele
# PEDE a permissão do Windows sozinho e se reabre elevado.
#
# Reabre o .BAT, não este .ps1: assim o 'pause' do fim mantém a janela
# aberta pra pessoa ler o resultado. E vai por -FilePath, nunca montando
# uma linha de comando: o caminho tem espaço ("INSTALAR NAS MAQUINAS"),
# e cmd.exe come aspas de um jeito que quebraria calado.
$souAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
            ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $souAdmin) {
    $bat = Join-Path $PSScriptRoot "instalar_tarefa.bat"
    Write-Host ""
    Write-Host "  Criar tarefa no Agendador precisa de administrador." -ForegroundColor Yellow
    Write-Host "  Vou pedir a permissão do Windows e me reabrir — clique em SIM." -ForegroundColor Yellow
    try {
        Start-Process -FilePath $bat -Verb RunAs | Out-Null
        Write-Host "  (continua na outra janela, a que abriu com permissão)" -ForegroundColor Green
    } catch {
        Write-Host ""
        Write-Host "  Você recusou a permissão, ou ela não foi pedida." -ForegroundColor Red
        Write-Host "  Então feche isto, clique com o BOTÃO DIREITO no instalar_tarefa.bat" -ForegroundColor Yellow
        Write-Host "  e escolha 'Executar como administrador'." -ForegroundColor Yellow
    }
    Write-Host ""
    Write-Host "  Nada foi alterado por esta janela." -ForegroundColor Green
    Fechar 0
}

if (-not (Test-Path $ORIGEM)) {
    Parar @("Não achei o rasterlink_hotfolder.py ao lado deste instalador ($ORIGEM).",
            "Ele tem que vir junto na pasta — é o vigia em si.")
}

# O Python do sistema. Procura por PADRÃO, não por lista fixa: cada jeito
# de instalar põe em um lugar diferente (o do python.org pra todos os
# usuários vai pro Program Files, o pra mim vai pro LOCALAPPDATA\Programs,
# e o gerenciador novo usa pythoncore-3.XX-64). Lista fixa envelhece e
# manda instalar um Python que já está instalado.
$encontrados = @()
foreach ($padrao in @(
    "$env:LOCALAPPDATA\Python\pythoncore-3.*\pythonw.exe",
    "$env:LOCALAPPDATA\Programs\Python\Python3*\pythonw.exe",
    "$env:ProgramFiles\Python3*\pythonw.exe",
    "${env:ProgramFiles(x86)}\Python3*\pythonw.exe",
    "C:\Python3*\pythonw.exe")) {
    $encontrados += @(Get-ChildItem -Path $padrao -ErrorAction SilentlyContinue)
}
$PYTHONW = ($encontrados | Sort-Object FullName -Descending | Select-Object -First 1).FullName

# O do PATH só serve se NÃO for o atalho da Microsoft Store: aquele é um
# arquivo de zero byte que, em vez de rodar, abre a loja — e numa tarefa
# agendada isso vira uma falha silenciosa, que é a pior de todas.
if (-not $PYTHONW) {
    $doPath = Get-Command pythonw.exe -ErrorAction SilentlyContinue
    if ($doPath -and $doPath.Source -notmatch "WindowsApps") { $PYTHONW = $doPath.Source }
}
if ($PYTHONW -and (Get-Item $PYTHONW).Length -eq 0) { $PYTHONW = $null }

if (-not $PYTHONW) {
    Parar @("Não achei Python nesta máquina (e o atalho da Microsoft Store não serve).",
            "Jeito mais curto, num PowerShell como administrador:",
            "    winget install -e --id Python.Python.3.13",
            "Ou baixe em python.org/downloads e MARQUE 'Add python.exe to PATH' antes de instalar.",
            "O vigia não precisa de biblioteca nenhuma além da padrão — é só o Python.",
            "Depois, rode este instalador de novo.")
}
$PYTHON = $PYTHONW -replace 'pythonw\.exe$', 'python.exe'
Write-Host "  Python......: $PYTHONW" -ForegroundColor Green

if ($PASTA -match "OneDrive") {
    Parar @("A pasta de instalação não pode ser sincronizada: $PASTA")
}

# ---------------------------------------------------------------- 2/7
Titulo "2/7  Copiando o vigia pra $PASTA"

if (-not (Test-Path $PASTA)) { New-Item -ItemType Directory -Path $PASTA | Out-Null }
if (Test-Path $SCRIPT) {
    $antigo = Get-Item $SCRIPT
    Write-Host "  Antes: $($antigo.Length) bytes, de $($antigo.LastWriteTime)" -ForegroundColor DarkGray
}
Copy-Item $ORIGEM $SCRIPT -Force
$novo = Get-Item $SCRIPT
Write-Host "  Depois: $($novo.Length) bytes, de $($novo.LastWriteTime)" -ForegroundColor Green

# ---------------------------------------------------------------- 3/7
Titulo "3/7  Perguntando ao próprio vigia o que ele enxerga daqui"

# Quem sabe qual é a hot folder de cada DOCAN é o rasterlink_hotfolder.py
# — perguntar a ele evita duas verdades sobre o mesmo caminho. E o SAi
# corta o nome da pasta em 12 letras, então caminho escrito de cabeça
# erra calado: o vigia diz "enviado" e a máquina nunca recebe.
#
# O sys.path.insert é o que faz o import achar o vigia: o Python só
# procura na pasta ATUAL, e um terminal de administrador abre em
# C:\Windows\system32. Sem isto deu 'ModuleNotFoundError' na máquina da
# DOCAN em 03/10/2026 — e aqui no PC principal passava despercebido,
# porque eu rodava de dentro do repositório, onde o módulo está ao lado.
#
# O stderr vem junto (2>&1) com o ErrorActionPreference afrouxado: sem
# ele a mensagem de erro do Python se perde e sobra um "Saída:" vazio,
# que não diz nada a quem está do outro lado. Afrouxar é obrigatório
# porque, com 'Stop', o PowerShell 5.1 embrulha cada linha de stderr num
# NativeCommandError e derruba o script inteiro.
$eapAntigo = $ErrorActionPreference
$ErrorActionPreference = "Continue"
$codigo = @"
import sys
sys.path.insert(0, r'$PASTA')
import rasterlink_hotfolder as r
for nome, cfg in r.maquinas_do_posto('sai').items():
    print('%s|%s' % (nome, r._config_maquina(cfg)[0]))
print('FILA|%s' % r.PASTA_FILA_ONEDRIVE)
dona = r.outro_vigia_no_posto(posto='sai')
print('DONA|%s' % (dona or ''))
"@
Push-Location $PASTA
$saida = & $PYTHON -c $codigo 2>&1
Pop-Location
$ErrorActionPreference = $eapAntigo

if ($LASTEXITCODE -ne 0 -or -not $saida) {
    Parar @("O Python não conseguiu ler o vigia recém-copiado.",
            "O que ele respondeu: $($saida -join ' / ')")
}

$problemas = @()
$dona = ""
foreach ($linha in $saida) {
    $partes = ([string]$linha).Split("|", 2)
    if ($partes.Count -lt 2) { continue }
    $chave = $partes[0].Trim()
    $valor = $partes[1].Trim()
    if ($chave -eq "FILA") {
        if (Test-Path $valor) {
            Write-Host "  Fila do OneDrive: $valor" -ForegroundColor Green
        } else {
            $problemas += "A fila do OneDrive não existe aqui: $valor (o OneDrive desta conta está sincronizado nesta máquina?)"
        }
    } elseif ($chave -eq "DONA") {
        $dona = $valor
    } else {
        if (Test-Path $valor) {
            Write-Host "  Hot folder de $chave : $valor" -ForegroundColor Green
        } else {
            $problemas += "A hot folder de $chave não existe aqui: $valor"
        }
    }
}

if ($dona -and $dona -ne $env:COMPUTERNAME) {
    $problemas += "O posto '$POSTO' está sendo atendido pela máquina $dona AGORA. Desligue a tarefa lá primeiro (maquina_sai\desinstalar_tarefa.bat, no PC principal) e rode isto de novo."
}

if ($problemas.Count -gt 0) {
    Write-Host ""
    Write-Host "  O arquivo já foi copiado, mas NÃO vou agendar nada:" -ForegroundColor Red
    foreach ($p in $problemas) { Write-Host "    - $p" -ForegroundColor Yellow }
    Write-Host ""
    Write-Host "  Sem tarefa criada, nada roda — a fila fica esperando, nada se perde." -ForegroundColor Green
    Write-Host "  Resolva o que está acima e rode este mesmo instalador de novo." -ForegroundColor Green
    Fechar 1
}

# ---------------------------------------------------------------- 4/7
Titulo "4/7  Como a tarefa está HOJE nesta máquina"

$tarefaAntiga = Get-ScheduledTask -TaskName $NOME_TAREFA -ErrorAction SilentlyContinue
if ($null -eq $tarefaAntiga) {
    Write-Host "  Não existe tarefa com esse nome aqui — instalação nova." -ForegroundColor Yellow
} else {
    $infoAntiga = Get-ScheduledTaskInfo -TaskName $NOME_TAREFA
    Write-Host "  Estado...............: $($tarefaAntiga.State)"
    Write-Host "  Última execução......: $($infoAntiga.LastRunTime)"
    Write-Host "  Resultado da última..: $(TraduzirResultado $infoAntiga.LastTaskResult)"
    $backup = Join-Path $PSScriptRoot ("tarefa_antiga_{0:yyyyMMdd_HHmmss}.xml" -f (Get-Date))
    Export-ScheduledTask -TaskName $NOME_TAREFA | Out-File $backup -Encoding utf8
    Write-Host "  Cópia da tarefa antiga: $backup" -ForegroundColor DarkGray
}

# ---------------------------------------------------------------- 5/7
Titulo "5/7  Testando se este pythonw consegue iniciar o vigia"

# Não é paranoia: na máquina do RIP o pythonw.exe NÃO inicia script por
# caminho de arquivo e falha em silêncio absoluto. O --autoteste escreve
# no log, então "funcionou" aqui é fato, não fé.
$antes = 0
if (Test-Path $LOG) { $antes = (Get-Item $LOG).Length }

$p = Start-Process -FilePath $PYTHONW `
                   -ArgumentList @("-m", "rasterlink_hotfolder", "--autoteste") `
                   -WorkingDirectory $PASTA -PassThru -Wait -WindowStyle Hidden

$depois = 0
if (Test-Path $LOG) { $depois = (Get-Item $LOG).Length }
if ($depois -le $antes) {
    Parar @("O pythonw não conseguiu iniciar o vigia (saída $($p.ExitCode), nada no log).")
}
Write-Host "  -m (módulo): FUNCIONA (escreveu no log)" -ForegroundColor Green

$ARGUMENTOS = "-m rasterlink_hotfolder --uma-vez --posto $POSTO"
Write-Host "  Vou agendar assim: $ARGUMENTOS" -ForegroundColor Green

# ---------------------------------------------------------------- 6/7
Titulo "6/7  Criando a tarefa"

$USUARIO = $env:USERNAME
try {
    $daSessao = (Get-CimInstance Win32_ComputerSystem -ErrorAction Stop).UserName
    if ($daSessao) { $USUARIO = $daSessao }
} catch { }

$argXml = [System.Security.SecurityElement]::Escape($ARGUMENTOS)

# As escolhas aqui são as mesmas das outras duas tarefas, pelos mesmos
# motivos: DOIS gatilhos (logon e horário), Repetition SEM <Duration>
# (com duração ela acaba, e foi assim que um conserto morreu calado),
# ExecutionTimeLimit de meia hora, IgnoreNew + a trava do próprio script,
# e InteractiveToken porque o SAi e o OneDrive precisam da sessão.
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
    Fechar 1
}
Write-Host "  Tarefa '$NOME_TAREFA' criada." -ForegroundColor Green

$atalho = Join-Path $PASTA "rodar_uma_vez.bat"
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
Write-Host "  Pra rodar uma passada na mão e VER: $atalho" -ForegroundColor Green

# ---------------------------------------------------------------- 7/7
Titulo "7/7  Conferindo que ela roda de verdade"

Start-ScheduledTask -TaskName $NOME_TAREFA
Start-Sleep -Seconds 10

$tarefa = Get-ScheduledTask -TaskName $NOME_TAREFA
$info   = Get-ScheduledTaskInfo -TaskName $NOME_TAREFA
Write-Host "  Estado...............: $($tarefa.State)"
Write-Host "  Última execução......: $($info.LastRunTime)"
Write-Host "  Resultado da última..: $(TraduzirResultado $info.LastTaskResult)"
Write-Host "  Próxima execução.....: $($info.NextRunTime)"

if (Test-Path $LOG) {
    Write-Host ""
    Write-Host "  Fim do log ($LOG):" -ForegroundColor DarkGray
    Get-Content $LOG -Encoding UTF8 -Tail 12 | ForEach-Object { Write-Host "    $_" -ForegroundColor DarkGray }
}

Write-Host ""
Write-Host "  Pronto. Daqui pra frente ela dispara sozinha de minuto em minuto." -ForegroundColor Green
Write-Host "  A PROVA de que esta máquina assumiu o posto é o sinal de vida:" -ForegroundColor Green
Write-Host "  o painel de Agentes, no PC principal, passa a mostrar $env:COMPUTERNAME." -ForegroundColor Green
Write-Host ""
Write-Host "  Teste de verdade: mande uma arte pela tela 'Enviar para impressão'" -ForegroundColor Cyan
Write-Host "  e veja ela aparecer na lista do Production Manager daqui." -ForegroundColor Cyan

Fechar 0
