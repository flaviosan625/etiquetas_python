"""
Módulo de Acabamento para o Chão de Fábrica da Comunicação Visual.

Gera marcas de acabamento de alta precisão diretamente no PDF da arte ou montagem:
  1. Marcas de Ilhós Automáticas:
     - Pontos de mira (círculo com cruz guia e ponto de agulha central) a cada 30/40/50 cm ou nos cantos.
     - Operadores PDF nativos com curvas de Bézier cúbicas e duplo contraste (halo branco e traço preto).
     - Permite que a equipe de acabamento utilize a prensa pneumática ou manual sem medir na trena.
     - Indicado para LONA, TECIDO (Wind Banner) e BANNERS.
  2. Borda de Solda / Bainha Térmica:
     - Adiciona margem de vira (3 cm a 5 cm) para solda vulcanizada ou tubo de bastão.
     - Centraliza a arte original via Form XObject e desenha linha guia tracejada cinza [3 3] 0 d.
  3. Sangria Espelhada (Mirror Bleed):
     - Expande a folha com sangria milimétrica e espelha as bordas e cantos da arte via Form XObject
       com matriz afim e clipping, eliminando filetes brancos na impressão e corte.
  4. Linha de Corte Digital (CutContour):
     - Contorno vetorial em camada OCG (Optional Content Group) com ColorSpace Separation /CutContour
       mapeado para DeviceCMYK 0 1 0 0 (100% Magenta), reconhecido por plotters (Summa, Mimaki, Roland)
       e mesas de corte CNC / routers.

100% NATIVO: Utiliza exclusivamente o motor interno motor_pdf (sem dependência de PyMuPDF).
"""

from __future__ import annotations

import math
import os
import pathlib
import zlib
from typing import Any, Dict, List, Optional, Tuple, Union

from motor_pdf import (
    Caixa,
    Matriz2D,
    PdfArray,
    PdfDict,
    PdfName,
    PdfReader,
    PdfRef,
    PdfStream,
    PdfString,
    PdfWriter,
    abrir_pdf,
)

PT_POR_M = 72.0 / 0.0254    # ~2834.64567 pontos por metro
PT_POR_MM = 72.0 / 25.4     # ~2.8346 pontos por milímetro
KAPPA = 0.5522847498        # Fator de aproximação de círculo por curva de Bézier cúbica


def _gerar_caminho_circulo_pdf(cx: float, cy: float, r: float) -> str:
    """
    Gera operadores nativos de PDF (m ... c ... h) para um círculo perfeito de raio r centrado em (cx, cy),
    utilizando 4 quadrantes aproximados por curvas de Bézier cúbicas com kappa = 0.5522847498.
    """
    k = r * KAPPA
    return (
        f"{cx + r:.4f} {cy:.4f} m\n"
        f"{cx + r:.4f} {cy + k:.4f} {cx + k:.4f} {cy + r:.4f} {cx:.4f} {cy + r:.4f} c\n"
        f"{cx - k:.4f} {cy + r:.4f} {cx - r:.4f} {cy + k:.4f} {cx - r:.4f} {cy:.4f} c\n"
        f"{cx - r:.4f} {cy - k:.4f} {cx - k:.4f} {cy - r:.4f} {cx:.4f} {cy - r:.4f} c\n"
        f"{cx + k:.4f} {cy - r:.4f} {cx + r:.4f} {cy - k:.4f} {cx + r:.4f} {cy:.4f} c\n"
        f"h\n"
    )


