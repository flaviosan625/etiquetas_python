"""
motor_pdf/leitor.py — Leitor e analisador estrutural de arquivos PDF (ISO 32000-1).

Implementa:
  - Busca de startxref e suporte a tabelas xref clássicas e streams de xref (/XRefStm)
  - Resolução de árvores de páginas (/Pages -> /Kids) com herança de MediaBox/Resources
  - Extração de caixas: MediaBox, CropBox, TrimBox, BleedBox e Rotação
  - Cálculo de dimensões métricas e pontos (largura_pt, altura_pt, largura_m, altura_m)
  - Inspeção de imagens (/XObject /Subtype /Image) e cálculo de DPI efetivo
  - Descompressão sob demanda de streams de conteúdo (/Contents)

100% autônomo, sem dependências de PyMuPDF ou bibliotecas externas.
"""

from __future__ import annotations

import io
import os
import pathlib
import re
import struct
from typing import Any, Dict, List, Optional, Tuple, Union

from .descompressao import descompactar_stream
from .sintaxe import (
    PdfArray,
    PdfDict,
    PdfName,
    PdfRef,
    PdfStream,
    PdfString,
    PdfTokenizer,
    parse_objeto,
)

PT_POR_M = 72.0 / 0.0254    # ~2834.64567 pontos por metro
PT_POR_MM = 72.0 / 25.4     # ~2.8346 pontos por milímetro


class Caixa:
    """Representa uma caixa retangular em coordenadas de página PDF [x0, y0, x1, y1]."""
    __slots__ = ("x0", "y0", "x1", "y1")

    def __init__(self, x0: float, y0: float, x1: float, y1: float):
        # Garante x0 <= x1 e y0 <= y1
        self.x0 = float(min(x0, x1))
        self.y0 = float(min(y0, y1))
        self.x1 = float(max(x0, x1))
        self.y1 = float(max(y0, y1))

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0

    @property
    def largura_m(self) -> float:
        return self.width / PT_POR_M

    @property
    def altura_m(self) -> float:
        return self.height / PT_POR_M

    def __repr__(self):
        return f"Caixa({self.x0:.2f}, {self.y0:.2f}, {self.x1:.2f}, {self.y1:.2f} | {self.largura_m:.3f}x{self.altura_m:.3f}m)"

    @classmethod
    def de_lista(cls, arr: Optional[List[Any]], padrao: Optional["Caixa"] = None) -> "Caixa":
        if arr and isinstance(arr, list) and len(arr) >= 4:
            try:
                return cls(float(arr[0]), float(arr[1]), float(arr[2]), float(arr[3]))
            except (ValueError, TypeError):
                pass
        return padrao or cls(0, 0, 612, 792)


class ImagemInfo:
    """Metadados de uma imagem embutida na página."""
    __slots__ = ("nome", "largura_px", "altura_px", "espaco_cor", "bpc", "dpi_efetivo")

    def __init__(
        self,
        nome: str,
        largura_px: int,
        altura_px: int,
        espaco_cor: str = "Desconhecido",
        bpc: int = 8,
        dpi_efetivo: Optional[float] = None,
    ):
        self.nome = nome
        self.largura_px = largura_px
        self.altura_px = altura_px
        self.espaco_cor = espaco_cor
        self.bpc = bpc
        self.dpi_efetivo = dpi_efetivo

    def __repr__(self):
        return f"ImagemInfo({self.nome}: {self.largura_px}x{self.altura_px}px, {self.espaco_cor}, DPI~{self.dpi_efetivo})"


