"""
Funções utilitárias pequenas, usadas em mais de um lugar do projeto.
"""
import re

# Caracteres que o Windows não aceita em nome de arquivo/pasta, mais
# caracteres de controle (invisíveis, mas que causam problema igual).
_CARACTERES_INVALIDOS = r'[<>:"/\\|?*\x00-\x1f]'

# pasta de saída é sempre "CLIENTE_AAAAMMDD_HHMMSS" (ver processamento.py)
_PADRAO_SUFIXO_TIMESTAMP = re.compile(r"_\d{8}_\d{6}$")


def nome_cliente_da_pasta(nome_pasta):
    """Tira o sufixo "_AAAAMMDD_HHMMSS" de um nome de pasta de pedido, sobrando só o nome do cliente."""
    return _PADRAO_SUFIXO_TIMESTAMP.sub("", nome_pasta)


_ACENTOS = str.maketrans(
    "ÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇáàâãäéèêëíìîïóòôõöúùûüç",
    "AAAAAEEEEIIIIOOOOOUUUUCaaaaaeeeeiiiiooooouuuuc",
)


def remover_acentos(texto):
    """
    Troca cada vogal acentuada e cedilha pelo equivalente sem acento.
    Usada pra comparar texto tolerando as várias formas de alguém
    digitar a mesma palavra com acento certo, errado ou faltando (ex:
    "reposição" == "reposicao" == "reposiçao" depois de normalizado) —
    sem precisar cadastrar cada combinação de acento na mão.
    """
    return texto.translate(_ACENTOS)


def sanitizar_nome_arquivo(nome, substituto="_"):
    """
    Remove caracteres que o Windows não aceita em nomes de arquivo ou
    pasta (< > : " / \\ | ? * e caracteres de controle), trocando cada
    um pelo caractere em 'substituto'. Também remove espaços e pontos
    no início/fim, que o Windows ignora silenciosamente e podem causar
    confusão (ex: "Cliente." vira "Cliente").

    Isso evita que o processamento quebre no meio quando o nome do
    cliente digitado tiver, por exemplo, uma barra ("Cliente A/B").
    """
    limpo = re.sub(_CARACTERES_INVALIDOS, substituto, nome)
    limpo = limpo.strip(" .")
    return limpo or "SEM_NOME"
