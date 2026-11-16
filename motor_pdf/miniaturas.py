"""
motor_pdf/miniaturas.py — Gerador autônomo de miniaturas (thumbnails).

100% independente de PyMuPDF, Poppler ou qualquer biblioteca AGPL/GPL.
Utiliza exclusivamente Pillow (PIL.Image, PIL.ImageDraw) e o motor nativo motor_pdf.

Regras do chão de fábrica:
  - Nunca levanta exceção: miniatura é conforto visual; erro de leitura retorna None.
  - Imagens rasterizadas diretamente na escala proporcional, sem distorção.
  - Suporte completo a imagens comuns (PNG, JPG, TIFF, BMP, WebP) via Pillow.
  - Suporte a PDF via motor_pdf:
      * Extração de imagens embutidas (/Resources /XObject /Subtype /Image).
      * Renderização vetorial e silhueta limpa com PIL.ImageDraw para PDFs puramente vetoriais.
  - Sistema de cache por mês/chave em disco para preservação de comprovantes antigos.
"""

from __future__ import annotations

import hashlib
import io
import os
import pathlib
from typing import Any, List, Optional, Tuple, Union

from PIL import Image, ImageDraw

from .descompressao import descompactar_stream
from .geometria import Matriz2D
from .interpretador_stream import PADRAO_TOKEN_STREAM
from .leitor import Caixa, Pagina, PdfReader, abrir_pdf
from .sintaxe import PdfName, PdfRef, PdfStream, PdfString

LADO_PADRAO = 300  # px no maior lado
QUALIDADE_PADRAO = 70
LIMITE_BYTES = 300 * 1024 * 1024  # 300 MB
NOME_PASTA_CACHE = "_miniaturas"

EXTENSOES_IMAGEM = {
    ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp",
    ".gif", ".ico", ".ppm", ".pgm", ".pbm", ".pnm"
}


# ==============================================================================
# 1. Funções de Proporção, Encaixe e Cache
# ==============================================================================

def proporcao(dados: bytes) -> Optional[Tuple[int, int]]:
    """(largura, altura) em px da miniatura, ou None — pra não distorcer."""
    if not dados or not isinstance(dados, (bytes, bytearray)):
        return None
    try:
        with Image.open(io.BytesIO(dados)) as img:
            return img.size
    except Exception:
        return None


def encaixar(dados: bytes, largura_max: float, altura_max: float) -> Tuple[float, float]:
    """
    (largura, altura) pra desenhar dentro da caixa MANTENDO a proporção.
    Arte esticada num documento de gráfica é defeito, não detalhe.
    """
    tamanho = proporcao(dados)
    if not tamanho:
        return largura_max, altura_max
    largura, altura = tamanho
    if largura <= 0 or altura <= 0:
        return largura_max, altura_max
    escala = min(largura_max / largura, altura_max / altura)
    return max(1, round(largura * escala)), max(1, round(altura * escala))


def _nome_guardado(chave: Any) -> str:
    """Nome curto e sem surpresa: nome de arte tem acento, barra e 200 letras."""
    texto = "|".join(str(p) for p in chave)
    return hashlib.sha1(texto.encode("utf-8")).hexdigest()[:16] + ".jpg"


def caminho_guardada(pasta_cache: Union[str, os.PathLike], mes: Any, chave: Any) -> pathlib.Path:
    """Caminho absoluto ou relativo onde a miniatura é guardada no cache."""
    return pathlib.Path(pasta_cache) / NOME_PASTA_CACHE / str(mes) / _nome_guardado(chave)


def guardada(pasta_cache: Union[str, os.PathLike], mes: Any, chave: Any) -> Optional[bytes]:
    """A miniatura que já foi guardada, ou None."""
    try:
        caminho = caminho_guardada(pasta_cache, mes, chave)
        return caminho.read_bytes() if caminho.is_file() else None
    except OSError:
        return None


def guardar(
    pasta_cache: Union[str, os.PathLike],
    mes: Any,
    chave: Any,
    dados_jpg: Optional[bytes]
) -> Optional[pathlib.Path]:
    """Guarda a miniatura em disco pra quando o arquivo original já não existir mais."""
    if not dados_jpg:
        return None
    caminho = caminho_guardada(pasta_cache, mes, chave)
    try:
        caminho.parent.mkdir(parents=True, exist_ok=True)
        temporario = caminho.with_suffix(".tmp")
        temporario.write_bytes(dados_jpg)
        temporario.replace(caminho)
        return caminho
    except OSError:
        return None


