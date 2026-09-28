"""
Encaixe do lote inteiro (aproveitamento.py) — rolo e chapa.

Pedido do usuário (28/09/2026): economizar ao máximo, e o desperdício contado
pelo lote, não por peça. Módulo puro: nenhum teste toca arquivo.
"""
import itertools
import pathlib
import random
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import pytest

import aproveitamento as ap


def _sobrepoe(a, b):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah


def _conferir_encaixe(pedaco, pecas):
    """Toda peça dentro do material, nenhuma em cima da outra, todas postas."""
    assert len(pedaco.postas) == len(pecas)
    for x, y, w, h in pedaco.postas:
        assert x >= 0 and y >= 0 and x + w <= pedaco.largura and y + h <= pedaco.altura
    for a, b in itertools.combinations(pedaco.postas, 2):
        assert not _sobrepoe(a, b), (a, b)
    postas = sorted(tuple(sorted((w, h))) for _, _, w, h in pedaco.postas)
    assert postas == sorted(tuple(sorted(p)) for p in pecas)


# ------------------------------------------------------------------ rolo

def test_pecas_saem_lado_a_lado_no_rolo():
    """Três peças de 1,00 m num rolo de 3,20: 2 m de rolo, não 6 m como na conta por peça."""
    r = ap.calcular_lote([(1.0, 2.0, 3)], "rolo", 3.20, 50)

    assert r["metros"] == pytest.approx(2.0)
    assert r["desperdicio_m2"] == pytest.approx(3.20 * 2.0 - 6.0)
    assert r["area_consumida_m2"] == pytest.approx(6.4)
    assert r["rolos"] == pytest.approx(2.0 / 50)


def test_desperdicio_e_do_lote_nao_a_soma_por_peca():
    """A conta antiga dava (3,20 − 1,00) × 2,00 × 3 = 13,2 m² de sobra; o lote dá 0,4."""
    r = ap.calcular_lote([(1.0, 2.0, 3)], "rolo", 3.20, 50)
    assert r["desperdicio_m2"] < 1.0


def test_rolo_nunca_gasta_mais_que_uma_peca_por_fileira():
    """O pior caso do lote é a conta antiga (cada peça sozinha na largura)."""
    aleatorio = random.Random(3)
    for _ in range(40):
        pecas = [(aleatorio.randint(5, 150) / 100, aleatorio.randint(5, 300) / 100, aleatorio.choice([1, 2, 3]))
                 for _ in range(aleatorio.randint(1, 25))]
        largura = aleatorio.choice([1.27, 3.20])
        pecas = [p for p in pecas if min(p[0], p[1]) <= largura]
        if not pecas:
            continue
        conta_antiga = sum(max(w, h) * q for w, h, q in pecas)
        r = ap.calcular_lote(pecas, "rolo", largura, 50)
        assert r["metros"] <= conta_antiga + 1e-9
        assert r["metros"] >= r["area_pecas_m2"] / largura - 1e-9


def test_encaixe_no_rolo_e_valido():
    aleatorio = random.Random(11)
    for _ in range(25):
        pecas = [(aleatorio.randint(50, 1270), aleatorio.randint(50, 2500)) for _ in range(aleatorio.randint(1, 40))]
        for ordem, politica, divisao in itertools.product(ap._ORDENS, ("livre", "estreita"),
                                                          ("prateleira", "coluna")):
            rolo = ap._encaixar_no_rolo(pecas, 1270, ordem, politica, divisao)
            _conferir_encaixe(rolo, pecas)


def test_lona_maior_que_o_rolo_entra_em_faixas():
    """4 × 5 m num rolo de 3,20: duas faixas de 4 m (8 m), emenda não contada e assinalada."""
    r = ap.calcular_lote([(4.0, 5.0, 1)], "rolo", 3.20, 50)

    assert r["metros"] == pytest.approx(8.0)
    assert r["pecas_divididas"] == 1
    assert r["area_pecas_m2"] == pytest.approx(20.0)


