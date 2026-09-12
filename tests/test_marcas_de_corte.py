import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import marcas_de_corte as mc


def _dados(media, corte, sangria=None, texto=False):
    """Monta o dicionário que marcas_de_corte.medidas devolveria, em pt."""
    d = {"MediaBox_pt": media, "TrimBox_pt": corte, "tem_texto": texto}
    if sangria:
        d["BleedBox_pt"] = sangria
    return d


# A confusão que gerou o bug de 2026-09-11: depois de remover a marca, a
# página fica do tamanho da SANGRIA (MediaBox = BleedBox), ainda maior que
# o corte. Comparar MediaBox com TrimBox achava que a sangria era marca e
# mandava remover de novo — o que travava, porque não havia o que remover.

def test_pagina_maior_que_a_sangria_tem_marca():
    # arte real: página 6,29 > sangria 6,10 > corte 6,00 (em pt aqui só a ordem importa)
    d = _dados(media=(6290, 1290), corte=(6000, 1000), sangria=(6100, 1100), texto=True)
    assert mc.tem_marca_de_corte(d) is True


def test_pagina_igual_a_sangria_nao_tem_marca():
    # já limpa: página = sangria (6,10), ainda maior que o corte (6,00) — isso é sangria, não marca
    d = _dados(media=(6100, 1100), corte=(6000, 1000), sangria=(6100, 1100))
    assert mc.tem_marca_de_corte(d) is False, "a sangria que sobra não é marca"


def test_sem_sangria_declarada_a_tarja_denuncia_a_marca():
    d = _dados(media=(6290, 1290), corte=(6000, 1000), sangria=None, texto=True)
    assert mc.tem_marca_de_corte(d) is True


def test_sem_sangria_e_sem_tarja_pagina_igual_ao_corte_nao_tem_marca():
    d = _dados(media=(6000, 1000), corte=(6000, 1000), sangria=None, texto=False)
    assert mc.tem_marca_de_corte(d) is False


def test_dados_vazios_nao_quebram():
    assert mc.tem_marca_de_corte(None) is False
    assert mc.tem_marca_de_corte({}) is False


def test_sangria_em_pontos_respeita_userunit():
    # corte [10,10,90,20], sangria [0,0,100,30], UserUnit 10 -> folga 10 * 10 = 100 pt
    dados = {"TrimBox": [10, 10, 90, 20], "BleedBox": [0, 0, 100, 30], "unidade": 10.0}
    assert mc.sangria_em_pontos(dados) == 100.0
