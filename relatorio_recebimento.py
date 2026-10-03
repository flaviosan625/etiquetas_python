"""
Relatório de Recebimento de Artes — o documento que o Flávio abre pra
saber, num relance, o que já entrou e o que falta.

Conforme o modelo aprovado (o mock de 2026-09-11): faixa de resumo no
topo, uma linha por peça, e o selo com o logo da Uny CV nas que já
pegamos. A novidade que ele pediu: cada linha tem um link que abre DIRETO
no slide daquela peça no caderno do cliente (via drive_artes.link_da_peca).

Some do ruído: mostra só o que é peça de verdade (tem nome no caderno) e
separa APROVADAS (o que interessa produzir) do resto. A fonte de "já
pegamos" é o _baixados.json que o recebimento grava — não um palpite.

CADERNO DO CANVA (2026-10-02): o mesmo documento, pedido pelo usuário
depois do recebimento do VIBRA — "relatório dos arquivos com miniatura
igual feito em Mercado Livre, e link indicando de onde pegou a determinada
arte". Quem diz o que muda de um caderno pro outro é a FONTE (_FonteSlides,
_FonteCanva): quais fichas contam, onde está o registro de cada uma e pra
onde cada link aponta. O desenho é um só. Cada linha ganhou, nos dois
cadernos, o link de ORIGEM da arte (a pasta do Drive no Mercado Livre, o
arquivo do Drive no Canva), ao lado do que abre o caderno.

Depois, no mesmo dia: "a parte onde está localizado no caderno continua
travada" — o visualizador do Canva não termina de abrir um caderno de 68
páginas. A página de cada ficha (a imagem que o próprio Canva gera, guardada
no recebimento) vai ANEXADA no fim do relatório, e 'abrir no caderno' pula
pra ela dentro do PDF — sem rede, sem Canva. Ver _FonteCanva.anexar.
"""
import datetime
import json
import pathlib

import pymupdf

import arte_recebida
import caderno_arte
import drive_artes
import miniaturas
from branding import CAMINHO_LOGO_GUI

NOME_RELATORIO = "RECEBIMENTO - %s.pdf"

LARG, ALT, MARGEM = 595.27, 841.89, 40
_TEXTO, _SUAVE, _FRACA = "#12161d", "#5c6675", "#8a93a1"
_ACENTO, _AVISO, _PERIGO, _VERDE = "#0b6b8a", "#8a5300", "#a3302a", "#2d6a45"
_F_NOVO, _F_PEGO, _F_FALTA = "#e9f3f7", "#eaf4ec", "#fdf2e0"
_LOGO = "logo_uny_cv_gui.png"


# A prévia da arte em cada linha — mesmo tamanho da OS e do relatório
# diário, pra a mesma peça aparecer igual nos três documentos.
_LARGURA_PREVIA = 60
_ALTURA_PREVIA = 42
# 1 pixel transparente, que _previa estica na largura da coluna (ver lá)
_ESPACO = "espaco_previa.png"


def _png_transparente():
    from PIL import Image
    import io
    buf = io.BytesIO()
    Image.new("RGBA", (1, 1), (255, 255, 255, 0)).save(buf, format="PNG")
    return buf.getvalue()


def _rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def _link(texto, url, cor=_ACENTO, tam="8pt", negrito=False):
    peso = "font-weight:700;" if negrito else ""
    return ('<a href="%s" style="color:%s;%sfont-size:%s;text-decoration:none">%s</a>'
            % (url, cor, peso, tam, texto))


def _selo(quando):
    if not quando:
        return '<span style="font-size:7pt;color:%s">ainda não pegamos</span>' % _FRACA
    return ('<span style="background:%s;padding:1px 5px 1px 2px">'
            '<img src="%s" width="24" style="vertical-align:middle">'
            '<b style="color:%s;font-size:6.5pt">JÁ PEGAMOS</b>'
            '<span style="font-size:6.5pt;color:%s"> %s</span></span>'
            % (_F_PEGO, _LOGO, _VERDE, _SUAVE, quando))


def _quando_legivel(iso):
    try:
        return datetime.datetime.strptime(iso, "%Y-%m-%dT%H:%M:%S").strftime("%d/%m %H:%M")
    except (ValueError, TypeError):
        return ""


def _previa(nome_imagem, tamanho=None):
    """
    A arte na coluna da esquerda — ou o quadrado cinza, como na OS.
    "Somos uma gráfica, a arte é sempre muito importante" (23/09/2026):
    documento que lista arte mostra a arte, não só o nome dela.
    """
    # Uma imagem transparente da largura cheia segura a coluna: o HTML do
    # PyMuPDF ignora a largura da célula e encolhia a coluna até a miniatura
    # — a placa alta e a lona estreita deixavam o texto começando em lugares
    # diferentes, linha a linha (visto no relatório do VIBRA, 02/10).
    espaco = ("<div style='font-size:1px;line-height:1px'><img src='%s' width='%d' height='1'></div>"
              % (_ESPACO, _LARGURA_PREVIA))
    if not nome_imagem:
        return ("<div style='width:%dpx;height:%dpx;background:#f0f1f3;"
                "border:0.5px solid #dcdee3'></div>%s" % (_LARGURA_PREVIA, _ALTURA_PREVIA, espaco))
    largura, altura = tamanho or (_LARGURA_PREVIA, _ALTURA_PREVIA)
    return "<img src='%s' width='%d' height='%d'>%s" % (nome_imagem, largura, altura, espaco)


