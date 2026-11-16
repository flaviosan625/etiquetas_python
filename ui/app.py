"""
Ponto de Entrada da Interface Gráfica PySide6 / Qt.

Inicialização e bootstrap da aplicação com tema escuro industrial.
"""

import sys
from typing import Optional, Tuple, List
from PySide6.QtWidgets import QApplication

from ui.tema import aplicar_tema
from ui.janela_principal import JanelaPrincipal


def iniciar_aplicativo(
    argumentos: Optional[List[str]] = None,
    executar: bool = True,
) -> Tuple[QApplication, JanelaPrincipal]:
    """
    Inicializa a aplicação PySide6 com JanelaPrincipal e tema industrial completo.

    :param argumentos: Lista opcional de argumentos de linha de comando.
    :param executar: Se True, inicia o event loop do Qt (app.exec()).
    :return: Tupla com (QApplication, JanelaPrincipal).
    """
    args = sys.argv if argumentos is None else argumentos
    app = QApplication.instance()
    if app is None:
        app = QApplication(args)

    app.setApplicationName("Sistema Integrado CNC & Impressão")
    app.setOrganizationName("UNY CV")

    # Aplicar o tema escuro globalmente
    aplicar_tema(app)

    janela = JanelaPrincipal()
    janela.show()

    if executar:
        sys.exit(app.exec())

    return app, janela


if __name__ == "__main__":
    iniciar_aplicativo()
