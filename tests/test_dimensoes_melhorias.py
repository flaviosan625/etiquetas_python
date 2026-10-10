"""Regressões da leitura de medidas sem usar configuração ou filas reais."""
import copy

import pytest

from config import CONFIG_PADRAO
from dimensoes import extrair_dimensoes
import envio_impressao


@pytest.mark.parametrize("nome", [
    "1UN LONA 600x400PIX.pdf",
    "1UN LONA 3,20x10,00DESCONHECIDA.pdf",
    "1UN LONA 3.20x10.00DESCONHECIDA.pdf",
])
def test_unidade_desconhecida_nao_corta_o_numero(nome):
    assert extrair_dimensoes(nome, CONFIG_PADRAO["typos_unidade"]) is None


def test_primeira_medida_desconhecida_nao_da_lugar_ao_acrescimo():
    nome = "1UN LONA 600x400PIX_acrescimo_605x405CM.pdf"
    assert extrair_dimensoes(nome, CONFIG_PADRAO["typos_unidade"]) is None


@pytest.mark.parametrize("nome, largura, altura, unidade", [
    ("1UN LONA 3,20x10,00MTS.pdf", 3.20, 10.00, "M"),
    ("1UN LONA 58x60XM.pdf", 0.58, 0.60, "CM"),
    ("1UN LONA 1000x220.pdf", 10.00, 2.20, "CM"),
    ("1UN LONA 900x1350MM.pdf", 0.90, 1.35, "MM"),
    ("1UN_LONA_2,10_X_2,10M.pdf", 2.10, 2.10, "M"),
    ("1UN LONA 2.12X3.20M_acrescimo_2.15X3.25M.pdf", 2.12, 3.20, "M"),
])
def test_envio_respeita_unidades_e_primeira_medida(tmp_path, monkeypatch,
                                                 nome, largura, altura, unidade):
    config = copy.deepcopy(CONFIG_PADRAO)
    arquivo = tmp_path / nome
    arquivo.write_bytes(b"arte isolada: a listagem le apenas o nome")
    monkeypatch.setattr(envio_impressao, "_arquivos_da_pasta", lambda pasta: [arquivo])
    [item] = envio_impressao.listar(tmp_path, config, maquinas={})
    medida = item["dimensao"]
    assert medida["largura_m"] == pytest.approx(largura)
    assert medida["altura_m"] == pytest.approx(altura)
    assert medida["unidade_usada"] == unidade
    assert item["area_total_m2"] == round(largura * altura, 2)


def test_unidade_reconhecida_colada_a_numero_preserva_regra_anterior():
    medida = extrair_dimensoes("1UN LONA 50x70CM01.pdf", {})
    assert medida["largura_m"] == pytest.approx(0.50)
    assert medida["altura_m"] == pytest.approx(0.70)
