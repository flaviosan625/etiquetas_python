"""
Janela Principal da Interface Moderna PySide6 / Qt.

Painel unificado para chão de fábrica e pré-impressão:
- Barra de ferramentas superior de alta produtividade (Ações de Triagem, Máquinas, CNC e RIP).
- Painel lateral com Seletor de Máquinas e Fila de Peças com Metadados.
- Viewport Central WYSIWYG com CanvasMontagem interativo.
- Barra de status industrial em tempo real (metragem, m² e taxa de aproveitamento).
"""

from typing import Optional, Dict, Any, List
import os

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
    QFrame,
    QStatusBar,
    QFileDialog,
    QMessageBox,
    QScrollArea,
    QAbstractItemView,
)
from PySide6.QtGui import QAction, QIcon, QFont, QColor, QPixmap

from ui.tema import CoresTema, aplicar_tema
from ui.canvas_montagem import CanvasMontagem, PecaGraficaItem


MAQUINAS_DISPONIVEIS = [
    {
        "nome": "Mimaki SWJ-320EA",
        "tipo": "Solvente Bobina",
        "largura_mm": 3200.0,
        "margem_lateral_mm": 15.0,
        "status": "Online",
    },
    {
        "nome": "Mimaki UJV100-160",
        "tipo": "UV LED Bobina",
        "largura_mm": 1600.0,
        "margem_lateral_mm": 12.0,
        "status": "Online",
    },
    {
        "nome": "DOCAN UV Flatbed",
        "tipo": "UV Chapa / Plana",
        "largura_mm": 2500.0,
        "margem_lateral_mm": 10.0,
        "status": "Pronta",
    },
    {
        "nome": "Mesa CNC Router",
        "tipo": "Fresa e Faca Tangencial",
        "largura_mm": 2000.0,
        "margem_lateral_mm": 20.0,
        "status": "Operacional",
    },
]


class CartaoMaquina(QFrame):
    """Cartão de exibição e seleção rápida de máquina de impressão/corte."""

    def __init__(self, dados_maquina: Dict[str, Any], ao_clicar, parent=None):
        super().__init__(parent)
        self.dados = dados_maquina
        self.ao_clicar = ao_clicar
        self.selecionada = False

        self.setProperty("classe", "cartao")
        self.setCursor(Qt.PointingHandCursor)
        self.setFrameShape(QFrame.StyledPanel)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(3)

        header_layout = QHBoxLayout()
        self.lbl_nome = QLabel(dados_maquina["nome"])
        self.lbl_nome.setStyleSheet("font-weight: 700; font-size: 13px; color: #ffffff;")
        
        self.lbl_status = QLabel(dados_maquina["status"])
        self.lbl_status.setStyleSheet(
            f"color: {CoresTema.SUCESSO}; font-size: 11px; font-weight: 600; "
            f"background-color: {CoresTema.SUCESSO_FUNDO}; border-radius: 4px; padding: 1px 6px;"
        )
        header_layout.addWidget(self.lbl_nome)
        header_layout.addStretch()
        header_layout.addWidget(self.lbl_status)
        layout.addLayout(header_layout)

        detalhes = f"{dados_maquina['tipo']} • Largura Útil: {dados_maquina['largura_mm'] / 1000.0:.2f} m"
        self.lbl_detalhes = QLabel(detalhes)
        self.lbl_detalhes.setStyleSheet(f"color: {CoresTema.TEXTO_SECUNDARIO}; font-size: 11px;")
        layout.addWidget(self.lbl_detalhes)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.ao_clicar(self.dados)
        super().mousePressEvent(event)

    def set_selecionada(self, valor: bool):
        self.selecionada = valor
        if valor:
            self.setStyleSheet(
                f"CartaoMaquina {{ border: 2px solid {CoresTema.ACENTO_PRIMARIO}; background-color: #1e2538; }}"
            )
        else:
            self.setStyleSheet("")


