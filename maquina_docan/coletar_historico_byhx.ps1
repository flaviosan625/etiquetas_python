try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch {}

# Copia os arquivos de HISTORICO do programa da impressora pra pasta do
# OneDrive, pra eu poder ler do outro computador.
#
# Por que estes (achados pelo diagnostico de 03/10/2026, em C:\PrinterManager):
#
#   Joblist_His.xml   o historico dos trabalhos — o que entrou na maquina
#   Joblist.xml       a fila de agora
#   PrintedArea.Log   a AREA impressa; e com ela que o relatorio de
#                     producao pode deixar de provar o que foi ENTREGUE e
#                     passar a provar o que foi IMPRESSO, em metro de verdade
#   Print.log         o log de impressao (estava vazio, vai junto pra ver
#                     se enche quando a maquina roda)
#
# So COPIA. Nao apaga, nao muda, nao precisa de administrador.

$ErrorActionPreference = "Continue"

$ORIGEM = "C:\PrinterManager"
$DESTINO = Join-Path $PSScriptRoot "_byhx"
$ARQUIVOS = @("Joblist_His.xml", "Joblist.xml", "PrintedArea.Log", "Print.log", "Setting.xml")

Write-Host ""
Write-Host "  HISTORICO DO PROGRAMA DA IMPRESSORA"
Write-Host "  Maquina: $env:COMPUTERNAME   Agora: $(Get-Date -Format 'dd/MM HH:mm')"
Write-Host ""

if (-not (Test-Path $ORIGEM)) {
    Write-Host "  PAREI: nao achei $ORIGEM nesta maquina." -ForegroundColor Red
    exit 1
}
New-Item -ItemType Directory -Path $DESTINO -Force | Out-Null

$copiados = 0
foreach ($nome in $ARQUIVOS) {
    # pode haver mais de um com o mesmo nome em subpastas; pega o MAIOR,
    # que e o que tem conteudo de verdade
    $achados = Get-ChildItem $ORIGEM -Recurse -Filter $nome -File -ErrorAction SilentlyContinue |
               Sort-Object Length -Descending
    if (-not $achados) { Write-Host "  (nao achei $nome)"; continue }
    $a = $achados[0]
    Copy-Item $a.FullName (Join-Path $DESTINO $nome) -Force -ErrorAction SilentlyContinue
    if (Test-Path (Join-Path $DESTINO $nome)) {
        Write-Host ("  copiado: {0,-20} {1,8:N0} KB   (de {2})" -f $nome, ($a.Length/1KB), $a.DirectoryName)
        $copiados++
    }
}

Write-Host ""
Write-Host "  $copiados arquivo(s) em $DESTINO"
Write-Host "  Deixe o OneDrive sincronizar — do outro PC eu leio tudo isto." -ForegroundColor Green
Write-Host ""
