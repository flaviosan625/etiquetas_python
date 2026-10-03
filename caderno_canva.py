"""
Caderno de arte feito no CANVA — lido pelo link, sem login e sem API.

Por que existe (2026-10-02): o caderno da LOJINHA MR2 CULTURAL (cliente
VIBRA) chegou como um design do Canva, não como apresentação do Google
Slides. Pedido do usuário: "preciso que toda a parte de recebimento de arte
leia esse caderno também em Canva, juntamente com os modelos que já temos".

O QUE SE DESCOBRIU SONDANDO O CADERNO DE VERDADE (2026-10-02)
  - O link de EDIÇÃO (/edit) pede login: HTTP 403. O de VISUALIZAÇÃO
    (/view), com o mesmo código de compartilhamento, abre sem login quando
    o design está como "qualquer pessoa com o link".
  - A página de visualização traz o documento inteiro embutido, em
    window['bootstrap'] = JSON.parse('...'), no caminho
    page.Pm.E.draft.content: 'D' é o título e 'A' a lista de páginas. Cada
    página tem 'E', a lista de elementos; 'K' é texto, e o texto mora em
    a.C.A (um parágrafo por item) com os estilos em a.C.C — é no estilo,
    campo 'Q', que fica o LINK de cada trecho. 'H' é grupo, com os filhos
    em 'c'.
  - O LINK ESCRITO NA PÁGINA NÃO É O LINK. Nas 60 fichas desse caderno o
    texto azul é o MESMO endereço (sobra do modelo: aponta um
    'Laterais_1x3cm-15sangria_90dpi_TV.jpg' de outro trabalho), e o
    hiperlink de cada página aponta o arquivo certo daquela peça. Vale
    sempre o hiperlink; o texto só conta quando não há hiperlink nenhum.
  - A ficha é UM bloco de texto: a primeira linha é o nome da peça, e
    depois rótulo e valor, um embaixo do outro, em minúsculas — 'medidas',
    'sangria', 'material', 'quantidade'. O material pode ocupar duas
    linhas ('LONA IMPRESSA' / 'PANTONE 802C').
  - Página com UM texto só, curto e em maiúsculas ('LOGOMARCAS', 'LONAS',
    'ADESIVOS') abre uma seção do caderno.
  - A mesma página traz uma IMAGEM de cada página do caderno (596 x 335
    px, com endereço que vence em horas) — é ela que mostra onde a peça
    fica na loja, já que o visualizador do Canva trava num caderno desse
    tamanho. Ver enderecos_das_paginas.

É o formato interno do Canva, não uma API oficial: pode mudar sem aviso,
como o do WeTransfer. Quando mudar, a leitura PARA com mensagem (nunca lê
pela metade); as artes continuam entrando pela origem 'Pasta...' baixadas
à mão.

Este módulo só lê o caderno. Quem vai buscar os arquivos que os links
apontam é origem_artes.OrigemCaderno; quem dá o nome, receber_artes.
"""
import json
import pathlib
import re
import unicodedata

NAVEGADOR = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
             "(KHTML, like Gecko) Chrome/128.0 Safari/537.36")

_LINK = re.compile(r"canva\.com/design/([A-Za-z0-9_-]{6,})(?:/([A-Za-z0-9_-]{6,}))?", re.I)
_ACOES = {"edit", "view", "watch", "present", "remix"}
_BOOTSTRAP = re.compile(r"window\['bootstrap'\]\s*=\s*JSON\.parse\('((?:[^'\\]|\\.)*)'\)", re.S)

