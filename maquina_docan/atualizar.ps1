# Leva pra ESTA máquina a versão nova do vigia. Rode pelo atualizar.bat,
# ao lado deste arquivo.
#
# POR QUE EXISTE UM ATUALIZADOR SEPARADO DO INSTALADOR
# O instalador cria a tarefa no Agendador, confere o Python, confere o
# posto — tudo de novo. Quando a única coisa que mudou é o rasterlink_
# hotfolder.py, isso é cerimônia demais pra uma cópia de 90 KB, e cada
# conferência a mais é uma chance a mais de ele parar no meio achando que
# algo deu errado.
#
# O QUE MUDA SÓ CHEGA AQUI QUANDO ALGUÉM TRAZ
# O PC principal roda o vigia DO REPOSITÓRIO; esta máquina roda a CÓPIA
# em C:\VigiaDocan. Então mexer no projeto não muda nada aqui até este
# script rodar — é a mesma história do maquina_rip\atualizar.bat, e já
# custou um dia de UJV e SWJ rodando versão velha (22/09/2026).
#
# QUEM CONFIRMA UM DEPLOY É O SINAL DE VIDA, NÃO A MENSAGEM DO SCRIPT
# No PC errado o copiador ainda diria "tudo certo". Por isso ele compara
# o nome desta máquina com o que o próprio vigia gravou no sinal do posto
# e, no fim, DISPARA a tarefa e espera o sinal ficar novo.

$ErrorActionPreference = "Stop"

try {
    Start-Transcript -Path (Join-Path $PSScriptRoot ("atualizacao_{0}.txt" -f $env:COMPUTERNAME)) -Force | Out-Null
} catch { }

$NOME_TAREFA = "Vigia DOCAN (SAi)"
$PASTA       = "C:\VigiaDocan"
$SCRIPT      = Join-Path $PASTA "rasterlink_hotfolder.py"
$LOG         = Join-Path $PASTA "rasterlink_hotfolder.log"
$POSTO       = "sai"
$SINAL       = Join-Path $env:USERPROFILE ("OneDrive\UNYCOMUNICACAO\FILA PARA IMPRESSÃO MAQUINAS\_sinal_de_vida_{0}.json" -f $POSTO)

# O vigia novo vem ao lado deste script (é assim que a pasta do OneDrive
# é montada). Rodando de dentro do repositório, ele está uma pasta acima.
#
# DESDE 04/10/2026 SÃO QUATRO ARQUIVOS, não um: nesta máquina o vigia
# também separa o ripado de cada DOCAN na pasta dela, e pra isso precisa
# do separador. Todos só de biblioteca padrão do Python.
$ARQUIVOS = @("rasterlink_hotfolder.py", "separar_ripados.py",
              "ripados_para_nuvem.py", "caminhos.py")
function Origem($nome) {
    $aqui = Join-Path $PSScriptRoot $nome
    if (Test-Path $aqui) { return $aqui }
    $acima = Join-Path (Split-Path -Parent $PSScriptRoot) $nome
    if (Test-Path $acima) { return $acima }
    return $aqui
}
$ORIGEM = Origem "rasterlink_hotfolder.py"

function Fechar($codigo) {
    try { Stop-Transcript | Out-Null } catch { }
    exit $codigo
}

