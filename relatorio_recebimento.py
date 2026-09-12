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
"""
import datetime
import pathlib

import pymupdf

import arte_recebida
import caderno_arte
import drive_artes
from branding import CAMINHO_LOGO_GUI

LARG, ALT, MARGEM = 595.27, 841.89, 40
_TEXTO, _SUAVE, _FRACA = "#12161d", "#5c6675", "#8a93a1"
_ACENTO, _AVISO, _PERIGO, _VERDE = "#0b6b8a", "#8a5300", "#a3302a", "#2d6a45"
_F_NOVO, _F_PEGO, _F_FALTA = "#e9f3f7", "#eaf4ec", "#fdf2e0"
_LOGO = "logo_uny_cv_gui.png"


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


def _linha_peca(ficha, baixado, url):
    situacao = ficha.get("situacao", "")
    material = ficha.get("material") or "—"
    medida = ficha.get("medidas") or "—"
    nome_final = (baixado.get("arquivo") if baixado else None) or ficha.get("nome_arquivo") or ""
    fundo = "background:%s;" % _F_PEGO if baixado else ""
    detalhe = ("<div style='font-size:7pt;color:%s;padding-top:1px'>%s</div>" % (_SUAVE, nome_final)
               if nome_final else "")
    return (
        "<div style='%sborder-bottom:0.5px solid #dce0e7;padding:5px 4px'>"
        "<b style='font-size:8.5pt;color:%s'>%s</b> &nbsp; "
        "<span style='font-size:7.5pt;color:%s'>%s · %s</span> &nbsp; %s &nbsp; %s"
        "%s</div>"
        % (fundo, _TEXTO, _escapar(ficha.get("nome") or ""), _SUAVE, material, medida,
           _selo(_quando_legivel(baixado.get("quando")) if baixado else None),
           _link("abrir no caderno", url, _ACENTO, "7pt"), detalhe))


def _titulo(texto, sub=""):
    s = ("<span style='font-weight:400;font-size:8pt;color:%s'> — %s</span>" % (_SUAVE, sub)
         if sub else "")
    return ("<div style='font-size:10pt;font-weight:700;color:%s;"
            "border-bottom:1px solid #b9c0cb;padding:14px 0 3px'>%s%s</div>" % (_TEXTO, texto, s))


def _escapar(t):
    return (str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def montar_blocos(fichas, baixados, presentation_id, mapa_etiquetas, caderno_nome, agora):
    aprovadas = [f for f in fichas if f.get("situacao") == "APROVADO"]
    pegas, faltando = [], []
    for f in aprovadas:
        chave = arte_recebida._chave_peca(caderno_nome, f)
        (pegas if chave in baixados else faltando).append((f, baixados.get(chave)))

    link_caderno = "https://docs.google.com/presentation/d/%s/edit" % presentation_id
    blocos = [
        "<div style='background:%s;border-left:4px solid %s;padding:9px 12px'>"
        "<div style='font-size:12pt;font-weight:700;color:%s'>%d de %d artes aprovadas já baixadas</div>"
        "<div style='font-size:8.5pt;color:%s;padding-top:3px'>"
        "com a marca de corte removida e renomeadas no nosso padrão. "
        "<b style='color:%s'>%d ainda faltam.</b></div>"
        "<div style='padding-top:5px'>%s</div></div>"
        "<div style='font-size:8pt;color:%s;padding:6px 2px 0'>"
        "Gerado em <b style='color:%s'>%s</b> · a fonte do “já pegamos” é o registro de "
        "download, não um palpite</div>"
        % (_F_NOVO, _ACENTO, _TEXTO, len(pegas), len(aprovadas), _SUAVE, _AVISO, len(faltando),
           _link("Abrir o caderno de arte", link_caderno, _ACENTO, "8.5pt", True),
           _SUAVE, _TEXTO, agora.strftime("%d/%m/%Y %H:%M")),
    ]

    blocos.append(_titulo("JÁ PEGAMOS", "%d artes, prontas em ARTES/" % len(pegas)))
    for f, b in sorted(pegas, key=lambda x: x[0]["slide"]):
        blocos.append(_linha_peca(f, b, drive_artes.link_da_peca(f, presentation_id, mapa_etiquetas)))

    if faltando:
        blocos.append(_titulo("APROVADAS QUE AINDA FALTAM", "sem link, medida incompleta ou a conferir"))
        for f, _ in sorted(faltando, key=lambda x: x[0]["slide"]):
            motivo = ""
            if not f.get("links"):
                motivo = "não tem link de pasta no caderno"
            elif not f.get("nome_arquivo"):
                motivo = f.get("motivo_nome") or "medida/material a conferir"
            url = drive_artes.link_da_peca(f, presentation_id, mapa_etiquetas)
            extra = " <span style='color:%s'>(%s)</span>" % (_AVISO, motivo) if motivo else ""
            blocos.append(
                "<div style='background:%s;border-bottom:0.5px solid #dce0e7;padding:5px 4px'>"
                "<b style='font-size:8.5pt;color:%s'>%s</b> &nbsp; "
                "<span style='font-size:7.5pt;color:%s'>%s</span>%s &nbsp; %s</div>"
                % (_F_FALTA, _TEXTO, _escapar(f.get("nome") or ""), _SUAVE,
                   f.get("medidas") or "—", extra,
                   _link("abrir no caderno", url, _ACENTO, "7pt")))

    blocos.append(
        "<div style='font-size:7pt;color:%s;line-height:1.5;border-top:0.5px solid #dce0e7;"
        "margin-top:14px;padding-top:7px'>Cada arte foi baixada da pasta do cliente, teve a marca "
        "de corte e a tarja removidas <b>sem tocar no desenho</b> (conferido pixel a pixel) e "
        "renomeada no padrão da casa. O link de cada linha abre direto o slide daquela peça no "
        "caderno. O status vem do carimbo dentro do slide.</div>" % _SUAVE)
    return blocos


def gerar(destino, caminho_caderno, pasta, presentation_id, drive_slides=None,
          agora=None, config=None):
    """
    Escreve o PDF do relatório. Puxa os objectIds dos slides via Slides
    API (pro link direto); se a API falhar, os links caem no caderno
    inteiro, e o relatório sai mesmo assim.
    """
    agora = agora or datetime.datetime.now()
    caminho_caderno = pathlib.Path(caminho_caderno)
    fichas = [f for f in caderno_arte.fichas_com_nome(caminho_caderno, config) if f.get("nome")]
    baixados = arte_recebida.ler_baixados(pasta)

    try:
        mapa = drive_artes.mapa_slides_por_etiqueta(presentation_id, drive_slides)
    except Exception:
        mapa = {}

    blocos = montar_blocos(fichas, baixados, presentation_id, mapa, caminho_caderno.stem, agora)

    doc = pymupdf.open()
    pagina = doc.new_page(width=LARG, height=ALT)
    try:
        from branding import inserir_logo
        inserir_logo(pagina, pymupdf.Rect(MARGEM, MARGEM, MARGEM + 92, MARGEM + 26),
                     caminho=CAMINHO_LOGO_GUI if CAMINHO_LOGO_GUI.is_file() else None)
    except Exception:
        pass
    pagina.insert_htmlbox(
        pymupdf.Rect(LARG / 2, MARGEM - 4, LARG - MARGEM, MARGEM + 34),
        "<div style='text-align:right;font-family:sans-serif'>"
        "<div style='font-size:13pt;font-weight:700;color:%s'>Recebimento de Artes</div>"
        "<div style='font-size:9pt;color:%s;margin-top:2px'>Mercado Livre · Experience 26</div>"
        "</div>" % (_TEXTO, _SUAVE))
    pagina.draw_line(pymupdf.Point(MARGEM, MARGEM + 38), pymupdf.Point(LARG - MARGEM, MARGEM + 38),
                     color=_rgb(_TEXTO), width=1.2)

    arquivo = pymupdf.Archive(str(pathlib.Path(__file__).parent / "assets"))

    def _altura(bloco):
        if "border-left:4px" in bloco:      # faixa de resumo do topo
            return 92
        if "border-top" in bloco:           # rodapé explicativo
            return 60
        if "border-bottom:1px" in bloco:    # título de seção
            return 26
        base = 30                           # linha de peça
        return base + (12 if "padding-top:1px" in bloco else 0)

    topo = MARGEM + 48
    y = topo
    pendentes = []

    def _descarregar(pg, blocos_pg, primeiro_y):
        if not blocos_pg:
            return
        pg.insert_htmlbox(
            pymupdf.Rect(MARGEM, primeiro_y, LARG - MARGEM, ALT - MARGEM),
            "<div style='font-family:sans-serif'>%s</div>" % "".join(blocos_pg), archive=arquivo)

    for bloco in blocos:
        altura = _altura(bloco)
        if y + altura > ALT - MARGEM:
            _descarregar(pagina, pendentes, topo if doc.page_count == 1 else MARGEM)
            pagina = doc.new_page(width=LARG, height=ALT)
            pendentes, y, topo = [], MARGEM, MARGEM
        pendentes.append(bloco)
        y += altura
    _descarregar(pagina, pendentes, topo if doc.page_count == 1 else MARGEM)

    destino = pathlib.Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    doc.subset_fonts()
    doc.save(str(destino), garbage=4, deflate=True)
    doc.close()
    return destino
