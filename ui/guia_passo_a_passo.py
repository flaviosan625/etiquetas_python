"""
ui/guia_passo_a_passo.py — Componente Visual de Fluxo e Orientação Industrial.

Guia o operador em 5 etapas claras para o chão de fábrica:
1. 📁 Entrada & Triagem (Carregar artes e validar resolução/escala)
2. 🏷️ Substrato/Material (Filtrar Vinil, Lona, Tecido ou Chapas)
3. 🖨️ Máquina & Mídia (DOCAN 5200 5m, SWJ-320, UJV-160, Flatbed ou CNC)
4. ⚡ Auto-Nesting (Espaçamento configurado e encaixe ótimo no rolo)
5. 🚀 Produção & Saída (Enviar ao RIP ou Gerar Corte CNC)
"""

from typing import List, Dict, Any, Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QLabel,
    QPushButton,
    QFrame,
)
from PySide6.QtGui import QFont, QColor
from ui.tema import CoresTema


ETAPAS_PRODUCAO = [
    {
        "id": 1,
        "titulo": "1. Triagem & Arquivos",
        "subtitulo": "Carregar e conferir artes",
        "instrucao": "Carregue a pasta de artes ou clique em 'Triagem em Lote' para conferir medidas e resolução.",
    },
    {
        "id": 2,
        "titulo": "2. Filtrar Material",
        "subtitulo": "Separar Vinil / Lona / Rígido",
        "instrucao": "Selecione o material desejado no filtro (ex: 'VINIL / ADESIVO') para nunca misturar mídias na mesma bobina.",
    },
    {
        "id": 3,
        "titulo": "3. Escolher Máquina",
        "subtitulo": "Definir largura da bobina",
        "instrucao": "Clique no cartão da máquina de destino (ex: DOCAN 5200 para rolos de 5m ou Mimaki SWJ/UJV).",
    },
    {
        "id": 4,
        "titulo": "4. Auto-Nesting",
        "subtitulo": "Encaixe e espaçamento",
        "instrucao": "Defina o espaçamento entre as artes (ex: 10 mm) e clique em '⚡ Auto Nesting' para organizar o rolo.",
    },
    {
        "id": 5,
        "titulo": "5. Enviar ao RIP / CNC",
        "subtitulo": "Produção final na fábrica",
        "instrucao": "Tudo conferido! Clique em '▶ Montar p/ RIP' para gerar o PDF montado ou '✂️ Gerar Corte CNC' para a Router.",
    },
]


class ItemEtapaWidget(QFrame):
    """Widget de uma etapa individual do fluxo."""

    clicado = Signal(int)

    def __init__(self, etapa_id: int, titulo: str, subtitulo: str, parent=None):
        super().__init__(parent)
        self.etapa_id = etapa_id
        self.titulo = titulo
        self.subtitulo = subtitulo
        self.ativa = False
        self.concluida = False

        self.setCursor(Qt.PointingHandCursor)
        self.setFrameShape(QFrame.StyledPanel)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(2)

        self.lbl_titulo = QLabel(titulo, self)
        self.lbl_titulo.setFont(QFont("Segoe UI", 9, QFont.Bold))

        self.lbl_subtitulo = QLabel(subtitulo, self)
        self.lbl_subtitulo.setFont(QFont("Segoe UI", 8))

        layout.addWidget(self.lbl_titulo)
        layout.addWidget(self.lbl_subtitulo)
        self._atualizar_estilo()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicado.emit(self.etapa_id)
        super().mousePressEvent(event)

    def definir_estado(self, ativa: bool, concluida: bool):
        self.ativa = ativa
        self.concluida = concluida
        self._atualizar_estilo()

    def _atualizar_estilo(self):
        if self.concluida:
            borda = CoresTema.SUCESSO
            fundo = "#132b21"
            cor_texto = "#a7f3d0"
            icone = "✓ "
        elif self.ativa:
            borda = CoresTema.ACENTO_PRIMARIO
            fundo = "#1e293b"
            cor_texto = "#38bdf8"
            icone = "➔ "
        else:
            borda = "#334155"
            fundo = "#1a1c23"
            cor_texto = "#94a3b8"
            icone = ""

        self.setStyleSheet(
            f"ItemEtapaWidget {{ "
            f"  border: 1.5px solid {borda}; "
            f"  background-color: {fundo}; "
            f"  border-radius: 6px; "
            f"}}"
        )
        self.lbl_titulo.setText(f"{icone}{self.titulo}")
        self.lbl_titulo.setStyleSheet(f"color: {cor_texto}; font-weight: 700;")
        self.lbl_subtitulo.setStyleSheet("color: #94a3b8; font-size: 11px;")


