"""
Leitura do "caderno de arte" que o cliente monta no Google Slides: uma
peça por slide, com a ficha completa e o link da pasta de onde baixar.

Por que existe (2026-09-11): hoje quantidade, material e medida saem do
NOME do arquivo, digitado à mão — foi assim que uma lona de 5,65 x 1,80m
escrita como "cm" virou 0,00 m² no relatório. O caderno traz esses mesmos
dados ESTRUTURADOS e conferidos pelo cliente. Lendo daqui, o resto do
sistema (etiqueta, OS, checklist, escolha de máquina, m² do relatório)
passa a trabalhar com dado certo por construção, sem mudar nada nele: só
o nome do arquivo passa a nascer correto.

O arquivo lido é o .pptx exportado da apresentação. Um .pptx é um zip de
XML, então isto não depende de python-pptx nem de nada instalado.

O QUE CADA SLIDE TRAZ
  NOME DO ARQUIVO / MATERIAL / MEDIDAS / MEDIDAS COM SANGRIA / QTDD / OBS
  o link azul do rodapé, que aponta a pasta da arte no Drive
  os carimbos de aprovação

COMO O STATUS É LIDO (descoberto sondando o arquivo, 2026-09-11)
Os 7 carimbos existem em TODOS os slides, mas a fileira do rodapé fica
FORA da área do slide (y > 100%) — é a paleta de onde o designer arrasta.
Vale só o carimbo posicionado DENTRO. O próprio usuário confirmou:
"o ideal é olhar para os que ficam dentro da imagem; aqueles do rodapé
eles deixam como exemplo".
"""
import pathlib
import re
import unicodedata
import zipfile

from config import carregar_config
from dimensoes import identificar_categoria
from utils import sanitizar_nome_arquivo

# Rótulo da tabela -> campo da ficha. O valor é o próximo texto do slide
# que não seja outro rótulo; é assim que a tabela foi montada.
_ROTULOS = {
    "NOME DO ARQUIVO": "nome",
    "MATERIAL": "material",
    "MEDIDAS:": "medidas",
    "MEDIDAS COM SANGRIA:": "medidas_sangria",
    "QTDD": "quantidade",
    "OBS:": "obs",
}

# Nome do arquivo de imagem -> o que aquele carimbo quer dizer. Os nomes
# vêm do próprio .pptx e foram conferidos abrindo cada imagem.
CARIMBOS = {
    "image4.png": "APROVADO",
    "image8.png": "EM APROVACAO",
    "image3.png": "REPROVADO",
    "image2.png": "EM CRIACAO",
    "image11.png": "CRIACAO CONFERIDO",
    "image1.png": "ARQUITETURA CONFERIDO",
    "image9.png": "PRODUCAO CONFERIDO",
}

# Carimbo colado abaixo disto (em % da altura) é paleta, não status.
_LIMITE_PALETA = 100.0

# Ordem de gravidade: o primeiro que aparecer decide a situação.
_PRIORIDADE = ("REPROVADO", "APROVADO", "EM APROVACAO")


def _sem_acento(texto):
    t = unicodedata.normalize("NFKD", str(texto or ""))
    return "".join(c for c in t if not unicodedata.combining(c))


def _numero_do_slide(caminho):
    return int(re.search(r"(\d+)", caminho.split("/")[-1]).group(1))


def _slides(z):
    return sorted(
        [n for n in z.namelist() if re.match(r"ppt/slides/slide\d+\.xml$", n)],
        key=_numero_do_slide,
    )


def _altura_do_slide(z):
    tag = re.search(r"<p:sldSz[^>]*>", z.read("ppt/presentation.xml").decode("utf-8"))
    return int(re.search(r'cy="(\d+)"', tag.group(0)).group(1))


