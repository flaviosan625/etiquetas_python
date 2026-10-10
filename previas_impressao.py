"""Prévia do arquivo atual para selecionar uma arte antes de enviá-la à impressão."""
import pathlib

import miniaturas
from envio_impressao import _ATTRS_SO_NA_NUVEM


def chave_do_arquivo(caminho):
    """Identifica a versão da arte; mesmo nome em outra pasta é outra prévia."""
    caminho = pathlib.Path(caminho)
    try:
        estado = caminho.stat()
        nuvem = getattr(estado, "st_file_attributes", 0) & _ATTRS_SO_NA_NUVEM
        return str(caminho.absolute()), estado.st_size, estado.st_mtime_ns, nuvem
    except OSError:
        return str(caminho.absolute()), None, None, None


def carregar(caminho, chave):
    """JPEG e mensagem de ausência; não baixa placeholders nem guarda imagens em disco."""
    try:
        atual = chave_do_arquivo(caminho)
        if atual != chave:
            return None, "Arquivo alterado — atualize a lista"
        if atual[1] is None:
            return None, "Arquivo indisponível"
        if atual[3]:
            return None, "Só na nuvem — prévia após baixar"
        if atual[1] > miniaturas.LIMITE_BYTES:
            return None, "Arquivo grande — prévia indisponível"
        dados = miniaturas.de_arquivo(caminho, lado=224)
        if chave_do_arquivo(caminho) != chave:
            return None, "Arquivo alterado — atualize a lista"
        return dados, "" if dados else "Prévia indisponível"
    except Exception:
        # A prévia nunca pode impedir seleção, conferência ou envio.
        return None, "Prévia indisponível"
