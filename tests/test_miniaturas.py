"""
Testes da miniatura da arte — a função única que OS, checklist,
documento de Enviados e relatório diário usam.
"""
import pymupdf
import pytest

import miniaturas


def _arte(caminho, largura_pt=300, altura_pt=200):
    doc = pymupdf.open()
    pagina = doc.new_page(width=largura_pt, height=altura_pt)
    pagina.draw_rect(pymupdf.Rect(10, 10, largura_pt - 10, altura_pt - 10),
                     color=(0.8, 0.1, 0.3), fill=(0.95, 0.85, 0.2), width=3)
    doc.save(str(caminho))
    doc.close()
    return caminho


def test_faz_o_jpeg_da_primeira_pagina(tmp_path):
    dados = miniaturas.de_arquivo(_arte(tmp_path / "arte.pdf"))

    assert dados and dados[:2] == b"\xff\xd8"          # assinatura de JPEG
    assert miniaturas.proporcao(dados) == (miniaturas.LADO_PADRAO, 200)


def test_arquivo_que_nao_abre_devolve_none_em_vez_de_quebrar(tmp_path):
    """EPS e arte corrompida acontecem — o documento sai mesmo assim."""
    ruim = tmp_path / "quebrada.pdf"
    ruim.write_bytes(b"isto nao e um PDF")

    assert miniaturas.de_arquivo(ruim) is None
    assert miniaturas.de_arquivo(tmp_path / "nem_existe.pdf") is None


def test_arquivo_grande_demais_nem_e_aberto(tmp_path):
    """Um TIF de 1,8 GB já apareceu no registro: a MuPDF decodifica inteiro."""
    arte = _arte(tmp_path / "arte.pdf")

    assert miniaturas.de_arquivo(arte, limite_bytes=10) is None
    assert miniaturas.de_arquivo(arte, limite_bytes=None) is not None


def test_encaixar_mantem_a_proporcao(tmp_path):
    """Arte esticada num documento de gráfica é defeito, não detalhe."""
    dados = miniaturas.de_arquivo(_arte(tmp_path / "deitada.pdf", 400, 100))

    largura, altura = miniaturas.encaixar(dados, 60, 42)

    assert largura == 60 and altura == 15
    assert abs(largura / altura - 4) < 0.3


def test_encaixar_com_dados_ruins_nao_quebra():
    assert miniaturas.encaixar(b"nao e imagem", 60, 42) == (60, 42)


def test_guarda_e_le_do_cache(tmp_path):
    chave = ("2026-09-18", "SWJ320A", "arte com acento e / barra.pdf")

    assert miniaturas.guardada(tmp_path, "2026-09", chave) is None
    miniaturas.guardar(tmp_path, "2026-09", chave, b"conteudo")

    assert miniaturas.guardada(tmp_path, "2026-09", chave) == b"conteudo"


def test_chaves_diferentes_nao_se_misturam(tmp_path):
    """O mesmo nome noutro dia pode ser outra arte."""
    miniaturas.guardar(tmp_path, "2026-09", ("2026-09-18", "SWJ320A", "a.pdf"), b"dia18")
    miniaturas.guardar(tmp_path, "2026-09", ("2026-09-19", "SWJ320A", "a.pdf"), b"dia19")

    assert miniaturas.guardada(tmp_path, "2026-09", ("2026-09-18", "SWJ320A", "a.pdf")) == b"dia18"
    assert miniaturas.guardada(tmp_path, "2026-09", ("2026-09-19", "SWJ320A", "a.pdf")) == b"dia19"


def test_obter_guarda_na_primeira_vez_e_le_depois(tmp_path):
    arte = _arte(tmp_path / "arte.pdf")
    chave = ("2026-09-18", "SWJ320A", "arte.pdf")

    primeira = miniaturas.obter(arte, tmp_path / "cache", "2026-09", chave)
    arte.unlink()                                  # passou dos 15 dias de guarda
    segunda = miniaturas.obter(arte, tmp_path / "cache", "2026-09", chave)

    assert primeira and segunda == primeira, "sem o cache o relatório velho voltaria sem arte"


def test_sem_cache_nao_escreve_nada(tmp_path):
    arte = _arte(tmp_path / "arte.pdf")

    assert miniaturas.obter(arte) is not None
    assert not (tmp_path / miniaturas.NOME_PASTA_CACHE).exists()
