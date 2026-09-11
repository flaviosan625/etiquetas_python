"""
Processa uma arte que já foi baixada da pasta do cliente: identifica qual
peça do caderno ela é, confere, tira a marca de corte, renomeia no nosso
padrão e registra o download na planilha de controle.

Por que existe (2026-09-11): enquanto a API do Drive não entra, o download
da pasta é manual — o Flávio pega o PDF e larga em '_entrada'. Deste ponto
em diante tudo é automático, e é este ponto em diante que este módulo faz.
Quando a API entrar, ela só substitui o "larga em _entrada": o resto aqui
não muda.

A IDENTIFICAÇÃO é pela MEDIDA da arte, conferida contra o caderno. O nome
que o cliente dá ao arquivo não é confiável (vem digitado, às vezes com a
medida diferente da declarada), então a chave é o tamanho real do desenho.
Havendo mais de uma peça do mesmo tamanho, o nome do arquivo desempata; se
ainda assim ficar ambíguo, NÃO adivinha — devolve as candidatas pra decidir.

SOMENTE PDF. Da pasta do cliente vem mockup, JPG de prévia e .ai de
trabalho; aqui só entra .pdf (regra do usuário, 2026-09-11: "somente o PDF,
não trazer junto nada além desse material").
"""
import datetime
import json
import pathlib
import re
import unicodedata

import caderno_arte
import marcas_de_corte

NOME_ESTADO = "_baixados.json"
NOME_ENTRADA = "_entrada"
NOME_ARTES = "ARTES"

# Quanto a medida da arte pode diferir da declarada no caderno e ainda ser
# a mesma peça. 3 cm: sangria, arredondamento de quem digitou o caderno e
# folga de recorte cabem aqui; peça de outro tamanho, não.
_TOLERANCIA_M = 0.03


def _sem_acento(texto):
    t = unicodedata.normalize("NFKD", str(texto or ""))
    return "".join(c for c in t if not unicodedata.combining(c)).upper()


def _medida_da_ficha(ficha):
    m = re.match(r"^\s*([\d.,]+)\s*[Xx]\s*([\d.,]+)", str(ficha.get("medidas") or ""))
    if not m:
        return None
    return (float(m.group(1).replace(",", ".")), float(m.group(2).replace(",", ".")))


def medir_arte(caminho_pdf):
    """
    Tamanho REAL da arte, em metros (largura, altura).

    Quando o PDF traz marca de corte, a arte é o TrimBox — nunca a página,
    que inclui a moldura. Respeita /UserUnit (arte grande vem em décimos).
    Devolve None se não der pra medir.
    """
    dados = marcas_de_corte.medidas(caminho_pdf)
    if not dados:
        return None
    mp = 0.0254 / 72
    corte = dados.get("TrimBox_pt") or dados.get("MediaBox_pt")
    if not corte:
        return None
    return (corte[0] * mp, corte[1] * mp)


def _casa_medida(medida_arte, medida_ficha):
    if not medida_arte or not medida_ficha:
        return False
    # aceita a peça girada (LxA ou AxL): o cliente às vezes deita a arte
    direto = (abs(medida_arte[0] - medida_ficha[0]) <= _TOLERANCIA_M
              and abs(medida_arte[1] - medida_ficha[1]) <= _TOLERANCIA_M)
    girado = (abs(medida_arte[0] - medida_ficha[1]) <= _TOLERANCIA_M
              and abs(medida_arte[1] - medida_ficha[0]) <= _TOLERANCIA_M)
    return direto or girado


def identificar(caminho_pdf, fichas, so_aprovadas=True):
    """
    Qual peça do caderno é este PDF. Devolve (ficha, candidatas):

      - (ficha, [ficha])        => uma só peça casou; é ela.
      - (None, [f1, f2, ...])   => várias do mesmo tamanho; decidir.
      - (None, [])              => nenhuma peça com essa medida.

    Só considera peças aprovadas por padrão — é o que se baixa.
    """
    alvo = medir_arte(caminho_pdf)
    if alvo is None:
        return None, []

    candidatos = [f for f in fichas
                  if (not so_aprovadas or f.get("situacao") == "APROVADO")
                  and _casa_medida(alvo, _medida_da_ficha(f))]
    if len(candidatos) <= 1:
        return (candidatos[0] if candidatos else None), candidatos

    # Empate de medida: o nome do arquivo baixado desempata pelo texto.
    nome = _sem_acento(pathlib.Path(caminho_pdf).stem)
    def afins(f):
        palavras = {p for p in _sem_acento(f.get("nome")).split() if len(p) > 2}
        return sum(1 for p in palavras if p in nome)
    ranque = sorted(candidatos, key=afins, reverse=True)
    if afins(ranque[0]) > afins(ranque[1]):
        return ranque[0], candidatos
    return None, candidatos


