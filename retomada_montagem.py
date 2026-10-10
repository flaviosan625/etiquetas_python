"""Retoma o arquivamento de um lote publicado sem montar os originais novamente."""
import json
import os
import pathlib
import re
import stat
import tempfile

PASTA_REGISTROS = "_lotes_montagem"
_PADRAO_LOTE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,119}\Z")


def _erro(mensagem):
    return ValueError(f"Confira o registro da montagem: {mensagem}")


def _lote_valido(lote_id):
    if not isinstance(lote_id, str) or not _PADRAO_LOTE.fullmatch(lote_id):
        raise _erro("identificador de lote inválido.")
    reservados = {"CON", "PRN", "AUX", "NUL"} | {f"COM{i}" for i in range(1, 10)} | {
        f"LPT{i}" for i in range(1, 10)}
    if lote_id.endswith(".") or lote_id.split(".")[0].upper() in reservados:
        raise _erro("identificador de lote inválido.")
    return lote_id


def _versoes_validas(versoes):
    if not isinstance(versoes, dict) or not versoes:
        raise _erro("faltam as versões dos originais.")
    resultado, nomes = {}, set()
    for nome, versao in versoes.items():
        if (not isinstance(nome, str) or not nome or pathlib.Path(nome).name != nome
                or nome in (".", "..") or "\x00" in nome):
            raise _erro("nome de original fora da pasta de entrada.")
        if nome.casefold() in nomes:
            raise _erro("originais com nomes ambíguos.")
        nomes.add(nome.casefold())
        if (not isinstance(versao, dict) or set(versao) != {"tamanho", "mtime_ns"}
                or type(versao["tamanho"]) is not int or versao["tamanho"] < 0
                or type(versao["mtime_ns"]) is not int):
            raise _erro(f"versão inválida de {nome!r}.")
        resultado[nome] = dict(versao)
    return resultado


def _pasta_registros(pasta):
    pasta = pathlib.Path(pasta).resolve()
    registros = pasta / PASTA_REGISTROS
    if registros.resolve() != registros:
        raise _erro("a pasta de registros redireciona para outro local.")
    return registros


def _saidas_validas(pasta, saidas):
    pasta = pathlib.Path(pasta).resolve()
    # A pasta interna pode ter um alias de apresentação (por exemplo,
    # ``UJV 100 UNY CV`` usa ``SAIDA UJV 100``). O registro deve validar
    # contra o destino efetivo, não reconstruir o nome pelo identificador.
    nome_saida = {
        "UJV 100 UNY CV": "UJV 100",
    }.get(pasta.name, pasta.name)
    raiz_saida = pasta.parent / f"SAIDA {nome_saida}"
    if raiz_saida.resolve() != raiz_saida:
        raise _erro("a pasta de saída redireciona para outro local.")
    if not isinstance(saidas, (list, tuple)) or not saidas:
        raise _erro("faltam os PDFs do lote.")
    resultado, repetidos = [], set()
    for saida in saidas:
        caminho = pathlib.Path(saida)
        if not caminho.is_absolute():
            raise _erro("o caminho de saída precisa ser absoluto.")
        resolvido = caminho.resolve()
        if resolvido.parent != raiz_saida or resolvido.suffix.lower() != ".pdf":
            raise _erro("PDF fora da saída desta máquina.")
        if str(resolvido).casefold() in repetidos:
            raise _erro("PDF repetido no lote.")
        repetidos.add(str(resolvido).casefold())
        resultado.append(str(resolvido))
    return resultado


def criar_registro(pasta, versoes_origem, saidas, lote_id):
    """Grava o compromisso do lote antes da publicação, sem tocar nos originais."""
    pasta = pathlib.Path(pasta).resolve()
    lote_id = _lote_valido(lote_id)
    registro = {"versao": 1, "lote_id": lote_id, "pasta": str(pasta),
                "originais": _versoes_validas(versoes_origem),
                "saidas": _saidas_validas(pasta, saidas)}
    registros = _pasta_registros(pasta)
    destino = registros / f"{lote_id}.json"
    try:
        destino.stat()
    except FileNotFoundError:
        pass
    except OSError as erro:
        raise _erro(f"não consegui conferir o identificador do lote: {erro}") from erro
    else:
        raise _erro("já existe um registro com este identificador.")
    temporario = None
    try:
        registros.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=registros,
                                         prefix=f".{lote_id}.", suffix=".tmp", delete=False) as stream:
            temporario = pathlib.Path(stream.name)
            json.dump(registro, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporario, destino)
    except OSError as erro:
        raise _erro(f"não consegui guardar o lote: {erro}") from erro
    finally:
        if temporario is not None:
            try:
                temporario.unlink(missing_ok=True)
            except OSError as erro:
                raise _erro(f"não consegui limpar o registro temporário: {erro}") from erro
    return destino


def _ler_json(caminho):
    try:
        return json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as erro:
        raise _erro(f"não consegui ler {caminho.name!r}: {erro}") from erro


def _ler_registros(pasta):
    pasta = pathlib.Path(pasta).resolve()
    registros = _pasta_registros(pasta)
    try:
        info = registros.stat()
    except FileNotFoundError:
        return []
    except OSError as erro:
        raise _erro(f"não consegui acessar os registros: {erro}") from erro
    if not stat.S_ISDIR(info.st_mode):
        raise _erro("a pasta de registros deixou de ser uma pasta.")
    lotes = []
    try:
        caminhos = sorted(caminho for caminho in registros.iterdir()
                          if caminho.suffix.casefold() == ".json")
    except OSError as erro:
        raise _erro(f"não consegui listar os lotes: {erro}") from erro
    for caminho in caminhos:
        if caminho.resolve().parent != registros or caminho.is_symlink():
            raise _erro("arquivo de registro redirecionado para outro local.")
        registro = _ler_json(caminho)
        if not isinstance(registro, dict) or registro.get("versao") != 1:
            raise _erro("formato de registro inválido.")
        lote_id = _lote_valido(registro.get("lote_id"))
        if caminho.stem != lote_id or registro.get("pasta") != str(pasta):
            raise _erro("o registro não pertence a esta entrada.")
        registro["originais"] = _versoes_validas(registro.get("originais"))
        registro["saidas"] = _saidas_validas(pasta, registro.get("saidas"))
        lotes.append((caminho, registro))
    return lotes


