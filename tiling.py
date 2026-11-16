"""
tiling.py — Módulo de Acabamento para Painelamento Automático de Grandes Formatos (Tiling).

Projetado para automação gráfica industrial e comunicação visual (ISSUE-06).
Implementa fatiamento de outdoors, lonas e frontlights em faixas com margem
de sobreposição de solda térmica / Leister, cruzetas de alinhamento e identificação técnica.

100% autônomo: utiliza exclusivamente o motor_pdf nativo (ISO 32000-1),
sem dependência de PyMuPDF, Poppler ou qualquer biblioteca AGPL/GPL.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
import zlib

from motor_pdf import Caixa, Matriz2D, PdfWriter, abrir_pdf
from motor_pdf.leitor import PT_POR_M, PT_POR_MM, Pagina, PdfReader
from motor_pdf.montador import (
    HELVETICA_LARGURAS,
    largura_texto_helvetica_1pt,
    sanitizar_texto_ascii,
)
from motor_pdf.sintaxe import PdfName, PdfRef, PdfStream, PdfString


@dataclass
class FaixaInfo:
    """Metadados de uma faixa individual resultante do painelamento."""

    indice: int  # Índice sequencial (1..N)
    x0_m: float  # Coordenada X inicial de corte na arte original (em metros)
    y0_m: float  # Coordenada Y inicial de corte na arte original (em metros)
    largura_util_m: float  # Largura útil efetiva da faixa sem overlap (em metros)
    largura_com_sobreposicao_m: float  # Largura física da faixa com overlaps (em metros)
    altura_m: float  # Altura física da faixa (em metros)
    sobreposicao_esquerda_m: float = 0.0  # Margem de solda à esquerda (em metros)
    sobreposicao_direita_m: float = 0.0  # Margem de solda à direita (em metros)
    sobreposicao_inferior_m: float = 0.0  # Margem de solda inferior (em metros)
    sobreposicao_superior_m: float = 0.0  # Margem de solda superior (em metros)
    altura_util_m: float = 0.0  # Altura útil efetiva da faixa sem overlap (em metros)
    bainha_extra_m: float = 0.0  # Margem de bainha/reforço de borda (em metros)


@dataclass
class PlanoPainelamento:
    """Plano geométrico completo de fatiamento de grande formato."""

    numero_faixas: int
    largura_total_m: float
    altura_total_m: float
    faixas: List[FaixaInfo]
    orientacao: str = "vertical"
    sobreposicao_solda_mm: float = 25.0
    bainha_extra_mm: float = 0.0


def calcular_painelamento(
    largura_m: float,
    altura_m: float,
    largura_maxima_faixa_m: float,
    sobreposicao_solda_mm: float = 25.0,
    orientacao: str = "vertical",
    bainha_extra_mm: float = 0.0,
) -> PlanoPainelamento:
    """
    Calcula o número ideal de faixas e a geometria exata de cada painel.

    Parâmetros:
      largura_m: Largura total da arte original em metros.
      altura_m: Altura total da arte original em metros.
      largura_maxima_faixa_m: Largura máxima imprimível da bobina/máquina em metros.
      sobreposicao_solda_mm: Margem de overlap de solda térmica entre faixas em milímetros (padrão 25 mm).
      orientacao: 'vertical' (fatiamento em colunas verticais) ou 'horizontal' (fatiamento em linhas horizontais).
      bainha_extra_mm: Margem extra de bainha perimetral em milímetros (padrão 0.0 mm).

    Retorna:
      PlanoPainelamento estruturado contendo a lista de FaixaInfo calculada.
    """
    if largura_m <= 0 or altura_m <= 0:
        raise ValueError("As dimensões da arte (largura e altura) devem ser maiores que zero.")

    if largura_maxima_faixa_m <= 0:
        raise ValueError("A largura máxima da faixa deve ser maior que zero.")

    if sobreposicao_solda_mm < 0:
        raise ValueError("A sobreposição de solda não pode ser negativa.")

    orientacao_norm = orientacao.strip().lower()
    if orientacao_norm not in ("vertical", "horizontal"):
        raise ValueError(f"Orientação inválida: '{orientacao}'. Use 'vertical' ou 'horizontal'.")

    sobreposicao_solda_m = sobreposicao_solda_mm / 1000.0
    bainha_extra_m = max(0.0, bainha_extra_mm / 1000.0)

    if sobreposicao_solda_m >= largura_maxima_faixa_m:
        raise ValueError("A sobreposição de solda não pode ser maior ou igual à largura útil da máquina.")

    faixas: List[FaixaInfo] = []

    if orientacao_norm == "vertical":
        # Fatiamento vertical (colunas ao longo da largura X)
        # Se a largura total couber diretamente na máquina, 1 faixa única
        if largura_m <= largura_maxima_faixa_m:
            numero_faixas = 1
        else:
            # Para N faixas com overlap de solda S em cada emenda:
            # cada faixa intermediária ou inicial com overlap tem largura útil + S <= largura_maxima
            # largura_util <= largura_maxima - S
            # N >= largura_m / (largura_maxima - S)
            passo_max_util = largura_maxima_faixa_m - sobreposicao_solda_m
            numero_faixas = max(2, math.ceil(largura_m / max(passo_max_util, 1e-6)))

        largura_util_base = largura_m / numero_faixas

        for i in range(1, numero_faixas + 1):
            x_ini = (i - 1) * largura_util_base
            x_fim = i * largura_util_base if i < numero_faixas else largura_m
            w_util = x_fim - x_ini

            # Padrão industrial com montagem em cascata [>>> SENTIDO DE MONTAGEM]:
            # Faixas 1..N-1 possuem margem de sobreposição à direita para solda da próxima faixa.
            # A última faixa (N) fecha a arte sem sobreposição à direita.
            if numero_faixas > 1 and i < numero_faixas:
                sob_dir = sobreposicao_solda_m
            else:
                sob_dir = 0.0

            sob_esq = 0.0

            # Adiciona bainha extra nas extremidades externas se configurada
            bainha_faixa_w = 0.0
            if bainha_extra_m > 0:
                if i == 1:
                    bainha_faixa_w += bainha_extra_m
                if i == numero_faixas:
                    bainha_faixa_w += bainha_extra_m

            largura_com_sob = w_util + sob_esq + sob_dir + bainha_faixa_w
            altura_faixa = altura_m + (2 * bainha_extra_m if bainha_extra_m > 0 else 0.0)

            faixas.append(
                FaixaInfo(
                    indice=i,
                    x0_m=x_ini,
                    y0_m=0.0,
                    largura_util_m=w_util,
                    largura_com_sobreposicao_m=largura_com_sob,
                    altura_m=altura_faixa,
                    sobreposicao_esquerda_m=sob_esq,
                    sobreposicao_direita_m=sob_dir,
                    altura_util_m=altura_m,
                    bainha_extra_m=bainha_extra_m,
                )
            )

    else:
        # Fatiamento horizontal (linhas ao longo da altura Y)
        # Se a altura total couber diretamente na máquina, 1 faixa única
        if altura_m <= largura_maxima_faixa_m:
            numero_faixas = 1
        else:
            passo_max_util = largura_maxima_faixa_m - sobreposicao_solda_m
            numero_faixas = max(2, math.ceil(altura_m / max(passo_max_util, 1e-6)))

        altura_util_base = altura_m / numero_faixas

        for j in range(1, numero_faixas + 1):
            y_ini = (j - 1) * altura_util_base
            y_fim = j * altura_util_base if j < numero_faixas else altura_m
            h_util = y_fim - y_ini

            if numero_faixas > 1 and j < numero_faixas:
                sob_sup = sobreposicao_solda_m
            else:
                sob_sup = 0.0

            sob_inf = 0.0

            bainha_faixa_h = 0.0
            if bainha_extra_m > 0:
                if j == 1:
                    bainha_faixa_h += bainha_extra_m
                if j == numero_faixas:
                    bainha_faixa_h += bainha_extra_m

            altura_com_sob = h_util + sob_inf + sob_sup + bainha_faixa_h
            largura_faixa = largura_m + (2 * bainha_extra_m if bainha_extra_m > 0 else 0.0)

            faixas.append(
                FaixaInfo(
                    indice=j,
                    x0_m=0.0,
                    y0_m=y_ini,
                    largura_util_m=largura_m,
                    largura_com_sobreposicao_m=largura_faixa,
                    altura_m=altura_com_sob,
                    sobreposicao_esquerda_m=0.0,
                    sobreposicao_direita_m=0.0,
                    sobreposicao_inferior_m=sob_inf,
                    sobreposicao_superior_m=sob_sup,
                    altura_util_m=h_util,
                    bainha_extra_m=bainha_extra_m,
                )
            )

    return PlanoPainelamento(
        numero_faixas=numero_faixas,
        largura_total_m=largura_m,
        altura_total_m=altura_m,
        faixas=faixas,
        orientacao=orientacao_norm,
        sobreposicao_solda_mm=sobreposicao_solda_mm,
        bainha_extra_mm=bainha_extra_mm,
    )


def gerar_faixas_pdf(
    caminho_arquivo: Union[str, Path],
    pasta_saida: Union[str, Path],
    largura_maxima_faixa_m: float,
    sobreposicao_solda_mm: float = 25.0,
    orientacao: str = "vertical",
    prefixo_nome: Optional[str] = None,
    bainha_extra_mm: float = 0.0,
    numero_pagina: int = 0,
) -> List[Path]:
    """
    Gera arquivos PDF individuais para cada faixa do plano de painelamento.

    Implementa:
      1. Preservação cega de bytes via importação como /Subtype /Form XObject.
      2. Mapeamento preciso por matriz afim de translação (cm).
      3. Cruzetas finas de solda no eixo da sobreposição com traçado '0 0 0 RG 0.5 w'.
      4. Identificação técnica no rodapé para orientação do operador de acabamento.

    Retorna:
      Lista de caminhos dos arquivos PDF gerados.
    """
    caminho_pdf = Path(caminho_arquivo).resolve()
    if not caminho_pdf.is_file():
        raise FileNotFoundError(f"Arquivo PDF não encontrado: {caminho_pdf}")

    pasta_dest = Path(pasta_saida).resolve()
    pasta_dest.mkdir(parents=True, exist_ok=True)

    # 1. Abre o documento original para inspeção de dimensões e extração de metadados
    with abrir_pdf(caminho_pdf) as leitor_orig:
        if len(leitor_orig.paginas) == 0:
            raise ValueError(f"O arquivo {caminho_pdf} não contém páginas.")

        if numero_pagina >= len(leitor_orig.paginas):
            raise IndexError(
                f"Página {numero_pagina} não encontrada (total: {len(leitor_orig.paginas)} páginas)."
            )

        pagina_orig = leitor_orig.paginas[numero_pagina]
        caixa_orig = pagina_orig.trimbox if not pagina_orig.trimbox.vazio else pagina_orig.cropbox
        if caixa_orig.vazio:
            caixa_orig = pagina_orig.mediabox

        largura_orig_m = pagina_orig.largura_m
        altura_orig_m = pagina_orig.altura_m

    # 2. Calcula o plano geométrico de fatiamento
    plano = calcular_painelamento(
        largura_m=largura_orig_m,
        altura_m=altura_orig_m,
        largura_maxima_faixa_m=largura_maxima_faixa_m,
        sobreposicao_solda_mm=sobreposicao_solda_mm,
        orientacao=orientacao,
        bainha_extra_mm=bainha_extra_mm,
    )

    nome_base = prefixo_nome.strip() if prefixo_nome else caminho_pdf.stem
    total_faixas = plano.numero_faixas
    arquivos_gerados: List[Path] = []

    # 3. Gera cada faixa como um PDF autônomo
    for faixa in plano.faixas:
        nome_arquivo = f"{nome_base}_FAIXA_{faixa.indice:02d}_DE_{total_faixas:02d}.pdf"
        caminho_saida = pasta_dest / nome_arquivo

        writer = PdfWriter(versao="1.6")

        # Importa a página original preservando 100% dos bytes de streams
        with abrir_pdf(caminho_pdf) as leitor:
            pag = leitor.paginas[numero_pagina]

            rec_orig = pag.raw_dict.get("/Resources") or pag.raw_dict.get(PdfName("/Resources"))
            recursos_clonados = {}
            if rec_orig:
                rec_resolvido = leitor._resolver_objeto(rec_orig)
                recursos_clonados = writer.importar_objeto(leitor, rec_resolvido) or {}

            raw_content = pag.obter_conteudo_bruto()
            stream_comprimido = zlib.compress(raw_content, level=6)

            form_header = {
                PdfName("/Type"): PdfName("/XObject"),
                PdfName("/Subtype"): PdfName("/Form"),
                PdfName("/FormType"): 1,
                PdfName("/BBox"): [
                    float(caixa_orig.x0),
                    float(caixa_orig.y0),
                    float(caixa_orig.x1),
                    float(caixa_orig.y1),
                ],
                PdfName("/Matrix"): [1.0, 0.0, 0.0, 1.0, 0.0, 0.0],
                PdfName("/Resources"): recursos_clonados,
                PdfName("/Filter"): PdfName("/FlateDecode"),
                PdfName("/Length"): len(stream_comprimido),
            }

            form_stream = PdfStream(form_header, stream_comprimido)
            form_ref = writer.adicionar_objeto(form_stream)

        # Registra fonte Helvetica para os textos técnicos
        fonte_id = writer.alocar_id()
        writer.objetos[fonte_id] = {
            PdfName("/Type"): PdfName("/Font"),
            PdfName("/Subtype"): PdfName("/Type1"),
            PdfName("/BaseFont"): PdfName("/Helvetica"),
            PdfName("/Encoding"): PdfName("/WinAnsiEncoding"),
        }

        # Dimensões da página da faixa em pontos PDF
        faixa_largura_pt = faixa.largura_com_sobreposicao_m * PT_POR_M
        faixa_altura_pt = faixa.altura_m * PT_POR_M

        stream_cmds = bytearray()

        # Determina a janela de recorte na arte original
        x_inicio_corte_m = faixa.x0_m - faixa.sobreposicao_esquerda_m
        y_inicio_corte_m = faixa.y0_m - faixa.sobreposicao_inferior_m

        dx_pt = x_inicio_corte_m * PT_POR_M
        dy_pt = y_inicio_corte_m * PT_POR_M

        # Matriz de translação afim para alinhar a janela correta da arte na faixa
        e = -(caixa_orig.x0 + dx_pt)
        f = -(caixa_orig.y0 + dy_pt)

        # 4. Invocação do Form XObject com máscara de recorte segura
        stream_cmds.extend(b"q\n")
        stream_cmds.extend(
            f"0.0 0.0 {faixa_largura_pt:.4f} {faixa_altura_pt:.4f} re W n\n".encode("ascii")
        )
        stream_cmds.extend(
            f"1.000000 0.000000 0.000000 1.000000 {e:.6f} {f:.6f} cm\n".encode("ascii")
        )
        stream_cmds.extend(b"/Fm1 Do\n")
        stream_cmds.extend(b"Q\n")

        # 5. Cruzetas finas de alinhamento de solda no eixo da sobreposição
        # Conforme especificação: '0 0 0 RG 0.5 w'
        raio_cruzeta_pt = 5.0 * PT_POR_MM  # 5 mm de raio (10 mm de extensão total)

        def adicionar_cruzeta(x_c: float, y_c: float):
            stream_cmds.extend(b"q\n")
            stream_cmds.extend(b"0 0 0 RG 0.5 w\n")
            stream_cmds.extend(
                f"{x_c - raio_cruzeta_pt:.2f} {y_c:.2f} m {x_c + raio_cruzeta_pt:.2f} {y_c:.2f} l S\n".encode(
                    "ascii"
                )
            )
            stream_cmds.extend(
                f"{x_c:.2f} {y_c - raio_cruzeta_pt:.2f} m {x_c:.2f} {y_c + raio_cruzeta_pt:.2f} l S\n".encode(
                    "ascii"
                )
            )
            stream_cmds.extend(b"Q\n")

        if plano.orientacao == "vertical":
            # Eixo de solda na extremidade direita da faixa
            if faixa.sobreposicao_direita_m > 0:
                x_eixo = (faixa.largura_com_sobreposicao_m - faixa.sobreposicao_direita_m) * PT_POR_M
                y_base = 25.0 * PT_POR_MM
                y_topo = faixa_altura_pt - (25.0 * PT_POR_MM)
                adicionar_cruzeta(x_eixo, y_base)
                adicionar_cruzeta(x_eixo, y_topo)
                if faixa_altura_pt > 1.5 * PT_POR_M:
                    adicionar_cruzeta(x_eixo, faixa_altura_pt / 2.0)

            # Eixo de solda na extremidade esquerda da faixa (se houver)
            if faixa.sobreposicao_esquerda_m > 0:
                x_eixo = faixa.sobreposicao_esquerda_m * PT_POR_M
                y_base = 25.0 * PT_POR_MM
                y_topo = faixa_altura_pt - (25.0 * PT_POR_MM)
                adicionar_cruzeta(x_eixo, y_base)
                adicionar_cruzeta(x_eixo, y_topo)
                if faixa_altura_pt > 1.5 * PT_POR_M:
                    adicionar_cruzeta(x_eixo, faixa_altura_pt / 2.0)
        else:
            # Eixo de solda no fatiamento horizontal
            if faixa.sobreposicao_superior_m > 0:
                y_eixo = (faixa.altura_m - faixa.sobreposicao_superior_m) * PT_POR_M
                x_esq = 25.0 * PT_POR_MM
                x_dir = faixa_largura_pt - (25.0 * PT_POR_MM)
                adicionar_cruzeta(x_esq, y_eixo)
                adicionar_cruzeta(x_dir, y_eixo)
                if faixa_largura_pt > 1.5 * PT_POR_M:
                    adicionar_cruzeta(faixa_largura_pt / 2.0, y_eixo)

            if faixa.sobreposicao_inferior_m > 0:
                y_eixo = faixa.sobreposicao_inferior_m * PT_POR_M
                x_esq = 25.0 * PT_POR_MM
                x_dir = faixa_largura_pt - (25.0 * PT_POR_MM)
                adicionar_cruzeta(x_esq, y_eixo)
                adicionar_cruzeta(x_dir, y_eixo)
                if faixa_largura_pt > 1.5 * PT_POR_M:
                    adicionar_cruzeta(faixa_largura_pt / 2.0, y_eixo)

        # 6. Identificação técnica no rodapé
        ov_val = plano.sobreposicao_solda_mm
        ov_str = f"OVERLAP {ov_val:.0f}MM" if ov_val.is_integer() else f"OVERLAP {ov_val:.1f}MM"
        sentido_montagem = "[>>> SENTIDO DE MONTAGEM]"

        if total_faixas > 1:
            texto_tecnico = f"FAIXA {faixa.indice:02d} DE {total_faixas:02d} ({ov_str}) - {sentido_montagem}"
        else:
            texto_tecnico = f"FAIXA 01 DE 01 (SEM OVERLAP) - [FAIXA UNICA]"

        corpo_fonte_pt = 9.0
        larg_texto_1pt = largura_texto_helvetica_1pt(texto_tecnico)
        largura_rotulo_pt = (larg_texto_1pt * corpo_fonte_pt) + 16.0
        altura_rotulo_pt = 16.0

        x_rotulo = 12.0 * PT_POR_MM
        y_rotulo = 6.0 * PT_POR_MM

        # Fundo branco com borda fina preta para legibilidade sobre qualquer arte gráfica
        stream_cmds.extend(b"q\n")
        stream_cmds.extend(b"1 1 1 rg 0 0 0 RG 0.5 w\n")
        stream_cmds.extend(
            f"{x_rotulo - 4.0:.2f} {y_rotulo - 3.5:.2f} {largura_rotulo_pt:.2f} {altura_rotulo_pt:.2f} re B\n".encode(
                "ascii"
            )
        )
        stream_cmds.extend(b"0 0 0 rg\n")
        stream_cmds.extend(b"BT\n")
        stream_cmds.extend(f"/F1 {corpo_fonte_pt:.2f} Tf\n".encode("ascii"))
        stream_cmds.extend(f"1 0 0 1 {x_rotulo:.2f} {y_rotulo:.2f} Tm\n".encode("ascii"))
        stream_cmds.extend(f"({sanitizar_texto_ascii(texto_tecnico)}) Tj\n".encode("ascii"))
        stream_cmds.extend(b"ET\n")
        stream_cmds.extend(b"Q\n")

        # 7. Registra os recursos e anexa a página final
        recursos_pagina = {
            PdfName("/XObject"): {
                PdfName("/Fm1"): form_ref,
            },
            PdfName("/Font"): {
                PdfName("/F1"): PdfRef(fonte_id, 0),
            },
        }

        writer.adicionar_pagina(
            largura_pt=faixa_largura_pt,
            altura_pt=faixa_altura_pt,
            recursos=recursos_pagina,
            conteudo_bytes=bytes(stream_cmds),
        )

        writer.salvar(caminho_saida)
        arquivos_gerados.append(caminho_saida)

    return arquivos_gerados


__all__ = [
    "FaixaInfo",
    "PlanoPainelamento",
    "calcular_painelamento",
    "gerar_faixas_pdf",
]
