"""
Testes dos parametros de usinagem.

Os numeros de passes aqui NAO foram calculados por mim: sao os que o
Flavio disse de cabeca em 06/09/2026 ("MDF 15 vai dar 3 passes", "MDF 9
vai dar 2"). Se a conta do modulo divergir deles, a conta e que esta
errada.
"""
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from corte_parametros import (
    buscar, combinacoes_cadastradas, profundidade_de_corte, quantidade_de_passes,
)


def test_corta_sempre_um_milimetro_alem_da_chapa():
    """
    Regra do usuario: "todos deve passar 1mm alem da espessura da chapa".
    Parar exatamente na espessura deixa a peca presa por um filme.
    """
    assert profundidade_de_corte(10) == 11.0
    assert profundidade_de_corte(20) == 21.0
    assert profundidade_de_corte(6) == 7.0


@pytest.mark.parametrize("material, espessura, passes", [
    ("PVC", 10, 1),   # profundidade 11, passada 11 -> sai de uma vez
    ("PVC", 20, 2),   # profundidade 21, passada 11
    ("MDF", 6, 1),    # profundidade 7, passada 7
    ("MDF", 9, 2),    # dito pelo usuario: "vai dar 2 passes"
    ("MDF", 15, 3),   # dito pelo usuario: "vai dar 3 passes"
])
def test_passes_batem_com_o_que_o_usuario_disse(material, espessura, passes):
    assert buscar(material, espessura)["passes"] == passes


def test_a_passada_muda_com_a_espessura_nao_so_com_o_material():
    """
    MDF de 6 usa passada 7 (corta de uma vez); MDF de 9 e 15 usam 6.
    Guardar a passada so por material perderia essa diferenca.
    """
    assert buscar("MDF", 6)["passada_mm"] == 7.0
    assert buscar("MDF", 9)["passada_mm"] == 6.0
    assert buscar("MDF", 15)["passada_mm"] == 6.0


def test_aponta_pra_ferramenta_do_banco_do_aspire():
    """
    'grupo' e 'ferramenta' tem que bater letra por letra com o banco, que
    e como GetTool(grupo, nome) acha. Lidos do arquivo real do banco.
    """
    pvc = buscar("PVC", 10)
    assert pvc["grupo"] == "Fresa 4 mm"
    assert pvc["ferramenta"] == "Topo Raso (4 mm)"

    mdf = buscar("MDF", 15)
    assert mdf["grupo"] == "Fresa 6 mm"
    assert mdf["ferramenta"] == "Topo Raso (6 mm)"


def test_material_nao_cadastrado_devolve_nada_em_vez_de_chutar():
    """
    Chutar parametro de corte quebra fresa e estraga chapa. Quem chama
    tem que tratar a ausencia.
    """
    assert buscar("ACRILICO", 4) is None
    assert buscar("PVC", 3) is None, "PVC 3mm existe no estoque mas ainda nao tem parametro"
    assert buscar("MDF", 15.0) is not None, "aceita float, arredonda pra espessura inteira"


def test_aceita_material_em_minusculo_e_com_espaco():
    assert buscar("  pvc  ", 10) == buscar("PVC", 10)


def test_passada_zero_nao_passa_calado():
    with pytest.raises(ValueError):
        quantidade_de_passes(10, 0)


def test_lista_o_que_esta_cadastrado():
    """A tela precisa saber o que falta, nao so o que tem."""
    combos = combinacoes_cadastradas()
    assert ("MDF", 6) in combos
    assert ("PVC", 20) in combos
    assert len(combos) == 5
