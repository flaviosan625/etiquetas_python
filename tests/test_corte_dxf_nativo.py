"""
tests/test_corte_dxf_nativo.py — Testes da extração de contornos de corte e geração DXF R12
utilizando exclusivamente o motor nativo 'motor_pdf' (sem dependência de PyMuPDF).
"""

import math
import pathlib
import sys
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import motor_pdf
from motor_pdf import PdfName, PdfRef, PdfWriter
import corte_dxf
from corte_dxf import (
    CAMADA_EXTERNO,
    CAMADA_INTERNO,
    NOME_CAMADA,
    TOLERANCIA_MM,
    _PT_PARA_MM,
    converter,
    e_camada_de_corte,
    e_cor_de_corte,
    e_spot_de_corte,
    escrever_dxf,
    extrair_contornos,
)


def _criar_pdf_nativo(caminho, conteudo_bytes: bytes, largura_pt: float = 200, altura_pt: float = 200, recursos: dict = None):
    """Cria um PDF de teste 100% nativo com o PdfWriter do motor_pdf."""
    writer = PdfWriter()
    writer.adicionar_pagina(largura_pt, altura_pt, recursos or {}, conteudo_bytes)
    dados = writer.salvar(caminho)
    return pathlib.Path(caminho)


# ==============================================================================
# 1. Extração nativa de corte (CMYK, Spot Color, RGB, Camada OCG)
# ==============================================================================

def test_extracao_corte_pdf_nativo_cmyk_magenta(tmp_path):
    """Garante extração de corte em PDF nativo com CMYK Magenta puro (0 1 0 0 K)."""
    # Retângulo de 100 pt de largura x 50 pt de altura
    conteudo = b"0 1 0 0 K 10 20 100 50 re S\n"
    pdf = _criar_pdf_nativo(tmp_path / "cmyk_magenta.pdf", conteudo, 200, 100)

    polilinhas, relatorio = extrair_contornos(pdf)

    assert relatorio["de_corte"] == 1
    assert relatorio["descartados"] == 0
    assert relatorio["criterio"] == "cor"
    assert len(polilinhas) == 1

    poli = polilinhas[0]
    xs = [p[0] for p in poli]
    ys = [p[1] for p in poli]

    # Medidas em mm (100 pt = 35.277 mm, 50 pt = 17.638 mm)
    largura_mm = max(xs) - min(xs)
    altura_mm = max(ys) - min(ys)
    assert largura_mm == pytest.approx(100 * _PT_PARA_MM, abs=0.01)
    assert altura_mm == pytest.approx(50 * _PT_PARA_MM, abs=0.01)


def test_extracao_corte_pdf_nativo_spot_color_cutcontour(tmp_path):
    """Garante detecção de Spot Color /CutContour (padrão Zünd/Summa/Mimaki/Roland)."""
    writer = PdfWriter()
    cs_id = writer.alocar_id()
    writer.objetos[cs_id] = [
        PdfName("/Separation"),
        PdfName("/CutContour"),
        PdfName("/DeviceCMYK"),
        {
            PdfName("/FunctionType"): 2,
            PdfName("/Domain"): [0.0, 1.0],
            PdfName("/C0"): [0.0, 0.0, 0.0, 0.0],
            PdfName("/C1"): [0.0, 1.0, 0.0, 0.0],
            PdfName("/N"): 1.0,
        },
    ]

    recursos = {
        PdfName("/ColorSpace"): {
            PdfName("/CutContour"): PdfRef(cs_id, 0),
        }
    }
    conteudo = b"/CutContour CS 1.0 SCN 15 15 70 70 re S\n"
    writer.adicionar_pagina(200, 200, recursos, conteudo)
    caminho = tmp_path / "spot_cutcontour.pdf"
    writer.salvar(caminho)

    polilinhas, relatorio = extrair_contornos(caminho)

    assert relatorio["de_corte"] == 1
    assert relatorio["criterio"] == "cor"
    assert len(polilinhas) == 1


def test_extracao_corte_pdf_nativo_camada_ocg(tmp_path):
    """Garante prioridade de camada OCG nomeada CutContour mesmo com traço preto."""
    writer = PdfWriter()
    ocg_id = writer.alocar_id()
    writer.objetos[ocg_id] = {
        PdfName("/Type"): PdfName("/OCG"),
        PdfName("/Name"): b"CutContour",
    }
    recursos = {
        PdfName("/Properties"): {
            PdfName("/MC0"): PdfRef(ocg_id, 0),
        }
    }
    # Traço preto (0 0 0 RG), mas dentro de /OC /MC0 BDC
    conteudo = b"/OC /MC0 BDC 0 0 0 RG 10 10 80 80 re S EMC\n"
    writer.adicionar_pagina(200, 200, recursos, conteudo)
    caminho = tmp_path / "camada_ocg.pdf"
    writer.salvar(caminho)

    polilinhas, relatorio = extrair_contornos(caminho)

    assert relatorio["criterio"] == "camada"
    assert "CutContour" in relatorio["camadas"]
    assert relatorio["de_corte"] == 1
    assert len(polilinhas) == 1


