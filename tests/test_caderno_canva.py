"""
Caderno de arte no CANVA, do link até o nome do arquivo (2026-10-02).

O que os testes travam saiu do caderno de verdade da LOJINHA MR2 CULTURAL
(cliente VIBRA): o documento embutido na página de visualização, o link
ESCRITO que não é o link (vale o hiperlink), a seção que abre com um título
só, a lona desenhada em 1:10, e várias fichas apontando o mesmo PDF.

Nenhum teste toca a internet nem pasta real: o Canva e o Drive são dublês,
e a fixture derruba qualquer tentativa de rede ou de login no Google.
"""
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import pymupdf
import pytest

import caderno_arte
import caderno_canva
import caminhos
import drive_artes
import marcas_de_corte
import origem_artes as oa
import receber_artes as ra

PT = 72 / 0.0254   # pontos por metro
LINK = "https://www.canva.com/design/DAHWe8X_fZk/codigoDeCompartilhamento/edit"
MEDIA_CANVA = "https://media.canva.com/v2/document-image"


@pytest.fixture(autouse=True)
def nada_real(tmp_path, monkeypatch):
    onedrive = tmp_path / "UNYCOMUNICACAO"
    monkeypatch.setattr(caminhos, "ONEDRIVE_UNY", onedrive)
    monkeypatch.setattr(caminhos, "RECEBIMENTO_DE_ARTES", onedrive / "Recebimento de Artes")
    monkeypatch.setattr(caminhos, "PASTA_RECEBENDO", tmp_path / "recebendo")
    (onedrive / "Recebimento de Artes").mkdir(parents=True)

    def proibido(*a, **k):
        raise AssertionError("teste tentou sair pra rede ou autenticar de verdade")
    monkeypatch.setattr(drive_artes, "autenticar", proibido)
    monkeypatch.setattr(marcas_de_corte, "remover_marcas_com_limite", proibido)
    import requests
    monkeypatch.setattr(requests.Session, "request", proibido)


# ============================================================ dublês

def _texto(paragrafos, links=(), topo=0, esquerda=0):
    """Um elemento de texto ('K') como o Canva grava: parágrafos em a.C.A, link no estilo 'Q'."""
    estilos = [{"G": "12px", "M": "#1b1b1e"}] + [{"Q": l, "O": "underline"} for l in links]
    return {"A?": "K", "A": topo, "B": esquerda, "D": 200, "C": 60,
            "a": {"C": {"A": [p + "\n" for p in paragrafos], "B": [10], "C": estilos, "D": [0]}}}


def _imagem():
    return {"A?": "I", "A": 100, "B": 100, "D": 400, "C": 300, "a": {"A": "M123"}}


def _pagina(*elementos):
    return {"A?": "i", "B": "slide texto grande", "E": list(elementos)}


def _ficha(nome, medidas, sangria, material, quantidade, link, escrito=None):
    """A página de uma peça como no caderno da LOJINHA: rótulos soltos, a ficha e o link."""
    escrito = escrito or "https://drive.google.com/file/d/1E1siFydgATgf8zxyOkEisb8BqZUlUvkg/view?usp=drive_link"
    linhas = [""] + nome.split("\n") + ["", "medidas", medidas, "", "sangria", sangria, "", "material"] \
        + material.split("\n") + ["", "quantidade", str(quantidade)]
    return _pagina(_texto(["", "ortogonal"], topo=25, esquerda=215), _texto(["", "arte"], topo=25, esquerda=985),
                   _texto(["", "especificações"], topo=25, esquerda=1621), _imagem(),
                   _texto(linhas, topo=96, esquerda=1605),
                   _texto(["", "link"], topo=555, esquerda=1621),
                   _texto([escrito], links=[link] if link else (), topo=709, esquerda=1651))


def _documento(paginas, titulo="Caderno de artes - LOJINHA MR2 CULTURAL"):
    return {"B": {"A?": "A"}, "C": {"A": 1920.0, "B": 1080.0}, "D": titulo, "A": paginas}


def _imagens_das_paginas(documento):
    """O imageSets que o Canva manda junto: uma imagem de 596x335 por página, com endereço assinado."""
    return {"thumbnail": {"height": 335, "width": 596, "version": 3, "images": [
        {"bucket": "document-export.canva.com", "key": "X_fZk/DAHWe8X_fZk/3/thumbnail/%04d.png" % n,
         "page": n, "pageHash": -484788849 - n, "height": 335, "width": 596,
         "url": "%s/hash:%d/height:335/id:DAHWe8X_fZk/type:B/width:596?csig=xxx&exp=1790984511"
                % (MEDIA_CANVA, n)} for n in range(1, len(documento["A"]) + 1)]},
        "preview": {"height": 576, "width": 1024, "version": 3, "images": [
            {"page": 1, "url": "%s/preview/0001.png" % MEDIA_CANVA}]}}


def _html(documento, caminho=("page", "Pm", "E", "draft", "content"), com_imagens=True):
    """A página de visualização: o documento dentro de JSON.parse('...'), escapado como o Canva faz."""
    dados = {"base": {"E": "453d8dc"}, "page": {}}
    no = dados
    for chave in caminho[:-1]:
        no = no.setdefault(chave, {})
    no[caminho[-1]] = documento
    if com_imagens and len(caminho) > 1:
        no["imageSets"] = _imagens_das_paginas(documento)
    js = json.dumps(dados).replace("\\", "\\\\").replace("'", "\\'").replace("/", "\\/").replace("=", "\\x3d")
    return ("<!DOCTYPE html><html><head><title>%s</title><script nonce=\"x\">(function() {"
            "window['__canva_public_path__'] = 'https:\\/\\/static.canva.com\\/web\\/'; "
            "window['bootstrap'] = JSON.parse('%s');})();</script></head><body></body></html>"
            % (documento.get("D"), js))


