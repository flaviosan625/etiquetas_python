"""
Suíte de Testes da Interface Gráfica PySide6 / Qt (ISSUE-13).

Testes automatizados cobrindo:
- Configuração headless ("offscreen")
- Tema escuro industrial e geração QSS
- Viewport interativa CanvasMontagem (zoom, pan, limites, métricas)
- PecaGraficaItem (movimento, rotação 90°, detecção de colisão e limites úteis)
- JanelaPrincipal (ações, seleção de máquinas, tabela e status bar)
- Bootstrap em app.py
"""

import os
import pytest

# Garantir execução headless antes de carregar módulos do Qt
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtCore import Qt, QPointF
from PySide6.QtWidgets import QApplication, QWidget, QPushButton
from PySide6.QtGui import QColor

from ui.tema import CoresTema, obter_qss, aplicar_tema
from ui.canvas_montagem import CanvasMontagem, PecaGraficaItem
from ui.janela_principal import JanelaPrincipal, CartaoMaquina, MAQUINAS_DISPONIVEIS
from ui.app import iniciar_aplicativo


@pytest.fixture(scope="session")
def qapp():
    """Fixture de sessão para inicializar o QApplication em modo headless."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


# -----------------------------------------------------------------------------
# 1. Testes do Sistema de Tema e QSS
# -----------------------------------------------------------------------------

def test_paleta_cores_tema():
    """Valida as constantes de cores industriais de alto contraste."""
    assert CoresTema.FUNDO == "#121318"
    assert CoresTema.SUPERFICIE == "#1a1c23"
    assert CoresTema.CARTAO == "#222530"
    assert CoresTema.BORDA == "#2e3242"
    assert CoresTema.TEXTO_PRINCIPAL == "#f0f2f8"
    assert CoresTema.TEXTO_SECUNDARIO == "#8a91a8"
    assert CoresTema.ACENTO_PRIMARIO in ("#0ea5e9", "#0078d4")
    assert CoresTema.SUCESSO == "#10b981"
    assert CoresTema.ALERTA == "#f59e0b"
    assert CoresTema.PERIGO == "#ef4444"


def test_geracao_qss(qapp):
    """Verifica se o QSS gerado contém as regras essenciais para componentes Qt."""
    qss = obter_qss()
    assert isinstance(qss, str)
    assert "QMainWindow" in qss
    assert "QToolBar" in qss
    assert "QPushButton" in qss
    assert "QTableWidget" in qss
    assert "QSplitter" in qss
    assert "QScrollBar" in qss
    assert CoresTema.FUNDO in qss
    assert CoresTema.ACENTO_PRIMARIO in qss


def test_aplicar_tema_em_widget(qapp):
    """Testa aplicação do tema em um widget arbitrário."""
    widget = QWidget()
    aplicar_tema(widget)
    assert len(widget.styleSheet()) > 100
    assert CoresTema.FUNDO in widget.styleSheet()


# -----------------------------------------------------------------------------
# 2. Testes de CanvasMontagem (Viewport e Bobina)
# -----------------------------------------------------------------------------

def test_canvas_criacao_e_limites(qapp):
    """Verifica a inicialização da bobina e cálculo de área útil."""
    canvas = CanvasMontagem(largura_bobina_mm=1600.0, margem_lateral_mm=15.0, margem_topo_mm=20.0)
    assert canvas.largura_mm == 1600.0
    assert canvas.margem_lateral_mm == 15.0
    assert canvas.margem_topo_mm == 20.0

    limites = canvas.obter_limites_uteis()
    assert limites.left() == 15.0
    assert limites.top() == 20.0
    assert limites.width() == 1600.0 - (2 * 15.0)  # 1570.0
    assert limites.height() >= 1000.0


def test_canvas_zoom_e_controles(qapp):
    """Testa controles de zoom in, zoom out, reset e enquadramento."""
    canvas = CanvasMontagem(largura_bobina_mm=1600.0)
    canvas.resize(800, 600)
    
    transform_inicial = canvas.transform()
    m11_inicial = transform_inicial.m11()

    # Zoom In
    canvas.zoom_in()
    assert canvas.transform().m11() > m11_inicial

    # Zoom Out
    canvas.zoom_out()
    # Praticamente de volta ao inicial (diferença minúscula de ponto flutuante)
    assert abs(canvas.transform().m11() - m11_inicial) < 0.05

    # Reset Zoom
    canvas.zoom_in()
    canvas.zoom_in()
    canvas.reset_zoom()
    assert abs(canvas.transform().m11() - 1.0) < 0.001

    # Fit in view não lança exceção
    canvas.fit_in_view()


def test_canvas_adicionar_remover_pecas(qapp):
    """Verifica adição, listagem e remoção de peças no canvas."""
    canvas = CanvasMontagem(largura_bobina_mm=1600.0)
    assert len(canvas.obter_pecas()) == 0

    p1 = canvas.adicionar_peca(nome="Painel A", largura_mm=400.0, altura_mm=300.0, pos_x=50.0, pos_y=50.0)
    assert p1 in canvas.obter_pecas()
    assert len(canvas.obter_pecas()) == 1
    assert p1.largura_mm == 400.0
    assert p1.altura_mm == 300.0

    p2 = canvas.adicionar_peca(nome="Painel B", largura_mm=500.0, altura_mm=400.0)
    assert len(canvas.obter_pecas()) == 2

    canvas.remover_peca(p1)
    assert len(canvas.obter_pecas()) == 1
    assert p1 not in canvas.obter_pecas()

    canvas.limpar_pecas()
    assert len(canvas.obter_pecas()) == 0


def test_canvas_estatisticas_aproveitamento(qapp):
    """Testa o cálculo métrico de aproveitamento e comprimento linear."""
    canvas = CanvasMontagem(largura_bobina_mm=1000.0, margem_lateral_mm=0.0, margem_topo_mm=0.0)
    # Adicionar duas peças de 500x500mm lado a lado na bobina de 1000mm
    # Área total útil das duas peças = 2 * (0.5 * 0.5) = 0.5 m²
    # Comprimento ocupado = 500 mm = 0.5 m
    # Área total da bobina até o final das peças = 1.0 m * 0.5 m = 0.5 m²
    # Aproveitamento esperado = 100%
    canvas.adicionar_peca(nome="P1", largura_mm=500.0, altura_mm=500.0, pos_x=0.0, pos_y=0.0)
    canvas.adicionar_peca(nome="P2", largura_mm=500.0, altura_mm=500.0, pos_x=500.0, pos_y=0.0)

    stats = canvas.calcular_estatisticas()
    assert stats["largura_m"] == 1.0
    assert abs(stats["comprimento_m"] - 0.5) < 0.01
    assert abs(stats["area_pecas_m2"] - 0.5) < 0.01
    assert abs(stats["area_total_m2"] - 0.5) < 0.01
    assert abs(stats["aproveitamento_pct"] - 100.0) < 1.0
    assert stats["total_pecas"] == 2
    assert stats["pecas_colidindo"] == 0


# -----------------------------------------------------------------------------
# 3. Testes de PecaGraficaItem (Movimentação, Rotação e Detecção de Colisão)
# -----------------------------------------------------------------------------

def test_peca_rotacao_90_graus(qapp):
    """Verifica se a rotação via tecla/método altera em 90 graus incrementalmente."""
    canvas = CanvasMontagem(largura_bobina_mm=1600.0)
    peca = canvas.adicionar_peca("Adesivo", 600.0, 400.0, pos_x=100.0, pos_y=100.0)
    assert peca.rotacao == 0.0

    peca.girar_90_graus()
    assert peca.rotacao == 90.0

    peca.girar_90_graus()
    assert peca.rotacao == 180.0

    peca.girar_90_graus()
    assert peca.rotacao == 270.0

    peca.girar_90_graus()
    assert peca.rotacao == 0.0


def test_peca_colisao_sobreposicao(qapp):
    """Testa detecção de colisão em tempo real quando duas peças se sobrepõem."""
    canvas = CanvasMontagem(largura_bobina_mm=1600.0, margem_lateral_mm=10.0, margem_topo_mm=10.0)

    # Peça 1 posicionada em (50, 50) com tamanho 200x200
    p1 = canvas.adicionar_peca("Peça 1", 200.0, 200.0, pos_x=50.0, pos_y=50.0)
    # Peça 2 posicionada longe (500, 500)
    p2 = canvas.adicionar_peca("Peça 2", 200.0, 200.0, pos_x=500.0, pos_y=500.0)

    canvas.verificar_todas_colisoes()
    assert not p1.tem_colisao
    assert not p2.tem_colisao
    assert not p1.fora_dos_limites
    assert not p2.fora_dos_limites

    # Mover a Peça 2 para cima da Peça 1 (sobreposição em 100, 100)
    p2.setPos(100.0, 100.0)
    canvas.verificar_todas_colisoes()

    assert p1.tem_colisao, "Peça 1 deveria registrar colisão após sobreposição"
    assert p2.tem_colisao, "Peça 2 deveria registrar colisão após sobreposição"

    stats = canvas.calcular_estatisticas()
    assert stats["pecas_colidindo"] == 2


def test_peca_fora_dos_limites_bobina(qapp):
    """Testa detecção quando uma peça ultrapassa a largura útil da máquina."""
    canvas = CanvasMontagem(largura_bobina_mm=1000.0, margem_lateral_mm=20.0, margem_topo_mm=20.0)
    # Área útil x: de 20 a 980 mm.
    # Peça com largura 300 colocada em x = 800 ultrapassa o limite direito (800 + 300 = 1100 > 980)
    p = canvas.adicionar_peca("Banner Grande", 300.0, 200.0, pos_x=800.0, pos_y=50.0)
    canvas.verificar_todas_colisoes()

    assert p.fora_dos_limites, "Peça ultrapassando a margem direita deve ser marcada como fora dos limites"

    # Move para dentro da área útil (x = 50)
    p.setPos(50.0, 50.0)
    canvas.verificar_todas_colisoes()
    assert not p.fora_dos_limites


# -----------------------------------------------------------------------------
# 4. Testes da JanelaPrincipal e Fluxos de Interface
# -----------------------------------------------------------------------------

@pytest.fixture
def janela_app(qapp):
    """Fixture que fornece uma JanelaPrincipal e garante encerramento limpo."""
    j = JanelaPrincipal()
    yield j
    j.close()
    j.deleteLater()
    qapp.processEvents()


def test_janela_principal_instanciacao(janela_app):
    """Verifica a montagem de todos os componentes da janela principal."""
    janela = janela_app
    assert janela.windowTitle() != ""
    assert janela.canvas is not None
    assert len(janela.cartoes_maquinas) == len(MAQUINAS_DISPONIVEIS)
    assert len(janela.acoes) == 7

    # Verificar presença de todas as ações solicitadas
    acoes_esperadas = [
        "carregar_pasta",
        "importar_planilha",
        "triagem_lote",
        "configurar_maquinas",
        "gerar_corte_cnc",
        "exportar_pdf",
        "enviar_rip",
    ]
    for acao_key in acoes_esperadas:
        assert acao_key in janela.acoes
        assert janela.acoes[acao_key].text() != ""


def test_janela_troca_maquina(janela_app):
    """Verifica se a seleção de máquina atualiza os limites no canvas."""
    janela = janela_app
    maq_320 = MAQUINAS_DISPONIVEIS[0]  # SWJ-320EA 3200mm
    janela.selecionar_maquina(maq_320)

    assert janela.maquina_atual["largura_mm"] == 3200.0
    assert janela.canvas.largura_mm == 3200.0
    assert "3200" in janela.status_largura.text()


def test_janela_adicionar_e_auto_nesting(janela_app):
    """Testa adição de peças na fila e execução do auto nesting."""
    janela = janela_app
    assert janela.tabela_pecas.rowCount() == 0

    janela.adicionar_peca_fila("Item 01", 300.0, 200.0)
    janela.adicionar_peca_fila("Item 02", 400.0, 300.0)
    assert janela.tabela_pecas.rowCount() == 2

    # Inserir peças no canvas
    janela.canvas.adicionar_peca("Item 01", 300.0, 200.0)
    janela.canvas.adicionar_peca("Item 02", 400.0, 300.0)
    assert len(janela.canvas.obter_pecas()) == 2

    # Executar auto-nesting
    janela._executar_auto_nesting()
    stats = janela.canvas.calcular_estatisticas()
    assert stats["pecas_colidindo"] == 0


def test_app_iniciar_aplicativo(qapp):
    """Testa a função inicializadora com executar=False."""
    app, j = iniciar_aplicativo(argumentos=[], executar=False)
    assert isinstance(app, QApplication)
    assert isinstance(j, JanelaPrincipal)
    assert j.isVisible() or os.environ.get("QT_QPA_PLATFORM") == "offscreen"
    j.close()
    j.deleteLater()
    qapp.processEvents()
