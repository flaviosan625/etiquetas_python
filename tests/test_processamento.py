import copy
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import pymupdf

from config import CONFIG_PADRAO
from processamento import _eh_reposicao, processar_etiquetas


def _pdf_de_uma_pagina(caminho):
    doc = pymupdf.open()
    doc.new_page(width=200, height=200)
    doc.save(str(caminho))
    doc.close()


def test_eh_reposicao_reconhece_variacoes_de_acento():
    nomes = [
        "1UN LONA 2,00X1,00 - REPOSIÇÃO.PDF",
        "1UN LONA 2,00X1,00 - REPOSICAO.PDF",
        "1UN LONA 2,00X1,00 - REPOSIÇAO.PDF",
        "1UN LONA 2,00X1,00 - REFAÇÃO.PDF",
        "1UN LONA 2,00X1,00 - REFACAO.PDF",
        "1UN LONA 2,00X1,00 - REFAÇAO.PDF",
        "1UN LONA 2,00X1,00 - REF.PDF",
    ]
    for nome in nomes:
        assert _eh_reposicao(nome), f"deveria reconhecer: {nome}"


def test_eh_reposicao_arquivo_normal_nao_e_marcado():
    assert not _eh_reposicao("1UN LONA 2,00X1,00.PDF")


def test_eh_reposicao_ref_nao_casa_dentro_de_outra_palavra():
    assert not _eh_reposicao("1UN LONA REFORCO 2,00X1,00.PDF")


def test_segunda_rodada_mantem_itens_da_primeira_na_os(tmp_path):
    """
    Regressão direta do bug real de produção (2026-08-26): a OS de uma
    rodada de atualização precisa mostrar os itens da rodada ANTERIOR
    junto com os novos, não só os novos. Roda processar_etiquetas duas
    vezes de ponta a ponta (não só unidades isoladas) contra o mesmo
    pedido — cada rodada com uma pasta de entrada e categoria
    diferente — e confere que a OS final (texto renderizado do PDF)
    contém as DUAS categorias, com a área de cada uma correta.
    """
    config = copy.deepcopy(CONFIG_PADRAO)
    pasta_saida_base = tmp_path / "saida"

    entrada1 = tmp_path / "entrada1"
    entrada1.mkdir()
    _pdf_de_uma_pagina(entrada1 / "1UN LONA 2,00X1,00M_arte.pdf")

    resultado1 = processar_etiquetas(
        str(entrada1), "CLIENTE TESTE", "Gerente", "Produtor",
        config, pasta_saida_base=str(pasta_saida_base),
    )
    assert resultado1 is not None
    pasta_saida = resultado1["pasta_saida"]

    entrada2 = tmp_path / "entrada2"
    entrada2.mkdir()
    _pdf_de_uma_pagina(entrada2 / "1UN PVC BRANCO 1,00X1,00M_arte2.pdf")

    resultado2 = processar_etiquetas(
        str(entrada2), "CLIENTE TESTE", "Gerente", "Produtor",
        config, pasta_saida_base=str(pasta_saida_base), pasta_saida_existente=pasta_saida,
    )
    assert resultado2 is not None
    assert resultado2["arquivos_novos"] == 1

    doc = pymupdf.open(resultado2["os"])
    texto = "".join(p.get_text() for p in doc)
    doc.close()

    assert "LONA" in texto, "item da PRIMEIRA rodada sumiu da OS depois da segunda rodada"
    assert "PVC" in texto
    assert "2.00 m" in texto  # área da LONA (2,00 x 1,00m)
    assert "1.00 m" in texto  # área do PVC (1,00 x 1,00m)
    assert "2 itens no total" in texto


def test_rodadas_seguintes_geram_checklist_separado_e_versionado(tmp_path):
    """
    Decisão do usuário (2026-08-26): cada rodada (arquivo novo ou
    reposição) vira um checklist SEPARADO — nunca mais cola página num
    checklist que já foi impresso/marcado à caneta antes. Primeira
    rodada sem sufixo, segunda "V2", terceira "V3" — cada uma só com o
    que foi processado NAQUELA rodada. Roda 3 rodadas reais e confere
    o nome de cada arquivo em disco e quantas etiquetas cada um tem.
    """
    config = copy.deepcopy(CONFIG_PADRAO)
    pasta_saida_base = tmp_path / "saida"

    entrada1 = tmp_path / "entrada1"
    entrada1.mkdir()
    _pdf_de_uma_pagina(entrada1 / "1UN LONA 2,00X1,00M_a.pdf")
    resultado1 = processar_etiquetas(
        str(entrada1), "CLIENTE TESTE", "Gerente", "Produtor",
        config, pasta_saida_base=str(pasta_saida_base),
    )
    pasta_saida = pathlib.Path(resultado1["pasta_saida"])

    entrada2 = tmp_path / "entrada2"
    entrada2.mkdir()
    _pdf_de_uma_pagina(entrada2 / "1UN LONA 3,00X1,00M_b.pdf")
    processar_etiquetas(
        str(entrada2), "CLIENTE TESTE", "Gerente", "Produtor",
        config, pasta_saida_base=str(pasta_saida_base), pasta_saida_existente=pasta_saida,
    )

    entrada3 = tmp_path / "entrada3"
    entrada3.mkdir()
    _pdf_de_uma_pagina(entrada3 / "1UN LONA 4,00X1,00M_c - REPOSICAO.pdf")
    processar_etiquetas(
        str(entrada3), "CLIENTE TESTE", "Gerente", "Produtor",
        config, pasta_saida_base=str(pasta_saida_base), pasta_saida_existente=pasta_saida,
    )

    nomes_checklist = sorted(p.name for p in pasta_saida.glob("Checklist * - LONA*.pdf"))
    assert nomes_checklist == [
        "Checklist CLIENTE TESTE - LONA V2.pdf",
        "Checklist CLIENTE TESTE - LONA V3.pdf",
        "Checklist CLIENTE TESTE - LONA.pdf",
    ]

    def _paginas(nome):
        doc = pymupdf.open(str(pasta_saida / nome))
        n = len(doc)
        doc.close()
        return n

    # cada rodada tem 1 arquivo só (banner + 1 etiqueta = 1 página cada)
    assert _paginas("Checklist CLIENTE TESTE - LONA.pdf") == 1
    assert _paginas("Checklist CLIENTE TESTE - LONA V2.pdf") == 1
    assert _paginas("Checklist CLIENTE TESTE - LONA V3.pdf") == 1

    nomes_unificado = sorted(p.name for p in pasta_saida.glob("Checklist * - UNIFICADO*.pdf"))
    assert nomes_unificado == [
        "Checklist CLIENTE TESTE - UNIFICADO V2.pdf",
        "Checklist CLIENTE TESTE - UNIFICADO V3.pdf",
        "Checklist CLIENTE TESTE - UNIFICADO.pdf",
    ]