def _midias_do_slide(z, arquivo):
    """rId -> nome do arquivo de imagem, pro slide dado."""
    rels = "ppt/slides/_rels/" + arquivo.split("/")[-1] + ".rels"
    try:
        texto = z.read(rels).decode("utf-8")
    except KeyError:
        return {}, []
    mapa = dict(re.findall(r'Id="([^"]+)"[^>]*Target="\.\./media/([^"]+)"', texto))
    links = []
    for m in re.finditer(r'Target="([^"]+)"[^>]*TargetMode="External"', texto):
        url = m.group(1).replace("&amp;", "&")
        if "drive.google.com" in url or "docs.google.com" in url:
            links.append(url)
    return mapa, sorted(set(links))


def _carimbos_aplicados(xml, mapa, altura):
    aplicados = []
    for pic in re.findall(r"<p:pic>.*?</p:pic>", xml, re.S):
        rid = re.search(r'r:embed="([^"]+)"', pic)
        off = re.search(r'<a:off x="(-?\d+)" y="(-?\d+)"', pic)
        if not (rid and off):
            continue
        marca = CARIMBOS.get(mapa.get(rid.group(1)))
        if marca and 100 * int(off.group(2)) / altura < _LIMITE_PALETA:
            aplicados.append(marca)
    return sorted(set(aplicados))


def situacao(marcas):
    """A situação da peça a partir dos carimbos colados no slide."""
    for prioritario in _PRIORIDADE:
        if prioritario in marcas:
            return prioritario
    return "EM CRIACAO" if marcas else "SEM CARIMBO"


def ler(caminho):
    """
    Todas as fichas do caderno, uma por slide, na ordem.

    Slide sem 'NOME DO ARQUIVO' (capa, índice, página de status) vem com
    'nome' None — quem chama decide ignorar. Não é erro.
    """
    with zipfile.ZipFile(str(caminho)) as z:
        altura = _altura_do_slide(z)
        fichas = []
        for arquivo in _slides(z):
            xml = z.read(arquivo).decode("utf-8")
            textos = [t.strip() for t in re.findall(r"<a:t>([^<]*)</a:t>", xml)]
            textos = [t for t in textos if t]

            ficha = {"slide": _numero_do_slide(arquivo)}
            for i, texto in enumerate(textos):
                campo = _ROTULOS.get(texto.upper())
                if campo and campo not in ficha:
                    for seguinte in textos[i + 1:]:
                        if seguinte.upper() not in _ROTULOS:
                            ficha[campo] = seguinte
                            break
            for campo in _ROTULOS.values():
                ficha.setdefault(campo, None)

            etiquetas = [t for t in textos if t.upper().startswith("AF")]
            ficha["etiqueta_link"] = etiquetas[0] if etiquetas else None

            mapa, links = _midias_do_slide(z, arquivo)
            ficha["links"] = links
            ficha["carimbos"] = _carimbos_aplicados(xml, mapa, altura)
            ficha["situacao"] = situacao(ficha["carimbos"])
            fichas.append(ficha)
    return fichas


def pecas(caminho):
    """Só os slides que são peça de verdade."""
    return [f for f in ler(caminho) if f.get("nome")]


# ----------------------------------------------------------------------
# Da ficha do cliente para o nome de arquivo do nosso dia a dia
# ----------------------------------------------------------------------

def medida_para_nome(medida):
    """'12,80 X 4,50' -> '12,80X4,50M'. None quando não for um par LxA."""
    m = re.match(r"^\s*([\d.,]+)\s*[Xx]\s*([\d.,]+)\s*M?\s*$", str(medida or ""))
    if not m:
        return None
    return "%sX%sM" % (m.group(1), m.group(2))


