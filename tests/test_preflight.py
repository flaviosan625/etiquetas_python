import pathlib
import pytest
import pymupdf

import preflight


def _criar_pdf_vetorial_puro(caminho):
    """Cria PDF simples com formas vetoriais, sem fontes vivas e sem imagens."""
    doc = pymupdf.open()
    page = doc.new_page(width=300, height=300)
    # Desenho vetorial CMYK
    page.draw_rect(pymupdf.Rect(50, 50, 200, 200), color=(0, 0, 0, 1), fill=(0, 0.5, 0.5, 0))
    doc.save(str(caminho))
    doc.close()


def _criar_pdf_com_texto_vivo(caminho):
    """Cria PDF contendo texto vivo (fonte)."""
    doc = pymupdf.open()
    page = doc.new_page(width=300, height=300)
    page.insert_text(pymupdf.Point(50, 100), "Texto de Teste para Preflight", fontsize=16)
    doc.save(str(caminho))
    doc.close()


def _criar_pdf_com_imagem_dpi(caminho, largura_px, altura_px, rect_pt, colorspace="RGB"):
    """Cria PDF inserindo uma imagem com dimensões em pixels específicas."""
    from PIL import Image
    import io

    # Cria imagem na memória
    modo = "RGB" if colorspace == "RGB" else "CMYK"
    cor = (255, 0, 0) if modo == "RGB" else (0, 255, 255, 0)
    img = Image.new(modo, (largura_px, altura_px), color=cor)
    buf = io.BytesIO()
    img.save(buf, format="PNG" if modo == "RGB" else "JPEG")
    img_bytes = buf.getvalue()

    doc = pymupdf.open()
    page = doc.new_page(width=500, height=500)
    page.insert_image(rect_pt, stream=img_bytes)
    doc.save(str(caminho))
    doc.close()


def test_preflight_arquivo_inexistente(tmp_path):
    rel = preflight.inspecionar_pdf(tmp_path / "nao_existe.pdf")
    assert rel["valido"] is False
    assert rel["status"] == "ERRO"
    assert "não encontrado" in rel["resumo"].lower()


def test_preflight_vetorial_puro_aprovado(tmp_path):
    pdf_path = tmp_path / "vetor.pdf"
    _criar_pdf_vetorial_puro(pdf_path)

    rel = preflight.inspecionar_pdf(pdf_path)
    assert rel["valido"] is True
    assert rel["status"] == "OK"
    assert rel["tem_baixa_resolucao"] is False
    assert rel["tem_fontes_vivas"] is False
    assert "Vetor" in rel["resumo"]


def test_preflight_detecta_fontes_vivas(tmp_path):
    pdf_path = tmp_path / "texto_vivo.pdf"
    _criar_pdf_com_texto_vivo(pdf_path)

    rel = preflight.inspecionar_pdf(pdf_path)
    assert rel["valido"] is True
    assert rel["status"] == "ALERTA"
    assert rel["tem_fontes_vivas"] is True
    assert len(rel["fontes"]) > 0
    assert any("Fontes vivas" in aviso for aviso in rel["avisos"])
    assert "Fontes Abertas" in rel["resumo"]


def test_preflight_detecta_baixa_resolucao_e_rgb(tmp_path):
    # Imagem pequena (50x50 px) esticada em 200x200 pt
    # DPI = (50 / 200) * 72 = 18 DPI (muito baixo!)
    pdf_path = tmp_path / "baixa_res.pdf"
    _criar_pdf_com_imagem_dpi(
        pdf_path, largura_px=50, altura_px=50,
        rect_pt=pymupdf.Rect(50, 50, 250, 250), colorspace="RGB"
    )

    rel = preflight.inspecionar_pdf(pdf_path, dpi_minimo=100)
    assert rel["valido"] is True
    assert rel["status"] == "ALERTA"
    assert rel["tem_baixa_resolucao"] is True
    assert rel["dpi_minimo_encontrado"] is not None
    assert rel["dpi_minimo_encontrado"] < 30.0
    assert rel["tem_rgb"] is True
    assert any("resolução baixa" in aviso.lower() for aviso in rel["avisos"])
    assert "RGB" in rel["resumo"]


def test_preflight_escala_1_para_10(tmp_path):
    # Imagem de 300x300 px num quadrado de 72x72 pt (1x1 polegada)
    # Na folha 1:10 isso parece ter 300 DPI: (300 / 72) * 72 = 300 DPI
    # Mas ao ampliar 10x para o tamanho real, o DPI cai para 30 DPI!
    pdf_path = tmp_path / "arte_1_10.pdf"
    _criar_pdf_com_imagem_dpi(
        pdf_path, largura_px=300, altura_px=300,
        rect_pt=pymupdf.Rect(0, 0, 72, 72), colorspace="RGB"
    )

    rel = preflight.inspecionar_pdf(pdf_path, dpi_minimo=100, escala_fator=10.0)
    assert rel["valido"] is True
    # DPI efetivo deve ser 30.0 (300 / 10)
    assert rel["dpi_minimo_encontrado"] == 30.0
    assert rel["tem_baixa_resolucao"] is True
    assert any("Escala 1:10" in aviso for aviso in rel["avisos"])


def test_relatorio_texto_completo(tmp_path):
    pdf_path = tmp_path / "vetor.pdf"
    _criar_pdf_vetorial_puro(pdf_path)

    rel = preflight.inspecionar_pdf(pdf_path)
    texto = preflight.relatorio_texto_completo(rel)
    assert "RELATÓRIO DE PREFLIGHT" in texto
    assert "Status: OK" in texto
    assert "100% pronto" in texto