# Rótulo da ficha (sem acento, minúsculo, sem ':') -> campo. A ficha do
# Canva escreve em minúsculas; os do Slides (caderno_arte._ROTULOS) em
# maiúsculas — a comparação ignora isso.
_ROTULOS = {
    "nome do arquivo": "nome",
    "medidas": "medidas", "medida": "medidas", "tamanho": "medidas", "medidas finais": "medidas",
    "medidas com sangria": "medidas_sangria",
    "sangria": "sangria",
    "material": "material", "materiais": "material",
    "quantidade": "quantidade", "qtd": "quantidade", "qtdd": "quantidade", "qtde": "quantidade",
    "quant": "quantidade",
    "obs": "obs", "observacao": "obs", "observacoes": "obs",
    "acabamento": "acabamento",
}
CAMPOS = ("nome", "medidas", "medidas_sangria", "sangria", "material", "quantidade", "obs", "acabamento")

# Títulos das áreas da página (em volta das imagens), que não são a ficha.
_ROTULOS_DA_PAGINA = {"ortogonal", "3d", "arte", "especificacoes", "especificacao", "link", "links",
                      "planta", "vista", "render", "referencia"}

_LIMITE_SECAO = 40


class ErroCanva(Exception):
    """Mensagem pronta pra tela: o que deu errado e o que fazer."""


def _sem_acento(texto):
    t = unicodedata.normalize("NFKD", str(texto or ""))
    return "".join(c for c in t if not unicodedata.combining(c))


def _rotulo(linha):
    """O campo que essa linha anuncia, ou None."""
    t = re.sub(r"[\s:.]+$", "", _sem_acento(linha).strip().lower())
    return _ROTULOS.get(re.sub(r"\s+", " ", t))


# ----------------------------------------------------------------------
# O link
# ----------------------------------------------------------------------

def e_link_do_canva(texto):
    t = (texto or "").lower()
    return "canva.com/design/" in t or "canva.link/" in t


def link_de_visualizacao(link):
    """
    (id_do_design, endereço de visualização) a partir de qualquer link do
    design — o de edição pede login, o de visualização não.
    """
    m = _LINK.search(link or "")
    if not m:
        raise ErroCanva("Não reconheci esse link do Canva. Use o link do design "
                        "(canva.com/design/...), o mesmo de abrir no navegador.")
    design, codigo = m.group(1), m.group(2)
    if codigo and codigo.lower() in _ACOES:
        codigo = None
    if codigo:
        return design, "https://www.canva.com/design/%s/%s/view" % (design, codigo)
    return design, "https://www.canva.com/design/%s/view" % design


def _sessao_padrao():
    import requests
    sessao = requests.Session()
    sessao.headers["User-Agent"] = NAVEGADOR
    return sessao


def baixar_pagina(link, sessao=None):
    """O HTML da página de visualização do design. (id_do_design, html)."""
    sessao = sessao or _sessao_padrao()
    if "canva.link/" in (link or "").lower():
        try:
            link = sessao.get(link, allow_redirects=True, timeout=40).url
        except Exception as e:
            raise ErroCanva("Não consegui abrir o link curto do Canva: %s" % e)
    design, url = link_de_visualizacao(link)
    try:
        r = sessao.get(url, allow_redirects=True, timeout=60)
    except Exception as e:
        raise ErroCanva("Não consegui abrir o caderno no Canva: %s" % e)
    texto = r.text or ""
    if r.status_code == 200 and "window['bootstrap']" in texto:
        return design, texto
    if r.status_code in (401, 403) and "challenge-platform" in texto and "bootstrap" not in texto:
        raise ErroCanva("O Canva pediu verificação de navegador e não entregou o caderno. Tente de "
                        "novo em alguns minutos.")
    if r.status_code in (401, 403) or "/login" in (getattr(r, "url", "") or ""):
        raise ErroCanva("O caderno não está aberto pra quem tem o link. Peça ao cliente: no Canva, "
                        "Compartilhar > Acesso: 'Qualquer pessoa com o link' pode ver.")
    if r.status_code == 404:
        raise ErroCanva("O Canva diz que esse design não existe (foi apagado, ou o link está errado).")
    raise ErroCanva("O Canva não entregou o caderno (HTTP %s). Se continuar, baixe as artes à mão "
                    "e use 'Pasta...'." % r.status_code)


# ----------------------------------------------------------------------
# O documento embutido na página
# ----------------------------------------------------------------------

