"""Validação de conversão com arquivos isolados e sem automação Adobe."""
import pathlib

import pymupdf
import pytest

import conversao_adobe


@pytest.fixture(autouse=True)
def _nunca_abrir_adobe(monkeypatch):
    monkeypatch.setattr(conversao_adobe, "CONVERSORES_POR_EXTENSAO", {})


def _entrada(tmp_path, extensao=".eps"):
    original = tmp_path / ("1UN LONA 1X2M_arte" + extensao)
    original.write_bytes(b"arte original preservada")
    return original


def _converter(original, conversor, **opcoes):
    mensagens = []
    resultado = conversao_adobe.converter_se_necessario(
        original.parent, original.name, original.parent / "_originais",
        lambda nivel, texto, *_: mensagens.append((nivel, texto)),
        conversores={original.suffix: conversor},
        **opcoes,
    )
    return resultado, mensagens


def _pdf_valido(origem, destino):
    with pymupdf.open() as documento:
        pagina = documento.new_page(width=100, height=200)
        pagina.insert_text((10, 20), "arte de teste")
        documento.save(destino)


@pytest.mark.parametrize("extensao", [".eps", ".psd"])
def test_conversor_sem_escrita_mantem_original(tmp_path, extensao):
    original = _entrada(tmp_path, extensao)
    resultado, mensagens = _converter(original, lambda origem, destino: None)
    assert resultado is None
    assert original.read_bytes() == b"arte original preservada"
    assert not (tmp_path / "_originais").exists()
    assert any(nivel == "err" and "não gerou um PDF" in texto
               and "original foi mantido" in texto for nivel, texto in mensagens)


@pytest.mark.parametrize("conteudo", [b"", b"arquivo quebrado", b"%PDF-1.4\narquivo quebrado"])
def test_pdf_invalido_nao_arquiva_original_nem_fica_na_entrada(tmp_path, conteudo):
    original = _entrada(tmp_path)
    resultado, mensagens = _converter(
        original, lambda origem, destino: pathlib.Path(destino).write_bytes(conteudo))
    assert resultado is None
    assert original.exists()
    assert not original.with_suffix(".pdf").exists()
    assert not (tmp_path / "_originais").exists()
    assert any(nivel == "err" for nivel, _ in mensagens)


def test_pdf_sem_paginas_mantem_original(tmp_path):
    original = _entrada(tmp_path)
    pdf_sem_paginas = (b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
                       b"2 0 obj\n<< /Type /Pages /Kids [] /Count 0 >>\nendobj\n"
                       b"trailer\n<< /Root 1 0 R >>\n%%EOF")
    resultado, mensagens = _converter(
        original, lambda origem, destino: pathlib.Path(destino).write_bytes(pdf_sem_paginas))
    assert resultado is None
    assert original.exists()
    assert not original.with_suffix(".pdf").exists()
    assert any(nivel == "err" and "não contém páginas" in texto
               for nivel, texto in mensagens)


def test_pdf_com_pagina_vazia_mantem_original(tmp_path):
    original = _entrada(tmp_path)

    def converter_vazio(origem, destino):
        with pymupdf.open() as documento:
            documento.new_page()
            documento.save(destino)

    resultado, mensagens = _converter(original, converter_vazio)
    assert resultado is None
    assert original.exists()
    assert not original.with_suffix(".pdf").exists()
    assert any("sem conteúdo de arte" in texto for _, texto in mensagens)


@pytest.mark.parametrize("extensao", [".eps", ".psd"])
def test_pdf_valido_e_conferido_antes_de_arquivar(tmp_path, extensao):
    original = _entrada(tmp_path, extensao)
    resultado, mensagens = _converter(original, _pdf_valido)
    assert resultado == original.with_suffix(".pdf").name
    assert not original.exists()
    assert (tmp_path / "_originais" / original.name).read_bytes() == b"arte original preservada"
    with pymupdf.open(tmp_path / resultado) as documento:
        assert documento.page_count == 1
        assert documento[0].rect == pymupdf.Rect(0, 0, 100, 200)
    assert any(nivel == "ok" for nivel, _ in mensagens)


def test_homonimo_existente_e_preservado_com_destino_novo(tmp_path):
    original = _entrada(tmp_path)
    anterior = original.with_suffix(".pdf")
    anterior.write_bytes(b"pdf anterior intocavel")
    resultado, _ = _converter(original, _pdf_valido)
    assert resultado == f"{original.stem} (2).pdf"
    assert anterior.read_bytes() == b"pdf anterior intocavel"
    with pymupdf.open(tmp_path / resultado) as documento:
        assert documento.page_count == 1


def test_homonimo_e_original_preservados_se_nova_tentativa_falha(tmp_path):
    original = _entrada(tmp_path)
    anterior = original.with_suffix(".pdf")
    anterior.write_bytes(b"pdf anterior intocavel")
    resultado, _ = _converter(original, lambda origem, destino: pathlib.Path(destino).write_bytes(b"ruim"))
    assert resultado is None
    assert anterior.read_bytes() == b"pdf anterior intocavel"
    assert original.exists()
    assert not (tmp_path / f"{original.stem} (2).pdf").exists()


def test_conversor_que_falha_depois_de_escrever_nao_deixa_parcial(tmp_path):
    original = _entrada(tmp_path)

    def falhar(origem, destino):
        pathlib.Path(destino).write_bytes(b"pdf parcial")
        raise RuntimeError("Adobe parou durante o salvamento")

    resultado, _ = _converter(original, falhar)
    assert resultado is None
    assert original.exists()
    assert not original.with_suffix(".pdf").exists()


