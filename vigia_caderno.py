"""
Vigia do caderno de arte — o cliente mexeu no Canva, e ele fica sabendo.

Pedido do usuário (2026-10-03): *"o vigia está sempre passando; pra saber se
houve mudança no caderno, de qualquer cliente, deve ser um padrão conferir se
o caderno tem coisa nova; se tiver link novo deve baixar e gerar um aviso pra
eu saber"*. O caderno do Canva é documento VIVO: a agência acrescenta peça,
troca a arte de uma ficha e corrige medida depois de a gente já ter recebido
o lote — e até aqui a única forma de descobrir era abrir o caderno na mão.

QUEM É VIGIADO SE CADASTRA SOZINHO
Todo cliente de Recebimento de Artes que já recebeu um caderno do Canva por
aqui: o link está no `caderno.json` que o recebimento guarda em
`_sistema/recebidos/`. É o mesmo princípio do resto do sistema — a pasta é o
cadastro, nenhum nome de cliente no código. Vale o caderno MAIS RECENTE do
cliente: terminado o trabalho, a pasta sai de Recebimento de Artes e o vigia
para junto.

O QUE É "COISA NOVA"
  - **ficha nova** — peça que não existia no caderno;
  - **link novo** — ficha que ganhou link, ou cuja arte foi TROCADA por outro
    arquivo (o id do Drive muda);
  - **ficha mexida** — medida, material ou quantidade diferente do que estava
    escrito quando a arte foi recebida. Não baixa nada (o arquivo é o mesmo),
    mas é o aviso que mais vale: produzir no tamanho velho é material perdido.

A conta é por FICHA (seção + nome), nunca por número de página: uma página
nova no meio empurra a numeração de todas as seguintes, e o vigia anunciaria
o caderno inteiro como novidade.

O QUE ELE FAZ E O QUE NÃO FAZ
Baixa o arquivo novo pra espera LOCAL (fora do OneDrive, como todo o
recebimento: arte que ele ainda pode recusar não sincroniza) e avisa. **Não
arquiva** — quem decide nome, medida e material é ele, na tela de dois passos.

NÃO LÊ O CANVA A CADA MINUTO
A passada do checklist é de minuto em minuto; a leitura do caderno é a cada
MINUTOS_ENTRE_LEITURAS por cliente, porque cada leitura puxa ~1,4 MB (a
página de visualização inteira). O Canva não dá ETag nem Last-Modified
(sondado em 02/10: HEAD volta sem os dois), então não há como perguntar
"mudou?" mais barato — mas o `version` do rascunho, que vem dentro dela,
responde na hora se vale a pena comparar ficha por ficha.

O AVISO É UM SÓ POR PASSADA
Novidade achada entra em 'pendentes' no estado do cliente e sai do estado
quando a notificação do Windows passa. Se avisar falhar, o que já foi baixado
não é baixado de novo — e o aviso tenta na passada seguinte, junto com o que
tiver aparecido. Alarme repetido é alarme que se aprende a ignorar
(a mesma régua do `aviso_fila`).
"""
import datetime
import json
import pathlib

import caminhos
import clientes

NOME_ESTADO = "caderno_vigiado.json"
NOME_LOG = "vigia_caderno.log"
# A arte nova espera aqui dentro de caminhos.PASTA_RECEBENDO, uma pasta por
# cliente. Começa com '_' de propósito: a tela que lê uma pasta de artes
# pula pastas assim, então a espera nunca se lê a si mesma.
PASTA_NOVIDADES = "_novidades"

MINUTOS_ENTRE_LEITURAS = 15
TITULO_AVISO = "O caderno de arte mudou"
LINHAS_NO_AVISO = 8
# O que o vigia compara numa ficha já conhecida.
CAMPOS = ("medidas", "medidas_sangria", "sangria", "material", "quantidade", "acabamento", "obs")


def arquivo_estado(cliente):
    return cliente.pasta_sistema / NOME_ESTADO


def arquivo_log(cliente):
    return cliente.pasta_sistema / NOME_LOG


def pasta_das_novidades(cliente, agora=None):
    """Onde a arte nova espera: local, fora do OneDrive, uma pasta por leitura."""
    agora = agora or datetime.datetime.now()
    return (caminhos.PASTA_RECEBENDO / PASTA_NOVIDADES / cliente.nome
            / agora.strftime("%Y-%m-%d %H%M%S"))


def _log(cliente, nivel, texto):
    try:
        caminho = arquivo_log(cliente)
        caminho.parent.mkdir(parents=True, exist_ok=True)
        with open(caminho, "a", encoding="utf-8") as f:
            f.write("[%s] %-5s %s\n" % (datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), nivel, texto))
    except OSError:
        pass        # log que não grava nunca derruba a passada


# ----------------------------------------------------------------------
# O que se compara de uma leitura pra outra
# ----------------------------------------------------------------------