def calcular_posicoes_ilhos(
    largura_pt: float,
    altura_pt: float,
    espacamento_m: float = 0.40,
    recuo_borda_m: float = 0.025,
    cantos_apenas: bool = False,
) -> List[Tuple[float, float]]:
    """
    Calcula as coordenadas (x, y) em pontos dos centros de cada furo de ilhós.

    Parâmetros:
      largura_pt: Largura da página em pontos.
      altura_pt: Altura da página em pontos.
      espacamento_m: Distância aproximada entre ilhoses (ex: 0.40 m = 40 cm).
      recuo_borda_m: Distância da borda ao centro do furo (padrão 2,5 cm).
      cantos_apenas: Se True, gera apenas os 4 cantos.

    Retorna:
      Lista de tuplas (x_pt, y_pt) com as coordenadas de todos os furos.
    """
    recuo_pt = recuo_borda_m * PT_POR_M
    recuo_pt = min(recuo_pt, largura_pt / 4.0, altura_pt / 4.0)

    # 4 Cantos obrigatórios
    cantos = [
        (recuo_pt, recuo_pt),
        (largura_pt - recuo_pt, recuo_pt),
        (largura_pt - recuo_pt, altura_pt - recuo_pt),
        (recuo_pt, altura_pt - recuo_pt),
    ]

    if cantos_apenas or espacamento_m <= 0:
        return cantos

    pontos = []
    w_util_pt = largura_pt - 2 * recuo_pt
    h_util_pt = altura_pt - 2 * recuo_pt

    largura_m = largura_pt / PT_POR_M
    altura_m = altura_pt / PT_POR_M

    # Número de intervalos no topo e na base
    nx = max(1, round(largura_m / espacamento_m))
    step_x = w_util_pt / nx

    # Número de intervalos nas laterais
    ny = max(1, round(altura_m / espacamento_m))
    step_y = h_util_pt / ny

    # Borda Superior
    for i in range(nx):
        pontos.append((recuo_pt + i * step_x, recuo_pt))

    # Borda Direita
    for j in range(ny):
        pontos.append((largura_pt - recuo_pt, recuo_pt + j * step_y))

    # Borda Inferior
    for i in range(nx):
        pontos.append((largura_pt - recuo_pt - i * step_x, altura_pt - recuo_pt))

    # Borda Esquerda
    for j in range(ny):
        pontos.append((recuo_pt, altura_pt - recuo_pt - j * step_y))

    # Remove duplicatas aproximadas preservando a ordem
    finais: List[Tuple[float, float]] = []
    for p in pontos:
        if not any(math.hypot(p[0] - f[0], p[1] - f[1]) < 2.0 for f in finais):
            finais.append((round(p[0], 2), round(p[1], 2)))

    return finais


def gerar_comandos_marca_ilhos(
    x: float,
    y: float,
    diametro_mm: float = 10.0,
    tamanho_mira_mm: float = 4.0,
) -> bytes:
    """
    Gera operadores nativos de PDF (q ... Q) desenhando uma marca de ilhós de alto contraste:
      - Círculos traçados com 4 curvas de Bézier cúbicas (kappa = 0.5522847498).
      - Duplo contraste:
          1. Halo externo branco (stroke 1.8pt) com cruz (+/- tamanho_mira_mm).
          2. Traço interno preto (stroke 0.8pt) com cruz (+/- tamanho_mira_mm).
          3. Ponto de agulha central de 1mm de diâmetro preenchido de branco com contorno preto.
    """
    raio = (diametro_mm / 2.0) * PT_POR_MM
    braco = tamanho_mira_mm * PT_POR_MM
    raio_agulha = (1.0 / 2.0) * PT_POR_MM  # 1mm de diâmetro -> 0.5mm de raio

    cmds = [
        "q",
        "1 J 1 j",  # pontas arredondadas e junções suaves
        # 1. Halo branco externo de contraste (stroke 1.8pt)
        "1 1 1 RG",
        "1.8 w",
        _gerar_caminho_circulo_pdf(x, y, raio).strip(),
        "S",
        f"{x - braco:.4f} {y:.4f} m {x + braco:.4f} {y:.4f} l S",
        f"{x:.4f} {y - braco:.4f} m {x:.4f} {y + braco:.4f} l S",
        # 2. Traçado preto interno (stroke 0.8pt)
        "0 0 0 RG",
        "0.8 w",
        _gerar_caminho_circulo_pdf(x, y, raio).strip(),
        "S",
        f"{x - braco:.4f} {y:.4f} m {x + braco:.4f} {y:.4f} l S",
        f"{x:.4f} {y - braco:.4f} m {x:.4f} {y + braco:.4f} l S",
        # 3. Ponto de agulha central de 1mm de diâmetro (preenchido de branco com contorno preto)
        "1 1 1 rg 0 0 0 RG",
        "0.5 w",
        _gerar_caminho_circulo_pdf(x, y, raio_agulha).strip(),
        "b",
        "Q\n",
    ]
    return "\n".join(cmds).encode("ascii")


