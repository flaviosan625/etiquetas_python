"""
Testes unitários do gerador de miniaturas motor_pdf.miniaturas.

Verifica:
  - Geração de thumbnail a partir de imagem PNG/JPG (RGB, RGBA, CMYK).
  - Geração de thumbnail a partir de PDF com imagem embutida (FlateDecode e DCTDecode).
  - Geração de thumbnail a partir de PDF puramente vetorial.
  - Cálculo de proporção e encaixe sem distorção.
  - Funções de cache (caminho_guardada, guardada, guardar, obter).
  - Tratamento silencioso de falhas (arquivo inexistente, corrompido ou acima do limite).
"""

from __future__ import annotations

import io
import pathlib
import zlib
import pytest
from PIL import Image

import motor_pdf.miniaturas as miniaturas
from motor_pdf import PdfWriter
from motor_pdf.sintaxe import PdfName, PdfStream


# ==============================================================================
# Utilitários de Criação de Arquivos de Teste (100% nativos e sem PyMuPDF)
# ==============================================================================

def _criar_imagem_png(caminho: pathlib.Path, largura: int = 800, altura: int = 400, modo: str = "RGB") -> pathlib.Path:
    """Cria uma imagem de teste PNG."""
    cor = (255, 100, 50) if modo == "RGB" else (255, 100, 50, 200)
    img = Image.new(modo, (largura, altura), cor)
    img.save(str(caminho), format="PNG")
    return caminho


def _criar_imagem_jpg(caminho: pathlib.Path, largura: int = 200, altura: int = 500) -> pathlib.Path:
    """Cria uma imagem de teste JPEG."""
    img = Image.new("RGB", (largura, altura), (50, 150, 250))
    img.save(str(caminho), format="JPEG", quality=90)
    return caminho


def _criar_pdf_com_imagem_flate(caminho: pathlib.Path, largura_px: int = 400, altura_px: int = 200) -> pathlib.Path:
    """Gera um PDF contendo imagem embutida comprimida com FlateDecode."""
    img = Image.new("RGB", (largura_px, altura_px), (30, 180, 80))
    dados_brutos = img.tobytes()
    comprimido = zlib.compress(dados_brutos)

    writer = PdfWriter()
    img_stream = PdfStream(
        {
            PdfName("/Type"): PdfName("/XObject"),
            PdfName("/Subtype"): PdfName("/Image"),
            PdfName("/Width"): largura_px,
            PdfName("/Height"): altura_px,
            PdfName("/ColorSpace"): PdfName("/DeviceRGB"),
            PdfName("/BitsPerComponent"): 8,
            PdfName("/Filter"): PdfName("/FlateDecode"),
            PdfName("/Length"): len(comprimido),
        },
        comprimido,
    )
    img_ref = writer.adicionar_objeto(img_stream)

    recursos = {
        PdfName("/XObject"): {
            PdfName("/Im0"): img_ref
        }
    }
    conteudo = f"q {largura_px} 0 0 {altura_px} 0 0 cm /Im0 Do Q".encode("ascii")
    writer.adicionar_pagina(largura_px, altura_px, recursos, conteudo)
    writer.salvar(str(caminho))
    return caminho


def _criar_pdf_com_imagem_dct(caminho: pathlib.Path, largura_px: int = 300, altura_px: int = 150) -> pathlib.Path:
    """Gera um PDF contendo imagem JPEG embutida com DCTDecode."""
    img = Image.new("RGB", (largura_px, altura_px), (220, 40, 40))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    dados_jpeg = buf.getvalue()

    writer = PdfWriter()
    img_stream = PdfStream(
        {
            PdfName("/Type"): PdfName("/XObject"),
            PdfName("/Subtype"): PdfName("/Image"),
            PdfName("/Width"): largura_px,
            PdfName("/Height"): altura_px,
            PdfName("/ColorSpace"): PdfName("/DeviceRGB"),
            PdfName("/BitsPerComponent"): 8,
            PdfName("/Filter"): PdfName("/DCTDecode"),
            PdfName("/Length"): len(dados_jpeg),
        },
        dados_jpeg,
    )
    img_ref = writer.adicionar_objeto(img_stream)

    recursos = {
        PdfName("/XObject"): {
            PdfName("/Im0"): img_ref
        }
    }
    conteudo = f"q {largura_px} 0 0 {altura_px} 0 0 cm /Im0 Do Q".encode("ascii")
    writer.adicionar_pagina(largura_px, altura_px, recursos, conteudo)
    writer.salvar(str(caminho))
    return caminho


