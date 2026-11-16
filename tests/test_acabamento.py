import pathlib
import pytest

import acabamento
from motor_pdf import PdfWriter, abrir_pdf


def _criar_pdf_lona_teste(caminho, largura_m=2.0, altura_m=1.0):
    """Cria um PDF de teste nativo representando uma lona de 2,00 x 1,00 m via motor_pdf."""
    pt_w = largura_m * acabamento.PT_POR_M
    pt_h = altura_m * acabamento.PT_POR_M

    writer = PdfWriter(versao="1.6")
    # Fundo azul para simular arte de lona
    conteudo = f"q 0.1 0.2 0.8 rg 0 0 1 RG 0 0 {pt_w:.2f} {pt_h:.2f} re B Q\n".encode("ascii")
    writer.adicionar_pagina(largura_pt=pt_w, altura_pt=pt_h, recursos={}, conteudo_bytes=conteudo)
    writer.salvar(caminho)


class MockPageDraw:
    """Mock de página gráfica com suporte a primitivas de desenho (compatibilidade)."""
    def __init__(self, width=1000, height=1000):
        self.width = width
        self.height = height
        self.rect = type("Rect", (), {
            "x0": 0.0,
            "y0": 0.0,
            "x1": float(width),
            "y1": float(height),
            "width": float(width),
            "height": float(height),
        })()
        self.desenhos = []

    def draw_circle(self, ponto, raio, color=None, fill=None, width=1.0):
        self.desenhos.append({"tipo": "circulo", "ponto": ponto, "raio": raio, "color": color, "fill": fill, "width": width})

    def draw_line(self, p1, p2, color=None, width=1.0):
        self.desenhos.append({"tipo": "linha", "p1": p1, "p2": p2, "color": color, "width": width})

    def draw_rect(self, rect, color=None, width=1.0):
        self.desenhos.append({"tipo": "retangulo", "rect": rect, "color": color, "width": width})

    def get_drawings(self):
        return self.desenhos


def test_calcular_posicoes_ilhos_apenas_cantos():
    largura_pt = 1000.0
    altura_pt = 500.0
    recuo_m = 0.025
    posicoes = acabamento.calcular_posicoes_ilhos(
        largura_pt, altura_pt, recuo_borda_m=recuo_m, cantos_apenas=True
    )
    assert len(posicoes) == 4
    # Confere se os 4 cantos estão nos recuos
    recuo_pt = recuo_m * acabamento.PT_POR_M
    assert posicoes[0] == (recuo_pt, recuo_pt)
    assert posicoes[1] == (largura_pt - recuo_pt, recuo_pt)
    assert posicoes[2] == (largura_pt - recuo_pt, altura_pt - recuo_pt)
    assert posicoes[3] == (recuo_pt, altura_pt - recuo_pt)


def test_calcular_posicoes_ilhos_distribuicao_perimetro():
    # Lona de 2,00 m x 1,00 m com ilhós a cada 0.40 m (40 cm)
    # No topo (2m): ~5 furos
    # Na base (2m): ~5 furos
    # Nas laterais (1m): ~2 furos intermediários cada
    # Total esperado: ~14 a 16 furos no perímetro
    w_pt = 2.0 * acabamento.PT_POR_M
    h_pt = 1.0 * acabamento.PT_POR_M
    posicoes = acabamento.calcular_posicoes_ilhos(
        w_pt, h_pt, espacamento_m=0.40, recuo_borda_m=0.025, cantos_apenas=False
    )
    assert len(posicoes) >= 12
    assert len(posicoes) <= 18


def test_aplicar_marcas_ilhos_pdf(tmp_path):
    origem = tmp_path / "lona_original.pdf"
    destino = tmp_path / "lona_com_ilhos.pdf"
    _criar_pdf_lona_teste(origem, largura_m=2.0, altura_m=1.0)

    resultado = acabamento.aplicar_marcas_ilhos_pdf(
        origem, destino, espacamento_m=0.40, recuo_borda_m=0.025
    )

    assert destino.exists()
    assert resultado["total_paginas"] == 1
    assert resultado["total_furos"] > 0
    assert resultado["total_furos"] == resultado["furos_por_pagina"][0]

    # Abre o destino com motor_pdf e confirma presença de comandos gráficos de ilhós
    with abrir_pdf(destino) as doc:
        assert len(doc.paginas) == 1
        conteudo = doc.paginas[0].obter_conteudo_bruto()
        assert b"q" in conteudo
        assert b"RG" in conteudo
        assert b"0.552285" in conteudo or b"0.5523" in conteudo or b"c\n" in conteudo


def test_adicionar_linha_cutcontour():
    page = MockPageDraw(width=500, height=500)
    desenhos_antes = len(page.get_drawings())

    acabamento.adicionar_linha_cutcontour(page)
    desenhos_depois = len(page.get_drawings())

    assert desenhos_depois > desenhos_antes
    # Confere se o último traçado desenhado corresponde à linha de contorno
    ultimo = page.get_drawings()[-1]
    assert ultimo["rect"] == page.rect
    assert ultimo["width"] == 1.0


def test_aplicar_borda_solda_pdf(tmp_path):
    origem = tmp_path / "banner_solda.pdf"
    destino = tmp_path / "banner_solda_4cm.pdf"
    # Lona de 1.0 x 1.0 m
    _criar_pdf_lona_teste(origem, largura_m=1.0, altura_m=1.0)

    # Aplica 4 cm (0.04 m) de solda
    resultado = acabamento.aplicar_borda_solda_pdf(origem, destino, borda_solda_m=0.04)

    assert destino.exists()
    with abrir_pdf(destino) as doc_dest:
        page_dest = doc_dest.paginas[0]

        # Medidas esperadas: 1.00 + 2 * 0.04 = 1.08 m
        esperado_pt = 1.08 * acabamento.PT_POR_M
        assert abs(page_dest.mediabox.width - esperado_pt) < 1.0
        assert abs(page_dest.mediabox.height - esperado_pt) < 1.0


def test_desenhar_ilhos_na_caixa():
    """Testa desenho de ilhós dentro de um retângulo de peça em uma folha montada."""
    page = MockPageDraw(width=1000, height=1000)
    caixa_peca = (100, 100, 900, 500)

    desenhos_antes = len(page.get_drawings())
    acabamento.desenhar_ilhos_na_caixa(page, caixa_peca, espacamento_m=0.40)
    desenhos_depois = len(page.get_drawings())

    assert desenhos_depois > desenhos_antes