def _id_do_link(link):
    """O id do Drive, quando houver — o mesmo arquivo com outra query não é link novo."""
    import drive_artes
    return drive_artes.id_do_link(link) or (link or "").strip()


def _chave_da_ficha(ficha, contagem):
    """
    'LONAS|LONA A|1' — seção, nome e a ordem entre homônimas (o caderno da
    LOJINHA tem 15 fichas chamadas 'PLACA PS'). Não entra o número da página:
    página nova no meio empurra todas as outras.
    """
    base = "%s|%s" % ((ficha.get("secao") or "").strip().upper(),
                      " ".join((ficha.get("nome") or "SEM NOME").split()).upper())
    contagem[base] = contagem.get(base, 0) + 1
    return "%s|%d" % (base, contagem[base])


def resumo(caderno):
    """
    O caderno reduzido ao que o vigia compara: por ficha, os campos da ficha e
    os ids dos arquivos que ela aponta. É isto que fica no estado — guardar o
    caderno inteiro faria o estado crescer sem precisar.
    """
    fichas, contagem = {}, {}
    for f in (caderno or {}).get("fichas") or []:
        fichas[_chave_da_ficha(f, contagem)] = {
            "pagina": f.get("pagina"),
            "nome": f.get("nome") or "",
            "secao": f.get("secao") or "",
            "campos": {c: f.get(c) for c in CAMPOS},
            "links": [_id_do_link(l) for l in f.get("links") or []],
        }
    return {"design_id": (caderno or {}).get("design_id") or "",
            "titulo": (caderno or {}).get("titulo") or "",
            "link": (caderno or {}).get("link") or "",
            "paginas": (caderno or {}).get("paginas"),
            "versao": (caderno or {}).get("versao"),
            "fichas": fichas}


def novidades(antes, agora):
    """
    O que o caderno ganhou desde a leitura anterior. Cada item diz o TIPO
    ('ficha nova', 'link novo', 'ficha mexida'), a ficha e, quando há arquivo
    pra pegar, os links novos.

    Link que já existia em OUTRA ficha não conta como novo (as três fichas dos
    QUADROS apontam o mesmo PDF): o que importa é arquivo que nunca foi visto.
    """
    de_antes = {l for f in (antes or {}).get("fichas", {}).values() for l in f.get("links") or []}
    achados = []
    for chave, ficha in (agora or {}).get("fichas", {}).items():
        velha = (antes or {}).get("fichas", {}).get(chave)
        links_novos = [l for l in ficha.get("links") or [] if l not in de_antes]
        item = {"chave": chave, "pagina": ficha.get("pagina"), "nome": ficha.get("nome"),
                "secao": ficha.get("secao"), "links": links_novos, "mudancas": []}
        if velha is None:
            achados.append(dict(item, tipo="ficha nova"))
            continue
        if links_novos:
            achados.append(dict(item, tipo="link novo"))
            continue
        mudou = [(c, velha.get("campos", {}).get(c), ficha["campos"].get(c))
                 for c in CAMPOS if velha.get("campos", {}).get(c) != ficha["campos"].get(c)]
        if mudou:
            achados.append(dict(item, tipo="ficha mexida", mudancas=mudou))
    return achados


def _pagina_e_nome(item):
    pagina = "p.%02d " % item["pagina"] if item.get("pagina") else ""
    return "%s%s" % (pagina, item.get("nome") or "sem nome")


def linha_da_novidade(item):
    """Uma novidade em uma linha, do jeito que ele lê no aviso e no log."""
    if item["tipo"] == "ficha mexida":
        mudancas = "; ".join("%s: %s -> %s" % (c, (de or "—"), (para or "—"))
                             for c, de, para in item["mudancas"])
        return "%s mudou no caderno (%s)" % (_pagina_e_nome(item), mudancas)
    if item["tipo"] == "link novo":
        return "%s: a arte foi trocada no caderno" % _pagina_e_nome(item)
    return "%s: peça nova no caderno" % _pagina_e_nome(item)


# ----------------------------------------------------------------------
# Baixar o que é novo
# ----------------------------------------------------------------------

