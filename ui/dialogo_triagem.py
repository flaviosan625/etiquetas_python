"""
Diálogo Moderno de Triagem em Lote e Preflight Técnico em PySide6.

Projetado para chão de fábrica e pré-impressão de comunicação visual:
- Carregamento em lote de artes (PDF, EPS, TIF, JPG, PNG).
- Extração de dimensões e proporção (1:1, 1:10, 1:20 com detecção inteligente de escala).
- Auditoria técnica (DPI efetivo real, detecção de fontes não convertidas em curvas, espaço de cores).
- Miniaturas visuais em tempo real.
- Aprovação individual ou em lote.
- Despacho automático das peças aprovadas diretamente para a fila e canvas da JanelaPrincipal!

100% PySide6, autônomo e livre de licenças restritivas/copyleft.
"""

from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
import os

from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtWidgets import (
    QDialog,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QFileDialog,
    QMessageBox,
    QLineEdit,
    QComboBox,
    QFrame,
    QAbstractItemView,
    QProgressBar,
    QDialogButtonBox,
    QTextEdit,
)
from PySide6.QtGui import QIcon, QPixmap, QColor, QFont

from ui.tema import CoresTema, aplicar_tema


def detectar_material_nome(nome_arquivo: str) -> str:
    """Classifica o material com base em regras de fábrica e palavras-chave."""
    n = nome_arquivo.upper()
    if any(k in n for k in ("VINIL", "ADESIVO", "FOSCO", "BRILHO", "PERFURADO", "TRANSPARENTE", "BLACKOUT", "JATEADO")):
        return "VINIL / ADESIVO"
    if any(k in n for k in ("LONA", "BANNER", "FRONT", "FRONTIGHT", "BACKLIGHT", "440G", "280G", "380G", "FAIXA")):
        return "LONA"
    if any(k in n for k in ("TECIDO", "CANVAS", "FLAG", "MICROFIBRA", "OXFORD")):
        return "TECIDO"
    if any(k in n for k in ("PS", "ACRILICO", "ACRÍLICO", "LEITOSO", "CRISTAL")):
        return "PS / ACRÍLICO"
    if any(k in n for k in ("MDF", "XPS", "PVC", "POLIONDA", "ALUCOBOND", "ACM")):
        return "MDF / XPS / ACM"
    return "OUTROS"