def _criar_form_xobject_da_pagina(
    writer: PdfWriter,
    doc: PdfReader,
    pagina: Any,
) -> Tuple[PdfRef, Caixa]:
    """
    Empacota uma página lida como /Subtype /Form XObject dentro do PdfWriter,
    preservando seus recursos originais (imagens, fontes, etc.) e conteúdo compactado.
    """
    caixa = pagina.trimbox if not pagina.trimbox.vazio else pagina.mediabox

    recursos_orig = pagina.raw_dict.get("/Resources") or pagina.raw_dict.get(PdfName("/Resources"))
    recursos_clonados = {}
    if recursos_orig:
        rec_resolvido = doc._resolver_objeto(recursos_orig)
        recursos_clonados = writer.importar_objeto(doc, rec_resolvido) or {}

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
    form_ref = writer.adicionar_objeto(form_stream)
    return form_ref, caixa


def aplicar_marcas_ilhos_pdf(
    caminho_origem: Union[str, os.PathLike],
    caminho_destino: Union[str, os.PathLike],
    espacamento_m: float = 0.40,
    recuo_borda_m: float = 0.025,
    diametro_mm: float = 10.0,
    cantos_apenas: bool = False,
) -> Dict[str, Any]:
    """
    Abre o PDF de origem, estampa marcas de ilhós em todas as páginas e salva no destino via motor_pdf.

    Retorna estatísticas: {origem, destino, total_paginas, total_furos, furos_por_pagina, ...}.
    """
    origem_p = pathlib.Path(caminho_origem)
    destino_p = pathlib.Path(caminho_destino)
    destino_p.parent.mkdir(parents=True, exist_ok=True)

    writer = PdfWriter(versao="1.6")
    total_furos = 0
    furos_por_pagina: List[int] = []

    with abrir_pdf(origem_p) as doc:
        for idx, pagina in enumerate(doc.paginas):
            nome_form = f"/Fm{idx + 1}"
            form_ref, caixa = _criar_form_xobject_da_pagina(writer, doc, pagina)

            w_orig = caixa.width
            h_orig = caixa.height
            tx = -caixa.x0
            ty = -caixa.y0

            posicoes = calcular_posicoes_ilhos(
                w_orig,
                h_orig,
                espacamento_m=espacamento_m,
                recuo_borda_m=recuo_borda_m,
                cantos_apenas=cantos_apenas,
            )

            cmds = bytearray()
            # 1. Desenha a arte original via Form XObject
            cmds.extend(f"q\n1 0 0 1 {tx:.4f} {ty:.4f} cm\n{nome_form} Do\nQ\n".encode("ascii"))

            # 2. Desenha cada marca de ilhós com Béziers cúbicas
            for x, y in posicoes:
                cmds.extend(gerar_comandos_marca_ilhos(x, y, diametro_mm=diametro_mm))

            recursos_pag = {
                PdfName("/XObject"): {
                    PdfName(nome_form): form_ref,
                }
            }

            writer.adicionar_pagina(
                largura_pt=w_orig,
                altura_pt=h_orig,
                recursos=recursos_pag,
                conteudo_bytes=bytes(cmds),
            )

            furos_por_pagina.append(len(posicoes))
            total_furos += len(posicoes)

        writer.salvar(destino_p)

    return {
        "origem": str(origem_p),
        "destino": str(destino_p),
        "total_paginas": len(furos_por_pagina),
        "total_furos": total_furos,
        "furos_por_pagina": furos_por_pagina,
        "espacamento_m": espacamento_m,
        "recuo_borda_m": recuo_borda_m,
    }


