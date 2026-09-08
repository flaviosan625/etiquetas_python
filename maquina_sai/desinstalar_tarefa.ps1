# Desfaz o que o instalar_tarefa.ps1 fez nesta máquina. Rode pelo
# desinstalar_tarefa.bat, ao lado deste arquivo.
#
# Existe porque o git guarda o código, mas não guarda a tarefa do
# Agendador. Sem isto, "voltar atrás" no vigia da DOCAN seria abrir o
# Agendador e caçar a tarefa na mão.
#
# O que ele NÃO toca, de propósito:
#   - a fila no OneDrive e o que estiver dentro dela (arquivo mandado é
#     trabalho de verdade esperando; sumir com ele seria estrago, não
#     limpeza);
#   - a hot folder do SAi;
#   - a tarefa da máquina do RIP, que nem mora aqui.

$ErrorActionPreference = "Stop"

$NOME_TAREFA = "Vigia DOCAN (SAi)"
$PASTA       = Split-Path -Parent $PSScriptRoot

# Mexer no Agendador precisa de elevação nesta máquina, igual ao
# instalar. Falhar no meio aqui é pior que falhar no instalar: pararia
# com a tarefa já derrubada e não removida.
$souAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
            ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $souAdmin) {
    Write-Host ""
    Write-Host "  PAREI ANTES DE MEXER EM QUALQUER COISA." -ForegroundColor Red
    Write-Host "  Clique com o BOTÃO DIREITO no desinstalar_tarefa.bat e escolha" -ForegroundColor Yellow
    Write-Host "  'Executar como administrador'." -ForegroundColor Yellow
    Write-Host "  Nada foi alterado." -ForegroundColor Green
    exit 1
}

Write-Host ""
Write-Host ("=" * 70) -ForegroundColor DarkGray
Write-Host "  Removendo a tarefa '$NOME_TAREFA'" -ForegroundColor Cyan
Write-Host ("=" * 70) -ForegroundColor DarkGray

$tarefa = Get-ScheduledTask -TaskName $NOME_TAREFA -ErrorAction SilentlyContinue
if ($null -eq $tarefa) {
    Write-Host "  Não existe tarefa com esse nome — nada a fazer." -ForegroundColor Yellow
} else {
    # Guarda o XML antes de apagar: reinstalar depois é um
    # schtasks /create /xml, sem precisar rodar o instalador de novo.
    $backup = Join-Path $PSScriptRoot ("tarefa_removida_{0:yyyyMMdd_HHmmss}.xml" -f (Get-Date))
    Export-ScheduledTask -TaskName $NOME_TAREFA | Out-File $backup -Encoding utf8
    Write-Host "  Cópia guardada em: $backup" -ForegroundColor DarkGray

    Stop-ScheduledTask -TaskName $NOME_TAREFA -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
    Unregister-ScheduledTask -TaskName $NOME_TAREFA -Confirm:$false
    Write-Host "  Tarefa removida." -ForegroundColor Green
}

# Uma passada pode estar rodando neste exato momento. Derrubar é seguro:
# o arquivo é montado FORA da hot folder e só entra por rename atômico,
# então ser morto no meio não deixa arquivo pela metade pro RIP ver.
$vigias = Get-CimInstance Win32_Process -Filter "Name = 'python.exe' OR Name = 'pythonw.exe'" -ErrorAction SilentlyContinue |
          Where-Object { $_.CommandLine -like "*rasterlink_hotfolder*" -and $_.CommandLine -like "*posto*sai*" }

if ($null -eq $vigias -or @($vigias).Count -eq 0) {
    Write-Host "  Nenhuma passada do posto sai rodando." -ForegroundColor Green
} else {
    foreach ($v in @($vigias)) {
        Write-Host "  Derrubando PID $($v.ProcessId)" -ForegroundColor Yellow
        Stop-Process -Id $v.ProcessId -Force -ErrorAction SilentlyContinue
    }
}

# A trava é por posto. Sobrando trancada de uma passada morta, a próxima
# instalação acharia que já tem outro vigia rodando e sairia sem fazer
# nada — calada, que é o pior jeito de falhar.
$trava = Join-Path $PASTA "rasterlink_hotfolder_sai.lock"
if (Test-Path $trava) {
    try {
        Remove-Item $trava -Force
        Write-Host "  Trava do posto sai removida." -ForegroundColor Green
    } catch {
        Write-Host "  A trava ainda está presa por algum processo — reinicie a máquina se for reinstalar." -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "  Pronto. A fila e a hot folder do SAi ficaram intactas." -ForegroundColor Green
Write-Host "  O sinal de vida do posto sai (_sinal_de_vida_sai.json) para de" -ForegroundColor Green
Write-Host "  envelhecer sozinho — é assim que se vê que ele não está mais rodando." -ForegroundColor Green
