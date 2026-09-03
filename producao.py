"""
Organiza a pasta "PRODUCAO" de cada cliente (dentro de EVENTOS no
OneDrive) automaticamente: garante que sempre existam as 4 subpastas
de trabalho (LONA, ADESIVO, CORTE, COMPOSTOS, cada uma com seu
Prontos e NADA MAIS dentro) e distribui os arquivos soltos que caem
direto na raiz da PRODUCAO pra subpasta certa, usando a MESMA
detecção de categoria já usada pra gerar a OS (dimensoes.
identificar_categoria/identificar_categoria_extra).

Regra (pedido do usuário, 2026-09-03):
  - Lonas: só lona pura, nada mais.
  - Adesivos: só adesivo puro, nada mais.
  - Cortes: só quando for corte DIRETO — PVC/PS/MDF/ACRÍLICO sem
    nenhuma impressão envolvida (nome sem "IMPRESSO" e sem gatilho de
    material composto).
  - Compostos: todo o resto — material composto de verdade (ex: "PS
    ADESIVADO", "PVC ADESIVADO"), PVC/PS/MDF/ACRÍLICO "IMPRESSO"
    (imprime E corta, mesmo sem ser um "adesivo" formal — ex: "PS
    IMPRESSO RECORTE"), e também QUALQUER arquivo cuja categoria não
    seja reconhecida — nunca fica solto sem classificar, por segurança
    (pedido do usuário, 2026-09-03: "o que não reconhecer joga em
    Compostos").

Decisão do usuário (2026-09-03): nunca decide sozinho quando um item
está PRONTO (impresso/cortado) — isso continua manual (ou, no caso de
impressão, pelo cruzamento com o RIP — ver rasterlink.py). Essa
organização aqui só resolve "onde esse arquivo começa a vida", nunca
move pra dentro de um Prontos.
"""
import pathlib

from dimensoes import contem_palavra, identificar_categoria, identificar_categoria_extra

NOME_PASTA_PRODUCAO = "PRODUCAO"
NOME_SUBPASTA_PRONTOS = "Prontos"

PASTA_LONA = "LONAS"
PASTA_ADESIVO = "ADESIVOS"
PASTA_CORTE = "CORTES"
PASTA_COMPOSTOS = "COMPOSTOS"

_SUBPASTAS_TRABALHO = (PASTA_LONA, PASTA_ADESIVO, PASTA_CORTE, PASTA_COMPOSTOS)

# Categorias que só têm processo de corte (router/CNC) — nunca
# impressão própria, a menos que o nome do arquivo diga o contrário
# (ver _pasta_de_trabalho_para).
_CATEGORIAS_CORTE = {"PVC", "PS", "MDF", "ACRILICO"}

# Palavra que, aparecendo no nome de uma categoria de corte, sinaliza
# que essa peça também passa por impressão — nesse caso vai pra
# COMPOSTOS, nunca pra CORTE, mesmo sem ser tecnicamente um "material
# composto" (que é o gatilho ADESIVADO, resolvido à parte por
# identificar_categoria_extra).
_PALAVRA_IMPRESSO = "IMPRESSO"


def _achar_pastas_producao(raiz_eventos):
    """
    Acha toda pasta cujo nome COMEÇA com 'PRODUCAO', um nível abaixo
    de 'raiz_eventos' — não só o nome exato. Achado ao vivo (2026-09-
    03, pasta real da FESTA ALEMÃ): quando a produção é dividida por
    data, aparece mais de uma pasta de produção pro MESMO cliente
    (ex: "PRODUCAO", "PRODUCAO 01_09", "PRODUCAO 02_09" coexistindo)
    — um match exato ignoraria silenciosamente as datadas.
    """
    raiz = pathlib.Path(raiz_eventos)
    if not raiz.is_dir():
        return []
    return sorted(
        p for p in raiz.glob(f"*/{NOME_PASTA_PRODUCAO}*")
        if p.is_dir() and p.name.upper().startswith(NOME_PASTA_PRODUCAO)
    )


def _rotulo_pasta_producao(pasta_producao):
    """
    Rótulo pra identificar a pasta num relatório/resultado — só o nome
    do cliente quando é a pasta "PRODUCAO" simples (caso comum), ou
    "CLIENTE — PRODUCAO 01_09" quando é uma das datadas, pra nunca
    duas pastas do mesmo cliente colidirem na mesma chave.
    """
    nome_cliente = pasta_producao.parent.name
    if pasta_producao.name.upper() == NOME_PASTA_PRODUCAO:
        return nome_cliente
    return f"{nome_cliente} — {pasta_producao.name}"


def garantir_estrutura_producao(pasta_producao):
    """Cria as 4 subpastas de trabalho (+ Prontos de cada) se ainda não existirem. Idempotente."""
    pasta = pathlib.Path(pasta_producao)
    for nome in _SUBPASTAS_TRABALHO:
        (pasta / nome / NOME_SUBPASTA_PRONTOS).mkdir(parents=True, exist_ok=True)


