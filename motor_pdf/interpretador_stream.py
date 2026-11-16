"""
motor_pdf/interpretador_stream.py — Interpretador de fluxos de operadores gráficos PDF.

Mede a caixa de tinta vetorial real (caixa_da_arte) sem rasterização:
  - Mantém pilha de estados gráficos (CTM, cores, opacidade e clipping box).
  - Avalia operadores de caminho (m, l, c, v, y, h, re).
  - Executa máscaras de recorte (W, W*) e interseção exata de BoundingBox.
  - Avalia XObjects (Do) para imagens e formulários recursivos (/Subtype /Form).
  - Estima limites de blocos de texto (BT, ET, Tf, Tm, Td, Tj, TJ).
  - Desconsidera franjas brancas de exportação conforme regra do chão de fábrica (10%).
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple, Union

from .geometria import BoundingBox, Matriz2D, adicionar_bezier_ao_bbox
from .leitor import Caixa, Pagina, PdfReader
from .sintaxe import PdfDict, PdfName, PdfRef, PdfStream, PdfString

# Expressão regular compilada para tokenização em alta velocidade de streams PDF
PADRAO_TOKEN_STREAM = re.compile(
    rb'%[^\r\n]*'                               # Comentários (% ...)
    rb'|/[^ \t\r\n\x0c\x00/()<>\[\]%]+'        # Nomes (/Nome)
    rb'|\((?:\\.|[^()\\])*\)'                  # Strings literais (...)
    rb'|<[0-9A-Fa-f\s]*>'                      # Strings hexadecimais <...>
    rb'|\[|\]|<<|>>'                           # Delimitadores de array e dicionário
    rb'|[^\s()<>\[\]%/]+'                      # Números e operadores
)

MARCADOR_ARRAY = object()
MARCADOR_DICT = object()


class EstadoGrafico:
    """Estado gráfico ativo do interpretador PDF salvo e restaurado por q / Q."""
    __slots__ = ("ctm", "clip_bbox", "opacidade", "cor_preenchimento", "cor_traco")

    def __init__(
        self,
        ctm: Optional[Matriz2D] = None,
        clip_bbox: Optional[BoundingBox] = None,
        opacidade: float = 1.0,
        cor_preenchimento: Optional[Tuple[float, ...]] = None,
        cor_traco: Optional[Tuple[float, ...]] = None,
    ):
        self.ctm = ctm if ctm is not None else Matriz2D.identidade()
        self.clip_bbox = clip_bbox
        self.opacidade = opacidade
        self.cor_preenchimento = cor_preenchimento
        self.cor_traco = cor_traco

    def clonar(self) -> "EstadoGrafico":
        clip_copia = None
        if self.clip_bbox is not None and not self.clip_bbox.vazio:
            clip_copia = BoundingBox(self.clip_bbox.x0, self.clip_bbox.y0, self.clip_bbox.x1, self.clip_bbox.y1)
        return EstadoGrafico(
            ctm=Matriz2D(self.ctm.a, self.ctm.b, self.ctm.c, self.ctm.d, self.ctm.e, self.ctm.f),
            clip_bbox=clip_copia,
            opacidade=self.opacidade,
            cor_preenchimento=self.cor_preenchimento,
            cor_traco=self.cor_traco,
        )


class InterpretadorStream:
    """Interpretador vetorial dos operadores gráficos contidos no stream da página."""

    def __init__(
        self,
        stream_bytes: bytes,
        recursos: Optional[dict] = None,
        ctm_inicial: Optional[Matriz2D] = None,
        clip_inicial: Optional[BoundingBox] = None,
        doc: Optional[PdfReader] = None,
        profundidade: int = 0,
    ):
        self.stream_bytes = stream_bytes
        self.recursos = recursos or {}
        self.doc = doc
        self.profundidade = profundidade

        self.estado = EstadoGrafico(ctm=ctm_inicial, clip_bbox=clip_inicial)
        self.pilha_estados: List[EstadoGrafico] = []

        # Bounding box acumulador da tinta desenhada/impressa
        self.acumulador_tinta = BoundingBox()

        # Caminho corrente sendo construído
        self.path_bbox = BoundingBox()
        self.cur_x: float = 0.0
        self.cur_y: float = 0.0
        self.start_x: float = 0.0
        self.start_y: float = 0.0
        self.clip_pendente: bool = False

        # Estado de texto (BT / ET)
        self.em_texto: bool = False
        self.tm = Matriz2D.identidade()
        self.tlm = Matriz2D.identidade()
        self.fonte_tamanho: float = 12.0

        # Conteúdo opcional (OC / camadas)
        self.camada_oculta_profundidade: int = 0

        # Pilha de operandos
        self.pilha_op: List[Any] = []

    def executar(self) -> BoundingBox:
        """Executa a interpretação de todos os operadores do stream e retorna a caixa de tinta."""
        if not self.stream_bytes:
            return self.acumulador_tinta

        tokens = PADRAO_TOKEN_STREAM.findall(self.stream_bytes)
        idx = 0
        total = len(tokens)

        while idx < total:
            tok = tokens[idx]
            idx += 1

            # Ignora comentários
            if tok.startswith(b"%"):
                continue

            # Delimitador de início de array
            if tok == b"[":
                self.pilha_op.append(MARCADOR_ARRAY)
                continue

            # Delimitador de fim de array
            if tok == b"]":
                itens = []
                while self.pilha_op:
                    topo = self.pilha_op.pop()
                    if topo is MARCADOR_ARRAY:
                        break
                    itens.append(topo)
                itens.reverse()
                self.pilha_op.append(itens)
                continue

            # Delimitador de início de dicionário
            if tok == b"<<":
                self.pilha_op.append(MARCADOR_DICT)
                continue

            # Delimitador de fim de dicionário
            if tok == b">>":
                d_itens = []
                while self.pilha_op:
                    topo = self.pilha_op.pop()
                    if topo is MARCADOR_DICT:
                        break
                    d_itens.append(topo)
                d_itens.reverse()
                d_obj = {}
                for k in range(0, len(d_itens) - 1, 2):
                    chave = d_itens[k]
                    if isinstance(chave, PdfName):
                        chave = str(chave)
                    elif isinstance(chave, str) and not chave.startswith("/"):
                        chave = "/" + chave
                    d_obj[chave] = d_itens[k + 1]
                self.pilha_op.append(d_obj)
                continue

            # Nomes PDF (/Nome)
            if tok.startswith(b"/"):
                nome_str = tok.decode("latin1", errors="ignore")
                self.pilha_op.append(PdfName(nome_str))
                continue

            # Strings literais (...) ou hexadecimais <...>
            if tok.startswith(b"(") or tok.startswith(b"<"):
                # Decodifica string básica
                self.pilha_op.append(tok)
                continue

            # Tenta interpretar como número (inteiro ou float)
            c = tok[0]
            if (0x30 <= c <= 0x39) or c in (0x2D, 0x2B, 0x2E):  # 0-9, '-', '+', '.'
                try:
                    val = float(tok)
                    self.pilha_op.append(val)
                    continue
                except ValueError:
                    pass

            # Caso contrário, é um operador PDF
            op = tok.decode("latin1", errors="ignore")
            self._executar_operador(op)

        return self.acumulador_tinta

    def _pop_numeros(self, n: int) -> List[float]:
        """Extrai n números do topo da pilha de operandos."""
        nums = []
        while self.pilha_op and len(nums) < n:
            val = self.pilha_op.pop()
            if isinstance(val, (int, float)):
                nums.append(float(val))
            else:
                nums.append(0.0)
        nums.reverse()
        while len(nums) < n:
            nums.insert(0, 0.0)
        return nums

    def _pop_arg(self) -> Any:
        """Extrai um argumento do topo da pilha de operandos."""
        if self.pilha_op:
            return self.pilha_op.pop()
        return None

    def _executar_operador(self, op: str):
        """Interpreta e executa um único operador PDF."""
        # Se estivermos dentro de uma camada oculta, ignora pintura e caminhos
        if self.camada_oculta_profundidade > 0:
            if op == "EMC":
                self.camada_oculta_profundidade -= 1
            elif op in ("BMC", "BDC"):
                self.camada_oculta_profundidade += 1
            return

        # ---- 1. Estado Gráfico e Matriz ----
        if op == "q":
            if len(self.pilha_estados) < 256:
                self.pilha_estados.append(self.estado.clonar())
        elif op == "Q":
            if self.pilha_estados:
                self.estado = self.pilha_estados.pop()
        elif op == "cm":
            nums = self._pop_numeros(6)
            m_nova = Matriz2D(nums[0], nums[1], nums[2], nums[3], nums[4], nums[5])
            self.estado.ctm = m_nova.multiplicar(self.estado.ctm)

        # ---- 2. Construção de Caminho ----
        elif op == "m":
            x, y = self._pop_numeros(2)
            px, py = self.estado.ctm.transformar_ponto(x, y)
            self.cur_x, self.cur_y = px, py
            self.start_x, self.start_y = px, py
            self.path_bbox.adicionar_ponto(px, py)
        elif op == "l":
            x, y = self._pop_numeros(2)
            px, py = self.estado.ctm.transformar_ponto(x, y)
            self.cur_x, self.cur_y = px, py
            self.path_bbox.adicionar_ponto(px, py)
        elif op == "c":
            x1, y1, x2, y2, x3, y3 = self._pop_numeros(6)
            p0 = (self.cur_x, self.cur_y)
            p1 = self.estado.ctm.transformar_ponto(x1, y1)
            p2 = self.estado.ctm.transformar_ponto(x2, y2)
            p3 = self.estado.ctm.transformar_ponto(x3, y3)
            adicionar_bezier_ao_bbox(self.path_bbox, p0[0], p0[1], p1[0], p1[1], p2[0], p2[1], p3[0], p3[1])
            self.cur_x, self.cur_y = p3
        elif op == "v":
            x2, y2, x3, y3 = self._pop_numeros(4)
            p0 = (self.cur_x, self.cur_y)
            p1 = (self.cur_x, self.cur_y)
            p2 = self.estado.ctm.transformar_ponto(x2, y2)
            p3 = self.estado.ctm.transformar_ponto(x3, y3)
            adicionar_bezier_ao_bbox(self.path_bbox, p0[0], p0[1], p1[0], p1[1], p2[0], p2[1], p3[0], p3[1])
            self.cur_x, self.cur_y = p3
        elif op == "y":
            x1, y1, x3, y3 = self._pop_numeros(4)
            p0 = (self.cur_x, self.cur_y)
            p1 = self.estado.ctm.transformar_ponto(x1, y1)
            p2 = self.estado.ctm.transformar_ponto(x3, y3)
            p3 = self.estado.ctm.transformar_ponto(x3, y3)
            adicionar_bezier_ao_bbox(self.path_bbox, p0[0], p0[1], p1[0], p1[1], p2[0], p2[1], p3[0], p3[1])
            self.cur_x, self.cur_y = p3
        elif op == "h":
            self.cur_x, self.cur_y = self.start_x, self.start_y
        elif op == "re":
            x, y, w, h = self._pop_numeros(4)
            p1 = self.estado.ctm.transformar_ponto(x, y)
            p2 = self.estado.ctm.transformar_ponto(x + w, y)
            p3 = self.estado.ctm.transformar_ponto(x + w, y + h)
            p4 = self.estado.ctm.transformar_ponto(x, y + h)
            self.path_bbox.adicionar_ponto(p1[0], p1[1])
            self.path_bbox.adicionar_ponto(p2[0], p2[1])
            self.path_bbox.adicionar_ponto(p3[0], p3[1])
            self.path_bbox.adicionar_ponto(p4[0], p4[1])
            self.cur_x, self.cur_y = self.start_x, self.start_y = p1

        # ---- 3. Recorte (Clipping) ----
        elif op in ("W", "W*"):
            self.clip_pendente = True

        # ---- 4. Pintura de Caminho ----
        elif op == "S":
            self._pintar(stroke=True, fill=False, fechar=False)
        elif op == "s":
            self._pintar(stroke=True, fill=False, fechar=True)
        elif op in ("f", "F", "f*"):
            self._pintar(stroke=False, fill=True, fechar=False)
        elif op in ("B", "B*"):
            self._pintar(stroke=True, fill=True, fechar=False)
        elif op in ("b", "b*"):
            self._pintar(stroke=True, fill=True, fechar=True)
        elif op == "n":
            self._terminar_caminho()

        # ---- 5. Cores e Transparência ----
        elif op == "g":
            self.estado.cor_preenchimento = (self._pop_numeros(1)[0],)
        elif op == "G":
            self.estado.cor_traco = (self._pop_numeros(1)[0],)
        elif op == "rg":
            self.estado.cor_preenchimento = tuple(self._pop_numeros(3))
        elif op == "RG":
            self.estado.cor_traco = tuple(self._pop_numeros(3))
        elif op == "k":
            self.estado.cor_preenchimento = tuple(self._pop_numeros(4))
        elif op == "K":
            self.estado.cor_traco = tuple(self._pop_numeros(4))
        elif op in ("sc", "scn"):
            # Consome componentes de cor
            self.pilha_op.clear()
        elif op in ("SC", "SCN"):
            self.pilha_op.clear()
        elif op == "gs":
            nome_gs = self._pop_arg()
            if self.recursos and nome_gs:
                self._aplicar_extgstate(str(nome_gs))

        # ---- 6. Objetos Externos (Do) ----
        elif op == "Do":
            nome_obj = self._pop_arg()
            if nome_obj:
                self._executar_do(str(nome_obj))

        # ---- 7. Texto ----
        elif op == "BT":
            self.em_texto = True
            self.tm = Matriz2D.identidade()
            self.tlm = Matriz2D.identidade()
        elif op == "ET":
            self.em_texto = False
        elif op == "Tf":
            tamanho = self._pop_numeros(1)[0]
            self.fonte_tamanho = max(0.1, tamanho)
            self._pop_arg()  # Nome da fonte
        elif op == "Tm":
            nums = self._pop_numeros(6)
            self.tm = Matriz2D(nums[0], nums[1], nums[2], nums[3], nums[4], nums[5])
            self.tlm = self.tm
        elif op in ("Td", "TD"):
            tx, ty = self._pop_numeros(2)
            m_desl = Matriz2D(1.0, 0.0, 0.0, 1.0, tx, ty)
            self.tlm = m_desl.multiplicar(self.tlm)
            self.tm = self.tlm
        elif op == "T*":
            m_desl = Matriz2D(1.0, 0.0, 0.0, 1.0, 0.0, -self.fonte_tamanho * 1.2)
            self.tlm = m_desl.multiplicar(self.tlm)
            self.tm = self.tlm
        elif op in ("Tj", "'"):
            texto = self._pop_arg()
            self._adicionar_texto_ao_bbox(texto)
        elif op == "TJ":
            array_texto = self._pop_arg()
            self._adicionar_array_texto_ao_bbox(array_texto)
        elif op == '"':
            texto = self._pop_arg()
            self._pop_numeros(2)  # aw, ac
            self._adicionar_texto_ao_bbox(texto)

        # ---- 8. Shading / Malhas ----
        elif op == "sh":
            self._pop_arg()
            if self.estado.clip_bbox is not None and not self.estado.clip_bbox.vazio:
                self.acumulador_tinta.adicionar_outro(self.estado.clip_bbox)

        # ---- 9. Conteúdo Opcional / Marcações ----
        elif op in ("BMC", "BDC"):
            # Se for /OC marcado e oculto, pode avançar camada_oculta_profundidade
            self._pop_arg()
        elif op == "EMC":
            pass

    def _aplicar_extgstate(self, nome_gs: str):
        """Lê metadados de ExtGState para detectar opacidade 0 (invisível)."""
        ext = self.recursos.get("/ExtGState")
        if not ext and self.doc:
            ext = self.doc._resolver_objeto(self.recursos.get(PdfName("/ExtGState")))
        if isinstance(ext, dict):
            gs_dict = ext.get(nome_gs) or ext.get(PdfName(nome_gs))
            if self.doc and isinstance(gs_dict, PdfRef):
                gs_dict = self.doc._resolver_objeto(gs_dict)
            if isinstance(gs_dict, dict):
                ca = gs_dict.get("/ca") or gs_dict.get(PdfName("/ca"))
                CA = gs_dict.get("/CA") or gs_dict.get(PdfName("/CA"))
                if ca is not None and float(ca) <= 0.0 and CA is not None and float(CA) <= 0.0:
                    self.estado.opacidade = 0.0
                elif ca is not None and float(ca) > 0.0:
                    self.estado.opacidade = 1.0

    def _pintar(self, stroke: bool, fill: bool, fechar: bool):
        """Pinta o caminho corrente e adiciona à caixa de tinta (respeitando recorte)."""
        if fechar:
            self.cur_x, self.cur_y = self.start_x, self.start_y

        if not self.path_bbox.vazio and self.estado.opacidade > 0.0:
            alvo = self.path_bbox
            if self.estado.clip_bbox is not None:
                alvo = alvo.intersecao(self.estado.clip_bbox)
            if not alvo.vazio:
                self.acumulador_tinta.adicionar_outro(alvo)

        if self.clip_pendente:
            self._aplicar_clip()

        self.path_bbox = BoundingBox()

    def _terminar_caminho(self):
        """Finaliza o caminho sem pintar (operador n), aplicando apenas o recorte se pendente."""
        if self.clip_pendente:
            self._aplicar_clip()
        self.path_bbox = BoundingBox()

    def _aplicar_clip(self):
        """Aplica a máscara de recorte ativa ao estado gráfico atual."""
        if not self.path_bbox.vazio:
            if self.estado.clip_bbox is None:
                self.estado.clip_bbox = BoundingBox(
                    self.path_bbox.x0, self.path_bbox.y0, self.path_bbox.x1, self.path_bbox.y1
                )
            else:
                self.estado.clip_bbox = self.estado.clip_bbox.intersecao(self.path_bbox)
        self.clip_pendente = False

    def _executar_do(self, nome_obj: str):
        """Executa a colocação de um XObject (imagem ou formulário)."""
        xobjects = self.recursos.get("/XObject")
        if not xobjects and self.doc:
            xobjects = self.doc._resolver_objeto(self.recursos.get(PdfName("/XObject")))

        obj_ref = None
        if isinstance(xobjects, dict):
            obj_ref = xobjects.get(nome_obj) or xobjects.get(PdfName(nome_obj))

        xobj = None
        if self.doc and obj_ref:
            xobj = self.doc._resolver_objeto(obj_ref)

        subtipo = None
        if isinstance(xobj, PdfStream):
            subtipo = xobj.header.get("/Subtype") or xobj.header.get(PdfName("/Subtype"))
        elif isinstance(xobj, dict):
            subtipo = xobj.get("/Subtype") or xobj.get(PdfName("/Subtype"))

        # Caso 1: Formulário XObject recursivo (/Subtype /Form)
        if str(subtipo) == "/Form" and self.profundidade < 12 and isinstance(xobj, PdfStream) and self.doc:
            m_form = Matriz2D.identidade()
            m_arr = xobj.header.get("/Matrix") or xobj.header.get(PdfName("/Matrix"))
            if m_arr:
                m_arr = self.doc._resolver_objeto(m_arr)
                if isinstance(m_arr, list) and len(m_arr) >= 6:
                    m_form = Matriz2D(float(m_arr[0]), float(m_arr[1]), float(m_arr[2]), float(m_arr[3]), float(m_arr[4]), float(m_arr[5]))

            form_ctm = m_form.multiplicar(self.estado.ctm)

            rec_form = xobj.header.get("/Resources") or xobj.header.get(PdfName("/Resources"))
            recursos_uso = self.doc._resolver_objeto(rec_form) if rec_form else self.recursos
            if not isinstance(recursos_uso, dict):
                recursos_uso = self.recursos

            form_stream = self.doc._descompactar_stream_obj(xobj)
            sub_interp = InterpretadorStream(
                stream_bytes=form_stream,
                recursos=recursos_uso,
                ctm_inicial=form_ctm,
                clip_inicial=self.estado.clip_bbox,
                doc=self.doc,
                profundidade=self.profundidade + 1,
            )
            form_bbox = sub_interp.executar()
            if not form_bbox.vazio:
                self.acumulador_tinta.adicionar_outro(form_bbox)
            return

        # Caso 2: Imagem XObject (/Subtype /Image ou fallback padrão)
        # Uma imagem em PDF ocupa o quadrado unitário [0, 0] a [1, 1] no espaço do usuário
        p1 = self.estado.ctm.transformar_ponto(0.0, 0.0)
        p2 = self.estado.ctm.transformar_ponto(1.0, 0.0)
        p3 = self.estado.ctm.transformar_ponto(1.0, 1.0)
        p4 = self.estado.ctm.transformar_ponto(0.0, 1.0)

        img_bbox = BoundingBox()
        img_bbox.adicionar_ponto(p1[0], p1[1])
        img_bbox.adicionar_ponto(p2[0], p2[1])
        img_bbox.adicionar_ponto(p3[0], p3[1])
        img_bbox.adicionar_ponto(p4[0], p4[1])

        if self.estado.clip_bbox is not None:
            img_bbox = img_bbox.intersecao(self.estado.clip_bbox)

        if not img_bbox.vazio:
            self.acumulador_tinta.adicionar_outro(img_bbox)

    def _adicionar_texto_ao_bbox(self, texto_obj: Any):
        """Estima e adiciona os limites de uma cadeia de texto ao acumulador de tinta."""
        if not texto_obj:
            return
        n_chars = 1
        if isinstance(texto_obj, (bytes, bytearray)):
            n_chars = max(1, len(texto_obj))
        elif isinstance(texto_obj, str):
            n_chars = max(1, len(texto_obj))

        largura_est = n_chars * self.fonte_tamanho * 0.6
        altura_est = self.fonte_tamanho

        # Matriz combinada: Texto x CTM
        m_comb = self.tm.multiplicar(self.estado.ctm)

        p1 = m_comb.transformar_ponto(0.0, -altura_est * 0.2)
        p2 = m_comb.transformar_ponto(largura_est, -altura_est * 0.2)
        p3 = m_comb.transformar_ponto(largura_est, altura_est * 0.8)
        p4 = m_comb.transformar_ponto(0.0, altura_est * 0.8)

        txt_bbox = BoundingBox()
        txt_bbox.adicionar_ponto(p1[0], p1[1])
        txt_bbox.adicionar_ponto(p2[0], p2[1])
        txt_bbox.adicionar_ponto(p3[0], p3[1])
        txt_bbox.adicionar_ponto(p4[0], p4[1])

        if self.estado.clip_bbox is not None:
            txt_bbox = txt_bbox.intersecao(self.estado.clip_bbox)

        if not txt_bbox.vazio:
            self.acumulador_tinta.adicionar_outro(txt_bbox)

        # Avança a matriz de texto horizontalmente
        m_avanco = Matriz2D(1.0, 0.0, 0.0, 1.0, largura_est, 0.0)
        self.tm = m_avanco.multiplicar(self.tm)

    def _adicionar_array_texto_ao_bbox(self, array_obj: Any):
        """Processa um array de texto do operador TJ."""
        if not isinstance(array_obj, list):
            return
        for item in array_obj:
            if isinstance(item, (bytes, bytearray, str)):
                self._adicionar_texto_ao_bbox(item)
            elif isinstance(item, (int, float)):
                # Ajuste de espaçamento kerning (1/1000 de em)
                desl_x = -float(item) / 1000.0 * self.fonte_tamanho
                m_avanco = Matriz2D(1.0, 0.0, 0.0, 1.0, desl_x, 0.0)
                self.tm = m_avanco.multiplicar(self.tm)


def interpretar_stream(
    stream_bytes: bytes,
    recursos: Optional[dict] = None,
    ctm_inicial: Optional[Matriz2D] = None,
    clip_inicial: Optional[BoundingBox] = None,
    doc: Optional[PdfReader] = None,
) -> BoundingBox:
    """Interpreta os operadores vetoriais de um stream e devolve seu BoundingBox."""
    interp = InterpretadorStream(
        stream_bytes=stream_bytes,
        recursos=recursos,
        ctm_inicial=ctm_inicial,
        clip_inicial=clip_inicial,
        doc=doc,
    )
    return interp.executar()


def calcular_caixa_da_arte(pagina: Pagina, margem_tolerancia_franja: float = 0.10) -> Caixa:
    """
    Calcula a caixa delimitadora real da ARTE vetorial/imagem dentro da página,
    eliminando a franja branca deixada pela exportação do Illustrator (ex: 1pt),
    mas preservando a página inteira quando o espaço em branco for intencional (design).
    """
    caixa_ref = pagina.trimbox if not pagina.trimbox.vazio else pagina.cropbox
    if caixa_ref.vazio:
        caixa_ref = pagina.mediabox

    stream_bytes = pagina.obter_conteudo_bruto()
    if not stream_bytes:
        return caixa_ref

    recursos = None
    if pagina.doc:
        rec_ref = pagina.raw_dict.get("/Resources") or pagina.raw_dict.get(PdfName("/Resources"))
        if rec_ref:
            recursos = pagina.doc._resolver_objeto(rec_ref)

    bbox_tinta = interpretar_stream(stream_bytes, recursos=recursos, doc=pagina.doc)
    if bbox_tinta.vazio:
        return caixa_ref

    caixa_tinta = bbox_tinta.para_caixa()

    # Intersecta com a caixa de referência da página (conteúdo fora da página não conta)
    caixa_tinta = caixa_tinta.intersecao(caixa_ref)

    if caixa_tinta.vazio or caixa_tinta.largura <= 0 or caixa_tinta.altura <= 0:
        return caixa_ref

    # Regra de ouro da produção:
    # Se a arte medida for menor que 90% da página em qualquer dimensão,
    # significa que o branco NÃO é franja de exportação, e sim DESIGN
    # (ex: logotipo pequeno no meio de folha branca). Manda a página inteira!
    limite_largura = caixa_ref.largura * (1.0 - margem_tolerancia_franja)
    limite_altura = caixa_ref.altura * (1.0 - margem_tolerancia_franja)

    if caixa_tinta.largura < limite_largura or caixa_tinta.altura < limite_altura:
        return caixa_ref

    return caixa_tinta
