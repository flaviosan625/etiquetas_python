"""
Pacote UI: Interface Gráfica Moderna PySide6 / Qt para Gestão, Triagem e Montagem CNC/Impressão.
"""

from ui.tema import CoresTema, aplicar_tema, obter_qss
from ui.canvas_montagem import CanvasMontagem, PecaGraficaItem
from ui.janela_principal import JanelaPrincipal

__all__ = [
    "CoresTema",
    "aplicar_tema",
    "obter_qss",
    "CanvasMontagem",
    "PecaGraficaItem",
    "JanelaPrincipal",
]