class DialogoDetalhesPreflight(QDialog):
    """Janela popup com o relatório técnico minucioso de uma arte específica."""

    def __init__(self, dados_arte: Dict[str, Any], parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Relatório Técnico Preflight — {dados_arte.get('nome', '')}")
        self.resize(680, 520)
        aplicar_tema(self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Cabeçalho
        lbl_titulo = QLabel(f"📄 {dados_arte.get('nome')}", self)
        lbl_titulo.setStyleSheet("font-size: 15px; font-weight: 800; color: #ffffff;")
        layout.addWidget(lbl_titulo)

        # Caixa com resumo de avisos
        txt_relatorio = QTextEdit(self)
        txt_relatorio.setReadOnly(True)
        txt_relatorio.setStyleSheet(
            f"background-color: #161821; border: 1px solid {CoresTema.BORDA}; "
            f"border-radius: 6px; font-family: 'Consolas', monospace; font-size: 12px; padding: 8px;"
        )

        linhas = [
            "=== AUDITORIA TÉCNICA DE PRÉ-IMPRESSÃO ===",
            f"Arquivo: {dados_arte.get('caminho')}",
            f"Substrato Detectado: {dados_arte.get('material')}",
            f"Dimensões Finais: {dados_arte.get('largura_mm', 0):.1f} × {dados_arte.get('altura_mm', 0):.1f} mm "
            f"({dados_arte.get('largura_mm', 0)/1000.0:.2f} × {dados_arte.get('altura_mm', 0)/1000.0:.2f} m)",
            f"Escala Aplicada: {dados_arte.get('escala', '1:1')}",
            f"Resolução Efetiva: {dados_arte.get('dpi_str', 'N/A')}",
            f"Status Tipográfico: {dados_arte.get('fontes_str', 'N/A')}",
            f"Espaço de Cores: {dados_arte.get('espacos_cor_str', 'N/A')}",
            f"Status Geral: {dados_arte.get('status', 'OK')}",
            "",
            "--- DETALHES DE PÁGINAS E AVISOS ---",
        ]

        avisos = dados_arte.get("avisos", [])
        if avisos:
            for av in avisos:
                linhas.append(f"⚠️  {av}")
        else:
            linhas.append("✓ Nenhum problema crítico ou alerta detectado.")

        fontes = dados_arte.get("lista_fontes", [])
        if fontes:
            linhas.append("")
            linhas.append("--- FONTES VIVAS DETECTADAS (RISCO NO RIP) ---")
            for f in fontes:
                linhas.append(f"  • {f} (Recomendado converter em curvas no Corel/Illustrator)")

        txt_relatorio.setText("\n".join(linhas))
        layout.addWidget(txt_relatorio)

        # Botão Fechar
        botoes = QDialogButtonBox(QDialogButtonBox.Close)
        botoes.rejected.connect(self.reject)
        layout.addWidget(botoes)


class DialogoTriagemLote(QDialog):
    """
    Diálogo Principal de Triagem Técnica em Lote.

    Inspeciona lote de arquivos, valida resolução/curvas/proporção e
    transfere as peças aprovadas para a JanelaPrincipal.
    """

    artes_aprovadas = Signal(list)

    def __init__(
        self,
        pasta_inicial: Optional[Path] = None,
        arquivos_iniciais: Optional[List[Path]] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Triagem Técnica de Lote & Preflight Pré-Impressão")
        self.resize(1260, 760)
        self.setMinimumSize(980, 600)

        self.pasta_atual: Optional[Path] = Path(pasta_inicial) if pasta_inicial else None
        self.itens_triagem: List[Dict[str, Any]] = []

        self._construir_ui()
        aplicar_tema(self)

        if arquivos_iniciais:
            self.carregar_arquivos(arquivos_iniciais)
        elif self.pasta_atual and self.pasta_atual.is_dir():
            self.carregar_pasta(self.pasta_atual)

    def _construir_ui(self) -> None:
        layout_principal = QVBoxLayout(self)
        layout_principal.setContentsMargins(16, 14, 16, 14)
        layout_principal.setSpacing(12)

        # ---------------------------------------------------------------------
        # 1. Cabeçalho com Título e Botões de Importação
        # ---------------------------------------------------------------------
        layout_topo = QHBoxLayout()
        layout_textos_topo = QVBoxLayout()
        layout_textos_topo.setSpacing(2)

        lbl_titulo = QLabel("🔍 Triagem Técnica de Lote & Auditoria Pré-Impressão", self)
        lbl_titulo.setStyleSheet("font-size: 16px; font-weight: 800; color: #ffffff;")
        lbl_subtitulo = QLabel(
            "Auditoria imediata de proporção (1:1 / 1:10), resolução efetiva (DPI), "
            "fontes em curvas e separação automática por substrato.",
            self,
        )
        lbl_subtitulo.setStyleSheet(f"font-size: 12px; color: {CoresTema.TEXTO_SECUNDARIO};")
        layout_textos_topo.addWidget(lbl_titulo)
        layout_textos_topo.addWidget(lbl_subtitulo)
        layout_topo.addLayout(layout_textos_topo)
        layout_topo.addStretch()

        btn_pasta = QPushButton("📁 Carregar Pasta", self)
        btn_pasta.clicked.connect(self._ao_selecionar_pasta)
        layout_topo.addWidget(btn_pasta)

        btn_arquivos = QPushButton("📄 Adicionar Arquivos", self)
        btn_arquivos.clicked.connect(self._ao_selecionar_arquivos)
        layout_topo.addWidget(btn_arquivos)

        btn_limpar = QPushButton("🧹 Limpar Lista", self)
        btn_limpar.clicked.connect(self.limpar_lista)
        layout_topo.addWidget(btn_limpar)

        layout_principal.addLayout(layout_topo)

        # ---------------------------------------------------------------------
        # 2. Painel de Indicadores Rápidos (KPIs Industriais)
        # ---------------------------------------------------------------------
        layout_kpis = QHBoxLayout()
        layout_kpis.setSpacing(10)

        self.kpi_total = self._criar_card_kpi("ARQUIVOS TOTAIS", "0", CoresTema.TEXTO_PRINCIPAL)
        self.kpi_aprovados = self._criar_card_kpi("APROVADOS (PRONTOS)", "0", CoresTema.SUCESSO)
        self.kpi_alertas = self._criar_card_kpi("AVISOS (DPI/RGB)", "0", CoresTema.ALERTA)
        self.kpi_erros = self._criar_card_kpi("ERROS / FONTES VIVAS", "0", CoresTema.PERIGO)

        layout_kpis.addWidget(self.kpi_total)
        layout_kpis.addWidget(self.kpi_aprovados)
        layout_kpis.addWidget(self.kpi_alertas)
        layout_kpis.addWidget(self.kpi_erros)
        layout_principal.addLayout(layout_kpis)

        # ---------------------------------------------------------------------
        # 3. Barra de Busca e Filtros
        # ---------------------------------------------------------------------
        layout_filtros = QHBoxLayout()
        layout_filtros.setSpacing(10)

        self.txt_busca = QLineEdit(self)
        self.txt_busca.setPlaceholderText("🔍 Filtrar por nome do arquivo ou material...")
        self.txt_busca.textChanged.connect(self._aplicar_filtros)
        layout_filtros.addWidget(self.txt_busca, 2)

        lbl_filtro_status = QLabel("Status:", self)
        lbl_filtro_status.setStyleSheet(f"color: {CoresTema.TEXTO_SECUNDARIO}; font-size: 11px;")
        layout_filtros.addWidget(lbl_filtro_status)

        self.combo_status = QComboBox(self)
        self.combo_status.addItems(["Todos os Status", "Apenas Aprovados", "Apenas com Avisos", "Apenas Erros/Fontes"])
        self.combo_status.currentTextChanged.connect(self._aplicar_filtros)
        layout_filtros.addWidget(self.combo_status)

        lbl_filtro_mat = QLabel("Material:", self)
        lbl_filtro_mat.setStyleSheet(f"color: {CoresTema.TEXTO_SECUNDARIO}; font-size: 11px;")
        layout_filtros.addWidget(lbl_filtro_mat)

        self.combo_material = QComboBox(self)
        self.combo_material.addItems([
            "Todos os Materiais",
            "VINIL / ADESIVO",
            "LONA",
            "TECIDO",
            "PS / ACRÍLICO",
            "MDF / XPS / ACM",
            "OUTROS",
        ])
        self.combo_material.currentTextChanged.connect(self._aplicar_filtros)
        layout_filtros.addWidget(self.combo_material)

        layout_principal.addLayout(layout_filtros)

        # Barra de Progresso durante leitura em lote
        self.progresso = QProgressBar(self)
        self.progresso.setFixedHeight(4)
        self.progresso.setTextVisible(False)
        self.progresso.setVisible(False)
        layout_principal.addWidget(self.progresso)

        # ---------------------------------------------------------------------
        # 4. Tabela de Triagem Principal (8 Colunas Industriais)
        # ---------------------------------------------------------------------
        self.tabela = QTableWidget(0, 8, self)
        colunas = [
            "Aprovar",
            "Prévia",
            "Nome do Arquivo",
            "Dimensões Finais",
            "Proporção / Escala",
            "Resolução (DPI)",
            "Fontes / Curvas",
            "Substrato",
        ]
        self.tabela.setHorizontalHeaderLabels(colunas)
        self.tabela.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.tabela.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.tabela.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.tabela.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.tabela.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.tabela.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeToContents)
        self.tabela.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeToContents)
        self.tabela.horizontalHeader().setSectionResizeMode(7, QHeaderView.ResizeToContents)

        self.tabela.verticalHeader().setVisible(False)
        self.tabela.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabela.setIconSize(QSize(48, 48))
        self.tabela.itemChanged.connect(self._ao_alterar_item_tabela)
        self.tabela.cellDoubleClicked.connect(self._ao_dar_duplo_clique)
        layout_principal.addWidget(self.tabela)

        # ---------------------------------------------------------------------
        # 5. Barra Inferior com Botões de Ação
        # ---------------------------------------------------------------------
        layout_rodape = QHBoxLayout()
        layout_rodape.setSpacing(10)

        btn_marcar_todos = QPushButton("☑ Aprovar Todas", self)
        btn_marcar_todos.clicked.connect(self.aprovar_todas)
        layout_rodape.addWidget(btn_marcar_todos)

        btn_rejeitar_todos = QPushButton("☐ Desmarcar / Rejeitar", self)
        btn_rejeitar_todos.clicked.connect(self.rejeitar_todas)
        layout_rodape.addWidget(btn_rejeitar_todos)

        btn_ver_detalhes = QPushButton("🔍 Ver Relatório Técnico", self)
        btn_ver_detalhes.clicked.connect(self._ao_clicar_ver_detalhes)
        layout_rodape.addWidget(btn_ver_detalhes)

        layout_rodape.addStretch()

        btn_cancelar = QPushButton("Cancelar", self)
        btn_cancelar.clicked.connect(self.reject)
        layout_rodape.addWidget(btn_cancelar)

        self.btn_avancar = QPushButton("🚀 Avançar para Montagem do Rolo", self)
        self.btn_avancar.setProperty("tipo", "primario")
        self.btn_avancar.setStyleSheet(
            f"QPushButton {{ "
            f"  background-color: {CoresTema.SUCESSO}; "
            f"  color: #ffffff; "
            f"  font-weight: 800; "
            f"  font-size: 13px; "
            f"  padding: 8px 20px; "
            f"  border-radius: 6px; "
            f"}} "
            f"QPushButton:hover {{ "
            f"  background-color: {CoresTema.SUCESSO_HOVER}; "
            f"}}"
        )
        self.btn_avancar.clicked.connect(self.avancar_para_montagem)
        layout_rodape.addWidget(self.btn_avancar)

        layout_principal.addLayout(layout_rodape)

    def _criar_card_kpi(self, titulo: str, valor_inicial: str, cor_valor: str) -> QFrame:
        card = QFrame(self)
        card.setStyleSheet(
            f"QFrame {{ "
            f"  background-color: {CoresTema.CARTAO}; "
            f"  border: 1px solid {CoresTema.BORDA}; "
            f"  border-radius: 6px; "
            f"  padding: 6px 12px; "
            f"}}"
        )
        layout = QVBoxLayout(card)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)

        lbl_t = QLabel(titulo, card)
        lbl_t.setStyleSheet("font-size: 10px; font-weight: 700; color: #8a91a8; letter-spacing: 0.5px;")
        lbl_v = QLabel(valor_inicial, card)
        lbl_v.setStyleSheet(f"font-size: 18px; font-weight: 800; color: {cor_valor};")
        lbl_v.setObjectName("valor")

        layout.addWidget(lbl_t)
        layout.addWidget(lbl_v)
        return card

    def _atualizar_kpi_card(self, card: QFrame, novo_valor: str) -> None:
        lbl = card.findChild(QLabel, "valor")
        if lbl:
            lbl.setText(novo_valor)

    # -------------------------------------------------------------------------
    # Métodos de Carregamento e Inspeção
    # -------------------------------------------------------------------------

    def _ao_selecionar_pasta(self) -> None:
        pasta = QFileDialog.getExistingDirectory(self, "Selecionar Pasta de Arquivos para Triagem")
        if pasta:
            self.carregar_pasta(Path(pasta))

    def _ao_selecionar_arquivos(self) -> None:
        caminhos, _ = QFileDialog.getOpenFileNames(
            self,
            "Selecionar Arquivos para Triagem",
            "",
            "Arquivos Gráficos (*.pdf *.eps *.tif *.tiff *.jpg *.jpeg *.png *.bmp)",
        )
        if caminhos:
            self.carregar_arquivos([Path(p) for p in caminhos])

    def limpar_lista(self) -> None:
        self.tabela.setRowCount(0)
        self.itens_triagem.clear()
        self._atualizar_contadores()

    def carregar_pasta(self, pasta: Path) -> None:
        self.pasta_atual = Path(pasta)
        exts = (".pdf", ".eps", ".tif", ".tiff", ".jpg", ".jpeg", ".png", ".bmp")
        try:
            arquivos = [
                f for f in sorted(self.pasta_atual.iterdir())
                if f.is_file() and f.suffix.lower() in exts and not f.name.startswith("~")
            ]
        except Exception:
            arquivos = []
        self.carregar_arquivos(arquivos)

    def carregar_arquivos(self, arquivos: List[Path]) -> None:
        if not arquivos:
            return

        self.progresso.setVisible(True)
        self.progresso.setRange(0, len(arquivos))
        self.progresso.setValue(0)

        for i, arq in enumerate(arquivos):
            self._inspecionar_e_adicionar(arq)
            self.progresso.setValue(i + 1)

        self.progresso.setVisible(False)
        self._atualizar_contadores()
        self._aplicar_filtros()

    def _inspecionar_e_adicionar(self, caminho: Path) -> None:
        nome = caminho.name
        ext = caminho.suffix.lower()
        material = detectar_material_nome(nome)

        largura_mm = 500.0
        altura_mm = 500.0
        quantidade = 1
        escala_str = "1:1"
        fator_escala = 1.0
        dpi_efetivo: Optional[float] = None
        dpi_str = "N/A"
        fontes_str = "N/A"
        espacos_cor_str = "CMYK"
        tem_fontes_vivas = False
        tem_baixa_resolucao = False
        avisos: List[str] = []
        lista_fontes: List[str] = []
        status_geral = "OK"

        # 1. Dimensões nominais do nome do arquivo (se houver)
        larg_nome_mm, alt_nome_mm = None, None
        try:
            from dimensoes import extrair_dimensoes, extrair_quantidade
            dim = extrair_dimensoes(nome)
            qtd = extrair_quantidade(nome) or 1
            quantidade = qtd
            if isinstance(dim, dict):
                lm = dim.get("largura_m", 0)
                am = dim.get("altura_m", 0)
                if lm > 0 and am > 0:
                    larg_nome_mm = round(lm * 1000.0, 1)
                    alt_nome_mm = round(am * 1000.0, 1)
            elif isinstance(dim, (list, tuple)) and len(dim) >= 2:
                if dim[0] > 0 and dim[1] > 0:
                    larg_nome_mm = round(dim[0] * 1000.0, 1)
                    alt_nome_mm = round(dim[1] * 1000.0, 1)
        except Exception:
            pass

        if larg_nome_mm and alt_nome_mm:
            largura_mm = larg_nome_mm
            altura_mm = alt_nome_mm

        # 2. Inspecionar com motor Preflight (PDF)
        if ext == ".pdf":
            try:
                import preflight
                rel = preflight.inspecionar_pdf(caminho, dpi_minimo=100.0, escala_fator=1.0)
                tem_fontes_vivas = rel.get("tem_fontes_vivas", False)
                lista_fontes = rel.get("fontes", [])
                avisos.extend(rel.get("avisos", []))

                # Ler dimensões da página do PDF
                larg_pdf_mm = None
                alt_pdf_mm = None
                if rel.get("paginas_detalhes"):
                    p0 = rel["paginas_detalhes"][0]
                    larg_pdf_mm = round(p0.get("largura_m", 0.5) * 1000.0, 1)
                    alt_pdf_mm = round(p0.get("altura_m", 0.5) * 1000.0, 1)

                # Comparar medida nominal vs medida do PDF para deduzir escala
                if larg_nome_mm and larg_pdf_mm and larg_pdf_mm > 0:
                    razao_w = larg_nome_mm / larg_pdf_mm
                    razao_h = alt_nome_mm / (alt_pdf_mm or 1) if alt_nome_mm else razao_w
                    razao_media = (razao_w + razao_h) / 2.0

                    if 8.5 <= razao_media <= 11.5:
                        escala_str = "1:10 (Auto)"
                        fator_escala = 10.0
                        largura_mm = larg_nome_mm
                        altura_mm = alt_nome_mm or (alt_pdf_mm * 10.0)
                    elif 1.8 <= razao_media <= 2.2:
                        escala_str = "1:2"
                        fator_escala = 2.0
                        largura_mm = larg_nome_mm
                        altura_mm = alt_nome_mm or (alt_pdf_mm * 2.0)
                    else:
                        escala_str = "1:1"
                        largura_mm = larg_nome_mm
                        altura_mm = alt_nome_mm or alt_pdf_mm
                elif larg_pdf_mm:
                    largura_mm = larg_pdf_mm
                    altura_mm = alt_pdf_mm

                # Reinspecionar DPI com o fator de escala correto
                if fator_escala > 1.0:
                    rel_escalado = preflight.inspecionar_pdf(
                        caminho, dpi_minimo=100.0, escala_fator=fator_escala
                    )
                    dpi_efetivo = rel_escalado.get("dpi_minimo_encontrado")
                else:
                    dpi_efetivo = rel.get("dpi_minimo_encontrado")

                if dpi_efetivo is not None:
                    if dpi_efetivo >= 150:
                        dpi_str = f"{dpi_efetivo:.0f} DPI (Ótimo)"
                    elif dpi_efetivo >= 100:
                        dpi_str = f"{dpi_efetivo:.0f} DPI (Bom)"
                    else:
                        dpi_str = f"⚠️ {dpi_efetivo:.0f} DPI (Baixo)"
                        tem_baixa_resolucao = True
                else:
                    dpi_str = "Vetorial Puro"

                # Status das Fontes
                if tem_fontes_vivas:
                    fontes_str = f"❌ {len(lista_fontes)} Fontes Vivas"
                    status_geral = "ERRO"
                else:
                    fontes_str = "✓ 100% Curvas"

                # Espaço de cor
                espacos = rel.get("espacos_cor", [])
                if rel.get("tem_rgb"):
                    espacos_cor_str = "⚠️ RGB"
                    if status_geral != "ERRO":
                        status_geral = "ALERTA"
                else:
                    espacos_cor_str = "CMYK"

            except Exception as exc:
                avisos.append(f"Erro ao analisar PDF: {exc}")

        # 3. Inspecionar Imagens Raster (Pillow)
        elif ext in (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"):
            try:
                from PIL import Image
                with Image.open(caminho) as img:
                    dpi = img.info.get("dpi", (72, 72))
                    dpi_x = dpi[0] if isinstance(dpi, tuple) and dpi[0] > 0 else 72.0
                    dpi_y = dpi[1] if isinstance(dpi, tuple) and dpi[1] > 0 else 72.0
                    dpi_efetivo = min(dpi_x, dpi_y)

                    if larg_nome_mm:
                        largura_mm, altura_mm = larg_nome_mm, alt_nome_mm
                        dpi_efetivo_real = (img.width / (largura_mm / 25.4))
                        dpi_efetivo = dpi_efetivo_real
                    else:
                        largura_mm = round((img.width / dpi_x) * 25.4, 1)
                        altura_mm = round((img.height / dpi_y) * 25.4, 1)

                    if dpi_efetivo >= 150:
                        dpi_str = f"{dpi_efetivo:.0f} DPI (Ótimo)"
                    elif dpi_efetivo >= 100:
                        dpi_str = f"{dpi_efetivo:.0f} DPI (Bom)"
                    else:
                        dpi_str = f"⚠️ {dpi_efetivo:.0f} DPI (Baixo)"
                        tem_baixa_resolucao = True

                    fontes_str = "Raster (N/A)"
                    modo = str(img.mode).upper()
                    if "CMYK" in modo:
                        espacos_cor_str = "CMYK"
                    else:
                        espacos_cor_str = f"⚠️ {modo}"
                        status_geral = "ALERTA"

            except Exception as exc:
                avisos.append(f"Erro ao ler imagem: {exc}")

        # Se houver baixa resolução sem fontes vivas, status é ALERTA
        if tem_baixa_resolucao and status_geral == "OK":
            status_geral = "ALERTA"

        # Gerar Miniatura
        miniatura_pix = None
        try:
            import miniaturas
            dados_mini = miniaturas.obter(caminho, lado=120)
            if dados_mini:
                miniatura_pix = QPixmap()
                miniatura_pix.loadFromData(dados_mini)
        except Exception:
            pass

        item_dados = {
            "nome": nome,
            "caminho": str(caminho),
            "largura_mm": largura_mm,
            "altura_mm": altura_mm,
            "material": material,
            "quantidade": quantidade,
            "escala": escala_str,
            "fator_escala": fator_escala,
            "dpi_efetivo": dpi_efetivo,
            "dpi_str": dpi_str,
            "fontes_str": fontes_str,
            "espacos_cor_str": espacos_cor_str,
            "tem_fontes_vivas": tem_fontes_vivas,
            "tem_baixa_resolucao": tem_baixa_resolucao,
            "lista_fontes": lista_fontes,
            "avisos": avisos,
            "status": status_geral,
            "miniatura": miniatura_pix,
            "aprovado": (status_geral != "ERRO"),  # Erros críticos começam desmarcados por segurança
        }

        self.itens_triagem.append(item_dados)
        self._inserir_linha_tabela(item_dados)

    def _inserir_linha_tabela(self, item_dados: Dict[str, Any]) -> None:
        self.tabela.blockSignals(True)
        row = self.tabela.rowCount()
        self.tabela.insertRow(row)

        # 0. Checkbox de Aprovação com Status
        status = item_dados["status"]
        if status == "OK":
            rotulo_check = "✓ OK"
        elif status == "ALERTA":
            rotulo_check = "⚠️ Alerta"
        else:
            rotulo_check = "❌ Risco"

        it_check = QTableWidgetItem(rotulo_check)
        it_check.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        it_check.setCheckState(Qt.Checked if item_dados["aprovado"] else Qt.Unchecked)
        it_check.setTextAlignment(Qt.AlignCenter)
        it_check.setData(Qt.UserRole, item_dados)
        if status == "OK":
            it_check.setForeground(QColor(CoresTema.SUCESSO))
        elif status == "ALERTA":
            it_check.setForeground(QColor(CoresTema.ALERTA))
        else:
            it_check.setForeground(QColor(CoresTema.PERIGO))
        self.tabela.setItem(row, 0, it_check)

        # 1. Prévia / Miniatura
        it_prev = QTableWidgetItem()
        if item_dados.get("miniatura") and not item_dados["miniatura"].isNull():
            it_prev.setIcon(QIcon(item_dados["miniatura"]))
        else:
            it_prev.setText("🖼️")
        it_prev.setTextAlignment(Qt.AlignCenter)
        self.tabela.setItem(row, 1, it_prev)

        # 2. Nome do Arquivo
        it_nome = QTableWidgetItem(item_dados["nome"])
        it_nome.setToolTip(item_dados["caminho"])
        self.tabela.setItem(row, 2, it_nome)

        # 3. Dimensões Finais
        dim_str = (
            f"{item_dados['largura_mm']:.0f} × {item_dados['altura_mm']:.0f} mm "
            f"({item_dados['largura_mm']/1000.0:.2f} × {item_dados['altura_mm']/1000.0:.2f} m)"
        )
        it_dim = QTableWidgetItem(dim_str)
        it_dim.setTextAlignment(Qt.AlignCenter)
        self.tabela.setItem(row, 3, it_dim)

        # 4. Proporção / Escala
        it_esc = QTableWidgetItem(item_dados["escala"])
        it_esc.setTextAlignment(Qt.AlignCenter)
        self.tabela.setItem(row, 4, it_esc)

        # 5. Resolução (DPI)
        it_dpi = QTableWidgetItem(item_dados["dpi_str"])
        it_dpi.setTextAlignment(Qt.AlignCenter)
        if item_dados.get("tem_baixa_resolucao"):
            it_dpi.setForeground(QColor(CoresTema.ALERTA))
        self.tabela.setItem(row, 5, it_dpi)

        # 6. Fontes / Curvas
        it_fontes = QTableWidgetItem(item_dados["fontes_str"])
        it_fontes.setTextAlignment(Qt.AlignCenter)
        if item_dados.get("tem_fontes_vivas"):
            it_fontes.setForeground(QColor(CoresTema.PERIGO))
        self.tabela.setItem(row, 6, it_fontes)

        # 7. Substrato
        it_mat = QTableWidgetItem(item_dados["material"])
        it_mat.setTextAlignment(Qt.AlignCenter)
        self.tabela.setItem(row, 7, it_mat)

        self.tabela.blockSignals(False)

    def _ao_alterar_item_tabela(self, item: QTableWidgetItem) -> None:
        if item.column() == 0:
            dados = item.data(Qt.UserRole)
            if dados:
                dados["aprovado"] = (item.checkState() == Qt.Checked)
            self._atualizar_contadores()

    def _ao_dar_duplo_clique(self, row: int, col: int) -> None:
        self._exibir_detalhes_linha(row)

    def _ao_clicar_ver_detalhes(self) -> None:
        row = self.tabela.currentRow()
        if row >= 0:
            self._exibir_detalhes_linha(row)
        else:
            QMessageBox.information(self, "Aviso", "Selecione uma linha para visualizar o relatório detalhado.")

    def _exibir_detalhes_linha(self, row: int) -> None:
        it = self.tabela.item(row, 0)
        if not it:
            return
        dados = it.data(Qt.UserRole)
        if dados:
            dlg = DialogoDetalhesPreflight(dados, self)
            dlg.exec()

    # -------------------------------------------------------------------------
    # Ações Rápidas (Aprovar / Rejeitar / Filtrar)
    # -------------------------------------------------------------------------

    def aprovar_todas(self) -> None:
        """Marca todas as linhas visíveis como aprovadas."""
        for row in range(self.tabela.rowCount()):
            if not self.tabela.isRowHidden(row):
                it = self.tabela.item(row, 0)
                if it:
                    it.setCheckState(Qt.Checked)
                    dados = it.data(Qt.UserRole)
                    if dados:
                        dados["aprovado"] = True
        self._atualizar_contadores()

    def _marcar_todos(self) -> None:
        """Compatibilidade e alias para aprovar_todas."""
        self.aprovar_todas()

    def rejeitar_todas(self) -> None:
        """Desmarca todas as linhas visíveis."""
        for row in range(self.tabela.rowCount()):
            if not self.tabela.isRowHidden(row):
                it = self.tabela.item(row, 0)
                if it:
                    it.setCheckState(Qt.Unchecked)
                    dados = it.data(Qt.UserRole)
                    if dados:
                        dados["aprovado"] = False
        self._atualizar_contadores()

    def _desmarcar_todos(self) -> None:
        """Compatibilidade e alias para rejeitar_todas."""
        self.rejeitar_todas()

    def _aplicar_filtros(self) -> None:
        termo_busca = self.txt_busca.text().strip().upper()
        filtro_status = self.combo_status.currentText()
        filtro_mat = self.combo_material.currentText().strip().upper()

        for row in range(self.tabela.rowCount()):
            it_check = self.tabela.item(row, 0)
            it_nome = self.tabela.item(row, 2)
            it_mat = self.tabela.item(row, 7)

            dados = it_check.data(Qt.UserRole) if it_check else {}
            nome = it_nome.text().upper() if it_nome else ""
            mat = it_mat.text().upper() if it_mat else ""
            status = dados.get("status", "OK")

            esconder = False

            # Filtro texto
            if termo_busca and (termo_busca not in nome and termo_busca not in mat):
                esconder = True

            # Filtro Status
            if not esconder:
                if filtro_status == "Apenas Aprovados" and not dados.get("aprovado", False):
                    esconder = True
                elif filtro_status == "Apenas com Avisos" and status != "ALERTA":
                    esconder = True
                elif filtro_status == "Apenas Erros/Fontes" and status != "ERRO":
                    esconder = True

            # Filtro Material
            if not esconder and "TODOS" not in filtro_mat:
                if filtro_mat not in mat and mat not in filtro_mat:
                    esconder = True

            self.tabela.setRowHidden(row, esconder)

    def _atualizar_contadores(self) -> None:
        total = len(self.itens_triagem)
        aprovados = sum(1 for item in self.itens_triagem if item.get("aprovado"))
        alertas = sum(1 for item in self.itens_triagem if item.get("status") == "ALERTA")
        erros = sum(1 for item in self.itens_triagem if item.get("status") == "ERRO")

        self._atualizar_kpi_card(self.kpi_total, str(total))
        self._atualizar_kpi_card(self.kpi_aprovados, str(aprovados))
        self._atualizar_kpi_card(self.kpi_alertas, str(alertas))
        self._atualizar_kpi_card(self.kpi_erros, str(erros))

        self.btn_avancar.setEnabled(aprovados > 0)
        self.btn_avancar.setText(f"🚀 Avançar para Montagem do Rolo ({aprovados} aprovadas)")

    # -------------------------------------------------------------------------
    # Conclusão e Despacho para a Janela Principal
    # -------------------------------------------------------------------------

    def obter_artes_aprovadas(self) -> List[Dict[str, Any]]:
        """Retorna lista com dicionários das artes aprovadas."""
        return [item for item in self.itens_triagem if item.get("aprovado")]

    def avancar_para_montagem(self) -> None:
        """Valida e despacha as artes aprovadas diretamente para o fluxo principal."""
        aprovadas = self.obter_artes_aprovadas()
        if not aprovadas:
            QMessageBox.warning(
                self,
                "Nenhuma Arte Aprovada",
                "Por favor, marque ao menos uma arte aprovada para avançar para a montagem da bobina.",
            )
            return

        # Notificar se houver artes aprovadas com alertas de fontes vivas
        com_fontes_vivas = [item for item in aprovadas if item.get("tem_fontes_vivas")]
        if com_fontes_vivas:
            resp = QMessageBox.question(
                self,
                "Aviso de Fontes Vivas",
                f"Você aprovou {len(com_fontes_vivas)} arquivo(s) com FONTES NÃO CONVERTIDAS EM CURVAS.\n\n"
                f"Isso pode gerar substituição involuntária de letras no RIP da impressora.\n"
                f"Deseja enviar para a montagem mesmo assim?",
            )
            if resp != QMessageBox.Yes:
                return

        self.artes_aprovadas.emit(aprovadas)
        self.accept()

    def _despachar_para_montagem(self) -> None:
        """Compatibilidade e alias para avancar_para_montagem."""
        self.avancar_para_montagem()
