"""
corte_dxf.py — Extração de linhas de corte vetoriais de PDF e exportação para DXF.

Compatibilidade total com:
  - Mesas de corte digitais (Zünd, Kongsberg, iEcho, Summa).
  - Fresas CNC e roteadores (CNC CAM, Aspire, Vectric, ArtCAM).

Regras de chão de fábrica (2026-09-06):
  - O PDF original NUNCA é tocado nem reescrito. O DXF é arquivo novo.
  - A linha de corte é detectada via:
      a) CMYK Magenta puro (0 1 0 0 k/K ou M predominante).
      b) Spot Color (/CutContour, /Separation/CutContour, CORTE, RECORTE).
      c) RGB Magenta (1 0 1 rg/RG ou matiz na faixa calibrada 300°-350°).
      d) Camada OCG nomeada CutContour, CORTE ou RECORTE.
  - Imagens são descartadas (apenas vetor vira corte). O relatório avisa se existiam.
  - O DXF é gerado no dialeto R12 ASCII em milímetros (1:1), com classificação
    de aninhamento ("dentro por dentro e fora por fora") em CORTE EXTERNO e
    CORTE INTERNO.

100% autônomo com o motor nativo 'motor_pdf' (sem dependência obrigatória de PyMuPDF).
"""

from __future__ import annotations

import colorsys
import math
import os
import pathlib
import unicodedata
from typing import Any, Dict, List, Optional, Set, Tuple, Union

import motor_pdf
from motor_pdf.geometria import Matriz2D
from motor_pdf.interpretador_stream import PADRAO_TOKEN_STREAM
from motor_pdf.leitor import Pagina, PdfReader
from motor_pdf.sintaxe import PdfName, PdfRef, PdfString

try:
    import pymupdf
except ImportError:
    pymupdf = None

# Faixa calibrada para RGB Magenta medido em arquivos reais de corte (2026-09-06):
#   - Contornos reais aparecem entre 329° e 336°, saturação 0,71 a 0,79.
#   - CMYK puro cai em 324° (RGB 1, 0, 1 = 300°).
#   - Preto com matiz residual (0.137, 0.122, 0.125) calcula 346°, mas saturação 0,11 (rejeitado).
#   - Vermelho de letra-caixa cai em 357° (rejeitado por MATIZ_MAX=350.0).
MATIZ_MIN, MATIZ_MAX = 300.0, 350.0
SATURACAO_MIN = 0.35
VALOR_MIN = 0.30

# Erro máximo ao transformar curva de Bézier em segmentos de reta.
# 0,05 mm é menos que a folga da própria fresa ou lâmina oscilante.
TOLERANCIA_MM = 0.05

_PT_PARA_MM = 25.4 / 72.0
NOME_CAMADA = "CORTE"
CAMADA_EXTERNO = "CORTE EXTERNO"
CAMADA_INTERNO = "CORTE INTERNO"

# Como o arquivo chegou, na ordem de quanto exige do usuário:
PRONTO = "pronto"          # camada nomeada: o arquivo diz qual é o corte
CONFERIR = "conferir"      # sem camada, achou magenta: provavelmente certo
PARADO = "parado"          # não dá pra converter, e o motivo está dito


def e_spot_de_corte(nome: Optional[Union[str, bytes]]) -> bool:
    """
    True se o nome de uma tinta especial (Spot Color) representa contorno de corte.

    Padrões da indústria gráfica:
      - /CutContour, CutContour, Cut_Contour (Summa, Mimaki, Roland, Zünd)
      - /Separation/CutContour
      - CORTE, RECORTE, Thru-cut, Kiss-cut
    """
    if not nome:
        return False
    if isinstance(nome, bytes):
        nome = nome.decode("latin1", errors="ignore")
    limpo = unicodedata.normalize("NFKD", str(nome)).encode("ascii", "ignore").decode().upper()
    limpo = limpo.replace("/", "").replace("_", "").replace("-", "").replace(" ", "")
    return (
        "CUTCONTOUR" in limpo
        or "CORTE" in limpo
        or "RECORTE" in limpo
        or "THRUCUT" in limpo
        or "KISSCUT" in limpo
    )


def e_cor_de_corte(cor, spot_nome: Optional[Union[str, bytes]] = None) -> bool:
    """
    True se esta cor ou spot color é o marcador de contorno de corte.

    Detecta:
      a) CMYK Magenta puro (0 1 0 0 k/K ou similar com M predominante).
      b) Spot Color (/CutContour, /Separation/CutContour, CORTE, RECORTE).
      c) RGB Magenta (1 0 1 rg/RG ou matiz na faixa 300°-350° com saturação e valor mínimos).
    """
    if isinstance(cor, (str, bytes)):
        return e_spot_de_corte(cor)

    if spot_nome and e_spot_de_corte(spot_nome):
        return True

    if not cor or not isinstance(cor, (tuple, list)):
        return False

    # CMYK (4 componentes de 0.0 a 1.0)
    if len(cor) == 4:
        c, m, y, k = (float(v) for v in cor)
        # Magenta puro ou dominante: M alto e C/Y/K baixos
        if m >= 0.70 and c <= 0.15 and y <= 0.15 and k <= 0.20:
            return True
        # Converte CMYK para RGB aproximado e avalia HSV
        r = (1.0 - c) * (1.0 - k)
        g = (1.0 - m) * (1.0 - k)
        b = (1.0 - y) * (1.0 - k)
        cor = (r, g, b)

    # RGB (3 componentes de 0.0 a 1.0)
    if len(cor) == 3:
        r, g, b = (float(v) for v in cor)
        # Magenta puro (1, 0, 1)
        if r >= 0.85 and g <= 0.15 and b >= 0.85:
            return True
        matiz, saturacao, valor = colorsys.rgb_to_hsv(r, g, b)
        return (
            MATIZ_MIN <= matiz * 360.0 <= MATIZ_MAX
            and saturacao >= SATURACAO_MIN
            and valor >= VALOR_MIN
        )

    return False