def categoria_do_material(texto_material, config=None):
    """
    A categoria que vai no nome, tirada SEMPRE do campo MATERIAL da ficha
    — nunca da descrição da peça. Regra do usuário (2026-09-11):
    "respeite sempre o que for material que o cliente pede".

    XPS decide antes de tudo ("tudo que for XPS pode considerar PVC",
    mesma data). Sem isso, num "LOGO XPS RECORTE COM ADESIVO IMPRESSO" o
    desempate por nome mais longo daria ADESIVO (7 letras) em vez de PVC
    (3) — e a peça iria pra máquina errada.
    """
    config = config or carregar_config()
    texto = _sem_acento(texto_material).upper()
    if re.search(r"\bXPS\b", texto) or re.search(r"\bPVC\b", texto):
        return "PVC"
    categoria, _ = identificar_categoria(
        texto, config["materiais"], config.get("sinonimos_categoria", {}))
    return categoria


def _descricao_limpa(descricao, config):
    """
    A descrição sem nenhuma palavra que seja categoria ou sinônimo.

    Sem isso o nome diria duas coisas: a peça do slide 14 do caderno da
    ASICS se CHAMA "ADESIVO" e é feita de LONA IMPRESSA, e o leitor
    ficaria com a errada.
    """
    palavras = set(config["materiais"]) | set(config.get("sinonimos_categoria", {}))
    palavras = {_sem_acento(p).upper() for p in palavras}
    sobra = [p for p in _sem_acento(descricao).upper().split()
             if p.strip(".,-;") not in palavras]
    return " ".join(sobra).strip(" -;,")


def nome_no_padrao(ficha, config=None):
    """
    Nome do arquivo no padrão da casa, a partir da ficha:

        <QTD>UN <CATEGORIA> <LARGURA>X<ALTURA>M_<DESCRIÇÃO>_sangria <LxA>

    A medida REAL vem primeiro e a de sangria depois — encaixa na regra
    que já existe no projeto ("duas medidas no nome, vale a primeira"),
    então a sangria fica registrada sem entrar em conta nenhuma.

    Devolve (nome, None) ou (None, motivo). Nunca inventa: medida que o
    cliente não preencheu no formato largura x altura vira motivo, não
    palpite — três peças do caderno real vieram com um número só.
    """
    config = config or carregar_config()

    medida = medida_para_nome(ficha.get("medidas"))
    if not medida:
        return None, "medida '%s' não está no formato largura x altura" % (ficha.get("medidas") or "",)

    categoria = categoria_do_material(ficha.get("material"), config)
    if not categoria:
        return None, "material '%s' não cai em nenhuma categoria cadastrada" % (ficha.get("material") or "",)

    descricao = _descricao_limpa(ficha.get("nome") or "", config)
    if not descricao:
        # Nome da peça é só uma palavra de material que contradiz o campo
        # MATERIAL. A etiqueta do link costuma ser mais descritiva.
        etiqueta = re.sub(r"^\s*AF\s*[-–]\s*", "", ficha.get("etiqueta_link") or "")
        descricao = _descricao_limpa(etiqueta, config) or "PECA SLIDE %s" % ficha.get("slide")

    quantidade = re.sub(r"\D", "", str(ficha.get("quantidade") or "1")) or "1"
    nome = "%dUN %s %s_%s" % (int(quantidade), categoria, medida, descricao)

    sangria = medida_para_nome(ficha.get("medidas_sangria"))
    if sangria:
        nome += "_sangria %s" % sangria
    return sanitizar_nome_arquivo(nome), None


def fichas_com_nome(caminho, config=None):
    """
    As peças do caderno, cada uma já com o nome que o arquivo deve ter
    aqui dentro ('nome_arquivo') ou o motivo de não dar ('motivo_nome').
    """
    config = config or carregar_config()
    fora = []
    for ficha in pecas(caminho):
        nome, motivo = nome_no_padrao(ficha, config)
        fora.append({**ficha, "nome_arquivo": nome, "motivo_nome": motivo})
    return fora


def caminho_valido(caminho):
    """True se o arquivo existe e é mesmo um .pptx (zip com slides)."""
    caminho = pathlib.Path(caminho)
    if not caminho.is_file():
        return False
    try:
        with zipfile.ZipFile(str(caminho)) as z:
            return bool(_slides(z))
    except (zipfile.BadZipFile, OSError):
        return False