class Pagina:
    """Representa uma página de documento PDF com caixas e recursos."""

    def __init__(self, doc: "PdfReader", indice: int, raw_dict: dict):
        self.doc = doc
        self.indice = indice
        self.raw_dict = raw_dict

        # Caixas de dimensão
        mb = doc._resolver_objeto(raw_dict.get("/MediaBox"))
        self.mediabox = Caixa.de_lista(mb)

        cb = doc._resolver_objeto(raw_dict.get("/CropBox"))
        self.cropbox = Caixa.de_lista(cb, padrao=self.mediabox)

        tb = doc._resolver_objeto(raw_dict.get("/TrimBox"))
        self.trimbox = Caixa.de_lista(tb, padrao=self.cropbox)

        bb = doc._resolver_objeto(raw_dict.get("/BleedBox"))
        self.bleedbox = Caixa.de_lista(bb, padrao=self.cropbox)

        rot = doc._resolver_objeto(raw_dict.get("/Rotate", 0))
        self.rotacao = int(rot or 0) % 360

        # Largura e altura efetivas levando em conta a rotação
        if self.rotacao in (90, 270):
            self.largura_pt = self.trimbox.height
            self.altura_pt = self.trimbox.width
        else:
            self.largura_pt = self.trimbox.width
            self.altura_pt = self.trimbox.height

        self.largura_m = self.largura_pt / PT_POR_M
        self.altura_m = self.altura_pt / PT_POR_M

    def obter_conteudo_bruto(self) -> bytes:
        """Obtém o stream de conteúdo descompactado da página."""
        contents_ref = self.raw_dict.get("/Contents")
        if not contents_ref:
            return b""

        contents_obj = self.doc._resolver_objeto(contents_ref)
        if isinstance(contents_obj, list):
            # Múltiplos streams concatenados
            partes = []
            for item in contents_obj:
                stream_obj = self.doc._resolver_objeto(item)
                if isinstance(stream_obj, PdfStream):
                    partes.append(self.doc._descompactar_stream_obj(stream_obj))
            return b"\n".join(partes)

        if isinstance(contents_obj, PdfStream):
            return self.doc._descompactar_stream_obj(contents_obj)

        return b""

    def listar_imagens(self) -> List[ImagemInfo]:
        """Inspeciona o dicionário de recursos (/Resources /XObject) procurando imagens."""
        imagens = []
        resources = self.doc._resolver_objeto(self.raw_dict.get("/Resources", {}))
        if not isinstance(resources, dict):
            return imagens

        xobjects = self.doc._resolver_objeto(resources.get("/XObject", {}))
        if not isinstance(xobjects, dict):
            return imagens

        for nome, xobj_ref in xobjects.items():
            xobj = self.doc._resolver_objeto(xobj_ref)
            if not isinstance(xobj, PdfStream):
                continue
            hdr = xobj.header
            subtype = self.doc._resolver_objeto(hdr.get("/Subtype"))
            if str(subtype) in ("/Image", "Image"):
                w = int(self.doc._resolver_objeto(hdr.get("/Width", 0)))
                h = int(self.doc._resolver_objeto(hdr.get("/Height", 0)))
                cs = str(self.doc._resolver_objeto(hdr.get("/ColorSpace", "Desconhecido")))
                bpc = int(self.doc._resolver_objeto(hdr.get("/BitsPerComponent", 8)))

                # Estimativa de DPI proporcional em relação à página
                dpi_efetivo = None
                if self.largura_pt > 0 and w > 0:
                    dpi_efetivo = round((w / (self.largura_pt / 72.0)), 1)

                imagens.append(ImagemInfo(str(nome), w, h, cs, bpc, dpi_efetivo))

        return imagens


def abrir_pdf(caminho_ou_dados: Union[str, os.PathLike, bytes]) -> PdfReader:
    """Abre um documento PDF para leitura estrutural."""
    return PdfReader(caminho_ou_dados)