def baixar_novas(caderno, achados, pasta, sessao=None, abrir_origem=None):
    """
    Os arquivos dos links novos, na pasta de espera. Devolve
    (caminhos baixados, motivos do que não veio).

    Reaproveita a OrigemCaderno — a mesma que a tela usa —, mas com um caderno
    REDUZIDO às fichas novas: assim ela resolve só esses links, e não os 60 do
    caderno inteiro a cada novidade.
    """
    import origem_artes as oa

    # A ficha de verdade de cada novidade, pela MESMA chave do resumo —
    # comparar por página e nome erraria onde há homônimas.
    contagem, por_chave = {}, {}
    for ficha in caderno.get("fichas") or []:
        por_chave[_chave_da_ficha(ficha, contagem)] = ficha
    querem_arquivo = [por_chave[i["chave"]] for i in achados
                      if i["links"] and i["chave"] in por_chave]
    if not querem_arquivo:
        return [], []

    reduzido = dict(caderno, fichas=querem_arquivo)
    abrir = abrir_origem or (lambda c: oa.OrigemCaderno(caderno.get("link") or "", sessao=sessao,
                                                        ler_caderno=lambda: c))
    origem = abrir(reduzido)
    baixados = []
    for arquivo in origem.listar():
        try:
            baixados.append(origem.baixar(arquivo, pasta))
        except Exception as e:   # noqa: BLE001 — o aviso vale mesmo sem o arquivo
            origem.ignorados.append((arquivo.nome, str(e)))
    return baixados, list(origem.ignorados)


# ----------------------------------------------------------------------
# A passada
# ----------------------------------------------------------------------

