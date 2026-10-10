"""Prévia correta por arquivo, sem baixar nuvem ou confundir versões da arte."""
from unittest.mock import Mock

import pymupdf

import previas_impressao as previas


def _pdf(caminho, cor=(1, 0, 0)):
    with pymupdf.open() as doc:
        pagina = doc.new_page(width=300, height=200)
        pagina.draw_rect(pagina.rect, color=cor, fill=cor)
        doc.save(str(caminho))
    return caminho


def test_previa_do_pdf_atual_e_jpeg_sem_escrever_cache(tmp_path):
    arte = _pdf(tmp_path / "arte.pdf")
    dados, mensagem = previas.carregar(arte, previas.chave_do_arquivo(arte))
    assert dados[:2] == b"\xff\xd8" and not mensagem
    assert list(tmp_path.iterdir()) == [arte]


def test_arquivos_de_mesmo_nome_em_pastas_diferentes_nao_se_misturam(tmp_path):
    pasta_a, pasta_b = tmp_path / "a", tmp_path / "b"
    pasta_a.mkdir()
    pasta_b.mkdir()
    a = _pdf(pasta_a / "arte.pdf")
    b = _pdf(pasta_b / "arte.pdf", cor=(0, 0, 1))
    assert previas.chave_do_arquivo(a) != previas.chave_do_arquivo(b)
    assert previas.carregar(a, previas.chave_do_arquivo(a))[0] != previas.carregar(b, previas.chave_do_arquivo(b))[0]


def test_arte_substituida_nao_reaproveita_previa_antiga(tmp_path):
    arte = _pdf(tmp_path / "arte.pdf")
    chave = previas.chave_do_arquivo(arte)
    arte.write_bytes(b"nova arte com outro tamanho")
    assert previas.chave_do_arquivo(arte) != chave
    dados, mensagem = previas.carregar(arte, chave)
    assert dados is None and "alterado" in mensagem


def test_arte_alterada_durante_renderizacao_nao_mostra_previa_desatualizada(tmp_path, monkeypatch):
    arte = _pdf(tmp_path / "arte.pdf")
    chave = previas.chave_do_arquivo(arte)

    def renderizar(*args, **kwargs):
        arte.write_bytes(b"outra versao")
        return b"jpeg da versao anterior"

    monkeypatch.setattr(previas.miniaturas, "de_arquivo", renderizar)
    dados, mensagem = previas.carregar(arte, chave)
    assert dados is None and "alterado" in mensagem


def test_placeholder_nao_e_aberto_para_baixar_previa(tmp_path, monkeypatch):
    chave = (str(tmp_path / "nuvem.tif"), 100, 123, previas._ATTRS_SO_NA_NUVEM)
    monkeypatch.setattr(previas, "chave_do_arquivo", lambda _: chave)
    renderizar = Mock()
    monkeypatch.setattr(previas.miniaturas, "de_arquivo", renderizar)
    dados, mensagem = previas.carregar(chave[0], chave)
    assert dados is None and "nuvem" in mensagem
    renderizar.assert_not_called()


def test_arquivo_grande_nao_e_decodificado(tmp_path, monkeypatch):
    arte = _pdf(tmp_path / "arte.pdf")
    monkeypatch.setattr(previas.miniaturas, "LIMITE_BYTES", 1)
    renderizar = Mock()
    monkeypatch.setattr(previas.miniaturas, "de_arquivo", renderizar)
    dados, mensagem = previas.carregar(arte, previas.chave_do_arquivo(arte))
    assert dados is None and "grande" in mensagem
    renderizar.assert_not_called()


def test_arquivo_invalido_ou_apagado_nao_impede_selecao(tmp_path):
    arte = tmp_path / "quebrado.pdf"
    arte.write_bytes(b"nao e pdf")
    dados, mensagem = previas.carregar(arte, previas.chave_do_arquivo(arte))
    assert dados is None and "indisponível" in mensagem
    arte.unlink()
    dados, mensagem = previas.carregar(arte, previas.chave_do_arquivo(arte))
    assert dados is None and "indisponível" in mensagem