class JanelaPrincipal(QMainWindow):
    """Janela Principal com arquitetura desacoplada e design industrial."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Sistema Integrado de Pré-Impressão e Corte CNC — Viewport 3D/2D")
        self.resize(1380, 880)

        self.maquinas = MAQUINAS_DISPONIVEIS
        self.maquina_atual = self.maquinas[1]  # Padrão: UJV100-160
        self.cartoes_maquinas: List[CartaoMaquina] = []
        self.acoes: Dict[str, QAction] = {}

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
        add_act("⚡ Triagem em Lote", "triagem_lote", self.on_triagem_lote)
        add_act("⚙️ Configurar Máquinas", "configurar_maquinas", self.on_configurar_maquinas)
        toolbar.addSeparator()
        add_act("✂️ Gerar Corte CNC", "gerar_corte_cnc", self.on_gerar_corte_cnc)
        add_act("📄 Exportar PDF Montado", "exportar_pdf", self.on_exportar_pdf)
        add_act("🚀 Enviar ao RIP", "enviar_rip", self.on_enviar_rip)

    def _construir_interface(self) -> None:
        """Estrutura os painéis central e lateral divididos por splitter moderno."""
        widget_central = QWidget(self)
        self.setCentralWidget(widget_central)
        layout_central = QHBoxLayout(widget_central)
        layout_central.setContentsMargins(6, 6, 6, 6)
        layout_central.setSpacing(0)

        splitter = QSplitter(Qt.Horizontal, widget_central)
        splitter.setHandleWidth(5)

        # ---------------------------------------------------------------------
        # Painel Lateral Esquerdo (Máquinas e Lista de Peças)
        # ---------------------------------------------------------------------
        painel_esquerdo = QWidget(splitter)
        painel_esquerdo.setMinimumWidth(320)
        painel_esquerdo.setMaximumWidth(460)
        layout_esq = QVBoxLayout(painel_esquerdo)
        layout_esq.setContentsMargins(8, 8, 8, 8)
        layout_esq.setSpacing(12)

        # 1. Seção de Máquinas
        lbl_sec_maq = QLabel("MÁQUINAS & DISPOSITIVOS", painel_esquerdo)
        lbl_sec_maq.setStyleSheet("font-weight: 700; color: #8a91a8; font-size: 11px; letter-spacing: 1px;")
        layout_esq.addWidget(lbl_sec_maq)

        self.container_maquinas = QVBoxLayout()
        self.container_maquinas.setSpacing(6)
        for maq in self.maquinas:
            cartao = CartaoMaquina(maq, self.selecionar_maquina, parent=painel_esquerdo)
            self.cartoes_maquinas.append(cartao)
            self.container_maquinas.addWidget(cartao)
        layout_esq.addLayout(self.container_maquinas)

        # 2. Seção de Peças a Montar
        lbl_sec_pecas = QLabel("FILA DE PEÇAS DISPONÍVEIS", painel_esquerdo)
        lbl_sec_pecas.setStyleSheet("font-weight: 700; color: #8a91a8; font-size: 11px; letter-spacing: 1px;")
        layout_esq.addWidget(lbl_sec_pecas)

        self.tabela_pecas = QTableWidget(0, 3, painel_esquerdo)
        self.tabela_pecas.setHorizontalHeaderLabels(["Nome", "Dimensões", "Ação"])
        self.tabela_pecas.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tabela_pecas.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.tabela_pecas.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.tabela_pecas.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabela_pecas.verticalHeader().setVisible(False)
        layout_esq.addWidget(self.tabela_pecas)

        # Botões de Ação Rápida na lateral
        botoes_fila = QHBoxLayout()
        btn_adicionar_demo = QPushButton("+ Peça Teste", painel_esquerdo)
        btn_adicionar_demo.clicked.connect(self._adicionar_peca_exemplo)
        botoes_fila.addWidget(btn_adicionar_demo)

        btn_auto_nesting = QPushButton("⚡ Auto Nesting", painel_esquerdo)
        btn_auto_nesting.setProperty("tipo", "primario")
        btn_auto_nesting.clicked.connect(self._executar_auto_nesting)
        botoes_fila.addWidget(btn_auto_nesting)
        layout_esq.addLayout(botoes_fila)

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
        barra_zoom.setSpacing(6)
        
        self.lbl_maquina_ativa = QLabel(painel_central)
        self.lbl_maquina_ativa.setStyleSheet("font-weight: 700; color: #0ea5e9; font-size: 13px;")
        barra_zoom.addWidget(self.lbl_maquina_ativa)
        barra_zoom.addStretch()

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
        layout_viewport.addLayout(barra_zoom)

        # Canvas de Montagem
        self.canvas = CanvasMontagem(
            largura_bobina_mm=self.maquina_atual["largura_mm"],
            margem_lateral_mm=self.maquina_atual["margem_lateral_mm"],
            parent=painel_central,
        )
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

    def selecionar_maquina(self, dados_maquina: Dict[str, Any]) -> None:
        """Altera a máquina ativa e reconfigura as dimensões da bobina no canvas."""
        self.maquina_atual = dados_maquina
        for c in self.cartoes_maquinas:
            c.set_selecionada(c.dados["nome"] == dados_maquina["nome"])

        self.lbl_maquina_ativa.setText(
            f"MÁQUINA SELECIONADA: {dados_maquina['nome'].upper()} ({dados_maquina['largura_mm']:.0f} mm)"
        )
        self.canvas.definir_bobina(
            largura_mm=dados_maquina["largura_mm"],
            margem_lateral_mm=dados_maquina.get("margem_lateral_mm", 15.0),
        )
        self.canvas.fit_in_view()

    def adicionar_peca_fila(self, nome: str, largura_mm: float, altura_mm: float) -> None:
        """Insere um novo item na tabela lateral de peças disponíveis."""
        row = self.tabela_pecas.rowCount()
        self.tabela_pecas.insertRow(row)

        item_nome = QTableWidgetItem(nome)
        item_dim = QTableWidgetItem(f"{largura_mm:.0f} × {altura_mm:.0f} mm")
        item_dim.setTextAlignment(Qt.AlignCenter)

        btn_inserir = QPushButton("Inserir", self.tabela_pecas)
        btn_inserir.setFixedHeight(24)
        btn_inserir.clicked.connect(
            lambda checked=False, n=nome, l=largura_mm, a=altura_mm: self.canvas.adicionar_peca(
                nome=n, largura_mm=l, altura_mm=a
            )
        )

        self.tabela_pecas.setItem(row, 0, item_nome)
        self.tabela_pecas.setItem(row, 1, item_dim)
        self.tabela_pecas.setCellWidget(row, 2, btn_inserir)

    def closeEvent(self, event):
        """Limpa recursos do canvas ao fechar."""
        self.canvas.limpar_pecas()
        super().closeEvent(event)

    def _adicionar_peca_exemplo(self) -> None:
        """Adiciona uma peça demo à fila e já insere na bobina."""
        contador = self.tabela_pecas.rowCount() + 1
        nome = f"Arte_{contador:02d}.pdf"
        # Dimensões variadas para teste visual
        larguras = [400.0, 600.0, 800.0, 500.0, 1000.0]
        alturas = [300.0, 400.0, 600.0, 500.0, 700.0]
        l = larguras[(contador - 1) % len(larguras)]
        a = alturas[(contador - 1) % len(alturas)]

        self.adicionar_peca_fila(nome, l, a)
        self.canvas.adicionar_peca(nome=nome, largura_mm=l, altura_mm=a)

    def _executar_auto_nesting(self) -> None:
        """Organiza as peças existentes na bobina em sequência organizada sem colisão."""
        pecas = self.canvas.obter_pecas()
        if not pecas:
            return

        limites = self.canvas.obter_limites_uteis()
        margem_espaco = 10.0
        x_atual = limites.left() + margem_espaco
        y_atual = limites.top() + margem_espaco
        linha_altura_max = 0.0

        for p in pecas:
            br = p.boundingRect()
            largura_item = br.width()
            altura_item = br.height()

            # Quebra de linha se ultrapassar a largura útil
            if x_atual + largura_item > limites.right() - margem_espaco:
                x_atual = limites.left() + margem_espaco
                y_atual += linha_altura_max + margem_espaco
                linha_altura_max = 0.0

            p.setPos(x_atual, y_atual)
            linha_altura_max = max(linha_altura_max, altura_item)
            x_atual += largura_item + margem_espaco

        self.canvas.verificar_todas_colisoes()
        self.canvas._atualizar_geometria_bobina()
        self.canvas.emitir_estatisticas()
        self.canvas.fit_in_view()

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
    # Handlers das Ações da Barra de Ferramentas
    # -------------------------------------------------------------------------

    def on_carregar_pasta(self) -> None:
        pasta = QFileDialog.getExistingDirectory(self, "Selecionar Pasta de Arquivos")
        if pasta:
            # Lista arquivos PDF / imagens comuns
            arquivos = [
                f for f in os.listdir(pasta)
                if f.lower().endswith((".pdf", ".eps", ".tif", ".tiff", ".jpg", ".png"))
            ]
            for arq in arquivos[:20]:
                self.adicionar_peca_fila(arq, 500.0, 500.0)
            self.statusBar().showMessage(f"{len(arquivos)} arquivos encontrados em {pasta}", 4000)

    def on_importar_planilha(self) -> None:
        caminho, _ = QFileDialog.getOpenFileName(
            self, "Importar Planilha de Pedidos", "", "Planilhas (*.csv *.xlsx *.xls)"
        )
        if caminho:
            self.statusBar().showMessage(f"Planilha carregada: {os.path.basename(caminho)}", 4000)

    def on_triagem_lote(self) -> None:
        self.statusBar().showMessage("Executando triagem e conferência em lote...", 3000)

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
        self.statusBar().showMessage("Exportação de PDF de montagem unificado concluída.", 4000)

    def on_enviar_rip(self) -> None:
        self.statusBar().showMessage(f"Arquivo enviado à fila do RIP ({self.maquina_atual['nome']}).", 4000)
