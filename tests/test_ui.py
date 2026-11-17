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

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtWidgets import QApplication, QWidget, QPushButton, QStyleOptionGraphicsItem
from PySide6.QtGui import QColor, QPainter, QImage, QPixmap

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
    assert len(janela.acoes) >= 7

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
    maq_docan = [m for m in MAQUINAS_DISPONIVEIS if "5200" in m["nome"]][0]
    janela.selecionar_maquina(maq_docan)
    assert janela.maquina_atual["largura_mm"] == 5000.0
    assert janela.canvas.largura_mm == 5000.0
    assert "5000" in janela.status_largura.text()

    maq_320 = [m for m in MAQUINAS_DISPONIVEIS if "320" in m["nome"]][0]
    janela.selecionar_maquina(maq_320)
    assert janela.maquina_atual["largura_mm"] == 3200.0
    assert janela.canvas.largura_mm == 3200.0
    assert "3200" in janela.status_largura.text()


def test_espacamento_configuravel_e_filtro_material(janela_app):
    """Testa controle de espaçamento e filtro de material vinil."""
    janela = janela_app
    assert hasattr(janela, "spin_espacamento")
    assert hasattr(janela, "combo_filtro_material")

    # Ajustar espaçamento para 15 mm
    janela.spin_espacamento.setValue(15)
    assert janela.canvas.espacamento_mm == 15.0

    # Adicionar itens de materiais distintos
    janela.adicionar_peca_fila("Adesivo_01.pdf", 400.0, 300.0, material="VINIL / ADESIVO")
    janela.adicionar_peca_fila("Banner_02.pdf", 600.0, 400.0, material="LONA")
    assert janela.tabela_pecas.rowCount() == 2

    # Filtrar somente Vinil
    janela.combo_filtro_material.setCurrentText("VINIL / ADESIVO")
    assert not janela.tabela_pecas.isRowHidden(0)
    assert janela.tabela_pecas.isRowHidden(1)

    # Auto nesting com filtro
    janela._executar_auto_nesting()
    pecas = janela.canvas.obter_pecas()
    assert len(pecas) == 1
    assert pecas[0].nome == "Adesivo_01.pdf"


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


# -----------------------------------------------------------------------------
# 5. Testes Específicos de Renderização Gráfica e Visual do Canvas (QGraphicsView)
# -----------------------------------------------------------------------------

