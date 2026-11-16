"""
motor_pdf — Motor nativo próprio de leitura, análise e manipulação de arquivos PDF.

Projetado para automação gráfica industrial e comunicação visual.
100% autônomo, sem dependências de PyMuPDF, Poppler ou qualquer biblioteca AGPL/GPL.
"""

from .leitor import Caixa, ImagemInfo, Pagina, PdfReader
from .sintaxe import PdfArray, PdfDict, PdfName, PdfRef, PdfStream, PdfString


def abrir_pdf(caminho_ou_bytes) -> PdfReader:
    """Abre um documento PDF para leitura e inspeção estrutural."""
    return PdfReader(caminho_ou_bytes)


__all__ = [
    "abrir_pdf",
    "PdfReader",
    "Pagina",
    "Caixa",
    "ImagemInfo",
    "PdfName",
    "PdfRef",
    "PdfString",
    "PdfDict",
    "PdfArray",
    "PdfStream",
]
