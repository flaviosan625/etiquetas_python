"""
tests/test_motor_pdf_geometria.py — Testes unitários de geometria, matrizes 2D, Bézier e medição de caixa de tinta.
"""

import math
import pytest

from motor_pdf.geometria import (
    BoundingBox,
    Matriz2D,
    adicionar_bezier_ao_bbox,
    extremos_bezier_1d,
    ponto_bezier,
)
from motor_pdf.interpretador_stream import (
    calcular_caixa_da_arte,
    interpretar_stream,
)
from motor_pdf.leitor import Caixa, Pagina, PdfReader, abrir_pdf

PT_M = 72.0 / 0.0254


class DummyDoc:
    def _resolver_objeto(self, obj):
        return obj


def test_matriz_2d_identidade_e_transformacao():
    m = Matriz2D.identidade()
    assert (m.a, m.b, m.c, m.d, m.e, m.f) == (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)

    # Ponto transformado na identidade não muda
    x, y = m.transformar_ponto(10.0, 25.0)
    assert x == pytest.approx(10.0)
    assert y == pytest.approx(25.0)

    # Translação: e=50, f=100
    m_trans = Matriz2D(1.0, 0.0, 0.0, 1.0, 50.0, 100.0)
    x, y = m_trans.transformar_ponto(10.0, 20.0)
    assert x == pytest.approx(60.0)
    assert y == pytest.approx(120.0)

    # Escala: a=2, d=3
    m_escala = Matriz2D(2.0, 0.0, 0.0, 3.0, 0.0, 0.0)
    x, y = m_escala.transformar_ponto(10.0, 20.0)
    assert x == pytest.approx(20.0)
    assert y == pytest.approx(60.0)

    # Multiplicação: Escala x Translação
    m_comb = m_escala.multiplicar(m_trans)
    # (x, y) escalado depois transladado
    x, y = m_comb.transformar_ponto(10.0, 20.0)
    assert x == pytest.approx(70.0)
    assert y == pytest.approx(160.0)


def test_bounding_box_acumulacao_e_intersecao():
    bbox = BoundingBox()
    assert bbox.vazio is True

    bbox.adicionar_ponto(10.0, 20.0)
    assert bbox.vazio is False
    assert (bbox.x0, bbox.y0, bbox.x1, bbox.y1) == (10.0, 20.0, 10.0, 20.0)

    bbox.adicionar_retangulo(5.0, 30.0, 50.0, 15.0)
    assert (bbox.x0, bbox.y0, bbox.x1, bbox.y1) == (5.0, 15.0, 50.0, 30.0)

    # Interseção com máscara de clipping
    clip = BoundingBox(10.0, 10.0, 40.0, 25.0)
    recortado = bbox.intersecao(clip)
    assert recortado.vazio is False
    assert (recortado.x0, recortado.y0, recortado.x1, recortado.y1) == (10.0, 15.0, 40.0, 25.0)

    # Interseção sem sobreposição resulta em caixa vazia
    fora = BoundingBox(100.0, 100.0, 200.0, 200.0)
    assert bbox.intersecao(fora).vazio is True


def test_bezier_extremos_analiticos():
    # Curva com extremo interno (máximo local):
    # p0=0, p1=100, p2=100, p3=0 -> simétrica com pico em t=0.5
    ts = extremos_bezier_1d(0.0, 100.0, 100.0, 0.0)
    assert 0.5 in [pytest.approx(t, abs=1e-5) for t in ts]
    val_max = ponto_bezier(0.0, 100.0, 100.0, 0.0, 0.5)
    assert val_max == pytest.approx(75.0)

    bbox = BoundingBox()
    adicionar_bezier_ao_bbox(bbox, 0.0, 0.0, 50.0, 100.0, 50.0, 100.0, 100.0, 0.0)
    assert bbox.x0 == pytest.approx(0.0)
    assert bbox.x1 == pytest.approx(100.0)
    assert bbox.y0 == pytest.approx(0.0)
    assert bbox.y1 == pytest.approx(75.0)


def test_interpretador_stream_caminhos_e_recorte():
    # Stream com:
    # 1. Desenho de retângulo 0 0 200 100 preenchido
    stream = b"""
    q
    10 20 m
    110 20 l
    110 70 l
    10 70 l
    h
    f
    Q
    """
    bbox = interpretar_stream(stream)
    assert bbox.vazio is False
    assert (bbox.x0, bbox.y0, bbox.x1, bbox.y1) == (10.0, 20.0, 110.0, 70.0)


