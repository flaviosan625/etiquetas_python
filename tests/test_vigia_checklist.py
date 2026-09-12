"""
Vigia do checklist: uma passada regenera o PDF só quando a pasta mudou.

Regra da casa: teste nunca toca pasta real. A fixture autouse aponta TODOS
os caminhos do módulo (pasta vigiada, PDF, estado, log) pra tmp_path antes
de qualquer teste rodar.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import pytest

import vigia_checklist as vc


@pytest.fixture(autouse=True)
def _isolar_em_tmp(tmp_path, monkeypatch):
    prod = tmp_path / "PRODUCAO"
    saida = tmp_path / "saida"
    prod.mkdir()
    monkeypatch.setattr(vc, "PASTA_PRODUCAO", prod)
    monkeypatch.setattr(vc, "PASTA_SAIDA", saida)
    monkeypatch.setattr(vc, "NOME_CLIENTE", "TESTE ML")
    monkeypatch.setattr(vc, "DESTINO_PDF", saida / "OS - TESTE ML.pdf")
    monkeypatch.setattr(vc, "ARQUIVO_ESTADO", saida / "_estado.json")
    monkeypatch.setattr(vc, "ARQUIVO_LOG", saida / "_log.log")
    return prod


def _por(prod, rel):
    caminho = prod / rel
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_bytes(b"%PDF-1.4 fake")


def test_primeira_passada_gera_o_pdf(_isolar_em_tmp):
    prod = _isolar_em_tmp
    _por(prod, "A_PREMIUM/UV/1UN LONA IMPRESSA 5.00X3.00M_L01.pdf")

    assert vc.passada() is True
    assert vc.DESTINO_PDF.is_file()


def test_segunda_passada_sem_mudanca_nao_regenera(_isolar_em_tmp):
    prod = _isolar_em_tmp
    _por(prod, "A_PREMIUM/UV/1UN LONA IMPRESSA 5.00X3.00M_L01.pdf")

    assert vc.passada() is True
    assert vc.passada() is False        # nada mudou


def test_movimento_na_pasta_regenera(_isolar_em_tmp):
    prod = _isolar_em_tmp
    _por(prod, "A_PREMIUM/UV/1UN LONA IMPRESSA 5.00X3.00M_L01.pdf")
    vc.passada()

    # entrou peça nova = movimento
    _por(prod, "A_PREMIUM/UV/1UN LONA IMPRESSA 6.00X3.00M_L02.pdf")
    assert vc.passada() is True

    # e voltou a estabilizar
    assert vc.passada() is False


def test_mover_para_prontos_conta_como_movimento(_isolar_em_tmp):
    prod = _isolar_em_tmp
    _por(prod, "A_PREMIUM/UV/1UN LONA IMPRESSA 5.00X3.00M_L01.pdf")
    vc.passada()

    # simula o arquivo indo pra Prontos (mudou de pasta = mudou de status)
    origem = prod / "A_PREMIUM/UV/1UN LONA IMPRESSA 5.00X3.00M_L01.pdf"
    destino = prod / "A_PREMIUM/UV/PRONTOS/1UN LONA IMPRESSA 5.00X3.00M_L01.pdf"
    destino.parent.mkdir(parents=True, exist_ok=True)
    origem.rename(destino)

    assert vc.passada() is True


def test_pdf_apagado_e_regenerado(_isolar_em_tmp):
    prod = _isolar_em_tmp
    _por(prod, "A_PREMIUM/UV/1UN LONA IMPRESSA 5.00X3.00M_L01.pdf")
    vc.passada()

    vc.DESTINO_PDF.unlink()
    assert vc.passada() is True         # PDF sumiu, refaz mesmo sem mudança