def _drive(id_):
    return "https://drive.google.com/file/d/%s/view?usp=drive_link" % id_


def _lojinha():
    """Um pedaço do caderno de verdade: capa, seções, lona 1:10, quadros num PDF só, placa sem link."""
    return _documento([
        _pagina(_texto(["LOJINHA MR2 CULTURAL"]), _texto(["2026"]), _texto(["truque.art.br"])),
        _pagina(_texto(["LOGOMARCAS"]), _imagem()),
        _ficha("LOGO TESTEIRA ", "1,15x 1,15m", "2cm + marcação faca de corte",
               "LOGO EM XPS COM REBAIXO PARA LED", 2, _drive("1LOGO115aaaaaaaaaaaaa")),
        _pagina(_texto(["LONAS"])),
        _ficha("LONA A", "7,14 x 1,10m", "15cm", "LONA IMPRESSA\nPANTONE 802C", 1, _drive("1LONAAaaaaaaaaaaaaaaa")),
        _pagina(_texto(["ADESIVOS"])),
        _ficha("QUADROS ADESIVADOS", "0,60 x 0,40m", "5cm", "ADESIVO", 1, _drive("1QUADROSaaaaaaaaaaaaa")),
        _ficha("QUADROS ADESIVADOS", "0,60 x 0,40m", "5cm", "ADESIVO", 1, _drive("1QUADROSaaaaaaaaaaaaa")),
        _ficha("PLACA PS", "1,00 x 0,50m", "5cm", "ADESIVO", 1, _drive("1PLACA1aaaaaaaaaaaaaa")),
        _ficha("PLACA PS", "1,00 x 0,50m", "5cm", "ADESIVO", 1, None),
        _pagina(_texto(["Obrigado por contar com nosso time!", "", "Conheça mais do nosso trabalho:"])),
    ])


class _Resposta:
    def __init__(self, status=200, conteudo=b"", cabecalhos=None, texto=None, url=""):
        self.status_code = status
        self.content = conteudo
        self.headers = cabecalhos or {}
        self.text = texto if texto is not None else conteudo.decode("latin-1", "replace")
        self.url = url

    def raise_for_status(self):
        if self.status_code >= 400:
            raise OSError("HTTP %s" % self.status_code)

    def iter_content(self, n):
        for i in range(0, len(self.content), n):
            yield self.content[i:i + n]

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _DrivePublico:
    """
    Serve arquivos públicos como o drive.usercontent.google.com responde:
    1 byte pedido devolve nome e tamanho; sem Range, o arquivo inteiro.
    Nome em UTF-8 no cabeçalho, como o Google manda (lido como latin-1).
    """
    def __init__(self, arquivos, privados=(), html_canva=None, paginas_vencidas=()):
        self.arquivos = arquivos          # id -> (nome, bytes)
        self.privados = set(privados)
        self.html_canva = html_canva
        self.paginas_vencidas = set(paginas_vencidas)
        self.downloads = []
        self.paginas_pedidas = []

    def get(self, url, params=None, headers=None, timeout=None, stream=False, allow_redirects=True):
        if url.startswith(MEDIA_CANVA):
            # a imagem de uma página do caderno; endereço vencido devolve XML de erro
            numero = int(re.search(r"hash:(\d+)", url).group(1))
            self.paginas_pedidas.append(numero)
            if numero in self.paginas_vencidas:
                return _Resposta(403, b"<?xml version='1.0'?><Error>Access denied</Error>")
            return _Resposta(200, b"\x89PNG\r\n\x1a\npagina %d" % numero, {"Content-Type": "image/png"})
        if "canva.com" in url:
            return _Resposta(200, texto=self.html_canva, url=url)
        id_ = (params or {}).get("id")
        if id_ in self.privados or id_ not in self.arquivos:
            return _Resposta(200, b"<html>login</html>", {"Content-Type": "text/html"})
        nome, dados = self.arquivos[id_]
        disp = 'attachment; filename="%s"' % nome.encode("utf-8").decode("latin-1")
        if "thumbnail" in url:
            return _Resposta(200, b"\x89PNG miniatura de " + id_.encode(), {"Content-Type": "image/png"})
        if (headers or {}).get("Range") == "bytes=0-0":
            return _Resposta(206, dados[:1], {"Content-Disposition": disp,
                                              "Content-Range": "bytes 0-0/%d" % len(dados)})
        self.downloads.append(id_)
        return _Resposta(200, dados, {"Content-Disposition": disp, "Content-Type": "application/octet-stream"})


def _pdf_bytes(paginas, sangria_m=0.0):
    """PDF com as caixas do arte-finalista: TrimBox = a arte, a página com a sangria em volta."""
    doc = pymupdf.open()
    for largura, altura in paginas:
        s = sangria_m * PT
        w, h = largura * PT + 2 * s, altura * PT + 2 * s
        pg = doc.new_page(width=w, height=h)
        pg.insert_text((s + 5, s + 15), "ARTE", fontsize=8)
        if s:
            pg.set_trimbox(pymupdf.Rect(s, s, w - s, h - s))
    dados = doc.tobytes()
    doc.close()
    return dados


# ================================================================ o link

