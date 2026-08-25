import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from processamento import _eh_reposicao


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