# ==============================================================================
# 2. Filtragem de cores (Preto, Azul, Vermelho descartados)
# ==============================================================================

def test_filtragem_cores_descarta_preto_azul_vermelho(tmp_path):
    """Garante que preto, azul e vermelho são descartados e só magenta vira corte."""
    conteudo = (
        b"0 0 0 1 K 10 10 30 30 re S\n"         # Preto CMYK
        b"1 1 0 0 K 50 10 30 30 re S\n"         # Azul CMYK (Cyan + Magenta)
        b"0 1 1 0 K 90 10 30 30 re S\n"         # Vermelho CMYK (Magenta + Yellow)
        b"0 1 0 0 K 130 10 30 30 re S\n"        # Magenta Puro (Corte)
    )
    pdf = _criar_pdf_nativo(tmp_path / "cores_mistas.pdf", conteudo, 200, 100)

    polilinhas, relatorio = extrair_contornos(pdf)

    assert relatorio["desenhos"] == 4
    assert relatorio["de_corte"] == 1
    assert relatorio["descartados"] == 3
    assert len(polilinhas) == 1


def test_reconhecimento_funcoes_de_cor_e_spot():
    """Valida as funções puras de validação de cor e spot."""
    # CMYK
    assert e_cor_de_corte((0.0, 1.0, 0.0, 0.0))
    assert e_cor_de_corte((0.05, 0.95, 0.02, 0.0))
    assert not e_cor_de_corte((0.0, 0.0, 0.0, 1.0))   # Preto
    assert not e_cor_de_corte((1.0, 0.0, 0.0, 0.0))   # Ciano
    assert not e_cor_de_corte((0.0, 0.0, 1.0, 0.0))   # Amarelo

    # RGB
    assert e_cor_de_corte((1.0, 0.0, 1.0))
    assert not e_cor_de_corte((0.0, 0.0, 0.0))
    assert not e_cor_de_corte((1.0, 0.0, 0.0))

    # Spot Names
    assert e_spot_de_corte("CutContour")
    assert e_spot_de_corte("/CutContour")
    assert e_spot_de_corte("/Separation/CutContour")
    assert e_spot_de_corte("Cut_Contour")
    assert e_spot_de_corte("CORTE")
    assert e_spot_de_corte("RECORTE")
    assert e_spot_de_corte("Thru-cut")
    assert not e_spot_de_corte("Pantone 186 C")
    assert not e_spot_de_corte("Fold")

    # Camadas
    assert e_camada_de_corte("CutContour")
    assert e_camada_de_corte("corte")
    assert e_camada_de_corte("CORTE")
    assert e_camada_de_corte("Recorte")
    assert not e_camada_de_corte("Camada 1")


# ==============================================================================
# 3. Achatamento geométrico de curvas de Bézier cúbicas
# ==============================================================================

def test_achatamento_curvas_bezier(tmp_path):
    """Garante que curvas de Bézier cúbicas (c, v, y) viram retas discretizadas respeitando TOLERANCIA_MM."""
    # Um semi-círculo aproximado com Bézier cúbica:
    # (0, 0) até (100, 0) com pontos de controle (0, 55.2) e (100, 55.2)
    conteudo = b"0 1 0 0 K 0 0 m 0 55.228 100 55.228 100 0 c S\n"
    pdf = _criar_pdf_nativo(tmp_path / "curva_bezier.pdf", conteudo, 200, 100)

    polilinhas, relatorio = extrair_contornos(pdf, tolerancia_mm=TOLERANCIA_MM)

    assert relatorio["de_corte"] == 1
    assert len(polilinhas) == 1
    pontos = polilinhas[0]

    # Uma curva de Bézier achatada deve gerar múltiplos vértices intermediários
    assert len(pontos) >= 8

    # Início e fim exatos
    p_ini = pontos[0]
    p_fim = pontos[-1]
    assert p_ini[0] == pytest.approx(0.0, abs=1e-3)
    assert p_ini[1] == pytest.approx(0.0, abs=1e-3)
    assert p_fim[0] == pytest.approx(100 * _PT_PARA_MM, abs=1e-3)
    assert p_fim[1] == pytest.approx(0.0, abs=1e-3)

    # O topo da curva deve estar próximo de 55.228 * 0.75 ~= 41.4 pt
    ys = [p[1] for p in pontos]
    max_y = max(ys)
    assert max_y > 10.0