def _criar_pdf_vetorial(caminho: pathlib.Path, largura_pt: float = 300, altura_pt: float = 200) -> pathlib.Path:
    """Gera um PDF puramente vetorial com retângulos e traçados."""
    writer = PdfWriter()
    # Stream com traçado retangular colorido (stroke e fill)
    conteudo = (
        b"q\n"
        b"10 10 280 180 re\n"
        b"2 w\n"
        b"0.8 0.1 0.2 RG\n"
        b"0.9 0.8 0.3 rg\n"
        b"B\n"
        b"Q\n"
    )
    writer.adicionar_pagina(largura_pt, altura_pt, {}, conteudo)
    writer.salvar(str(caminho))
    return caminho


# ==============================================================================
# Testes de Imagens Comuns (PNG, JPG, RGBA, CMYK)
# ==============================================================================

def test_thumbnail_de_imagem_png(tmp_path):
    """Gera thumbnail JPEG a partir de arquivo PNG redimensionando proporcionalmente."""
    png = _criar_imagem_png(tmp_path / "foto.png", 800, 400)
    dados = miniaturas.de_arquivo(png, lado=300)

    assert dados is not None
    assert dados[:2] == b"\xff\xd8"
    largura, altura = miniaturas.proporcao(dados)
    assert largura == 300
    assert altura == 150


def test_thumbnail_de_imagem_jpg(tmp_path):
    """Gera thumbnail JPEG a partir de JPG preservando proporção retrato."""
    jpg = _criar_imagem_jpg(tmp_path / "arte.jpg", 200, 500)
    dados = miniaturas.de_arquivo(jpg, lado=250)

    assert dados is not None
    assert dados[:2] == b"\xff\xd8"
    largura, altura = miniaturas.proporcao(dados)
    assert altura == 250
    assert largura == 100


def test_thumbnail_de_imagem_rgba(tmp_path):
    """Gera thumbnail de imagem RGBA com transparência mesclada sobre fundo branco."""
    rgba = _criar_imagem_png(tmp_path / "logo.png", 400, 400, modo="RGBA")
    dados = miniaturas.de_arquivo(rgba, lado=200)

    assert dados is not None
    assert dados[:2] == b"\xff\xd8"
    assert miniaturas.proporcao(dados) == (200, 200)


def test_thumbnail_de_imagem_cmyk(tmp_path):
    """Gera thumbnail a partir de imagem em espaço de cor CMYK convertendo para RGB."""
    img_cmyk = Image.new("CMYK", (300, 200), (0, 100, 100, 0))  # Vermelho CMYK
    caminho = tmp_path / "cmyk.jpg"
    img_cmyk.save(str(caminho), format="JPEG")

    dados = miniaturas.de_arquivo(caminho, lado=300)
    assert dados is not None
    assert dados[:2] == b"\xff\xd8"
    assert miniaturas.proporcao(dados) == (300, 200)


# ==============================================================================
# Testes de Documentos PDF (Imagem Embutida e Puramente Vetorial)
# ==============================================================================

def test_thumbnail_de_pdf_com_imagem_embutida_flate(tmp_path):
    """Extrai imagem embutida FlateDecode e gera miniatura sem perda nem distorção."""
    pdf = _criar_pdf_com_imagem_flate(tmp_path / "arte_flate.pdf", 400, 200)
    dados = miniaturas.de_arquivo(pdf, lado=300)

    assert dados is not None
    assert dados[:2] == b"\xff\xd8"
    largura, altura = miniaturas.proporcao(dados)
    assert largura == 300
    assert altura == 150


def test_thumbnail_de_pdf_com_imagem_embutida_dct(tmp_path):
    """Extrai imagem embutida DCTDecode (JPEG nativo) e gera miniatura."""
    pdf = _criar_pdf_com_imagem_dct(tmp_path / "arte_dct.pdf", 300, 150)
    dados = miniaturas.de_arquivo(pdf, lado=300)

    assert dados is not None
    assert dados[:2] == b"\xff\xd8"
    largura, altura = miniaturas.proporcao(dados)
    assert largura == 300
    assert altura == 150


