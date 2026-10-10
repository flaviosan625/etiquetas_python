"""Falhas de saída e concorrência não devem apagar ou duplicar uma arte."""
import pathlib
import subprocess
import sys

import pymupdf
import pytest

from seguranca_montagem import MontagemOcupada, PublicacaoMontagem, trava_montagem


def _documento():
    doc = pymupdf.open()
    pagina = doc.new_page(width=300, height=400)
    pagina.draw_rect(pagina.rect, fill=(0.2, 0.4, 0.6))
    return doc


def test_mesma_entrada_nao_monta_duas_vezes_e_outra_maquina_pode(tmp_path):
    docan, swj = tmp_path / "DOCAN", tmp_path / "SWJ"
    docan.mkdir()
    swj.mkdir()
    with trava_montagem(docan):
        with pytest.raises(MontagemOcupada):
            with trava_montagem(docan):
                pytest.fail("A mesma entrada foi liberada duas vezes")
        with trava_montagem(swj):
            pass
    with trava_montagem(docan):
        pass


def test_a_trava_tambem_impede_um_segundo_processo(tmp_path):
    script = (
        "import sys\n"
        "from seguranca_montagem import trava_montagem, MontagemOcupada\n"
        "try:\n"
        "    with trava_montagem(sys.argv[1]): print('livre')\n"
        "except MontagemOcupada: print('ocupada')\n"
    )
    with trava_montagem(tmp_path):
        resultado = subprocess.run(
            [sys.executable, "-c", script, str(tmp_path)],
            cwd=pathlib.Path(__file__).resolve().parent.parent,
            capture_output=True, text=True, timeout=15, check=True)
    assert resultado.stdout.strip() == "ocupada"


def test_pdf_e_ficha_so_aparecem_depois_de_conferir_lote(tmp_path):
    saida = tmp_path / "saida"
    with _documento() as doc, PublicacaoMontagem(saida) as lote:
        destino = lote.salvar(doc, saida / "1UN LONA 3.2x12M.pdf", {"pecas": ["ARTE_A"]})
        assert not destino.exists()
        assert not destino.with_suffix(".json").exists()
        lote.publicar()
        with pymupdf.open(destino) as salvo:
            assert salvo.page_count == 1
        assert destino.with_suffix(".json").is_file()
    assert len(list(saida.iterdir())) == 2


def test_mesmo_nome_nao_sobrescreve_trabalho_anterior(tmp_path):
    anterior = tmp_path / "1UN LONA 3.2x12M.pdf"
    anterior.write_bytes(b"trabalho anterior")
    with _documento() as doc, PublicacaoMontagem(tmp_path) as lote:
        destino = lote.salvar(doc, anterior, {"pecas": ["NOVA"]})
        lote.publicar()
    assert destino.name.endswith("__02.pdf")
    assert anterior.read_bytes() == b"trabalho anterior"


def test_falha_na_ficha_desfaz_todos_os_pdfs_novos(tmp_path, monkeypatch):
    original_rename = pathlib.Path.rename

    def falhar_segunda_ficha(origem, alvo):
        if origem.name == "0001.json":
            raise OSError("simulação de disco indisponível")
        return original_rename(origem, alvo)

    with _documento() as doc, PublicacaoMontagem(tmp_path) as lote:
        lote.salvar(doc, tmp_path / "A.pdf", {"pecas": ["A"]})
        lote.salvar(doc, tmp_path / "B.pdf", {"pecas": ["B"]})
        monkeypatch.setattr(pathlib.Path, "rename", falhar_segunda_ficha)
        with pytest.raises(OSError, match="disco indisponível"):
            lote.publicar()
        assert not list(tmp_path.glob("*.pdf"))
        assert not list(tmp_path.glob("*.json"))
    assert not list(tmp_path.iterdir())


def test_falha_no_preparo_nao_deixa_saida_final(tmp_path):
    with pytest.raises(ValueError):
        with _documento() as doc, PublicacaoMontagem(tmp_path) as lote:
            lote.salvar(doc, tmp_path / "A.pdf", {"pecas": ["A"]})
            lote.salvar(doc, tmp_path / "B.pdf", {"dpi": float("nan")})
    assert not list(tmp_path.iterdir())