def test_interpretador_stream_recorte_w_n():
    # Um traçado maior (0 0 200 200), mas recortado por W n em (20 30 100 120)
    stream = b"""
    q
    20 30 80 90 re
    W n
    0 0 200 200 re
    f
    Q
    """
    bbox = interpretar_stream(stream)
    assert bbox.vazio is False
    # A área pintada deve ser exatamente a da máscara de recorte
    assert (bbox.x0, bbox.y0, bbox.x1, bbox.y1) == (20.0, 30.0, 100.0, 120.0)


def test_interpretador_stream_xobject_imagem():
    # Posicionamento de imagem via cm e Do:
    # CTM desloca para (50, 60) e amplia para (300, 400)
    stream = b"""
    q
    300 0 0 400 50 60 cm
    /Im1 Do
    Q
    """
    bbox = interpretar_stream(stream)
    assert bbox.vazio is False
    assert (bbox.x0, bbox.y0, bbox.x1, bbox.y1) == (50.0, 60.0, 350.0, 460.0)


def test_interpretador_stream_texto_e_matriz():
    stream = b"""
    BT
    /F1 10 Tf
    1 0 0 1 100 200 Tm
    (Arte Grafica) Tj
    ET
    """
    bbox = interpretar_stream(stream)
    assert bbox.vazio is False
    assert bbox.x0 == pytest.approx(100.0)
    assert bbox.y0 < 200.0  # descender
    assert bbox.y1 > 200.0  # ascender


def test_caixa_da_arte_franja_branca_descontada():
    # Simula página 102 x 102 pt, arte real 100 x 100 pt (1 pt de branco de cada lado)
    stream = b"""
    1 1 100 100 re
    f
    """
    doc_dummy = DummyDoc()
    raw_dict = {
        "/MediaBox": [0, 0, 102, 102],
        "/Contents": None,
    }
    pagina = Pagina(doc_dummy, 0, raw_dict)
    # Injeta stream na página
    pagina.obter_conteudo_bruto = lambda: stream

    caixa = calcular_caixa_da_arte(pagina)
    # A franja de 1pt é descontada:
    assert caixa.x0 == pytest.approx(1.0)
    assert caixa.y0 == pytest.approx(1.0)
    assert caixa.width == pytest.approx(100.0)
    assert caixa.height == pytest.approx(100.0)


def test_caixa_da_arte_franja_grande_preserva_design():
    # Se o desenho ocupar apenas 40% da página, o espaço branco é intencional (design)
    stream = b"""
    30 30 40 40 re
    f
    """
    doc_dummy = DummyDoc()
    raw_dict = {
        "/MediaBox": [0, 0, 100, 100],
        "/Contents": None,
    }
    pagina = Pagina(doc_dummy, 0, raw_dict)
    pagina.obter_conteudo_bruto = lambda: stream

    caixa = calcular_caixa_da_arte(pagina)
    # Manda a página inteira:
    assert caixa.x0 == pytest.approx(0.0)
    assert caixa.y0 == pytest.approx(0.0)
    assert caixa.width == pytest.approx(100.0)
    assert caixa.height == pytest.approx(100.0)


def test_caixa_da_arte_recorte_illustrator_chao_de_fabrica():
    # Caso real do chão de fábrica:
    # Arte de 2.00m x 1.00m com 1pt de franja e recorte W n aparando 0.5pt da direita
    largura_pt = 2.00 * PT_M
    altura_pt = 1.00 * PT_M
    franja_pt = 1.0

    # Recorte: (0.5, 1.0, 0.5 + 2.00 * PT_M, 1.0 + 1.00 * PT_M)
    # Desenho: (1.0, 1.0, 1.0 + 2.00 * PT_M, 1.0 + 1.00 * PT_M)
    stream = f"""
    q
    0.5 1.0 {largura_pt} {altura_pt} re
    W n
    {franja_pt} {franja_pt} {largura_pt} {altura_pt} re
    f
    Q
    """.encode("ascii")

    doc_dummy = DummyDoc()
    raw_dict = {
        "/MediaBox": [0, 0, largura_pt + 2 * franja_pt, altura_pt + 2 * franja_pt],
    }
    pagina = Pagina(doc_dummy, 0, raw_dict)
    pagina.obter_conteudo_bruto = lambda: stream

    caixa = calcular_caixa_da_arte(pagina)

    esperado_largura_pt = largura_pt - 0.5
    assert caixa.width == pytest.approx(esperado_largura_pt, abs=1e-5)
    assert caixa.height == pytest.approx(altura_pt, abs=1e-5)
    assert (caixa.width / PT_M) == pytest.approx(esperado_largura_pt / PT_M, abs=1e-6)
