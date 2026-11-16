"""
motor_pdf/montador.py — Motor nativo de imposição gráfica para bobinas e chapas (ISO 32000-1).

Princípios Arquiteturais:
  1. Preservação cega de bytes: as páginas importadas são encapsuladas como /Subtype /Form XObjects,
     sem recompactação ou perda de canais de cor, vetores ou camadas especiais (CutContour).
  2. Deduplicação inteligente: peças repetidas na bobina compartilham o mesmo objeto /Form,
     sendo apenas referenciadas com matrizes afins (cm) distintas.
  3. Rótulos milimétricos com fonte Helvetica calculada proporcionalmente para caber em 300 mm.
  4. Linhas de corte vetoriais e cabeçalho de produção padronizado.
"""

from __future__ import annotations

import io
import os
import pathlib
import unicodedata
import zlib
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple, Union

from .escritor import PdfWriter
from .geometria import Matriz2D
from .leitor import Caixa, Pagina, PdfReader, PT_POR_M, PT_POR_MM, abrir_pdf
from .sintaxe import PdfName, PdfRef, PdfStream, PdfString

# Tabela de larguras de glifos da fonte padrão Helvetica (unidades por 1000 de em)
HELVETICA_LARGURAS = {
    " ": 278, "!": 278, '"': 355, "#": 556, "$": 556, "%": 889, "&": 667, "'": 191,
    "(": 333, ")": 333, "*": 389, "+": 584, ",": 278, "-": 333, ".": 278, "/": 278,
    "0": 556, "1": 556, "2": 556, "3": 556, "4": 556, "5": 556, "6": 556, "7": 556,
    "8": 556, "9": 556, ":": 278, ";": 278, "<": 584, "=": 584, ">": 584, "?": 556,
    "@": 1015, "A": 667, "B": 667, "C": 722, "D": 722, "E": 667, "F": 611, "G": 778,
    "H": 722, "I": 278, "J": 500, "K": 667, "L": 556, "M": 833, "N": 722, "O": 778,
    "P": 667, "Q": 778, "R": 722, "S": 667, "T": 611, "U": 722, "V": 667, "W": 944,
    "X": 667, "Y": 667, "Z": 611, "[": 278, "\\": 278, "]": 278, "^": 469, "_": 556,
    "`": 333, "a": 556, "b": 556, "c": 500, "d": 556, "e": 556, "f": 278, "g": 556,
    "h": 556, "i": 222, "j": 222, "k": 500, "l": 222, "m": 833, "n": 556, "o": 556,
    "p": 556, "q": 556, "r": 333, "s": 500, "t": 278, "u": 556, "v": 500, "w": 722,
    "x": 500, "y": 500, "z": 500, "{": 334, "|": 260, "}": 334, "~": 584,
}


def largura_texto_helvetica_1pt(texto: str) -> float:
    """Calcula a largura teórica do texto em Helvetica com tamanho de fonte de 1 pt."""
    total_unidades = sum(HELVETICA_LARGURAS.get(ch, 500) for ch in texto)
    return total_unidades / 1000.0


def sanitizar_texto_ascii(texto: str) -> str:
    """Substitui quebras de linha e normaliza caracteres para exibição limpa em Type 1."""
    limpo = texto.replace("\r", " ").replace("\n", " ").strip()
    # Converte acentuações para ASCII padrão sem descaracterizar o nome
    normalizado = unicodedata.normalize("NFKD", limpo).encode("ascii", "ignore").decode("ascii")
    # Escapa parênteses e barras para sintaxe de string PDF
    return normalizado.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


@dataclass
class PecaMontagem:
    """Especificação de uma peça a ser imposta na bobina/chapa."""
    arquivo: Union[str, pathlib.Path]
    numero_pagina: int = 0
    x_m: float = 0.0              # Posição X (em metros)
    y_m: float = 0.0              # Posição Y (em metros)
    largura_m: float = 0.0        # Largura final desejada (em metros)
    altura_m: float = 0.0         # Altura final desejada (em metros)
    girada: bool = False          # True se girada 90 graus para melhor aproveitamento
    escala: float = 1.0           # Fator de escala (ex: 10.0 se for arte 1:10)
    rotulo: Optional[str] = None  # Texto de identificação da peça
    descontar_franja: bool = True # Se True, utiliza caixa_da_arte eliminando franjas brancas