def obter(
    caminho_arte: Union[str, os.PathLike],
    pasta_cache: Optional[Union[str, os.PathLike]] = None,
    mes: Any = None,
    chave: Any = None,
    lado: int = LADO_PADRAO,
    qualidade: int = QUALIDADE_PADRAO,
) -> Optional[bytes]:
    """
    A miniatura, do cache ou do arquivo — e guardando quando faz do
    arquivo. Sem `pasta_cache` é só a miniatura, sem guardar nada.
    """
    if pasta_cache and chave:
        ja = guardada(pasta_cache, mes, chave)
        if ja:
            return ja
    dados = de_arquivo(caminho_arte, lado=lado, qualidade=qualidade)
    if dados and pasta_cache and chave:
        guardar(pasta_cache, mes, chave, dados)
    return dados


# ==============================================================================
# 2. Processamento e Normalização de Imagens para JPEG
# ==============================================================================

def _processar_imagem_para_jpeg(img: Image.Image, lado: int, qualidade: int) -> bytes:
    """Ajusta dimensões mantendo aspect ratio e converte para JPEG RGB."""
    try:
        img.seek(0)
    except Exception:
        pass

    im = img.copy()

    # Redimensiona proporcionalmente respeitando o lado máximo
    if max(im.size) > lado:
        im.thumbnail((lado, lado), Image.Resampling.LANCZOS)

    # Converte cores para RGB de modo compatível com o formato JPEG
    if im.mode in ("RGBA", "LA"):
        fundo = Image.new("RGB", im.size, (255, 255, 255))
        fundo.paste(im, mask=im.split()[-1])
        im = fundo
    elif im.mode == "CMYK":
        im = im.convert("RGB")
    elif im.mode == "P":
        im = im.convert("RGB")
    elif im.mode != "RGB":
        im = im.convert("RGB")

    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=qualidade)
    return buf.getvalue()


# ==============================================================================
# 3. Extração e Decodificação de Imagens Embutidas no PDF
# ==============================================================================

