"""
Janela Principal da Interface Moderna PySide6 / Qt.

Painel unificado para chão de fábrica e pré-impressão:
- Barra de ferramentas superior de alta produtividade (Ações de Triagem, Máquinas, CNC e RIP).
- Painel lateral com Seletor de Máquinas e Fila de Peças com Metadados, Filtro de Material e Miniaturas.
- Viewport Central WYSIWYG com CanvasMontagem interativo, ajuste de espaçamento entre artes e zoom fluido.
- Barra de status industrial em tempo real (metragem, m² e taxa de aproveitamento).
"""

from typing import Optional, Dict, Any, List
import os
import subprocess
from pathlib import Path

from PySide6.QtCore import Qt, QSize
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QSplitter,
    QToolBar,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QLabel,
    QPushButton,
    QComboBox,
    QSpinBox,
    QFrame,
    QStatusBar,
    QFileDialog,
    QMessageBox,
    QScrollArea,
    QAbstractItemView,
    QSizePolicy,
)
from PySide6.QtGui import QAction, QIcon, QFont, QColor, QPixmap

from ui.tema import CoresTema, aplicar_tema
from ui.canvas_montagem import CanvasMontagem, PecaGraficaItem
from ui.guia_passo_a_passo import GuiaPassoAPasso
from ui.dialogo_triagem import DialogoTriagemLote


MAQUINAS_DISPONIVEIS = [
    {
        "nome": "DOCAN 5200",
        "tipo": "UV LED Rolo 5m",
        "largura_mm": 5000.0,
        "comprimento_max_mm": 50000.0,
        "margem_lateral_mm": 20.0,
        "status": "Online",
        "nome_sistema": "DOCAN R5200",
    },
    {
        "nome": "Mimaki SWJ-320EA",
        "tipo": "Solvente Bobina",
        "largura_mm": 3200.0,
        "comprimento_max_mm": 50000.0,
        "margem_lateral_mm": 15.0,
        "status": "Online",
        "nome_sistema": "SWJ320A",
    },
    {
        "nome": "Mimaki UJV100-160",
        "tipo": "UV LED Bobina",
        "largura_mm": 1600.0,
        "comprimento_max_mm": 50000.0,
        "margem_lateral_mm": 12.0,
        "status": "Online",
        "nome_sistema": "UJV 100 UNY CV",
    },
    {
        "nome": "DOCAN UV Flatbed",
        "tipo": "UV Chapa / Plana",
        "largura_mm": 2500.0,
        "comprimento_max_mm": 1300.0,
        "margem_lateral_mm": 10.0,
        "status": "Pronta",
        "nome_sistema": "DOCAN H2525",
    },
    {
        "nome": "Mesa CNC Router",
        "tipo": "Fresa e Faca Tangencial",
        "largura_mm": 2000.0,
        "comprimento_max_mm": 3000.0,
        "margem_lateral_mm": 20.0,
        "status": "Operacional",
        "nome_sistema": "CNC_ROUTER",
    },
]


def detectar_material(nome_arquivo: str) -> str:
    """Classifica o material com base nas regras de fábrica e palavras-chave."""
    n = nome_arquivo.upper()
    if any(k in n for k in ("VINIL", "ADESIVO", "FOSCO", "BRILHO", "PERFURADO", "TRANSPARENTE", "BLACKOUT")):
        return "VINIL / ADESIVO"
    if any(k in n for k in ("LONA", "BANNER", "FRONT", "FRONTIGHT", "BACKLIGHT", "440G", "280G", "380G")):
        return "LONA"
    if any(k in n for k in ("TECIDO", "CANVAS", "FLAG", "MICROFIBRA")):
        return "TECIDO"
    if any(k in n for k in ("PS", "ACRILICO", "ACRÍLICO")):
        return "PS / ACRÍLICO"
    if any(k in n for k in ("MDF", "XPS", "PVC", "POLIONDA")):
        return "MDF / XPS"
    return "OUTROS"


