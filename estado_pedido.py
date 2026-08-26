"""
Memória de um pedido em andamento: quais arquivos já foram processados
numa pasta de cliente, guardada dentro da própria pasta
(estado_pedido.json). É o que permite jogar a pasta de entrada inteira
de novo — mesmo vindo misturada, com o que já foi mandado antes junto
com o que é novo — e o sistema reconhecer sozinho, pelo nome do
arquivo, só o que ainda não foi processado. Nunca reprocessa, nunca
recalcula m² do que já está na pasta.

Arquivo separado da OS/checklist de propósito: aqueles são saída para
o usuário (não dá pra confiar em ler de volta se o layout mudar), esse
aqui é lido pelo próprio programa na rodada seguinte.
"""
import base64
import csv
import json
import pathlib

from dimensoes import extrair_dimensoes, extrair_quantidade, identificar_categoria, identificar_variante
from utils import chave_comparacao_cliente, nome_cliente_da_pasta

NOME_ARQUIVO_ESTADO = "estado_pedido.json"


def localizar_pastas_cliente(nome_cliente_seguro, pasta_saida_base="etiquetas_geradas"):
    """
    Lista as pastas já existentes desse cliente, mais recente primeiro
    pelo nome (o timestamp no nome já ordena assim). Compara o nome do
    cliente ignorando diferença de espaço (ver utils.chave_comparacao_
    cliente) — sem isso, um espaço a mais ou a menos na hora de digitar
    faz o sistema não achar o pedido anterior e começar um do zero, sem
    avisar. Cliente nunca processado antes: lista vazia.
    """
    base = pathlib.Path(pasta_saida_base)
    if not base.exists():
        return []
    chave_alvo = chave_comparacao_cliente(nome_cliente_seguro)
    pastas = []
    for p in base.iterdir():
        if not p.is_dir():
            continue
        if chave_comparacao_cliente(nome_cliente_da_pasta(p.name)) == chave_alvo:
            pastas.append(p)
    return sorted(pastas, key=lambda p: p.name, reverse=True)


def _nomes_do_log(pasta_saida):
    """
    Fallback pra pasta de antes do estado_pedido.json existir: lê o(s)
    log_processamento_*.csv que TODA pasta já salva (mesmo as antigas)
    e recupera o nome de cada arquivo com status OK. Não recupera
    categoria/medida/miniatura (o log não guarda isso de um jeito
    confiável de re-extrair) — só o nome, que já é o suficiente pra não
    reprocessar um arquivo repetido, o problema mais urgente. Devolve
    conjunto vazio se não achar log nenhum (pasta realmente sem
    histórico recuperável).
    """
    nomes = set()
    for caminho_log in pathlib.Path(pasta_saida).glob("log_processamento_*.csv"):
        try:
            with open(caminho_log, "r", encoding="utf-8-sig", newline="") as f:
                for linha in csv.DictReader(f):
                    if linha.get("status") == "OK" and linha.get("arquivo"):
                        nomes.add(linha["arquivo"])
        except (OSError, csv.Error):
            continue
    return nomes


def estado_existe(pasta_saida):
    """
    Pasta pode ser atualizada se tiver o estado_pedido.json completo OU
    (pasta de antes desse recurso existir) pelo menos um log CSV, que
    dá pra reconstruir os nomes já processados a partir dele (ver
    _nomes_do_log/carregar_estado). Só recusa se não tiver nem um nem
    outro — aí não existe nenhum jeito confiável de saber o que já foi
    processado nessa pasta.
    """
    pasta = pathlib.Path(pasta_saida)
    if (pasta / NOME_ARQUIVO_ESTADO).exists():
        return True
    return any(pasta.glob("log_processamento_*.csv"))