class PdfReader:

    """Leitor de arquivos PDF autônomo e sem dependências externas."""

    def __init__(self, caminho_ou_dados: Union[str, os.PathLike, bytes]):
        if isinstance(caminho_ou_dados, (str, os.PathLike)):
            caminho_p = pathlib.Path(caminho_ou_dados)
            self.caminho = str(caminho_p)
            self.dados = caminho_p.read_bytes()
        else:
            self.caminho = "<memoria>"
            self.dados = bytes(caminho_ou_dados)

        self.length = len(self.dados)
        self.xref_offsets: Dict[int, int] = {}       # num_obj -> file_offset
        self.stream_xref: Dict[int, Tuple[int, int]] = {}  # num_obj -> (stream_obj_num, index)
        self.cache_objetos: Dict[int, Any] = {}
        self.trailer: dict = {}
        self.paginas: List[Pagina] = []

        self._carregar_xref()
        self._carregar_paginas()

    def fechar(self):
        self.dados = b""
        self.cache_objetos.clear()
        self.paginas.clear()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.fechar()

    @property
    def num_paginas(self) -> int:
        return len(self.paginas)

    def obter_pagina(self, idx: int) -> Pagina:
        if 0 <= idx < len(self.paginas):
            return self.paginas[idx]
        raise IndexError(f"Página {idx} fora dos limites (total: {len(self.paginas)})")

    def _localizar_startxref(self) -> int:
        """Encontra a posição do último startxref no arquivo."""
        busca_inicio = max(0, self.length - 4096)
        bloco = self.dados[busca_inicio:]
        matches = list(re.finditer(rb"startxref\s+(\d+)", bloco))
        if not matches:
            raise ValueError(f"Não foi possível localizar o 'startxref' no arquivo PDF: {self.caminho}")
        return int(matches[-1].group(1))

    def _carregar_xref(self):
        """Carrega a tabela de referências cruzadas seguindo a cadeia /Prev."""
        offset = self._localizar_startxref()
        visitados = set()

        while offset and offset not in visitados:
            visitados.add(offset)
            tok = PdfTokenizer(self.dados, offset)
            palavra = tok.ler_token()

            if palavra == "xref":
                # Tabela tradicional de xref
                offset = self._ler_tabela_xref(tok)
            elif isinstance(palavra, str) and palavra.isdigit():
                # Possível XRef Stream (PDF 1.5+)
                gen = tok.ler_token()
                obj_kw = tok.ler_token()
                if obj_kw == "obj":
                    dicionario = parse_objeto(tok)
                    if isinstance(dicionario, dict) and str(dicionario.get("/Type")) in ("/XRef", "XRef"):
                        offset = self._ler_stream_xref(tok, dicionario)
                    else:
                        break
                else:
                    break
            else:
                break

    def _ler_tabela_xref(self, tok: PdfTokenizer) -> Optional[int]:
        """Lê as seções da tabela de xref tradicional."""
        while True:
            t1 = tok.ler_token()
            if t1 == "trailer" or t1 is None:
                break

            # Se for número de objeto inicial
            if not (isinstance(t1, str) and t1.isdigit()):
                break

            start_obj = int(t1)
            t2 = tok.ler_token()
            if not (isinstance(t2, str) and t2.isdigit()):
                break
            count = int(t2)

            for i in range(count):
                tok.pular_espacos_e_comentarios()
                linha = self.dados[tok.pos:tok.pos + 20]
                tok.pos += 20
                partes = linha.split()
                if len(partes) >= 3:
                    off = int(partes[0])
                    tipo = partes[2].decode("ascii", errors="ignore")
                    num_obj = start_obj + i
                    if tipo == "n" and num_obj not in self.xref_offsets:
                        self.xref_offsets[num_obj] = off

        # Lê o trailer
        t_obj = parse_objeto(tok)
        if isinstance(t_obj, dict):
            for k, v in t_obj.items():
                if k not in self.trailer:
                    self.trailer[k] = v
            prev = t_obj.get("/Prev")
            return int(prev) if prev else None
        return None

    def _ler_stream_xref(self, tok: PdfTokenizer, header: dict) -> Optional[int]:
        """Lê uma tabela xref em formato de stream (/Type /XRef)."""
        for k, v in header.items():
            if k not in self.trailer:
                self.trailer[k] = v

        stream_bytes = self._ler_corpo_stream(tok, header)
        descompactado = descompactar_stream(
            stream_bytes,
            header.get("/Filter"),
            header.get("/DecodeParms"),
        )

        w = header.get("/W", [1, 2, 1])
        w1, w2, w3 = int(w[0]), int(w[1]), int(w[2])
        entry_size = w1 + w2 + w3

        index_arr = header.get("/Index", [0, header.get("/Size", 0)])
        if len(index_arr) % 2 != 0:
            index_arr = [0, header.get("/Size", 0)]

        stream_pos = 0
        for i in range(0, len(index_arr), 2):
            start_num = int(index_arr[i])
            count = int(index_arr[i + 1])

            for num in range(start_num, start_num + count):
                if stream_pos + entry_size > len(descompactado):
                    break
                entry = descompactado[stream_pos:stream_pos + entry_size]
                stream_pos += entry_size

                f1 = int.from_bytes(entry[:w1], "big") if w1 > 0 else 1
                f2 = int.from_bytes(entry[w1:w1 + w2], "big") if w2 > 0 else 0
                f3 = int.from_bytes(entry[w1 + w2:w1 + w2 + w3], "big") if w3 > 0 else 0

                if f1 == 1:  # objeto normal (f2 = offset)
                    if num not in self.xref_offsets:
                        self.xref_offsets[num] = f2
                elif f1 == 2:  # objeto compactado em stream (f2 = num_stream, f3 = indice)
                    if num not in self.stream_xref:
                        self.stream_xref[num] = (f2, f3)

        prev = header.get("/Prev")
        return int(prev) if prev else None

    def _ler_corpo_stream(self, tok: PdfTokenizer, header: dict) -> bytes:
        """Extrai os bytes entre 'stream' e 'endstream'."""
        # Encontra a palavra 'stream'
        idx = self.dados.find(b"stream", tok.pos)
        if idx == -1:
            return b""
        idx += 6
        if self.dados[idx:idx + 2] == b"\r\n":
            idx += 2
        elif self.dados[idx:idx + 1] in (b"\n", b"\r"):
            idx += 1

        length = self._resolver_objeto(header.get("/Length"))
        if isinstance(length, int) and length >= 0 and idx + length <= self.length:
            return self.dados[idx:idx + length]

        # Fallback: busca por 'endstream'
        end_idx = self.dados.find(b"endstream", idx)
        if end_idx != -1:
            raw = self.dados[idx:end_idx]
            if raw.endswith(b"\r\n"):
                return raw[:-2]
            if raw.endswith(b"\n") or raw.endswith(b"\r"):
                return raw[:-1]
            return raw
        return b""

    def _descompactar_stream_obj(self, stream_obj: PdfStream) -> bytes:
        return descompactar_stream(
            stream_obj.raw_bytes,
            self._resolver_objeto(stream_obj.header.get("/Filter")),
            self._resolver_objeto(stream_obj.header.get("/DecodeParms")),
        )

    def _resolver_objeto(self, obj: Any) -> Any:
        """Se o objeto for uma referência indireta (PdfRef), carrega o valor real."""
        if isinstance(obj, PdfRef):
            return self.obter_objeto(obj.num)
        return obj

    def obter_objeto(self, num_obj: int) -> Any:
        """Carrega e armazena em cache um objeto indireto pelo seu número."""
        if num_obj in self.cache_objetos:
            return self.cache_objetos[num_obj]

        # 1. Objeto normal por offset
        if num_obj in self.xref_offsets:
            off = self.xref_offsets[num_obj]
            tok = PdfTokenizer(self.dados, off)
            t_num = tok.ler_token()
            t_gen = tok.ler_token()
            t_obj = tok.ler_token()
            if t_obj != "obj":
                return None

            obj_val = parse_objeto(tok)

            # Verifica se há stream associado
            tok.pular_espacos_e_comentarios()
            if self.dados[tok.pos:tok.pos + 6] == b"stream" and isinstance(obj_val, dict):
                raw_bytes = self._ler_corpo_stream(tok, obj_val)
                obj_val = PdfStream(obj_val, raw_bytes)

            self.cache_objetos[num_obj] = obj_val
            return obj_val

        # 2. Objeto dentro de stream de objetos (/ObjStm)
        if num_obj in self.stream_xref:
            stm_num, idx = self.stream_xref[num_obj]
            stream_obj = self.obter_objeto(stm_num)
            if isinstance(stream_obj, PdfStream):
                dados_stm = self._descompactar_stream_obj(stream_obj)
                n_objs = int(self._resolver_objeto(stream_obj.header.get("/N", 0)))
                primeiro_offset = int(self._resolver_objeto(stream_obj.header.get("/First", 0)))

                tok_stm = PdfTokenizer(dados_stm)
                offsets = []
                for _ in range(n_objs):
                    num = int(tok_stm.ler_token())
                    off = int(tok_stm.ler_token())
                    offsets.append((num, primeiro_offset + off))

                for o_num, o_off in offsets:
                    t_sub = PdfTokenizer(dados_stm, o_off)
                    self.cache_objetos[o_num] = parse_objeto(t_sub)

                return self.cache_objetos.get(num_obj)

        return None

    def _carregar_paginas(self):
        """Navega na árvore de páginas /Pages e coleta todas as páginas do documento."""
        root_ref = self.trailer.get("/Root")
        root = self._resolver_objeto(root_ref)
        if not isinstance(root, dict):
            return

        pages_ref = root.get("/Pages")
        pages_node = self._resolver_objeto(pages_ref)
        if not isinstance(pages_node, dict):
            return

        self._visitar_no_paginas(pages_node)

    def _visitar_no_paginas(self, no: dict, heranca: Optional[dict] = None):
        """Travessia recursiva nos nós /Kids da árvore de páginas."""
        ctx = dict(heranca or {})
        for k in ("/MediaBox", "/CropBox", "/Resources", "/Rotate"):
            if k in no:
                ctx[k] = no[k]

        tipo = str(self._resolver_objeto(no.get("/Type")))
        if tipo in ("/Pages", "Pages"):
            kids = self._resolver_objeto(no.get("/Kids", []))
            if isinstance(kids, list):
                for kid_ref in kids:
                    kid_obj = self._resolver_objeto(kid_ref)
                    if isinstance(kid_obj, dict):
                        self._visitar_no_paginas(kid_obj, ctx)
        elif tipo in ("/Page", "Page"):
            # Mescla herança
            pagina_dict = dict(ctx)
            pagina_dict.update(no)
            self.paginas.append(Pagina(self, len(self.paginas), pagina_dict))
