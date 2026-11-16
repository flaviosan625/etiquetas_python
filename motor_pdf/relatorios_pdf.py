"""
motor_pdf/relatorios_pdf.py — Gerador nativo de relatórios e documentos em formato A4 (ISO 32000-1).

Implementa:
  - Layout e paginação para documentos em folha A4 (595.28 x 841.89 pt).
  - Composição de tabelas com linhas zebradas, caixas de seleção e badges de categoria.
  - Inserção de logotipos e miniaturas gráficas preservando proporção.
  - Paginação automática no rodapé ("Página X de Y").
  - Geração de Comprovante de Retirada (Romaneio) e Ordem de Serviço (OS).
"""

from __future__ import annotations

import io
import math
import os
import pathlib
import unicodedata
from typing import Any, Dict, List, Optional, Tuple, Union

from .escritor import PdfWriter
from .leitor import PT_POR_M, PT_POR_MM
from .montador import HELVETICA_LARGURAS, largura_texto_helvetica_1pt, sanitizar_texto_ascii
from .sintaxe import PdfName, PdfRef, PdfStream, PdfString

LARGURA_A4_PT = 595.28
ALTURA_A4_PT = 841.89

MARGEM_PADRAO_PT = 36.0  # 0.5 polegada = 36 pt


class RelatorioA4Builder:
    """Construtor de páginas A4 com operações gráficas e tipográficas de alta precisão."""

    def __init__(self, versao: str = "1.6"):
        self.writer = PdfWriter(versao=versao)
        self.paginas_comandos: List[bytearray] = []
        self.paginas_recursos: List[Dict[PdfName, Any]] = []

        # Registra fonte padrão Helvetica
        self.fonte_helv_id = self.writer.alocar_id()
        self.writer.objetos[self.fonte_helv_id] = {
            PdfName("/Type"): PdfName("/Font"),
            PdfName("/Subtype"): PdfName("/Type1"),
            PdfName("/BaseFont"): PdfName("/Helvetica"),
            PdfName("/Encoding"): PdfName("/WinAnsiEncoding"),
        }

        self.fonte_helv_bold_id = self.writer.alocar_id()
        self.writer.objetos[self.fonte_helv_bold_id] = {
            PdfName("/Type"): PdfName("/Font"),
            PdfName("/Subtype"): PdfName("/Type1"),
            PdfName("/BaseFont"): PdfName("/Helvetica-Bold"),
            PdfName("/Encoding"): PdfName("/WinAnsiEncoding"),
        }

        self._imagem_cache: Dict[bytes, Tuple[PdfRef, str, int, int]] = {}
        self._cont_img = 1

        self._cmd_atual: Optional[bytearray] = None
        self._rec_atual: Optional[Dict[PdfName, Any]] = None
        self._xobjects_atual: Dict[PdfName, PdfRef] = {}

    def nova_pagina(self):
        """Inicia uma nova página em branco A4."""
        self._finalizar_pagina_se_aberta()
        self._cmd_atual = bytearray()
        self._xobjects_atual = {}
        self._rec_atual = {
            PdfName("/Font"): {
                PdfName("/F1"): PdfRef(self.fonte_helv_id, 0),
                PdfName("/F2"): PdfRef(self.fonte_helv_bold_id, 0),
            },
            PdfName("/XObject"): self._xobjects_atual,
        }

    def _finalizar_pagina_se_aberta(self):
        if self._cmd_atual is not None and self._rec_atual is not None:
            self.paginas_comandos.append(self._cmd_atual)
            self.paginas_recursos.append(self._rec_atual)
            self._cmd_atual = None
            self._rec_atual = None

    def desenhar_linha(
        self,
        x0: float,
        y0: float,
        x1: float,
        y1: float,
        cor: Tuple[float, float, float] = (0.0, 0.0, 0.0),
        espessura: float = 1.0,
    ):
        """Desenha um segmento de reta entre (x0, y0) e (x1, y1)."""
        if self._cmd_atual is None:
            self.nova_pagina()
        # Converte Y (origem no topo para coordenadas PDF que começam na base)
        py0 = ALTURA_A4_PT - y0
        py1 = ALTURA_A4_PT - y1
        self._cmd_atual.extend(b"q\n")
        self._cmd_atual.extend(f"{cor[0]:.3f} {cor[1]:.3f} {cor[2]:.3f} RG\n".encode("ascii"))
        self._cmd_atual.extend(f"{espessura:.2f} w\n".encode("ascii"))
        self._cmd_atual.extend(f"{x0:.2f} {py0:.2f} m {x1:.2f} {py1:.2f} l S\n".encode("ascii"))
        self._cmd_atual.extend(b"Q\n")

    def desenhar_retangulo(
        self,
        x: float,
        y: float,
        w: float,
        h: float,
        cor_traco: Optional[Tuple[float, float, float]] = None,
        cor_fundo: Optional[Tuple[float, float, float]] = None,
        espessura: float = 1.0,
    ):
        """Desenha um retângulo com cantos vivos ou preenchimento de fundo."""
        if self._cmd_atual is None:
            self.nova_pagina()
        py = ALTURA_A4_PT - (y + h)
        self._cmd_atual.extend(b"q\n")
        if cor_fundo:
            self._cmd_atual.extend(f"{cor_fundo[0]:.3f} {cor_fundo[1]:.3f} {cor_fundo[2]:.3f} rg\n".encode("ascii"))
        if cor_traco:
            self._cmd_atual.extend(f"{cor_traco[0]:.3f} {cor_traco[1]:.3f} {cor_traco[2]:.3f} RG\n".encode("ascii"))
            self._cmd_atual.extend(f"{espessura:.2f} w\n".encode("ascii"))

        self._cmd_atual.extend(f"{x:.2f} {py:.2f} {w:.2f} {h:.2f} re\n".encode("ascii"))
        if cor_fundo and cor_traco:
            self._cmd_atual.extend(b"B\n")
        elif cor_fundo:
            self._cmd_atual.extend(b"f\n")
        elif cor_traco:
            self._cmd_atual.extend(b"S\n")
        self._cmd_atual.extend(b"Q\n")

    def desenhar_texto(
        self,
        x: float,
        y: float,
        texto: str,
        tamanho: float = 9.0,
        cor: Tuple[float, float, float] = (0.0, 0.0, 0.0),
        negrito: bool = False,
        alinhamento: str = "left",
        largura_max: Optional[float] = None,
    ):
        """Desenha uma linha de texto na página com suporte a alinhamento esquerdo, centro e direito."""
        if self._cmd_atual is None:
            self.nova_pagina()
        if not texto:
            return

        txt_sanitizado = sanitizar_texto_ascii(texto)
        fonte = "/F2" if negrito else "/F1"

        largura_est = largura_texto_helvetica_1pt(txt_sanitizado) * tamanho
        if largura_max and largura_est > largura_max and largura_max > 0:
            # Encurta com reticências
            while len(txt_sanitizado) > 3 and (largura_texto_helvetica_1pt(txt_sanitizado + "...") * tamanho) > largura_max:
                txt_sanitizado = txt_sanitizado[:-1]
            txt_sanitizado += "..."
            largura_est = largura_texto_helvetica_1pt(txt_sanitizado) * tamanho

        px = x
        if alinhamento == "right":
            px = x - largura_est
        elif alinhamento == "center":
            px = x - (largura_est / 2.0)

        py = ALTURA_A4_PT - y
        self._cmd_atual.extend(b"q\n")
        self._cmd_atual.extend(f"{cor[0]:.3f} {cor[1]:.3f} {cor[2]:.3f} rg\n".encode("ascii"))
        self._cmd_atual.extend(b"BT\n")
        self._cmd_atual.extend(f"{fonte} {tamanho:.2f} Tf\n".encode("ascii"))
        self._cmd_atual.extend(f"1 0 0 1 {px:.2f} {py:.2f} Tm\n".encode("ascii"))
        self._cmd_atual.extend(f"({txt_sanitizado}) Tj\n".encode("ascii"))
        self._cmd_atual.extend(b"ET\n")
        self._cmd_atual.extend(b"Q\n")

    def desenhar_imagem(
        self,
        x: float,
        y: float,
        w: float,
        h: float,
        dados_imagem: bytes,
        manter_proporcao: bool = True,
    ):
        """Insere uma imagem na página A4 preservando a proporção de aspecto."""
        if self._cmd_atual is None:
            self.nova_pagina()
        if not dados_imagem:
            return

        # Verifica cache de imagens embutidas
        if dados_imagem in self._imagem_cache:
            img_ref, nome_img, img_w, img_h = self._imagem_cache[dados_imagem]
        else:
            img_ref, img_w, img_h = self.writer.adicionar_imagem(dados_imagem)
            nome_img = f"/Im{self._cont_img}"
            self._cont_img += 1
            self._imagem_cache[dados_imagem] = (img_ref, nome_img, img_w, img_h)

        self._xobjects_atual[PdfName(nome_img)] = img_ref

        largura_final = w
        altura_final = h
        desl_x = 0.0
        desl_y = 0.0

        if manter_proporcao and img_w > 0 and img_h > 0:
            escala = min(w / img_w, h / img_h)
            largura_final = img_w * escala
            altura_final = img_h * escala
            desl_x = (w - largura_final) / 2.0
            desl_y = (h - altura_final) / 2.0

        # Converte Y de topo para PDF
        py = ALTURA_A4_PT - (y + desl_y + altura_final)
        px = x + desl_x

        self._cmd_atual.extend(b"q\n")
        self._cmd_atual.extend(f"{largura_final:.2f} 0 0 {altura_final:.2f} {px:.2f} {py:.2f} cm\n".encode("ascii"))
        self._cmd_atual.extend(f"{nome_img} Do\n".encode("ascii"))
        self._cmd_atual.extend(b"Q\n")

    def salvar(self, destino: Union[str, os.PathLike, io.BytesIO]) -> bytes:
        """Finaliza todas as páginas e grava o documento PDF."""
        self._finalizar_pagina_se_aberta()

        total_paginas = len(self.paginas_comandos)
        for idx in range(total_paginas):
            cmds = self.paginas_comandos[idx]
            recs = self.paginas_recursos[idx]

            # Rodapé de paginação: Pagina X de Y
            txt_pag = sanitizar_texto_ascii(f"Pagina {idx + 1} de {total_paginas}")
            largura_pag = largura_texto_helvetica_1pt(txt_pag) * 7.0
            x_pag = LARGURA_A4_PT - MARGEM_PADRAO_PT - largura_pag
            y_pag = 20.0  # pontos a partir do rodapé físico

            rodape_cmd = f"""
            q
            0.4 0.4 0.4 rg
            BT
            /F1 7.00 Tf
            1 0 0 1 {x_pag:.2f} {y_pag:.2f} Tm
            ({txt_pag}) Tj
            ET
            Q
            """.encode("ascii")

            cmds.extend(rodape_cmd)

            self.writer.adicionar_pagina(
                largura_pt=LARGURA_A4_PT,
                altura_pt=ALTURA_A4_PT,
                recursos=recs,
                conteudo_bytes=bytes(cmds),
            )

        return self.writer.salvar(destino)