def aplicar_borda_solda_pdf(
    caminho_origem: Union[str, os.PathLike],
    caminho_destino: Union[str, os.PathLike],
    borda_solda_m: float = 0.04,  # Padrão 4 cm de vira para solda térmica
    linhas_guia: bool = True,
) -> Dict[str, Any]:
    """
    Expande as dimensões do PDF adicionando a margem de solda/bainha (ex: 4cm de cada lado).
    Centraliza a página original como Form XObject e insere linhas guias pontilhadas [3 3] 0 d
    na linha de dobra para a equipe de acabamento.
    """
    origem_p = pathlib.Path(caminho_origem)
    destino_p = pathlib.Path(caminho_destino)
    destino_p.parent.mkdir(parents=True, exist_ok=True)

    borda_pt = borda_solda_m * PT_POR_M

    writer = PdfWriter(versao="1.6")

    with abrir_pdf(origem_p) as doc:
        for idx, pagina in enumerate(doc.paginas):
            nome_form = f"/Fm{idx + 1}"
            form_ref, caixa = _criar_form_xobject_da_pagina(writer, doc, pagina)

            w_orig = caixa.width
            h_orig = caixa.height

            nova_w = w_orig + 2 * borda_pt
            nova_h = h_orig + 2 * borda_pt

            cmds = bytearray()
            # Encaixa o conteúdo original centralizado com margem borda_pt
            tx = borda_pt - caixa.x0
            ty = borda_pt - caixa.y0
            cmds.extend(f"q\n1 0 0 1 {tx:.4f} {ty:.4f} cm\n{nome_form} Do\nQ\n".encode("ascii"))

            # Linhas guias tracejadas suaves cinza na linha de dobra
            if linhas_guia:
                cmds.extend(b"q\n")
                cmds.extend(b"0.4 0.4 0.4 RG\n")
                cmds.extend(b"0.5 w\n")
                cmds.extend(b"[3 3] 0 d\n")
                cmds.extend(f"{borda_pt:.4f} {borda_pt:.4f} {w_orig:.4f} {h_orig:.4f} re\n".encode("ascii"))
                cmds.extend(b"S\n")
                cmds.extend(b"Q\n")

            recursos_pag = {
                PdfName("/XObject"): {
                    PdfName(nome_form): form_ref,
                }
            }

            writer.adicionar_pagina(
                largura_pt=nova_w,
                altura_pt=nova_h,
                recursos=recursos_pag,
                conteudo_bytes=bytes(cmds),
            )

        qtd_paginas = len(doc.paginas)
        writer.salvar(destino_p)

    return {
        "origem": str(origem_p),
        "destino": str(destino_p),
        "borda_solda_m": borda_solda_m,
        "paginas": qtd_paginas,
    }


