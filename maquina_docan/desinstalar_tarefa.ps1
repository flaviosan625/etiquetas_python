# Tira a tarefa do vigia da DOCAN DESTA máquina (a da impressora).
#
# Desfaz o que o instalar_tarefa.ps1 fez, e só isso: a pasta C:\VigiaDocan
# fica onde está, com o log e o estado de avisos. Apagar ela não traria
# benefício nenhum e levaria junto o histórico de quando cada arte foi
# entregue nesta máquina.
#
# Sem vigia aqui, nada se perde: o arquivo continua na fila do OneDrive
# esperando quem atender. Doze minutos depois da última passada, o posto
# fica livre pra outra máquina assumir (ver outro_vigia_no_posto).

$ErrorActionPreference = "Stop"

$NOME_TAREFA = "Vigia DOCAN (SAi)"
$PASTA       = "C:\VigiaDocan"

Write-Host ""
Write-Host "  Esta máquina: $env:COMPUTERNAME" -ForegroundColor DarkGray
Write-Host "  Removendo a tarefa '$NOME_TAREFA'" -ForegroundColor Cyan
Write-Host ""

$tarefa = Get-ScheduledTask -TaskName $NOME_TAREFA -ErrorAction SilentlyContinue
if ($null -eq $tarefa) {
    Write-Host "  Não existe tarefa com esse nome aqui — nada a fazer." -ForegroundColor Yellow
} else {
    $backup = Join-Path $PSScriptRoot ("tarefa_removida_{0:yyyyMMdd_HHmmss}.xml" -f (Get-Date))
    try {
        Export-ScheduledTask -TaskName $NOME_TAREFA | Out-File $backup -Encoding utf8
        Write-Host "  Cópia da tarefa guardada em: $backup" -ForegroundColor DarkGray
    } catch {
        Write-Host "  (não consegui guardar a cópia da tarefa: $($_.Exception.Message))" -ForegroundColor DarkGray
    }
    try {
        Stop-ScheduledTask -TaskName $NOME_TAREFA -ErrorAction SilentlyContinue
        Unregister-ScheduledTask -TaskName $NOME_TAREFA -Confirm:$false
        Write-Host "  Tarefa removida." -ForegroundColor Green
    } catch {
        Write-Host "  PAREI: $($_.Exception.Message)" -ForegroundColor Red
        Write-Host "  Se for acesso negado, rode o .bat como administrador." -ForegroundColor Red
        exit 1
    }
}

# A trava fica pra trás quando um processo é morto no meio. Arquivo de
# trava velho não impede nada (ela é por bloqueio de arquivo, não por
# existência), mas deixar limpo evita susto na próxima instalação.
$trava = Join-Path $PASTA "rasterlink_hotfolder_sai.lock"
if (Test-Path $trava) {
    Remove-Item $trava -ErrorAction SilentlyContinue
    Write-Host "  Trava antiga removida: $trava" -ForegroundColor DarkGray
}

# LARGAR O POSTO, se ele for desta máquina.
#
# O sinal de vida é o que diz qual PC atende a DOCAN, e o vigia se recusa
# a rodar quando o posto tem dono vivo em outro lugar. Sem apagar aqui, a
# máquina seguinte espera 12 minutos sem entender por quê — aconteceu em
# 03/10/2026, porque este desinstalador foi rodado no PC principal (os
# dois kits têm .bat de mesmo nome) e lá quem soltava o sinal era o outro.
#
# Só apaga se o sinal for DESTA máquina: largar o posto de outro PC que
# está vivo colocaria dois vigias na mesma fila, que é exatamente o que
# essa trava existe pra impedir.
$fila = Get-ChildItem -Path "$env:USERPROFILE\OneDrive\UNYCOMUNICACAO" -Directory -Filter "FILA*MAQUINAS" -ErrorAction SilentlyContinue | Select-Object -First 1
if ($fila) {
    $sinal = Join-Path $fila.FullName "_sinal_de_vida_sai.json"
    if (Test-Path $sinal) {
        $dona = ""
        try { $dona = (Get-Content $sinal -Raw -Encoding UTF8 | ConvertFrom-Json).maquina } catch { }
        if ($dona -eq $env:COMPUTERNAME) {
            try {
                Remove-Item $sinal -Force
                Write-Host "  Sinal de vida apagado — o posto da DOCAN está LIVRE agora." -ForegroundColor Green
            } catch {
                Write-Host "  Não consegui apagar o sinal ($sinal); quem assumir espera até 12 min." -ForegroundColor Yellow
            }
        } elseif ($dona) {
            Write-Host "  O posto é da máquina $dona, não desta — deixei o sinal onde está." -ForegroundColor Yellow
        }
    }
}

Write-Host ""
Write-Host "  Os arquivos continuam em $PASTA (log e histórico)." -ForegroundColor Green
Write-Host "  A fila do OneDrive não se perde: ela espera quem atender." -ForegroundColor Green
