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
