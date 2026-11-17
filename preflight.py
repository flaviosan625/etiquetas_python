"""
Módulo de Preflight (Auditoria Técnica) de PDFs para Comunicação Visual.

Inspeciona arquivos PDF sem depender do Adobe Acrobat / PitStop:
  1. Resolução efetiva de imagens (DPI real no tamanho final de impressão,
     com compensação de escala 1:10 se aplicável).
  2. Detecção de fontes vivas não convertidas em curvas (risco tipográfico no RIP).
  3. Detecção de espaço de cores (alerta de elementos RGB em fluxos CMYK).
  4. Dimensões de página (MediaBox, TrimBox, BleedBox).

Produz diagnósticos imediatos para avisar o cliente ou o operador antes
da montagem e da gravação na hot folder do RIP.
"""

from __future__ import annotations

import os
import pathlib
import re
from typing import Any, Dict, List, Optional, Tuple

import pymupdf


DPI_MINIMO_PADRAO = 100.0  # Mínimo recomendado para grandes formatos / comunicação visual


def _limpar_nome_fonte(nome_fonte: str) -> str:
    """Remove o prefixo de subset do PDF (ex: 'ABCDEF+Arial' -> 'Arial')."""
    if not nome_fonte:
        return "Desconhecida"
    # Padrão subset PDF: 6 letras maiúsculas seguidas de '+'
    return re.sub(r"^[A-Z]{6}\+", "", nome_fonte)