def _reconstruir_item_legado(nome_arquivo, config):
    """
    Reconstrói categoria/dimensão/quantidade/variante de um item legado
    (pasta de antes do estado_pedido.json existir, recuperado só pelo
    nome via _nomes_do_log) usando a MESMA detecção por nome de arquivo
    já usada no processamento normal (dimensoes.identificar_categoria e
    afins) — o nome do arquivo já carrega esse dado, não precisa
    inventar nada. Sem isso, o item ficava com categoria=None pra
    sempre: nenhuma categoria bate com None, então ele nunca aparece no
    resumo visual da OS nem entra em nenhum subtotal — se a rodada
    tiver poucos ou nenhum item genuinamente novo, a OS inteira pode
    sair sem nenhum item visível (bug real visto em produção,
    2026-08-26).

    'config' é o config.json carregado (materiais/sinonimos_categoria/
    typos_unidade); sem ele (compatibilidade com chamadas antigas/
    testes que não têm config à mão), devolve o item mínimo de sempre,
    com categoria=None.
    """
    item = {
        "arquivo": nome_arquivo, "categoria": None, "quantidade": 1,
        "dimensao": None, "variante": None, "thumbnail_bytes": None,
    }
    if not config:
        return item

    materiais = config.get("materiais", {})
    nome_upper = nome_arquivo.upper()
    categoria, _ = identificar_categoria(nome_upper, materiais, config.get("sinonimos_categoria", {}))
    if categoria is None:
        return item

    quantidade, _ = extrair_quantidade(nome_arquivo)
    item["categoria"] = categoria
    item["dimensao"] = extrair_dimensoes(nome_arquivo, config.get("typos_unidade", {}))
    item["quantidade"] = quantidade
    item["variante"] = identificar_variante(nome_upper, materiais.get(categoria, {}).get("variantes", []))
    return item


def carregar_estado(pasta_saida, config=None):
    """
    Lê os itens já processados nessa pasta, com a miniatura decodificada
    de volta pra bytes. Se não existir estado_pedido.json ainda (pasta
    de antes desse recurso existir, mas com log recuperável — ver
    estado_existe), reconstrói cada item a partir do nome do arquivo
    recuperado do log (ver _reconstruir_item_legado) — só falta a
    miniatura, que não tem como recuperar sem o PDF original. A partir
    da próxima rodada, o estado_pedido.json completo é salvo por cima e
    essa reconstrução não é mais necessária pra essa pasta.
    """
    caminho = pathlib.Path(pasta_saida) / NOME_ARQUIVO_ESTADO
    if not caminho.exists():
        return [
            _reconstruir_item_legado(nome, config)
            for nome in sorted(_nomes_do_log(pasta_saida))
        ]
    try:
        with open(caminho, "r", encoding="utf-8") as f:
            dados = json.load(f)
    except (json.JSONDecodeError, OSError):
        # arquivo corrompido (ex: queda de energia/sync do OneDrive no
        # meio de uma escrita antiga, de antes de salvar_estado virar
        # atômico) — guarda uma cópia pra dar pra investigar depois, em
        # vez de só descartar em silêncio (mesmo espírito de config.py/
        # estoque.py). Sem isso, o filtro de "já processado" voltaria a
        # zero sem nenhum aviso, reprocessando tudo de novo.
        try:
            caminho.replace(caminho.with_suffix(".json.bak"))
        except OSError:
            pass
        return []

    itens = dados.get("itens", [])
    for item in itens:
        b64 = item.pop("thumbnail_b64", None)
        item["thumbnail_bytes"] = base64.b64decode(b64) if b64 else None
    return itens


def salvar_estado(pasta_saida, itens):
    """
    Grava a lista completa de itens já processados nessa pasta (os de
    antes + os novos dessa rodada), pra próxima rodada continuar de
    onde essa parou. JSON não guarda bytes crus, então a miniatura vai
    em base64; nenhum campo transitório de exibição (como 'novo_em'/
    'reposicao_em', usados só pra desenhar o selo na OS dessa rodada) é
    persistido — 'reposicao' (se esse item era uma reposição) continua
    salvo, é fato permanente do item, não muda depois.

    Escreve num arquivo temporário e só troca no final (mesmo padrão já
    usado em processamento._colar_paginas_no_final) — esse arquivo é a
    memória inteira do filtro de "já processado"; uma queda de energia
    ou conflito de sincronização do OneDrive no meio de uma escrita
    direta deixaria ele corrompido, e o próximo carregar_estado
    reprocessaria tudo de novo sem avisar.
    """
    itens_serializaveis = []
    for item in itens:
        copia = {k: v for k, v in item.items() if k not in ("thumbnail_bytes", "novo_em", "reposicao_em")}
        if item.get("thumbnail_bytes"):
            copia["thumbnail_b64"] = base64.b64encode(item["thumbnail_bytes"]).decode("ascii")
        itens_serializaveis.append(copia)

    caminho = pathlib.Path(pasta_saida) / NOME_ARQUIVO_ESTADO
    caminho_tmp = caminho.with_suffix(".tmp.json")
    with open(caminho_tmp, "w", encoding="utf-8") as f:
        json.dump({"itens": itens_serializaveis}, f, ensure_ascii=False, indent=2)
    caminho_tmp.replace(caminho)


def nomes_ja_processados(itens_estado):
    return {item["arquivo"] for item in itens_estado}