def test_link_de_edicao_vira_o_de_visualizacao():
    """O /edit pede login (HTTP 403 no teste de 02/10); o /view, com o mesmo código, abre."""
    design, url = caderno_canva.link_de_visualizacao(LINK)
    assert design == "DAHWe8X_fZk"
    assert url == "https://www.canva.com/design/DAHWe8X_fZk/codigoDeCompartilhamento/view"


def test_link_sem_codigo_de_compartilhamento():
    _, url = caderno_canva.link_de_visualizacao("https://www.canva.com/design/DAHWe8X_fZk/edit?utm=x")
    assert url == "https://www.canva.com/design/DAHWe8X_fZk/view"


def test_link_que_nao_e_do_canva():
    with pytest.raises(caderno_canva.ErroCanva):
        caderno_canva.link_de_visualizacao("https://example.com/qualquer")


def test_abrir_reconhece_o_link_do_canva_sem_sair_pra_rede():
    assert isinstance(oa.abrir(LINK), oa.OrigemCaderno)


# =========================================================== o documento

def test_documento_sai_de_dentro_do_json_parse_escapado():
    html = _html(_documento([_pagina(_texto(["especificações = sim"]))]))
    doc = caderno_canva.documento_da_pagina(html)
    assert doc["D"] == "Caderno de artes - LOJINHA MR2 CULTURAL"
    assert caderno_canva._texto(doc["A"][0]["E"][0]) == "especificações = sim\n"


def test_documento_achado_mesmo_se_o_caminho_mudar():
    """O formato não é oficial: se o Canva mover o documento, ele é procurado pela forma."""
    html = _html(_lojinha(), caminho=("page", "outro", "lugar", "doc"))
    assert caderno_canva.documento_da_pagina(html)["D"].startswith("Caderno de artes")


def test_pagina_sem_o_caderno_dentro_para_com_mensagem():
    with pytest.raises(caderno_canva.ErroCanva, match="mudado o formato"):
        caderno_canva.documento_da_pagina("<html>nada aqui</html>")


def test_caderno_fechado_diz_o_que_pedir_ao_cliente():
    class Sessao:
        def get(self, url, **k):
            return _Resposta(403, texto="<html>login</html>", url=url)
    with pytest.raises(caderno_canva.ErroCanva, match="Qualquer pessoa com o link"):
        caderno_canva.baixar_pagina(LINK, Sessao())


# ================================================================ a ficha

def test_fichas_secoes_e_o_que_fica_de_fora():
    caderno = caderno_canva.ler_documento(_lojinha(), design_id="DAHWe8X_fZk")
    fichas = caderno["fichas"]

    assert caderno["paginas"] == 11
    assert [f["pagina"] for f in fichas] == [3, 5, 7, 8, 9, 10]
    assert [f["secao"] for f in fichas] == ["LOGOMARCAS", "LONAS", "ADESIVOS", "ADESIVOS", "ADESIVOS", "ADESIVOS"]
    lona = fichas[1]
    assert lona["nome"] == "LONA A"
    assert lona["medidas"] == "7,14 x 1,10m"
    assert lona["sangria"] == "15cm"
    assert lona["material"] == "LONA IMPRESSA PANTONE 802C"
    assert lona["quantidade"] == "1"


def test_vale_o_hiperlink_e_nao_o_endereco_escrito():
    """
    Na LOJINHA o texto azul das 60 fichas era o mesmo endereço, sobra do
    modelo — de um JPG de outro trabalho. O hiperlink de cada página é o certo.
    """
    lona = caderno_canva.ler_documento(_lojinha())["fichas"][1]
    assert lona["links"] == [_drive("1LONAAaaaaaaaaaaaaaaa")]
    assert "1E1siFydgATgf8zxyOkEisb8BqZUlUvkg" in lona["links_escritos"][0]


def test_sem_hiperlink_vale_o_endereco_escrito():
    doc = _documento([_ficha("PLACA", "1 x 1m", "", "PS", 1, None, escrito=_drive("1ESCRITOaaaaaaaaaaaaa"))])
    assert caderno_canva.ler_documento(doc)["fichas"][0]["links"] == [_drive("1ESCRITOaaaaaaaaaaaaa")]


def test_ficha_sem_hiperlink_nao_usa_o_link_escrito_do_modelo():
    """O endereço do modelo, repetido em todas as fichas, levaria à arte de outro trabalho."""
    ficha = caderno_canva.ler_documento(_lojinha())["fichas"][-1]
    assert ficha["nome"] == "PLACA PS" and ficha["links"] == [] and ficha["link_do_modelo"]


def test_rotulos_em_elementos_separados_tambem_formam_a_ficha():
    """Outro modelo de caderno: cada rótulo e valor numa caixa de texto."""
    pagina = _pagina(_texto(["CUPOM FISCAL"], topo=10), _texto(["Medidas:"], topo=20), _texto(["3,10 x 0,95m"], topo=30),
                     _texto(["Material:"], topo=40), _texto(["ADESIVO"], topo=50), _texto(["QTD"], topo=60),
                     _texto(["4"], topo=70))
    ficha = caderno_canva.ler_documento(_documento([pagina]))["fichas"][0]
    assert (ficha["nome"], ficha["medidas"], ficha["material"], ficha["quantidade"]) == (
        "CUPOM FISCAL", "3,10 x 0,95m", "ADESIVO", "4")


def test_texto_dentro_de_grupo_e_lido():
    grupo = {"A?": "H", "A": 0, "B": 0, "c": [_texto(["PAINEL", "medidas", "2 x 1m", "material", "LONA"])]}
    ficha = caderno_canva.ler_documento(_documento([_pagina(grupo)]))["fichas"][0]
    assert ficha["nome"] == "PAINEL" and ficha["material"] == "LONA"


