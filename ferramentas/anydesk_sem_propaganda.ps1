# Deixa o AnyDesk sem propaganda, sem desinstalar nada.
#
# Observacao dele (03/10/2026), que e o que destravou isto: "quando ele
# instala novamente nao tem propaganda; entao e so nao deixar entrar mais
# nada na raiz pra que as propagandas nao aparecam".
#
# E exatamente isso. Olhando a pasta do AnyDesk logo depois de uma
# reinstalacao limpa, o unico arquivo que nasce junto com as mensagens e
#
#     %APPDATA%\AnyDesk\cache\anymessage.cache
#
# o cache do "AnyMessage" — o canal por onde o programa recebe aviso,
# promocao e propaganda (ele chega com o idioma dentro: 'pt-br').
# Instalacao nova nao tem esse arquivo, e por isso nao tem anuncio; ele
# aparece depois, quando a mensagem chega.
#
# O QUE ESTE SCRIPT FAZ
# Apaga esse cache e poe no lugar um arquivo VAZIO que nao pode ser
# escrito nem apagado (negacao pra Todos — e negacao ganha de permissao,
# inclusive pra administrador). O canal continua existindo; so nao entra
# conteudo nenhum nele.
#
# POR QUE NAO TRANCAR A PASTA INTEIRA
# Porque o AnyDesk PRECISA escrever ali o tempo todo: user.conf e
# service.conf guardam as suas configuracoes e o ID da maquina. Trancar
# tudo nao tiraria so a propaganda — tiraria o programa. Uma tranca de
# um arquivo so e a diferenca entre "sem anuncio" e "sem funcionar".
#
# QUANDO REPETIR
# Depois de REINSTALAR ou atualizar o AnyDesk: o instalador recria a
# pasta e o arquivo volta a poder nascer. Rode isto de novo (ele avisa
# quando ja esta trancado, e nao faz nada).
#
# PRA DESFAZER: rode com -Desfazer.

param([switch]$Desfazer)

$ErrorActionPreference = "Continue"

$TODOS = "*S-1-1-0"
$CACHE = Join-Path $env:APPDATA "AnyDesk\cache"
$ALVO = Join-Path $CACHE "anymessage.cache"

function Diga($t, $cor = "Gray") { Write-Host "  $t" -ForegroundColor $cor }

Write-Host ""
Write-Host "  ANYDESK SEM PROPAGANDA" -ForegroundColor Cyan
Write-Host "  ======================" -ForegroundColor Cyan
Write-Host ""
Diga "Maquina: $env:COMPUTERNAME   Usuario: $env:USERNAME"
Diga "Arquivo: $ALVO"
Write-Host ""

if ($Desfazer) {
    if (-not (Test-Path $ALVO)) {
        Diga "Nao existe nada pra desfazer." "Yellow"
        exit 0
    }
    icacls $ALVO /remove:d $TODOS | Out-Null
    icacls $ALVO /inheritance:e | Out-Null
    Remove-Item $ALVO -Force -ErrorAction SilentlyContinue
    if (Test-Path $ALVO) {
        Diga "Nao consegui liberar. Feche o AnyDesk e rode de novo." "Red"
        exit 1
    }
    Diga "Liberado. O AnyDesk volta a receber as mensagens (e os anuncios)." "Green"
    exit 0
}

# Ja esta trancado? (arquivo vazio que nao aceita escrita)
if (Test-Path $ALVO) {
    $tamanho = (Get-Item $ALVO).Length
    $trancado = $false
    try { [IO.File]::OpenWrite($ALVO).Close() } catch { $trancado = $true }
    if ($trancado -and $tamanho -eq 0) {
        Diga "Ja esta trancado (vazio e sem permissao de escrita). Nada a fazer." "Green"
        exit 0
    }
    Diga "Achei o cache com $tamanho byte(s) — e por ele que a propaganda entra."
    try {
        if ($trancado) { icacls $ALVO /remove:d $TODOS | Out-Null }
        Remove-Item $ALVO -Force -ErrorAction Stop
        Diga "Apagado." "Green"
    } catch {
        Diga "NAO consegui apagar: $($_.Exception.Message)" "Red"
        Diga "Feche o AnyDesk (icone ao lado do relogio > Sair) e rode de novo." "Yellow"
        exit 1
    }
} else {
    if (-not (Test-Path $CACHE)) {
        New-Item -ItemType Directory -Path $CACHE -Force | Out-Null
        Diga "A pasta de cache nem existia — criei vazia."
    }
    Diga "O cache ainda nao tinha nascido. Melhor ainda: tranco antes."
}

New-Item -ItemType File -Path $ALVO -Force | Out-Null
icacls $ALVO /inheritance:r | Out-Null
icacls $ALVO /grant "${TODOS}:(R)" | Out-Null
icacls $ALVO /deny "${TODOS}:(W,DE)" | Out-Null

# Prova, nao promessa: tenta escrever e apagar de verdade.
$escreveu = $true
try { Set-Content -Path $ALVO -Value "propaganda" -ErrorAction Stop } catch { $escreveu = $false }
$apagou = $true
try { Remove-Item $ALVO -Force -ErrorAction Stop } catch { $apagou = $false }

Write-Host ""
if ($escreveu -or $apagou) {
    Diga "ATENCAO: a tranca NAO pegou (escrita=$escreveu, exclusao=$apagou)." "Red"
    exit 1
}
Diga "Trancado: o arquivo existe, esta vazio, e nao aceita escrita nem exclusao." "Green"
Write-Host ""
Diga "Abra o AnyDesk e confira. Se ainda aparecer anuncio, me avise: a" "Cyan"
Diga "propaganda vem por outro caminho e eu procuro qual." "Cyan"
Diga "Repita isto depois de reinstalar ou atualizar o AnyDesk." "Cyan"
Diga "Pra desfazer: desbloquear_propaganda_anydesk.bat, ao lado deste." "DarkGray"