def test_faixa_que_sobra_da_lona_grande_divide_o_rolo_com_outra_peca():
    """A faixa de 1,80 m da lona grande deixa 1,40 m do lado — cabe a peça de 1,20."""
    sozinha = ap.calcular_lote([(4.0, 5.0, 1)], "rolo", 3.20, 50)
    junto = ap.calcular_lote([(4.0, 5.0, 1), (1.2, 4.0, 1)], "rolo", 3.20, 50)
    assert junto["metros"] == pytest.approx(sozinha["metros"])


def test_muitas_pecas_iguais_viram_blocos_e_a_conta_segue_boa():
    """500 adesivos de 10 × 10 cm num rolo de 1,27: 12 por fileira, 42 fileiras."""
    inicio = time.time()
    r = ap.calcular_lote([(0.10, 0.10, 500)], "rolo", 1.27, 50)

    assert time.time() - inicio < 2
    assert r["metros"] == pytest.approx(4.2)
    assert r["pecas"] == 500
    assert r["area_pecas_m2"] == pytest.approx(5.0)


# ----------------------------------------------------------------- chapa

def test_chapa_e_encaixe_de_verdade_e_nao_fila_de_faixas():
    """PS 1,80 × 0,50 × 4 numa chapa de 2,00 × 1,00: duas por chapa, 2 chapas."""
    r = ap.calcular_lote([(1.80, 0.50, 4)], "chapa", 2.00, 1.00)

    assert r["chapas"] == 2
    assert r["desperdicio_m2"] == pytest.approx(4.0 - 3.6)


def test_sobra_da_chapa_e_a_chapa_inteira_que_saiu_do_estoque():
    """Uma peça numa chapa: sai a chapa toda; o resto aparece como retalho."""
    r = ap.calcular_lote([(1.80, 0.50, 1)], "chapa", 2.00, 1.00)

    assert r["chapas"] == 1
    assert r["area_consumida_m2"] == pytest.approx(2.0)
    assert r["desperdicio_m2"] == pytest.approx(1.1)
    assert r["maior_retalho_m"] == pytest.approx((2.0, 0.5))


def test_medida_exata_cabe_sem_a_virgula_flutuante_atrapalhar():
    """1,26 + 0,94 = 2,20: cabe na chapa de 2,20, em milímetros inteiros."""
    r = ap.calcular_lote([(1.26, 1.0, 1), (0.94, 1.0, 1)], "chapa", 2.20, 1.00)
    assert r["chapas"] == 1
    assert r["desperdicio_m2"] == pytest.approx(0.0)


def test_peca_que_gira_pra_caber_na_chapa():
    """0,90 × 1,90 só entra na chapa de 2,00 × 1,00 deitada — e não é dividida por isso."""
    r = ap.calcular_lote([(0.90, 1.90, 1)], "chapa", 2.00, 1.00)
    assert r["chapas"] == 1
    assert r["pecas_divididas"] == 0


def test_painel_maior_que_a_chapa_vira_grade():
    """3,00 × 1,50 numa chapa de 2,00 × 1,00: três chapas (em pé), como a estimativa antiga."""
    r = ap.calcular_lote([(3.0, 1.5, 1)], "chapa", 2.00, 1.00)

    assert r["chapas"] == 3
    assert r["pecas_divididas"] == 1


def test_encaixe_em_chapas_e_valido():
    aleatorio = random.Random(5)
    for _ in range(15):
        largura, altura = aleatorio.choice([(1220, 2440), (2000, 1000), (1850, 2700)])
        pecas = [(aleatorio.randint(60, 1200), aleatorio.randint(60, 1000)) for _ in range(aleatorio.randint(1, 30))]
        for ordem, regra, divisao in itertools.product(ap._ORDENS, ("area", "lado", "baixo"),
                                                       ("menor_sobra", "maior_sobra", "maior_area")):
            chapas = ap._encaixar_em_chapas(pecas, largura, altura, ordem, regra, divisao)
            postas = []
            for chapa in chapas:
                for x, y, w, h in chapa.postas:
                    assert x + w <= largura and y + h <= altura
                for a, b in itertools.combinations(chapa.postas, 2):
                    assert not _sobrepoe(a, b)
                postas += [tuple(sorted((w, h))) for _, _, w, h in chapa.postas]
            assert sorted(postas) == sorted(tuple(sorted(p)) for p in pecas)