# =================================================== medida e cor do caderno

@pytest.mark.parametrize("texto, metros", [
    ("2,51 x 0,65m", (2.51, 0.65)),
    ("1,15x 1,15m", (1.15, 1.15)),
    ("6,94m x 2,40m", (6.94, 2.40)),
    ("26,02cm x 10cm", (0.2602, 0.10)),
    ("A3 - 29,7 x 42cm", (0.297, 0.42)),
    ("A4 - 21 x 29,7cm", (0.21, 0.297)),
    ("2,0m x 2,10m", (2.0, 2.10)),
    ("7,00 x 6,00", (7.0, 6.0)),
])
def test_medida_do_caderno_com_a_unidade_em_qualquer_lado(texto, metros):
    assert caderno_arte.medida_em_metros(texto) == pytest.approx(metros)


def test_medida_sem_par_nao_vira_numero():
    assert caderno_arte.medida_em_metros("11CM DE ALTURA") is None


@pytest.mark.parametrize("texto, cor", [
    ("LONA IMPRESSA PANTONE 802C", "PANTONE 802C"),
    ("ADESIVO 382C", "PANTONE 382C"),
    ("LONA IMPRESSA 1655C", "PANTONE 1655C"),
    ("LOGO EM XPS COM REBAIXO PARA LED", None),
])
def test_cor_pantone_no_texto_do_material(texto, cor):
    assert caderno_arte.cor_no_texto(texto) == cor


# ======================================================== Drive público

def test_nome_do_cabecalho_volta_a_ter_acento():
    """O Google manda UTF-8 dentro de filename="..."; lido como latin-1 vira 'SAÃ\\x8dDA'."""
    bruto = 'attachment; filename="%s"' % "LETRA_CAIXA_SAÍDA.pdf".encode("utf-8").decode("latin-1")
    assert drive_artes.nome_do_cabecalho(bruto) == "LETRA_CAIXA_SAÍDA.pdf"
    assert drive_artes.nome_do_cabecalho("attachment; filename*=UTF-8''A%C3%87O.pdf") == "AÇO.pdf"


def test_info_publica_pede_um_byte_so():
    sessao = _DrivePublico({"x": ("LONA_A.pdf", b"%PDF" + b"0" * 996)})
    assert drive_artes.info_publica(sessao, "x") == {"id": "x", "name": "LONA_A.pdf", "size": 1000}
    assert sessao.downloads == []


def test_arquivo_restrito_nao_e_publico():
    sessao = _DrivePublico({}, privados={"x"})
    assert drive_artes.info_publica(sessao, "x") is None
    assert drive_artes.miniatura_publica(sessao, "x") is None


def test_baixar_publico_que_vira_pagina_de_login_nao_deixa_nada(tmp_path):
    sessao = _DrivePublico({}, privados={"x"})
    destino = tmp_path / "a" / "x.pdf"
    with pytest.raises(drive_artes.NaoPublico):
        drive_artes.baixar_publico(sessao, "x", destino)
    assert not destino.exists() and not list(destino.parent.iterdir())


# ======================================================== a origem do caderno

def _arquivos_da_lojinha():
    return {
        "1LOGO115aaaaaaaaaaaaa": ("LOGO_TESTEIRA_1,15x1,15m_loja_de_incoveniencia_vibra_sangria2cm_facadecorte.pdf",
                    _pdf_bytes([(1.15, 1.15)], 0.02)),
        "1LONAAaaaaaaaaaaaaaaa": ("LONA_A_7,14x1,10m_loja_de_incoveniencia_vibra_sangria15cm.pdf",
                  _pdf_bytes([(0.714, 0.110)], 0.015)),          # desenhada em 1:10
        "1QUADROSaaaaaaaaaaaaa": ("QUADROS_ADESIVOS_0,60x0,40m_loja_de_incoveniencia_vibra_sangria5cm.pdf",
                    _pdf_bytes([(0.40, 0.60)] * 2, 0.05)),       # 2 fichas, 2 páginas
        "1PLACA1aaaaaaaaaaaaaa": ("PLACA_PS_1_1,00x0540m_loja_de_incoveniencia_vibra_sangria5cm.pdf",
                   _pdf_bytes([(1.00, 0.50)], 0.05)),
    }


def _origem(arquivos=None, privados=(), api=None):
    arquivos = arquivos if arquivos is not None else _arquivos_da_lojinha()
    sessao = _DrivePublico(arquivos, privados=privados, html_canva=_html(_lojinha()))
    return oa.OrigemCaderno(LINK, sessao=sessao, api=api), sessao


def test_cada_ficha_vira_um_grupo_com_a_secao_na_frente():
    origem, _ = _origem()
    itens = origem.listar()

    assert origem.rotulo.startswith("Canva  ·  Caderno de artes - LOJINHA MR2 CULTURAL  ·  6 peças")
    assert [a.grupo for a in itens] == ["LOGOMARCAS / 03 · LOGO TESTEIRA", "LONAS / 05 · LONA A",
                                        "ADESIVOS / 07 · QUADROS ADESIVADOS", "ADESIVOS / 08 · QUADROS ADESIVADOS",
                                        "ADESIVOS / 09 · PLACA PS"]
    assert all(a.ficha for a in itens)
    assert origem.resumo_do_grupo("LONAS / 05 · LONA A") == (
        "7,14 x 1,10m  ·  sangria 15cm  ·  LONA IMPRESSA PANTONE 802C  ·  1 un")
    motivo = dict(origem.ignorados)["página 10 (PLACA PS)"]
    assert "link escrito do modelo" in motivo


