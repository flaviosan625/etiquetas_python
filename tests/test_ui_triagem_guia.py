"""
tests/test_ui_triagem_guia.py — Testes do Guia Passo a Passo e Diálogo de Triagem em Lote.
"""

import os
import pytest

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from ui.guia_passo_a_passo import GuiaPassoAPasso, ETAPAS_PRODUCAO
from ui.dialogo_triagem import DialogoTriagemLote
from ui.janela_principal import JanelaPrincipal


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_guia_passo_a_passo_etapas(qapp):
    guia = GuiaPassoAPasso()
    assert len(guia.itens_etapas) == 5
    assert guia.etapa_atual == 1

    # Avançar etapas
    guia.avancar_etapa()
    assert guia.etapa_atual == 2
    assert guia.itens_etapas[1].concluida is True
    assert guia.itens_etapas[2].ativa is True

    # Pular para etapa 4
    guia.ir_para_etapa(4)
    assert guia.etapa_atual == 4
    assert guia.itens_etapas[3].concluida is True
    assert guia.itens_etapas[4].ativa is True

    # Pular para última etapa
    guia.ir_para_etapa(5)
    assert guia.etapa_atual == 5
    assert "Concluído" in guia.btn_proximo.text()


def test_dialogo_triagem_lote(qapp, tmp_path):
    # Criar arquivos falsos para teste de triagem
    arq1 = tmp_path / "1UN_VINIL_BRILHO_1000x500MM_PROMO.png"
    arq1.write_bytes(b"dummy")

    arq2 = tmp_path / "2UN_LONA_440G_2000x1000MM_FACHADA.jpg"
    arq2.write_bytes(b"dummy")

    dialogo = DialogoTriagemLote(pasta_inicial=tmp_path)
    assert dialogo.tabela.columnCount() >= 8
    assert dialogo.tabela.rowCount() == 2

    # Verificar seleção e aprovação
    dialogo.aprovar_todas()
    assert dialogo.tabela.item(0, 0).checkState() == Qt.Checked
    assert dialogo.tabela.item(1, 0).checkState() == Qt.Checked

    # Despachar
    aprovados = []
    dialogo.artes_aprovadas.connect(lambda l: aprovados.extend(l))
    dialogo.avancar_para_montagem()

    assert len(aprovados) == 2
    assert aprovados[0]["nome"] == "1UN_VINIL_BRILHO_1000x500MM_PROMO.png"
    assert aprovados[0]["material"] == "VINIL / ADESIVO"


def test_janela_principal_integracao_guia(qapp):
    janela = JanelaPrincipal()
    assert hasattr(janela, "guia_passo")
    assert janela.guia_passo.etapa_atual == 1

    # Simular recebimento de artes da triagem
    artes_fake = [
        {
            "nome": "Arte_Aprovada.pdf",
            "largura_mm": 1200.0,
            "altura_mm": 800.0,
            "material": "VINIL / ADESIVO",
            "quantidade": 1,
            "caminho": None,
            "miniatura": None,
        }
    ]
    janela._ao_receber_artes_triadas(artes_fake)

    assert janela.tabela_pecas.rowCount() == 1
    assert janela.guia_passo.etapa_atual == 2

    # Troca de máquina avança para etapa 4
    janela.guia_passo.ir_para_etapa(3)
    janela.selecionar_maquina(janela.maquinas[0])
    assert janela.guia_passo.etapa_atual == 4

    # Executar auto-nesting avança para etapa 5
    janela._executar_auto_nesting()
    assert janela.guia_passo.etapa_atual == 5

    janela.close()
    janela.deleteLater()
    qapp.processEvents()