def aplicar_sangria_espelhada_pdf(
    caminho_origem: Union[str, os.PathLike],
    caminho_destino: Union[str, os.PathLike],
    sangria_mm: float = 10.0,
) -> Dict[str, Any]:
    """
    Aplica sangria espelhada (Mirror Bleed) expandindo a folha em `sangria_mm` (convertido para pt) em cada lado.
    Posiciona a arte original no centro e, nas 4 margens e 4 cantos, aplica clipping da região de borda
    e renderiza o Form XObject com transformação de escala negativa (-1) e translação correspondente,
    eliminando filetes brancos na impressão e no refile.
    """
    origem_p = pathlib.Path(caminho_origem)
    destino_p = pathlib.Path(caminho_destino)
    destino_p.parent.mkdir(parents=True, exist_ok=True)

    sangria_pt = float(sangria_mm) * PT_POR_MM

    writer = PdfWriter(versao="1.6")
    nova_w = 0.0
    nova_h = 0.0

    with abrir_pdf(origem_p) as doc:
        for idx, pagina in enumerate(doc.paginas):
            nome_form = f"/Fm{idx + 1}"
            form_ref, caixa = _criar_form_xobject_da_pagina(writer, doc, pagina)

            W = caixa.width
            H = caixa.height
            x0 = caixa.x0
            y0 = caixa.y0
            S = sangria_pt

            nova_w = W + 2 * S
            nova_h = H + 2 * S

            cmds = bytearray()

            def _adicionar_bloco(
                clip_x: float,
                clip_y: float,
                clip_w: float,
                clip_h: float,
                a: float,
                b: float,
                c: float,
                d: float,
                e: float,
                f: float,
            ):
                bloco = (
                    f"q\n"
                    f"{clip_x:.4f} {clip_y:.4f} {clip_w:.4f} {clip_h:.4f} re W n\n"
                    f"{a:.6f} {b:.6f} {c:.6f} {d:.6f} {e:.4f} {f:.4f} cm\n"
                    f"{nome_form} Do\n"
                    f"Q\n"
                )
                cmds.extend(bloco.encode("ascii"))

            # 0. Arte Central (original posicionada em (S, S))
            _adicionar_bloco(S, S, W, H, 1.0, 0.0, 0.0, 1.0, S - x0, S - y0)

            # 1. Margem Esquerda (espelhamento horizontal em X = S)
            _adicionar_bloco(0.0, S, S, H, -1.0, 0.0, 0.0, 1.0, S + x0, S - y0)

            # 2. Margem Direita (espelhamento horizontal em X = S + W)
            _adicionar_bloco(S + W, S, S, H, -1.0, 0.0, 0.0, 1.0, S + 2 * W + x0, S - y0)

            # 3. Margem Inferior (espelhamento vertical em Y = S)
            _adicionar_bloco(S, 0.0, W, S, 1.0, 0.0, 0.0, -1.0, S - x0, S + y0)

            # 4. Margem Superior (espelhamento vertical em Y = S + H)
            _adicionar_bloco(S, S + H, W, S, 1.0, 0.0, 0.0, -1.0, S - x0, S + 2 * H + y0)

            # 5. Canto Inferior-Esquerdo (espelhamento duplo em X = S e Y = S)
            _adicionar_bloco(0.0, 0.0, S, S, -1.0, 0.0, 0.0, -1.0, S + x0, S + y0)

            # 6. Canto Inferior-Direito (espelhamento duplo em X = S + W e Y = S)
            _adicionar_bloco(S + W, 0.0, S, S, -1.0, 0.0, 0.0, -1.0, S + 2 * W + x0, S + y0)

            # 7. Canto Superior-Esquerdo (espelhamento duplo em X = S e Y = S + H)
            _adicionar_bloco(0.0, S + H, S, S, -1.0, 0.0, 0.0, -1.0, S + x0, S + 2 * H + y0)

            # 8. Canto Superior-Direito (espelhamento duplo em X = S + W e Y = S + H)
            _adicionar_bloco(S + W, S + H, S, S, -1.0, 0.0, 0.0, -1.0, S + 2 * W + x0, S + 2 * H + y0)

            recursos_pag = {
                PdfName("/XObject"): {
                    PdfName(nome_form): form_ref,
                }
            }

            writer.adicionar_pagina(
                largura_pt=nova_w,
                altura_pt=nova_h,
                recursos=recursos_pag,
                conteudo_bytes=bytes(cmds),
            )

        qtd_paginas = len(doc.paginas)
        writer.salvar(destino_p)

    return {
        "origem": str(origem_p),
        "destino": str(destino_p),
        "sangria_mm": sangria_mm,
        "paginas": qtd_paginas,
        "largura_final_pt": round(nova_w, 2),
        "altura_final_pt": round(nova_h, 2),
    }


