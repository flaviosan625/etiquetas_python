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
import hashlib
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

# Carimbo identificado pelo CONTEÚDO da imagem, nunca pelo nome do
# arquivo. A numeração de 'ppt/media' é por apresentação: num caderno o
# APROVADO é 'image4.png' e no seguinte é 'image3.png' — que lá é o
# REPROVADO. Identificar por nome fez um caderno inteiro de 154 peças
# sair como reprovado (2026-09-11), com o sinal exatamente invertido.
#
# Os arquivos são byte a byte iguais entre cadernos (é o mesmo desenho
# colado por quem monta), então o hash é chave estável. Cada rótulo foi
# conferido abrindo a imagem e lendo o que está escrito nela.
CARIMBOS_POR_CONTEUDO = {
    "d8526c205cbf8b983a082104c3cb8b552203feb258675a3aadffffa1ac8d6ddb":
        "APROVADO",
    "69c29d1179daae87971292e4f90d8482a4e4d2e8831571359c1d1879ca8dee9d":
        "EM APROVACAO",
    "96dd93ac4e091665a9ca363178ff6fb3c2ece1982a4cd3862fa0342fccc7fc88":
        "REPROVADO",
    "6d11db18b0874985e52a3e1343a223f873eda4f87c297682e67c56480ba0663b":
        "EM CRIACAO",
    "89220e36e20c82b66382b6ebd7a162840ad263ef22531fc03c757d9863cede07":
        "CRIACAO CONFERIDO",
    "43f499e8d82ccf003862c8a54c6635108c43d05466fc54fd2e2c675227140eba":
        "ARQUITETURA CONFERIDO",
    "9810866343bebde306e69d91c6c548b7f60ecc739ba8571db7e34be3839c8059":
        "PRODUCAO CONFERIDO",
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


def _carimbo_da_imagem(z, nome_midia, cache):
    """Que carimbo é esta imagem, pelo conteúdo. None se não for carimbo."""
    if nome_midia in cache:
        return cache[nome_midia]
    try:
        digito = hashlib.sha256(z.read("ppt/media/" + nome_midia)).hexdigest()
    except KeyError:
        digito = None
    cache[nome_midia] = CARIMBOS_POR_CONTEUDO.get(digito)
    return cache[nome_midia]


def _carimbos_aplicados(z, xml, mapa, altura, cache):
    aplicados = []
    for pic in re.findall(r"<p:pic>.*?</p:pic>", xml, re.S):
        rid = re.search(r'r:embed="([^"]+)"', pic)
        off = re.search(r'<a:off x="(-?\d+)" y="(-?\d+)"', pic)
        if not (rid and off):
            continue
        nome_midia = mapa.get(rid.group(1))
        if not nome_midia:
            continue
        marca = _carimbo_da_imagem(z, nome_midia, cache)
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
        cache_carimbos = {}
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
            ficha["carimbos"] = _carimbos_aplicados(z, xml, mapa, altura, cache_carimbos)
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


# Material que o cliente ainda não definiu na ficha. Regra do usuário
# (2026-09-12): quando a peça está APROVADA e tem link, "aguardando
# imagens 3D" é sobre o render de arquitetura do slide, não sobre a arte
# — a arte já existe na pasta e deve ser baixada. Fica "A DEFINIR" no
# nome, sinalizando que o material real ainda precisa ser confirmado
# antes de mandar pra máquina.
MATERIAL_A_DEFINIR = "A DEFINIR"


def _material_aguardando(texto):
    """True quando o campo MATERIAL é o placeholder de espera do cliente."""
    t = _sem_acento(texto).upper()
    return "AGUARDANDO" in t and "3D" in t


def categoria_do_material(texto_material, config=None):
    """
    A categoria que vai no nome, tirada SEMPRE do campo MATERIAL da ficha
    — nunca da descrição da peça. Regra do usuário (2026-09-11):
    "respeite sempre o que for material que o cliente pede".

    XPS decide antes de tudo ("tudo que for XPS pode considerar PVC",
    mesma data). Sem isso, num "LOGO XPS RECORTE COM ADESIVO IMPRESSO" o
    desempate por nome mais longo daria ADESIVO (7 letras) em vez de PVC
    (3) — e a peça iria pra máquina errada.

    Material que o cliente deixou como "aguardando 3D" vira A DEFINIR:
    a arte é baixável (aprovada, com link), o material real fica pra
    confirmar.
    """
    config = config or carregar_config()
    texto = _sem_acento(texto_material).upper()
    if re.search(r"\bXPS\b", texto) or re.search(r"\bPVC\b", texto):
        return "PVC"
    if _material_aguardando(texto_material):
        return MATERIAL_A_DEFINIR
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


def _medida_metros_para_nome(medida_m):
    """(6.0, 3.0) -> '6,00X3,00M'. É a medida MEDIDA na arte, não do nome."""
    if not medida_m:
        return None
    return "%sX%sM" % (("%.2f" % medida_m[0]).replace(".", ","),
                       ("%.2f" % medida_m[1]).replace(".", ","))


def nome_no_padrao(ficha, config=None, medida_arte=None):
    """
    Nome do arquivo no padrão da casa, a partir da ficha:

        <QTD>UN <CATEGORIA> <LARGURA>X<ALTURA>M_<DESCRIÇÃO>_sangria <LxA>

    A medida REAL vem primeiro e a de sangria depois — encaixa na regra
    que já existe no projeto ("duas medidas no nome, vale a primeira"),
    então a sangria fica registrada sem entrar em conta nenhuma.

    'medida_arte' é (largura_m, altura_m) medida no PDF. Só entra quando
    o caderno NÃO deu a medida no formato largura x altura (o cliente
    preencheu só um número) — aí a medida real da arte completa o nome,
    em vez de a peça ficar de fora. Sem ela, não se inventa medida.

    Devolve (nome, None) ou (None, motivo).
    """
    config = config or carregar_config()

    medida = medida_para_nome(ficha.get("medidas")) or _medida_metros_para_nome(medida_arte)
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
