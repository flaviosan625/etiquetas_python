"""
Componente Visual de Etapas de Trabalho (Workflow Stepper / Guia Passo a Passo).

Orientação visual de ponta a ponta para operadores de impressão em grandes formatos
e operadores de corte CNC:
  Etapa 1: 📁 Entrada & Triagem (Carregar artes e validar resolução/escala/curvas)
  Etapa 2: 🏷️ Substrato/Material (Filtrar Vinil, Lona, Tecido ou Chapa)
  Etapa 3: 🖨️ Máquina & Mídia (DOCAN 5200 5m, SWJ-320, UJV-160, Flatbed ou CNC)
  Etapa 4: ⚡ Encaixe / Auto-Nesting (Organizar com espaçamento configurado)
  Etapa 5: 🚀 Produção (Enviar ao RIP da máquina ou Gerar Corte CNC)

Inclui painel dinâmico 'O que fazer agora?' com instruções contextuais e botões de ação rápida.
100% PySide6 e livre de bibliotecas restritivas/copyleft.
"""

from typing import List, Dict, Any, Optional
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtWidgets import (
    QWidget,
    QFrame,
    QHBoxLayout,
    QVBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
)
from PySide6.QtGui import QFont, QCursor, QColor

from ui.tema import CoresTema


ETAPAS_PADRAO: List[Dict[str, Any]] = [
    {
        "id": 1,
        "titulo": "1. Entrada & Triagem",
        "subtitulo": "Carregar artes e validar resolução/escala",
        "icone": "📁",
        "instrucao": (
            "Carregue a pasta de arquivos e execute a **Triagem em Lote** para auditar "
            "resolução efetiva (DPI), conferir escala (1:1 ou 1:10) e garantir fontes 100% em curvas."
        ),
        "acao_texto": "Executar Triagem em Lote",
        "acao_chave": "triagem",
    },
    {
        "id": 2,
        "titulo": "2. Substrato / Material",
        "subtitulo": "Filtrar Vinil, Lona, Tecido ou Chapa",
        "icone": "🏷️",
        "instrucao": (
            "Selecione o substrato no seletor de material (ex: Vinil, Lona 440g, Tecido Canvas ou Chapas). "
            "A bobina agrupa exclusivamente materiais compatíveis para evitar perda de substrato."
        ),
        "acao_texto": "Filtrar Substrato",
        "acao_chave": "material",
    },
    {
        "id": 3,
        "titulo": "3. Máquina & Mídia",
        "subtitulo": "DOCAN 5200 5m, SWJ-320, UJV-160, Flatbed ou CNC",
        "icone": "🖨️",
        "instrucao": (
            "Selecione a impressora ou centro de usinagem CNC correspondente. "
            "A largura útil da bobina e as margens de segurança serão ajustadas automaticamente."
        ),
        "acao_texto": "Confirmar Máquina",
        "acao_chave": "maquina",
    },
    {
        "id": 4,
        "titulo": "4. Encaixe / Auto-Nesting",
        "subtitulo": "Organizar com espaçamento configurado",
        "icone": "⚡",
        "instrucao": (
            "Defina o espaçamento entre as artes (padrão 10 mm / 1 cm) e clique em **Auto Nesting**. "
            "O sistema organiza as peças aproveitando ao máximo a largura da mídia sem sobreposição."
        ),
        "acao_texto": "Executar Auto-Nesting",
        "acao_chave": "nesting",
    },
    {
        "id": 5,
        "titulo": "5. Produção & Saída",
        "subtitulo": "Enviar ao RIP da máquina ou Gerar Corte CNC",
        "icone": "🚀",
        "instrucao": (
            "Tudo inspecionado e montado! Clique em **Montar p/ RIP** para gerar o PDF na Hot Folder "
            "da máquina ou em **Gerar Corte CNC** para exportar o arquivo para a fresa/faca."
        ),
        "acao_texto": "Montar e Enviar p/ RIP",
        "acao_chave": "producao",
    },
]