def adicionar_camada_cutcontour(
    caminho_origem: Union[str, os.PathLike],
    caminho_destino: Union[str, os.PathLike],
    recuo_pt: float = 0.0,
    spot_color_name: str = "CutContour",
) -> Dict[str, Any]:
    """
    Adiciona a camada vetorial CutContour com:
      - ColorSpace Separation /CutContour mapeado para DeviceCMYK 0 1 0 0 (100% Magenta).
      - Optional Content Group /OCG /Name (CutContour) registrado no Catálogo (/OCProperties).
      - Traçado retangular com operadores /OC /OC1 BDC ... /CS_Cut CS 1.0 SCN ... EMC.
    """
    origem_p = pathlib.Path(caminho_origem)
    destino_p = pathlib.Path(caminho_destino)
    destino_p.parent.mkdir(parents=True, exist_ok=True)

    writer = PdfWriter(versao="1.6")

    # 1. Configura o OCG (Optional Content Group) para a camada CutContour
    ocg_id = writer.alocar_id()
    ocg_dict = {
        PdfName("/Type"): PdfName("/OCG"),
        PdfName("/Name"): PdfString(spot_color_name.encode("utf-8")),
    }
    writer.objetos[ocg_id] = ocg_dict
    ocg_ref = PdfRef(ocg_id, 0)

    # Registra no Catálogo /OCProperties
    cat_obj = writer.objetos.setdefault(writer.catalogo_id, {})
    cat_obj[PdfName("/OCProperties")] = {
        PdfName("/OCGs"): [ocg_ref],
        PdfName("/D"): {
            PdfName("/Order"): [ocg_ref],
            PdfName("/ON"): [ocg_ref],
        },
    }

    # 2. Configura a Separation ColorSpace para a cor Spot CutContour (100% Magenta)
    func_dict = {
        PdfName("/FunctionType"): 2,
        PdfName("/Domain"): [0.0, 1.0],
        PdfName("/Range"): [0.0, 1.0, 0.0, 1.0, 0.0, 1.0, 0.0, 1.0],
        PdfName("/C0"): [0.0, 0.0, 0.0, 0.0],
        PdfName("/C1"): [0.0, 1.0, 0.0, 0.0],
        PdfName("/N"): 1.0,
    }
    cs_separation = [
        PdfName("/Separation"),
        PdfName(f"/{spot_color_name}"),
        PdfName("/DeviceCMYK"),
        func_dict,
    ]

    with abrir_pdf(origem_p) as doc:
        for idx, pagina in enumerate(doc.paginas):
            nome_form = f"/Fm{idx + 1}"
            form_ref, caixa = _criar_form_xobject_da_pagina(writer, doc, pagina)

            w_orig = caixa.width
            h_orig = caixa.height
            tx = -caixa.x0
            ty = -caixa.y0

            cmds = bytearray()
            # 1. Arte original como Form XObject
            cmds.extend(f"q\n1 0 0 1 {tx:.4f} {ty:.4f} cm\n{nome_form} Do\nQ\n".encode("ascii"))

            # 2. Camada CutContour demarcada com OCG e traço Separation
            x_corte = recuo_pt
            y_corte = recuo_pt
            w_corte = w_orig - 2 * recuo_pt
            h_corte = h_orig - 2 * recuo_pt

            cmds.extend(b"/OC /OC1 BDC\n")
            cmds.extend(b"q\n")
            cmds.extend(b"/CS_Cut CS\n")
            cmds.extend(b"1.0 SCN\n")
            cmds.extend(b"1.0 w\n")
            cmds.extend(f"{x_corte:.4f} {y_corte:.4f} {w_corte:.4f} {h_corte:.4f} re\n".encode("ascii"))
            cmds.extend(b"S\n")
            cmds.extend(b"Q\n")
            cmds.extend(b"EMC\n")

            recursos_pag = {
                PdfName("/XObject"): {
                    PdfName(nome_form): form_ref,
                },
                PdfName("/ColorSpace"): {
                    PdfName("/CS_Cut"): cs_separation,
                },
                PdfName("/Properties"): {
                    PdfName("/OC1"): ocg_ref,
                },
            }

            writer.adicionar_pagina(
                largura_pt=w_orig,
                altura_pt=h_orig,
                recursos=recursos_pag,
                conteudo_bytes=bytes(cmds),
            )

        qtd_paginas = len(doc.paginas)
        writer.salvar(destino_p)

    return {
        "origem": str(origem_p),
        "destino": str(destino_p),
        "spot_color_name": spot_color_name,
        "recuo_pt": recuo_pt,
        "paginas": qtd_paginas,
    }


# =========================================================================
# Wrappers de Compatibilidade com o ecossistema legado
# =========================================================================