def _desfazer_escape_js(texto):
    """O conteúdo de uma string JS entre aspas simples, como o navegador lê."""
    def troca(m):
        e = m.group(1)
        if e[0] in "xu":
            return chr(int(e[1:], 16))
        return {"n": "\n", "t": "\t", "r": "\r", "b": "\b", "f": "\f", "v": "\v", "0": "\0"}.get(e, e)
    return re.sub(r"\\(x[0-9a-fA-F]{2}|u[0-9a-fA-F]{4}|.)", troca, texto, flags=re.S)


def _parece_documento(no):
    if not (isinstance(no, dict) and isinstance(no.get("A"), list) and isinstance(no.get("D"), str)):
        return False
    paginas = [p for p in no["A"] if isinstance(p, dict)]
    return bool(paginas) and all(isinstance(p.get("E", []), list) for p in paginas)


def _procurar_documento(no, profundidade=0):
    """Plano B, se o caminho mudar: o primeiro nó com cara de documento."""
    if profundidade > 12:
        return None
    if _parece_documento(no):
        return no
    filhos = no.values() if isinstance(no, dict) else (no if isinstance(no, list) else ())
    for filho in filhos:
        if isinstance(filho, (dict, list)):
            achado = _procurar_documento(filho, profundidade + 1)
            if achado is not None:
                return achado
    return None


def _bootstrap(html):
    """O JSON inteiro que a página de visualização carrega."""
    m = _BOOTSTRAP.search(html or "")
    if not m:
        raise ErroCanva("A página do Canva veio sem o caderno dentro — o Canva pode ter mudado o "
                        "formato. Baixe as artes à mão e use 'Pasta...'.")
    try:
        return json.loads(_desfazer_escape_js(m.group(1)))
    except ValueError as e:
        raise ErroCanva("Não consegui ler o caderno de dentro da página do Canva: %s" % e)


def documento_da_pagina(html, dados=None):
    """O documento do design ({'D': título, 'A': páginas}) de dentro do HTML."""
    dados = _bootstrap(html) if dados is None else dados
    try:
        conteudo = dados["page"]["Pm"]["E"]["draft"]["content"]
    except (KeyError, TypeError):
        conteudo = None
    if not _parece_documento(conteudo):
        conteudo = _procurar_documento(dados)
    if conteudo is None:
        raise ErroCanva("A página do Canva não tem as páginas do caderno onde eu esperava — o Canva "
                        "pode ter mudado o formato. Baixe as artes à mão e use 'Pasta...'.")
    return conteudo


# ----------------------------------------------------------------------
# Elementos de uma página
# ----------------------------------------------------------------------

def _elementos(pagina):
    """Todos os elementos da página, entrando nos grupos ('H' guarda os filhos em 'c')."""
    fila = list(pagina.get("E") or [])
    saida = []
    while fila:
        e = fila.pop(0)
        if not isinstance(e, dict):
            continue
        saida.append(e)
        if isinstance(e.get("c"), list):
            fila.extend(e["c"])
    return saida


def _texto_rico(elemento):
    a = elemento.get("a")
    rico = a.get("C") if isinstance(a, dict) else None
    return rico if isinstance(rico, dict) else None


def _texto(elemento):
    rico = _texto_rico(elemento)
    if not rico:
        return ""
    return "".join(p for p in rico.get("A") or [] if isinstance(p, str))


def _hiperlinks(elemento):
    rico = _texto_rico(elemento) or {}
    return [c["Q"] for c in rico.get("C") or []
            if isinstance(c, dict) and isinstance(c.get("Q"), str) and c["Q"].startswith("http")]


def _num(v):
    return v if isinstance(v, (int, float)) else 0


def _posicao(elemento):
    """(topo, esquerda): no Canva 'A' é o topo e 'B' a esquerda do elemento."""
    return (_num(elemento.get("A")), _num(elemento.get("B")))


