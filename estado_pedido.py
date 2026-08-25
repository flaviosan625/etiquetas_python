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
import json
import pathlib
import re

NOME_ARQUIVO_ESTADO = "estado_pedido.json"

# pasta de saída é sempre "CLIENTE_AAAAMMDD_HHMMSS" (ver processamento.py)
_PADRAO_SUFIXO_TIMESTAMP = re.compile(r"_\d{8}_\d{6}$")


def _chave_comparacao(nome):
    """
    Chave só pra COMPARAR se duas pastas são do mesmo cliente — ignora
    diferença de espaço (ex: "SUPERBET" vs "SUPER BET", digitado
    diferente entre uma rodada e outra e que por isso não seria
    reconhecido como o mesmo pedido). Não muda o nome real da pasta,
    que continua exatamente como foi sanitizado a partir do que o
    usuário digitou.
    """
    return re.sub(r"\s+", "", nome.upper())


def localizar_pastas_cliente(nome_cliente_seguro, pasta_saida_base="etiquetas_geradas"):
    """
    Lista as pastas já existentes desse cliente, mais recente primeiro
    pelo nome (o timestamp no nome já ordena assim). Compara o nome do
    cliente ignorando diferença de espaço (ver _chave_comparacao) — sem
    isso, um espaço a mais ou a menos na hora de digitar faz o sistema
    não achar o pedido anterior e começar um do zero, sem avisar.
    Cliente nunca processado antes: lista vazia.
    """
    base = pathlib.Path(pasta_saida_base)
    if not base.exists():
        return []
    chave_alvo = _chave_comparacao(nome_cliente_seguro)
    pastas = []
    for p in base.iterdir():
        if not p.is_dir():
            continue
        nome_sem_timestamp = _PADRAO_SUFIXO_TIMESTAMP.sub("", p.name)
        if _chave_comparacao(nome_sem_timestamp) == chave_alvo:
            pastas.append(p)
    return sorted(pastas, key=lambda p: p.name, reverse=True)


def estado_existe(pasta_saida):
    """
    Se a pasta não tem estado_pedido.json, é porque foi criada antes
    desse recurso existir — não tem como saber com segurança quais
    arquivos já estão nela, então não é seguro tratar como "atualizar".
    """
    return (pathlib.Path(pasta_saida) / NOME_ARQUIVO_ESTADO).exists()


def carregar_estado(pasta_saida):
    """
    Lê os itens já processados nessa pasta, com a miniatura decodificada
    de volta pra bytes. Devolve lista vazia se o arquivo não existir ou
    estiver corrompido — quem chama decide o que fazer nesse caso (ver
    estado_existe, checado antes de tratar como atualização).
    """
    caminho = pathlib.Path(pasta_saida) / NOME_ARQUIVO_ESTADO
    if not caminho.exists():
        return []
    try:
        with open(caminho, "r", encoding="utf-8") as f:
            dados = json.load(f)
    except (json.JSONDecodeError, OSError):
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
    em base64; nenhum campo transitório de exibição (como 'novo_em',
    usado só pra desenhar o selo na OS dessa rodada) é persistido.
    """
    itens_serializaveis = []
    for item in itens:
        copia = {k: v for k, v in item.items() if k not in ("thumbnail_bytes", "novo_em")}
        if item.get("thumbnail_bytes"):
            copia["thumbnail_b64"] = base64.b64encode(item["thumbnail_bytes"]).decode("ascii")
        itens_serializaveis.append(copia)

    caminho = pathlib.Path(pasta_saida) / NOME_ARQUIVO_ESTADO
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump({"itens": itens_serializaveis}, f, ensure_ascii=False, indent=2)


def nomes_ja_processados(itens_estado):
    return {item["arquivo"] for item in itens_estado}