def _pasta_de_trabalho_para(nome_arquivo, materiais, sinonimos_categoria=None, materiais_compostos=None):
    """
    Devolve o nome da subpasta de trabalho certa pra esse arquivo
    ('Lonas'/'Adesivos'/'Cortes'/'Compostos') — nunca None: um
    arquivo cuja categoria não foi reconhecida cai em Compostos junto
    (pedido do usuário, 2026-09-03), pra nunca ficar solto sem
    ninguém perceber.
    """
    nome_upper = nome_arquivo.upper()

    categoria, _ = identificar_categoria(nome_upper, materiais, sinonimos_categoria)
    if categoria is None:
        return PASTA_COMPOSTOS

    categoria_extra = identificar_categoria_extra(nome_upper, materiais, materiais_compostos)

    if categoria == "LONA":
        return PASTA_COMPOSTOS if categoria_extra else PASTA_LONA
    if categoria == "ADESIVO":
        return PASTA_COMPOSTOS if categoria_extra else PASTA_ADESIVO

    if categoria in _CATEGORIAS_CORTE:
        eh_corte_puro = categoria_extra is None and not contem_palavra(nome_upper, _PALAVRA_IMPRESSO)
        return PASTA_CORTE if eh_corte_puro else PASTA_COMPOSTOS

    # categoria reconhecida mas fora do que sabemos rotear (ex: uma
    # categoria nova cadastrada no config.json que este mapa ainda não
    # conhece) — mais seguro cair em COMPOSTOS pra alguém conferir do
    # que ficar solto sem ninguém perceber.
    return PASTA_COMPOSTOS


def organizar_pasta_producao(pasta_producao, config):
    """
    Garante a estrutura e move todo arquivo solto direto na raiz da
    PRODUCAO (nunca mexe no que já está dentro de uma subpasta de
    trabalho ou de Prontos — só olha o primeiro nível) pra subpasta
    certa (categoria não reconhecida vai pra Compostos também — ver
    _pasta_de_trabalho_para). Retorna um dict com o que foi movido e
    o que ficou parado por colisão de nome.
    """
    pasta = pathlib.Path(pasta_producao)
    garantir_estrutura_producao(pasta)

    materiais = config["materiais"]
    sinonimos_categoria = config.get("sinonimos_categoria", {})
    materiais_compostos = config.get("materiais_compostos", {})

    resultado = {"movidos": [], "colisoes": []}

    for arquivo in [f for f in pasta.iterdir() if f.is_file()]:
        pasta_destino = _pasta_de_trabalho_para(
            arquivo.name, materiais, sinonimos_categoria, materiais_compostos,
        )
        destino = pasta / pasta_destino / arquivo.name
        if destino.exists():
            resultado["colisoes"].append(arquivo.name)
            continue
        arquivo.rename(destino)
        resultado["movidos"].append((arquivo.name, pasta_destino))

    return resultado


def gerar_relatorio_pendencias(raiz_eventos):
    """
    Conta, por cliente, quantos arquivos ainda estão pendentes (soltos
    dentro de IMPRESSAO/CORTE/COMPOSTOS, fora do respectivo Prontos)
    — pra responder "qual cliente ainda tem coisa parada", não só "tem
    algo parado em algum lugar" (pedido do usuário, 2026-09-03).

    Devolve {nome_cliente: {"IMPRESSAO": N, "CORTE": N, "COMPOSTOS": N}}
    só com clientes que têm pelo menos 1 pendência — quem já está tudo
    em Prontos não aparece. Vazio (nunca estoura erro) se a raiz não
    existir.
    """
    pendencias = {}
    for pasta_producao in _achar_pastas_producao(raiz_eventos):
        rotulo = _rotulo_pasta_producao(pasta_producao)

        contagem = {}
        for subpasta in _SUBPASTAS_TRABALHO:
            caminho_subpasta = pasta_producao / subpasta
            if not caminho_subpasta.is_dir():
                continue
            n = sum(1 for f in caminho_subpasta.iterdir() if f.is_file())
            if n > 0:
                contagem[subpasta] = n

        if contagem:
            pendencias[rotulo] = contagem

    return pendencias


def formatar_relatorio_pendencias(pendencias):
    """Texto pronto pra notificação/relatório a partir do que gerar_relatorio_pendencias devolveu."""
    if not pendencias:
        return "Nenhuma pendência — tudo organizado em Prontos."

    linhas = []
    for cliente, contagem in pendencias.items():
        linhas.append(cliente)
        for subpasta, n in contagem.items():
            linhas.append(f"  {subpasta}: {n} pendente{'s' if n != 1 else ''}")
    return "\n".join(linhas)


def abrir_relatorio_pendencias(raiz_eventos):
    """Gera o relatório de pendências por cliente, salva num arquivo temporário e abre no Bloco de Notas."""
    import subprocess
    import tempfile
    from datetime import datetime

    texto = formatar_relatorio_pendencias(gerar_relatorio_pendencias(raiz_eventos))
    caminho = pathlib.Path(tempfile.gettempdir()) / f"pendencias_producao_{datetime.now():%Y%m%d_%H%M%S}.txt"
    caminho.write_text(texto, encoding="utf-8")
    subprocess.Popen(["notepad.exe", str(caminho)])
    return caminho


def varrer_e_organizar_todas(raiz_eventos, config):
    """
    Acha toda pasta de produção (nome começando com 'PRODUCAO') um
    nível abaixo de 'raiz_eventos' — inclusive quando um cliente tem
    mais de uma, dividida por data (ex: "PRODUCAO 01_09", "PRODUCAO
    02_09" — ver _achar_pastas_producao) — e organiza cada uma. É a
    varredura de "arrumar tudo que ficou bagunçado enquanto o
    computador estava desligado", chamada ao iniciar o monitor (ver
    monitor_onedrive.rodar_com_bandeja).

    Devolve vazio (nunca estoura erro) se 'raiz_eventos' não existir —
    a organização é um extra best-effort, não pode travar o monitor.
    """
    resultado_por_pasta = {}
    for pasta_producao in _achar_pastas_producao(raiz_eventos):
        rotulo = _rotulo_pasta_producao(pasta_producao)
        resultado_por_pasta[rotulo] = organizar_pasta_producao(pasta_producao, config)

    return resultado_por_pasta