def test_cliente_digitado_com_espaco_diferente_nao_fragmenta_os_nem_checklist(tmp_path):
    """
    Regressão de bug real de produção (2026-08-28, SUPERBET): cliente
    digitado "SUPERBET" numa rodada e "SUPER BET" (com espaço) na
    seguinte, atualizando o MESMO pedido — antes desse fix, OS e
    checklist usavam o nome como foi digitado NAQUELA rodada, então a
    segunda rodada gerava "OS - SUPER BET.pdf" e "Checklist SUPER BET -
    ..." SEPARADOS dos arquivos "OS - SUPERBET.pdf"/"Checklist SUPERBET
    - ..." da primeira — a OS deixava de ser um documento só, cada
    arquivo só com metade do pedido. Precisa sempre usar o nome já
    fixado no nome da pasta, não o que foi digitado de novo.
    """
    config = copy.deepcopy(CONFIG_PADRAO)
    pasta_saida_base = tmp_path / "saida"

    entrada1 = tmp_path / "entrada1"
    entrada1.mkdir()
    _pdf_de_uma_pagina(entrada1 / "1UN LONA 2,00X1,00M_a.pdf")
    resultado1 = processar_etiquetas(
        str(entrada1), "SUPERBET", "Gerente", "Produtor",
        config, pasta_saida_base=str(pasta_saida_base),
    )
    pasta_saida = pathlib.Path(resultado1["pasta_saida"])
    assert (pasta_saida / "OS - SUPERBET.pdf").exists()

    entrada2 = tmp_path / "entrada2"
    entrada2.mkdir()
    _pdf_de_uma_pagina(entrada2 / "1UN LONA 3,00X1,00M_b.pdf")
    resultado2 = processar_etiquetas(
        str(entrada2), "SUPER BET", "Gerente", "Produtor",
        config, pasta_saida_base=str(pasta_saida_base), pasta_saida_existente=pasta_saida,
    )

    # continua sendo o MESMO arquivo de OS de sempre, atualizado — nunca
    # um "OS - SUPER BET.pdf" separado
    assert resultado2["os"] == str(pasta_saida / "OS - SUPERBET.pdf")
    assert not (pasta_saida / "OS - SUPER BET.pdf").exists()

    doc = pymupdf.open(resultado2["os"])
    texto = "".join(p.get_text() for p in doc)
    doc.close()
    assert "2 itens no total" in texto, "OS devia ter os itens das DUAS rodadas, não só a última"

    nomes_checklist = sorted(p.name for p in pasta_saida.glob("Checklist * - LONA*.pdf"))
    assert nomes_checklist == ["Checklist SUPERBET - LONA V2.pdf", "Checklist SUPERBET - LONA.pdf"]


def test_log_processamento_fica_dentro_da_subpasta_log(tmp_path):
    """Decisão do usuário (2026-08-26): log_processamento_*.csv não fica solto na pasta do pedido, deixa cheio."""
    config = copy.deepcopy(CONFIG_PADRAO)
    pasta_saida_base = tmp_path / "saida"
    entrada = tmp_path / "entrada"
    entrada.mkdir()
    _pdf_de_uma_pagina(entrada / "1UN LONA 2,00X1,00M_a.pdf")

    resultado = processar_etiquetas(
        str(entrada), "CLIENTE TESTE", "Gerente", "Produtor",
        config, pasta_saida_base=str(pasta_saida_base),
    )

    pasta_saida = pathlib.Path(resultado["pasta_saida"])
    assert not list(pasta_saida.glob("log_processamento_*.csv")), "log não deveria ficar solto na pasta"
    assert list(pasta_saida.glob("_log/log_processamento_*.csv")), "log deveria estar dentro de _log"