def _ler_estado(cliente):
    try:
        dados = json.loads(arquivo_estado(cliente).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return dados if isinstance(dados, dict) else {}


def _gravar_estado(cliente, estado):
    try:
        caminho = arquivo_estado(cliente)
        caminho.parent.mkdir(parents=True, exist_ok=True)
        caminho.write_text(json.dumps(estado, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError as e:
        _log(cliente, "erro", "não consegui gravar o estado: %s" % e)


def _passou_o_intervalo(estado, agora, minutos):
    quando = estado.get("conferido_em")
    if not quando:
        return True
    try:
        anterior = datetime.datetime.fromisoformat(quando)
    except (TypeError, ValueError):
        return True
    if anterior > agora:        # relógio pra trás não pode calar o vigia
        return True
    return (agora - anterior).total_seconds() / 60 >= minutos


def caderno_do_cliente(cliente):
    """
    O caderno do Canva que este cliente recebeu por último, ou None. É o
    `caderno.json` que o arquivamento guarda — nenhum cadastro à parte.
    """
    import relatorio_recebimento
    caderno = relatorio_recebimento.caderno_guardado(cliente.pasta)
    if not caderno:
        return None
    import caderno_canva
    return caderno if caderno_canva.e_link_do_canva(caderno.get("link") or "") else None


def conferir_cliente(cliente, agora=None, ler=None, sessao=None, forcar=False,
                     minutos=MINUTOS_ENTRE_LEITURAS, baixar=None):
    """
    Uma conferida no caderno de UM cliente. Devolve a lista de novidades
    achadas AGORA ([] quando nada mudou ou quando ainda não deu a hora de
    ler). Nunca levanta: falha de um cliente é linha no log dele.
    """
    agora = agora or datetime.datetime.now()
    try:
        guardado = caderno_do_cliente(cliente)
        if not guardado:
            return []
        estado = _ler_estado(cliente)
        if not (forcar or _passou_o_intervalo(estado, agora, minutos)):
            return []

        import caderno_canva
        try:
            caderno = (ler or caderno_canva.ler)(guardado["link"], sessao)
        except Exception as e:   # noqa: BLE001 — Canva fora do ar, link fechado, rede
            _log(cliente, "warn", "não consegui ler o caderno: %s" % e)
            return []

        agora_resumo = resumo(caderno)
        estado["conferido_em"] = agora.strftime("%Y-%m-%dT%H:%M:%S")
        # Da primeira vez a régua é o caderno COMO ESTAVA no recebimento:
        # o que a agência acrescentou desde então é novidade de verdade, que
        # ele ainda não viu.
        antes = estado.get("resumo") or resumo(guardado)
        achados = novidades(antes, agora_resumo)
        if not achados:
            estado["resumo"] = agora_resumo
            _gravar_estado(cliente, estado)
            return []

        # Novidade sem arquivo novo (medida mexida, ou link que outra ficha já
        # apontava) não abre pasta de espera nenhuma.
        pasta = pasta_das_novidades(cliente, agora)
        baixados, ignorados = ((baixar or baixar_novas)(caderno, achados, pasta, sessao)
                               if any(i["links"] for i in achados) else ([], []))
        for item in achados:
            _log(cliente, "ok", linha_da_novidade(item))
        for rotulo, motivo in ignorados:
            _log(cliente, "warn", "não baixei %s: %s" % (rotulo, motivo))
        if baixados:
            _log(cliente, "ok", "%d arquivo(s) novo(s) em %s" % (len(baixados), pasta))

        estado["resumo"] = agora_resumo
        estado["pendentes"] = (estado.get("pendentes") or []) + [
            dict(item, quando=agora.strftime("%Y-%m-%dT%H:%M:%S"),
                 pasta=str(pasta) if item["links"] and baixados else "") for item in achados]
        _gravar_estado(cliente, estado)
        return achados
    except Exception as e:       # noqa: BLE001 — um cliente nunca derruba os outros
        _log(cliente, "erro", "falhou ao conferir: %s: %s" % (type(e).__name__, e))
        return []


def mensagem(pendentes):
    """
    O texto da notificação: cada linha diz o cliente, a peça e o que mudou —
    quem lê está no meio de outra coisa e não vai abrir nada pra entender.
    """
    linhas, pastas = [], []
    for nome, itens in sorted(pendentes.items()):
        for item in itens:
            linhas.append("%s — %s" % (nome, linha_da_novidade(item)))
            if item.get("pasta") and item["pasta"] not in pastas:
                pastas.append(item["pasta"])
    # Caderno reorganizado inteiro daria uma notificação de sessenta linhas,
    # que ninguém lê: as primeiras e a conta do resto.
    if len(linhas) > LINHAS_NO_AVISO:
        sobraram = len(linhas) - LINHAS_NO_AVISO
        linhas = linhas[:LINHAS_NO_AVISO] + ["... e mais %d mudança(s) — veja o log do cliente." % sobraram]
    if pastas:
        linhas.append("A arte nova já foi baixada em %s — receba pela tela Receber artes."
                      % (pastas[0] if len(pastas) == 1 else "%d pastas da espera" % len(pastas)))
    else:
        linhas.append("Nada foi baixado: confira o caderno antes de produzir.")
    return "\n".join(linhas)


def conferir(agora=None, notificar=None, raiz=None, ler=None, sessao=None, forcar=False,
             minutos=MINUTOS_ENTRE_LEITURAS, baixar=None):
    """
    A passada: confere o caderno de todos os clientes e avisa UMA vez o que
    apareceu (inclusive o que ficou pendente de avisos anteriores).

    Devolve {cliente: [novidades avisadas]} — {} quando não havia o que dizer.
    """
    agora = agora or datetime.datetime.now()
    lista = clientes.listar(raiz)
    for cliente in lista:
        conferir_cliente(cliente, agora, ler=ler, sessao=sessao, forcar=forcar,
                         minutos=minutos, baixar=baixar)

    pendentes, estados = {}, {}
    for cliente in lista:
        estado = _ler_estado(cliente)
        if estado.get("pendentes"):
            pendentes[cliente.nome] = estado["pendentes"]
            estados[cliente.nome] = (cliente, estado)
    if not pendentes:
        return {}

    if notificar is None:
        from monitor_onedrive import notificar_windows
        notificar = notificar_windows
    try:
        notificar(mensagem(pendentes), titulo=TITULO_AVISO)
    except Exception as e:       # noqa: BLE001 — sem aviso, fica pendente pra próxima
        for cliente, _ in estados.values():
            _log(cliente, "warn", "não consegui avisar no Windows: %s" % e)
        return {}

    # Avisado: sai da fila de pendentes. O que foi baixado fica onde está.
    for cliente, estado in estados.values():
        estado["pendentes"] = []
        estado["avisado_em"] = agora.strftime("%Y-%m-%dT%H:%M:%S")
        _gravar_estado(cliente, estado)
    return pendentes


def ultima_acao(agora=None):
    """Uma linha por cliente vigiado, pro painel de agentes."""
    agora = agora or datetime.datetime.now()
    partes = []
    for cliente in clientes.listar():
        estado = _ler_estado(cliente)
        if not estado.get("conferido_em") and not caderno_do_cliente(cliente):
            continue
        quando = estado.get("conferido_em") or ""
        try:
            lido = datetime.datetime.fromisoformat(quando)
            faz = "há %d min" % max(0, int((agora - lido).total_seconds() // 60))
        except (TypeError, ValueError):
            faz = "ainda não conferido"
        fichas = len((estado.get("resumo") or {}).get("fichas") or {})
        pendentes = len(estado.get("pendentes") or [])
        partes.append("%s: caderno conferido %s%s%s" % (
            cliente.nome, faz, " · %d fichas" % fichas if fichas else "",
            " · %d novidade(s) a avisar" % pendentes if pendentes else ""))
    return "  ·  ".join(partes) or "nenhum cliente com caderno do Canva recebido por aqui"


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Vigia do caderno de arte no Canva (uma passada).")
    parser.add_argument("--uma-vez", action="store_true", help="uma passada e sai (padrão)")
    parser.add_argument("--forcar", action="store_true", help="lê o caderno mesmo sem dar a hora")
    parser.add_argument("--sem-aviso", action="store_true", help="não notifica; só escreve o que achou")
    args = parser.parse_args()

    achados = conferir(forcar=args.forcar, notificar=(lambda *a, **k: None) if args.sem_aviso else None)
    if not achados:
        print("sem novidade no caderno")
    for nome, itens in achados.items():
        for item in itens:
            print("%s — %s" % (nome, linha_da_novidade(item)))