def test_o_mesmo_arquivo_em_duas_fichas_sao_dois_itens_de_um_arquivo_so():
    origem, sessao = _origem()
    q1, q2 = [a for a in origem.listar() if a.mesmo_arquivo == "1QUADROSaaaaaaaaaaaaa"]

    assert q1.id != q2.id
    assert origem.baixar(q1, caminhos.PASTA_RECEBENDO) == origem.baixar(q2, caminhos.PASTA_RECEBENDO)
    assert sessao.downloads == ["1QUADROSaaaaaaaaaaaaa"], "baixou o mesmo arquivo duas vezes"


def test_miniatura_vem_pronta_do_google_sem_baixar_a_arte():
    origem, sessao = _origem()
    lona = origem.listar()[1]
    assert origem.miniatura(lona).startswith(b"\x89PNG")
    assert sessao.downloads == []


def test_arquivo_restrito_vai_pela_api():
    class Pedido:
        def __init__(self, dado):
            self.dado = dado

        def execute(self):
            return self.dado

    class Arquivos:
        def get(self, fileId, fields=None, supportsAllDrives=True):
            return Pedido({"id": fileId, "name": "LONA_A.pdf", "mimeType": "application/pdf", "size": "77"})

    class Servico:
        def files(self):
            return Arquivos()

    origem, _ = _origem(privados={"1LONAAaaaaaaaaaaaaaaa"}, api=(Servico(), lambda url: b""))
    lona = next(a for a in origem.listar() if a.mesmo_arquivo == "1LONAAaaaaaaaaaaaaaaa")
    assert lona.ref["via"] == "api" and lona.nome == "LONA_A.pdf" and lona.bytes == 77


def test_caderno_lido_fica_guardado(tmp_path):
    origem, _ = _origem()
    origem.listar()
    gravados = origem.guardar_original(tmp_path / "recebidos")
    caminho = gravados[0]
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    assert dados["titulo"].endswith("LOJINHA MR2 CULTURAL") and len(dados["fichas"]) == 6 and dados["lido_em"]


# ============================ a página do caderno em imagem (02/10, à noite)
#
# "Os arquivos abrem, porém a parte onde está localizado no caderno continua
# travada": o visualizador do Canva não termina de abrir um caderno de 68
# páginas. A imagem de cada página passa a viajar com o recebimento.

def test_endereco_da_imagem_de_cada_pagina_sai_do_mesmo_json():
    dados = caderno_canva._bootstrap(_html(_lojinha()))
    enderecos = caderno_canva.enderecos_das_paginas(dados)
    assert sorted(enderecos) == list(range(1, 12))
    assert enderecos[5].startswith(MEDIA_CANVA)


def test_endereco_das_paginas_achado_mesmo_se_o_caminho_mudar():
    """Plano B, como o do documento: procura o 'thumbnail' em qualquer lugar."""
    dados = caderno_canva._bootstrap(_html(_lojinha(), caminho=("page", "outro", "content")))
    assert len(caderno_canva.enderecos_das_paginas(dados)) == 11


def test_caderno_sem_imagem_nenhuma_nao_quebra_a_leitura():
    """A imagem é conforto: sem ela, o caderno continua sendo lido."""
    dados = caderno_canva._bootstrap(_html(_lojinha(), com_imagens=False))
    assert caderno_canva.enderecos_das_paginas(dados) == {}


def test_baixa_so_as_paginas_pedidas_e_descarta_o_que_nao_e_imagem():
    sessao = _DrivePublico({}, html_canva=_html(_lojinha()), paginas_vencidas={5})
    dados = caderno_canva._bootstrap(_html(_lojinha()))
    enderecos = caderno_canva.enderecos_das_paginas(dados)

    imagens = caderno_canva.baixar_paginas(enderecos, {3, 5, 7}, sessao)

    assert sorted(sessao.paginas_pedidas) == [3, 5, 7], "baixou página que ninguém pediu"
    assert sorted(imagens) == [3, 7], "endereço vencido devolve XML, e XML não é imagem"
    assert imagens[3].startswith(b"\x89PNG")


def test_listar_ja_guarda_a_imagem_das_paginas_com_ficha():
    """O endereço vence em horas, e o passo 1 pode ficar aberto a tarde inteira."""
    origem, sessao = _origem()
    origem.listar()

    assert sorted(origem.paginas) == [3, 5, 7, 8, 9, 10]
    assert 1 not in sessao.paginas_pedidas, "a capa não tem ficha: não precisa da imagem"


def test_a_pagina_do_caderno_fica_guardada_ao_lado_do_caderno(tmp_path):
    origem, _ = _origem()
    origem.listar()
    pasta = tmp_path / "recebidos"

    origem.guardar_original(pasta)

    guardadas = caderno_canva.imagens_guardadas(pasta)
    assert sorted(guardadas) == [3, 5, 7, 8, 9, 10]
    assert guardadas[5].name == "0005.png" and guardadas[5].read_bytes().startswith(b"\x89PNG")
    dados = json.loads((pasta / "caderno.json").read_text(encoding="utf-8"))
    assert "enderecos_das_paginas" not in dados, "endereço que vence em horas não se guarda"
    assert dados["paginas_em_imagem"]["5"], "o rodapé da página anexada diz de quando é a imagem"