def _decodificar_imagem_stream(doc: PdfReader, xobj: PdfStream) -> Optional[Image.Image]:
    """Reconstrói um objeto PIL.Image a partir de um PdfStream /Subtype /Image."""
    hdr = xobj.header
    w = int(doc._resolver_objeto(hdr.get("/Width", 0)) or 0)
    h = int(doc._resolver_objeto(hdr.get("/Height", 0)) or 0)
    bpc = int(doc._resolver_objeto(hdr.get("/BitsPerComponent", 8)) or 8)
    filtro = doc._resolver_objeto(hdr.get("/Filter"))
    params = doc._resolver_objeto(hdr.get("/DecodeParms"))
    cs = doc._resolver_objeto(hdr.get("/ColorSpace"))

    filtros = [filtro] if isinstance(filtro, (str, PdfName)) else (list(filtro) if isinstance(filtro, list) else [])
    nomes_filtros = [str(f).strip("/") for f in filtros]

    # 1. Se for DCTDecode (JPEG nativo) ou começar com SOI JPEG (\xff\xd8)
    if "DCTDecode" in nomes_filtros or xobj.raw_bytes[:2] == b"\xff\xd8":
        try:
            im = Image.open(io.BytesIO(xobj.raw_bytes))
            im.load()
            return im
        except Exception:
            pass
        # Se houver decodificadores ASCII anteriores ao DCT
        if any(f in ("ASCIIHexDecode", "ASCII85Decode") for f in nomes_filtros):
            try:
                filtros_sem_dct = [f for f in nomes_filtros if f not in ("DCTDecode", "DCT")]
                dados_ascii = descompactar_stream(xobj.raw_bytes, filtros_sem_dct, params)
                im = Image.open(io.BytesIO(dados_ascii))
                im.load()
                return im
            except Exception:
                pass

    # 2. Descompacta streams comprimidos (FlateDecode, ASCII, RunLength)
    try:
        dados = doc._descompactar_stream_obj(xobj)
    except Exception:
        dados = xobj.raw_bytes

    if not dados:
        return None

    # Tenta abrir diretamente com Pillow caso seja um formato de arquivo completo
    try:
        im = Image.open(io.BytesIO(dados))
        im.load()
        return im
    except Exception:
        pass

    if w <= 0 or h <= 0:
        return None

    # 3. Resolução do espaço de cor
    tipo_cs = ""
    paleta_bytes = None

    if isinstance(cs, list) and len(cs) > 0:
        tipo_cs = str(cs[0]).strip("/")
        if tipo_cs in ("Indexed", "I") and len(cs) >= 4:
            lookup = doc._resolver_objeto(cs[3])
            if isinstance(lookup, PdfStream):
                paleta_bytes = doc._descompactar_stream_obj(lookup)
            elif isinstance(lookup, PdfString):
                paleta_bytes = lookup.dados if hasattr(lookup, "dados") else bytes(lookup)
            elif isinstance(lookup, (bytes, bytearray)):
                paleta_bytes = bytes(lookup)
        elif tipo_cs == "ICCBased" and len(cs) >= 2:
            icc_stream = doc._resolver_objeto(cs[1])
            if isinstance(icc_stream, PdfStream):
                n_comp = int(doc._resolver_objeto(icc_stream.header.get("/N", 3)) or 3)
                if n_comp == 4:
                    tipo_cs = "DeviceCMYK"
                elif n_comp == 1:
                    tipo_cs = "DeviceGray"
                else:
                    tipo_cs = "DeviceRGB"
    elif cs is not None:
        tipo_cs = str(cs).strip("/")

    # 4. Reconstrução de amostras de pixels
    try:
        if tipo_cs in ("DeviceRGB", "RGB"):
            if bpc == 8 and len(dados) >= w * h * 3:
                return Image.frombytes("RGB", (w, h), dados[:w * h * 3])
        elif tipo_cs in ("DeviceCMYK", "CMYK"):
            if bpc == 8 and len(dados) >= w * h * 4:
                return Image.frombytes("CMYK", (w, h), dados[:w * h * 4]).convert("RGB")
        elif tipo_cs in ("DeviceGray", "Gray", "G"):
            if bpc == 8 and len(dados) >= w * h:
                return Image.frombytes("L", (w, h), dados[:w * h])
            elif bpc == 1:
                stride = (w + 7) // 8
                if len(dados) >= stride * h:
                    return Image.frombytes("1", (w, h), dados[:stride * h])
        elif tipo_cs in ("Indexed", "I"):
            if len(dados) >= w * h:
                im_p = Image.frombytes("P", (w, h), dados[:w * h])
                if paleta_bytes:
                    im_p.putpalette(paleta_bytes)
                return im_p.convert("RGB")

        # Heurística pelo comprimento dos dados
        if len(dados) >= w * h * 3:
            return Image.frombytes("RGB", (w, h), dados[:w * h * 3])
        elif len(dados) >= w * h * 4:
            return Image.frombytes("CMYK", (w, h), dados[:w * h * 4]).convert("RGB")
        elif len(dados) >= w * h:
            return Image.frombytes("L", (w, h), dados[:w * h])
    except Exception:
        pass

    return None


def _coletar_imagens_xobject(doc: PdfReader, xobjects: dict, destino: list):
    """Varre dicionário de XObjects procurando imagens e formas recursivas."""
    if not isinstance(xobjects, dict):
        return

    for _, xobj_ref in xobjects.items():
        xobj = doc._resolver_objeto(xobj_ref)
        if not isinstance(xobj, PdfStream):
            continue
        hdr = xobj.header
        subtype = str(doc._resolver_objeto(hdr.get("/Subtype", "")))
        if subtype in ("/Image", "Image"):
            w = int(doc._resolver_objeto(hdr.get("/Width", 0)) or 0)
            h = int(doc._resolver_objeto(hdr.get("/Height", 0)) or 0)
            area = w * h
            destino.append((area, xobj))
        elif subtype in ("/Form", "Form"):
            # Varre recursos internos do Form
            form_res = doc._resolver_objeto(hdr.get("/Resources", {}))
            if isinstance(form_res, dict):
                form_xobjs = doc._resolver_objeto(form_res.get("/XObject", {}))
                _coletar_imagens_xobject(doc, form_xobjs, destino)


