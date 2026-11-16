"""
Testes unitários do WorkflowStepper (Barra de Progresso Visual de Etapas Industrial).
"""

import os
import pytest

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from ui.workflow_stepper import WorkflowStepper, ETAPAS_PADRAO


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_workflow_stepper_inicializacao(qapp):
    stepper = WorkflowStepper()
    assert len(stepper.cartoes) == 5
    assert stepper.obter_etapa_atual() == 0

    # Testar textos das 5 etapas
    assert "Entrada & Triagem" in ETAPAS_PADRAO[0]["titulo"]
    assert "Substrato" in ETAPAS_PADRAO[1]["titulo"]
    assert "Máquina" in ETAPAS_PADRAO[2]["titulo"]
    assert "Encaixe" in ETAPAS_PADRAO[3]["titulo"]
    assert "Produção" in ETAPAS_PADRAO[4]["titulo"]


def test_workflow_stepper_navegacao(qapp):
    stepper = WorkflowStepper()
    mudancas = []
    stepper.etapa_alterada.connect(lambda idx: mudancas.append(idx))

    # Avançar etapa
    stepper.avancar_etapa()
    assert stepper.obter_etapa_atual() == 1
    assert stepper.etapas_concluidas[0] is True
    assert mudancas == [1]

    # Navegação direta 1-based e 0-based
    stepper.ir_para_etapa(3)  # Etapa 3 (índice 2)
    assert stepper.obter_etapa_atual() == 2

    stepper.ir_para_etapa(5)  # Etapa 5 (índice 4)
    assert stepper.obter_etapa_atual() == 4
    assert not stepper.btn_avancar.isVisible()  # Última etapa oculta botão avançar

    # Voltar / retroceder
    stepper.retroceder_etapa()
    assert stepper.obter_etapa_atual() == 3


def test_workflow_stepper_acao_disparada(qapp):
    stepper = WorkflowStepper()
    acoes = []
    stepper.acao_etapa_disparada.connect(lambda idx: acoes.append(idx))

    stepper.definir_etapa_atual(0)
    stepper.btn_acao_etapa.click()
    assert acoes == [0]

    stepper.definir_etapa_atual(3)
    stepper.btn_acao_etapa.click()
    assert acoes == [0, 3]