def test_pagina_mexida_depois_do_recebimento_nao_vale_mais():
    """
    O cliente edita o Canva quando quer: página que mudou não pode ilustrar
    um recebimento antigo, e uma página nova no meio empurra todas as outras.
    """
    guardado = caderno_canva.ler_documento(_lojinha())
    mexido = _lojinha()
    mexido["A"][4] = _ficha("LONA A", "7,14 x 2,20m", "15cm", "LONA IMPRESSA", 1,
                            _drive("1LONAAaaaaaaaaaaaaaaa"))     # a medida mudou na página 5
    novo = caderno_canva.ler_documento(mexido)

    conferem = caderno_canva.paginas_que_conferem(guardado, novo)
    assert 5 not in conferem
    assert {3, 7, 8, 9, 10} <= conferem


# ================================================== do caderno até o nome

def _pecas_da_lojinha():
    origem, _ = _origem()
    itens = origem.listar()
    baixados = [(a, origem.baixar(a, caminhos.PASTA_RECEBENDO), origem.chave(a)) for a in itens]
    pecas = ra.propor(baixados, todos=itens, cliente="VIBRA")
    return {p.ficha["pagina"]: p for p in pecas}, pecas


def test_material_e_quantidade_vem_da_ficha():
    """'Respeite sempre o que for material que o cliente pede' — e XPS é PVC."""
    por_pagina, _ = _pecas_da_lojinha()
    logo = por_pagina[3]
    assert (logo.material, logo.quantidade) == ("PVC", 2)
    assert logo.de_onde["material"] == "caderno (página 3)"


def test_lona_em_escala_1_10_ganha_o_tamanho_do_caderno_e_avisa():
    """A LONA A da LOJINHA: 7,14 x 1,10 no caderno, 0,714 x 0,110 no PDF."""
    por_pagina, _ = _pecas_da_lojinha()
    lona = por_pagina[5]

    assert (lona.escala, lona.escala_achada) == (10, 10)
    assert lona.arte_m == pytest.approx((7.14, 1.10), abs=0.001)
    assert lona.sangria_m == pytest.approx((7.44, 1.40), abs=0.001)
    assert lona.arte_pdf_m == pytest.approx((0.714, 0.110), abs=0.0001)
    assert any("escala 1:10" in a for a in lona.avisos)
    assert ra.nome_final(lona) == "1UN LONA 7,44X1,40M_LONA A ESCALA 1-10_final 7,14X1,10M.pdf"


def test_escala_desligada_na_tela_volta_pro_pdf():
    por_pagina, _ = _pecas_da_lojinha()
    lona = ra.aplicar_escala(por_pagina[5], False)
    assert lona.escala == 1 and lona.arte_m == pytest.approx((0.714, 0.110), abs=0.0001)
    assert "ESCALA" not in ra.nome_final(lona)
    ra.aplicar_escala(lona, True)
    assert lona.arte_m == pytest.approx((7.14, 1.10), abs=0.001)


def test_duas_fichas_no_mesmo_pdf_de_duas_paginas_dividem_as_paginas():
    por_pagina, _ = _pecas_da_lojinha()
    q1, q2 = por_pagina[7], por_pagina[8]
    assert (q1.pagina, q2.pagina) == (1, 2)
    assert ra.nome_final(q1) == "1UN ADESIVO 0,50X0,70M_QUADROS ADESIVOS_final 0,40X0,60M.pdf"
    assert ra.nome_final(q2) == "1UN ADESIVO 0,50X0,70M_QUADROS ADESIVOS - PAGINA 2_final 0,40X0,60M.pdf"


def test_descricao_vem_do_arquivo_sem_o_nome_do_projeto():
    """15 fichas 'PLACA PS' na LOJINHA; os arquivos é que se chamam PLACA_PS_1, PLACA_PS_2..."""
    por_pagina, pecas = _pecas_da_lojinha()
    assert por_pagina[9].descricao == "PLACA PS 1"         # placa é PS ADESIVADO: o PS fica
    assert por_pagina[3].descricao == "LOGO TESTEIRA FACADECORTE"
    assert not ra.repetidos(pecas)


def test_placa_e_ps_adesivado_na_medida_final():
    """Regra do usuário de 02/10: "quando falar placa pode colocar o PS + adesivo" — e a chapa é cortada no final."""
    por_pagina, _ = _pecas_da_lojinha()
    placa = por_pagina[9]
    assert placa.material == "PS ADESIVADO"
    assert placa.de_onde["material"].startswith("regra da placa")
    assert not any("escolha '" in a for a in placa.avisos)
    assert ra.nome_final(placa) == "1UN PS ADESIVADO 1,00X0,50M_PLACA PS 1_sangria 1,10X0,60M.pdf"
    assert ra.medida_que_conta(placa) == pytest.approx((1.00, 0.50))


def test_arquivar_registra_a_ficha_e_a_escala(tmp_path):
    import clientes
    _, pecas = _pecas_da_lojinha()
    cliente = clientes.criar("VIBRA")
    lona = next(p for p in pecas if p.ficha["pagina"] == 5)

    ra.arquivar([lona], cliente, cliente.pasta / "ARTES", origem=None, remover_marcas=False)

    registro = json.loads((cliente.pasta / "_baixados.json").read_text(encoding="utf-8"))
    entrada, = registro.values()
    assert entrada["escala"] == 10
    assert entrada["medida_no_arquivo_m"] == pytest.approx([0.714, 0.11])
    assert entrada["caderno"]["pagina"] == 5 and entrada["caderno"]["material"] == "LONA IMPRESSA PANTONE 802C"
    assert (cliente.pasta / "ARTES" / ra.nome_final(lona)).is_file()


# ================================================================ escala

def test_escala_so_com_prova_nos_dois_lados():
    assert ra.escala_provada([(0.714, 0.110)], [(7.14, 1.10)]) == (10, "total")
    assert ra.escala_provada([(7.14, 1.10)], [(7.14, 1.10)]) == (1, None)


