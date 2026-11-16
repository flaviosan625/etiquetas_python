"""
Testes unitários para o motor próprio de leitura e parsing de PDF (ISSUE-02).
"""

import pathlib
import zlib
import pytest

from motor_pdf.descompressao import (
    ascii85_decode,
    ascii_hex_decode,
    descompactar_stream,
    desfaz_preditor,
    run_length_decode,
)
from motor_pdf.sintaxe import (
    PdfArray,
    PdfDict,
    PdfName,
    PdfRef,
    PdfString,
    PdfTokenizer,
    parse_objeto,
)
from motor_pdf.leitor import Caixa, PdfReader, abrir_pdf


def test_ascii_hex_decode():
    raw = b"48656c6c6f20576f726c64>"
    assert ascii_hex_decode(raw) == b"Hello World"

    # Hex ímpar: '4>' vira 0x40
    assert ascii_hex_decode(b"4>") == b"\x40"


def test_ascii85_decode():
    # 'Hello world!' codificado em ASCII85 é 87cURD]j7BEbo80
    raw = b"<~87cURD]j7BEbo80~>"
    assert ascii85_decode(raw) == b"Hello world!"


def test_run_length_decode():
    # 2 bytes literais (len=1), depois 4 bytes repetidos de 0xFF (len=257-254=3 + 1 = 4 -> len=254)
    # 257 - 254 = 3 bytes repetidos
    raw = bytes([1, ord('A'), ord('B'), 254, ord('Z'), 128])
    assert run_length_decode(raw) == b"ABZZZ"


def test_desfaz_preditor_png():
    # 1 coluna, 3 linhas, cores=1, bpc=8. Stride = 2 bytes (1 byte filtro + 1 byte dado)
    # Linha 1: filtro 0 (None), dado 10
    # Linha 2: filtro 1 (Sub), dado 5 (deve somar com left, mas em col=1 left é 0) -> 5
    # Linha 3: filtro 2 (Up), dado 3 (soma com linha de cima = 5 + 3 = 8)
    raw = bytes([0, 10, 1, 5, 2, 3])
    dec = desfaz_preditor(raw, predictor=12, colors=1, bits_per_component=8, columns=1)
    assert dec == bytes([10, 5, 8])


def test_descompactar_flate():
    original = b"Conteudo de teste do motor de PDF da Uny CV"
    comprimido = zlib.compress(original)
    assert descompactar_stream(comprimido, "/FlateDecode") == original


def test_sintaxe_tokens_e_objetos():
    texto = b"""
    <<
      /Type /Page
      /MediaBox [0 0 612 792]
      /Rotate 90
      /Parent 2 0 R
      /Nome (Exemplo \\(Com Parenteses\\))
      /Hex <414243>
      /Ativo true
      /Inativo false
    >>
    """
    tok = PdfTokenizer(texto)
    obj = parse_objeto(tok)

    assert isinstance(obj, dict)
    assert obj[PdfName("Type")] == PdfName("Page")
    assert obj[PdfName("MediaBox")] == [0, 0, 612, 792]
    assert obj[PdfName("Rotate")] == 90
    assert obj[PdfName("Parent")] == PdfRef(2, 0)
    assert obj[PdfName("Ativo")] is True
    assert obj[PdfName("Inativo")] is False
    assert obj[PdfName("Nome")].texto() == "Exemplo (Com Parenteses)"
    assert obj[PdfName("Hex")] == b"ABC"


def test_leitor_pdf_sintetico():
    """Gera um PDF 1.4 minimalista em memória e valida o PdfReader."""
    corpo = (
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595.28 841.89] /TrimBox [10 10 585.28 831.89] /Rotate 0 >>\nendobj\n"
        b"xref\n"
        b"0 4\n"
        b"0000000000 65535 f \n"
        b"0000000009 00000 n \n"
        b"0000000058 00000 n \n"
        b"0000000115 00000 n \n"
        b"trailer\n"
        b"<< /Size 4 /Root 1 0 R >>\n"
        b"startxref\n"
        b"233\n"
        b"%%EOF\n"
    )

    with abrir_pdf(corpo) as doc:
        assert doc.num_paginas == 1
        pag = doc.obter_pagina(0)
        assert pag.rotacao == 0
        assert round(pag.mediabox.width, 2) == 595.28
        assert round(pag.mediabox.height, 2) == 841.89
        assert round(pag.trimbox.x0, 2) == 10.0
        assert round(pag.trimbox.x1, 2) == 585.28
        assert round(pag.largura_pt, 2) == 575.28
        assert round(pag.altura_pt, 2) == 821.89


def test_leitor_pdf_real_relatorio():
    """Valida o leitor abrindo um PDF real existente na raiz do projeto."""
    caminho = pathlib.Path(__file__).parent.parent / "Relatorio - Sistema de Gestao de Producao UNY CV.pdf"
    if not caminho.exists():
        pytest.skip("PDF de relatório não encontrado")

    with abrir_pdf(caminho) as doc:
        assert doc.num_paginas > 0
        pag = doc.obter_pagina(0)
        assert pag.largura_pt > 0
        assert pag.altura_pt > 0
        assert pag.largura_m > 0
        assert pag.altura_m > 0
        # MediaBox e TrimBox válidos
        assert pag.mediabox.width > 0
        assert pag.mediabox.height > 0