def inspecionar_pdf(
    caminho: os.PathLike | str,
    dpi_minimo: float = DPI_MINIMO_PADRAO,
    escala_fator: float = 1.0,
) -> Dict[str, Any]:
    """
    Executa auditoria técnica completa (Preflight) em um arquivo PDF.

    Parâmetros:
      caminho: Caminho do arquivo PDF.
      dpi_minimo: Limiar mínimo de DPI aceitável (padrão 100 DPI).
      escala_fator: Fator de ampliação (ex: 10.0 para arte 1:10).

    Retorna:
      Dicionário com status ('OK', 'ALERTA', 'ERRO'), métricas e lista de avisos.
    """
    caminho_p = pathlib.Path(caminho)
    relatorio: Dict[str, Any] = {
        "caminho": str(caminho_p),
        "nome": caminho_p.name,
        "valido": False,
        "total_paginas": 0,
        "status": "ERRO",
        "dpi_minimo_encontrado": None,
        "dpi_recomendado": dpi_minimo,
        "escala_fator": escala_fator,
        "tem_baixa_resolucao": False,
        "tem_fontes_vivas": False,
        "fontes": [],
        "espacos_cor": set(),
        "tem_rgb": False,
        "avisos": [],
        "paginas_detalhes": [],
        "resumo": "",
    }

    if not caminho_p.is_file():
        relatorio["avisos"].append(f"Arquivo não encontrado: {caminho_p}")
        relatorio["resumo"] = "Arquivo não encontrado"
        relatorio["espacos_cor"] = sorted(relatorio["espacos_cor"])
        return relatorio

    try:
        doc = pymupdf.open(str(caminho_p))
    except Exception as e:
        relatorio["avisos"].append(f"Não foi possível abrir o PDF: {e}")
        relatorio["resumo"] = "PDF corrompido ou formato inválido"
        relatorio["espacos_cor"] = sorted(relatorio["espacos_cor"])
        return relatorio

    try:
        relatorio["valido"] = True
        relatorio["total_paginas"] = doc.page_count
        menor_dpi_global: Optional[float] = None
        fontes_encontradas: set[str] = set()
        espacos_cor_encontrados: set[str] = set()
        alerta_dpi = False
        alerta_rgb = False
        alerta_fontes = False

        fator_escala = max(1.0, float(escala_fator or 1.0))

        for idx in range(doc.page_count):
            pagina = doc[idx]
            detalhe_pagina: Dict[str, Any] = {
                "pagina": idx + 1,
                "largura_pt": pagina.rect.width,
                "altura_pt": pagina.rect.height,
                "largura_m": round(pagina.rect.width * 0.0254 / 72.0 * fator_escala, 4),
                "altura_m": round(pagina.rect.height * 0.0254 / 72.0 * fator_escala, 4),
                "imagens": [],
                "fontes": [],
            }

            # 1. Auditoria de Imagens e Resolução Efetiva
            imagens_pagina = pagina.get_images(full=True)
            for img_info in imagens_pagina:
                xref = img_info[0]
                px_w = img_info[2]
                px_h = img_info[3]
                cs = str(img_info[5]) if len(img_info) > 5 else "Desconhecido"

                # Identifica canais e cores via extract_image
                try:
                    img_dict = doc.extract_image(xref)
                    num_canais = img_dict.get("colorspace", 0)
                    nome_cs = str(img_dict.get("cs-name", cs)).upper()
                except Exception:
                    num_canais = 0
                    nome_cs = cs.upper()

                if num_canais == 3 or "RGB" in cs.upper() or "RGB" in nome_cs:
                    espacos_cor_encontrados.add("RGB")
                    alerta_rgb = True
                elif num_canais == 4 or "CMYK" in cs.upper() or "CMYK" in nome_cs:
                    espacos_cor_encontrados.add("CMYK")
                elif num_canais == 1 or "GRAY" in cs.upper() or "GRAY" in nome_cs:
                    espacos_cor_encontrados.add("Grayscale")
                else:
                    espacos_cor_encontrados.add(cs)

                # Dimensões na página (retângulo de exibição)
                rects = pagina.get_image_rects(xref)
                for r in rects:
                    if r.width > 0 and r.height > 0:
                        # DPI bruto na página do PDF
                        dpi_x = (px_w / r.width) * 72.0
                        dpi_y = (px_h / r.height) * 72.0
                        # Se o arquivo está 1:10, o tamanho real impresso será 10x maior,
                        # logo a resolução efetiva cai por fator_escala
                        dpi_efetivo_x = dpi_x / fator_escala
                        dpi_efetivo_y = dpi_y / fator_escala
                        dpi_efetivo = min(dpi_efetivo_x, dpi_efetivo_y)

                        if menor_dpi_global is None or dpi_efetivo < menor_dpi_global:
                            menor_dpi_global = dpi_efetivo

                        detalhe_pagina["imagens"].append({
                            "xref": xref,
                            "largura_px": px_w,
                            "altura_px": px_h,
                            "dpi_efetivo": round(dpi_efetivo, 1),
                            "colorspace": cs,
                        })

                        if dpi_efetivo < dpi_minimo:
                            alerta_dpi = True
                            relatorio["avisos"].append(
                                f"Pág. {idx + 1}: Imagem com resolução baixa ({int(dpi_efetivo)} DPI). "
                                f"Recomendado mínimo de {int(dpi_minimo)} DPI para evitar pixelamento."
                            )

            # 2. Auditoria de Fontes (Texto vivo sem curvas)
            fontes_pg = pagina.get_fonts()
            texto_pg = pagina.get_text().strip()
            if fontes_pg and texto_pg:
                for f_info in fontes_pg:
                    nome_f = _limpar_nome_fonte(f_info[3])
                    fontes_encontradas.add(nome_f)
                    detalhe_pagina["fontes"].append(nome_f)
                alerta_fontes = True

            # 3. Auditoria de Desenhos Vetoriais (Espaço de cores)
            try:
                for desenho in pagina.get_drawings():
                    for tipo_cor in ("stroke", "fill"):
                        c = desenho.get(f"{tipo_cor}_color")
                        if c is not None and isinstance(c, (list, tuple)):
                            if len(c) == 3:
                                espacos_cor_encontrados.add("RGB")
                                alerta_rgb = True
                            elif len(c) == 4:
                                espacos_cor_encontrados.add("CMYK")
                            elif len(c) == 1:
                                espacos_cor_encontrados.add("Grayscale")
            except Exception:
                pass

            relatorio["paginas_detalhes"].append(detalhe_pagina)

        if alerta_fontes and fontes_encontradas:
            lista_f = ", ".join(sorted(fontes_encontradas)[:4])
            relatorio["avisos"].append(
                f"Fontes vivas detectadas ({lista_f}) — recomenda-se converter em curvas para evitar substituição de tipografia no RIP."
            )

        if alerta_rgb:
            relatorio["avisos"].append(
                "Espaço de cores RGB detectado — pode ocorrer variação de tonalidade na impressão CMYK."
            )

        if fator_escala > 1.0:
            relatorio["avisos"].append(
                f"Escala 1:{int(fator_escala)} considerada no cálculo de DPI e medidas reais."
            )

        relatorio["dpi_minimo_encontrado"] = round(menor_dpi_global, 1) if menor_dpi_global is not None else None
        relatorio["tem_baixa_resolucao"] = alerta_dpi
        relatorio["tem_fontes_vivas"] = alerta_fontes
        relatorio["fontes"] = sorted(fontes_encontradas)
        relatorio["espacos_cor"] = sorted(espacos_cor_encontrados) or ["CMYK"]
        relatorio["tem_rgb"] = alerta_rgb

        # Define status final
        if alerta_dpi:
            relatorio["status"] = "ALERTA"
        elif alerta_fontes or alerta_rgb:
            relatorio["status"] = "ALERTA"
        else:
            relatorio["status"] = "OK"

        relatorio["resumo"] = formatar_resumo_curto(relatorio)

    finally:
        doc.close()

    return relatorio


