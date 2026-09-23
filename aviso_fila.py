"""
Aviso de fila parada — o sistema para de esperar que alguém abra a tela.

Nasceu em 23/09/2026: o vigia do PC do RIP deu o último sinal às 15:03 e
isso só foi notado às 19:22, quando o painel de agentes foi aberto. Naquele
dia não custou material — as três filas estavam vazias —, mas o buraco
ficou à mostra: quem descobre o problema é a tela, e a tela só fala com
quem a abre. Quatro horas é tempo de sobra pra um dia inteiro de produção
esperar por nada.

O QUE ELE MEDE É O FATO, NÃO A CAUSA
Arquivo parado na fila há tempo demais. Serve igual pro vigia derrubado, pro
OneDrive travado do outro lado e pra hot folder que sumiu — sem precisar
saber qual dos três foi. Em condição normal a fila esvazia em segundos.
Fila vazia não avisa nada: RIP fora do ar sem ninguém esperando material é
assunto de manutenção, não urgência de produção.

QUEM CHAMA
A passada do `rasterlink_hotfolder`, que já roda de minuto em minuto neste
PC pela DOCAN — então o aviso passa a existir sem tarefa nova no Agendador.
No PC do RIP o projeto inteiro não existe (lá só mora aquele módulo), então
a chamada de lá não acha este arquivo e segue em frente: por isso o gancho
é import tardio dentro de try/except.

NÃO REPETE O AVISO A CADA MINUTO
Alarme que toca sessenta vezes por hora é alarme que se aprende a ignorar —
e aí o de verdade passa batido. Uma vez por hora por máquina, e o relógio
zera quando a fila anda.
"""
import datetime
import json

import caminhos

# Mesma fronteira que a tela de envio usa pra pintar o aviso de fila parada
# (envio_impressao.fila_parada). Uma régua só: dois números diferentes pro
# mesmo fato fariam a tela e a notificação discordarem na frente dele.
MINUTOS_PARA_AVISAR = 20
MINUTOS_ENTRE_AVISOS = 60

NOME_ESTADO = "_aviso_fila.json"
TITULO = "A fila das máquinas parou"


def caminho_estado():
    # Lido na hora do uso, nunca guardado em constante de módulo: é assim
    # que o teste consegue apontar pra tmp_path em vez da pasta de verdade.
    return caminhos.PASTA_PROGRAMA / NOME_ESTADO


def _ler_estado():
    try:
        dados = json.loads(caminho_estado().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return dados if isinstance(dados, dict) else {}


def _gravar_estado(estado):
    try:
        caminho_estado().write_text(
            json.dumps(estado, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        # Não poder gravar o "já avisei" é chato (vai repetir), mas nunca
        # pode impedir o aviso nem derrubar a passada do vigia.
        pass


def _cabe_novo_aviso(avisado_em, agora):
    if not avisado_em:
        return True
    try:
        quando = datetime.datetime.fromisoformat(avisado_em)
    except (TypeError, ValueError):
        return True
    # Relógio pra trás (ou estado de outra máquina) não pode calar o aviso.
    if quando > agora:
        return True
    return (agora - quando).total_seconds() / 60 >= MINUTOS_ENTRE_AVISOS


def mensagem(paradas):
    """
    O texto da notificação. Cada linha diz o que foi MEDIDO e o que aquilo
    significa — a mesma regra dos textos da tela de envio, porque quem lê
    isso está no meio de outra coisa e não vai lembrar da régua de cabeça.
    """
    from envio_impressao import _quanto_faz

    linhas = [
        f"{maquina}: {quantos} arquivo(s) esperando há {_quanto_faz(minutos)}."
        for maquina, (quantos, minutos) in sorted(paradas.items())
    ]
    linhas.append(
        "O envio daqui funcionou — o que não está acontecendo é a máquina "
        "puxar. Confira o PC do RIP: vigia rodando e OneDrive sincronizando.")
    return "\n".join(linhas)


def conferir(agora=None, notificar=None, paradas=None):
    """
    Uma passada: olha as filas e notifica se tem coisa parada.

    Devolve o dicionário do que foi avisado agora ({} quando não avisou
    nada), pra quem chamar poder registrar no log.
    """
    agora = agora or datetime.datetime.now()

    if paradas is None:
        from envio_impressao import fila_parada
        paradas = fila_parada(minutos=MINUTOS_PARA_AVISAR, agora=agora)

    if not paradas:
        # A fila andou: esquece o que já foi avisado, pra que o PRÓXIMO
        # problema seja anunciado na hora em vez de esperar a hora fechar.
        if _ler_estado():
            _gravar_estado({})
        return {}

    estado = _ler_estado()
    if not any(_cabe_novo_aviso(estado.get(maquina), agora) for maquina in paradas):
        return {}

    if notificar is None:
        from monitor_onedrive import notificar_windows
        notificar = notificar_windows

    # Se a notificação falhar, o estado NÃO é gravado de propósito: ninguém
    # foi avisado, então a próxima passada tem que tentar de novo.
    notificar(mensagem(paradas), titulo=TITULO)

    estado.update({maquina: agora.isoformat(timespec="seconds") for maquina in paradas})
    _gravar_estado(estado)
    return paradas