def test_thumbnail_de_pdf_puramente_vetorial(tmp_path):
    """PDF sem bitmap: desenha traçados vetoriais limpos com PIL.ImageDraw."""
    pdf = _criar_pdf_vetorial(tmp_path / "vetorial.pdf", 300, 200)
    dados = miniaturas.de_arquivo(pdf, lado=300)

    assert dados is not None
    assert dados[:2] == b"\xff\xd8"
    assert miniaturas.proporcao(dados) == (300, 200)


# ==============================================================================
# Testes de Proporção e Encaixe Sem Distorção
# ==============================================================================

def test_proporcao_e_encaixe_sem_distorcao(tmp_path):
    """Garante que a miniatura nunca seja distorcida dentro da caixa do relatório."""
    png = _criar_imagem_png(tmp_path / "banner.png", 600, 200)
    dados = miniaturas.de_arquivo(png, lado=300)

    assert miniaturas.proporcao(dados) == (300, 100)

    # Caixa retangular padrão 60x42
    largura, altura = miniaturas.encaixar(dados, 60, 42)
    assert largura == 60
    assert altura == 20
    assert abs((largura / altura) - 3.0) < 0.1


def test_encaixar_com_dados_invalidos():
    """Dados corrompidos ou não-imagem devolvem o tamanho máximo sem lançar exceção."""
    assert miniaturas.encaixar(b"lixo binario", 100, 80) == (100, 80)
    assert miniaturas.encaixar(b"", 100, 80) == (100, 80)
    assert miniaturas.encaixar(None, 100, 80) == (100, 80)


def test_proporcao_dados_invalidos():
    """Devolve None para dados vazios ou corrompidos."""
    assert miniaturas.proporcao(b"nao e imagem") is None
    assert miniaturas.proporcao(b"") is None
    assert miniaturas.proporcao(None) is None


# ==============================================================================
# Testes das Funções de Cache
# ==============================================================================

def test_funcoes_de_cache(tmp_path):
    """Testa armazenamento, leitura e caminho do cache por mês e chave."""
    chave = ("2026-11-16", "SWJ320", "arte_teste.pdf")
    pasta_cache = tmp_path / "cache_teste"

    assert miniaturas.guardada(pasta_cache, "2026-11", chave) is None

    conteudo_jpg = b"\xff\xd8\xff\xe0conteudo_simulado"
    salvo = miniaturas.guardar(pasta_cache, "2026-11", chave, conteudo_jpg)

    assert salvo is not None
    assert salvo.is_file()
    assert miniaturas.guardada(pasta_cache, "2026-11", chave) == conteudo_jpg


def test_obter_com_cache_transparente(tmp_path):
    """Testa fluxo completo de 'obter': guarda na 1ª vez e recupera após arquivo original sumir."""
    png = _criar_imagem_png(tmp_path / "original.png", 400, 300)
    pasta_cache = tmp_path / "cache"
    chave = ("2026-11-16", "MIMAKI", "original.png")

    # 1ª chamada: lê do arquivo original e guarda no cache
    dados1 = miniaturas.obter(png, pasta_cache=pasta_cache, mes="2026-11", chave=chave)
    assert dados1 is not None and dados1[:2] == b"\xff\xd8"

    # Apaga arquivo original simulando arquivo limpo da pasta Enviados após 15 dias
    png.unlink()
    assert not png.exists()

    # 2ª chamada: deve recuperar do cache sem falhar
    dados2 = miniaturas.obter(png, pasta_cache=pasta_cache, mes="2026-11", chave=chave)
    assert dados2 == dados1


# ==============================================================================
# Testes de Tratamento Silencioso de Erros
# ==============================================================================

def test_arquivo_inexistente_retorna_none(tmp_path):
    """Arquivo que não existe não quebra a execução."""
    assert miniaturas.de_arquivo(tmp_path / "nao_existe.pdf") is None


def test_arquivo_corrompido_retorna_none(tmp_path):
    """Arquivo corrompido devolve None silenciosamente."""
    ruim = tmp_path / "corrompido.pdf"
    ruim.write_bytes(b"%PDF-1.4 lixo quebrado sem estrutura valida")
    assert miniaturas.de_arquivo(ruim) is None


def test_arquivo_acima_do_limite_retorna_none(tmp_path):
    """Arquivo que excede limite de bytes nem tenta ser decodificado."""
    png = _criar_imagem_png(tmp_path / "foto.png", 200, 200)
    tamanho = png.stat().st_size
    assert miniaturas.de_arquivo(png, limite_bytes=tamanho - 1) is None
    assert miniaturas.de_arquivo(png, limite_bytes=tamanho + 100) is not None