def formatar_resumo_curto(relatorio: Dict[str, Any]) -> str:
    """Gera resumo de uma linha para visualização rápida em tabelas e listas."""
    if not relatorio.get("valido"):
        return f"❌ {relatorio.get('resumo', 'PDF Inválido')}"

    partes = []
    dpi = relatorio.get("dpi_minimo_encontrado")
    if dpi is not None:
        if relatorio.get("tem_baixa_resolucao"):
            partes.append(f"⚠️ {int(dpi)} DPI (Baixo)")
        else:
            partes.append(f"✓ {int(dpi)} DPI")
    else:
        partes.append("✓ 100% Vetor")

    if relatorio.get("tem_rgb"):
        partes.append("⚠️ RGB")
    else:
        partes.append("✓ CMYK")

    if relatorio.get("tem_fontes_vivas"):
        partes.append("⚠️ Fontes Abertas")
    else:
        partes.append("✓ Curvas")

    return " | ".join(partes)


def relatorio_texto_completo(relatorio: Dict[str, Any]) -> str:
    """Gera relatório formatado em texto para visualização pelo operador ou envio ao cliente."""
    linhas = [
        f"=== RELATÓRIO DE PREFLIGHT (AUDITORIA TÉCNICA) ===",
        f"Arquivo: {relatorio.get('nome')}",
        f"Status: {relatorio.get('status')}",
        f"Total de Páginas: {relatorio.get('total_paginas')}",
    ]

    dpi = relatorio.get("dpi_minimo_encontrado")
    if dpi is not None:
        linhas.append(f"Menor Resolução Efetiva: {dpi} DPI (Mínimo: {relatorio.get('dpi_recomendado')} DPI)")
    else:
        linhas.append("Conteúdo: 100% Vetorial")

    espacos = ", ".join(relatorio.get("espacos_cor", [])) or "CMYK"
    linhas.append(f"Espaço de Cores: {espacos}")

    fontes = relatorio.get("fontes", [])
    if fontes:
        linhas.append(f"Fontes Vivas: {', '.join(fontes)}")
    else:
        linhas.append("Fontes: Em curvas / Não detectadas")

    avisos = relatorio.get("avisos", [])
    if avisos:
        linhas.append("\nAlertas Detectados:")
        for a in avisos:
            linhas.append(f"  • {a}")
    else:
        linhas.append("\n✓ Nenhum problema técnico encontrado. Arquivo 100% pronto para o RIP.")

    return "\n".join(linhas)