def test_operadores_curva_v_e_y(tmp_path):
    """Testa operadores v e y de Bézier cúbica com controle implícito."""
    conteudo = (
        b"0 1 0 0 K 0 0 m 20 40 50 40 v S\n"        # v: p1 = cur_pt
        b"0 1 0 0 K 60 0 m 80 40 100 40 y S\n"       # y: p2 = p3
    )
    pdf = _criar_pdf_nativo(tmp_path / "curvas_v_y.pdf", conteudo, 200, 100)

    polilinhas, relatorio = extrair_contornos(pdf)

    assert relatorio["de_corte"] == 2
    assert len(polilinhas) == 2
    assert len(polilinhas[0]) >= 4
    assert len(polilinhas[1]) >= 4


# ==============================================================================
# 4. Saída DXF R12 limpa e compatível com mesas CNC
# ==============================================================================

def test_saida_dxf_r12_estrutura_e_medidas(tmp_path):
    """
    Verifica a estrutura completa do DXF R12 ASCII:
    - HEADER com $ACADVER AC1009, $INSUNITS 4 (mm), $MEASUREMENT 1
    - TABLES com TABLE LAYER e camada CORTE
    - BLOCKS limpo
    - ENTITIES com POLYLINE, VERTEX e SEQEND
    - 1:1 em milímetros
    """
    conteudo = b"0 1 0 0 K 0 0 100 50 re S\n"
    pdf = _criar_pdf_nativo(tmp_path / "peca_retangular.pdf", conteudo, 200, 100)

    relatorio = converter(pdf)
    assert relatorio["dxf"] is not None

    dxf_path = pathlib.Path(relatorio["dxf"])
    assert dxf_path.exists()

    texto = dxf_path.read_text(encoding="ascii")

    # 1. Cabeçalho R12 limpo
    assert "SECTION\n2\nHEADER" in texto
    assert "$ACADVER\n1\nAC1009" in texto
    assert "$INSUNITS\n70\n4" in texto
    assert "$MEASUREMENT\n70\n1" in texto

    # 2. Tabelas e camadas
    assert "SECTION\n2\nTABLES" in texto
    assert "TABLE\n2\nLAYER" in texto
    assert "CORTE" in texto

    # 3. Seção BLOCKS
    assert "SECTION\n2\nBLOCKS" in texto

    # 4. Entidades
    assert "SECTION\n2\nENTITIES" in texto
    assert "POLYLINE" in texto
    assert "VERTEX" in texto
    assert "SEQEND" in texto
    assert "ENDSEC\n0\nEOF" in texto

    # 5. Coordenadas em milímetros escala 1:1
    # 100 pt = 35.2778 mm
    assert "35.2778" in texto


def test_aninhamento_letras_com_furo_classificacao(tmp_path):
    """Verifica separação de CORTE INTERNO e CORTE EXTERNO para percursos de fresa."""
    conteudo = (
        b"0 1 0 0 K 0 0 100 100 re S\n"       # Contorno externo
        b"0 1 0 0 K 25 25 50 50 re S\n"        # Furo interno
    )
    pdf = _criar_pdf_nativo(tmp_path / "letra_O.pdf", conteudo, 200, 200)

    relatorio = converter(pdf)
    assert relatorio["externos"] == 1
    assert relatorio["internos"] == 1

    texto = pathlib.Path(relatorio["dxf"]).read_text(encoding="ascii")
    assert CAMADA_EXTERNO in texto
    assert CAMADA_INTERNO in texto


# ==============================================================================
# 5. Compatibilidade retroativa com PyMuPDF
# ==============================================================================

def test_retrocompatibilidade_objeto_pagina_pymupdf(tmp_path):
    """Se um objeto de página do PyMuPDF for passado, deve aceitar graciosamente."""
    try:
        import pymupdf
    except ImportError:
        pytest.skip("PyMuPDF não instalado no ambiente.")

    doc = pymupdf.open()
    page = doc.new_page(width=200, height=100)
    page.draw_rect(pymupdf.Rect(10, 10, 90, 60), color=(0.922, 0.229, 0.506), width=1)

    # Passa o próprio objeto de página diretamente
    polilinhas, relatorio = extrair_contornos(page)

    assert relatorio["de_corte"] == 1
    assert len(polilinhas) == 1
    doc.close()