class CartaoEtapa(QFrame):
    """Cartão individual de uma etapa do workflow."""

    clicado = Signal(int)

    def __init__(
        self,
        indice: int,
        dados_etapa: Dict[str, Any],
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.indice = indice
        self.dados = dados_etapa
        self.ativa = False
        self.concluida = False

        self.setCursor(QCursor(Qt.PointingHandCursor))
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._construir_ui()
        self._atualizar_estilo()

    def _construir_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(10)

        # Círculo com o número / check
        self.lbl_circulo = QLabel(str(self.dados["id"]), self)
        self.lbl_circulo.setFixedSize(30, 30)
        self.lbl_circulo.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.lbl_circulo)

        # Informações de texto
        layout_textos = QVBoxLayout()
        layout_textos.setContentsMargins(0, 0, 0, 0)
        layout_textos.setSpacing(2)

        self.lbl_titulo = QLabel(self.dados["titulo"], self)
        self.lbl_subtitulo = QLabel(self.dados["subtitulo"], self)
        self.lbl_subtitulo.setWordWrap(False)

        layout_textos.addWidget(self.lbl_titulo)
        layout_textos.addWidget(self.lbl_subtitulo)
        layout.addLayout(layout_textos)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicado.emit(self.indice)
        super().mousePressEvent(event)

    def definir_estado(self, ativa: bool, concluida: bool) -> None:
        self.ativa = ativa
        self.concluida = concluida
        self._atualizar_estilo()

    def _atualizar_estilo(self) -> None:
        if self.concluida and not self.ativa:
            # Estado CONCLUÍDA: Verde Esmeralda com checkmark
            self.lbl_circulo.setText("✓")
            self.lbl_circulo.setStyleSheet(
                f"background-color: {CoresTema.SUCESSO}; color: #ffffff; "
                f"border-radius: 15px; font-weight: 800; font-size: 13px;"
            )
            self.lbl_titulo.setStyleSheet(
                f"color: {CoresTema.TEXTO_PRINCIPAL}; font-weight: 700; font-size: 12px;"
            )
            self.lbl_subtitulo.setStyleSheet(
                f"color: {CoresTema.TEXTO_SECUNDARIO}; font-size: 11px;"
            )
            self.setStyleSheet(
                f"CartaoEtapa {{ "
                f"  background-color: #15221e; "
                f"  border: 1px solid #10b98166; "
                f"  border-radius: 8px; "
                f"}} "
                f"CartaoEtapa:hover {{ "
                f"  background-color: #1a2f29; "
                f"  border: 1px solid {CoresTema.SUCESSO}; "
                f"}}"
            )

        elif self.ativa:
            # Estado ATIVA: Destaque Ciano Elétrico / Azul Alto Contraste
            self.lbl_circulo.setText(str(self.dados["id"]))
            self.lbl_circulo.setStyleSheet(
                f"background-color: {CoresTema.ACENTO_PRIMARIO}; color: #ffffff; "
                f"border-radius: 15px; font-weight: 800; font-size: 13px;"
            )
            self.lbl_titulo.setStyleSheet(
                f"color: #ffffff; font-weight: 800; font-size: 12px;"
            )
            self.lbl_subtitulo.setStyleSheet(
                f"color: #bae6fd; font-size: 11px; font-weight: 500;"
            )
            self.setStyleSheet(
                f"CartaoEtapa {{ "
                f"  background-color: #0c263d; "
                f"  border: 2px solid {CoresTema.ACENTO_PRIMARIO}; "
                f"  border-radius: 8px; "
                f"}}"
            )

        else:
            # Estado PENDENTE: Neutro / Cartão Suave
            self.lbl_circulo.setText(str(self.dados["id"]))
            self.lbl_circulo.setStyleSheet(
                f"background-color: #272a36; color: {CoresTema.TEXTO_SECUNDARIO}; "
                f"border-radius: 15px; font-weight: 700; font-size: 12px; "
                f"border: 1px solid {CoresTema.BORDA};"
            )
            self.lbl_titulo.setStyleSheet(
                f"color: {CoresTema.TEXTO_MUTED}; font-weight: 600; font-size: 12px;"
            )
            self.lbl_subtitulo.setStyleSheet(
                f"color: #555b70; font-size: 11px;"
            )
            self.setStyleSheet(
                f"CartaoEtapa {{ "
                f"  background-color: #181a22; "
                f"  border: 1px solid {CoresTema.BORDA}; "
                f"  border-radius: 8px; "
                f"}} "
                f"CartaoEtapa:hover {{ "
                f"  background-color: #202330; "
                f"  border-color: #3e445a; "
                f"}}"
            )