def e_camada_de_corte(nome) -> bool:
    """
    True se o nome desta camada (OCG) marca a linha de corte.

    Aceita 'CORTE', 'RECORTE', 'CutContour', 'Cut Contour', 'CUT_CONTOUR', etc.
    """
    if not nome:
        return False
    if isinstance(nome, bytes):
        nome = nome.decode("latin1", errors="ignore")
    limpo = unicodedata.normalize("NFKD", str(nome)).encode("ascii", "ignore").decode().upper()
    limpo_sem_espaco = limpo.replace(" ", "").replace("_", "").replace("-", "")
    return "CORTE" in limpo or "CUTCONTOUR" in limpo_sem_espaco


def _passos_da_curva(p0, p1, p2, p3, tolerancia_pt):
    """
    Quantos segmentos usar pra achatar esta Bézier.
    Estima pelo perímetro do polígono de controle.
    """
    perimetro = sum(math.dist(a, b) for a, b in ((p0, p1), (p1, p2), (p2, p3)))
    if perimetro <= 0:
        return 1
    return max(2, min(128, math.ceil(math.sqrt(perimetro / max(tolerancia_pt, 1e-6)))))


def _achatar_curva(p0, p1, p2, p3, tolerancia_pt):
    """Pontos da Bézier cúbica, sem repetir o ponto inicial."""
    n = _passos_da_curva(p0, p1, p2, p3, tolerancia_pt)
    pontos = []
    for i in range(1, n + 1):
        t = i / n
        u = 1.0 - t
        x = (u * u * u * p0[0] + 3 * u * u * t * p1[0]
             + 3 * u * t * t * p2[0] + t * t * t * p3[0])
        y = (u * u * u * p0[1] + 3 * u * u * t * p1[1]
             + 3 * u * t * t * p2[1] + t * t * t * p3[1])
        pontos.append((x, y))
    return pontos


def _mesmo_ponto(a, b, folga=1e-5):
    return a is not None and b is not None and math.dist(a, b) <= folga


def _polilinhas_do_desenho(desenho, tolerancia_pt):
    """
    Quebra os itens de um desenho em polilinhas contínuas.
    Preserva retas e achata curvas cúbicas de Bézier com tolerância geométrica.
    """
    polilinhas = []
    atual = []

    def fechar():
        if len(atual) >= 2:
            polilinhas.append(list(atual))
        atual.clear()

    for item in desenho.get("items", []):
        tipo = item[0]
        if tipo == "l":
            p1, p2 = tuple(item[1]), tuple(item[2])
            if not atual or not _mesmo_ponto(atual[-1], p1):
                fechar()
                atual.append(p1)
            atual.append(p2)
        elif tipo == "c":
            p0, p1, p2, p3 = (tuple(item[i]) for i in range(1, 5))
            if not atual or not _mesmo_ponto(atual[-1], p0):
                fechar()
                atual.append(p0)
            atual.extend(_achatar_curva(p0, p1, p2, p3, tolerancia_pt))
        elif tipo in ("re", "qu"):
            fechar()
            if tipo == "re":
                r = item[1]
                if hasattr(r, "x0"):
                    cantos = [(r.x0, r.y0), (r.x1, r.y0), (r.x1, r.y1), (r.x0, r.y1)]
                elif isinstance(r, (list, tuple)) and len(r) >= 4:
                    if isinstance(r[0], (tuple, list)):
                        cantos = [tuple(p) for p in r[:4]]
                    else:
                        cantos = [
                            (r[0], r[1]),
                            (r[0] + r[2], r[1]),
                            (r[0] + r[2], r[1] + r[3]),
                            (r[0], r[1] + r[3]),
                        ]
                else:
                    cantos = []
            else:
                q = item[1]
                cantos = [tuple(q.ul), tuple(q.ur), tuple(q.lr), tuple(q.ll)]
            if cantos:
                polilinhas.append(cantos + [cantos[0]])
    fechar()
    return polilinhas


def _mascaras_suspeitas(pagina):
    """
    Máscaras de recorte com forma complexa — candidatas a serem contorno
    de corte que perdeu a cor ao virar máscara no Illustrator.
    Compatibilidade com objetos de página PyMuPDF.
    """
    achadas = []
    if hasattr(pagina, "get_drawings"):
        for desenho in pagina.get_drawings(extended=True):
            if desenho.get("type") != "clip":
                continue
            itens = len(desenho.get("items", []))
            if itens > 4:
                achadas.append(itens)
    return achadas