@pytest.mark.parametrize("extensao", [".eps", ".psd"])
def test_conversao_pode_aguardar_publicacao_sem_mover_original(tmp_path, monkeypatch, extensao):
    original = _entrada(tmp_path, extensao)

    def nao_mover(self, destino):
        raise AssertionError("O modo sem arquivamento não pode mover arquivos")

    monkeypatch.setattr(pathlib.Path, "rename", nao_mover)
    resultado, mensagens = _converter(original, _pdf_valido, guardar_original=False)
    assert resultado == original.with_suffix(".pdf").name
    assert original.read_bytes() == b"arte original preservada"
    assert not (tmp_path / "_originais").exists()
    with pymupdf.open(tmp_path / resultado) as documento:
        assert documento.page_count == 1
        assert "arte de teste" in documento[0].get_text()
    assert any(nivel == "ok" for nivel, _ in mensagens)


@pytest.mark.parametrize("homonimo", [False, True])
def test_falha_ao_arquivar_nao_libera_pdf_nem_altera_homonimo(tmp_path, monkeypatch, homonimo):
    original = _entrada(tmp_path)
    anterior = original.with_suffix(".pdf")
    if homonimo:
        anterior.write_bytes(b"pdf anterior intocavel")
    renomear = pathlib.Path.rename

    def original_aberto(self, destino):
        if self == original:
            raise PermissionError("O original está aberto no editor")
        return renomear(self, destino)

    monkeypatch.setattr(pathlib.Path, "rename", original_aberto)
    resultado, mensagens = _converter(original, _pdf_valido)
    assert resultado is None
    assert original.read_bytes() == b"arte original preservada"
    if homonimo:
        assert anterior.read_bytes() == b"pdf anterior intocavel"
        assert not (tmp_path / f"{original.stem} (2).pdf").exists()
    else:
        assert not anterior.exists()
    assert not (tmp_path / "_originais" / original.name).exists()
    assert not any(nivel == "ok" for nivel, _ in mensagens)
    assert any(nivel == "err" and "não foi possível arquivar" in texto
               and "original foi mantido" in texto for nivel, texto in mensagens)


def test_pdf_pode_ser_preparado_em_pasta_separada_sem_mover_raw(tmp_path):
    original = _entrada(tmp_path)
    destino = tmp_path / "derivadas" / "lote temporario"

    def converter_no_destino(origem, pdf):
        assert pathlib.Path(origem) == original.resolve()
        assert pathlib.Path(pdf).parent == destino.resolve()
        assert pathlib.Path(pdf).is_absolute()
        _pdf_valido(origem, pdf)

    resultado, mensagens = _converter(
        original, converter_no_destino, guardar_original=False, pasta_pdf=destino)
    assert resultado == original.with_suffix(".pdf").name
    assert original.read_bytes() == b"arte original preservada"
    assert not original.with_suffix(".pdf").exists()
    assert not (tmp_path / "_originais").exists()
    with pymupdf.open(destino / resultado) as documento:
        assert "arte de teste" in documento[0].get_text()
    assert any(nivel == "ok" for nivel, _ in mensagens)


def test_colisao_na_pasta_separada_preserva_pdf_anterior(tmp_path):
    original = _entrada(tmp_path)
    destino = tmp_path / "derivadas"
    destino.mkdir()
    anterior = destino / original.with_suffix(".pdf").name
    anterior.write_bytes(b"derivada anterior intocavel")
    resultado, _ = _converter(original, _pdf_valido, guardar_original=False, pasta_pdf=destino)
    assert resultado == f"{original.stem} (2).pdf"
    assert anterior.read_bytes() == b"derivada anterior intocavel"
    assert original.exists()
    assert not original.with_suffix(".pdf").exists()
    with pymupdf.open(destino / resultado) as documento:
        assert documento.page_count == 1


def test_destino_separado_que_nao_pode_ser_criado_mantem_original(tmp_path):
    original = _entrada(tmp_path)
    destino = tmp_path / "derivadas"
    destino.write_bytes(b"arquivo preexistente")

    def nao_converter(origem, pdf):
        raise AssertionError("Não deve abrir o Adobe sem uma pasta de saída")

    resultado, mensagens = _converter(
        original, nao_converter, guardar_original=False, pasta_pdf=destino)
    assert resultado is None
    assert destino.read_bytes() == b"arquivo preexistente"
    assert original.read_bytes() == b"arte original preservada"
    assert not original.with_suffix(".pdf").exists()
    assert any(nivel == "err" and "original foi mantido" in texto for nivel, texto in mensagens)


def test_conversao_invalida_limpa_apenas_derivada_na_pasta_separada(tmp_path):
    original = _entrada(tmp_path)
    destino = tmp_path / "derivadas"
    destino.mkdir()
    anterior = destino / original.with_suffix(".pdf").name
    anterior.write_bytes(b"derivada anterior intocavel")
    resultado, _ = _converter(
        original, lambda origem, pdf: pathlib.Path(pdf).write_bytes(b"%PDF-1.4\nquebrado"),
        guardar_original=False, pasta_pdf=destino)
    assert resultado is None
    assert original.exists()
    assert anterior.read_bytes() == b"derivada anterior intocavel"
    assert not (destino / f"{original.stem} (2).pdf").exists()
