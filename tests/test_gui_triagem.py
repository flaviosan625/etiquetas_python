"""
Testes unitários para gui_triagem.py (ISSUE-09).
"""

import pathlib
from unittest.mock import Mock, patch
import pytest
import tkinter as tk

import gui_triagem as gt
from motor_pdf import PdfWriter


@pytest.fixture
def tk_root():
    """Fixture para inicializar Tk em modo oculto para testes de interface."""
    try:
        root = tk.Tk()
        root.withdraw()
        yield root
        root.destroy()
    except tk.TclError:
        pytest.skip("Ambiente sem display gráfico Tkinter disponível")


def criar_pdf_teste(caminho: pathlib.Path, largura_pt: float = 283.46, altura_pt: float = 141.73):
    """Cria um PDF minimalista para teste (~0.10 x 0.05 m com ~28.346 pt/cm)."""
    writer = PdfWriter()
    writer.adicionar_pagina(largura_pt=largura_pt, altura_pt=altura_pt, recursos={}, conteudo_bytes=b"")
    writer.salvar(caminho)


# =====================================================================
# Testes da Lógica Pura: ItemTriagem e Escala
# =====================================================================


def test_interpretar_escala():
    assert gt.interpretar_escala("1:1") == 1.0
    assert gt.interpretar_escala("1:10") == 10.0
    assert gt.interpretar_escala("1:20") == 20.0
    assert gt.interpretar_escala("1:5") == 5.0
    assert gt.interpretar_escala("1:2") == 2.0
    assert gt.interpretar_escala("1:50") == 50.0
    assert gt.interpretar_escala("1:100") == 100.0
    assert gt.interpretar_escala("2:1") == pytest.approx(0.5)
    assert gt.interpretar_escala("10") == 10.0
    assert gt.interpretar_escala("") == 1.0


def test_detectar_ou_sugerir_escala_padrao():
    # 1:1 Idêntico
    fator, escala = gt.detectar_ou_sugerir_escala(1.0, 0.5, 1.0, 0.5)
    assert fator == 1.0
    assert escala == "1:1"

    # 1:10
    fator, escala = gt.detectar_ou_sugerir_escala(0.20, 0.10, 2.00, 1.00)
    assert fator == 10.0
    assert escala == "1:10"

    # 1:20
    fator, escala = gt.detectar_ou_sugerir_escala(0.15, 0.10, 3.00, 2.00)
    assert fator == 20.0
    assert escala == "1:20"

    # 1:5
    fator, escala = gt.detectar_ou_sugerir_escala(0.40, 0.20, 2.00, 1.00)
    assert fator == 5.0
    assert escala == "1:5"


def test_detectar_ou_sugerir_escala_rotacionada():
    # PDF girado 90°: 0.10 x 0.20 m -> Alvo: 2.00 x 1.00 m (relação 10x cruzada)
    fator, escala = gt.detectar_ou_sugerir_escala(0.10, 0.20, 2.00, 1.00)
    assert fator == 10.0
    assert escala == "1:10"


def test_detectar_ou_sugerir_escala_nao_proporcional():
    # Proporções distorcidas (largura 10x, altura 2x)
    fator, escala = gt.detectar_ou_sugerir_escala(0.20, 0.50, 2.00, 1.00)
    assert fator == 1.0
    assert escala == "1:1"

    # Valores zerados ou negativos
    fator, escala = gt.detectar_ou_sugerir_escala(0.0, 1.0, 2.0, 1.0)
    assert fator == 1.0
    assert escala == "1:1"


def test_item_triagem_validacao():
    # Item incompleto (sem material)
    item = gt.ItemTriagem(
        arquivo="arte1.pdf",
        larg_pdf_m=0.20,
        alt_pdf_m=0.10,
        escala="1:1",
        larg_final_m=0.20,
        alt_final_m=0.10,
        material=None,
    )
    assert item.status == "PENDENTE"
    assert "Material não definido" in item.avisos

    # Completando o material
    item.material = "LONA 440G"
    valido = item.validar()
    assert valido is True
    assert item.status == "VALIDO"
    assert len(item.avisos) == 0

    # Testando aplicação de escala
    item.aplicar_escala("1:10")
    assert item.fator_escala == 10.0
    assert item.larg_final_m == pytest.approx(2.00)
    assert item.alt_final_m == pytest.approx(1.00)
    assert item.status == "VALIDO"


def test_item_triagem_serializacao():
    item = gt.ItemTriagem(
        arquivo="teste.pdf",
        larg_pdf_m=1.0,
        alt_pdf_m=0.5,
        escala="1:1",
        material="ADESIVO",
        cliente="LOJA A",
        os="999",
        quantidade=3,
    )
    d = item.to_dict()
    assert d["arquivo"] == "teste.pdf"
    assert d["material"] == "ADESIVO"
    assert d["quantidade"] == 3
    assert d["status"] == "VALIDO"

    novo_item = gt.ItemTriagem.from_dict(d)
    assert novo_item.arquivo == item.arquivo
    assert novo_item.material == item.material
    assert novo_item.status == "VALIDO"


# =====================================================================
# Teste de Preparação com motor_pdf e Planilha
# =====================================================================