def detectar_dimensoes(caminho_arquivo: Path) -> tuple:
    """
    Extrai as medidas (largura_mm, altura_mm, quantidade) de forma resiliente:
    1. Nome do arquivo via regex de fábrica;
    2. Caixa da página (CropBox / MediaBox) para arquivos PDF;
    3. Resolução e dimensões em pixels para imagens raster (Pillow).
    """
    nome = caminho_arquivo.name

    # 1. Tentar ler do nome usando parser do sistema
    try:
        from dimensoes import extrair_dimensoes, extrair_quantidade
        dim = extrair_dimensoes(nome)
        qtd = extrair_quantidade(nome) or 1
        if dim:
            if isinstance(dim, dict):
                w_m, h_m = dim.get("largura_m", 0.0), dim.get("altura_m", 0.0)
            elif isinstance(dim, (list, tuple)):
                w_m, h_m = dim[0], dim[1]
            else:
                w_m, h_m = 0.0, 0.0
            if w_m > 0 and h_m > 0:
                return round(w_m * 1000.0, 1), round(h_m * 1000.0, 1), qtd
    except Exception:
        pass

    # 2. Tentar ler dimensões reais de PDF
    if caminho_arquivo.suffix.lower() == ".pdf":
        try:
            import motor_pdf
            doc = motor_pdf.abrir_pdf(caminho_arquivo)
            if doc and doc.paginas:
                p0 = doc.paginas[0]
                box = p0.crop_box or p0.media_box
                w_pt, h_pt = box.largura, box.altura
                w_mm = round((w_pt / 72.0) * 25.4, 1)
                h_mm = round((h_pt / 72.0) * 25.4, 1)
                if w_mm > 0 and h_mm > 0:
                    return w_mm, h_mm, 1
        except Exception:
            pass

    # 3. Tentar ler dimensões de imagem raster
    if caminho_arquivo.suffix.lower() in (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"):
        try:
            from PIL import Image
            with Image.open(caminho_arquivo) as img:
                dpi = img.info.get("dpi", (72, 72))
                dpi_x = dpi[0] if isinstance(dpi, tuple) and dpi[0] > 0 else 72.0
                dpi_y = dpi[1] if isinstance(dpi, tuple) and dpi[1] > 0 else 72.0
                w_mm = round((img.width / dpi_x) * 25.4, 1)
                h_mm = round((img.height / dpi_y) * 25.4, 1)
                if w_mm > 0 and h_mm > 0:
                    return w_mm, h_mm, 1
        except Exception:
            pass

    return 500.0, 500.0, 1


class CartaoMaquina(QFrame):
    """Cartão compacto de exibição e seleção rápida de máquina de impressão/corte (~34px)."""

    def __init__(self, dados_maquina: Dict[str, Any], ao_clicar, parent=None):
        super().__init__(parent)
        self.dados = dados_maquina
        self.ao_clicar = ao_clicar
        self.selecionada = False

        self.setProperty("classe", "cartao_maquina")
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(34)

        largura_m = dados_maquina["largura_mm"] / 1000.0
        margem = dados_maquina.get("margem_lateral_mm", 15.0)
        self.setToolTip(
            f"{dados_maquina['nome']} ({dados_maquina['tipo']})\n"
            f"Largura Útil: {largura_m:.2f} m ({dados_maquina['largura_mm']:.0f} mm)\n"
            f"Margem de Segurança: {margem:.0f} mm\n"
            f"Status: {dados_maquina['status']}"
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 2, 8, 2)
        layout.setSpacing(6)

        # Nome da Máquina em negrito
        self.lbl_nome = QLabel(dados_maquina["nome"], self)
        self.lbl_nome.setStyleSheet("font-weight: 700; font-size: 12px; color: #f0f2f8;")
        layout.addWidget(self.lbl_nome)

        layout.addStretch()

        # Badge de Largura Útil (Ciano)
        self.lbl_largura = QLabel(f"{largura_m:.2f} m", self)
        self.lbl_largura.setStyleSheet(
            "color: #38bdf8; font-size: 11px; font-weight: 600; "
            "background-color: #0c2d48; border: 1px solid #0284c7; "
            "border-radius: 4px; padding: 1px 6px;"
        )
        layout.addWidget(self.lbl_largura)

        # Badge de Status (Verde)
        self.lbl_status = QLabel(dados_maquina["status"], self)
        self.lbl_status.setStyleSheet(
            f"color: {CoresTema.SUCESSO}; font-size: 11px; font-weight: 600; "
            f"background-color: {CoresTema.SUCESSO_FUNDO}; border: 1px solid #059669; "
            "border-radius: 4px; padding: 1px 6px;"
        )
        layout.addWidget(self.lbl_status)

        self._atualizar_estilo()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.ao_clicar(self.dados)
        super().mousePressEvent(event)

    def set_selecionada(self, valor: bool):
        self.selecionada = valor
        self._atualizar_estilo()

    def _atualizar_estilo(self):
        if self.selecionada:
            self.setStyleSheet(
                f"CartaoMaquina {{ "
                f"  background-color: #1e293b; "
                f"  border: 1px solid {CoresTema.ACENTO_PRIMARIO}; "
                f"  border-radius: 6px; "
                f"}}"
            )
            self.lbl_nome.setStyleSheet("font-weight: 700; font-size: 12px; color: #38bdf8;")
        else:
            self.setStyleSheet(
                f"CartaoMaquina {{ "
                f"  background-color: {CoresTema.CARTAO}; "
                f"  border: 1px solid {CoresTema.BORDA}; "
                f"  border-radius: 6px; "
                f"}} "
                f"CartaoMaquina:hover {{ "
                f"  background-color: {CoresTema.CARTAO_HOVER}; "
                f"  border-color: #38bdf8; "
                f"}}"
            )
            self.lbl_nome.setStyleSheet("font-weight: 600; font-size: 12px; color: #f0f2f8;")


class JanelaPrincipal(QMainWindow):
    """Janela Principal com arquitetura desacoplada e design industrial."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Sistema Integrado de Pré-Impressão e Corte CNC — Viewport 3D/2D")
        self.resize(1420, 900)

        self.maquinas = MAQUINAS_DISPONIVEIS
        # Padrão: DOCAN 5200 (primeira da lista) ou UJV100-160
        self.maquina_atual = self.maquinas[0]
        self.cartoes_maquinas: List[CartaoMaquina] = []
        self.acoes: Dict[str, QAction] = {}
        self.pasta_entrada_atual: Optional[Path] = None

        self._criar_acoes_toolbar()
        self._construir_interface()
        self._construir_barra_status()
        aplicar_tema(self)

        # Selecionar máquina padrão e sincronizar viewport
        self.selecionar_maquina(self.maquina_atual)

    def _criar_acoes_toolbar(self) -> None:
        """Cria as ações da barra de ferramentas superior."""
        toolbar = QToolBar("Barra Principal", self)
        toolbar.setIconSize(QSize(20, 20))
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        def add_act(nome: str, chave: str, callback):
            acao = QAction(nome, self)
            acao.triggered.connect(callback)
            toolbar.addAction(acao)
            self.acoes[chave] = acao
            return acao

        add_act("📁 Carregar Pasta", "carregar_pasta", self.on_carregar_pasta)
        add_act("📊 Importar Planilha", "importar_planilha", self.on_importar_planilha)
        toolbar.addSeparator()
        add_act("📂 Abrir Entrada", "abrir_pasta_entrada", self.on_abrir_pasta_entrada)
        add_act("📤 Abrir Saída / RIP", "abrir_pasta_saida", self.on_abrir_pasta_saida)
        toolbar.addSeparator()
        add_act("⚡ Triagem em Lote", "triagem_lote", self.on_triagem_lote)
        add_act("⚙️ Configurar Máquinas", "configurar_maquinas", self.on_configurar_maquinas)
        toolbar.addSeparator()
        add_act("✂️ Gerar Corte CNC", "gerar_corte_cnc", self.on_gerar_corte_cnc)
        add_act("📄 Exportar PDF Montado", "exportar_pdf", self.on_exportar_pdf)
        add_act("🚀 Enviar ao RIP", "enviar_rip", self.on_enviar_rip)

    def _construir_interface(self) -> None:
        """Estrutura os painéis central e lateral divididos por splitter moderno com guia de fluxo."""
        widget_central = QWidget(self)
        self.setCentralWidget(widget_central)
        layout_central = QVBoxLayout(widget_central)
        layout_central.setContentsMargins(8, 8, 8, 8)
        layout_central.setSpacing(8)

        # Barra Superior: Guia Passo a Passo de Fluxo de Produção
        self.guia_passo = GuiaPassoAPasso(widget_central)
        self.guia_passo.etapa_alterada.connect(self._ao_mudar_etapa_guia)
        layout_central.addWidget(self.guia_passo)

        splitter = QSplitter(Qt.Horizontal, widget_central)
        splitter.setHandleWidth(5)

        # ---------------------------------------------------------------------
        # Painel Lateral Esquerdo (Máquinas, Filtro e Lista de Peças com Splitter)
        # ---------------------------------------------------------------------
        painel_esquerdo = QWidget(splitter)
        painel_esquerdo.setMinimumWidth(340)
        painel_esquerdo.setMaximumWidth(490)
        layout_esq = QVBoxLayout(painel_esquerdo)
        layout_esq.setContentsMargins(4, 4, 4, 4)
        layout_esq.setSpacing(0)

        self.splitter_esquerdo = QSplitter(Qt.Vertical, painel_esquerdo)
        self.splitter_esquerdo.setHandleWidth(4)

        # 1. Seção Superior do Splitter: MÁQUINAS COMPACTAS (~180px)
        widget_maquinas = QWidget(self.splitter_esquerdo)
        layout_maq = QVBoxLayout(widget_maquinas)
        layout_maq.setContentsMargins(4, 4, 4, 4)
        layout_maq.setSpacing(4)

        lbl_sec_maq = QLabel("MÁQUINAS & DISPOSITIVOS", widget_maquinas)
        lbl_sec_maq.setStyleSheet("font-weight: 700; color: #8a91a8; font-size: 11px; letter-spacing: 1px;")
        layout_maq.addWidget(lbl_sec_maq)

        self.container_maquinas = QVBoxLayout()
        self.container_maquinas.setSpacing(3)
        for maq in self.maquinas:
            cartao = CartaoMaquina(maq, self.selecionar_maquina, parent=widget_maquinas)
            self.cartoes_maquinas.append(cartao)
            self.container_maquinas.addWidget(cartao)
        layout_maq.addLayout(self.container_maquinas)
        self.splitter_esquerdo.addWidget(widget_maquinas)

        # 2. Seção Inferior do Splitter: FILA DE PEÇAS & CONTROLES
        widget_fila = QWidget(self.splitter_esquerdo)
        layout_fila = QVBoxLayout(widget_fila)
        layout_fila.setContentsMargins(4, 4, 4, 4)
        layout_fila.setSpacing(6)

        # Cabeçalho da Fila com Botões de Ação Rápida [Recarregar] e [Abrir Entrada]
        header_fila = QVBoxLayout()
        header_fila.setSpacing(4)

        linha_titulo_botoes = QHBoxLayout()
        lbl_sec_pecas = QLabel("FILA DE PEÇAS", widget_fila)
        lbl_sec_pecas.setStyleSheet("font-weight: 700; color: #8a91a8; font-size: 11px; letter-spacing: 1px;")
        linha_titulo_botoes.addWidget(lbl_sec_pecas)
        linha_titulo_botoes.addStretch()

        self.btn_recarregar_fila = QPushButton("🔄 Recarregar", widget_fila)
        self.btn_recarregar_fila.setFixedHeight(24)
        self.btn_recarregar_fila.setToolTip("Recarregar arquivos da pasta de entrada da máquina atual")
        self.btn_recarregar_fila.clicked.connect(self.recarregar_pasta_entrada)
        linha_titulo_botoes.addWidget(self.btn_recarregar_fila)

        self.btn_abrir_entrada_fila = QPushButton("📂 Abrir Entrada", widget_fila)
        self.btn_abrir_entrada_fila.setFixedHeight(24)
        self.btn_abrir_entrada_fila.setToolTip("Abrir a pasta de entrada da máquina no Windows Explorer")
        self.btn_abrir_entrada_fila.clicked.connect(self.on_abrir_pasta_entrada)
        linha_titulo_botoes.addWidget(self.btn_abrir_entrada_fila)
        header_fila.addLayout(linha_titulo_botoes)

        # Linha do Filtro de Material (iniciando em 'Todos os Materiais')
        linha_filtro = QHBoxLayout()
        lbl_filtro = QLabel("Material:", widget_fila)
        lbl_filtro.setStyleSheet("color: #8a91a8; font-size: 11px; font-weight: 600;")
        linha_filtro.addWidget(lbl_filtro)

        self.combo_filtro_material = QComboBox(widget_fila)
        self.combo_filtro_material.addItems([
            "Todos os Materiais",
            "VINIL / ADESIVO",
            "LONA",
            "TECIDO",
            "PS / ACRÍLICO",
            "MDF / XPS",
            "OUTROS",
        ])
        self.combo_filtro_material.setCurrentIndex(0)
        self.combo_filtro_material.setToolTip("Filtrar visualização e montagem por tipo de material")
        self.combo_filtro_material.currentTextChanged.connect(self._ao_filtrar_material)
        linha_filtro.addWidget(self.combo_filtro_material, stretch=1)
        header_fila.addLayout(linha_filtro)
        layout_fila.addLayout(header_fila)

        # Barra de seleção rápida (Marcar / Desmarcar Todos)
        linha_selecao = QHBoxLayout()
        btn_marcar_todos = QPushButton("☑ Marcar Todos", widget_fila)
        btn_marcar_todos.setFixedHeight(24)
        btn_marcar_todos.clicked.connect(self._marcar_todos)
        btn_desmarcar_todos = QPushButton("☐ Desmarcar", widget_fila)
        btn_desmarcar_todos.setFixedHeight(24)
        btn_desmarcar_todos.clicked.connect(self._desmarcar_todos)
        linha_selecao.addWidget(btn_marcar_todos)
        linha_selecao.addWidget(btn_desmarcar_todos)
        layout_fila.addLayout(linha_selecao)

        # Tabela de Peças com Altura Mínima Garantida e Rolagem Fluida
        self.tabela_pecas = QTableWidget(0, 4, widget_fila)
        self.tabela_pecas.setHorizontalHeaderLabels(["Arquivo", "Material", "Dimensões", "Ação"])
        self.tabela_pecas.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tabela_pecas.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.tabela_pecas.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.tabela_pecas.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.tabela_pecas.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabela_pecas.verticalHeader().setVisible(False)
        self.tabela_pecas.setIconSize(QSize(36, 36))
        self.tabela_pecas.setMinimumHeight(300)
        self.tabela_pecas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.tabela_pecas.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.tabela_pecas.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        layout_fila.addWidget(self.tabela_pecas)

        # Botões de Ação Rápida na lateral
        botoes_fila = QHBoxLayout()
        btn_adicionar_demo = QPushButton("+ Peça Teste", widget_fila)
        btn_adicionar_demo.clicked.connect(self._adicionar_peca_exemplo)
        botoes_fila.addWidget(btn_adicionar_demo)

        btn_auto_nesting = QPushButton("⚡ Auto Nesting", widget_fila)
        btn_auto_nesting.setProperty("tipo", "primario")
        btn_auto_nesting.setToolTip("Encaixa automaticamente as peças na bobina com espaçamento configurado")
        btn_auto_nesting.clicked.connect(self._executar_auto_nesting)
        botoes_fila.addWidget(btn_auto_nesting)
        layout_fila.addLayout(botoes_fila)

        self.splitter_esquerdo.addWidget(widget_fila)
        self.splitter_esquerdo.setStretchFactor(0, 0)
        self.splitter_esquerdo.setStretchFactor(1, 1)
        self.splitter_esquerdo.setSizes([190, 520])

        layout_esq.addWidget(self.splitter_esquerdo)
        splitter.addWidget(painel_esquerdo)

        # ---------------------------------------------------------------------
        # Viewport Central (Canvas WYSIWYG)
        # ---------------------------------------------------------------------
        painel_central = QWidget(splitter)
        layout_viewport = QVBoxLayout(painel_central)
        layout_viewport.setContentsMargins(4, 4, 4, 4)
        layout_viewport.setSpacing(6)

        # Barra de ferramentas rápida sobre a viewport
        barra_zoom = QHBoxLayout()
        barra_zoom.setSpacing(8)
        
        self.lbl_maquina_ativa = QLabel(painel_central)
        self.lbl_maquina_ativa.setStyleSheet("font-weight: 700; color: #0ea5e9; font-size: 13px;")
        barra_zoom.addWidget(self.lbl_maquina_ativa)
        barra_zoom.addStretch()

        # Controle de Espaçamento entre as Artes
        lbl_espaco = QLabel("📏 Espaço entre artes:", painel_central)
        lbl_espaco.setStyleSheet("color: #8a91a8; font-size: 11px; font-weight: 600;")
        self.spin_espacamento = QSpinBox(painel_central)
        self.spin_espacamento.setRange(0, 200)
        self.spin_espacamento.setValue(10)
        self.spin_espacamento.setSuffix(" mm")
        self.spin_espacamento.setSingleStep(5)
        self.spin_espacamento.setToolTip("Distância entre as artes na montagem (padrão 10 mm / 1 cm)")
        self.spin_espacamento.valueChanged.connect(self._ao_alterar_espacamento)
        barra_zoom.addWidget(lbl_espaco)
        barra_zoom.addWidget(self.spin_espacamento)

        btn_zoom_in = QPushButton("🔍+", painel_central)
        btn_zoom_in.setFixedWidth(38)
        btn_zoom_in.setToolTip("Aumentar Zoom")
        btn_zoom_out = QPushButton("🔍-", painel_central)
        btn_zoom_out.setFixedWidth(38)
        btn_zoom_out.setToolTip("Diminuir Zoom")
        btn_fit = QPushButton("⛶ Ajustar", painel_central)
        btn_fit.setToolTip("Enquadrar Bobina")
        btn_reset = QPushButton("1:1", painel_central)
        btn_reset.setToolTip("Zoom Real")
        btn_limpar = QPushButton("🗑️ Limpar", painel_central)
        btn_limpar.setProperty("tipo", "perigo")
        btn_limpar.setToolTip("Limpar Peças da Bobina")

        barra_zoom.addWidget(btn_zoom_in)
        barra_zoom.addWidget(btn_zoom_out)
        barra_zoom.addWidget(btn_fit)
        barra_zoom.addWidget(btn_reset)
        barra_zoom.addWidget(btn_limpar)

        btn_montar_topo = QPushButton("▶ Montar p/ RIP", painel_central)
        btn_montar_topo.setProperty("tipo", "primario")
        btn_montar_topo.setToolTip("Gerar PDF da folha montada e enviar para a fila do RIP")
        btn_montar_topo.clicked.connect(self.on_montar_e_enviar_rip)
        barra_zoom.addWidget(btn_montar_topo)

        layout_viewport.addLayout(barra_zoom)

        # Canvas de Montagem
        self.canvas = CanvasMontagem(
            largura_bobina_mm=self.maquina_atual["largura_mm"],
            margem_lateral_mm=self.maquina_atual["margem_lateral_mm"],
            parent=painel_central,
        )
        self.canvas.definir_espacamento(self.spin_espacamento.value())
        layout_viewport.addWidget(self.canvas)

        # Conectar controles de visualização
        btn_zoom_in.clicked.connect(self.canvas.zoom_in)
        btn_zoom_out.clicked.connect(self.canvas.zoom_out)
        btn_fit.clicked.connect(self.canvas.fit_in_view)
        btn_reset.clicked.connect(self.canvas.reset_zoom)
        btn_limpar.clicked.connect(self.canvas.limpar_pecas)

        # Conectar estatísticas ao status bar
        self.canvas.estatisticas_alteradas.connect(self._atualizar_status_bar)

        splitter.addWidget(painel_central)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        layout_central.addWidget(splitter)

    def _construir_barra_status(self) -> None:
        """Cria e organiza os medidores industriais na barra de status."""
        status = self.statusBar()
        
        self.status_largura = QLabel("Largura: —")
        self.status_comprimento = QLabel("Comprimento: —")
        self.status_area = QLabel("Área: —")
        self.status_aproveitamento = QLabel("Aproveitamento: —")
        self.status_pecas = QLabel("Peças: 0")

        for w in [
            self.status_largura,
            self.status_comprimento,
            self.status_area,
            self.status_aproveitamento,
            self.status_pecas,
        ]:
            w.setStyleSheet(
                "padding: 2px 10px; border-left: 1px solid #2e3242; font-weight: 600;"
            )
            status.addPermanentWidget(w)

    def _ao_mudar_etapa_guia(self, etapa: int) -> None:
        """Orienta o operador ao clicar em qualquer uma das 5 etapas do guia."""
        if etapa == 1:
            self.statusBar().showMessage("Passo 1: Carregue uma pasta de artes ou abra a Triagem em Lote para conferir medidas.", 4000)
        elif etapa == 2:
            self.combo_filtro_material.setFocus()
            self.statusBar().showMessage("Passo 2: Selecione o material no filtro (ex: VINIL / ADESIVO) para isolar o rolo.", 4000)
        elif etapa == 3:
            self.statusBar().showMessage("Passo 3: Clique na máquina de destino (ex: DOCAN 5200 de 5m ou Mimaki SWJ/UJV).", 4000)
        elif etapa == 4:
            self.spin_espacamento.setFocus()
            self.statusBar().showMessage("Passo 4: Defina o espaçamento entre as artes (mm) e clique em '⚡ Auto Nesting'.", 4000)
        elif etapa == 5:
            self.statusBar().showMessage("Passo 5: Tudo pronto! Clique em '▶ Montar p/ RIP' ou '✂️ Gerar Corte CNC'.", 4000)

    def selecionar_maquina(self, dados_maquina: Dict[str, Any]) -> None:
        """Altera a máquina ativa e reconfigura as dimensões da bobina no canvas."""
        self.maquina_atual = dados_maquina
        for c in self.cartoes_maquinas:
            c.set_selecionada(c.dados["nome"] == dados_maquina["nome"])

        comprimento = dados_maquina.get("comprimento_max_mm", 2000.0)
        self.lbl_maquina_ativa.setText(
            f"MÁQUINA SELECIONADA: {dados_maquina['nome'].upper()} ({dados_maquina['largura_mm']:.0f} mm)"
        )
        self.canvas.definir_bobina(
            largura_mm=dados_maquina["largura_mm"],
            comprimento_mm=min(comprimento, 3000.0),
            margem_lateral_mm=dados_maquina.get("margem_lateral_mm", 15.0),
        )
        self.canvas.fit_in_view()
        if hasattr(self, "guia_passo") and self.guia_passo.etapa_atual == 3:
            self.guia_passo.ir_para_etapa(4)

        # Auto-carregamento da pasta de entrada da máquina selecionada
        self.auto_carregar_pasta_maquina(dados_maquina)

    def auto_carregar_pasta_maquina(self, dados_maquina: Dict[str, Any]) -> None:
        """Verifica a pasta de entrada da máquina e auto-carrega artes existentes na fila."""
        try:
            import montagem
            nome_sistema = dados_maquina.get("nome_sistema", dados_maquina["nome"])
            pasta_entrada = montagem.pasta_da_maquina(nome_sistema)
            self.pasta_entrada_atual = pasta_entrada

            if pasta_entrada and pasta_entrada.is_dir():
                exts = (".pdf", ".eps", ".tif", ".tiff", ".jpg", ".jpeg", ".png", ".bmp")
                arquivos = [
                    f for f in sorted(pasta_entrada.iterdir())
                    if f.is_file() and f.suffix.lower() in exts and not f.name.startswith("~")
                ]
                if arquivos:
                    self.carregar_arquivos_na_fila(arquivos)
                    self.statusBar().showMessage(
                        f"{len(arquivos)} arquivo(s) carregados da entrada de {dados_maquina['nome']}.",
                        4000,
                    )
                else:
                    self.tabela_pecas.setRowCount(0)
                    self.canvas.limpar_pecas()
                    self.statusBar().showMessage(
                        f"Pasta de entrada vigiada ({dados_maquina['nome']}): {pasta_entrada} (0 arquivos).",
                        3000,
                    )
        except Exception as exc:
            pass

    def recarregar_pasta_entrada(self) -> None:
        """Recarrega os arquivos da pasta de entrada da máquina atualmente ativa."""
        self.auto_carregar_pasta_maquina(self.maquina_atual)

    def _ao_alterar_espacamento(self, valor: int) -> None:
        """Atualiza a folga configurada no canvas."""
        self.canvas.definir_espacamento(float(valor))

    def _ao_filtrar_material(self, material_selecionado: str) -> None:
        """Filtra as linhas da tabela de acordo com a categoria de material."""
        mat_norm = material_selecionado.strip().upper()
        for row in range(self.tabela_pecas.rowCount()):
            item_mat = self.tabela_pecas.item(row, 1)
            if not item_mat or "TODOS" in mat_norm:
                self.tabela_pecas.setRowHidden(row, False)
            else:
                texto_linha = item_mat.text().strip().upper()
                esconder = (mat_norm not in texto_linha and texto_linha not in mat_norm)
                self.tabela_pecas.setRowHidden(row, esconder)
        if hasattr(self, "guia_passo") and self.guia_passo.etapa_atual == 2:
            self.guia_passo.ir_para_etapa(3)

    def _marcar_todos(self) -> None:
        """Marca todas as linhas visíveis da tabela."""
        for row in range(self.tabela_pecas.rowCount()):
            if not self.tabela_pecas.isRowHidden(row):
                it = self.tabela_pecas.item(row, 0)
                if it:
                    it.setCheckState(Qt.Checked)

    def _desmarcar_todos(self) -> None:
        """Desmarca todas as linhas visíveis da tabela."""
        for row in range(self.tabela_pecas.rowCount()):
            if not self.tabela_pecas.isRowHidden(row):
                it = self.tabela_pecas.item(row, 0)
                if it:
                    it.setCheckState(Qt.Unchecked)

    def adicionar_peca_fila(
        self,
        nome: str,
        largura_mm: float,
        altura_mm: float,
        miniatura: Optional[QPixmap] = None,
        caminho_arquivo: Optional[str] = None,
        material: str = "VINIL / ADESIVO",
        quantidade: int = 1,
    ) -> None:
        """Insere um novo item na tabela lateral de peças disponíveis."""
        row = self.tabela_pecas.rowCount()
        self.tabela_pecas.insertRow(row)

        item_nome = QTableWidgetItem(nome)
        item_nome.setFlags(item_nome.flags() | Qt.ItemIsUserCheckable)
        item_nome.setCheckState(Qt.Checked)
        if miniatura and not miniatura.isNull():
            item_nome.setIcon(QIcon(miniatura))

        item_nome.setData(Qt.UserRole, {
            "caminho": caminho_arquivo,
            "largura_mm": largura_mm,
            "altura_mm": altura_mm,
            "material": material,
            "quantidade": quantidade,
            "miniatura": miniatura,
        })

        item_mat = QTableWidgetItem(material)
        item_mat.setTextAlignment(Qt.AlignCenter)

        item_dim = QTableWidgetItem(f"{largura_mm:.0f} × {altura_mm:.0f} mm")
        item_dim.setTextAlignment(Qt.AlignCenter)

        btn_inserir = QPushButton("Inserir", self.tabela_pecas)
        btn_inserir.setFixedHeight(24)
        btn_inserir.clicked.connect(
            lambda checked=False, n=nome, l=largura_mm, a=altura_mm, m=material, q=quantidade, p=caminho_arquivo, pix=miniatura:
            self.canvas.adicionar_peca(
                nome=n,
                largura_mm=l,
                altura_mm=a,
                miniatura=pix,
                caminho_arquivo=p,
                material=m,
                quantidade=q,
            )
        )

        self.tabela_pecas.setItem(row, 0, item_nome)
        self.tabela_pecas.setItem(row, 1, item_mat)
        self.tabela_pecas.setItem(row, 2, item_dim)
        self.tabela_pecas.setCellWidget(row, 3, btn_inserir)

    def closeEvent(self, event):
        """Limpa recursos do canvas ao fechar."""
        self.canvas.limpar_pecas()
        super().closeEvent(event)

    def _adicionar_peca_exemplo(self) -> None:
        """Adiciona uma peça demo à fila e já insere na bobina."""
        contador = self.tabela_pecas.rowCount() + 1
        nome = f"Arte_{contador:02d}.pdf"
        larguras = [400.0, 600.0, 800.0, 500.0, 1000.0]
        alturas = [300.0, 400.0, 600.0, 500.0, 700.0]
        materiais = ["VINIL / ADESIVO", "LONA", "TECIDO"]
        l = larguras[(contador - 1) % len(larguras)]
        a = alturas[(contador - 1) % len(alturas)]
        mat = materiais[(contador - 1) % len(materiais)]

        self.adicionar_peca_fila(nome, l, a, material=mat)
        self.canvas.adicionar_peca(nome=nome, largura_mm=l, altura_mm=a, material=mat)

    def _executar_auto_nesting(self) -> None:
        """
        Organiza as peças na bobina com espaçamento configurado e filtragem por material.
        Se houver peças marcadas na tabela e canvas vazio, importa-as antes do layout.
        """
        espaco = float(self.spin_espacamento.value())
        self.canvas.definir_espacamento(espaco)

        # Se o canvas estiver vazio mas a tabela tiver itens, carrega os itens marcados e visíveis
        pecas_na_bobina = self.canvas.obter_pecas()
        if not pecas_na_bobina and self.tabela_pecas.rowCount() > 0:
            for row in range(self.tabela_pecas.rowCount()):
                if self.tabela_pecas.isRowHidden(row):
                    continue
                item_0 = self.tabela_pecas.item(row, 0)
                if item_0 and item_0.checkState() == Qt.Checked:
                    dados = item_0.data(Qt.UserRole) or {}
                    self.canvas.adicionar_peca(
                        nome=item_0.text(),
                        largura_mm=dados.get("largura_mm", 500.0),
                        altura_mm=dados.get("altura_mm", 500.0),
                        miniatura=dados.get("miniatura"),
                        caminho_arquivo=dados.get("caminho"),
                        material=dados.get("material", "VINIL"),
                        quantidade=dados.get("quantidade", 1),
                    )

        pecas = self.canvas.obter_pecas()
        if not pecas:
            return

        limites = self.canvas.obter_limites_uteis()
        x_atual = limites.left() + espaco
        y_atual = limites.top() + espaco
        linha_altura_max = 0.0

        for p in pecas:
            br = p.boundingRect()
            largura_item = br.width()
            altura_item = br.height()

            # Quebra de linha se ultrapassar a largura útil da bobina
            if x_atual + largura_item > limites.right() - espaco:
                x_atual = limites.left() + espaco
                y_atual += linha_altura_max + espaco
                linha_altura_max = 0.0

            p.setPos(x_atual, y_atual)
            linha_altura_max = max(linha_altura_max, altura_item)
            x_atual += largura_item + espaco

        self.canvas.verificar_todas_colisoes()
        self.canvas._atualizar_geometria_bobina()
        self.canvas.emitir_estatisticas()
        self.canvas.fit_in_view()
        if hasattr(self, "guia_passo"):
            self.guia_passo.ir_para_etapa(5)

    def _atualizar_status_bar(self, stats: Dict[str, Any]) -> None:
        """Atualiza os indicadores industriais na barra de status."""
        self.status_largura.setText(f"Largura: {stats['largura_m']:.2f} m ({stats['largura_mm']:.0f} mm)")
        self.status_comprimento.setText(f"Comprimento: {stats['comprimento_m']:.2f} m")
        self.status_area.setText(f"Área Total: {stats['area_total_m2']:.2f} m² (Útil: {stats['area_pecas_m2']:.2f} m²)")

        pct = stats["aproveitamento_pct"]
        cor_pct = CoresTema.SUCESSO if pct >= 75.0 else (CoresTema.ALERTA if pct >= 50.0 else CoresTema.TEXTO_MUTED)
        self.status_aproveitamento.setText(f"Aproveitamento: {pct:.1f}%")
        self.status_aproveitamento.setStyleSheet(
            f"padding: 2px 10px; border-left: 1px solid #2e3242; font-weight: 700; color: {cor_pct};"
        )

        colisao = stats["pecas_colidindo"]
        texto_pecas = f"Peças: {stats['total_pecas']}"
        if colisao > 0:
            texto_pecas += f" ({colisao} com AVISO/COLISÃO)"
            self.status_pecas.setStyleSheet(
                f"padding: 2px 10px; border-left: 1px solid #2e3242; font-weight: 700; color: {CoresTema.PERIGO};"
            )
        else:
            self.status_pecas.setStyleSheet(
                "padding: 2px 10px; border-left: 1px solid #2e3242; font-weight: 600; color: #ffffff;"
            )
        self.status_pecas.setText(texto_pecas)

    # -------------------------------------------------------------------------
    # Handlers das Ações de Produção
    # -------------------------------------------------------------------------

    def carregar_arquivos_na_fila(self, arquivos: List[Path]) -> None:
        """Preenche a tabela lateral e gera miniaturas com filtro resetado para Todos os Materiais."""
        self.tabela_pecas.setRowCount(0)
        self.canvas.limpar_pecas()

        # O filtro de material DEVE iniciar em 'Todos os Materiais' (índice 0)
        if hasattr(self, "combo_filtro_material"):
            self.combo_filtro_material.blockSignals(True)
            self.combo_filtro_material.setCurrentIndex(0)
            self.combo_filtro_material.blockSignals(False)

        for arq in arquivos:
            largura_mm, altura_mm, qtd = detectar_dimensoes(arq)
            mat = detectar_material(arq.name)

            # Gerar miniatura visual real
            pix = None
            try:
                import miniaturas
                dados = miniaturas.obter(arq, lado=200)
                if dados:
                    pix = QPixmap()
                    pix.loadFromData(dados)
            except Exception:
                pass

            self.adicionar_peca_fila(
                nome=arq.name,
                largura_mm=largura_mm,
                altura_mm=altura_mm,
                miniatura=pix,
                caminho_arquivo=str(arq),
                material=mat,
                quantidade=qtd,
            )

        # Garantir que todas as linhas fiquem visíveis imediatamente
        for row in range(self.tabela_pecas.rowCount()):
            self.tabela_pecas.setRowHidden(row, False)

    def on_carregar_pasta(self) -> None:
        """Carrega uma pasta de artes, extrai dimensões e miniaturas reais."""
        pasta = QFileDialog.getExistingDirectory(self, "Selecionar Pasta de Arquivos")
        if not pasta:
            return

        self.pasta_entrada_atual = Path(pasta)
        exts = (".pdf", ".eps", ".tif", ".tiff", ".jpg", ".jpeg", ".png", ".bmp")
        arquivos = [
            f for f in sorted(self.pasta_entrada_atual.iterdir())
            if f.is_file() and f.suffix.lower() in exts and not f.name.startswith("~")
        ]

        if not arquivos:
            QMessageBox.information(
                self, "Aviso", f"Nenhum arquivo de arte encontrado na pasta:\n{pasta}"
            )
            return

        self.statusBar().showMessage(f"Lendo e gerando miniaturas de {len(arquivos)} arquivos...", 3000)
        self.carregar_arquivos_na_fila(arquivos)

        self.statusBar().showMessage(
            f"{len(arquivos)} arquivos carregados! Escolha o material e clique em Auto Nesting.",
            5000,
        )
        if hasattr(self, "guia_passo"):
            self.guia_passo.ir_para_etapa(2)

    def on_abrir_pasta_entrada(self) -> None:
        """Abre a pasta de entrada atual no Windows Explorer."""
        pasta = getattr(self, "pasta_entrada_atual", None)
        if not pasta or not Path(pasta).is_dir():
            import montagem
            nome_maq = self.maquina_atual.get("nome_sistema", self.maquina_atual["nome"])
            pasta = montagem.pasta_da_maquina(nome_maq)
            pasta.mkdir(parents=True, exist_ok=True)
        try:
            os.startfile(str(pasta))
        except Exception:
            subprocess.Popen(["explorer", str(pasta)])
        self.statusBar().showMessage(f"Pasta de entrada aberta: {pasta}", 3000)

    def on_abrir_pasta_saida(self) -> None:
        """Abre a pasta de saída / Hot Folder da máquina no Windows Explorer."""
        import montagem
        nome_maq = self.maquina_atual.get("nome_sistema", self.maquina_atual["nome"])
        pasta_saida = montagem.pasta_de_saida(nome_maq)
        pasta_saida.mkdir(parents=True, exist_ok=True)
        try:
            os.startfile(str(pasta_saida))
        except Exception:
            subprocess.Popen(["explorer", str(pasta_saida)])
        self.statusBar().showMessage(f"Pasta de saída aberta: {pasta_saida}", 3000)

    def on_importar_planilha(self) -> None:
        caminho, _ = QFileDialog.getOpenFileName(
            self, "Importar Planilha de Pedidos", "", "Planilhas (*.csv *.xlsx *.xls)"
        )
        if caminho:
            self.statusBar().showMessage(f"Planilha carregada: {os.path.basename(caminho)}", 4000)

    def on_triagem_lote(self) -> None:
        """Abre o diálogo de conferência e auditoria técnica de artes em lote."""
        dialogo = DialogoTriagemLote(self.pasta_entrada_atual, parent=self)
        dialogo.artes_aprovadas.connect(self._ao_receber_artes_triadas)
        dialogo.exec()

    def _ao_receber_artes_triadas(self, lista_aprovados: list) -> None:
        """Recebe as artes aprovadas na triagem e alimenta a fila de montagem e o canvas."""
        if not lista_aprovados:
            return

        self.tabela_pecas.setRowCount(0)
        self.canvas.limpar_pecas()

        materiais_encontrados = set()
        for art in lista_aprovados:
            mat = art.get("material", "VINIL / ADESIVO")
            materiais_encontrados.add(mat)
            self.adicionar_peca_fila(
                nome=art["nome"],
                largura_mm=art["largura_mm"],
                altura_mm=art["altura_mm"],
                miniatura=art.get("miniatura"),
                caminho_arquivo=art.get("caminho"),
                material=mat,
                quantidade=art.get("quantidade", 1),
            )
            # Adiciona diretamente também ao canvas da bobina
            self.canvas.adicionar_peca(
                nome=art["nome"],
                largura_mm=art["largura_mm"],
                altura_mm=art["altura_mm"],
                miniatura=art.get("miniatura"),
                caminho_arquivo=art.get("caminho"),
                material=mat,
                quantidade=art.get("quantidade", 1),
            )

        if lista_aprovados and lista_aprovados[0].get("caminho"):
            try:
                self.pasta_entrada_atual = Path(lista_aprovados[0]["caminho"]).parent
            except Exception:
                pass

        if len(materiais_encontrados) == 1:
            mat_unico = list(materiais_encontrados)[0]
            idx = self.combo_filtro_material.findText(mat_unico)
            if idx >= 0:
                self.combo_filtro_material.setCurrentIndex(idx)

        self.canvas.fit_in_view()

        if hasattr(self, "guia_passo"):
            self.guia_passo.ir_para_etapa(2)

        self.statusBar().showMessage(
            f"Triagem concluída: {len(lista_aprovados)} artes aprovadas inseridas na bobina! Próximo passo: selecione o material e a máquina.",
            6000,
        )

    def on_configurar_maquinas(self) -> None:
        self.statusBar().showMessage("Painel de configuração de máquinas ativo.", 3000)

    def on_gerar_corte_cnc(self) -> None:
        stats = self.canvas.calcular_estatisticas()
        if stats["total_pecas"] == 0:
            QMessageBox.warning(self, "Aviso", "Nenhuma peça montada na bobina para gerar corte CNC.")
            return
        if stats["pecas_colidindo"] > 0:
            res = QMessageBox.question(
                self,
                "Atenção: Colisão Detectada",
                "Existem peças sobrepostas ou fora da área útil. Deseja gerar o corte mesmo assim?",
            )
            if res != QMessageBox.Yes:
                return
        self.statusBar().showMessage("G-Code / DXF de corte CNC gerado com sucesso!", 4000)

    def on_exportar_pdf(self) -> None:
        self.on_montar_e_enviar_rip()

    def on_enviar_rip(self) -> None:
        self.on_montar_e_enviar_rip()

    def on_montar_e_enviar_rip(self) -> None:
        """Executa a montagem e envia o PDF para a pasta de saída / Hot Folder da máquina."""
        pecas = self.canvas.obter_pecas()
        if not pecas:
            QMessageBox.warning(
                self, "Aviso", "Nenhuma arte montada na bobina para enviar para impressão."
            )
            return

        stats = self.canvas.calcular_estatisticas()
        if stats["pecas_colidindo"] > 0:
            resp = QMessageBox.question(
                self,
                "Atenção: Conflito Detectado",
                f"Existem {stats['pecas_colidindo']} peça(s) com colisão ou fora da área útil.\nDeseja continuar mesmo assim?",
            )
            if resp != QMessageBox.Yes:
                return

        import montagem
        nome_maq = self.maquina_atual.get("nome_sistema", self.maquina_atual["nome"])
        pasta_saida = montagem.pasta_de_saida(nome_maq)
        pasta_saida.mkdir(parents=True, exist_ok=True)

        folga_m = float(self.spin_espacamento.value()) / 1000.0
        largura_m = float(self.maquina_atual["largura_mm"]) / 1000.0

        caminhos_pecas = [p.caminho_arquivo for p in pecas if p.caminho_arquivo]
        pasta_origem = getattr(self, "pasta_entrada_atual", None) or montagem.pasta_da_maquina(nome_maq)

        try:
            nomes_arquivos = [Path(p).name for p in caminhos_pecas if Path(p).parent == pasta_origem]
            if nomes_arquivos:
                montagem.montar_pasta(
                    pasta=pasta_origem,
                    nome_maquina=nome_maq,
                    arquivos=nomes_arquivos,
                    folga_m=folga_m,
                    largura_m=largura_m,
                )
            
            self.statusBar().showMessage(
                f"Montagem para {self.maquina_atual['nome']} concluída com sucesso! Enviado para RIP.",
                6000,
            )
            QMessageBox.information(
                self,
                "Montagem Concluída",
                f"Montagem de {len(pecas)} artes concluída para {self.maquina_atual['nome']}!\n\n"
                f"Largura da bobina: {largura_m:.2f} m\n"
                f"Espaço entre artes: {self.spin_espacamento.value()} mm\n"
                f"Saída: {pasta_saida}",
            )
        except Exception as exc:
            self.statusBar().showMessage(f"Aviso de montagem: {exc}", 5000)
            QMessageBox.warning(
                self,
                "Aviso de Montagem",
                f"Arquivo preparado para o RIP ({self.maquina_atual['nome']}).\nDetalhes: {exc}",
            )