def _extrair_imagem_de_pagina(pagina: Pagina) -> Optional[Image.Image]:
    """Inspeciona /Resources /XObject da página procurando imagens embutidas."""
    resources = pagina.doc._resolver_objeto(pagina.raw_dict.get("/Resources", {}))
    if not isinstance(resources, dict):
        return None

    xobjects = pagina.doc._resolver_objeto(resources.get("/XObject", {}))
    if not isinstance(xobjects, dict):
        return None

    candidatos: list = []
    _coletar_imagens_xobject(pagina.doc, xobjects, candidatos)
    if not candidatos:
        return None

    # Ordena para preferir a imagem principal (maior área em pixels)
    candidatos.sort(key=lambda item: item[0], reverse=True)

    for _, xobj in candidatos:
        img = _decodificar_imagem_stream(pagina.doc, xobj)
        if img is not None:
            return img

    return None


# ==============================================================================
# 4. Renderização Vetorial Limpa via PIL.ImageDraw (PDFs sem imagem bitmap)
# ==============================================================================

class _EstadoVetor:
    """Estado gráfico para renderização de traçados e silhuetas."""
    __slots__ = ("ctm", "stroke_color", "fill_color", "line_width")

    def __init__(
        self,
        ctm: Optional[Matriz2D] = None,
        stroke_color: Tuple[int, int, int] = (0, 0, 0),
        fill_color: Tuple[int, int, int] = (0, 0, 0),
        line_width: float = 1.0,
    ):
        self.ctm = ctm if ctm is not None else Matriz2D.identidade()
        self.stroke_color = stroke_color
        self.fill_color = fill_color
        self.line_width = line_width

    def clonar(self) -> "_EstadoVetor":
        return _EstadoVetor(
            ctm=Matriz2D(self.ctm.a, self.ctm.b, self.ctm.c, self.ctm.d, self.ctm.e, self.ctm.f),
            stroke_color=self.stroke_color,
            fill_color=self.fill_color,
            line_width=self.line_width,
        )


def _aproximar_bezier(
    p0: Tuple[float, float],
    p1: Tuple[float, float],
    p2: Tuple[float, float],
    p3: Tuple[float, float],
    passos: int = 6,
) -> List[Tuple[float, float]]:
    """Gera segmentos lineares aproximando curva de Bézier cúbica."""
    pts = []
    for i in range(1, passos + 1):
        t = i / passos
        it = 1.0 - t
        x = (it ** 3) * p0[0] + 3 * (it ** 2) * t * p1[0] + 3 * it * (t ** 2) * p2[0] + (t ** 3) * p3[0]
        y = (it ** 3) * p0[1] + 3 * (it ** 2) * t * p1[1] + 3 * it * (t ** 2) * p2[1] + (t ** 3) * p3[1]
        pts.append((x, y))
    return pts