def _linha_peca(ficha, baixado, url, previa=None, tamanho_previa=None, origem=None, rotulo=""):
    """
    Uma peça: a prévia, o nome e o que o caderno pede, o selo, os links e o
    nome que o arquivo ganhou. 'origem' é (texto, endereço) de ONDE a arte
    foi pega; 'rotulo' vai antes do nome ('p.08', a página do caderno).
    """
    material = ficha.get("material") or "—"
    medida = ficha.get("medidas") or "—"
    nome_final = (baixado.get("arquivo") if baixado else None) or ficha.get("nome_arquivo") or ""
    fundo = "background:%s;" % _F_PEGO if baixado else ""
    links = _link("abrir no caderno", url, _ACENTO, "7pt")
    if origem and origem[1]:
        links += " &nbsp;·&nbsp; " + _link(origem[0], origem[1], _ACENTO, "7pt")
    detalhe = ("<div style='font-size:7pt;color:%s;padding-top:1px'>%s</div>" % (_SUAVE, _escapar(nome_final))
               if nome_final else "")
    antes = ("<span style='font-size:7.5pt;color:%s'>%s</span> " % (_SUAVE, _escapar(rotulo))
             if rotulo else "")
    # três linhas, sempre: o que o caderno pede e o selo; o nome que o arquivo
    # ganhou; e os links (o caderno e de onde a arte foi pega, 02/10)
    return (
        "<table style='width:100%%;%sborder-bottom:0.5px solid #dce0e7'>"
        "<tr><td width='%d' style='padding:5px 0'>%s</td>"
        "<td style='padding:5px 4px'>"
        "%s<b style='font-size:8.5pt;color:%s'>%s</b> &nbsp; "
        "<span style='font-size:7.5pt;color:%s'>%s · %s</span> &nbsp; %s"
        "%s<div style='padding-top:1px'>%s</div></td></tr></table>"
        % (fundo, _LARGURA_PREVIA + 8, _previa(previa, tamanho_previa),
           antes, _TEXTO, _escapar(ficha.get("nome") or ""), _SUAVE, _escapar(material), _escapar(medida),
           _selo(_quando_legivel(baixado.get("quando")) if baixado else None),
           detalhe, links))


def _titulo(texto, sub=""):
    s = ("<span style='font-weight:400;font-size:8pt;color:%s'> — %s</span>" % (_SUAVE, sub)
         if sub else "")
    return ("<div style='font-size:10pt;font-weight:700;color:%s;"
            "border-bottom:1px solid #b9c0cb;padding:14px 0 3px'>%s%s</div>" % (_TEXTO, texto, s))


