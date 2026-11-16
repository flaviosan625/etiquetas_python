"""
motor_pdf — Motor nativo próprio de leitura, análise e manipulação de arquivos PDF.

Projetado para automação gráfica industrial e comunicação visual.
100% autônomo, sem dependências de PyMuPDF, Poppler ou qualquer biblioteca AGPL/GPL.
"""

from .escritor import PdfWriter
from .geometria import BoundingBox, Matriz2D
from .interpretador_stream import calcular_caixa_da_arte, interpretar_stream
from .leitor import Caixa, ImagemInfo, Pagina, PdfReader
from .montador import MontadorBobina, PecaMontagem
from .sintaxe import PdfArray, PdfDict, PdfName, PdfRef, PdfStream, PdfString


def abrir_pdf(caminho_ou_bytes) -> PdfReader:
    """Abre um documento PDF para leitura e inspeção estrutural."""
    return PdfReader(caminho_ou_bytes)


__all__ = [
    "abrir_pdf",
    "PdfReader",
    "PdfWriter",
    "MontadorBobina",
    "PecaMontagem",
    "Pagina",
    "Caixa",
    "ImagemInfo",
    "Matriz2D",
    "BoundingBox",
    "calcular_caixa_da_arte",
    "interpretar_stream",
    "PdfName",
    "PdfRef",
    "PdfString",
    "PdfDict",
    "PdfArray",
    "PdfStream",
]
