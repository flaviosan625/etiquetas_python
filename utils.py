"""
Funções utilitárias pequenas, usadas em mais de um lugar do projeto.
"""
import pathlib
import re

# Caracteres que o Windows não aceita em nome de arquivo/pasta, mais
# caracteres de controle (invisíveis, mas que causam problema igual).
_CARACTERES_INVALIDOS = r'[<>:"/\\|?*\x00-\x1f]'

# pasta de saída é sempre "CLIENTE_AAAAMMDD_HHMMSS" (ver processamento.py)
_PADRAO_SUFIXO_TIMESTAMP = re.compile(r"_(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})$")


# Desde 03/10/2026 o lote é uma SUBPASTA do cliente, e o nome dela é só o
# carimbo de data: "etiquetas_geradas/VIBRA/20261003_192549". O formato
# antigo ("VIBRA_20261003_192549", tudo na raiz) continua sendo lido —
# tem pedido em andamento no disco nos dois formatos.
_PADRAO_SO_TIMESTAMP = re.compile(r"^(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})$")


def nome_cliente_da_pasta(nome_pasta):
    """Tira o sufixo "_AAAAMMDD_HHMMSS" de um nome de pasta de pedido, sobrando só o nome do cliente."""
    return _PADRAO_SUFIXO_TIMESTAMP.sub("", nome_pasta)


def pasta_e_de_lote(pasta):
    """A pasta é um LOTE de etiquetas (nos dois formatos), e não a do cliente?"""
    nome = pathlib.Path(pasta).name
    return bool(_PADRAO_SO_TIMESTAMP.match(nome) or _PADRAO_SUFIXO_TIMESTAMP.search(nome))


def cliente_do_pedido(pasta):
    """
    De quem é esta pasta de lote — funciona nos dois formatos:
      VIBRA/20261003_192549   -> VIBRA   (desde 03/10/2026)
      VIBRA_20261003_192549   -> VIBRA   (como era antes)
    """
    pasta = pathlib.Path(pasta)
    if _PADRAO_SO_TIMESTAMP.match(pasta.name):
        return pasta.parent.name
    return nome_cliente_da_pasta(pasta.name)


def pastas_de_lote(pasta_saida_base):
    """
    Toda pasta de LOTE debaixo da base, nos dois formatos, mais recente
    primeiro. Nunca devolve a pasta do cliente em si — lá mora a OS da
    produção, que o vigia regenera e que não é um lote.
    """
    base = pathlib.Path(pasta_saida_base)
    if not base.is_dir():
        return []
    achadas = []
    for p in sorted(base.iterdir()):
        if not p.is_dir():
            continue
        if _PADRAO_SUFIXO_TIMESTAMP.search(p.name):
            achadas.append(p)              # formato antigo, na raiz
            continue
        achadas.extend(sub for sub in sorted(p.iterdir())
                       if sub.is_dir() and _PADRAO_SO_TIMESTAMP.match(sub.name))
    # o carimbo ordena sozinho; o mais recente primeiro
    return sorted(achadas, key=lambda p: (data_hora_ordenavel(p), p.name), reverse=True)


def data_hora_ordenavel(pasta):
    """'20261003192549' de uma pasta de lote, nos dois formatos; '' se não houver."""
    nome = pathlib.Path(pasta).name
    m = _PADRAO_SO_TIMESTAMP.match(nome) or _PADRAO_SUFIXO_TIMESTAMP.search(nome)
    return "".join(m.groups()) if m else ""


def data_hora_da_pasta(nome_pasta):
    """
    Extrai a data/hora de um nome de pasta de lote — do sufixo
    "_AAAAMMDD_HHMMSS" (formato antigo) ou do nome inteiro, que desde
    03/10/2026 é só o carimbo. Formatada como "DD-MM-AAAA HH-MM-SS". Usada como nome de
    subpasta mais enxuto (sem repetir o nome do cliente, que já é a
    pasta de fora) — inclui hora e minuto E segundo de propósito: mais
    de um pedido do mesmo cliente pode acontecer no mesmo dia (material
    chegando aos poucos), só a data sozinha colidiria entre eles.
    Sem o padrão esperado no nome, devolve o nome original sem mudar
    nada (mais seguro que inventar uma data).
    """
    m = _PADRAO_SUFIXO_TIMESTAMP.search(nome_pasta) or _PADRAO_SO_TIMESTAMP.match(nome_pasta)
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