class _EstadoGraficoCorte:
    """Estado gráfico ativo do interpretador nativo de fluxos de corte."""
    __slots__ = ("ctm", "cor_traco", "cor_preenchimento", "spot_traco", "spot_preenchimento", "camada")

    def __init__(
        self,
        ctm: Optional[Matriz2D] = None,
        cor_traco: Optional[Tuple[float, ...]] = None,
        cor_preenchimento: Optional[Tuple[float, ...]] = None,
        spot_traco: Optional[str] = None,
        spot_preenchimento: Optional[str] = None,
        camada: Optional[str] = None,
    ):
        self.ctm = ctm if ctm is not None else Matriz2D.identidade()
        self.cor_traco = cor_traco
        self.cor_preenchimento = cor_preenchimento
        self.spot_traco = spot_traco
        self.spot_preenchimento = spot_preenchimento
        self.camada = camada

    def clonar(self) -> "_EstadoGraficoCorte":
        return _EstadoGraficoCorte(
            ctm=Matriz2D(self.ctm.a, self.ctm.b, self.ctm.c, self.ctm.d, self.ctm.e, self.ctm.f),
            cor_traco=self.cor_traco,
            cor_preenchimento=self.cor_preenchimento,
            spot_traco=self.spot_traco,
            spot_preenchimento=self.spot_preenchimento,
            camada=self.camada,
        )