# RODAR UM PROGRAMA NO POWERSHELL 5.1 PEDE CUIDADO.
#
# Com $ErrorActionPreference = "Stop", cada linha que o programa escreve
# em stderr vira um NativeCommandError e DERRUBA o script — mesmo com o
# programa terminando em código 0. Aconteceu em 04/10/2026: um
# SyntaxWarning do Python (um "\P" perdido numa docstring minha) matou
# este atualizador no meio, DEPOIS de ele já ter copiado os arquivos.
# O vigia estava certo e rodando; quem quebrou foi o script que conferia.
#
# O instalar_tarefa.ps1 já fazia isso certo desde 03/10 e eu não copiei o
# cuidado pra cá. Agora está num lugar só.
function RodarPython($exe, $argumentos) {
    # A TAREFA CHAMA pythonw.exe, QUE NÃO TEM CONSOLE — e isso muda tudo
    # aqui. O PowerShell não espera por programa sem console e NÃO
    # preenche o $LASTEXITCODE: em 04/10/2026 o código voltou VAZIO, o
    # atualizador leu vazio como falha e desfez um deploy que estava
    # certo. Conferido na mão: com atribuição a saída vem vazia e o
    # código também; só no formato de pipeline é que funcionava.
    #
    # Então duas coisas: o python.exe do lado (mesma pasta) quando
    # existir, que tem console e fala de verdade; e Start-Process em vez
    # de "& exe", que espera, devolve o ExitCode certo e faz a
    # redireção FORA do PowerShell — assim nenhuma linha de stderr vira
    # NativeCommandError, que foi o estrago da tentativa anterior.
    $console = $exe -replace "pythonw\.exe$", "python.exe"
    if (-not (Test-Path $console)) { $console = $exe }

    # Pro acento do log não chegar embaralhado na tela.
    $ioAntigo = $env:PYTHONIOENCODING
    $env:PYTHONIOENCODING = "utf-8"
    $fSaida = Join-Path $env:TEMP "vigia_atualizar_saida.txt"
    $fErro  = Join-Path $env:TEMP "vigia_atualizar_erro.txt"
    try {
        $proc = Start-Process -FilePath $console -ArgumentList $argumentos `
                              -WorkingDirectory $PASTA -NoNewWindow -Wait -PassThru `
                              -RedirectStandardOutput $fSaida -RedirectStandardError $fErro
        $codigo = $proc.ExitCode
    } catch {
        return @{ saida = @("não consegui rodar o $console : $($_.Exception.Message)"); codigo = $null }
    } finally {
        $env:PYTHONIOENCODING = $ioAntigo
    }

    $linhas = @()
    foreach ($f in @($fSaida, $fErro)) {
        if (Test-Path $f) {
            $linhas += @(Get-Content $f -Encoding UTF8 -ErrorAction SilentlyContinue)
            Remove-Item $f -Force -ErrorAction SilentlyContinue
        }
    }
    return @{ saida = @($linhas | Where-Object { "$_".Trim() }); codigo = $codigo }
}

function Parar($linhas) {
    Write-Host ""
    Write-Host "  PAREI." -ForegroundColor Red
    foreach ($l in $linhas) { Write-Host "  $l" -ForegroundColor Yellow }
    Write-Host ""
    Write-Host "  Nada foi alterado." -ForegroundColor Green
    Fechar 1
}

Write-Host ""
Write-Host "  ATUALIZAR O VIGIA DA DOCAN NESTA MÁQUINA"
Write-Host "  Esta máquina: $env:COMPUTERNAME   Agora: $(Get-Date -Format 'dd/MM HH:mm')"
Write-Host ""

# 1. É esta a máquina certa?
#
# A pasta deste kit está no OneDrive, sincronizada nos dois PCs, e os dois
# kits têm .bat de mesmo nome — em 03/10/2026 ele rodou o da DOCAN aqui no
# PC principal sem perceber. Quem denuncia o PC principal é o que só
# existe nele: a tarefa do Checklist e o repositório na área de trabalho.
$souOPrincipal = @()
if (Get-ScheduledTask -TaskName "Checklist de Producao" -ErrorAction SilentlyContinue) {
    $souOPrincipal += "a tarefa 'Checklist de Producao' está instalada aqui"
}
$repo = Join-Path $env:USERPROFILE "Desktop\etiquetas_python\rasterlink_hotfolder.py"
if (Test-Path $repo) { $souOPrincipal += "o projeto está em $(Split-Path -Parent $repo)" }
if ($souOPrincipal.Count -gt 0) {
    foreach ($m in $souOPrincipal) { Write-Host "    - $m" -ForegroundColor Yellow }
    Parar @("Esta parece ser a MÁQUINA PRINCIPAL, não a da impressora.",
            "Aqui o vigia roda do repositório e já está atualizado: não há o que copiar.",
            "Abra esta mesma pasta do OneDrive NA MÁQUINA DA DOCAN e rode por lá.")
}

if (-not (Test-Path $ORIGEM)) {
    Parar @("Não achei o rasterlink_hotfolder.py ao lado deste script ($ORIGEM).",
            "Ele tem que vir junto na pasta — é o vigia em si.")
}
if (-not (Test-Path $SCRIPT)) {
    Parar @("Não existe ${SCRIPT}: o vigia nunca foi instalado nesta máquina.",
            "Rode o instalar_tarefa.bat primeiro — ele cria a pasta e a tarefa.")
}

