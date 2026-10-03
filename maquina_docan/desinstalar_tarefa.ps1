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

Write-Host ""
Write-Host "  Os arquivos continuam em $PASTA (log e histórico)." -ForegroundColor Green
Write-Host "  A fila do OneDrive não se perde: ela espera quem atender." -ForegroundColor Green