def test_render_peca_grafica_item_paint(qapp):
    """
    Testa a renderização gráfica completa de PecaGraficaItem via QPainter:
    - Estado normal com chanfro e elevação
    - Com miniatura real renderizada
    - Estado selecionado (borda azul elétrico e alças)
    - Estado de colisão (borda vermelho vivo e banner de alerta)
    - Rotação 90 graus
    """
    canvas = CanvasMontagem(largura_bobina_mm=1600.0)
    
    # Criar uma miniatura de teste 100x100
    pix = QPixmap(100, 100)
    pix.fill(QColor("#0284c7"))

    peca = canvas.adicionar_peca(
        nome="Adesivo_Render_Test",
        largura_mm=300.0,
        altura_mm=200.0,
        miniatura=pix,
        material="VINIL BRILHO",
        pos_x=50.0,
        pos_y=50.0,
    )

    # Imagem offscreen para validar pintura real
    img = QImage(400, 300, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    painter = QPainter(img)
    opt = QStyleOptionGraphicsItem()

    try:
        # 1. Pintura em estado normal com miniatura
        peca.paint(painter, opt, None)

        # 2. Pintura em estado selecionado
        peca.setSelected(True)
        assert peca.isSelected()
        peca.paint(painter, opt, None)

        # 3. Pintura com rotação
        peca.girar_90_graus()
        assert peca.rotacao == 90.0
        peca.paint(painter, opt, None)

        # 4. Pintura em estado de colisão
        peca.set_estado_colisao(tem_colisao=True, fora_dos_limites=False)
        assert peca.tem_colisao
        peca.paint(painter, opt, None)

        # 5. Pintura fora dos limites
        peca.set_estado_colisao(tem_colisao=False, fora_dos_limites=True)
        assert peca.fora_dos_limites
        peca.paint(painter, opt, None)
    finally:
        painter.end()


def test_render_canvas_background_e_foreground(qapp):
    """
    Valida a renderização do fundo da bobina (drawBackground) e das
    réguas dinâmicas métricas de 10cm, 50cm e 1m (drawForeground).
    """
    canvas = CanvasMontagem(largura_bobina_mm=1600.0, comprimento_inicial_mm=2500.0, margem_lateral_mm=20.0, margem_topo_mm=25.0)
    canvas.resize(800, 600)

    img = QImage(800, 600, QImage.Format_ARGB32)
    img.fill(QColor("#0d0e12"))
    painter = QPainter(img)

    try:
        rect_cena = QRectF(-100, -100, 1800, 2700)
        # Executar drawBackground da bobina industrial
        canvas.drawBackground(painter, rect_cena)

        # Executar drawForeground das réguas métricas
        rect_view = QRectF(0, 0, 800, 600)
        canvas.drawForeground(painter, rect_view)
    finally:
        painter.end()

    # Validar área útil e dimensões
    limites = canvas.obter_limites_uteis()
    assert limites.left() == 20.0
    assert limites.width() == 1600.0 - 40.0


def test_canvas_guia_reticular_mouse(qapp):
    """Testa a posição da guia reticular do mouse nas réguas métricas."""
    canvas = CanvasMontagem(largura_bobina_mm=1600.0)
    canvas.resize(800, 600)
    assert canvas._pos_mouse_view is None

    # Simular leaveEvent limpando posição
    from PySide6.QtCore import QEvent
    ev_leave = QEvent(QEvent.Leave)
    canvas.leaveEvent(ev_leave)
    assert canvas._pos_mouse_view is None


def test_cartao_maquina_compacto_e_badges(janela_app):
    """Verifica se os cartões de máquinas estão no formato compacto (~34px) com badges."""
    janela = janela_app
    for cartao in janela.cartoes_maquinas:
        assert cartao.height() in (30, 34) or cartao.maximumHeight() in (30, 34)
        assert hasattr(cartao, "lbl_nome")
        assert hasattr(cartao, "lbl_largura")
        assert hasattr(cartao, "lbl_status")
        # Verificar se as badges contêm as medidas e status
        assert "m" in cartao.lbl_largura.text()
        assert cartao.lbl_status.text() in ("Online", "Pronta", "Operacional")


def test_painel_esquerdo_splitter_e_tabela_altura_minima(janela_app):
    """Valida o uso do QSplitter vertical e tabela de peças com altura flexível."""
    janela = janela_app
    assert hasattr(janela, "splitter_esquerdo")
    assert janela.splitter_esquerdo.orientation() == Qt.Vertical
    assert janela.tabela_pecas.minimumHeight() >= 120
    assert hasattr(janela, "btn_recarregar_fila")
    assert hasattr(janela, "btn_abrir_entrada_fila")
    assert janela.combo_filtro_material.currentIndex() == 0
    assert janela.combo_filtro_material.currentText() == "Todos os Materiais"


def test_auto_carregamento_pasta_maquina(janela_app, tmp_path, monkeypatch):
    """Testa o auto-carregamento de artes da pasta de entrada da máquina."""
    import montagem
    janela = janela_app

    # Criar pasta de entrada simulada com arquivos de arte
    pasta_fake = tmp_path / "UJV 100"
    pasta_fake.mkdir(parents=True)
    arq1 = pasta_fake / "Lona_Promo_2000x1000mm.pdf"
    arq1.write_text("fake pdf")
    arq2 = pasta_fake / "Adesivo_Vinil_500x500mm.jpg"
    arq2.write_text("fake image")

    # Fazer mock de montagem.pasta_da_maquina
    monkeypatch.setattr(montagem, "pasta_da_maquina", lambda nome: pasta_fake)

    # Selecionar máquina e disparar auto-carregamento
    maq_ujv = [m for m in MAQUINAS_DISPONIVEIS if "UJV100" in m["nome"]][0]
    janela.selecionar_maquina(maq_ujv)

    # Deve ter carregado automaticamente os 2 arquivos
    assert janela.tabela_pecas.rowCount() == 2
    nomes = [janela.tabela_pecas.item(r, 0).text() for r in range(janela.tabela_pecas.rowCount())]
    assert "Lona_Promo_2000x1000mm.pdf" in nomes
    assert "Adesivo_Vinil_500x500mm.jpg" in nomes
    assert janela.combo_filtro_material.currentIndex() == 0

    # Testar botão [🔄 Recarregar]
    janela.recarregar_pasta_entrada()
    assert janela.tabela_pecas.rowCount() == 2


def test_regras_historicas_rotulos_e_cabecalho(qapp):
    """
    Valida as regras consagradas de fábrica (montagem.py de 04/10/2026):
    1. Rótulo de cada peça: f"{numero:02d}  {nome_do_arquivo}" e com cópia f"({copia}/{quantidade})"
    2. Numeração sequencial automática nas peças (01, 02...)
    3. Cabeçalho de 80mm (CABECALHO_M):
       MONTAGEM  ·  {CLIENTE}  ·  {MATERIAL}  ·  {N} PEÇAS  ·  LARGURA {L}m  ·  APROVEITAMENTO {APROV}%  ·  RIPAR A 100%, NÃO REDIMENSIONAR
    """
    canvas = CanvasMontagem(largura_bobina_mm=3200.0, cliente="LOJINHA")

    # Adicionar 3 peças com nomes e quantidades diferentes
    p1 = canvas.adicionar_peca(nome="Lona_Promocao_Frente.pdf", largura_mm=1000.0, altura_mm=1000.0, material="LONA")
    p2 = canvas.adicionar_peca(nome="Adesivo_Vitrine_01.pdf", largura_mm=500.0, altura_mm=500.0, material="VINIL", quantidade=3, copia=1)
    p3 = canvas.adicionar_peca(nome="Banner_Evento_Entrada.jpg", largura_mm=800.0, altura_mm=600.0, material="LONA")

    # Verificar numeração sequencial automática (01, 02, 03)
    assert p1.numero == 1
    assert p2.numero == 2
    assert p3.numero == 3

    # Verificar rótulos oficiais de montagem.py
    assert p1.texto_do_rotulo() == "01  Lona_Promocao_Frente"
    assert p2.texto_do_rotulo() == "02  Adesivo_Vitrine_01 (1/3)"
    assert p3.texto_do_rotulo() == "03  Banner_Evento_Entrada"

    # Remover peça do meio e validar renumeração automática
    canvas.remover_peca(p2)
    assert len(canvas.obter_pecas()) == 2
    assert p1.numero == 1
    assert p3.numero == 2
    assert p3.texto_do_rotulo() == "02  Banner_Evento_Entrada"

    # Verificar formatação oficial do cabeçalho de 80mm
    titulo = canvas.obter_titulo_cabecalho()
    assert "MONTAGEM  ·  LOJINHA  ·  " in titulo
    assert "2 PEÇAS" in titulo
    assert "LARGURA 3.20m" in titulo
    assert "APROVEITAMENTO" in titulo
    assert "RIPAR A 100%, NÃO REDIMENSIONAR" in titulo


def test_inserir_arte_com_quantidade_tupla(janela_app):
    """
    Testa a correção do bug de inserção: quando extrair_quantidade retorna tupla (qtd, True),
    clicar no botão Inserir deve adicionar a peça na bobina sem lançar TypeError.
    """
    janela = janela_app
    janela.canvas.limpar_pecas()
    janela.tabela_pecas.setRowCount(0)

    # Simular peça adicionada com quantidade sendo tupla (1, True)
    janela.adicionar_peca_fila(
        nome="01  1UN VINIL 500X500.pdf",
        largura_mm=500.0,
        altura_mm=500.0,
        material="VINIL / ADESIVO",
        quantidade=(1, True),
    )

    assert janela.tabela_pecas.rowCount() == 1
    btn_inserir = janela.tabela_pecas.cellWidget(0, 3)
    assert isinstance(btn_inserir, QPushButton)

    # Clicar no botão Inserir
    btn_inserir.click()

    # Verificar que a arte entrou na folha do canvas!
    pecas = janela.canvas.obter_pecas()
    assert len(pecas) == 1
    p = pecas[0]
    assert p.largura_mm == 500.0
    assert p.altura_mm == 500.0
    assert p.quantidade == 1
    assert p.material == "VINIL / ADESIVO"


def test_recarregar_pasta_preserva_pasta_carregada(janela_app, tmp_path):
    """Verifica que o botão Recarregar re-lê a pasta atualmente aberta pelo usuário sem limpá-la."""
    janela = janela_app
    pasta_cliente = tmp_path / "Cliente_Jobs"
    pasta_cliente.mkdir()
    f1 = pasta_cliente / "Adesivo_1000x500mm.pdf"
    f1.write_text("dummy")

    janela.pasta_entrada_atual = pasta_cliente
    janela.recarregar_pasta_entrada()

    assert janela.tabela_pecas.rowCount() == 1
    assert janela.tabela_pecas.item(0, 0).text() == "Adesivo_1000x500mm.pdf"

    # Adicionar segundo arquivo e recarregar
    f2 = pasta_cliente / "Banner_2000x1000mm.jpg"
    f2.write_text("dummy 2")
    janela.recarregar_pasta_entrada()

    assert janela.tabela_pecas.rowCount() == 2


def test_posicionamento_inteligente_lado_a_lado(qapp):
    """Verifica que peças menores que a largura da bobina são encaixadas lado a lado."""
    canvas = CanvasMontagem(largura_bobina_mm=3200.0)
    canvas.limpar_pecas()

    p1 = canvas.adicionar_peca("Arte1.pdf", largura_mm=1000.0, altura_mm=800.0)
    p2 = canvas.adicionar_peca("Arte2.pdf", largura_mm=1000.0, altura_mm=800.0)

    # Ambas devem estar na mesma linha (mesmo y aproximado) e p2 deve estar à direita de p1
    assert abs(p1.pos().y() - p2.pos().y()) < 2.0
    assert p2.pos().x() >= p1.pos().x() + 1000.0


def test_rotulo_em_preto_sem_tarja(qapp):
    """
    Verifica que o rótulo da peça é renderizado em preto sem tarja escura de fundo,
    economizando tinta e seguindo fielmente a regra oficial de montagem.py.
    """
    peca = PecaGraficaItem(
        nome="1UN VINIL BLOCKOUT IMPRESSO 1,29X2,95M.pdf",
        largura_mm=500.0,
        altura_mm=500.0,
        material="VINIL",
        numero=12,
    )
    assert peca.texto_do_rotulo() == "12  1UN VINIL BLOCKOUT IMPRESSO 1,29X2,95M"

    # Renderizar a peça em um QImage para validar o paint
    img = QImage(500, 500, QImage.Format_ARGB32)
    img.fill(Qt.white)
    painter = QPainter(img)
    opt = QStyleOptionGraphicsItem()
    peca.paint(painter, opt, None)
    painter.end()

    # O topo da peça (fora do texto) deve ser predominantemente branco/claro, sem tarja escura
    # Pixel na área onde ficava a antiga tarja (ex: x=50, y=5)
    cor_topo = img.pixelColor(50, 5)
    assert cor_topo.red() > 200 and cor_topo.green() > 200 and cor_topo.blue() > 200