def _chave_peca(caderno, ficha):
    return "%s|slide|%s" % (caderno, ficha.get("slide"))


def ler_baixados(pasta):
    caminho = pathlib.Path(pasta) / NOME_ESTADO
    if not caminho.is_file():
        return {}
    try:
        return json.loads(caminho.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _gravar_baixados(pasta, estado):
    caminho = pathlib.Path(pasta) / NOME_ESTADO
    caminho.write_text(json.dumps(estado, ensure_ascii=False, indent=2), encoding="utf-8")


def processar_pdf(caminho_pdf, caminho_caderno, pasta, quando=None, logger=None,
                  remover_marcas=True):
    """
    Uma arte, de ponta a ponta:

      1. identifica a peça pela medida (contra o caderno)
      2. tira a marca de corte, se houver, sem tocar na arte
      3. renomeia no nosso padrão
      4. move pra ARTES/
      5. registra em _baixados.json (peça, arquivo, quando, medida conferida)

    Devolve (ok, mensagem, detalhe). Não move nada quando a peça não é
    identificada com segurança — devolve as candidatas em 'detalhe'.
    """
    def aviso(nivel, texto):
        if logger:
            logger(nivel, texto)

    quando = quando or datetime.datetime.now()
    caminho_pdf = pathlib.Path(caminho_pdf)
    pasta = pathlib.Path(pasta)
    if caminho_pdf.suffix.lower() != ".pdf":
        return False, "só processo PDF; '%s' não é." % caminho_pdf.name, None

    fichas = caderno_arte.fichas_com_nome(caminho_caderno)
    ficha, candidatas = identificar(caminho_pdf, fichas)
    if ficha is None:
        if not candidatas:
            return False, ("não achei no caderno nenhuma peça aprovada do tamanho de '%s'. "
                           "Confira se é a arte certa, ou se a peça já foi aprovada."
                           % caminho_pdf.name), []
        nomes = ", ".join("slide %s (%s)" % (c["slide"], c["nome"]) for c in candidatas)
        return False, ("'%s' casa com mais de uma peça do mesmo tamanho: %s. "
                       "Me diga qual é." % (caminho_pdf.name, nomes)), candidatas

    if not ficha.get("nome_arquivo"):
        return False, ("achei a peça (slide %s, %s), mas o caderno não dá um nome utilizável: %s. "
                       "A arte fica em '_entrada' até o caderno ser corrigido."
                       % (ficha["slide"], ficha["nome"], ficha.get("motivo_nome"))), ficha

    destino = pasta / NOME_ARTES / (ficha["nome_arquivo"] + ".pdf")
    destino.parent.mkdir(parents=True, exist_ok=True)

    # move pra ARTES antes de mexer: a partir daqui trabalhamos na cópia
    # de trabalho, e o que estava em _entrada sai de cena.
    import shutil
    shutil.move(str(caminho_pdf), str(destino))

    marca_removida = False
    if remover_marcas:
        dados = marcas_de_corte.medidas(destino)
        tem_moldura = dados and dados.get("MediaBox_pt") and dados.get("TrimBox_pt") \
            and dados["MediaBox_pt"] != dados["TrimBox_pt"]
        if tem_moldura:
            trocou, msg = marcas_de_corte.remover_marcas_de_corte(destino, logger=logger)
            marca_removida = trocou
            if not trocou:
                aviso("warn", "A arte foi salva, mas não removi a marca de corte: %s" % msg)

    conferida = medir_arte(destino)
    estado = ler_baixados(pasta)
    caderno = pathlib.Path(caminho_caderno).stem
    estado[_chave_peca(caderno, ficha)] = {
        "peca": ficha["nome"],
        "slide": ficha["slide"],
        "arquivo": destino.name,
        "quando": quando.strftime("%Y-%m-%dT%H:%M:%S"),
        "medida_conferida_m": [round(conferida[0], 3), round(conferida[1], 3)] if conferida else None,
        "marca_removida": marca_removida,
    }
    _gravar_baixados(pasta, estado)

    mp_txt = ""
    if conferida:
        mp_txt = " · arte %.2f x %.2f m" % conferida
    return True, ("'%s' identificada como slide %s (%s), salva como '%s'%s%s."
                  % (caminho_pdf.name, ficha["slide"], ficha["nome"], destino.name,
                     mp_txt, " · marca de corte removida" if marca_removida else "")), ficha
