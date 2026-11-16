"""
ui/dialogo_triagem.py — Diálogo Moderno de Triagem e Auditoria Técnica em Lote.

Permite ao operador de pré-impressão:
- Auditar lote de arquivos antes da montagem (dimensões pedidas no nome x medidas do PDF).
- Avaliar proporção geométrica, resolução estimada (DPI) e detecção de fontes/curvas.
- Aprovar ou rejeitar itens visualmente.
- Despachar os itens aprovados diretamente para a montagem de rolo da JanelaPrincipal.
"""

from typing import List, Dict, Any, Optional
from pathlib import Path

from PySide6.QtCore import Qt, QSize, Signal
from PySide6.QtWidgets import (
    QDialog,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QLabel,
    QPushButton,
    QFileDialog,
    QMessageBox,
    QAbstractItemView,
)
from PySide6.QtGui import QIcon, QPixmap, QColor, QFont

from ui.tema import CoresTema, aplicar_tema


class DialogoTriagemLote(QDialog):
    """Janela modal para conferência e auditoria de arquivos antes de montar na bobina."""

    artes_aprovadas = Signal(list)  # Emite lista de itens aprovados

    def __init__(self, pasta_inicial: Optional[Path] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Triagem e Auditoria Técnica de Artes em Lote (Preflight)")
        self.resize(1100, 680)

        self.pasta_atual = pasta_inicial
        self.itens_triagem: List[Dict[str, Any]] = []

        self._construir_interface()
        aplicar_tema(self)

        if self.pasta_atual and Path(self.pasta_atual).is_dir():
            self.carregar_pasta(self.pasta_atual)

    def _construir_interface(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        # 1. Barra de Ações Superior
        barra_topo = QHBoxLayout()
        barra_topo.setSpacing(8)

        btn_pasta = QPushButton("📂 Escolher Outra Pasta", self)
        btn_pasta.clicked.connect(self._ao_escolher_pasta)
        barra_topo.addWidget(btn_pasta)

        btn_marcar = QPushButton("☑ Marcar Todos", self)
        btn_marcar.clicked.connect(self._marcar_todos)
        barra_topo.addWidget(btn_marcar)

        btn_desmarcar = QPushButton("☐ Desmarcar", self)
        btn_desmarcar.clicked.connect(self._desmarcar_todos)
        barra_topo.addWidget(btn_desmarcar)

        barra_topo.addStretch()

        self.lbl_pasta_info = QLabel("Pasta: nenhuma", self)
        self.lbl_pasta_info.setStyleSheet("color: #94a3b8; font-size: 11px;")
        barra_topo.addWidget(self.lbl_pasta_info)

        layout.addLayout(barra_topo)

        # 2. Tabela de Triagem
        self.tabela = QTableWidget(0, 8, self)
        self.tabela.setHorizontalHeaderLabels([
            "✓",
            "Prévia",
            "Arquivo",
            "Material",
            "Pede (Nome)",
            "Sai (Real)",
            "Proporção",
            "Status",
        ])
        self.tabela.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.tabela.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.tabela.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.tabela.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.tabela.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.tabela.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeToContents)
        self.tabela.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeToContents)
        self.tabela.horizontalHeader().setSectionResizeMode(7, QHeaderView.ResizeToContents)
        self.tabela.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabela.verticalHeader().setVisible(False)
        self.tabela.setIconSize(QSize(44, 44))
        layout.addWidget(self.tabela)

        # 3. Rodapé com Resumo e Ação de Despacho
        barra_rodape = QHBoxLayout()
        barra_rodape.setSpacing(10)

        self.lbl_resumo = QLabel("Nenhum arquivo auditado.", self)
        self.lbl_resumo.setStyleSheet("font-weight: 600; color: #f0f2f8;")
        barra_rodape.addWidget(self.lbl_resumo, stretch=1)

        btn_aprovar = QPushButton("✅ Aprovar Selecionados", self)
        btn_aprovar.clicked.connect(self._aprovar_selecionados)
        barra_rodape.addWidget(btn_aprovar)

        btn_rejeitar = QPushButton("❌ Rejeitar", self)
        btn_rejeitar.setProperty("tipo", "perigo")
        btn_rejeitar.clicked.connect(self._rejeitar_selecionados)
        barra_rodape.addWidget(btn_rejeitar)

        btn_despachar = QPushButton("🚀 Despachar Aprovados para Montagem do Rolo", self)
        btn_despachar.setProperty("tipo", "primario")
        btn_despachar.setStyleSheet(
            f"background-color: {CoresTema.SUCESSO}; color: #ffffff; "
            f"font-weight: 700; padding: 6px 18px; border-radius: 4px;"
        )
        btn_despachar.clicked.connect(self._despachar_para_montagem)
        barra_rodape.addWidget(btn_despachar)

        layout.addLayout(barra_rodape)

    def _ao_escolher_pasta(self):
        pasta = QFileDialog.getExistingDirectory(self, "Selecionar Pasta para Triagem")
        if pasta:
            self.carregar_pasta(Path(pasta))

    def carregar_pasta(self, pasta: Path):
        self.pasta_atual = Path(pasta)
        self.lbl_pasta_info.setText(f"Pasta: {self.pasta_atual.name}")
        self.tabela.setRowCount(0)
        self.itens_triagem.clear()

        exts = (".pdf", ".eps", ".tif", ".tiff", ".jpg", ".jpeg", ".png", ".bmp")
        arquivos = [
            f for f in sorted(self.pasta_atual.iterdir())
            if f.is_file() and f.suffix.lower() in exts and not f.name.startswith("~")
        ]

        if not arquivos:
            self.lbl_resumo.setText("Nenhum arquivo encontrado na pasta.")
            return

        import miniaturas
        from dimensoes import extrair_dimensoes, extrair_quantidade

        for arq in arquivos:
            nome = arq.name
            dim_nome = extrair_dimensoes(nome)
            qtd = extrair_quantidade(nome) or 1

            # Medidas pedidas
            if dim_nome and dim_nome[0] > 0 and dim_nome[1] > 0:
                pede_w = round(dim_nome[0] * 1000.0, 1)
                pede_h = round(dim_nome[1] * 1000.0, 1)
                txt_pede = f"{pede_w:.0f} × {pede_h:.0f} mm"
            else:
                pede_w, pede_h = 500.0, 500.0
                txt_pede = "Não definida"

            # Medidas reais do PDF / Arquivo
            sai_w, sai_h = pede_w, pede_h
            if arq.suffix.lower() == ".pdf":
                try:
                    import motor_pdf
                    doc = motor_pdf.abrir_pdf(arq)
                    if doc and doc.paginas:
                        b = doc.paginas[0].crop_box or doc.paginas[0].media_box
                        sai_w = round((b.largura / 72.0) * 25.4, 1)
                        sai_h = round((b.altura / 72.0) * 25.4, 1)
                except Exception:
                    pass

            txt_sai = f"{sai_w:.0f} × {sai_h:.0f} mm"

            # Proporção
            dif_pct = 0.0
            if pede_w > 0 and pede_h > 0 and sai_w > 0 and sai_h > 0:
                prop_pede = pede_w / pede_h
                prop_sai = sai_w / sai_h
                dif_pct = abs(prop_pede - prop_sai) / prop_pede * 100.0

            if dif_pct < 2.0:
                txt_prop = "✓ OK"
                cor_prop = CoresTema.SUCESSO
                status = "Aprovado"
            elif dif_pct < 6.0:
                txt_prop = f"Ajuste {dif_pct:.1f}%"
                cor_prop = CoresTema.ALERTA
                status = "Atenção"
            else:
                txt_prop = f"Divergência {dif_pct:.0f}%"
                cor_prop = CoresTema.PERIGO
                status = "Divergente"

            # Material
            from ui.janela_principal import detectar_material
            mat = detectar_material(nome)

            # Miniatura
            pix = None
            try:
                dados_mini = miniaturas.obter(arq, lado=120)
                if dados_mini:
                    pix = QPixmap()
                    pix.loadFromData(dados_mini)
            except Exception:
                pass

            item_dados = {
                "caminho": str(arq),
                "nome": nome,
                "material": mat,
                "largura_mm": sai_w,
                "altura_mm": sai_h,
                "quantidade": qtd,
                "status": status,
                "miniatura": pix,
            }
            self.itens_triagem.append(item_dados)
            self._adicionar_linha_tabela(item_dados, txt_pede, txt_sai, txt_prop, cor_prop)

        self._atualizar_resumo()

    def _adicionar_linha_tabela(self, item_dados: dict, txt_pede: str, txt_sai: str, txt_prop: str, cor_prop: str):
        row = self.tabela.rowCount()
        self.tabela.insertRow(row)

        it_check = QTableWidgetItem()
        it_check.setFlags(it_check.flags() | Qt.ItemIsUserCheckable)
        it_check.setCheckState(Qt.Checked if item_dados["status"] != "Divergente" else Qt.Unchecked)

        it_previa = QTableWidgetItem()
        if item_dados["miniatura"] and not item_dados["miniatura"].isNull():
            it_previa.setIcon(QIcon(item_dados["miniatura"]))

        it_nome = QTableWidgetItem(item_dados["nome"])
        it_mat = QTableWidgetItem(item_dados["material"])
        it_mat.setTextAlignment(Qt.AlignCenter)

        it_pede = QTableWidgetItem(txt_pede)
        it_pede.setTextAlignment(Qt.AlignCenter)

        it_sai = QTableWidgetItem(txt_sai)
        it_sai.setTextAlignment(Qt.AlignCenter)

        it_prop = QTableWidgetItem(txt_prop)
        it_prop.setTextAlignment(Qt.AlignCenter)
        it_prop.setForeground(QColor(cor_prop))

        it_status = QTableWidgetItem(item_dados["status"])
        it_status.setTextAlignment(Qt.AlignCenter)
        cor_st = CoresTema.SUCESSO if item_dados["status"] == "Aprovado" else (
            CoresTema.ALERTA if item_dados["status"] == "Atenção" else CoresTema.PERIGO
        )
        it_status.setForeground(QColor(cor_st))

        self.tabela.setItem(row, 0, it_check)
        self.tabela.setItem(row, 1, it_previa)
        self.tabela.setItem(row, 2, it_nome)
        self.tabela.setItem(row, 3, it_mat)
        self.tabela.setItem(row, 4, it_pede)
        self.tabela.setItem(row, 5, it_sai)
        self.tabela.setItem(row, 6, it_prop)
        self.tabela.setItem(row, 7, it_status)

    def _marcar_todos(self):
        for r in range(self.tabela.rowCount()):
            it = self.tabela.item(r, 0)
            if it:
                it.setCheckState(Qt.Checked)
        self._atualizar_resumo()

    def _desmarcar_todos(self):
        for r in range(self.tabela.rowCount()):
            it = self.tabela.item(r, 0)
            if it:
                it.setCheckState(Qt.Unchecked)
        self._atualizar_resumo()

    def _aprovar_selecionados(self):
        for r in range(self.tabela.rowCount()):
            if self.tabela.item(r, 0).checkState() == Qt.Checked:
                self.itens_triagem[r]["status"] = "Aprovado"
                it_st = self.tabela.item(r, 7)
                it_st.setText("Aprovado")
                it_st.setForeground(QColor(CoresTema.SUCESSO))
        self._atualizar_resumo()

    def _rejeitar_selecionados(self):
        for r in range(self.tabela.rowCount()):
            if self.tabela.item(r, 0).checkState() == Qt.Checked:
                self.itens_triagem[r]["status"] = "Rejeitado"
                it_st = self.tabela.item(r, 7)
                it_st.setText("Rejeitado")
                it_st.setForeground(QColor(CoresTema.PERIGO))
                self.tabela.item(r, 0).setCheckState(Qt.Unchecked)
        self._atualizar_resumo()

    def _atualizar_resumo(self):
        total = len(self.itens_triagem)
        marcados = sum(
            1 for r in range(self.tabela.rowCount())
            if self.tabela.item(r, 0) and self.tabela.item(r, 0).checkState() == Qt.Checked
        )
        self.lbl_resumo.setText(f"{marcados} de {total} arte(s) selecionadas para montagem.")

    def _despachar_para_montagem(self):
        aprovados = []
        for r in range(self.tabela.rowCount()):
            if self.tabela.item(r, 0) and self.tabela.item(r, 0).checkState() == Qt.Checked:
                aprovados.append(self.itens_triagem[r])

        if not aprovados:
            QMessageBox.warning(self, "Aviso", "Nenhum arquivo marcado para despachar.")
            return

        self.artes_aprovadas.emit(aprovados)
        self.accept()