def _centro(elemento):
    """O meio do elemento ('C' é a altura e 'D' a largura)."""
    return (_num(elemento.get("A")) + _num(elemento.get("C")) / 2,
            _num(elemento.get("B")) + _num(elemento.get("D")) / 2)


# ----------------------------------------------------------------------
# A ficha
# ----------------------------------------------------------------------

def ficha_do_texto(texto):
    """
    Os campos de um bloco de ficha. O que vem antes do primeiro rótulo é
    o nome da peça; cada rótulo leva as linhas seguintes até o próximo.
    None quando o bloco não tem pelo menos dois rótulos (não é ficha).
    """
    linhas = [l.strip() for l in str(texto or "").splitlines()]
    campos, atual, antes, rotulos = {}, None, [], 0
    for linha in linhas:
        if not linha:
            continue
        campo = _rotulo(linha)
        if campo:
            rotulos += 1
            atual = campo
            campos.setdefault(campo, [])
            continue
        if atual is None:
            if _sem_acento(linha).lower().strip(" :") not in _ROTULOS_DA_PAGINA:
                antes.append(linha)
        else:
            campos[atual].append(linha)
    if rotulos < 2:
        return None
    ficha = {c: (" ".join(v).strip() or None) for c, v in campos.items()}
    if not ficha.get("nome"):
        ficha["nome"] = " ".join(antes).strip() or None
    for c in CAMPOS:
        ficha.setdefault(c, None)
    return ficha


def _titulo_de_secao(textos):
    """A página é a abertura de uma seção: um texto só, curto e em maiúsculas."""
    uteis = [t for t in textos if _sem_acento(t).lower().strip(" :") not in _ROTULOS_DA_PAGINA]
    if len(uteis) != 1:
        return None
    t = re.sub(r"\s+", " ", uteis[0]).strip()
    if 0 < len(t) <= _LIMITE_SECAO and re.search(r"[A-Za-z]", t) and t == t.upper():
        return t
    return None


def ler_documento(conteudo, design_id="", link=""):
    """
    O caderno inteiro: {'titulo', 'design_id', 'link', 'paginas', 'fichas'}.

    Cada ficha: pagina, secao, nome, medidas, medidas_sangria, sangria,
    material, quantidade, obs, acabamento, links (os HIPERLINKS da página,
    em ordem) e links_escritos (o endereço que aparece escrito, só pra
    conferência — ver o topo do módulo).
    """
    fichas = []
    secao = ""
    paginas = [p for p in conteudo.get("A") or [] if isinstance(p, dict)]
    for numero, pagina in enumerate(paginas, start=1):
        elementos = sorted((e for e in _elementos(pagina) if _texto(e).strip()), key=_posicao)
        textos = [_texto(e).strip() for e in elementos]
        blocos = [(e, f) for e, f in ((e, ficha_do_texto(_texto(e))) for e in elementos) if f]
        if not blocos and textos:
            # rótulo e valor em caixas separadas: a página inteira é a ficha
            ficha = ficha_do_texto("\n".join(textos))
            blocos = [(None, ficha)] if ficha else []
        if not blocos:
            titulo = _titulo_de_secao(textos)
            if titulo:
                secao = titulo
            continue

        # Cada link vai pra ficha mais perto dele — página com duas peças não
        # pode perder uma, nem trocar o link de uma pela outra.
        achados = [{"links": [], "escritos": []} for _ in blocos]
        for e in elementos:
            links, escritos = _hiperlinks(e), re.findall(r"https?://\S+", _texto(e))
            if not (links or escritos):
                continue
            if len(blocos) == 1 or blocos[0][0] is None:
                alvo = 0
            else:
                cy, cx = _centro(e)
                alvo = min(range(len(blocos)), key=lambda i: (
                    (_centro(blocos[i][0])[0] - cy) ** 2 + (_centro(blocos[i][0])[1] - cx) ** 2))
            achados[alvo]["links"].extend(links)
            achados[alvo]["escritos"].extend(escritos)
        for i, ((_, ficha), achado) in enumerate(zip(blocos, achados), start=1):
            ficha.update({"pagina": numero, "secao": secao, "links": list(dict.fromkeys(achado["links"])),
                          "links_escritos": list(dict.fromkeys(achado["escritos"])), "situacao": None,
                          "na_pagina": i if len(blocos) > 1 else None})
            fichas.append(ficha)

    # Sem hiperlink, vale o endereço escrito — MENOS o do modelo: o mesmo
    # endereço escrito em várias fichas que têm, cada uma, outro hiperlink.
    # Na LOJINHA ele aponta um JPG de outro trabalho; usar ele numa ficha sem
    # hiperlink baixaria a arte errada sem ninguém perceber.
    contagem = {}
    for f in fichas:
        for url in f["links_escritos"]:
            contagem[url] = contagem.get(url, 0) + 1
    do_modelo = {url for url, n in contagem.items() if n > 1 and any(
        f["links"] and url not in f["links"] for f in fichas if url in f["links_escritos"])}
    for f in fichas:
        f["link_do_modelo"] = any(url in do_modelo for url in f["links_escritos"])
        if not f["links"]:
            f["links"] = [url for url in f["links_escritos"] if url not in do_modelo]
    return {"titulo": conteudo.get("D") or "", "design_id": design_id, "link": link,
            "paginas": len(paginas), "fichas": fichas}