def _desenhar_conteudo_vetorial(
    pagina: Pagina,
    draw: ImageDraw.ImageDraw,
    img: Image.Image,
    largura_px: int,
    altura_px: int,
    escala: float,
):
    """Executa operadores gráficos de traçados do stream PDF na imagem PIL."""
    cropbox = pagina.cropbox or pagina.mediabox or Caixa(0, 0, pagina.largura_pt, pagina.altura_pt)
    x0, y0, x1, y1 = cropbox.x0, cropbox.y0, cropbox.x1, cropbox.y1
    rotacao = getattr(pagina, "rotacao", 0) % 360

    def projetar(x: float, y: float) -> Tuple[float, float]:
        if rotacao == 90:
            return (y - y0) * escala, (x - x0) * escala
        elif rotacao == 180:
            return (x1 - x) * escala, (y - y0) * escala
        elif rotacao == 270:
            return (y1 - y) * escala, (x1 - x) * escala
        else:
            return (x - x0) * escala, (y1 - y) * escala

    conteudo = pagina.obter_conteudo_bruto()
    if not conteudo:
        draw.rectangle([0, 0, largura_px - 1, altura_px - 1], outline=(225, 225, 225), fill=(255, 255, 255))
        return

    tokens = PADRAO_TOKEN_STREAM.findall(conteudo)
    pilha_op: List[Any] = []
    estado = _EstadoVetor()
    pilha_estados: List[_EstadoVetor] = []
    subpaths: List[List[Tuple[float, float]]] = []
    cur_pos = (0.0, 0.0)
    elementos_desenhados = 0

    def pop_numeros(n: int) -> List[float]:
        nums = []
        while pilha_op and len(nums) < n:
            val = pilha_op.pop()
            if isinstance(val, (int, float)):
                nums.append(float(val))
            else:
                nums.append(0.0)
        nums.reverse()
        while len(nums) < n:
            nums.insert(0, 0.0)
        return nums

    def pop_arg() -> Any:
        return pilha_op.pop() if pilha_op else None

    def pintar(stroke: bool, fill: bool, fechar: bool):
        nonlocal elementos_desenhados
        for sp in subpaths:
            if not sp:
                continue
            pontos = list(sp)
            if fechar and pontos[0] != pontos[-1]:
                pontos.append(pontos[0])
            pts_px = [projetar(*estado.ctm.transformar_ponto(px, py)) for (px, py) in pontos]
            if fill and len(pts_px) >= 3:
                draw.polygon(pts_px, fill=estado.fill_color)
                elementos_desenhados += 1
            if stroke and len(pts_px) >= 2:
                lw = max(1, round(estado.line_width * escala))
                draw.line(pts_px, fill=estado.stroke_color, width=lw)
                elementos_desenhados += 1
        subpaths.clear()

    idx = 0
    total = len(tokens)
    while idx < total:
        tok = tokens[idx]
        idx += 1

        if tok.startswith(b"%"):
            continue
        if tok in (b"[", b"]", b"<<", b">>"):
            continue
        if tok.startswith(b"/"):
            pilha_op.append(tok.decode("latin1", errors="ignore"))
            continue
        if tok.startswith(b"(") or tok.startswith(b"<"):
            pilha_op.append(tok)
            continue

        c = tok[0]
        if (0x30 <= c <= 0x39) or c in (0x2D, 0x2B, 0x2E):
            try:
                pilha_op.append(float(tok))
                continue
            except ValueError:
                pass

        op = tok.decode("latin1", errors="ignore")

        if op == "q":
            if len(pilha_estados) < 256:
                pilha_estados.append(estado.clonar())
        elif op == "Q":
            if pilha_estados:
                estado = pilha_estados.pop()
        elif op == "cm":
            nums = pop_numeros(6)
            m = Matriz2D(nums[0], nums[1], nums[2], nums[3], nums[4], nums[5])
            estado.ctm = m.multiplicar(estado.ctm)
        elif op == "w":
            estado.line_width = max(0.5, pop_numeros(1)[0])
        elif op == "G":
            g = min(max(pop_numeros(1)[0], 0.0), 1.0)
            gv = int(g * 255)
            estado.stroke_color = (gv, gv, gv)
        elif op == "g":
            g = min(max(pop_numeros(1)[0], 0.0), 1.0)
            gv = int(g * 255)
            estado.fill_color = (gv, gv, gv)
        elif op == "RG":
            r, g, b = pop_numeros(3)
            estado.stroke_color = (
                int(min(max(r, 0.0), 1.0) * 255),
                int(min(max(g, 0.0), 1.0) * 255),
                int(min(max(b, 0.0), 1.0) * 255),
            )
        elif op == "rg":
            r, g, b = pop_numeros(3)
            estado.fill_color = (
                int(min(max(r, 0.0), 1.0) * 255),
                int(min(max(g, 0.0), 1.0) * 255),
                int(min(max(b, 0.0), 1.0) * 255),
            )
        elif op == "K":
            c_val, m_val, y_val, k_val = [min(max(v, 0.0), 1.0) for v in pop_numeros(4)]
            estado.stroke_color = (
                int(255 * (1.0 - c_val) * (1.0 - k_val)),
                int(255 * (1.0 - m_val) * (1.0 - k_val)),
                int(255 * (1.0 - y_val) * (1.0 - k_val)),
            )
        elif op == "k":
            c_val, m_val, y_val, k_val = [min(max(v, 0.0), 1.0) for v in pop_numeros(4)]
            estado.fill_color = (
                int(255 * (1.0 - c_val) * (1.0 - k_val)),
                int(255 * (1.0 - m_val) * (1.0 - k_val)),
                int(255 * (1.0 - y_val) * (1.0 - k_val)),
            )
        elif op == "m":
            x, y = pop_numeros(2)
            cur_pos = (x, y)
            subpaths.append([cur_pos])
        elif op == "l":
            x, y = pop_numeros(2)
            cur_pos = (x, y)
            if not subpaths:
                subpaths.append([cur_pos])
            else:
                subpaths[-1].append(cur_pos)
        elif op == "re":
            x, y, w, h = pop_numeros(4)
            subpaths.append([(x, y), (x + w, y), (x + w, y + h), (x, y + h), (x, y)])
            cur_pos = (x, y)
        elif op == "c":
            x1, y1, x2, y2, x3, y3 = pop_numeros(6)
            p0 = cur_pos
            cur_pos = (x3, y3)
            curva = _aproximar_bezier(p0, (x1, y1), (x2, y2), cur_pos)
            if not subpaths:
                subpaths.append([p0])
            subpaths[-1].extend(curva)
        elif op == "v":
            x2, y2, x3, y3 = pop_numeros(4)
            p0 = cur_pos
            cur_pos = (x3, y3)
            curva = _aproximar_bezier(p0, p0, (x2, y2), cur_pos)
            if not subpaths:
                subpaths.append([p0])
            subpaths[-1].extend(curva)
        elif op == "y":
            x1, y1, x3, y3 = pop_numeros(4)
            p0 = cur_pos
            cur_pos = (x3, y3)
            curva = _aproximar_bezier(p0, (x1, y1), cur_pos, cur_pos)
            if not subpaths:
                subpaths.append([p0])
            subpaths[-1].extend(curva)
        elif op == "h":
            if subpaths and subpaths[-1]:
                sp = subpaths[-1]
                if sp[0] != sp[-1]:
                    sp.append(sp[0])
                cur_pos = sp[0]
        elif op == "S":
            pintar(stroke=True, fill=False, fechar=False)
        elif op == "s":
            pintar(stroke=True, fill=False, fechar=True)
        elif op in ("f", "F", "f*"):
            pintar(stroke=False, fill=True, fechar=False)
        elif op in ("B", "B*"):
            pintar(stroke=True, fill=True, fechar=False)
        elif op in ("b", "b*"):
            pintar(stroke=True, fill=True, fechar=True)
        elif op == "n":
            subpaths.clear()
        elif op == "Do":
            nome_xobj = pop_arg()
            if nome_xobj and pagina.doc:
                _desenhar_xobject_em_vetor(pagina, str(nome_xobj), estado, draw, img, projetar)
                elementos_desenhados += 1
        elif op in ("Tj", "'", "\"", "TJ"):
            pop_arg()
            elementos_desenhados += 1
        else:
            pass

    if elementos_desenhados == 0:
        draw.rectangle([0, 0, largura_px - 1, altura_px - 1], outline=(225, 225, 225), fill=(255, 255, 255))


