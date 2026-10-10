"""Adobe simulado: originais só saem da entrada após publicação confirmada."""
import json

import pymupdf
import pytest

import montagem
import conversao_adobe
from seguranca_montagem import PublicacaoMontagem


@pytest.fixture
def entrada(tmp_path, monkeypatch):
    pasta = tmp_path / "DOCAN R5200"
    pasta.mkdir()
    chamadas = []

    def converter(origem, destino):
        chamadas.append(origem)
        with pymupdf.open() as doc:
            page = doc.new_page(width=montagem.PT_M, height=montagem.PT_M / 2)
            page.draw_rect(page.rect, color=None, fill=(0.1, 0.4, 0.7))
            doc.save(destino)

    monkeypatch.setattr(conversao_adobe, "CONVERSORES_POR_EXTENSAO", {".eps": converter, ".psd": converter})
    return pasta, chamadas


def montar(pasta, **kwargs):
    return montagem.montar_pasta(pasta, config={"materiais": {"LONA": {"tipo": "rolo"}}},
                                raiz_clientes=pasta.parent / "clientes", **kwargs)


@pytest.mark.parametrize("extensao", ["eps", "psd"])
def test_arquiva_original_e_identifica_ficha(entrada, extensao):
    pasta, chamadas = entrada
    original = pasta / f"2UN LONA 1.00X0.50M_CLIENTE.{extensao}"
    original.write_bytes(b"original Adobe")
    resultado = montar(pasta)
    ficha = json.loads(resultado["folhas"][0]["arquivo"].with_suffix(".json").read_text(encoding="utf-8"))
    assert list(ficha["originais"]) == [original.name]
    assert len(ficha["pecas"]) == 2
    assert all(p["arquivo"] == original.name for p in ficha["pecas"])
    assert not original.exists()
    assert len(list((pasta / "_originais").rglob(f"*.{extensao}"))) == 1
    assert not list(pasta.glob("*.pdf"))
    assert not list(pasta.glob(".conversao-*"))
    assert len(chamadas) == 1


def test_falha_ao_publicar_preserva_original_sem_derivada_na_entrada(entrada, monkeypatch):
    pasta, _ = entrada
    original = pasta / "1UN LONA 1.00X0.50M_CLIENTE.eps"
    original.write_bytes(b"original")

    def falhar(self):
        raise OSError("publicacao simulada")

    monkeypatch.setattr(PublicacaoMontagem, "publicar", falhar)
    with pytest.raises(OSError, match="simulada"):
        montar(pasta)
    assert original.read_bytes() == b"original"
    assert not list(pasta.glob("*.pdf"))
    assert not list(pasta.glob(".conversao-*"))


def test_arquivamento_pendente_nao_repete_conversao_ou_montagem(entrada, monkeypatch):
    pasta, chamadas = entrada
    original = pasta / "1UN LONA 1.00X0.50M_CLIENTE.eps"
    original.write_bytes(b"original")

    def falhar(*args):
        raise PermissionError("original aberto")

    monkeypatch.setattr(montagem, "_mover_para", falhar)
    primeira = montar(pasta)
    segunda = montar(pasta)
    assert primeira["folhas"] and primeira["avisos"]
    assert not segunda["folhas"]
    assert len(chamadas) == 1
    assert original.exists()


def test_sem_arquivar_preserva_original(entrada):
    pasta, _ = entrada
    original = pasta / "1UN LONA 1.00X0.50M_CLIENTE.eps"
    original.write_bytes(b"original")
    assert montar(pasta, guardar_originais=False)["folhas"]
    assert original.exists()
    assert not list(pasta.glob("*.pdf"))


def test_recusa_aponta_original_e_preserva_arte_que_nao_cabe(entrada):
    pasta, _ = entrada
    original = pasta / "1UN LONA 12.00X6.00M_CLIENTE.eps"
    original.write_bytes(b"original")
    resultado = montar(pasta)
    assert not resultado["folhas"]
    assert resultado["recusadas"][0]["arquivo"] == original.name
    assert original.exists()
    assert not list(pasta.glob(".conversao-*"))


def test_adobe_indisponivel_mantem_original_na_entrada(entrada, monkeypatch):
    pasta, _ = entrada
    original = pasta / "1UN LONA 1.00X0.50M_CLIENTE.eps"
    original.write_bytes(b"original")

    def falhar(*args):
        raise RuntimeError("Adobe indisponivel")

    monkeypatch.setattr(conversao_adobe, "CONVERSORES_POR_EXTENSAO", {".eps": falhar})
    resultado = montar(pasta)
    assert not resultado["folhas"]
    assert "conversão" in resultado["recusadas"][0]["motivo"]
    assert original.read_bytes() == b"original"
    assert not (pasta / "_conferir").exists()