def test_chapas_nunca_menos_que_a_area_pede():
    aleatorio = random.Random(8)
    for _ in range(20):
        pecas = [(aleatorio.randint(10, 120) / 100, aleatorio.randint(10, 240) / 100, aleatorio.choice([1, 2]))
                 for _ in range(aleatorio.randint(1, 20))]
        r = ap.calcular_lote(pecas, "chapa", 1.22, 2.44)
        assert r["chapas"] >= r["area_pecas_m2"] / (1.22 * 2.44) - 1e-9
        assert 0 < r["aproveitamento"] <= 1


def test_partes_da_peca():
    assert ap.partes_da_peca(1.0, 2.0, "rolo", 3.20, 50) == 1
    assert ap.partes_da_peca(4.0, 5.0, "rolo", 3.20, 50) == 2
    assert ap.partes_da_peca(3.0, 1.5, "chapa", 2.0, 1.0) == 3


def test_lote_sem_medida_nao_da_numero():
    assert ap.calcular_lote([], "rolo", 3.20, 50) is None
    assert ap.calcular_lote([(0, 1.0, 1)], "chapa", 2.0, 1.0) is None


# --------------------------------------------------------------- materiais

_MATERIAIS = {
    "LONA": {"tipo": "rolo", "largura_cm": 320.0, "comprimento_cm": 5000.0},
    "ADESIVO": {"tipo": "rolo", "largura_cm": 127.0, "comprimento_cm": 5000.0},
    "PS": {"tipo": "chapa", "largura_cm": 200.0, "comprimento_cm": 100.0},
}


def _item(categoria, largura, altura, quantidade=1, variante=None, extra=None):
    return {"categoria": categoria, "quantidade": quantidade, "variante": variante, "categoria_extra": extra,
            "dimensao": {"largura_m": largura, "altura_m": altura, "area_m2": largura * altura}}


def test_material_composto_entra_nos_dois_lotes_e_o_adesivo_encaixa_com_o_resto():
    """O adesivo do PS ADESIVADO é o mesmo rolo do adesivo solto: um lote só."""
    itens = [_item("PS", 1.0, 0.5, 2, variante={"espessura": "2MM", "cor": "BRANCO"}, extra="ADESIVO"),
             _item("ADESIVO", 0.25, 0.5, 1)]
    consumo = {c["categoria"]: c for c in ap.consumo_por_material(itens, _MATERIAIS)}

    assert set(consumo) == {"PS", "ADESIVO"}
    assert consumo["PS"]["variante"] == {"espessura": "2MM", "cor": "BRANCO"}
    assert consumo["ADESIVO"]["variante"] is None
    assert consumo["ADESIVO"]["pecas"] == 3
    assert consumo["PS"]["chapas"] == 1


def test_variante_e_o_que_a_chapa_e_nao_o_que_o_cadastro_carrega():
    """Mesma espessura e cor, uma cópia com preço e outra sem: é o mesmo lote de chapa."""
    itens = [_item("PS", 1.0, 1.0, variante={"espessura": "2MM", "cor": "BRANCO", "preco_m2": 40.0}),
             _item("PS", 1.0, 1.0, variante={"espessura": "2MM", "cor": "BRANCO"}),
             _item("PS", 1.0, 1.0, variante={"espessura": "3MM", "cor": "BRANCO"})]
    consumo = ap.consumo_por_material(itens, _MATERIAIS)

    assert [c["chapas"] for c in consumo] == [1, 1]


def test_item_sem_medida_ou_sem_cadastro_fica_de_fora():
    itens = [{"categoria": "LONA", "quantidade": 1, "dimensao": None}, _item("MDF", 1.0, 1.0)]
    assert ap.consumo_por_material(itens, _MATERIAIS) == []


def test_descrever_diz_que_e_estimativa_e_a_emenda():
    consumo = ap.consumo_por_material([_item("LONA", 4.0, 5.0)], _MATERIAIS)[0]
    texto = ap.descrever(consumo)
    assert "estimativa" in texto
    assert "emenda não contada" in texto
    assert "8.00 m de rolo" in texto
