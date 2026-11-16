"""
Sistema de Tema Escuro Industrial para PySide6 / Qt.

Paleta de alto contraste e folha de estilos QSS para ambiente de chão de fábrica
e estúdio de pré-impressão/corte CNC.
"""

from typing import Union
from PySide6.QtWidgets import QApplication, QWidget
from PySide6.QtGui import QColor, QFont


class CoresTema:
    """Paleta de cores industrial de alto contraste."""
    FUNDO = "#121318"
    SUPERFICIE = "#1a1c23"
    CARTAO = "#222530"
    CARTAO_HOVER = "#2a2e3d"
    BORDA = "#2e3242"
    BORDA_FOCO = "#0ea5e9"
    BORDA_SUAVE = "#252836"
    
    TEXTO_PRINCIPAL = "#f0f2f8"
    TEXTO_SECUNDARIO = "#8a91a8"
    TEXTO_MUTED = "#646b82"
    TEXTO_INVERSO = "#0b0c10"
    
    ACENTO_PRIMARIO = "#0ea5e9"  # Ciano elétrico / azul moderno
    ACENTO_SECUNDARIO = "#0078d4"
    ACENTO_HOVER = "#38bdf8"
    ACENTO_PRESS = "#0284c7"
    
    SUCESSO = "#10b981"
    SUCESSO_FUNDO = "#064e3b"
    SUCESSO_HOVER = "#34d399"
    
    ALERTA = "#f59e0b"
    ALERTA_FUNDO = "#78350f"
    ALERTA_HOVER = "#fbbf24"
    
    PERIGO = "#ef4444"
    PERIGO_FUNDO = "#7f1d1d"
    PERIGO_HOVER = "#f87171"
    
    # Viewport e Mídia
    CANVAS_FUNDO = "#0d0e12"
    MIDIA_PAPEL = "#f8fafc"
    MIDIA_BORDA = "#94a3b8"
    MARGEM_CORTE = "#ef4444"
    GRADE_LINHA = "#1e222e"