class WorkflowStepper(QFrame):
    """
    Barra Superior de Fluxo de Trabalho (Stepper / Guia Industrial Passo a Passo).

    Apresenta 5 etapas visuais e painel dinâmico de orientação ao operador com
    botão de ação direta para destravar o processo de chão de fábrica.
    """

    etapa_alterada = Signal(int)
    acao_etapa_disparada = Signal(int)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.etapas_dados = ETAPAS_PADRAO
        self.etapa_atual = 0  # 0 a 4
        self.etapas_concluidas = [False] * len(self.etapas_dados)
        self.cartoes: List[CartaoEtapa] = []

        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet(
            f"WorkflowStepper {{ "
            f"  background-color: {CoresTema.SUPERFICIE}; "
            f"  border-bottom: 1px solid {CoresTema.BORDA}; "
            f"}}"
        )

        self._construir_ui()
        self.definir_etapa_atual(0)

    def _construir_ui(self) -> None:
        layout_principal = QVBoxLayout(self)
        layout_principal.setContentsMargins(12, 8, 12, 8)
        layout_principal.setSpacing(8)

        # ---------------------------------------------------------------------
        # Linha Superior: As 5 Etapas em Linha
        # ---------------------------------------------------------------------
        layout_cards = QHBoxLayout()
        layout_cards.setContentsMargins(0, 0, 0, 0)
        layout_cards.setSpacing(8)

        for i, dados in enumerate(self.etapas_dados):
            cartao = CartaoEtapa(i, dados, self)
            cartao.clicado.connect(self.definir_etapa_atual)
            self.cartoes.append(cartao)
            layout_cards.addWidget(cartao)

            # Separador visual entre etapas (seta sutil)
            if i < len(self.etapas_dados) - 1:
                lbl_seta = QLabel("›", self)
                lbl_seta.setStyleSheet(
                    f"color: {CoresTema.BORDA}; font-size: 18px; font-weight: 300;"
                )
                layout_cards.addWidget(lbl_seta)

        layout_principal.addLayout(layout_cards)

        # ---------------------------------------------------------------------
        # Linha Inferior: Painel de Orientação ao Operador ("O que fazer agora?")
        # ---------------------------------------------------------------------
        self.painel_orientacao = QFrame(self)
        self.painel_orientacao.setStyleSheet(
            f"QFrame {{ "
            f"  background-color: #161821; "
            f"  border: 1px solid #272a38; "
            f"  border-radius: 6px; "
            f"}}"
        )
        layout_guia = QHBoxLayout(self.painel_orientacao)
        layout_guia.setContentsMargins(12, 6, 12, 6)
        layout_guia.setSpacing(12)

        self.lbl_badge_etapa = QLabel("PASSO 1", self.painel_orientacao)
        self.lbl_badge_etapa.setStyleSheet(
            f"background-color: {CoresTema.ACENTO_PRIMARIO}; color: #ffffff; "
            f"font-size: 11px; font-weight: 800; border-radius: 4px; padding: 2px 8px;"
        )
        layout_guia.addWidget(self.lbl_badge_etapa)

        self.lbl_instrucao = QLabel("", self.painel_orientacao)
        self.lbl_instrucao.setStyleSheet(
            f"color: {CoresTema.TEXTO_PRINCIPAL}; font-size: 12px;"
        )
        self.lbl_instrucao.setTextFormat(Qt.MarkdownText)
        self.lbl_instrucao.setWordWrap(True)
        layout_guia.addWidget(self.lbl_instrucao, 1)

        # Botão de Ação Imediata da Etapa Atual
        self.btn_acao_etapa = QPushButton("Executar Ação", self.painel_orientacao)
        self.btn_acao_etapa.setStyleSheet(
            f"QPushButton {{ "
            f"  background-color: {CoresTema.ACENTO_PRIMARIO}; "
            f"  color: #ffffff; "
            f"  font-weight: 700; "
            f"  padding: 5px 14px; "
            f"  border-radius: 5px; "
            f"  font-size: 12px; "
            f"}} "
            f"QPushButton:hover {{ "
            f"  background-color: {CoresTema.ACENTO_HOVER}; "
            f"}}"
        )
        self.btn_acao_etapa.clicked.connect(self._ao_clicar_acao_etapa)
        layout_guia.addWidget(self.btn_acao_etapa)

        # Botão de Avançar Etapa
        self.btn_avancar = QPushButton("Próximo Passo ❯", self.painel_orientacao)
        self.btn_avancar.setStyleSheet(
            f"QPushButton {{ "
            f"  background-color: #272a38; "
            f"  color: {CoresTema.TEXTO_PRINCIPAL}; "
            f"  font-weight: 600; "
            f"  padding: 5px 12px; "
            f"  border-radius: 5px; "
            f"  font-size: 11px; "
            f"  border: 1px solid {CoresTema.BORDA}; "
            f"}} "
            f"QPushButton:hover {{ "
            f"  background-color: #323647; "
            f"  color: #ffffff; "
            f"}}"
        )
        self.btn_avancar.clicked.connect(self.avancar_etapa)
        layout_guia.addWidget(self.btn_avancar)

        layout_principal.addWidget(self.painel_orientacao)

    def definir_etapa_atual(self, indice: int) -> None:
        """Altera a etapa ativa e sincroniza os cartões e as instruções."""
        if not (0 <= indice < len(self.etapas_dados)):
            return

        self.etapa_atual = indice
        for i, c in enumerate(self.cartoes):
            c.definir_estado(
                ativa=(i == self.etapa_atual),
                concluida=self.etapas_concluidas[i],
            )

        dados = self.etapas_dados[self.etapa_atual]
        self.lbl_badge_etapa.setText(f"PASSO {dados['id']} DE 5")
        self.lbl_instrucao.setText(dados["instrucao"])
        self.btn_acao_etapa.setText(f"{dados['icone']} {dados['acao_texto']}")

        # Ajusta visibilidade do botão avançar
        self.btn_avancar.setVisible(self.etapa_atual < len(self.etapas_dados) - 1)

        self.etapa_alterada.emit(self.etapa_atual)

    def marcar_etapa_concluida(self, indice: int, concluida: bool = True) -> None:
        """Marca uma etapa como concluída (ex: triagem finalizada)."""
        if 0 <= indice < len(self.etapas_concluidas):
            self.etapas_concluidas[indice] = concluida
            self.cartoes[indice].definir_estado(
                ativa=(indice == self.etapa_atual),
                concluida=concluida,
            )

    def avancar_etapa(self) -> None:
        """Avança para a próxima etapa do fluxo."""
        if self.etapa_atual < len(self.etapas_dados) - 1:
            self.marcar_etapa_concluida(self.etapa_atual, True)
            self.definir_etapa_atual(self.etapa_atual + 1)

    def voltar_etapa(self) -> None:
        """Retorna para a etapa anterior."""
        if self.etapa_atual > 0:
            self.definir_etapa_atual(self.etapa_atual - 1)

    def _ao_clicar_acao_etapa(self) -> None:
        """Dispara a ação rápida associada à etapa corrente."""
        self.acao_etapa_disparada.emit(self.etapa_atual)

    def obter_etapa_atual(self) -> int:
        """Retorna o índice da etapa corrente (0 a 4)."""
        return self.etapa_atual