class ExtratorVetoresNativo:
    """
    Interpreta os operadores vetoriais de página PDF (ISO 32000-1) e extrai
    caminhos, cores (RGB, CMYK, Spot Color) e camadas OCG de forma nativa.
    """

    def __init__(self, pagina: Pagina, doc: PdfReader):
        self.pagina = pagina
        self.doc = doc
        self.recursos = self._obter_recursos_pagina()
        self.mapa_spots = self._carregar_mapa_spots()
        self.mapa_camadas = self._carregar_mapa_camadas()

        self.desenhos: List[Dict[str, Any]] = []
        self.mascaras_suspeitas: List[int] = []
        self.camadas_encontradas: Set[str] = set()

    def _obter_recursos_pagina(self) -> dict:
        rec = self.pagina.raw_dict.get("/Resources") or self.pagina.raw_dict.get(PdfName("/Resources"))
        if rec and self.doc:
            obj = self.doc._resolver_objeto(rec)
            return obj if isinstance(obj, dict) else {}
        return {}

    def _carregar_mapa_spots(self) -> Dict[str, str]:
        mapa = {}
        cs_dict = self.recursos.get("/ColorSpace") or self.recursos.get(PdfName("/ColorSpace"))
        if cs_dict and self.doc:
            cs_dict = self.doc._resolver_objeto(cs_dict)
        if isinstance(cs_dict, dict):
            for k, ref in cs_dict.items():
                cs_obj = self.doc._resolver_objeto(ref)
                if isinstance(cs_obj, list) and len(cs_obj) >= 2:
                    tipo = str(cs_obj[0]).lstrip("/")
                    spot_nome = str(cs_obj[1]).lstrip("/")
                    if tipo.lower() in ("separation", "devicen"):
                        mapa[str(k)] = spot_nome
                        if not str(k).startswith("/"):
                            mapa["/" + str(k)] = spot_nome
        return mapa

    def _carregar_mapa_camadas(self) -> Dict[str, str]:
        mapa = {}
        # 1. /Properties da página
        props = self.recursos.get("/Properties") or self.recursos.get(PdfName("/Properties"))
        if props and self.doc:
            props = self.doc._resolver_objeto(props)
        if isinstance(props, dict):
            for k, ref in props.items():
                obj = self.doc._resolver_objeto(ref)
                if isinstance(obj, dict):
                    nome = obj.get("/Name") or obj.get(PdfName("/Name"))
                    if nome:
                        val = self.doc._resolver_objeto(nome)
                        if isinstance(val, (bytes, bytearray)):
                            val = val.decode("latin1", errors="ignore")
                        mapa[str(k)] = str(val)
                        if not str(k).startswith("/"):
                            mapa["/" + str(k)] = str(val)

        # 2. /OCProperties do documento
        root = self.doc._resolver_objeto(self.doc.trailer.get("/Root"))
        if isinstance(root, dict):
            oc_props = self.doc._resolver_objeto(root.get("/OCProperties") or root.get(PdfName("/OCProperties")))
            if isinstance(oc_props, dict):
                ocgs = self.doc._resolver_objeto(oc_props.get("/OCGs") or oc_props.get(PdfName("/OCGs")))
                if isinstance(ocgs, list):
                    for ref in ocgs:
                        obj = self.doc._resolver_objeto(ref)
                        if isinstance(obj, dict):
                            nome = obj.get("/Name") or obj.get(PdfName("/Name"))
                            if nome:
                                val = self.doc._resolver_objeto(nome)
                                if isinstance(val, (bytes, bytearray)):
                                    val = val.decode("latin1", errors="ignore")
                                mapa[str(val)] = str(val)
        return mapa

    def extrair(self) -> Tuple[List[Dict[str, Any]], List[int], List[str]]:
        stream_bytes = self.pagina.obter_conteudo_bruto()
        if not stream_bytes:
            return [], [], []

        self._processar_stream(stream_bytes, ctm_inicial=Matriz2D.identidade())
        return self.desenhos, self.mascaras_suspeitas, sorted(self.camadas_encontradas)

    def _processar_stream(self, stream_bytes: bytes, ctm_inicial: Matriz2D, profundidade: int = 0):
        tokens = PADRAO_TOKEN_STREAM.findall(stream_bytes)
        if not tokens:
            return

        estado = _EstadoGraficoCorte(ctm=ctm_inicial)
        pilha_estados: List[_EstadoGraficoCorte] = []
        pilha_op: List[Any] = []
        pilha_camadas: List[str] = []

        cur_x, cur_y = 0.0, 0.0
        start_x, start_y = 0.0, 0.0
        path_items: List[Tuple[Any, ...]] = []
        clip_pendente = False

        def _pop_numeros(n: int) -> List[float]:
            nums = []
            while pilha_op and len(nums) < n:
                v = pilha_op.pop()
                if isinstance(v, (int, float)):
                    nums.append(float(v))
                else:
                    nums.append(0.0)
            nums.reverse()
            while len(nums) < n:
                nums.insert(0, 0.0)
            return nums

        def _pop_arg() -> Any:
            return pilha_op.pop() if pilha_op else None

        idx = 0
        total = len(tokens)

        while idx < total:
            tok = tokens[idx]
            idx += 1

            if tok.startswith(b"%"):
                continue

            if tok.startswith(b"/"):
                nome_str = tok.decode("latin1", errors="ignore")
                pilha_op.append(nome_str)
                continue

            if tok.startswith(b"(") or tok.startswith(b"<"):
                pilha_op.append(tok)
                continue

            if tok in (b"[", b"]", b"<<", b">>"):
                continue

            c = tok[0]
            if (0x30 <= c <= 0x39) or c in (0x2D, 0x2B, 0x2E):
                try:
                    val = float(tok)
                    pilha_op.append(val)
                    continue
                except ValueError:
                    pass

            op = tok.decode("latin1", errors="ignore")

            # ---- 1. Estado Gráfico e Matriz ----
            if op == "q":
                pilha_estados.append(estado.clonar())
            elif op == "Q":
                if pilha_estados:
                    estado = pilha_estados.pop()
            elif op == "cm":
                a, b, c, d, e, f = _pop_numeros(6)
                m_nova = Matriz2D(a, b, c, d, e, f)
                estado.ctm = m_nova.multiplicar(estado.ctm)

            # ---- 2. Construção de Caminho ----
            elif op == "m":
                x, y = _pop_numeros(2)
                px, py = estado.ctm.transformar_ponto(x, y)
                cur_x, cur_y = px, py
                start_x, start_y = px, py
            elif op == "l":
                x, y = _pop_numeros(2)
                px, py = estado.ctm.transformar_ponto(x, y)
                path_items.append(("l", (cur_x, cur_y), (px, py)))
                cur_x, cur_y = px, py
            elif op == "c":
                x1, y1, x2, y2, x3, y3 = _pop_numeros(6)
                p0 = (cur_x, cur_y)
                p1 = estado.ctm.transformar_ponto(x1, y1)
                p2 = estado.ctm.transformar_ponto(x2, y2)
                p3 = estado.ctm.transformar_ponto(x3, y3)
                path_items.append(("c", p0, p1, p2, p3))
                cur_x, cur_y = p3
            elif op == "v":
                x2, y2, x3, y3 = _pop_numeros(4)
                p0 = (cur_x, cur_y)
                p1 = (cur_x, cur_y)
                p2 = estado.ctm.transformar_ponto(x2, y2)
                p3 = estado.ctm.transformar_ponto(x3, y3)
                path_items.append(("c", p0, p1, p2, p3))
                cur_x, cur_y = p3
            elif op == "y":
                x1, y1, x3, y3 = _pop_numeros(4)
                p0 = (cur_x, cur_y)
                p1 = estado.ctm.transformar_ponto(x1, y1)
                p2 = estado.ctm.transformar_ponto(x3, y3)
                p3 = estado.ctm.transformar_ponto(x3, y3)
                path_items.append(("c", p0, p1, p2, p3))
                cur_x, cur_y = p3
            elif op == "h":
                if not _mesmo_ponto((cur_x, cur_y), (start_x, start_y)):
                    path_items.append(("l", (cur_x, cur_y), (start_x, start_y)))
                cur_x, cur_y = start_x, start_y
            elif op == "re":
                x, y, w, h = _pop_numeros(4)
                p1 = estado.ctm.transformar_ponto(x, y)
                p2 = estado.ctm.transformar_ponto(x + w, y)
                p3 = estado.ctm.transformar_ponto(x + w, y + h)
                p4 = estado.ctm.transformar_ponto(x, y + h)
                path_items.append(("re", [p1, p2, p3, p4, p1]))
                cur_x, cur_y = start_x, start_y = p1

            # ---- 3. Máscara de Recorte ----
            elif op in ("W", "W*"):
                clip_pendente = True

            # ---- 4. Pintura e Finalização de Caminho ----
            elif op in ("S", "s", "f", "F", "f*", "B", "b", "B*", "b*"):
                if op in ("s", "b", "b*") and not _mesmo_ponto((cur_x, cur_y), (start_x, start_y)):
                    path_items.append(("l", (cur_x, cur_y), (start_x, start_y)))
                    cur_x, cur_y = start_x, start_y

                tem_traco = op in ("S", "s", "B", "b", "B*", "b*")
                tem_preenchimento = op in ("f", "F", "f*", "B", "b", "B*", "b*")

                if path_items:
                    self.desenhos.append({
                        "type": "fs" if (tem_traco and tem_preenchimento) else ("s" if tem_traco else "f"),
                        "color": estado.cor_traco if tem_traco else None,
                        "fill": estado.cor_preenchimento if tem_preenchimento else None,
                        "stroke_spot": estado.spot_traco if tem_traco else None,
                        "fill_spot": estado.spot_preenchimento if tem_preenchimento else None,
                        "layer": estado.camada,
                        "items": list(path_items),
                    })
                    path_items.clear()
                clip_pendente = False

            elif op == "n":
                if clip_pendente:
                    n_itens = len(path_items)
                    if n_itens > 4:
                        self.mascaras_suspeitas.append(n_itens)
                path_items.clear()
                clip_pendente = False

            # ---- 5. Cores e Espaços de Cor ----
            elif op == "G":
                g_val = _pop_numeros(1)[0]
                estado.cor_traco = (g_val, g_val, g_val)
                estado.spot_traco = None
            elif op == "g":
                g_val = _pop_numeros(1)[0]
                estado.cor_preenchimento = (g_val, g_val, g_val)
                estado.spot_preenchimento = None
            elif op == "RG":
                estado.cor_traco = tuple(_pop_numeros(3))
                estado.spot_traco = None
            elif op == "rg":
                estado.cor_preenchimento = tuple(_pop_numeros(3))
                estado.spot_preenchimento = None
            elif op == "K":
                estado.cor_traco = tuple(_pop_numeros(4))
                estado.spot_traco = None
            elif op == "k":
                estado.cor_preenchimento = tuple(_pop_numeros(4))
                estado.spot_preenchimento = None

            elif op == "CS":
                nome_cs = str(_pop_arg() or "")
                spot = self.mapa_spots.get(nome_cs) or (nome_cs if e_spot_de_corte(nome_cs) else None)
                estado.spot_traco = spot
            elif op == "cs":
                nome_cs = str(_pop_arg() or "")
                spot = self.mapa_spots.get(nome_cs) or (nome_cs if e_spot_de_corte(nome_cs) else None)
                estado.spot_preenchimento = spot

            elif op in ("SC", "SCN"):
                if estado.spot_traco:
                    _pop_numeros(1)
                else:
                    if len(pilha_op) >= 4 and all(isinstance(x, (int, float)) for x in pilha_op[-4:]):
                        estado.cor_traco = tuple(_pop_numeros(4))
                    elif len(pilha_op) >= 3 and all(isinstance(x, (int, float)) for x in pilha_op[-3:]):
                        estado.cor_traco = tuple(_pop_numeros(3))
                    else:
                        pilha_op.clear()

            elif op in ("sc", "scn"):
                if estado.spot_preenchimento:
                    _pop_numeros(1)
                else:
                    if len(pilha_op) >= 4 and all(isinstance(x, (int, float)) for x in pilha_op[-4:]):
                        estado.cor_preenchimento = tuple(_pop_numeros(4))
                    elif len(pilha_op) >= 3 and all(isinstance(x, (int, float)) for x in pilha_op[-3:]):
                        estado.cor_preenchimento = tuple(_pop_numeros(3))
                    else:
                        pilha_op.clear()

            # ---- 6. Camadas (OCG / Marked Content) ----
            elif op == "BMC":
                tag = str(_pop_arg() or "")
                nome_camada = tag.lstrip("/")
                pilha_camadas.append(nome_camada)
                estado.camada = nome_camada
                self.camadas_encontradas.add(nome_camada)

            elif op == "BDC":
                prop = _pop_arg()
                tag = str(_pop_arg() or "")
                nome_camada = None
                if prop:
                    nome_camada = self.mapa_camadas.get(str(prop))
                if not nome_camada:
                    nome_camada = tag.lstrip("/")
                pilha_camadas.append(nome_camada)
                estado.camada = nome_camada
                self.camadas_encontradas.add(nome_camada)

            elif op == "EMC":
                if pilha_camadas:
                    pilha_camadas.pop()
                estado.camada = pilha_camadas[-1] if pilha_camadas else None

            # ---- 7. Objetos Externos (Do) ----
            elif op == "Do":
                nome_obj = str(_pop_arg() or "")
                if self.recursos and profundidade < 10 and self.doc:
                    xobjs = self.recursos.get("/XObject") or self.recursos.get(PdfName("/XObject"))
                    if isinstance(xobjs, PdfRef):
                        xobjs = self.doc._resolver_objeto(xobjs)
                    if isinstance(xobjs, dict):
                        ref_x = xobjs.get(nome_obj) or xobjs.get(PdfName(nome_obj))
                        xobj = self.doc._resolver_objeto(ref_x)
                        if isinstance(xobj, motor_pdf.sintaxe.PdfStream):
                            hdr = xobj.header
                            subtype = str(hdr.get("/Subtype") or hdr.get(PdfName("/Subtype")) or "")
                            if subtype in ("/Form", "Form"):
                                m_form = Matriz2D.identidade()
                                m_arr = hdr.get("/Matrix") or hdr.get(PdfName("/Matrix"))
                                if m_arr:
                                    m_arr = self.doc._resolver_objeto(m_arr)
                                    if isinstance(m_arr, list) and len(m_arr) >= 6:
                                        m_form = Matriz2D(*(float(v) for v in m_arr[:6]))
                                form_ctm = m_form.multiplicar(estado.ctm)
                                form_bytes = self.doc._descompactar_stream_obj(xobj)
                                self._processar_stream(form_bytes, form_ctm, profundidade + 1)