def obter_qss() -> str:
    """Retorna a folha de estilos QSS completa para o tema escuro industrial."""
    c = CoresTema
    return f"""
    /* Janela e Superfície Base */
    QMainWindow, QDialog, QWidget {{
        background-color: {c.FUNDO};
        color: {c.TEXTO_PRINCIPAL};
        font-family: 'Segoe UI', 'SF Pro Display', -apple-system, sans-serif;
        font-size: 13px;
    }}

    /* Barra de Ferramentas */
    QToolBar {{
        background-color: {c.SUPERFICIE};
        border-bottom: 1px solid {c.BORDA};
        spacing: 6px;
        padding: 5px 10px;
    }}
    QToolBar::separator {{
        width: 1px;
        background-color: {c.BORDA};
        margin: 4px 6px;
    }}
    QToolButton {{
        background-color: {c.CARTAO};
        color: {c.TEXTO_PRINCIPAL};
        border: 1px solid {c.BORDA};
        border-radius: 6px;
        padding: 6px 12px;
        font-weight: 600;
        min-height: 20px;
    }}
    QToolButton:hover {{
        background-color: {c.CARTAO_HOVER};
        border-color: {c.ACENTO_PRIMARIO};
        color: #ffffff;
    }}
    QToolButton:pressed {{
        background-color: {c.ACENTO_PRESS};
        border-color: {c.ACENTO_PRIMARIO};
    }}

    /* Botões Padrão */
    QPushButton {{
        background-color: {c.CARTAO};
        color: {c.TEXTO_PRINCIPAL};
        border: 1px solid {c.BORDA};
        border-radius: 6px;
        padding: 7px 16px;
        font-weight: 600;
        min-height: 20px;
    }}
    QPushButton:hover {{
        background-color: {c.CARTAO_HOVER};
        border-color: {c.ACENTO_PRIMARIO};
        color: #ffffff;
    }}
    QPushButton:pressed {{
        background-color: {c.ACENTO_PRESS};
        border-color: {c.ACENTO_PRIMARIO};
        color: #ffffff;
    }}
    QPushButton:disabled {{
        background-color: {c.SUPERFICIE};
        color: {c.TEXTO_MUTED};
        border-color: {c.BORDA_SUAVE};
    }}

    /* Variações de Botões */
    QPushButton[tipo="primario"] {{
        background-color: {c.ACENTO_PRIMARIO};
        color: {c.TEXTO_INVERSO};
        border: 1px solid {c.ACENTO_HOVER};
        font-weight: 700;
    }}
    QPushButton[tipo="primario"]:hover {{
        background-color: {c.ACENTO_HOVER};
        border-color: #ffffff;
    }}
    QPushButton[tipo="primario"]:pressed {{
        background-color: {c.ACENTO_PRESS};
    }}

    QPushButton[tipo="sucesso"] {{
        background-color: {c.SUCESSO};
        color: {c.TEXTO_INVERSO};
        border: 1px solid {c.SUCESSO_HOVER};
        font-weight: 700;
    }}
    QPushButton[tipo="sucesso"]:hover {{
        background-color: {c.SUCESSO_HOVER};
    }}

    QPushButton[tipo="perigo"] {{
        background-color: {c.PERIGO};
        color: #ffffff;
        border: 1px solid {c.PERIGO_HOVER};
        font-weight: 700;
    }}
    QPushButton[tipo="perigo"]:hover {{
        background-color: {c.PERIGO_HOVER};
    }}

    /* Entradas de Texto, Números e Combos */
    QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
        background-color: {c.SUPERFICIE};
        color: {c.TEXTO_PRINCIPAL};
        border: 1px solid {c.BORDA};
        border-radius: 6px;
        padding: 6px 10px;
        selection-background-color: {c.ACENTO_PRIMARIO};
        selection-color: {c.TEXTO_INVERSO};
    }}
    QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
        border: 1px solid {c.BORDA_FOCO};
        background-color: #1c202b;
    }}
    QComboBox::drop-down {{
        subcontrol-origin: padding;
        subcontrol-position: top right;
        width: 24px;
        border-left: 1px solid {c.BORDA};
    }}
    QComboBox QAbstractItemView {{
        background-color: {c.CARTAO};
        color: {c.TEXTO_PRINCIPAL};
        border: 1px solid {c.BORDA};
        selection-background-color: {c.ACENTO_PRIMARIO};
        selection-color: {c.TEXTO_INVERSO};
    }}

    /* Tabelas e Árvores */
    QTableWidget, QTableView, QTreeWidget, QTreeView, QListWidget, QListView {{
        background-color: {c.SUPERFICIE};
        color: {c.TEXTO_PRINCIPAL};
        border: 1px solid {c.BORDA};
        border-radius: 6px;
        gridline-color: {c.BORDA_SUAVE};
        selection-background-color: #1e3a5f;
        selection-color: #ffffff;
    }}
    QHeaderView::section {{
        background-color: {c.CARTAO};
        color: {c.TEXTO_SECUNDARIO};
        border: none;
        border-right: 1px solid {c.BORDA};
        border-bottom: 1px solid {c.BORDA};
        padding: 6px 8px;
        font-weight: 600;
        font-size: 12px;
    }}
    QTableWidget::item:hover, QTableView::item:hover {{
        background-color: {c.CARTAO};
    }}

    /* Splitter */
    QSplitter::handle {{
        background-color: {c.BORDA};
    }}
    QSplitter::handle:horizontal {{
        width: 4px;
    }}
    QSplitter::handle:vertical {{
        height: 4px;
    }}
    QSplitter::handle:hover {{
        background-color: {c.ACENTO_PRIMARIO};
    }}

    /* Barras de Rolagem */
    QScrollBar:vertical {{
        background-color: {c.FUNDO};
        width: 10px;
        margin: 0;
        border: none;
    }}
    QScrollBar::handle:vertical {{
        background-color: {c.BORDA};
        min-height: 25px;
        border-radius: 5px;
    }}
    QScrollBar::handle:vertical:hover {{
        background-color: {c.ACENTO_PRIMARIO};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
    }}
    QScrollBar:horizontal {{
        background-color: {c.FUNDO};
        height: 10px;
        margin: 0;
        border: none;
    }}
    QScrollBar::handle:horizontal {{
        background-color: {c.BORDA};
        min-width: 25px;
        border-radius: 5px;
    }}
    QScrollBar::handle:horizontal:hover {{
        background-color: {c.ACENTO_PRIMARIO};
    }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
        width: 0px;
    }}

    /* Cartões e Grupos */
    QGroupBox {{
        background-color: {c.CARTAO};
        border: 1px solid {c.BORDA};
        border-radius: 8px;
        margin-top: 24px;
        font-weight: 600;
        padding: 12px;
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        subcontrol-position: top left;
        padding: 4px 10px;
        color: {c.ACENTO_PRIMARIO};
        background-color: {c.SUPERFICIE};
        border: 1px solid {c.BORDA};
        border-radius: 4px;
    }}
    QFrame[classe="cartao"] {{
        background-color: {c.CARTAO};
        border: 1px solid {c.BORDA};
        border-radius: 8px;
        padding: 10px;
    }}
    QFrame[classe="cartao"]:hover {{
        border-color: {c.ACENTO_PRIMARIO};
    }}

    /* Barra de Status */
    QStatusBar {{
        background-color: {c.SUPERFICIE};
        border-top: 1px solid {c.BORDA};
        color: {c.TEXTO_SECUNDARIO};
        font-size: 12px;
        font-weight: 500;
        min-height: 28px;
    }}
    QStatusBar QLabel {{
        color: {c.TEXTO_PRINCIPAL};
        padding: 2px 8px;
    }}

    /* Rótulos e Textos */
    QLabel {{
        color: {c.TEXTO_PRINCIPAL};
    }}
    QLabel[subtitulo="true"] {{
        color: {c.TEXTO_SECUNDARIO};
        font-size: 11px;
    }}
    QLabel[titulo="true"] {{
        font-size: 15px;
        font-weight: 700;
        color: #ffffff;
    }}

    /* Tooltip */
    QToolTip {{
        background-color: {c.CARTAO};
        color: {c.TEXTO_PRINCIPAL};
        border: 1px solid {c.ACENTO_PRIMARIO};
        border-radius: 4px;
        padding: 5px 8px;
        font-size: 12px;
    }}

    /* Checkbox e RadioButton */
    QCheckBox, QRadioButton {{
        color: {c.TEXTO_PRINCIPAL};
        spacing: 8px;
    }}
    QCheckBox::indicator, QRadioButton::indicator {{
        width: 18px;
        height: 18px;
        border: 1px solid {c.BORDA};
        border-radius: 4px;
        background-color: {c.SUPERFICIE};
    }}
    QCheckBox::indicator:hover, QRadioButton::indicator:hover {{
        border-color: {c.ACENTO_PRIMARIO};
    }}
    QCheckBox::indicator:checked {{
        background-color: {c.ACENTO_PRIMARIO};
        border-color: {c.ACENTO_PRIMARIO};
    }}

    /* Barra de Progresso */
    QProgressBar {{
        background-color: {c.SUPERFICIE};
        border: 1px solid {c.BORDA};
        border-radius: 6px;
        text-align: center;
        color: #ffffff;
        font-weight: 600;
        font-size: 11px;
    }}
    QProgressBar::chunk {{
        background-color: {c.ACENTO_PRIMARIO};
        border-radius: 5px;
    }}
    """


def aplicar_tema(alvo: Union[QApplication, QWidget]) -> None:
    """Aplica o tema escuro industrial ao QApplication ou QWidget alvo."""
    qss = obter_qss()
    alvo.setStyleSheet(qss)
