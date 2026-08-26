"""
Funções utilitárias pequenas, usadas em mais de um lugar do projeto.
"""
import re

# Caracteres que o Windows não aceita em nome de arquivo/pasta, mais
# caracteres de controle (invisíveis, mas que causam problema igual).
_CARACTERES_INVALIDOS = r'[<>:"/\\|?*\x00-\x1f]'

# pasta de saída é sempre "CLIENTE_AAAAMMDD_HHMMSS" (ver processamento.py)
_PADRAO_SUFIXO_TIMESTAMP = re.compile(r"_(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})$")


def nome_cliente_da_pasta(nome_pasta):
    """Tira o sufixo "_AAAAMMDD_HHMMSS" de um nome de pasta de pedido, sobrando só o nome do cliente."""
    return _PADRAO_SUFIXO_TIMESTAMP.sub("", nome_pasta)


def data_hora_da_pasta(nome_pasta):
    """
    Extrai a data/hora do sufixo "_AAAAMMDD_HHMMSS" de um nome de pasta
    de pedido, formatada como "DD-MM-AAAA HH-MM-SS". Usada como nome de
    subpasta mais enxuto (sem repetir o nome do cliente, que já é a
    pasta de fora) — inclui hora e minuto E segundo de propósito: mais
    de um pedido do mesmo cliente pode acontecer no mesmo dia (material
    chegando aos poucos), só a data sozinha colidiria entre eles.
    Sem o padrão esperado no nome, devolve o nome original sem mudar
    nada (mais seguro que inventar uma data).
    """
    m = _PADRAO_SUFIXO_TIMESTAMP.search(nome_pasta)
    if not m:
        return nome_pasta
    ano, mes, dia, hora, minuto, segundo = m.groups()
    return f"{dia}-{mes}-{ano} {hora}-{minuto}-{segundo}"


def chave_comparacao_cliente(nome):
    """
    Chave só pra COMPARAR se dois nomes são do mesmo cliente — ignora
    diferença de espaço (ex: "SUPERBET" vs "SUPER BET", digitado
    diferente entre uma vez e outra). Não serve pra exibir/nomear pasta
    nenhuma, só pra achar uma pasta de cliente já existente que
    provavelmente é a mesma, apesar da grafia diferente.
    """
    return re.sub(r"\s+", "", nome.upper())


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


def formatar_duracao_minutos(minutos):
    """
    Formata uma duração em minutos como "Xh Ymin" (ou só "Ymin" se der
    menos de 1h, só "Xh" se der um número redondo de horas). Usada pra
    mostrar a estimativa de tempo de máquina na OS (área × minutos por
    m² de cada categoria — ver relatorios.gerar_os) de um jeito legível,
    em vez de um número solto de minutos.
    """
    minutos_inteiros = round(minutos)
    horas, resto = divmod(minutos_inteiros, 60)
    if horas and resto:
        return f"{horas}h {resto}min"
    if horas:
        return f"{horas}h"
    return f"{resto}min"


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