class MontadorBobina:
    """
    Motor autônomo de imposição por Form XObjects.
    Gera bobinas contínuas ou chapas planas em conformidade com ISO 32000-1.
    """

    def __init__(
        self,
        largura_m: float,
        altura_m: float,
        margem_m: float = 0.02,
        folga_m: float = 0.05,
        cabecalho_m: float = 0.08,
        titulo: Optional[str] = None,
    ):
        self.largura_m = float(largura_m)
        self.altura_m = float(altura_m)
        self.margem_m = float(margem_m)
        self.folga_m = float(folga_m)
        self.cabecalho_m = float(cabecalho_m)
        self.titulo = titulo

        self.largura_pt = self.largura_m * PT_POR_M
        self.altura_pt = self.altura_m * PT_POR_M

        self.pecas: List[PecaMontagem] = []
        self.writer = PdfWriter(versao="1.6")

        # Cache de Forms criados para reaproveitamento:
        # (caminho_str, num_pag, descontar_franja) -> (PdfRef, nome_xobject, Caixa)
        self._cache_forms: Dict[Tuple[str, int, bool], Tuple[PdfRef, str, Caixa]] = {}
        self._cont_forms = 1

        # Registra fonte padrão Helvetica
        self.fonte_helvetica_id = self.writer.alocar_id()
        self.writer.objetos[self.fonte_helvetica_id] = {
            PdfName("/Type"): PdfName("/Font"),
            PdfName("/Subtype"): PdfName("/Type1"),
            PdfName("/BaseFont"): PdfName("/Helvetica"),
            PdfName("/Encoding"): PdfName("/WinAnsiEncoding"),
        }

    def adicionar_peca(self, peca: PecaMontagem):
        """Adiciona uma peça à lista de imposição da folha."""
        self.pecas.append(peca)

    def _obter_ou_criar_form(
        self,
        arquivo_path: Union[str, pathlib.Path],
        numero_pagina: int,
        descontar_franja: bool,
    ) -> Tuple[PdfRef, str, Caixa]:
        """Cria ou recupera do cache o Form XObject correspondente à página da arte."""
        caminho_str = str(pathlib.Path(arquivo_path).resolve())
        chave = (caminho_str, numero_pagina, descontar_franja)
        if chave in self._cache_forms:
            return self._cache_forms[chave]

        with abrir_pdf(caminho_str) as leitor:
            if numero_pagina >= len(leitor.paginas):
                raise IndexError(f"Página {numero_pagina} não encontrada no arquivo {caminho_str}")

            pagina = leitor.paginas[numero_pagina]
            if descontar_franja:
                caixa = pagina.obter_caixa_da_arte()
            else:
                caixa = pagina.trimbox if not pagina.trimbox.vazio else pagina.cropbox

            # Clona dicionário de recursos da página para dentro do writer
            recursos_orig = pagina.raw_dict.get("/Resources") or pagina.raw_dict.get(PdfName("/Resources"))
            recursos_clonados = {}
            if recursos_orig:
                rec_resolvido = leitor._resolver_objeto(recursos_orig)
                recursos_clonados = self.writer.importar_objeto(leitor, rec_resolvido) or {}

            # Obtém stream de conteúdo da página e comprime em Flate
            raw_content = pagina.obter_conteudo_bruto()
            stream_comprimido = zlib.compress(raw_content, level=6)

            form_header = {
                PdfName("/Type"): PdfName("/XObject"),
                PdfName("/Subtype"): PdfName("/Form"),
                PdfName("/FormType"): 1,
                PdfName("/BBox"): [float(caixa.x0), float(caixa.y0), float(caixa.x1), float(caixa.y1)],
                PdfName("/Matrix"): [1.0, 0.0, 0.0, 1.0, 0.0, 0.0],
                PdfName("/Resources"): recursos_clonados,
                PdfName("/Filter"): PdfName("/FlateDecode"),
                PdfName("/Length"): len(stream_comprimido),
            }

            form_stream = PdfStream(form_header, stream_comprimido)
            form_ref = self.writer.adicionar_objeto(form_stream)
            nome_form = f"/Fm{self._cont_forms}"
            self._cont_forms += 1

            resultado = (form_ref, nome_form, caixa)
            self._cache_forms[chave] = resultado
            return resultado

    def montar(self) -> bytes:
        """Executa a imposição e retorna os bytes do PDF gerado."""
        dicionario_xobjects: Dict[PdfName, PdfRef] = {}
        stream_pagina = bytearray()

        # 1. Cabeçalho de Identificação no Topo (se houver título)
        if self.titulo:
            texto_titulo = sanitizar_texto_ascii(self.titulo)
            y_cabecalho = self.altura_pt - (self.cabecalho_m * PT_POR_M * 0.6)
            x_cabecalho = self.margem_m * PT_POR_M
            corpo_cabecalho = min(16.0 * PT_POR_MM, max(8.0 * PT_POR_MM, self.cabecalho_m * PT_POR_M * 0.25))

            stream_pagina.extend(b"q\n")
            stream_pagina.extend(b"0.35 0.35 0.35 rg\n")  # Cinza padrão de produção
            stream_pagina.extend(b"BT\n")
            stream_pagina.extend(f"/F1 {corpo_cabecalho:.2f} Tf\n".encode("ascii"))
            stream_pagina.extend(f"1 0 0 1 {x_cabecalho:.2f} {y_cabecalho:.2f} Tm\n".encode("ascii"))
            stream_pagina.extend(f"({texto_titulo}) Tj\n".encode("ascii"))
            stream_pagina.extend(b"ET\n")
            stream_pagina.extend(b"Q\n")

        # 2. Imposição de cada peça
        for peca in self.pecas:
            form_ref, nome_form, caixa_orig = self._obter_ou_criar_form(
                peca.arquivo, peca.numero_pagina, peca.descontar_franja
            )
            dicionario_xobjects[PdfName(nome_form)] = form_ref

            x_pt = peca.x_m * PT_POR_M
            y_pt = peca.y_m * PT_POR_M
            l_pt = peca.largura_m * PT_POR_M
            a_pt = peca.altura_m * PT_POR_M

            w_orig = max(0.001, caixa_orig.width)
            h_orig = max(0.001, caixa_orig.height)

            # Matriz Afim para Colocação da Peça
            if not peca.girada:
                sx = l_pt / w_orig
                sy = a_pt / h_orig
                a = sx
                b = 0.0
                c = 0.0
                d = sy
                e = x_pt - (sx * caixa_orig.x0)
                f = y_pt - (sy * caixa_orig.y0)
            else:
                # Girada 90 graus no sentido anti-horário
                sx = l_pt / h_orig
                sy = a_pt / w_orig
                a = 0.0
                b = sy
                c = -sx
                d = 0.0
                e = x_pt + (sx * caixa_orig.y1)
                f = y_pt - (sy * caixa_orig.x0)

            # Invocação do Form XObject
            stream_pagina.extend(b"q\n")
            stream_pagina.extend(f"{a:.6f} {b:.6f} {c:.6f} {d:.6f} {e:.6f} {f:.6f} cm\n".encode("ascii"))
            stream_pagina.extend(f"{nome_form} Do\n".encode("ascii"))
            stream_pagina.extend(b"Q\n")

            # 3. Rótulo da Peça (Largura alvo: 300 mm = 0.30 m)
            if peca.rotulo:
                texto_rotulo = sanitizar_texto_ascii(peca.rotulo)
                largura_alvo_rotulo_pt = min(l_pt, 0.30 * PT_POR_M)
                largura_1pt = largura_texto_helvetica_1pt(texto_rotulo)

                # Tamanho da fonte proporcional
                corpo_pt = largura_alvo_rotulo_pt / max(largura_1pt, 1e-6)
                # Limite: máximo 10 mm, mínimo 2 mm
                corpo_pt = min(10.0 * PT_POR_MM, max(2.0 * PT_POR_MM, corpo_pt))

                # Posicionado acima da borda superior da peça (dentro da folga de corte)
                y_rotulo = y_pt + a_pt + (1.5 * PT_POR_MM)
                x_rotulo = x_pt

                stream_pagina.extend(b"q\n")
                stream_pagina.extend(b"0 0 0 rg\n")  # Preto puro
                stream_pagina.extend(b"BT\n")
                stream_pagina.extend(f"/F1 {corpo_pt:.2f} Tf\n".encode("ascii"))
                stream_pagina.extend(f"1 0 0 1 {x_rotulo:.2f} {y_rotulo:.2f} Tm\n".encode("ascii"))
                stream_pagina.extend(f"({texto_rotulo}) Tj\n".encode("ascii"))
                stream_pagina.extend(b"ET\n")
                stream_pagina.extend(b"Q\n")

        # 4. Registra recursos da Página Mestra
        recursos_mestre = {
            PdfName("/XObject"): dicionario_xobjects,
            PdfName("/Font"): {
                PdfName("/F1"): PdfRef(self.fonte_helvetica_id, 0),
            },
        }

        self.writer.adicionar_pagina(
            largura_pt=self.largura_pt,
            altura_pt=self.altura_pt,
            recursos=recursos_mestre,
            conteudo_bytes=bytes(stream_pagina),
        )

        return self.writer.salvar(io.BytesIO())

    def salvar(self, caminho_arquivo: Union[str, pathlib.Path]):
        """Executa a montagem e salva diretamente no disco."""
        caminho = pathlib.Path(caminho_arquivo)
        caminho.parent.mkdir(parents=True, exist_ok=True)
        pdf_bytes = self.montar()
        with open(caminho, "wb") as f:
            f.write(pdf_bytes)