class GuiaPassoAPasso(QFrame):
    """Barra superior com indicação visual clara de fluxo passo a passo."""

    etapa_alterada = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.etapa_atual = 1
        self.itens_etapas: Dict[int, ItemEtapaWidget] = {}

        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet(
            "GuiaPassoAPasso { background-color: #161821; border: 1px solid #262a36; border-radius: 8px; }"
        )

        layout_principal = QVBoxLayout(self)
        layout_principal.setContentsMargins(10, 8, 10, 8)
        layout_principal.setSpacing(6)

        # 1. Linha com os blocos das 5 etapas
        linha_etapas = QHBoxLayout()
        linha_etapas.setSpacing(8)

        for e in ETAPAS_PRODUCAO:
            item = ItemEtapaWidget(e["id"], e["titulo"], e["subtitulo"], self)
            item.clicado.connect(self.ir_para_etapa)
            self.itens_etapas[e["id"]] = item
            linha_etapas.addWidget(item)

        layout_principal.addLayout(linha_etapas)

        # 2. Linha inferior com instrução prática do que fazer agora
        linha_instrucao = QHBoxLayout()
        linha_instrucao.setContentsMargins(4, 2, 4, 2)

        self.lbl_dica = QLabel(self)
        self.lbl_dica.setStyleSheet("color: #e2e8f0; font-size: 12px; font-weight: 500;")
        linha_instrucao.addWidget(self.lbl_dica, stretch=1)

        self.btn_proximo = QPushButton("Próximo Passo ➔", self)
        self.btn_proximo.setFixedHeight(26)
        self.btn_proximo.setCursor(Qt.PointingHandCursor)
        self.btn_proximo.setStyleSheet(
            f"background-color: {CoresTema.ACENTO_PRIMARIO}; color: #ffffff; "
            f"font-weight: 700; border-radius: 4px; padding: 2px 14px;"
        )
        self.btn_proximo.clicked.connect(self.avancar_etapa)
        linha_instrucao.addWidget(self.btn_proximo)

        layout_principal.addLayout(linha_instrucao)
        self.atualizar_visual()

    def ir_para_etapa(self, etapa_id: int):
        self.etapa_atual = max(1, min(5, etapa_id))
        self.atualizar_visual()
        self.etapa_alterada.emit(self.etapa_atual)

    def avancar_etapa(self):
        if self.etapa_atual < 5:
            self.ir_para_etapa(self.etapa_atual + 1)

    def retroceder_etapa(self):
        if self.etapa_atual > 1:
            self.ir_para_etapa(self.etapa_atual - 1)

    def atualizar_visual(self):
        for eid, item in self.itens_etapas.items():
            item.definir_estado(
                ativa=(eid == self.etapa_atual),
                concluida=(eid < self.etapa_atual),
            )

        info = ETAPAS_PRODUCAO[self.etapa_atual - 1]
        self.lbl_dica.setText(f"💡 <b>O que fazer agora:</b> {info['instrucao']}")

        if self.etapa_atual == 5:
            self.btn_proximo.setText("✓ Concluído")
            self.btn_proximo.setEnabled(False)
        else:
            self.btn_proximo.setText("Próximo Passo ➔")
            self.btn_proximo.setEnabled(True)