def ler(link, sessao=None):
    """
    Do link do Canva até as fichas — ver ler_documento. Vem junto
    'enderecos_das_paginas', a imagem de cada página (ver
    enderecos_das_paginas): endereço que vence em horas, pra baixar já e
    nunca guardar.
    """
    design, html = baixar_pagina(link, sessao)
    dados = _bootstrap(html)
    caderno = ler_documento(documento_da_pagina(html, dados), design_id=design, link=link)
    caderno["enderecos_das_paginas"] = enderecos_das_paginas(dados)
    caderno["versao"] = versao_do_rascunho(dados)
    return caderno


def versao_do_rascunho(dados):
    """
    O número de revisão do design ('version' do rascunho; 274 no caderno da
    LOJINHA em 02/10). O Canva não dá ETag nem Last-Modified — este é o
    carimbo que diz, de uma leitura pra outra, se o cliente mexeu em alguma
    coisa. None quando não vier.
    """
    try:
        versao = dados["page"]["Pm"]["E"]["draft"]["version"]
    except (KeyError, TypeError):
        return None
    return versao if isinstance(versao, int) else None


# ----------------------------------------------------------------------
# A página do caderno em imagem
# ----------------------------------------------------------------------
#
# "Os arquivos abrem, porém a parte onde está localizado no caderno continua
# travada" (02/10/2026): o visualizador do Canva não termina de abrir um
# caderno de 68 páginas — nem no Chrome dele, nem num Chrome sem tela, que
# derrubou a aba. Quem diz ONDE a peça fica na loja é a página do caderno (a
# planta e o 3D com a peça marcada em vermelho), então ela passa a viajar
# como imagem, guardada no recebimento e anexada ao relatório.
#
# Sondado no caderno da LOJINHA: a página de visualização traz, em
# draft.imageSets.thumbnail.images, uma imagem de CADA página (596 x 335 px,
# a mesma que o Canva mostra nas miniaturas), com endereço assinado que vence
# em cerca de duas horas. Pedir outro tamanho no endereço dá HTTP 403 (a
# assinatura cobre o tamanho), e o 'preview' de 1024 px só existe da página 1.

def _imagens_de(conjunto):
    imagens = conjunto.get("images") if isinstance(conjunto, dict) else None
    saida = {}
    for item in imagens if isinstance(imagens, list) else ():
        if (isinstance(item, dict) and isinstance(item.get("page"), int)
                and str(item.get("url") or "").startswith("http")):
            saida.setdefault(item["page"], item["url"])
    return saida