def extrair_contornos(caminho_ou_doc, tolerancia_mm=TOLERANCIA_MM, aceitar_tudo=False):
    """
    Lê o PDF e devolve (polilinhas_em_mm, relatorio).

    As polilinhas já vêm em milímetros e com o Y virado pra cima, escala 1:1,
    conforme padrão para corte em fresas CNC e mesas digitais (Zünd, Kongsberg, iEcho, Summa).

    Aceita:
      - Caminho de arquivo (str ou pathlib.Path)
      - Bytes ou stream de arquivo PDF
      - Documento ou Página nativa do motor_pdf (PdfReader, Pagina)
      - Objeto Document ou Page do PyMuPDF (compatibilidade retroativa)

    'aceitar_tudo' pega TODO vetor do arquivo, sem exigir magenta nem camada nomeada.
    É OPT-IN e nunca o padrão.
    """
    tolerancia_pt = tolerancia_mm / _PT_PARA_MM
    relatorio = {
        "paginas": 0, "desenhos": 0, "de_corte": 0, "descartados": 0,
        "imagens": 0, "contornos": 0, "mascaras": [],
        "criterio": None, "camadas": [],
    }
    saida = []

    # 1. Compatibilidade com objeto de página do PyMuPDF
    if hasattr(caminho_ou_doc, "get_drawings"):
        pg = caminho_ou_doc
        relatorio["paginas"] = 1
        altura = pg.rect.height
        relatorio["imagens"] = len(pg.get_images())
        relatorio["mascaras"].extend(_mascaras_suspeitas(pg))

        todos = [(pg, d) for d in pg.get_drawings(extended=True) if d.get("type") != "clip"]
        nomes = {str(d.get("layer")) for _, d in todos if d.get("layer")}
        relatorio["camadas"] = sorted(n for n in nomes if n != "None")
        por_camada = any(e_camada_de_corte(n) for n in nomes)
        tem_corte = any(
            e_cor_de_corte(d.get("color")) or e_cor_de_corte(d.get("fill"))
            for _, d in todos
        )
        usar_tudo = aceitar_tudo and not por_camada and not tem_corte
        relatorio["criterio"] = "tudo" if usar_tudo else ("camada" if por_camada else "cor")

        for _, d in todos:
            relatorio["desenhos"] += 1
            if usar_tudo:
                corte = True
            elif por_camada:
                corte = e_camada_de_corte(d.get("layer"))
            else:
                corte = e_cor_de_corte(d.get("color")) or e_cor_de_corte(d.get("fill"))

            if not corte:
                relatorio["descartados"] += 1
                continue
            relatorio["de_corte"] += 1
            for poli in _polilinhas_do_desenho(d, tolerancia_pt):
                saida.append([((x * _PT_PARA_MM), ((altura - y) * _PT_PARA_MM)) for x, y in poli])

        relatorio["contornos"] = len(saida)
        return saida, relatorio

    # 2. Caminho principal nativo: motor_pdf (100% autônomo)
    doc_aberto = None
    if isinstance(caminho_ou_doc, Pagina):
        doc = caminho_ou_doc.doc
        paginas = [caminho_ou_doc]
    elif isinstance(caminho_ou_doc, PdfReader):
        doc = caminho_ou_doc
        paginas = list(doc.paginas)
    else:
        doc_aberto = motor_pdf.abrir_pdf(caminho_ou_doc)
        doc = doc_aberto
        paginas = list(doc.paginas)

    try:
        relatorio["paginas"] = len(paginas)

        todos_desenhos = []
        todas_camadas = set()

        for pg in paginas:
            relatorio["imagens"] += len(pg.listar_imagens())
            extrator = ExtratorVetoresNativo(pg, doc)
            desenhos, mascaras, camadas = extrator.extrair()
            relatorio["mascaras"].extend(mascaras)
            todas_camadas.update(camadas)
            for d in desenhos:
                todos_desenhos.append((pg, d))

        relatorio["camadas"] = sorted(n for n in todas_camadas if n and n != "None")
        por_camada = any(e_camada_de_corte(n) for n in todas_camadas)
        tem_corte = any(
            e_cor_de_corte(d.get("color"), d.get("stroke_spot"))
            or e_cor_de_corte(d.get("fill"), d.get("fill_spot"))
            for _, d in todos_desenhos
        )

        usar_tudo = aceitar_tudo and not por_camada and not tem_corte
        relatorio["criterio"] = "tudo" if usar_tudo else ("camada" if por_camada else "cor")

        def e_de_corte(d):
            if usar_tudo:
                return True
            if por_camada:
                return e_camada_de_corte(d.get("layer"))
            return (
                e_cor_de_corte(d.get("color"), d.get("stroke_spot"))
                or e_cor_de_corte(d.get("fill"), d.get("fill_spot"))
            )

        for pg, d in todos_desenhos:
            relatorio["desenhos"] += 1
            if not e_de_corte(d):
                relatorio["descartados"] += 1
                continue

            relatorio["de_corte"] += 1

            # No PDF nativo, coordenadas em pontos já têm Y para cima (DXF padrão)
            crop = pg.cropbox if not pg.cropbox.vazio else pg.mediabox
            x0 = crop.x0
            y0 = crop.y0

            for poli in _polilinhas_do_desenho(d, tolerancia_pt):
                saida.append([
                    (((x - x0) * _PT_PARA_MM), ((y - y0) * _PT_PARA_MM))
                    for x, y in poli
                ])

    finally:
        if doc_aberto is not None:
            doc_aberto.close()

    relatorio["contornos"] = len(saida)
    return saida, relatorio