def test_sem_referencia_nao_multiplica_sozinho():
    """Regra do usuário de 29/08: sem referência confiável, não multiplicar."""
    assert ra.escala_provada([(0.714, 0.110)], [None, None]) == (1, None)


def test_medida_trocada_no_caderno_nao_vira_escala():
    """Caderno 6,00 x 0,40 pra arte 0,60 x 0,40: é o caderno errado, não escala."""
    assert ra.escala_provada([(0.60, 0.40)], [(6.00, 0.40)]) == (1, None)


def test_um_lado_exato_e_o_outro_perto_e_escala_parcial():
    """A LONA 18: 6,00 bate × 10; a altura dá 2,40 contra 2,70 do caderno — escala, e confira."""
    assert ra.escala_provada([(0.60, 0.24)], [(6.00, 2.70)]) == (10, "parcial")


def test_paginas_que_sao_partes_da_peca():
    """O piso de 7,00 x 6,00 da LOJINHA, em três lonas de tamanhos diferentes, em 1:10."""
    assert ra.escala_provada([(0.445, 0.365), (0.700, 0.235), (0.255, 0.600)], [(7.00, 6.00)]) == (10, "partes")


def test_escala_vale_tambem_sem_caderno_pela_medida_do_nome(tmp_path):
    """O 'Esc_10_1' do SPFW: o nome diz 200x20cm e a arte tem um décimo — e o nome não repete a escala."""
    a = oa.Arquivo(id="x", nome="AF_TABLADO_FRENTE 200x20cm_Esc_10_1.pdf")
    local = tmp_path / "x.pdf"
    local.write_bytes(_pdf_bytes([(0.20, 0.02)]))

    peca, = ra.propor([(a, local, "teste|x")])

    assert peca.escala == 10 and peca.arte_m == pytest.approx((2.0, 0.2), abs=0.001)
    assert ra.nome_final(peca).count("ESC") == 1


# ============================================================ a tela

def test_lista_de_materiais_tem_a_chapa_adesivada():
    escolhas = ra.materiais_para_escolher()
    assert escolhas[0] == "A DEFINIR" and "LONA" in escolhas and "PS ADESIVADO" in escolhas
    assert "ADESIVO ADESIVADO" not in escolhas and "LONA ADESIVADO" not in escolhas


def test_trecho_comum_e_o_nome_do_projeto():
    nomes = ["LONA_A_7,14x1,10m_loja_de_incoveniencia_vibra_sangria15cm",
             "PLACA_PS_1_1,00x0540m_loja_de_incoveniencia_vibra_sangria5cm",
             "LOGO_TESTEIRA_1,15x1,15m_loja_de_incoveniencia_vibra_sangria2cm_facadecorte",
             "PLACAS_QRCODE_A4_21x29,7cm_sangria5cm_2modelos"]
    assert ra.trecho_comum(nomes) == ("LOJA", "DE", "INCOVENIENCIA", "VIBRA")


# ============================================ casos que o próximo caderno pode trazer

def test_duas_fichas_na_mesma_pagina_cada_uma_com_o_seu_link():
    """Página com duas peças: nenhuma se perde e o link de uma não vai pra outra."""
    pagina = _pagina(
        _texto(["TOTEM A", "medidas", "1 x 2m", "material", "PS"], topo=100, esquerda=100),
        _texto(["link"], links=[_drive("1TOTEMAaaaaaaaaaaaaaa")], topo=400, esquerda=100),
        _texto(["TOTEM B", "medidas", "1 x 2m", "material", "PS"], topo=100, esquerda=1200),
        _texto(["link"], links=[_drive("1TOTEMBaaaaaaaaaaaaaa")], topo=400, esquerda=1200))
    a, b = caderno_canva.ler_documento(_documento([pagina]))["fichas"]

    assert (a["nome"], a["links"], a["na_pagina"]) == ("TOTEM A", [_drive("1TOTEMAaaaaaaaaaaaaaa")], 1)
    assert (b["nome"], b["links"], b["na_pagina"]) == ("TOTEM B", [_drive("1TOTEMBaaaaaaaaaaaaaa")], 2)
    assert oa._nome_de_grupo(b) == "01.2 · TOTEM B"


def test_material_que_nao_existe_no_cadastro_avisa_e_fica_a_definir():
    ficha = {"pagina": 4, "nome": "BANDEIRA", "material": "TECIDO", "quantidade": "3"}
    qtd, material, _, avisos = ra.especificacao_do_caderno(ficha, oa.Arquivo(id="x", nome="BANDEIRA.pdf"))
    assert (qtd, material) == (3, "A DEFINIR")
    assert any("'TECIDO'" in a for a in avisos)


def test_material_trocado_na_tela_nao_deixa_outro_material_no_nome():
    """'ADESIVO ESPELHOS' passado pra PS ADESIVADO: com o ADESIVO no nome, o leitor lia ADESIVO e o PS sumia."""
    from config import carregar_config
    from dimensoes import identificar_categoria
    peca = ra.Peca(arquivo=oa.Arquivo(id="x", nome="ADESIVO_ESPELHOS.pdf"), local=pathlib.Path("x.pdf"),
                   chave="t|x", papel="arte", descricao="ADESIVO ESPELHOS", material="PS ADESIVADO",
                   arte_m=(0.60, 1.45))
    nome = ra.nome_final(peca)
    c = carregar_config()
    assert nome == "1UN PS ADESIVADO 0,60X1,45M_ESPELHOS.pdf"
    assert identificar_categoria(nome.upper(), c["materiais"], c.get("sinonimos_categoria", {}))[0] == "PS"
    peca.material = "ADESIVO"
    assert ra.nome_final(peca) == "1UN ADESIVO 0,60X1,45M_ADESIVO ESPELHOS.pdf"