def _arquivo_existe(caminho):
    """Distingue ausência de falha de acesso para não presumir lote não publicado."""
    try:
        info = caminho.stat()
    except FileNotFoundError:
        return False
    except OSError as erro:
        raise _erro(f"não consegui conferir {caminho.name!r}: {erro}") from erro
    if not stat.S_ISREG(info.st_mode):
        raise _erro(f"a saída {caminho.name!r} deixou de ser um arquivo.")
    if info.st_size == 0:
        raise _erro(f"Publicação incompleta: {caminho.name!r} está vazio; confira as saídas antes de remontar.")
    return True


def _publicacao_confirmada(registro):
    """A ausência de qualquer saída mantém o lote pendente, nunca presume sucesso."""
    artefatos = [caminho for nome_saida in registro["saidas"]
                 for caminho in (pathlib.Path(nome_saida), pathlib.Path(nome_saida).with_suffix(".json"))]
    existentes = [_arquivo_existe(caminho) for caminho in artefatos]
    if not any(existentes):
        return False
    originais_encontrados = {}
    for nome_saida in registro["saidas"]:
        pdf = pathlib.Path(nome_saida)
        ficha = pdf.with_suffix(".json")
        if not _arquivo_existe(pdf) or not _arquivo_existe(ficha):
            raise _erro("Publicação incompleta: confira as saídas antes de remontar.")
        if ficha.resolve().parent != pdf.parent or ficha.is_symlink():
            raise _erro("ficha de saída fora da pasta da máquina.")
        dados = _ler_json(ficha)
        if not isinstance(dados, dict):
            raise _erro("a ficha da saída é inválida.")
        if dados.get("lote_id") != registro["lote_id"]:
            raise _erro("Publicação incompleta: a ficha pertence a outro lote; confira as saídas antes de remontar.")
        usados = _versoes_validas(dados.get("originais"))
        if any(nome not in registro["originais"] for nome in usados):
            raise _erro("a ficha contém original que não pertence ao lote.")
        if any(versao != registro["originais"][nome] for nome, versao in usados.items()):
            raise _erro("Publicação incompleta: a ficha declara outra versão; confira as saídas antes de remontar.")
        originais_encontrados.update(usados)
    if originais_encontrados != registro["originais"]:
        raise _erro("as fichas não comprovam todos os originais do lote.")
    return True


def _versao_atual(pasta, nome):
    caminho = pathlib.Path(pasta).resolve() / nome
    if caminho.resolve().parent != pathlib.Path(pasta).resolve() or caminho.is_symlink():
        raise _erro("original redirecionado para outro local.")
    try:
        info = caminho.stat()
    except FileNotFoundError:
        return None
    except OSError as erro:
        raise _erro(f"não consegui conferir o original {nome!r}: {erro}") from erro
    if not stat.S_ISREG(info.st_mode):
        raise _erro(f"o original {nome!r} deixou de ser um arquivo.")
    return {"tamanho": info.st_size, "mtime_ns": info.st_mtime_ns}


def originais_confirmados(pasta):
    """Prévia somente leitura: versões ainda presentes já têm todas as saídas."""
    confirmados = {}
    for _caminho, registro in _ler_registros(pasta):
        if not _publicacao_confirmada(registro):
            continue
        for nome, versao in registro["originais"].items():
            if _versao_atual(pasta, nome) == versao:
                confirmados[nome] = dict(versao)
    return confirmados


def retomar_arquivamento(pasta, mover, logger=None):
    """Tenta apenas arquivar fontes publicadas, mantendo pendências de arquivo aberto."""
    pasta = pathlib.Path(pasta).resolve()
    logger = logger or (lambda nivel, mensagem: None)
    avisos = []
    for caminho, registro in _ler_registros(pasta):
        if not _publicacao_confirmada(registro):
            # Não há nenhum PDF nem ficha publicado; uma queda antes do commit
            # deixa somente este marcador e a entrada pode ser montada de novo.
            try:
                caminho.unlink()
            except OSError as erro:
                raise _erro(f"não consegui limpar o lote não publicado: {erro}") from erro
            logger("info", f"Lote {registro['lote_id']} não publicado; originais mantidos na entrada.")
            continue
        destino = pasta / "_originais" / registro["lote_id"]
        if destino.resolve() != destino:
            raise _erro("o arquivamento redireciona para outro local.")
        pendente = False
        for nome, versao in registro["originais"].items():
            if _versao_atual(pasta, nome) != versao:
                continue
            try:
                mover(pasta / nome, destino)
            except OSError as erro:
                pendente = True
                aviso = f"{nome}: PDF já salvo; arquivamento pendente ({erro})."
                avisos.append(aviso)
                logger("warn", aviso)
                continue
            if _versao_atual(pasta, nome) == versao:
                pendente = True
                aviso = f"{nome}: o original ainda está na entrada; arquivamento pendente."
                avisos.append(aviso)
                logger("warn", aviso)
        if not pendente:
            try:
                caminho.unlink()
            except OSError as erro:
                raise _erro(f"não consegui concluir o registro de arquivamento: {erro}") from erro
    return avisos