def _ponto_dentro(ponto, poligono):
    """
    Lançamento de raio: conta quantas vezes um raio horizontal saindo do
    ponto cruza o polígono. Ímpar = dentro.
    """
    x, y = ponto
    dentro = False
    n = len(poligono)
    j = n - 1
    for i in range(n):
        xi, yi = poligono[i]
        xj, yj = poligono[j]
        if (yi > y) != (yj > y):
            corte = (xj - xi) * (y - yi) / (yj - yi) + xi
            if x < corte:
                dentro = not dentro
        j = i
    return dentro


def _caixa(poli):
    xs = [p[0] for p in poli]
    ys = [p[1] for p in poli]
    return min(xs), min(ys), max(xs), max(ys)


def classificar_aninhamento(polilinhas):
    """
    Diz, pra cada contorno, se ele é externo ou interno.

    Regra de fabricação: "dentro por dentro e fora por fora". O buraco do 'O'
    tem que ser usinado POR DENTRO da linha; o contorno da letra tem que ser
    usinado POR FORA.
    """
    caixas = [_caixa(p) for p in polilinhas]
    niveis = []
    for i, poli in enumerate(polilinhas):
        ponto = poli[0]
        x0, y0, x1, y1 = caixas[i]
        nivel = 0
        for j, outro in enumerate(polilinhas):
            if i == j or len(outro) < 3:
                continue
            ox0, oy0, ox1, oy1 = caixas[j]
            if not (ox0 <= x0 and oy0 <= y0 and ox1 >= x1 and oy1 >= y1):
                continue
            if _ponto_dentro(ponto, outro):
                nivel += 1
        niveis.append(nivel)
    return [CAMADA_INTERNO if n % 2 else CAMADA_EXTERNO for n in niveis]