# ======================================== regras do usuário de 2026-10-02

def test_com_sangria_o_tamanho_maior_vai_na_frente_e_e_o_que_conta():
    """"o restante manter o tamanho maior sempre que é com sangria" — como a equipe já nomeia as lonas."""
    por_pagina, _ = _pecas_da_lojinha()
    lona = por_pagina[5]
    assert ra.medidas_do_nome(lona) == ("7,44X1,40M", "7,14X1,10M", "final")
    assert ra.medida_que_conta(lona) == pytest.approx((7.44, 1.40), abs=0.001)


def test_sem_sangria_nao_ha_segunda_medida():
    peca = ra.Peca(arquivo=oa.Arquivo(id="x", nome="FAIXA.pdf"), local=pathlib.Path("x.pdf"), chave="t|x",
                   papel="arte", descricao="FAIXA", material="LONA", arte_m=(3.0, 1.0), sangria_m=(3.0, 1.0))
    assert ra.nome_final(peca) == "1UN LONA 3,00X1,00M_FAIXA.pdf"


def test_placa_que_cita_outra_chapa_fica_fora_da_regra_do_ps():
    config = {"materiais": {"PS": {"tipo": "chapa"}, "PVC": {"tipo": "chapa"}, "ADESIVO": {"tipo": "rolo"}},
              "materiais_compostos": {"ADESIVADO": "ADESIVO"}, "sinonimos_categoria": {"XPS": "PVC"}}
    assert ra.regra_da_placa(("PLACA PVC 10MM",), "ADESIVO", config) == ("ADESIVO", None)
    assert ra.regra_da_placa(("PLACA EM XPS",), "ADESIVO", config) == ("ADESIVO", None)
    assert ra.regra_da_placa(("PLACA ENTRADA",), "A DEFINIR", config)[0] == "PS ADESIVADO"
    assert ra.regra_da_placa(("PLACA PS",), "PS", config)[0] == "PS ADESIVADO"
    assert ra.regra_da_placa(("QUADROS ADESIVADOS",), "ADESIVO", config) == ("ADESIVO", None)


def test_placa_sem_caderno_tambem_e_ps_adesivado(tmp_path):
    """A regra é da placa, não do caderno: o arquivo que chega solto também."""
    a = oa.Arquivo(id="x", nome="PLACA_ENTRADA_1,00x0,50m.pdf")
    local = tmp_path / "x.pdf"
    local.write_bytes(_pdf_bytes([(1.00, 0.50)], 0.05))

    peca, = ra.propor([(a, local, "teste|x")])

    assert peca.material == "PS ADESIVADO"
    assert ra.nome_final(peca) == "1UN PS ADESIVADO 1,00X0,50M_PLACA ENTRADA_sangria 1,10X0,60M.pdf"


def test_registro_diz_que_a_medida_do_nome_e_com_sangria(tmp_path):
    import clientes
    _, pecas = _pecas_da_lojinha()
    cliente = clientes.criar("VIBRA")
    lona = next(p for p in pecas if p.ficha["pagina"] == 5)
    placa = next(p for p in pecas if p.ficha["pagina"] == 9)

    ra.arquivar([lona, placa], cliente, cliente.pasta / "ARTES", origem=None, remover_marcas=False)

    registro = json.loads((cliente.pasta / "_baixados.json").read_text(encoding="utf-8"))
    por_arquivo = {r["arquivo"]: r for r in registro.values()}
    assert por_arquivo[ra.nome_final(lona)]["medida_no_nome"] == "com sangria"
    assert "medida_no_nome" not in por_arquivo[ra.nome_final(placa)]


def test_peca_de_chapa_maior_que_a_chapa_avisa(tmp_path):
    """O CUPOM FISCAL (3,10 m) caiu na regra da placa, e a chapa de PS cadastrada não passa de 2 m."""
    a = oa.Arquivo(id="x", nome="PLACA_CUPOM_FISCAL_3,10x0,95m.pdf")
    local = tmp_path / "x.pdf"
    local.write_bytes(_pdf_bytes([(3.10, 0.95)]))

    peca, = ra.propor([(a, local, "teste|x")])

    assert peca.material == "PS ADESIVADO"
    assert any("maior que a chapa de PS" in av for av in peca.avisos)


def test_arquivar_guarda_de_onde_veio_e_a_pagina_do_caderno():
    """O relatório de recebimento mostra os dois links (pedido de 02/10)."""
    import clientes
    origem, _ = _origem()
    itens = origem.listar()
    baixados = [(a, origem.baixar(a, caminhos.PASTA_RECEBENDO), origem.chave(a)) for a in itens]
    lona = next(p for p in ra.propor(baixados, todos=itens, cliente="VIBRA") if p.ficha["pagina"] == 5)
    cliente = clientes.criar("VIBRA")

    ra.arquivar([lona], cliente, cliente.pasta / "ARTES", origem=origem, remover_marcas=False,
                guardar_original=False)

    entrada, = json.loads((cliente.pasta / "_baixados.json").read_text(encoding="utf-8")).values()
    assert entrada["link_origem"] == "https://drive.google.com/file/d/1LONAAaaaaaaaaaaaaaaa/view"
    assert entrada["link_caderno"] == "https://www.canva.com/design/DAHWe8X_fZk/codigoDeCompartilhamento/view"