def _desenhar_xobject_em_vetor(
    pagina: Pagina,
    nome: str,
    estado: _EstadoVetor,
    draw: ImageDraw.ImageDraw,
    img: Image.Image,
    projetar: Any,
):
    """Renderiza imagem invocada por operador Do dentro do canvas vetorial."""
    try:
        resources = pagina.doc._resolver_objeto(pagina.raw_dict.get("/Resources", {}))
        if not isinstance(resources, dict):
            return
        xobjects = pagina.doc._resolver_objeto(resources.get("/XObject", {}))
        if not isinstance(xobjects, dict):
            return
        xobj_ref = xobjects.get(nome) or xobjects.get("/" + nome.lstrip("/"))
        if not xobj_ref:
            return
        xobj = pagina.doc._resolver_objeto(xobj_ref)
        if not isinstance(xobj, PdfStream):
            return

        subtype = str(pagina.doc._resolver_objeto(xobj.header.get("/Subtype", "")))
        if subtype in ("/Image", "Image"):
            img_decod = _decodificar_imagem_stream(pagina.doc, xobj)
            if img_decod is not None:
                # O XObject de imagem no PDF preenche o quadrado unitário [0, 0] a [1, 1] no CTM
                p_tl = projetar(*estado.ctm.transformar_ponto(0.0, 1.0))
                p_br = projetar(*estado.ctm.transformar_ponto(1.0, 0.0))
                ix0, iy0 = min(p_tl[0], p_br[0]), min(p_tl[1], p_br[1])
                ix1, iy1 = max(p_tl[0], p_br[0]), max(p_tl[1], p_br[1])
                iw = max(1, round(ix1 - ix0))
                ih = max(1, round(iy1 - iy0))
                im_res = img_decod.resize((iw, ih), Image.Resampling.BILINEAR)
                pos = (round(ix0), round(iy0))
                if im_res.mode in ("RGBA", "LA"):
                    img.paste(im_res, pos, mask=im_res.split()[-1])
                else:
                    img.paste(im_res, pos)
    except Exception:
        pass