def _par(codigo, valor):
    return f"{codigo}\n{valor}\n"


def escrever_dxf(polilinhas, caminho_dxf, camadas=None):
    """
    Grava as polilinhas como DXF R12 ASCII, em milímetros (escala 1:1).

    Garante compatibilidade total com mesas de corte (Zünd, Kongsberg, iEcho, Summa)
    e softwares CNC (CNC CAM, Aspire, Vectric):
      - Cabeçalho R12 limpo (SECTION HEADER com $ACADVER AC1009, $INSUNITS 4, $MEASUREMENT 1).
      - Tabela de camadas (TABLES / LAYER) declarando CORTE / CORTE EXTERNO / CORTE INTERNO.
      - Seção BLOCKS padrão.
      - Entidades POLYLINE / VERTEX / SEQEND puras.
    """
    caminho_dxf = pathlib.Path(caminho_dxf)
    usadas = []
    for nome in (camadas or [NOME_CAMADA]):
        if nome not in usadas:
            usadas.append(nome)

    partes = [
        _par(0, "SECTION"), _par(2, "HEADER"),
        _par(9, "$ACADVER"), _par(1, "AC1009"),
        _par(9, "$INSUNITS"), _par(70, 4),          # 4 = milímetros
        _par(9, "$MEASUREMENT"), _par(70, 1),      # 1 = métrico
        _par(0, "ENDSEC"),
        _par(0, "SECTION"), _par(2, "TABLES"),
        _par(0, "TABLE"), _par(2, "LAYER"), _par(70, len(usadas)),
    ]
    for indice, nome in enumerate(usadas):
        partes += [
            _par(0, "LAYER"), _par(2, nome),
            _par(70, 0),                    # sem trava, sem congelar
            _par(62, indice + 1),           # cor AutoCAD (1=Red, 2=Yellow, etc.)
            _par(6, "CONTINUOUS"),
        ]
    partes += [
        _par(0, "ENDTAB"), _par(0, "ENDSEC"),
        _par(0, "SECTION"), _par(2, "BLOCKS"),
        _par(0, "ENDSEC"),
        _par(0, "SECTION"), _par(2, "ENTITIES"),
    ]
    for indice, poli in enumerate(polilinhas):
        camada = camadas[indice] if camadas else NOME_CAMADA
        fechada = len(poli) > 2 and _mesmo_ponto(poli[0], poli[-1], folga=1e-4)
        pontos = poli[:-1] if fechada else poli
        partes += [
            _par(0, "POLYLINE"), _par(8, camada),
            _par(66, 1), _par(70, 1 if fechada else 0),
        ]
        for x, y in pontos:
            partes += [
                _par(0, "VERTEX"), _par(8, camada),
                _par(10, f"{x:.4f}"), _par(20, f"{y:.4f}"), _par(30, "0.0"),
            ]
        partes += [_par(0, "SEQEND"), _par(8, camada)]

    partes += [_par(0, "ENDSEC"), _par(0, "EOF")]
    caminho_dxf.write_text("".join(partes), encoding="ascii")
    return caminho_dxf