def _escapar(t):
    return (str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


# ----------------------------------------------------------------------
# A página do caderno, anexada no fim (caderno do Canva, 02/10/2026)
# ----------------------------------------------------------------------
#
# O HTML do PyMuPDF só sabe fazer link pra fora (e '#id' só pra dentro da
# MESMA caixa): a linha escreve 'caderno:pagina:<n>' e _FonteCanva.anexar
# troca, depois de tudo montado, por um pulo pra folha da página <n>.

_PULO = "caderno:pagina:"
# A5 deitado: a mesma largura da folha do relatório, e a imagem do Canva
# (596 x 335 px) cabe quase do tamanho em que veio
_A5_LARG, _A5_ALT = 595.28, 419.53
_M_A5 = 28


def _pulo(pagina):
    return "%s%s" % (_PULO, pagina)


def _latin1(texto):
    """As fontes base-14 só falam Latin-1: travessão e aspa curva virariam '·' calados."""
    t = str(texto or "")
    for de, para in (("–", "-"), ("—", "-"), ("“", '"'), ("”", '"'), ("‘", "'"), ("’", "'"),
                     ("•", "·"), ("…", "...")):
        t = t.replace(de, para)
    return t.encode("latin-1", "replace").decode("latin-1")


def _caber(texto, fonte, tamanho, largura):
    """O texto cortado com '...' pra caber na largura."""
    if pymupdf.get_text_length(texto, fontname=fonte, fontsize=tamanho) <= largura:
        return texto
    while texto and pymupdf.get_text_length(texto + "...", fontname=fonte, fontsize=tamanho) > largura:
        texto = texto[:-1]
    return texto.rstrip() + "..."


def _folha_do_caderno(doc, numero, total, imagem, titulo, rodape, volta, link_canva):
    """
    Uma página do caderno: o que ela é em cima, a imagem inteira (sem
    esticar) e de quando ela é embaixo. Com as fontes base-14, que não se
    embutem: são dezenas de folhas, e cada insert_htmlbox pesaria até ~90 KB
    (ver CLAUDE.md). 'volta' é (folha, y) da linha que aponta pra cá.
    """
    pg = doc.new_page(width=_A5_LARG, height=_A5_ALT)
    esquerda, direita = _M_A5, _A5_LARG - _M_A5
    links = [("voltar à lista", {"kind": pymupdf.LINK_GOTO, "page": volta[0],
                                 "to": pymupdf.Point(0, max(0, volta[1] - 30)), "zoom": 0})]
    if link_canva:
        links.append(("abrir no Canva", {"kind": pymupdf.LINK_URI, "uri": link_canva}))
    x = direita
    for i, (texto, alvo) in enumerate(reversed(links)):
        if i:
            x -= pymupdf.get_text_length("  ·  ", fontname="helv", fontsize=7.5)
            pg.insert_text((x, 31), "  ·  ", fontname="helv", fontsize=7.5, color=_rgb(_FRACA))
        largura = pymupdf.get_text_length(_latin1(texto), fontname="helv", fontsize=7.5)
        x -= largura
        pg.insert_text((x, 31), _latin1(texto), fontname="helv", fontsize=7.5, color=_rgb(_ACENTO))
        pg.insert_link(dict(alvo, **{"from": pymupdf.Rect(x - 1, 22, x + largura + 1, 34)}))
    pg.insert_text((esquerda, 31), "CADERNO DE ARTES  ·  PÁGINA %02d DE %d" % (numero, total),
                   fontname="helv", fontsize=7, color=_rgb(_SUAVE))
    pg.insert_text((esquerda, 48), _caber(_latin1(titulo), "hebo", 12, direita - esquerda),
                   fontname="hebo", fontsize=12, color=_rgb(_TEXTO))
    pg.draw_line(pymupdf.Point(esquerda, 56), pymupdf.Point(direita, 56), color=_rgb("#b9c0cb"), width=0.6)

    caixa = pymupdf.Rect(esquerda, 64, direita, _A5_ALT - 34)
    largura, altura = miniaturas.encaixar(imagem, caixa.width, caixa.height)
    x0 = caixa.x0 + (caixa.width - largura) / 2
    onde = pymupdf.Rect(x0, caixa.y0, x0 + largura, caixa.y0 + altura)
    pg.insert_image(onde, stream=imagem)
    pg.draw_rect(onde, color=_rgb("#dce0e7"), width=0.5)
    pg.insert_text((esquerda, _A5_ALT - 20), _caber(_latin1(rodape), "helv", 6.5, direita - esquerda),
                   fontname="helv", fontsize=6.5, color=_rgb(_FRACA))
    return doc.page_count - 1


class _FonteSlides:
    """
    O caderno do Google Slides (o do Mercado Livre, lido do .pptx): só as
    APROVADAS contam, o registro é '<caderno>|slide|<n>', e o link abre o
    slide da peça. É o comportamento de sempre deste relatório.
    """
    resumo = "%d de %d artes aprovadas já baixadas"
    explicacao = "com a marca de corte removida e renomeadas no nosso padrão."
    titulo_pegas = "%d artes, prontas em ARTES/"
    titulo_faltam = ("APROVADAS QUE AINDA FALTAM", "sem link, medida incompleta ou a conferir")
    rodape = ("Cada arte foi baixada da pasta do cliente, teve a marca de corte e a tarja removidas "
              "<b>sem tocar no desenho</b> (conferido pixel a pixel) e renomeada no padrão da casa. O "
              "link de cada linha abre direto o slide daquela peça no caderno; 'pasta da arte' abre a "
              "pasta do Drive de onde ela foi baixada. O status vem do carimbo dentro do slide.")

    def __init__(self, presentation_id, mapa_etiquetas, caderno_nome):
        self.presentation_id = presentation_id
        self.mapa = mapa_etiquetas or {}
        self.caderno_nome = caderno_nome
        self.link_caderno = "https://docs.google.com/presentation/d/%s/edit" % presentation_id

    def contam(self, fichas):
        return [f for f in fichas if f.get("situacao") == "APROVADO"]

    def recebidas(self, ficha, baixados):
        chave = arte_recebida._chave_peca(self.caderno_nome, ficha)
        return [(chave, baixados[chave])] if chave in baixados else []

    def link_da_ficha(self, ficha):
        return drive_artes.link_da_peca(ficha, self.presentation_id, self.mapa)

    def abrir_caderno(self):
        return _link("Abrir o caderno de arte", self.link_caderno, _ACENTO, "8.5pt", True)

    # o slide abre direto pelo link: não há o que anexar
    anexar = None

    def origem(self, ficha, registro=None):
        links = ficha.get("links") or []
        return ("pasta da arte", links[0]) if links else None

    def motivo_falta(self, ficha):
        if not ficha.get("links"):
            return "não tem link de pasta no caderno"
        if not ficha.get("nome_arquivo"):
            return ficha.get("motivo_nome") or "medida/material a conferir"
        return ""

    def ordem(self, ficha):
        return (ficha.get("slide") or 0, 0)

    def rotulo(self, ficha):
        return ""


class _FonteCanva:
    """
    O caderno do Canva (caderno_canva.ler): toda ficha conta — não há
    carimbo de aprovação —, uma ficha pode ter dado mais de uma peça (o PDF
    de páginas diferentes vira uma peça por página), e o registro é
    'canva|<design>|p<página>|<id do Drive>'. O de origem abre o arquivo do
    Drive de onde a arte saiu. 'abrir no caderno' pula pra página da ficha
    anexada no fim (ver anexar) — ou, sem a imagem dela, abre o caderno no
    Canva, e a página vai escrita na linha.

    'paginas' é {número: bytes ou caminho da imagem}; 'paginas_em', quando
    a imagem foi tirada, se o caderno não disser página por página.
    """
    resumo = "%d de %d peças do caderno já recebidas"
    explicacao = "renomeadas no nosso padrão, com material e quantidade da ficha do caderno."
    titulo_pegas = "%d arquivos, prontos em ARTES/"
    titulo_faltam = ("AINDA FALTAM", "fichas do caderno sem nenhuma arte recebida")
    _RODAPE = ("Cada arte veio do link da sua ficha no caderno do Canva — o hiperlink da página; o "
               "endereço escrito nas fichas é sobra do modelo e não foi usado. %s 'arquivo de origem' "
               "abre o arquivo do Drive de onde a arte foi baixada. Arte em escala 1:10 leva ESCALA 1-10 "
               "no nome; com sangria, o tamanho maior vai na frente e o final atrás — a placa, na medida "
               "final.")
    _SO_CANVA = "'abrir no caderno' abre o caderno no Canva (a página da ficha é o p.NN da linha);"
    _ANEXADA = ("'abrir no caderno' leva à página da ficha, anexada no fim deste relatório — a imagem "
                "que o próprio Canva gera da página, guardada no recebimento, porque o visualizador do "
                "Canva não termina de abrir um caderno deste tamanho;")

    def __init__(self, caderno, paginas=None, paginas_em=None):
        import caderno_canva
        self.caderno = caderno
        self.design = caderno.get("design_id") or ""
        try:
            _, self.link_caderno = caderno_canva.link_de_visualizacao(caderno.get("link"))
        except caderno_canva.ErroCanva:
            self.link_caderno = caderno.get("link") or ""
        self.paginas = {}
        for numero, imagem in (paginas or {}).items():
            if not isinstance(imagem, (bytes, bytearray)):
                try:
                    imagem = pathlib.Path(imagem).read_bytes()
                except OSError:
                    continue
            if imagem:
                self.paginas[int(numero)] = bytes(imagem)
        quando = caderno.get("paginas_em_imagem") or {}
        self._quando = {int(n): q for n, q in quando.items() if str(n).isdigit()} if isinstance(quando, dict) else {}
        self._quando_padrao = paginas_em

    @property
    def rodape(self):
        return self._RODAPE % (self._ANEXADA if self.paginas else self._SO_CANVA)

    def abrir_caderno(self):
        if not self.paginas:
            return _link("Abrir o caderno de arte", self.link_caderno, _ACENTO, "8.5pt", True)
        return (_link("Ver as páginas do caderno", _pulo("primeira"), _ACENTO, "8.5pt", True)
                + "<span style='font-size:8pt;color:%s'> (no fim deste PDF) &nbsp;·&nbsp; </span>" % _SUAVE
                + _link("abrir no Canva", self.link_caderno, _ACENTO, "8pt"))

    @staticmethod
    def _pagina(ficha):
        import origem_artes
        return origem_artes._pagina_da_ficha(ficha)

    def contam(self, fichas):
        return list(fichas)

    def recebidas(self, ficha, baixados):
        prefixo = "canva|%s|p%s|" % (self.design, self._pagina(ficha))
        return sorted((k, v) for k, v in baixados.items() if k.startswith(prefixo))

    def link_da_ficha(self, ficha):
        if ficha.get("pagina") in self.paginas:
            return _pulo(ficha["pagina"])
        # Só o caderno, sem '#<página>' no fim (02/10): o pulo de página nunca
        # foi provado, e o '#' que chega no Canva como '%23' dá a página de
        # erro dele (testado: HTTP 404) — "não está abrindo o link".
        return self.link_caderno

    def _titulo_da_pagina(self, numero):
        fichas = [f for f in self.caderno.get("fichas") or [] if f.get("pagina") == numero]
        secao = next((f.get("secao") for f in fichas if f.get("secao")), "")
        nomes = [f.get("nome") or "sem nome" for f in fichas]
        return "  ·  ".join([secao] + nomes if secao else nomes)

    def _rodape_da_pagina(self, numero):
        quando = _quando_legivel(self._quando.get(numero) or self._quando_padrao or "")
        return ("Como estava no Canva%s  ·  imagem que o próprio Canva gera da página, guardada no "
                "recebimento  ·  o link de cada arte é o do relatório, não o escrito na ficha"
                % (" em %s" % quando if quando else ""))

    def anexar(self, doc):
        """
        A página de cada ficha no fim do PDF, e cada 'caderno:pagina:<n>' do
        relatório trocado pelo pulo até ela. Só entra a página que alguma
        linha aponta; 'voltar à lista' volta pra primeira linha que apontou.

        Recebe o PDF RELIDO (ver _escrever): na folha recém-escrita o
        insert_htmlbox ainda não mostra os links.
        """
        volta, pedidas = {}, []
        for i in range(doc.page_count):
            for l in doc[i].get_links():
                uri = l.get("uri") or ""
                if uri.startswith(_PULO):
                    alvo = uri[len(_PULO):]
                    numero = int(alvo) if alvo.isdigit() else None    # 'primeira': a do resumo
                    pedidas.append((i, l, numero))
                    if numero is not None:
                        volta.setdefault(numero, (i, l["from"].y0))
        if not pedidas:
            return
        total = self.caderno.get("paginas") or max(self.paginas or {0: None})
        folha = {}
        for numero in sorted(set(volta) & set(self.paginas)):
            folha[numero] = _folha_do_caderno(doc, numero, total, self.paginas[numero],
                                              self._titulo_da_pagina(numero), self._rodape_da_pagina(numero),
                                              volta[numero], self.link_caderno)
        for i, l, numero in pedidas:
            destino = folha.get(numero) if numero is not None else (folha[min(folha)] if folha else None)
            pagina = doc[i]
            pagina.delete_link(l)
            if destino is not None:
                pagina.insert_link({"kind": pymupdf.LINK_GOTO, "from": l["from"], "page": destino,
                                    "to": pymupdf.Point(0, 0), "zoom": 0})
            elif self.link_caderno:
                pagina.insert_link({"kind": pymupdf.LINK_URI, "from": l["from"], "uri": self.link_caderno})

    def origem(self, ficha, registro=None):
        if registro and registro.get("link_origem"):
            return ("arquivo de origem", registro["link_origem"])
        id_drive = None
        if registro and registro.get("_chave"):
            partes = registro["_chave"].split("|")
            id_drive = partes[3] if len(partes) > 3 else None
        if id_drive:
            return ("arquivo de origem", "https://drive.google.com/file/d/%s/view" % id_drive)
        links = ficha.get("links") or []
        return ("arquivo de origem", links[0]) if links else None

    def motivo_falta(self, ficha):
        if not ficha.get("links"):
            return ("a ficha só tem o link escrito do modelo" if ficha.get("link_do_modelo")
                    else "a ficha não tem link")
        return "não foi marcada no recebimento"

    def ordem(self, ficha):
        return (ficha.get("pagina") or 0, ficha.get("na_pagina") or 0)

    def rotulo(self, ficha):
        return "p.%s" % self._pagina(ficha)


def montar_blocos(fichas, baixados, presentation_id, mapa_etiquetas, caderno_nome, agora,
                  previas=None, fonte=None):
    """
    Os blocos de HTML do relatório. Sem 'fonte', é o caderno do Google
    Slides de sempre (presentation_id, mapa_etiquetas e caderno_nome); com
    ela (_FonteCanva), os outros três parâmetros não são usados.
    """
    fonte = fonte or _FonteSlides(presentation_id, mapa_etiquetas, caderno_nome)
    contam = fonte.contam(fichas)
    pegas, faltando = [], []
    for f in contam:
        recebidas = fonte.recebidas(f, baixados)
        if recebidas:
            pegas.extend((f, chave, registro) for chave, registro in recebidas)
        else:
            faltando.append(f)
    fichas_pegas = len(contam) - len(faltando)

    blocos = [
        "<div style='background:%s;border-left:4px solid %s;padding:9px 12px'>"
        "<div style='font-size:12pt;font-weight:700;color:%s'>%s</div>"
        "<div style='font-size:8.5pt;color:%s;padding-top:3px'>%s "
        "<b style='color:%s'>%d ainda faltam.</b></div>"
        "<div style='padding-top:5px'>%s</div></div>"
        "<div style='font-size:8pt;color:%s;padding:6px 2px 0'>"
        "Gerado em <b style='color:%s'>%s</b> · a fonte do “já pegamos” é o registro de "
        "download, não um palpite</div>"
        % (_F_NOVO, _ACENTO, _TEXTO, fonte.resumo % (fichas_pegas, len(contam)), _SUAVE, fonte.explicacao,
           _AVISO, len(faltando), fonte.abrir_caderno(),
           _SUAVE, _TEXTO, agora.strftime("%d/%m/%Y %H:%M")),
    ]

    previas = previas or {}
    blocos.append(_titulo("JÁ PEGAMOS", fonte.titulo_pegas % len(pegas)))
    for f, chave, registro in sorted(pegas, key=lambda x: (fonte.ordem(x[0]), x[1])):
        nome_imagem, tamanho = previas.get(chave, (None, None))
        blocos.append(_linha_peca(f, registro, fonte.link_da_ficha(f), nome_imagem, tamanho,
                                  origem=fonte.origem(f, dict(registro or {}, _chave=chave)),
                                  rotulo=fonte.rotulo(f)))

    if faltando:
        blocos.append(_titulo(*fonte.titulo_faltam))
        for f in sorted(faltando, key=fonte.ordem):
            motivo = fonte.motivo_falta(f)
            extra = (" <span style='font-size:7.5pt;color:%s'>(%s)</span>" % (_AVISO, _escapar(motivo))
                     if motivo else "")
            origem = fonte.origem(f)
            links = _link("abrir no caderno", fonte.link_da_ficha(f), _ACENTO, "7pt")
            if origem and origem[1]:
                links += " &nbsp;·&nbsp; " + _link(origem[0], origem[1], _ACENTO, "7pt")
            rotulo = fonte.rotulo(f)
            blocos.append(
                "<div style='background:%s;border-bottom:0.5px solid #dce0e7;padding:5px 4px'>"
                "%s<b style='font-size:8.5pt;color:%s'>%s</b> &nbsp; "
                "<span style='font-size:7.5pt;color:%s'>%s</span>%s &nbsp; %s</div>"
                % (_F_FALTA, ("<span style='font-size:7.5pt;color:%s'>%s</span> " % (_SUAVE, rotulo))
                   if rotulo else "", _TEXTO, _escapar(f.get("nome") or ""), _SUAVE,
                   _escapar(f.get("medidas") or "—"), extra, links))

    blocos.append(
        "<div style='font-size:7pt;color:%s;line-height:1.5;border-top:0.5px solid #dce0e7;"
        "margin-top:14px;padding-top:7px'>%s</div>" % (_SUAVE, fonte.rodape))
    return blocos


def _previas_das_artes(pasta, baixados, arquivo):
    """
    Uma prévia por arte já baixada, posta no Archive do PDF.

    A arte fica em ARTES/<área>/<nome>, e a área é opcional — em vez de
    remontar o caminho (que mudaria junto com a organização das pastas),
    procura o arquivo pelo nome uma vez só e usa o índice.
    """
    raiz = pathlib.Path(pasta)
    indice = {}
    try:
        for caminho in raiz.rglob("*"):
            if caminho.is_file():
                indice.setdefault(caminho.name, caminho)
    except OSError:
        return {}

    previas = {}
    for chave, baixado in baixados.items():
        caminho = indice.get((baixado or {}).get("arquivo") or "")
        if not caminho:
            continue
        dados = miniaturas.de_arquivo(caminho)
        if not dados:
            continue
        nome_imagem = "previa_%s.jpg" % len(previas)
        arquivo.add(dados, nome_imagem)
        previas[chave] = (nome_imagem, miniaturas.encaixar(dados, _LARGURA_PREVIA, _ALTURA_PREVIA))
    return previas


def _cabecalho(pagina, subtitulo):
    try:
        from branding import inserir_logo
        inserir_logo(pagina, pymupdf.Rect(MARGEM, MARGEM, MARGEM + 92, MARGEM + 26),
                     caminho=CAMINHO_LOGO_GUI if CAMINHO_LOGO_GUI.is_file() else None)
    except Exception:
        pass
    pagina.insert_htmlbox(
        pymupdf.Rect(LARG / 2 - 60, MARGEM - 4, LARG - MARGEM, MARGEM + 34),
        "<div style='text-align:right;font-family:sans-serif'>"
        "<div style='font-size:13pt;font-weight:700;color:%s'>Recebimento de Artes</div>"
        "<div style='font-size:9pt;color:%s;margin-top:2px'>%s</div>"
        "</div>" % (_TEXTO, _SUAVE, _escapar(subtitulo)))
    pagina.draw_line(pymupdf.Point(MARGEM, MARGEM + 38), pymupdf.Point(LARG - MARGEM, MARGEM + 38),
                     color=_rgb(_TEXTO), width=1.2)


def _alturas(blocos, arquivo):
    """
    A altura de VERDADE de cada bloco, medida numa folha de rascunho. Até
    2026-10-02 era um palpite por tipo de bloco; com o link de origem na
    linha, a linha comprida quebra em duas, e o insert_htmlbox ENCOLHE a
    letra calado pra caber (armadilha do CLAUDE.md).
    """
    rascunho = pymupdf.open()
    folha = rascunho.new_page(width=LARG, height=4000)
    caixa = pymupdf.Rect(MARGEM, 0, LARG - MARGEM, 3900)
    alturas = []
    for bloco in blocos:
        sobra, _ = folha.insert_htmlbox(caixa, "<div style='font-family:sans-serif'>%s</div>" % bloco,
                                        archive=arquivo)
        alturas.append(caixa.height - sobra if sobra >= 0 else caixa.height)
    rascunho.close()
    return alturas


def _escrever(destino, blocos, arquivo, subtitulo, depois=None):
    """
    O PDF: cabeçalho, e os blocos em folhas A4 pela altura medida. Se uma
    folha ainda assim precisasse encolher a letra, refaz com mais folga — o
    documento nunca sai com letra menor que a do modelo. 'depois(doc)'
    roda com tudo montado, antes de gravar (o anexo do caderno do Canva).
    """
    arquivo.add(_png_transparente(), _ESPACO)
    alturas = _alturas(blocos, arquivo)
    for folga in (6, 30, 60, 120):
        doc = pymupdf.open()
        pagina = doc.new_page(width=LARG, height=ALT)
        _cabecalho(pagina, subtitulo)
        topo = MARGEM + 48
        y, pendentes, menor = topo, [], 1.0

        def descarregar(pg, blocos_pg, primeiro_y):
            if not blocos_pg:
                return 1.0
            _, escala = pg.insert_htmlbox(
                pymupdf.Rect(MARGEM, primeiro_y, LARG - MARGEM, ALT - MARGEM),
                "<div style='font-family:sans-serif'>%s</div>" % "".join(blocos_pg), archive=arquivo)
            return escala

        for bloco, altura in zip(blocos, alturas):
            if pendentes and y + altura > ALT - MARGEM - folga:
                menor = min(menor, descarregar(pagina, pendentes, topo))
                pagina = doc.new_page(width=LARG, height=ALT)
                pendentes, y, topo = [], MARGEM, MARGEM
            pendentes.append(bloco)
            y += altura
        menor = min(menor, descarregar(pagina, pendentes, topo))
        if menor >= 0.999:
            break
        doc.close()

    if depois:
        # Relido, porque na folha recém-escrita o insert_htmlbox ainda não
        # mostra os links que ele mesmo criou (visto em 02/10) — e é por eles
        # que o anexo acha onde pôr o pulo pra página do caderno.
        relido = pymupdf.open("pdf", doc.tobytes())
        doc.close()
        doc = relido
        depois(doc)
    destino = pathlib.Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    doc.subset_fonts()
    doc.save(str(destino), garbage=4, deflate=True)
    doc.close()
    return destino


def gerar(destino, caminho_caderno, pasta, presentation_id, drive_slides=None,
          agora=None, config=None, nome_cliente=None):
    """
    Escreve o PDF do relatório do caderno do Google Slides (.pptx). Puxa os
    objectIds dos slides via Slides API (pro link direto); se a API falhar,
    os links caem no caderno inteiro, e o relatório sai mesmo assim.

    'nome_cliente' vai no cabeçalho; sem ele, é o nome da pasta do cliente
    em Recebimento de Artes (até 2026-09-13 o cabeçalho dizia "Mercado
    Livre" pra qualquer cliente).
    """
    agora = agora or datetime.datetime.now()
    caminho_caderno = pathlib.Path(caminho_caderno)
    fichas = [f for f in caderno_arte.fichas_com_nome(caminho_caderno, config) if f.get("nome")]
    baixados = arte_recebida.ler_baixados(pasta)

    try:
        mapa = drive_artes.mapa_slides_por_etiqueta(presentation_id, drive_slides)
    except Exception:
        mapa = {}

    arquivo = pymupdf.Archive(str(pathlib.Path(__file__).parent / "assets"))
    previas = _previas_das_artes(pasta, baixados, arquivo)
    blocos = montar_blocos(fichas, baixados, presentation_id, mapa, caminho_caderno.stem, agora,
                           previas)
    return _escrever(destino, blocos, arquivo, nome_cliente or pathlib.Path(pasta).name)


def gerar_do_canva(destino, caderno, pasta, agora=None, nome_cliente=None, paginas=None, paginas_em=None):
    """
    O mesmo relatório pro caderno do Canva (2026-10-02). 'caderno' é o que
    caderno_canva.ler devolve — ou o caderno.json guardado no recebimento
    (caderno_guardado), quando o relatório é refeito depois. A fonte do
    "já pegamos" continua sendo o _baixados.json da pasta do cliente.

    'paginas' ({número: bytes ou caminho}) é a imagem das páginas, que vai
    anexada no fim; sem ela, as que o recebimento guardou ao lado do
    caderno.json. Nenhuma imagem: os links abrem o caderno no Canva.
    """
    import re
    import caderno_canva
    agora = agora or datetime.datetime.now()
    if paginas is None and caderno.get("_pasta"):
        paginas = caderno_canva.imagens_guardadas(caderno["_pasta"])
    baixados = arte_recebida.ler_baixados(pasta)
    arquivo = pymupdf.Archive(str(pathlib.Path(__file__).parent / "assets"))
    previas = _previas_das_artes(pasta, baixados, arquivo)
    fonte = _FonteCanva(caderno, paginas, paginas_em)
    blocos = montar_blocos(caderno.get("fichas") or [], baixados, None, None, None, agora, previas,
                           fonte=fonte)
    titulo = re.sub(r"^\s*caderno de artes?\s*[-–:]\s*", "", caderno.get("titulo") or "", flags=re.I)
    subtitulo = nome_cliente or pathlib.Path(pasta).name
    return _escrever(destino, blocos, arquivo, "%s · %s" % (subtitulo, titulo) if titulo else subtitulo,
                     depois=fonte.anexar if fonte.paginas else None)


def caderno_guardado(pasta_cliente):
    """
    O caderno do Canva como foi lido no último recebimento — o caderno.json
    que o arquivamento guarda em _sistema/recebidos/, com '_pasta' dizendo
    onde (é ao lado dele que moram as imagens das páginas). None quando não há.
    """
    melhor = None
    for caminho in pathlib.Path(pasta_cliente).glob("_sistema/recebidos/*/caderno.json"):
        try:
            dados = json.loads(caminho.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if dados.get("fichas") and (melhor is None or (dados.get("lido_em") or "") > (melhor.get("lido_em") or "")):
            melhor = dict(dados, _pasta=str(caminho.parent))
    return melhor


def completar_paginas(caderno, ler=None, baixar=None, agora=None):
    """
    A imagem das páginas de um caderno guardado SEM elas (o do VIBRA, de
    antes de 02/10 à noite, ou um recebimento em que o Canva não as mandou):
    lê o Canva de novo e guarda só as páginas que ainda dizem exatamente o
    que diziam no recebimento (caderno_canva.paginas_que_conferem) — página
    editada depois fica sem imagem, e a linha dela abre o Canva. Devolve
    {número: caminho} de tudo o que ficou guardado.

    'ler' e 'baixar' existem pro teste passar dublês (caderno_canva.ler e
    caderno_canva.baixar_paginas).
    """
    import caderno_canva
    pasta = caderno.get("_pasta")
    if not pasta or not caderno.get("link"):
        return {}
    pasta = pathlib.Path(pasta)
    guardadas = caderno_canva.imagens_guardadas(pasta)
    faltam = {f.get("pagina") for f in caderno.get("fichas") or [] if f.get("pagina")} - set(guardadas)
    if not faltam:
        return guardadas
    try:
        novo = (ler or caderno_canva.ler)(caderno["link"])
    except Exception:   # noqa: BLE001 — sem a imagem, o relatório sai com o link do Canva
        return guardadas
    conferem = caderno_canva.paginas_que_conferem(caderno, novo) & faltam
    imagens = (baixar or caderno_canva.baixar_paginas)(novo.get("enderecos_das_paginas") or {}, conferem)
    if not imagens:
        return guardadas
    quando = (agora or datetime.datetime.now()).strftime("%Y-%m-%dT%H:%M:%S")
    for numero, dados in sorted(imagens.items()):
        destino = pasta / caderno_canva.PASTA_DAS_PAGINAS / caderno_canva.nome_da_imagem(numero, dados)
        destino.parent.mkdir(parents=True, exist_ok=True)
        parcial = destino.with_name("~gravando~" + destino.name)
        parcial.write_bytes(dados)
        parcial.replace(destino)
    # de quando é cada imagem — o rodapé da página anexada diz
    caminho = pasta / "caderno.json"
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
        em = dados.get("paginas_em_imagem") if isinstance(dados.get("paginas_em_imagem"), dict) else {}
        em.update({str(n): quando for n in imagens})
        dados["paginas_em_imagem"] = em
        parcial = caminho.with_name("~gravando~" + caminho.name)
        parcial.write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")
        parcial.replace(caminho)
        caderno["paginas_em_imagem"] = em
    except (OSError, ValueError):
        pass
    return caderno_canva.imagens_guardadas(pasta)


def caminho_do_relatorio(cliente):
    """
    Onde o relatório do cliente mora: 'RECEBIMENTO - <CLIENTE>.pdf', na pasta
    dele em Recebimento de Artes — o mesmo nome do do Mercado Livre.
    """
    return pathlib.Path(cliente.pasta) / (NOME_RELATORIO % cliente.nome.upper())