# 2. Já está igual?
$novo  = Get-Item $ORIGEM
$velho = Get-Item $SCRIPT
Write-Host "  no OneDrive : $('{0,8:N0}' -f ($novo.Length/1KB)) KB   $($novo.LastWriteTime.ToString('dd/MM HH:mm'))"
Write-Host "  nesta máquina: $('{0,8:N0}' -f ($velho.Length/1KB)) KB   $($velho.LastWriteTime.ToString('dd/MM HH:mm'))"
if ($novo.Length -eq $velho.Length) {
    Write-Host ""
    Write-Host "  Os dois têm o mesmo tamanho — provavelmente já é a mesma versão." -ForegroundColor Cyan
    Write-Host "  Vou copiar de novo de qualquer jeito: custa 90 KB e tira a dúvida." -ForegroundColor Cyan
}

# 3. Copiar, guardando as anteriores.
#
# A cópia de segurança é barata (uns 150 KB no total) e salva o dia em que
# a versão nova vier com defeito: é só renomear de volta e a tarefa volta
# a funcionar. Guarda ANTES de copiar qualquer um, porque o desfazer tem
# que devolver o conjunto inteiro — vigia novo com separador velho é uma
# combinação que nunca foi testada.
$guardados = @{}
try {
    foreach ($nome in $ARQUIVOS) {
        $instalado = Join-Path $PASTA $nome
        if (Test-Path $instalado) {
            $copia = "$instalado.anterior"
            Copy-Item $instalado $copia -Force
            $guardados[$nome] = $copia
        }
    }
    foreach ($nome in $ARQUIVOS) {
        $de = Origem $nome
        if (-not (Test-Path $de)) {
            Write-Host "  (não achei $nome ao lado deste script — pulei)" -ForegroundColor Yellow
            continue
        }
        Copy-Item $de (Join-Path $PASTA $nome) -Force
        Write-Host ("  copiado: {0,-26} {1,8:N0} KB" -f $nome, ((Get-Item $de).Length/1KB)) -ForegroundColor Green
    }
} catch {
    Parar @("Não consegui escrever em $PASTA : $($_.Exception.Message)",
            "Feche esta janela, clique com o BOTÃO DIREITO no atualizar.bat e",
            "escolha 'Executar como administrador'.")
}
Write-Host ""
Write-Host "  As versões anteriores ficaram como <nome>.anterior, na mesma pasta." -ForegroundColor Green