def converter(caminho_pdf, caminho_dxf=None, tolerancia_mm=TOLERANCIA_MM, aceitar_tudo=False):
    """
    Gera o DXF de corte ao lado do PDF, com o mesmo nome.

    NUNCA escreve no PDF nem o apaga — o DXF é arquivo novo.
    """
    caminho_pdf = pathlib.Path(caminho_pdf)
    polilinhas, relatorio = extrair_contornos(caminho_pdf, tolerancia_mm, aceitar_tudo)
    relatorio["pdf"] = str(caminho_pdf)
    relatorio["dxf"] = None
    relatorio["motivo"] = None

    if not polilinhas:
        if relatorio["desenhos"] == 0:
            relatorio["motivo"] = (
                "não achei vetor nenhum neste PDF — se ele é imagem, "
                "não há o que cortar"
            )
        elif relatorio["mascaras"]:
            relatorio["motivo"] = (
                f"nenhum contorno magenta entre os {relatorio['desenhos']} vetores, MAS há "
                f"máscara de recorte com forma complexa ({', '.join(str(m) for m in relatorio['mascaras'])} "
                f"segmentos) — máscara não guarda cor, então pode ser o contorno de corte com o "
                f"magenta perdido. Abra no Illustrator e libere a máscara de recorte"
            )
        else:
            relatorio["motivo"] = (
                f"nenhum contorno magenta entre os {relatorio['desenhos']} vetores — "
                f"ou a linha de corte está em outra cor, ou a peça é o próprio "
                f"desenho preenchido (letra caixa)"
            )
        return relatorio

    destino = pathlib.Path(caminho_dxf) if caminho_dxf else caminho_pdf.with_suffix(".dxf")
    camadas = classificar_aninhamento(polilinhas)
    escrever_dxf(polilinhas, destino, camadas)
    relatorio["dxf"] = str(destino)
    relatorio["internos"] = camadas.count(CAMADA_INTERNO)
    relatorio["externos"] = camadas.count(CAMADA_EXTERNO)

    try:
        from corte_parametros import atalho_do_menu
        relatorio["atalho"] = atalho_do_menu(caminho_pdf.name)
    except Exception:
        relatorio["atalho"] = None
    return relatorio


def conferir_pasta(pasta, converter_prontos=False):
    """
    Passa o olho numa pasta de cortes e diz, arquivo por arquivo, o que
    está pronto e o que precisa de você.
    """
    pasta = pathlib.Path(pasta)
    resultado = []
    if not pasta.is_dir():
        return resultado

    for pdf in sorted(pasta.rglob("*.pdf")):
        if pdf.parent.name.upper() in ("PRONTOS", "ENVIADOS"):
            continue
        try:
            polilinhas, relatorio = extrair_contornos(pdf)
        except Exception as e:
            resultado.append({
                "arquivo": pdf, "estado": PARADO, "contornos": 0,
                "motivo": f"não consegui ler: {e}", "dxf": None
            })
            continue

        relatorio["arquivo"] = pdf
        relatorio["dxf"] = None
        if not polilinhas:
            relatorio["estado"] = PARADO
            relatorio["motivo"] = converter(pdf)["motivo"]
        elif relatorio["criterio"] == "camada":
            relatorio["estado"] = PRONTO
            relatorio["motivo"] = None
            if converter_prontos:
                camadas = classificar_aninhamento(polilinhas)
                relatorio["dxf"] = str(escrever_dxf(polilinhas, pdf.with_suffix(".dxf"), camadas))
        else:
            relatorio["estado"] = CONFERIR
            relatorio["motivo"] = (
                "saiu pela cor magenta, não por camada nomeada — "
                "se o arquivo tiver sanca ou gabarito, eles vêm junto"
            )
        resultado.append(relatorio)
    return resultado
