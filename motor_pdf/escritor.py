"""
motor_pdf/escritor.py — Gerador e serializador de arquivos PDF compatível com ISO 32000-1.

Implementa:
  - Tabela de objetos indiretos com numeração sequencial.
  - Tabela clássica de referências cruzadas (xref) e trailer padrão.
  - Importação de objetos e streams com remapeamento automático de referências e deduplicação.
  - Preservação cega de bytes de streams comprimidos (Flate, DCT, JBIG2, etc.).
"""

from __future__ import annotations

import io
import os
import zlib
from typing import Any, BinaryIO, Dict, List, Optional, Set, Tuple, Union

from .leitor import PdfReader
from .sintaxe import PdfArray, PdfDict, PdfName, PdfRef, PdfStream, PdfString


class PdfWriter:
    """Montador e gravador de documentos PDF em conformidade com ISO 32000-1."""

    def __init__(self, versao: str = "1.6"):
        self.versao = versao
        self.objetos: Dict[int, Any] = {}
        self._proximo_id: int = 1

        # Mapeamento para deduplicação de objetos importados:
        # (id_leitor, num_obj_antigo) -> novo_id
        self._mapa_importados: Dict[Tuple[int, int], int] = {}

        # Catálogo raiz e árvore de páginas
        self.catalogo_id = self.alocar_id()
        self.paginas_id = self.alocar_id()
        self.lista_paginas: List[PdfRef] = []
        self.objetos[self.catalogo_id] = {
            PdfName("/Type"): PdfName("/Catalog"),
            PdfName("/Pages"): PdfRef(self.paginas_id, 0),
        }

        self.info: Dict[str, Any] = {
            "/Producer": PdfString(b"Antigravity Native Industrial PDF Engine (ISO 32000-1)"),
            "/Creator": PdfString(b"Sistema Autonomo de Producao Grafica"),
        }

    def alocar_id(self) -> int:
        """Reserva um novo identificador sequencial de objeto indireto."""
        nid = self._proximo_id
        self._proximo_id += 1
        return nid

    def adicionar_objeto(self, obj: Any, num: Optional[int] = None) -> PdfRef:
        """Registra um objeto indireto na tabela do escritor."""
        if num is None:
            num = self.alocar_id()
        self.objetos[num] = obj
        return PdfRef(num, 0)

    def importar_objeto(self, leitor: PdfReader, obj_ou_ref: Any) -> Any:
        """
        Importa recursivamente um objeto ou referência indireta de outro PdfReader,
        preservando streams brutos e remapeando os identificadores sem colisão.
        """
        if obj_ou_ref is None:
            return None

        # Caso 1: Referência Indireta
        if isinstance(obj_ou_ref, PdfRef):
            chave = (id(leitor), obj_ou_ref.num)
            if chave in self._mapa_importados:
                return PdfRef(self._mapa_importados[chave], 0)

            # Reserva o ID novo antes de resolver para evitar loop em referências circulares
            novo_id = self.alocar_id()
            self._mapa_importados[chave] = novo_id

            conteudo = leitor.obter_objeto(obj_ou_ref.num)
            objeto_clonado = self.importar_objeto(leitor, conteudo)
            self.objetos[novo_id] = objeto_clonado
            return PdfRef(novo_id, 0)

        # Caso 2: Stream de dados (PdfStream)
        if isinstance(obj_ou_ref, PdfStream):
            # Clona cabeçalho recursivamente
            novo_header = {}
            for k, v in obj_ou_ref.header.items():
                chave_nome = str(k) if str(k).startswith("/") else "/" + str(k)
                novo_header[PdfName(chave_nome)] = self.importar_objeto(leitor, v)

            # Os bytes brutos do stream são preservados rigorosamente sem descompressão
            return PdfStream(novo_header, obj_ou_ref.raw_bytes)

        # Caso 3: Dicionário
        if isinstance(obj_ou_ref, dict):
            novo_dict = {}
            for k, v in obj_ou_ref.items():
                chave_nome = str(k) if str(k).startswith("/") else "/" + str(k)
                novo_dict[PdfName(chave_nome)] = self.importar_objeto(leitor, v)
            return novo_dict

        # Caso 4: Array / Lista
        if isinstance(obj_ou_ref, list):
            return [self.importar_objeto(leitor, item) for item in obj_ou_ref]

        # Caso 5: Tipos primitivos imutáveis
        return obj_ou_ref

    def adicionar_pagina(
        self,
        largura_pt: float,
        altura_pt: float,
        recursos: dict,
        conteudo_bytes: bytes,
    ) -> PdfRef:
        """Cria e adiciona uma nova página (/Type /Page) ao documento montado."""
        page_id = self.alocar_id()
        contents_id = self.alocar_id()

        # Comprime o stream de comandos da página mestra com zlib
        stream_comprimido = zlib.compress(conteudo_bytes, level=6)
        contents_stream = PdfStream(
            {
                PdfName("/Filter"): PdfName("/FlateDecode"),
                PdfName("/Length"): len(stream_comprimido),
            },
            stream_comprimido,
        )
        self.objetos[contents_id] = contents_stream

        page_dict = {
            PdfName("/Type"): PdfName("/Page"),
            PdfName("/Parent"): PdfRef(self.paginas_id, 0),
            PdfName("/MediaBox"): [0.0, 0.0, float(largura_pt), float(altura_pt)],
            PdfName("/Resources"): recursos,
            PdfName("/Contents"): PdfRef(contents_id, 0),
        }
        self.objetos[page_id] = page_dict

        ref_pag = PdfRef(page_id, 0)
        self.lista_paginas.append(ref_pag)
        return ref_pag

    def adicionar_imagem(self, dados_ou_img: Union[bytes, Any]) -> Tuple[PdfRef, int, int]:
        """
        Adiciona uma imagem ao documento como /XObject /Image e retorna (PdfRef, largura_px, altura_px).
        Preserva bytes JPEG nativos com /DCTDecode ou comprime RGB com /FlateDecode.
        """
        from PIL import Image

        if isinstance(dados_ou_img, bytes):
            if dados_ou_img.startswith(b"\xff\xd8"):
                # JPEG direto: não precisa re-comprimir
                with Image.open(io.BytesIO(dados_ou_img)) as im:
                    w, h = im.size
                img_id = self.alocar_id()
                hdr = {
                    PdfName("/Type"): PdfName("/XObject"),
                    PdfName("/Subtype"): PdfName("/Image"),
                    PdfName("/Width"): w,
                    PdfName("/Height"): h,
                    PdfName("/ColorSpace"): PdfName("/DeviceRGB"),
                    PdfName("/BitsPerComponent"): 8,
                    PdfName("/Filter"): PdfName("/DCTDecode"),
                    PdfName("/Length"): len(dados_ou_img),
                }
                self.objetos[img_id] = PdfStream(hdr, dados_ou_img)
                return PdfRef(img_id, 0), w, h
            im = Image.open(io.BytesIO(dados_ou_img))
        else:
            im = dados_ou_img

        im_rgb = im.convert("RGB")
        w, h = im_rgb.size
        raw_rgb = im_rgb.tobytes()
        comp = zlib.compress(raw_rgb, level=6)
        img_id = self.alocar_id()
        hdr = {
            PdfName("/Type"): PdfName("/XObject"),
            PdfName("/Subtype"): PdfName("/Image"),
            PdfName("/Width"): w,
            PdfName("/Height"): h,
            PdfName("/ColorSpace"): PdfName("/DeviceRGB"),
            PdfName("/BitsPerComponent"): 8,
            PdfName("/Filter"): PdfName("/FlateDecode"),
            PdfName("/Length"): len(comp),
        }
        self.objetos[img_id] = PdfStream(hdr, comp)
        return PdfRef(img_id, 0), w, h

    def salvar(self, destino: Union[str, os.PathLike, BinaryIO]) -> bytes:
        """Serializa o documento PDF final e grava em arquivo ou fluxo binário."""
        # 1. Configura a árvore /Pages
        self.objetos[self.paginas_id] = {
            PdfName("/Type"): PdfName("/Pages"),
            PdfName("/Kids"): list(self.lista_paginas),
            PdfName("/Count"): len(self.lista_paginas),
        }

        # 2. Configura o catálogo raiz /Catalog
        cat_dict = self.objetos.setdefault(self.catalogo_id, {})
        cat_dict[PdfName("/Type")] = PdfName("/Catalog")
        cat_dict[PdfName("/Pages")] = PdfRef(self.paginas_id, 0)
        self.objetos[self.catalogo_id] = cat_dict

        # 3. Informações do documento /Info
        info_id = self.alocar_id()
        self.objetos[info_id] = {PdfName(k): v for k, v in self.info.items()}

        buf = io.BytesIO()

        # Cabeçalho padrão ISO 32000
        buf.write(f"%PDF-{self.versao}\n".encode("ascii"))
        buf.write(b"%\xe2\xe3\xcf\xd3\n")

        # Tabela de offsets
        total_objs = max(self.objetos.keys())
        offsets: Dict[int, int] = {}

        # Grava os objetos em ordem numérica
        for num in range(1, total_objs + 1):
            if num not in self.objetos:
                continue
            offsets[num] = buf.tell()
            buf.write(f"{num} 0 obj\n".encode("ascii"))
            self._serializar_objeto(buf, self.objetos[num])
            buf.write(b"\nendobj\n")

        # Início da tabela de referências cruzadas
        xref_offset = buf.tell()
        buf.write(b"xref\n")
        buf.write(f"0 {total_objs + 1}\n".encode("ascii"))
        buf.write(b"0000000000 65535 f \n")

        for num in range(1, total_objs + 1):
            if num in offsets:
                buf.write(f"{offsets[num]:010d} 00000 n \n".encode("ascii"))
            else:
                buf.write(b"0000000000 00000 f \n")

        # Trailer
        trailer_dict = {
            PdfName("/Size"): total_objs + 1,
            PdfName("/Root"): PdfRef(self.catalogo_id, 0),
            PdfName("/Info"): PdfRef(info_id, 0),
        }

        buf.write(b"trailer\n")
        self._serializar_objeto(buf, trailer_dict)
        buf.write(b"\n")
        buf.write(f"startxref\n{xref_offset}\n%%EOF\n".encode("ascii"))

        dados_pdf = buf.getvalue()

        if isinstance(destino, (str, os.PathLike)):
            with open(destino, "wb") as f:
                f.write(dados_pdf)
        elif hasattr(destino, "write"):
            destino.write(dados_pdf)

        return dados_pdf

    def _serializar_objeto(self, buf: BinaryIO, obj: Any):
        """Formata e serializa um tipo primitivo ou estrutura PDF para bytes."""
        if obj is None:
            buf.write(b"null")
        elif isinstance(obj, bool):
            buf.write(b"true" if obj else b"false")
        elif isinstance(obj, (int, float)):
            if isinstance(obj, int) or obj.is_integer():
                buf.write(str(int(obj)).encode("ascii"))
            else:
                s = f"{obj:.6f}".rstrip("0").rstrip(".")
                buf.write(s.encode("ascii"))
        elif isinstance(obj, PdfRef):
            buf.write(f"{obj.num} {obj.gen} R".encode("ascii"))
        elif isinstance(obj, PdfName):
            buf.write(str(obj).encode("ascii"))
        elif isinstance(obj, PdfString):
            # Escapa parênteses e barras invertidas
            escapado = bytearray(b"(")
            for b in obj:
                if b in (0x28, 0x29, 0x5C):  # ( ) \
                    escapado.append(0x5C)
                escapado.append(b)
            escapado.append(0x29)
            buf.write(escapado)
        elif isinstance(obj, (bytes, bytearray)):
            # String literal padrão
            buf.write(b"(" + bytes(obj) + b")")
        elif isinstance(obj, str):
            if obj.startswith("/"):
                buf.write(obj.encode("ascii"))
            else:
                # String literal em latin1
                limpo = obj.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
                buf.write(f"({limpo})".encode("latin1", errors="replace"))
        elif isinstance(obj, list):
            buf.write(b"[")
            for idx, item in enumerate(obj):
                if idx > 0:
                    buf.write(b" ")
                self._serializar_objeto(buf, item)
            buf.write(b"]")
        elif isinstance(obj, dict):
            buf.write(b"<<\n")
            for k, v in obj.items():
                nome_k = str(k) if str(k).startswith("/") else "/" + str(k)
                buf.write(f"  {nome_k} ".encode("ascii"))
                self._serializar_objeto(buf, v)
                buf.write(b"\n")
            buf.write(b">>")
        elif isinstance(obj, PdfStream):
            # Garante que o /Length está atualizado
            obj.header[PdfName("/Length")] = len(obj.raw_bytes)
            self._serializar_objeto(buf, obj.header)
            buf.write(b"\nstream\r\n")
            buf.write(obj.raw_bytes)
            buf.write(b"\r\nendstream")
        else:
            buf.write(str(obj).encode("latin1", errors="replace"))