# 4. O vigia aguenta subir?
#
# --autoteste só diz se ele consegue INICIAR: import, caminhos, cadastro.
# Um erro de sintaxe no arquivo novo aparece aqui, não daqui a um minuto
# no log que ninguém lê.
$acao = $null
try {
    $tarefa = Get-ScheduledTask -TaskName $NOME_TAREFA -ErrorAction Stop
    $acao = $tarefa.Actions[0]
} catch {
    Write-Host "  (não achei a tarefa '$NOME_TAREFA' — confira no Agendador)" -ForegroundColor Yellow
}
if ($acao -and $acao.Execute) {
    Write-Host ""
    Write-Host "  Conferindo se o vigia novo inicia..."
    $r = RodarPython $acao.Execute @("-m", "rasterlink_hotfolder", "--autoteste")
    foreach ($linha in $r.saida) { Write-Host "    $linha" }
    $codigo = $r.codigo
    # "Não sei" não é "falhou". Desfazer um deploy bom por causa de uma
    # resposta que não veio foi exatamente o erro de 04/10/2026 —
    # conferido: com pythonw.exe o código voltava vazio.
    if ($null -eq $codigo) {
        Write-Host "  Não consegui saber se o vigia iniciou (o programa não devolveu código)." -ForegroundColor Yellow
        Write-Host "  NÃO vou desfazer por isso. O sinal de vida, logo abaixo, é a prova que vale." -ForegroundColor Yellow
        $codigo = 0
    }
    if ($codigo -ne 0) {
        Write-Host ""
        Write-Host "  O VIGIA NOVO NÃO INICIOU (código $codigo)." -ForegroundColor Red
        Write-Host "  Desfazendo: as versões anteriores voltam agora." -ForegroundColor Yellow
        foreach ($nome in $guardados.Keys) {
            Copy-Item $guardados[$nome] (Join-Path $PASTA $nome) -Force
        }
        Write-Host "  Pronto, voltou. Mande a mensagem acima pra quem mexeu no vigia." -ForegroundColor Yellow
        Fechar 1
    }
    Write-Host "  Inicia." -ForegroundColor Green

    # 4b. A pasta de saída de cada DOCAN, e um atalho pra elas.
    #
    # A partir de agora o ripado não fica mais num monte só: o vigia
    # separa cada .prt na pasta da máquina que o gerou, com prova do
    # RIPLOG. Quem precisa ACHAR a pasta é gente — por isso o atalho na
    # área de trabalho, igual ao que existe no PC principal.
    #
    # Quem diz onde é a raiz é o próprio vigia (--preparar-ripados):
    # nesta máquina não há D:, e caminho escrito de cabeça erra calado.
    Write-Host ""
    Write-Host "  Preparando a pasta de saída de cada DOCAN..."
    $raiz = $null
    $r = RodarPython $acao.Execute @("-m", "rasterlink_hotfolder", "--preparar-ripados", "--posto", $POSTO)
    foreach ($linha in $r.saida) {
        if ($linha -match "^RAIZ=(.+)$") { $raiz = $Matches[1].Trim() } else { Write-Host "    $linha" }
    }

    if ($raiz -and (Test-Path $raiz)) {
        Write-Host "    raiz do ripado nesta máquina: $raiz" -ForegroundColor Green
        try {
            $atalho = Join-Path ([Environment]::GetFolderPath("Desktop")) "RIPADOS.lnk"
            $sh = New-Object -ComObject WScript.Shell
            $lnk = $sh.CreateShortcut($atalho)
            $lnk.TargetPath = $raiz
            $lnk.Description = "Ripados das DOCAN, separados por maquina"
            $lnk.Save()
            Write-Host "    atalho 'RIPADOS' na área de trabalho -> $raiz" -ForegroundColor Green
        } catch {
            Write-Host "    (não consegui criar o atalho: $($_.Exception.Message))" -ForegroundColor Yellow
        }
    }
}

# 5. A prova: a tarefa roda e o sinal de vida fica NOVO.
#
# Mensagem de script não prova deploy — o sinal prova, porque é o próprio
# vigia que escreve, com o nome desta máquina.
$antes = $null
if (Test-Path $SINAL) { $antes = (Get-Item $SINAL).LastWriteTime }
Write-Host ""
Write-Host "  Disparando a tarefa e esperando o sinal de vida..."
try { Start-ScheduledTask -TaskName $NOME_TAREFA } catch {
    Write-Host "  (não consegui disparar a tarefa: $($_.Exception.Message))" -ForegroundColor Yellow
}
$apareceu = $false
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Seconds 2
    if (-not (Test-Path $SINAL)) { continue }
    $agora = (Get-Item $SINAL).LastWriteTime
    if ($null -eq $antes -or $agora -gt $antes) { $apareceu = $true; break }
}

Write-Host ""
if ($apareceu) {
    try {
        $dados = Get-Content $SINAL -Raw | ConvertFrom-Json
        Write-Host "  TUDO CERTO. O vigia rodou agora e assinou como '$($dados.maquina)', posto '$($dados.posto)'." -ForegroundColor Green
        Write-Host "  Máquinas atendidas: $(($dados.maquinas | Get-Member -MemberType NoteProperty | ForEach-Object { $_.Name }) -join ', ')" -ForegroundColor Green
    } catch {
        Write-Host "  TUDO CERTO. O sinal de vida foi reescrito agora." -ForegroundColor Green
    }
} else {
    Write-Host "  O sinal de vida NÃO mudou em 1 minuto." -ForegroundColor Yellow
    Write-Host "  Pode ser o OneDrive demorando, ou a tarefa não disparando." -ForegroundColor Yellow
    Write-Host "  Confira o fim do log abaixo e, se precisar, o Agendador de Tarefas." -ForegroundColor Yellow
}

if (Test-Path $LOG) {
    Write-Host ""
    Write-Host "  --- fim do log do vigia ---"
    Get-Content $LOG -Tail 12 | ForEach-Object { Write-Host "    $_" }
}

Write-Host ""
Fechar 0