def _renderizar_vetor_para_jpeg(pagina: Pagina, lado: int, qualidade: int) -> Optional[bytes]:
    """Gera miniatura JPEG desenhando os traçados vetoriais da página."""
    largura_pt = float(pagina.largura_pt or 612.0)
    altura_pt = float(pagina.altura_pt or 792.0)
    maior = max(largura_pt, altura_pt) or 1.0
    escala = min(lado / maior, 1.0)
    largura_px = max(1, round(largura_pt * escala))
    altura_px = max(1, round(altura_pt * escala))

    img = Image.new("RGB", (largura_px, altura_px), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    _desenhar_conteudo_vetorial(pagina, draw, img, largura_px, altura_px, escala)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=qualidade)
    return buf.getvalue()


# ==============================================================================
# 5. Entrada Principal: de_arquivo
# ==============================================================================

def _de_imagem(caminho: pathlib.Path, lado: int, qualidade: int) -> Optional[bytes]:
    """Abre arquivos de imagem comuns (PNG, JPG, TIFF, BMP, WebP) com Pillow."""
    try:
        with Image.open(str(caminho)) as img:
            return _processar_imagem_para_jpeg(img, lado, qualidade)
    except Exception:
        return None


def _de_pdf(caminho: pathlib.Path, lado: int, qualidade: int) -> Optional[bytes]:
    """Abre arquivo PDF usando motor_pdf e gera thumbnail da primeira página."""
    try:
        with abrir_pdf(caminho) as doc:
            if not doc.paginas:
                return None
            pagina = doc.obter_pagina(0)

            # 1. Procura imagem embutida (/Resources /XObject /Subtype /Image)
            img_embutida = _extrair_imagem_de_pagina(pagina)
            if img_embutida is not None:
                # Aplica rotação de visualização se especificada na página
                if pagina.rotacao in (90, 180, 270):
                    rot = (360 - pagina.rotacao) % 360
                    img_embutida = img_embutida.rotate(rot, expand=True)
                return _processar_imagem_para_jpeg(img_embutida, lado, qualidade)

            # 2. PDF puramente vetorial: desenha traçados ou silhueta com PIL.ImageDraw
            return _renderizar_vetor_para_jpeg(pagina, lado, qualidade)
    except Exception:
        return None


def de_arquivo(
    caminho: Union[str, os.PathLike],
    lado: int = LADO_PADRAO,
    qualidade: int = QUALIDADE_PADRAO,
    limite_bytes: Optional[int] = LIMITE_BYTES,
) -> Optional[bytes]:
    """
    JPEG da primeira página ou imagem do arquivo, ou None se não for possível.
    100% autônomo, sem exceções e sem bibliotecas de terceiros restritivas.
    """
    try:
        caminho_p = pathlib.Path(caminho)
        if not caminho_p.is_file():
            return None
        if limite_bytes and caminho_p.stat().st_size > limite_bytes:
            return None

        # Inspeciona cabeçalho para diferenciar PDF de imagens raster
        with open(caminho_p, "rb") as f:
            inicio = f.read(1024)
    except (OSError, Exception):
        return None

    sufixo = caminho_p.suffix.lower()
    eh_pdf = (sufixo == ".pdf") or inicio.startswith(b"%PDF-") or (b"%PDF-" in inicio[:1024])

    if eh_pdf:
        resultado = _de_pdf(caminho_p, lado=lado, qualidade=qualidade)
        if resultado is not None:
            return resultado
        # Fallback para tentar abrir via Pillow caso seja imagem com extensão .pdf errônea
        return _de_imagem(caminho_p, lado=lado, qualidade=qualidade)
    else:
        resultado = _de_imagem(caminho_p, lado=lado, qualidade=qualidade)
        if resultado is not None:
            return resultado
        # Fallback para PDF se houver assinatura interna de PDF
        if b"%PDF-" in inicio:
            return _de_pdf(caminho_p, lado=lado, qualidade=qualidade)
        return None