def _procurar_miniaturas(no, profundidade=0):
    """Plano B, se o caminho mudar: o primeiro 'thumbnail' com imagem por página."""
    if profundidade > 12 or not isinstance(no, (dict, list)):
        return {}
    if isinstance(no, dict) and _imagens_de(no.get("thumbnail")):
        return _imagens_de(no["thumbnail"])
    for filho in (no.values() if isinstance(no, dict) else no):
        achado = _procurar_miniaturas(filho, profundidade + 1)
        if achado:
            return achado
    return {}


def enderecos_das_paginas(dados):
    """
    {número da página: endereço da imagem dela}, do JSON da página de
    visualização. {} quando o Canva não mandou — a imagem é conforto, e a
    falta dela nunca impede a leitura do caderno.
    """
    try:
        conjunto = dados["page"]["Pm"]["E"]["draft"]["imageSets"]["thumbnail"]
    except (KeyError, TypeError):
        conjunto = None
    return _imagens_de(conjunto) or _procurar_miniaturas(dados)


def _e_imagem(dados):
    return bool(dados) and (dados[:8] == b"\x89PNG\r\n\x1a\n" or dados[:3] == b"\xff\xd8\xff")


def baixar_paginas(enderecos, numeros=None, sessao=None, trabalhadores=8):
    """
    {número: bytes da imagem} das páginas pedidas ('numeros'; todas quando
    None). Página que não vem — endereço vencido, rede caída, resposta que
    não é imagem — simplesmente fica de fora.
    """
    import concurrent.futures
    sessao = sessao or _sessao_padrao()
    quais = None if numeros is None else set(numeros)
    pedidas = sorted(n for n in (enderecos or {}) if quais is None or n in quais)

    def uma(numero):
        try:
            r = sessao.get(enderecos[numero], timeout=40)
        except Exception:   # noqa: BLE001 — sem a página não é erro
            return numero, None
        dados = r.content if r.status_code == 200 else None
        return numero, dados if _e_imagem(dados) else None

    if not pedidas:
        return {}
    with concurrent.futures.ThreadPoolExecutor(max(1, min(trabalhadores, len(pedidas)))) as ex:
        return {n: d for n, d in ex.map(uma, pedidas) if d}


# Onde as imagens moram, ao lado do caderno.json do recebimento:
# paginas/0008.png é a página 8.
PASTA_DAS_PAGINAS = "paginas"


def nome_da_imagem(numero, dados=b""):
    return "%04d.%s" % (numero, "jpg" if dados[:3] == b"\xff\xd8\xff" else "png")


def imagens_guardadas(pasta):
    """{número: caminho} das páginas guardadas em <pasta>/paginas/."""
    saida = {}
    try:
        candidatos = sorted((pathlib.Path(pasta) / PASTA_DAS_PAGINAS).glob("*"))
    except OSError:
        return {}
    for caminho in candidatos:
        if caminho.is_file() and caminho.stem.isdigit() and caminho.suffix.lower() in (".png", ".jpg"):
            saida.setdefault(int(caminho.stem), caminho)
    return saida


_CAMPOS_QUE_CONFEREM = ("nome", "medidas", "medidas_sangria", "sangria", "material", "quantidade")


def _fichas_por_pagina(caderno):
    paginas = {}
    for f in (caderno or {}).get("fichas") or []:
        paginas.setdefault(f.get("pagina"), []).append(
            tuple(f.get(c) for c in _CAMPOS_QUE_CONFEREM) + (tuple(f.get("links") or ()),))
    return paginas


def paginas_que_conferem(guardado, novo):
    """
    As páginas em que o caderno de HOJE ('novo') ainda diz exatamente o que
    dizia no recebimento ('guardado'): as mesmas fichas, com os mesmos
    campos e links. Só a imagem dessas pode ilustrar um recebimento antigo —
    o cliente edita o Canva quando quer, e uma página nova no meio empurra a
    numeração de todas as seguintes.
    """
    antes, agora = _fichas_por_pagina(guardado), _fichas_por_pagina(novo)
    return {n for n, fichas in antes.items() if n is not None and agora.get(n) == fichas}