def desenhar_marca_ilhos(
    pagina: Any,
    x: float,
    y: float,
    diametro_mm: float = 10.0,
    tamanho_mira_mm: float = 4.0,
):
    """
    Wrapper de compatibilidade para desenhar marca de ilhós em páginas com interface de desenho (duck typing).
    """
    if hasattr(pagina, "draw_circle") and hasattr(pagina, "draw_line"):
        raio = (diametro_mm / 2.0) * PT_POR_MM
        braco = (tamanho_mira_mm / 2.0) * PT_POR_MM

        ponto = (x, y)
        p1 = (x - braco, y)
        p2 = (x + braco, y)
        p3 = (x, y - braco)
        p4 = (x, y + braco)

        # 1. Halo branco
        pagina.draw_circle(ponto, raio, color=(1, 1, 1), width=1.8)
        pagina.draw_line(p1, p2, color=(1, 1, 1), width=1.8)
        pagina.draw_line(p3, p4, color=(1, 1, 1), width=1.8)

        # 2. Linha interna escura
        pagina.draw_circle(ponto, raio, color=(0, 0, 0), width=0.8)
        pagina.draw_line(p1, p2, color=(0, 0, 0), width=0.8)
        pagina.draw_line(p3, p4, color=(0, 0, 0), width=0.8)

        # 3. Ponto de agulha
        pagina.draw_circle(ponto, 0.5 * PT_POR_MM, color=(0, 0, 0), fill=(1, 1, 1), width=0.5)


def desenhar_ilhos_na_caixa(
    pagina: Any,
    caixa_pt: Any,
    espacamento_m: float = 0.40,
    recuo_borda_m: float = 0.025,
    diametro_mm: float = 10.0,
    cantos_apenas: bool = False,
):
    """
    Desenha marcas de ilhós dentro de uma caixa retangular específica da página (ex: peça em folha montada).
    """
    w = getattr(caixa_pt, "width", None)
    if w is None:
        w = float(caixa_pt[2] - caixa_pt[0])
    h = getattr(caixa_pt, "height", None)
    if h is None:
        h = float(caixa_pt[3] - caixa_pt[1])
    x0 = getattr(caixa_pt, "x0", None)
    if x0 is None:
        x0 = float(caixa_pt[0])
    y0 = getattr(caixa_pt, "y0", None)
    if y0 is None:
        y0 = float(caixa_pt[1])

    posicoes_relativas = calcular_posicoes_ilhos(
        w,
        h,
        espacamento_m=espacamento_m,
        recuo_borda_m=recuo_borda_m,
        cantos_apenas=cantos_apenas,
    )
    for rx, ry in posicoes_relativas:
        desenhar_marca_ilhos(
            pagina,
            x0 + rx,
            y0 + ry,
            diametro_mm=diametro_mm,
        )


def adicionar_linha_cutcontour(
    pagina: Any,
    recuo_pt: float = 0.0,
    cor_magenta_cmyk: Tuple[float, float, float, float] = (0.0, 1.0, 0.0, 0.0),
    largura_linha_pt: float = 1.0,
):
    """
    Desenha um contorno vetorial de corte ao redor da página/área de corte.
    Compatível com chamadas de montagem legada (duck typing).
    """
    if hasattr(pagina, "draw_rect") and hasattr(pagina, "rect"):
        ret = pagina.rect
        if recuo_pt != 0.0:
            try:
                ret = type(ret)(
                    ret.x0 + recuo_pt,
                    ret.y0 + recuo_pt,
                    ret.x1 - recuo_pt,
                    ret.y1 - recuo_pt,
                )
            except Exception:
                pass
        pagina.draw_rect(ret, color=cor_magenta_cmyk, width=largura_linha_pt)


__all__ = [
    "PT_POR_M",
    "PT_POR_MM",
    "KAPPA",
    "calcular_posicoes_ilhos",
    "gerar_comandos_marca_ilhos",
    "aplicar_marcas_ilhos_pdf",
    "aplicar_borda_solda_pdf",
    "aplicar_sangria_espelhada_pdf",
    "adicionar_camada_cutcontour",
    "desenhar_marca_ilhos",
    "desenhar_ilhos_na_caixa",
    "adicionar_linha_cutcontour",
]
