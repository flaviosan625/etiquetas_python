"""
Funções utilitárias pequenas, usadas em mais de um lugar do projeto.
"""
import re

# Caracteres que o Windows não aceita em nome de arquivo/pasta, mais
# caracteres de controle (invisíveis, mas que causam problema igual).
_CARACTERES_INVALIDOS = r'[<>:"/\\|?*\x00-\x1f]'


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
