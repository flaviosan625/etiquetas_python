import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from dimensoes import (
    contem_palavra, extrair_dimensoes, calcular_desperdicio_item, extrair_quantidade,
    identificar_variante, formatar_variante, calcular_desperdicio_chapa_grande,
)


def test_contem_palavra_evita_falso_positivo_em_substring():
    assert contem_palavra("BANNER_XPS_60X40.PDF", "PS") is False
    assert contem_palavra("PLACA_PS_60X40.PDF", "PS") is True


def test_contem_palavra_aceita_numero_colado_depois():
    # nome real: "VINIL150" (Vinil, 150cm de largura), sem separador
    assert contem_palavra("1UN VINIL150 DE LARGURA IMPRESSO.PDF", "VINIL") is True


def test_contem_palavra_ainda_rejeita_letra_colada_depois():
    # "VINILICO" não devia contar como "VINIL"
    assert contem_palavra("BANNER VINILICO ESPECIAL.PDF", "VINIL") is False


def test_extrair_dimensoes_assume_cm_quando_sem_unidade():
    d = extrair_dimensoes("banner_58x60.pdf", {})
    assert d is not None
    assert d["unidade_usada"] == "CM"
    assert round(d["area_m2"], 4) == round(0.58 * 0.60, 4)


def test_extrair_dimensoes_aceita_virgula_decimal():
    d = extrair_dimensoes("placa_1,5x2M.pdf", {})
    assert d["unidade_usada"] == "M"
    assert round(d["largura_m"], 2) == 1.5


def test_extrair_dimensoes_corrige_typo_configuravel():
    d = extrair_dimensoes("banner_58x60XM.pdf", {"XM": "CM"})
    assert d["unidade_usada"] == "CM"
    assert d["unidade_corrigida"] is True


def test_extrair_dimensoes_novo_typo_configurado_funciona():
    # simula um erro de digitação novo, cadastrado só no config,
    # sem precisar mexer no código
    d = extrair_dimensoes("placa_40x50NM.pdf", {"NM": "MM"})
    assert d["unidade_usada"] == "MM"
    assert d["unidade_corrigida"] is True


def test_extrair_dimensoes_sem_medida_no_nome():
    assert extrair_dimensoes("arte_final_cliente.pdf", {}) is None


def test_extrair_dimensoes_usa_ultima_ocorrencia():
    d = extrair_dimensoes("pedido_123x456_58x60cm.pdf", {})
    assert round(d["largura_m"], 2) == 0.58


def test_extrair_quantidade_reconhece_prefixo_un():
    assert extrair_quantidade("1UN ADESIVO IMPRESSA 2.30X2.30M.pdf") == (1, True)
    assert extrair_quantidade("12UN LONA banner.pdf") == (12, True)
    assert extrair_quantidade("3 UN mdf recorte.pdf") == (3, True)


def test_extrair_quantidade_assume_1_quando_ausente():
    assert extrair_quantidade("banner_58x60.pdf") == (1, False)


_VARIANTES_PVC = [
    {"espessura": "10MM", "cor": "BRANCO"},
    {"espessura": "10MM", "cor": "PRETO"},
    {"espessura": "20MM", "cor": "BRANCO"},
    {"espessura": "20MM", "cor": "PRETO"},
]


def test_identificar_variante_encontra_espessura_e_cor():
    v = identificar_variante("1UN PVC 10MM RECORTE_PRETO_Credenciamento.pdf", _VARIANTES_PVC)
    assert v == {"espessura": "10MM", "cor": "PRETO"}


def test_identificar_variante_nao_bate_sem_as_duas_palavras():
    # só a espessura, sem a cor — não deve "adivinhar"
    assert identificar_variante("1UN PVC 10MM RECORTE.pdf", _VARIANTES_PVC) is None


def test_identificar_variante_sem_lista_retorna_none():
    assert identificar_variante("1UN MDF 9MM RECORTE.pdf", []) is None


_VARIANTES_MDF = [
    {"espessura": "6MM"}, {"espessura": "9MM"}, {"espessura": "15MM"}, {"espessura": "18MM"},
    {"espessura": "6MM", "cor": "VERDE", "rotulo": "MDF HIDRO"},
    {"espessura": "9MM", "cor": "VERDE", "rotulo": "MDF HIDRO"},
]


def test_identificar_variante_so_espessura_sem_cor_no_arquivo():
    # MDF cru: nunca tem cor no nome, a variante não exige cor
    v = identificar_variante("1UN MDF 9MM RECORTE_Tiktok Criadores.pdf", _VARIANTES_MDF)
    assert v == {"espessura": "9MM"}


def test_identificar_variante_especifica_tem_prioridade_sobre_generica():
    # com "verde" no nome, tem que cair na variante hidro, não na crua de mesma espessura
    v = identificar_variante("1UN MDF_VERDE_9MM_RECORTE.pdf", _VARIANTES_MDF)
    assert v == {"espessura": "9MM", "cor": "VERDE", "rotulo": "MDF HIDRO"}


def test_formatar_variante_com_cor():
    assert formatar_variante({"espessura": "10MM", "cor": "PRETO"}) == "10MM · PRETO"


def test_formatar_variante_com_rotulo_prioriza_rotulo():
    assert formatar_variante({"espessura": "9MM", "cor": "VERDE", "rotulo": "MDF HIDRO"}) == "9MM · MDF HIDRO"


def test_formatar_variante_so_espessura():
    assert formatar_variante({"espessura": "9MM"}) == "9MM"


def test_formatar_variante_none():
    assert formatar_variante(None) == ""


def test_calcular_desperdicio_chapa_grande_escolhe_orientacao_com_menos_chapas():
    # peça real (BASE_RAMPA do pedido CIF): 5.00 x 3.60m numa chapa de MDF 1.85 x 2.70m
    # sem girar: 3 colunas x 2 linhas = 6 chapas; girada: 2x2 = 4 chapas
    dimensao = {"largura_m": 5.00, "altura_m": 3.60}
    r = calcular_desperdicio_chapa_grande(dimensao, 1.85, 2.70)
    assert r["total_chapas"] == 4
    assert r["girada"] is True
    assert round(r["desperdicio_m2"], 2) == round(4 * 1.85 * 2.70 - 5.00 * 3.60, 2)


def test_calcular_desperdicio_chapa_grande_sem_diferenca_de_orientacao():
    dimensao = {"largura_m": 5.00, "altura_m": 4.99}
    r = calcular_desperdicio_chapa_grande(dimensao, 1.85, 2.70)
    assert r["total_chapas"] == 6


def test_calcular_desperdicio_peca_cabe_no_rolo():
    dimensao = {"largura_m": 0.5, "altura_m": 2.0}
    r = calcular_desperdicio_item(dimensao, 1.0)
    assert r is not None
    assert round(r["desperdicio_m2"], 2) == round((1.0 - 0.5) * 2.0, 2)


def test_calcular_desperdicio_peca_nao_cabe_no_rolo():
    # mesmo o lado menor da peça (1.5m) é maior que a largura do rolo (1.0m)
    dimensao = {"largura_m": 2.0, "altura_m": 1.5}
    r = calcular_desperdicio_item(dimensao, 1.0)
    assert r is None