def test_preparar_itens_para_triagem_com_pdf_e_regras(tmp_path):
    # Cria PDF com ~0.20m x ~0.10m
    # 72 pt/in = 2834.65 pt/m -> 0.20m = ~566.93 pt, 0.10m = ~283.46 pt
    pdf_path = tmp_path / "OS1001_ACME_LONA_200x100CM.pdf"
    criar_pdf_teste(pdf_path, largura_pt=566.93, altura_pt=283.46)

    itens = gt.preparar_itens_para_triagem([pdf_path])
    assert len(itens) == 1
    it = itens[0]
    assert it.arquivo == pdf_path.name
    assert it.os == "1001"
    assert it.cliente == "ACME"
    assert it.material == "LONA"
    # PDF lido: ~0.20 x 0.10m; Alvo do nome: 2.00 x 1.00m -> Detecta escala 1:10
    assert it.escala == "1:10"
    assert it.fator_escala == 10.0
    assert it.larg_final_m == pytest.approx(2.00, abs=0.01)
    assert it.alt_final_m == pytest.approx(1.00, abs=0.01)
    assert it.status == "VALIDO"


def test_preparar_itens_cruzando_com_planilha(tmp_path):
    pdf_path = tmp_path / "banner_evento.pdf"
    criar_pdf_teste(pdf_path, largura_pt=283.46, altura_pt=141.73)  # 0.10 x 0.05m

    dados_planilha = [
        {
            "arquivo": "banner_evento.pdf",
            "quantidade": 5,
            "material": "TECIDO",
            "largura_m": 2.00,
            "altura_m": 1.00,
            "cliente": "PRODUTORA",
            "os": "OS-450",
        }
    ]

    itens = gt.preparar_itens_para_triagem([pdf_path], dados_planilha=dados_planilha)
    assert len(itens) == 1
    it = itens[0]
    assert it.material == "TECIDO"
    assert it.cliente == "PRODUTORA"
    assert it.os == "OS-450"
    assert it.quantidade == 5
    # PDF: 0.10x0.05m -> Alvo: 2.00x1.00m -> Escala 1:20
    assert it.escala == "1:20"
    assert it.larg_final_m == pytest.approx(2.00, abs=0.01)
    assert it.alt_final_m == pytest.approx(1.00, abs=0.01)
    assert it.status == "VALIDO"


# =====================================================================
# Testes da Interface Gráfica JanelaTriagem
# =====================================================================


def test_janela_triagem_adicionar_e_atualizar(tk_root):
    janela = gt.JanelaTriagem(tk_root)
    item1 = gt.ItemTriagem("arte1.pdf", larg_pdf_m=1.0, alt_pdf_m=1.0, material="LONA", quantidade=2)
    item2 = gt.ItemTriagem("arte2.pdf", larg_pdf_m=1.0, alt_pdf_m=1.0, material=None, quantidade=1)

    janela.adicionar_itens([item1, item2])
    assert len(janela.obter_itens()) == 2
    assert "Total: 2" in janela.var_total.get()
    assert "Válidos: 1" in janela.var_validos.get()
    assert "Pendentes: 1" in janela.var_pendentes.get()


def test_janela_triagem_edicao_em_lote(tk_root):
    janela = gt.JanelaTriagem(tk_root)
    item1 = gt.ItemTriagem("arte1.pdf", larg_pdf_m=0.2, alt_pdf_m=0.1, material=None)
    item2 = gt.ItemTriagem("arte2.pdf", larg_pdf_m=0.2, alt_pdf_m=0.1, material=None)
    janela.adicionar_itens([item1, item2])

    assert item1.status == "PENDENTE"
    assert item2.status == "PENDENTE"

    # Aplicação em lote
    valores = {
        "material": "PS 2MM",
        "cliente": "SHOPPING",
        "escala": "1:10",
        "quantidade": 4,
    }
    janela.aplicar_edicao_lote([item1, item2], valores)

    assert item1.material == "PS 2MM"
    assert item1.cliente == "SHOPPING"
    assert item1.quantidade == 4
    assert item1.escala == "1:10"
    assert item1.larg_final_m == pytest.approx(2.0)
    assert item1.status == "VALIDO"

    assert item2.material == "PS 2MM"
    assert item2.status == "VALIDO"
    assert "Válidos: 2" in janela.var_validos.get()


def test_janela_triagem_despachar_validados(tk_root):
    callback_mock = Mock()
    janela = gt.JanelaTriagem(tk_root, ao_despachar=callback_mock)

    item_valido = gt.ItemTriagem("valido.pdf", larg_pdf_m=1.0, alt_pdf_m=0.5, material="LONA")
    item_pendente = gt.ItemTriagem("pendente.pdf", larg_pdf_m=1.0, alt_pdf_m=0.5, material=None)
    janela.adicionar_itens([item_valido, item_pendente])

    with patch("tkinter.messagebox.showinfo"):
        despachados = janela.despachar_validados()

    assert len(despachados) == 1
    assert despachados[0].arquivo == "valido.pdf"
    assert despachados[0].status == "DESPACHADO"
    assert item_pendente.status == "PENDENTE"
    assert "Despachados: 1" in janela.var_despachados.get()
    callback_mock.assert_called_once_with([item_valido])
