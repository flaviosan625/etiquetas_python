"""
Orquestra o recebimento das artes: baixa do Drive todas as peças
LIBERADAS, tira a marca de corte, renomeia no padrão da casa e registra —
tudo a partir do caderno de arte do cliente.

É a junção das peças que já existem, cada uma provada sozinha:
  caderno_arte  -> lê a ficha e o status de cada peça
  drive_artes   -> baixa SÓ o PDF da pasta do Drive
  arte_recebida -> tira a marca sem tocar na arte, renomeia, registra
  controle_artes-> a planilha que cruza com a planilha do cliente

REGRA DE QUEM ENTRA (pedido do usuário, 2026-09-11): "baixar todas as
liberadas". Liberada = carimbo APROVADO no caderno, com link de pasta e
com medida/material que dão um nome utilizável. Aprovada sem link, ou com
medida incompleta, NÃO entra — fica registrada na planilha pra conferir,
nunca baixada no escuro.

RETOMÁVEL: o que já baixou (em _baixados.json) é pulado. Se o lote parar
no meio — Illustrator travou, rede caiu — é só rodar de novo que ele
continua de onde estava, sem refazer o que já está pronto.

RESILIENTE: uma peça que falha não derruba o lote. O gargalo é o
Illustrator (uma arte por vez, ~30-60s cada), e ele já travou de vez uma
vez; por isso a remoção tem tempo-limite e a falha de uma peça só a
sinaliza, seguindo para a próxima.

SEM CADERNO (2026-09-21) — a segunda metade deste módulo
Muita arte chega só com o link (Drive, WeTransfer, ZIP, pasta). Quem lê a
origem é origem_artes; daqui pra baixo é o passo 2 da tela: da pasta de
espera até ARTES. Sem ficha, o que se sabe sai do próprio arquivo, com as
regras do usuário:
  - a MEDIDA vem sempre da arte ("tamanho da arte sempre mais confiável");
  - o que o nome do arquivo especificar (10UN, LONA...) vale;
  - o que ninguém especificou: 1 unidade e material A DEFINIR, sem
    perguntar ("1 unidade de cada quando não achar especificação";
    "pode jogar sempre como A Definir").

CADERNO NA TELA (2026-10-02) — o caderno do Canva
O arquivo chega com a ficha da peça junto (origem_artes.OrigemCaderno). A
ficha decide MATERIAL e QUANTIDADE ("respeite sempre o que for material que
o cliente pede"); a medida continua vindo da arte, e a do caderno serve pra
conferir — e pra provar escala: a lona grande vem desenhada em 1:10 (ver
escala_provada).
"""
import collections
import dataclasses
import datetime
import hashlib
import json
import pathlib
import re
import shutil

import arte_recebida
import caderno_arte
import caminhos
import drive_artes
from config import carregar_config


def pecas_liberadas(caminho_caderno, config=None):
    """
    As peças que entram no lote: aprovadas e com link de pasta.

    O nome utilizável NÃO é exigido aqui. Quando o caderno traz a medida
    pela metade — um número só, "0,80" — a peça ainda entra: o nome é
    completado na hora do processamento, medindo a arte baixada (regra do
    usuário, 2026-09-12: "aprovada com link deve baixar, mesmo com a ficha
    pela metade"; vale para as áreas 'aguardando 3D' também). Se nem a arte
    der um nome, aí sim ela fica em '_entrada', sinalizada, sem entrar em
    ARTES no escuro — quem decide isso é arte_recebida.processar_pdf.
    """
    fichas = caderno_arte.fichas_com_nome(caminho_caderno, config)
    return [f for f in fichas
            if f.get("situacao") == "APROVADO" and f.get("links")]


def baixar_lote(caminho_caderno, pasta, drive=None, limite=None, refazer=False,
                logger=print, config=None):
    """
    Baixa e processa as peças liberadas do caderno. Devolve um resumo
    {baixadas, puladas, falharam}. Nunca levanta por causa de uma peça —
    a falha dela vira uma linha em 'falharam'.

    'limite' baixa só as N primeiras que faltam (pra um primeiro teste).
    'refazer' ignora o que já foi baixado e baixa tudo de novo.
    """
    caminho_caderno = pathlib.Path(caminho_caderno)
    pasta = pathlib.Path(pasta)
    entrada = pasta / arte_recebida.NOME_ENTRADA
    entrada.mkdir(parents=True, exist_ok=True)
    caderno_nome = caminho_caderno.stem

    liberadas = pecas_liberadas(caminho_caderno, config)
    ja_baixadas = arte_recebida.ler_baixados(pasta)
    drive = drive or drive_artes.servico()

    resumo = {"baixadas": [], "puladas": [], "falharam": []}
    feitas = 0
    for ficha in liberadas:
        chave = arte_recebida._chave_peca(caderno_nome, ficha)
        if not refazer and chave in ja_baixadas:
            resumo["puladas"].append(ficha["nome"])
            continue
        if limite is not None and feitas >= limite:
            break
        feitas += 1

        rotulo = "slide %s (%s)" % (ficha["slide"], ficha["nome"])
        try:
            caminho, msg = drive_artes.baixar_arte_para_entrada(ficha, entrada, drive)
        except Exception as e:
            resumo["falharam"].append((ficha["nome"], "erro ao baixar: %s" % e))
            logger("warn", "%s — erro ao baixar: %s" % (rotulo, e))
            continue
        if caminho is None:
            resumo["falharam"].append((ficha["nome"], msg))
            logger("warn", "%s — %s" % (rotulo, msg))
            continue

        try:
            ok, msg2, _ = arte_recebida.processar_pdf(caminho, caminho_caderno, pasta,
                                                      logger=logger, ficha=ficha)
        except Exception as e:
            resumo["falharam"].append((ficha["nome"], "erro ao processar: %s" % e))
            logger("warn", "%s — erro ao processar: %s" % (rotulo, e))
            continue
        if ok:
            resumo["baixadas"].append(ficha["nome"])
            logger("ok", msg2)
        else:
            resumo["falharam"].append((ficha["nome"], msg2))
            logger("warn", msg2)

    return resumo


# ======================================================================
# SEM CADERNO: da pasta de espera até ARTES
# ======================================================================

MP = 0.0254 / 72
# Duas páginas com diferença maior que isto são peças de tamanhos diferentes.
_TOLERANCIA_PAGINA_M = 0.002
# Sangria menor que isto é arredondamento de exportação, não sangria.
_SANGRIA_MINIMA_M = 0.001

_MEDIDA_NO_TEXTO = re.compile(
    r"\d+(?:[.,]\d+)?\s*[X×]\s*\d+(?:[.,]\d+)?\s*(?:MM|CM|M)?(?![A-Z])", re.I)
_QUANTIDADE_NO_TEXTO = re.compile(r"\b\d+\s*(?:UN|UND|UNIDADES?)\b", re.I)
_AVISO_AI_SEM_PDF = "saved without pdf content"


class ErroRecebimento(Exception):
    """Mensagem pronta pra tela."""


@dataclasses.dataclass
class Peca:
    """Uma linha do passo 2: o que vai virar UM arquivo em ARTES."""
    arquivo: object              # origem_artes.Arquivo de onde veio
    local: pathlib.Path          # o baixado, na pasta de espera
    chave: str                   # de onde veio, pro registro
    papel: str                   # arte | trabalho | previa | outro
    descricao: str = ""
    material: str = caderno_arte.MATERIAL_A_DEFINIR
    quantidade: int = 1
    pagina: int = None           # 1..N quando o PDF traz peças diferentes por página
    paginas: int = 1
    arte_m: tuple = None         # (largura, altura) — da arte, sempre que der
    sangria_m: tuple = None
    marca: str = ""              # tem | nao tem | nao sei | a verificar
    medida_no_nome: tuple = None
    de_onde: dict = dataclasses.field(default_factory=dict)
    avisos: list = dataclasses.field(default_factory=list)
    copia: int = 1               # a mesma arte servindo mais de uma peça
    corte_px: tuple = None       # imagem: o retângulo que FICA, aprovado por ele (x0, y0, x1, y1)
    marca_removida: bool = False
    # imagem: o que marcas_de_corte.propor_corte_imagem achou (pra tela mostrar)
    proposta_corte: dict = dataclasses.field(default=None, repr=False, compare=False)
    # caderno: a ficha da peça (página, nome, medidas, material, quantidade...)
    ficha: dict = dataclasses.field(default=None, repr=False, compare=False)
    # arte desenhada em escala (1:10): 'escala' é o fator em uso, 'escala_achada'
    # o que a prova achou (a tela liga e desliga), e a medida como está no PDF
    escala: int = 1
    escala_achada: int = 1
    arte_pdf_m: tuple = None
    sangria_pdf_m: tuple = None

    @property
    def leva_nome_do_padrao(self):
        """Arte com medida ganha o nome da casa; o resto fica com o nome do cliente."""
        return self.papel == "arte" and self.arte_m is not None

    @property
    def material_definido(self):
        return self.material != caderno_arte.MATERIAL_A_DEFINIR


# ------------------------------------------------------------- medir

def _medir_pdf(caminho):
    """Uma entrada por página: (arte_m, sangria_m, marca). None se não abrir."""
    import marcas_de_corte
    import pymupdf
    try:
        doc = pymupdf.open(str(caminho))
    except Exception:
        return None
    try:
        if _AVISO_AI_SEM_PDF in " ".join(doc[0].get_text().split()).lower():
            return []   # .ai salvo sem PDF: só o Illustrator sabe o tamanho
        paginas = []
        for i in range(doc.page_count):
            d = marcas_de_corte.medidas_da_pagina(doc, i)
            corte = d.get("TrimBox_pt") or d.get("MediaBox_pt")
            sang = d.get("BleedBox_pt") or d.get("MediaBox_pt")
            paginas.append((
                (corte[0] * MP, corte[1] * MP) if corte else None,
                (sang[0] * MP, sang[1] * MP) if sang else None,
                "tem" if marcas_de_corte.tem_marca_de_corte(d) else "nao tem"))
        return paginas
    finally:
        doc.close()


def _medir_imagem(caminho):
    """(arte_m, None) pelo tamanho em pixel e a resolução gravada; só lê o cabeçalho."""
    from PIL import Image
    try:
        with Image.open(str(caminho)) as img:
            dpi = img.info.get("dpi")
            largura, altura = img.size
    except Exception:
        return None
    if not dpi or not dpi[0] or float(dpi[0]) < 10:
        return None
    dx, dy = float(dpi[0]), float(dpi[1] or dpi[0])
    return (largura / dx * 0.0254, altura / dy * 0.0254)


def _medir_eps(caminho):
    """Pelo %%HiResBoundingBox (ou %%BoundingBox) do cabeçalho."""
    try:
        with open(caminho, "rb") as f:
            cabeca = f.read(65536).decode("latin-1", "replace")
    except OSError:
        return None
    for rotulo in ("%%HiResBoundingBox:", "%%BoundingBox:"):
        m = re.search(re.escape(rotulo) + r"\s*([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)", cabeca)
        if m:
            x0, y0, x1, y1 = map(float, m.groups())
            return ((x1 - x0) * MP, (y1 - y0) * MP)
    return None


def _medir_imagem_com_marca(caminho, medida_da_imagem, peca):
    """
    (arte_m, sangria_m, marca) de uma imagem, procurando a marca de corte.

    Numa imagem com marca, o tamanho pelo DPI é o da imagem INTEIRA, com
    a moldura — a arte é a distância entre as marcas. Por isso a detecção
    roda já aqui, e não só quando ele abrir o 'ver corte'. Imagem grande
    demais pro Pillow fica 'a verificar': o Photoshop só é chamado na tela
    de corte, pra este passo não travar.
    """
    import marcas_de_corte
    from PIL import Image
    try:
        with Image.open(str(caminho)) as img:
            pixels = img.width * img.height
    except Exception:
        return medida_da_imagem, medida_da_imagem, "nao sei"
    if pixels > marcas_de_corte.LIMITE_DETECCAO_PIXELS:
        peca.avisos.append("imagem grande: a marca de corte é procurada quando você abrir 'ver corte'")
        return medida_da_imagem, medida_da_imagem, "a verificar"

    proposta = marcas_de_corte.propor_corte_imagem(caminho)
    peca.proposta_corte = proposta
    if proposta.get("corte_px") is None:
        # nenhuma marca batendo nas margens opostas: imagem limpa
        return medida_da_imagem, medida_da_imagem, "nao tem"
    arte, sangria = marcas_de_corte.medidas_da_proposta(proposta)
    if proposta["ok"]:
        peca.avisos.append("marca de corte encontrada: a arte mede %s entre as marcas — confira em "
                           "'ver corte' e aprove" % formatar_medida(arte))
    else:
        peca.avisos.append(proposta["motivo"])
    return arte or medida_da_imagem, sangria or medida_da_imagem, "tem"


def _medida_do_nome(nome):
    from dimensoes import extrair_dimensoes
    try:
        d = extrair_dimensoes(nome)
    except Exception:
        return None
    return (d["largura_m"], d["altura_m"]) if d else None


def _mesmo_tamanho(a, b):
    return bool(a and b) and (abs(a[0] - b[0]) <= _TOLERANCIA_PAGINA_M
                              and abs(a[1] - b[1]) <= _TOLERANCIA_PAGINA_M)


# ---------------------------------------------------------- descrever

def limpar_descricao(texto, remover=(), config=None):
    """
    Nome de pasta ou de arquivo do cliente -> descrição do nosso nome.
    'AF_MANDARIN_SESSIONS_BACKDROP_400X250CM' -> 'BACKDROP' (removendo o
    nome do cliente). Tira medida, quantidade, "Artboard", o 'AF' da
    frente e palavra de material (que já vai na categoria do nome).
    """
    t = caderno_arte._sem_acento(texto or "").upper()
    t = re.sub(r"ARTBOARD\s*\d*", " ", t)
    t = _MEDIDA_NO_TEXTO.sub(" ", t)
    t = _QUANTIDADE_NO_TEXTO.sub(" ", t)
    t = re.sub(r"[_]+", " ", t)
    t = re.sub(r"^\s*AFS?\b[\s\-]*", "", t)
    fora = set()
    for r in remover:
        fora |= set(caderno_arte._sem_acento(r or "").upper().split())
    t = " ".join(p for p in t.split() if p.strip(".,-;") not in fora)
    t = re.sub(r"(\s*-\s*){2,}", " - ", t).strip(" -_.,;")
    if config:
        t = caderno_arte.descricao_limpa(t, config)
    return re.sub(r"\s+", " ", t).strip(" -_.,;")


def _uma_arte_so(irmaos):
    """A pasta é de UMA peça quando tudo que é arte ali é versão da mesma arte."""
    import origem_artes
    artes = [a for a in irmaos if origem_artes.papel(a, irmaos) in ("arte", "trabalho")]
    if not artes:
        return False
    primeira = artes[0]
    return all(origem_artes._mesma_arte(primeira, a) for a in artes[1:])


def descricao_sugerida(arquivo, irmaos, cliente="", area="", config=None):
    """
    Pasta de UMA peça (o ML: PAINEL FRONTAL FUNDO/ com o PDF, o .ai e o
    PNG da mesma arte) -> o nome da pasta, que é o que o cliente chamou a
    peça. Pasta com várias peças (o ZIP do Mandarin: AFs_CENOGRAFIA/ com 4
    artes) -> o nome de cada arquivo, limpo.
    """
    pasta = arquivo.grupo.split(" / ")[-1] if arquivo.grupo else ""
    remover = (cliente, area)
    # Pasta de nome genérico ("AFs", "AFs_CENOGRAFIA" limpo de novo...) com
    # uma arte só não é o nome da peça: se limpa vira vazio, vale o arquivo.
    if pasta and _uma_arte_so(irmaos):
        da_pasta = limpar_descricao(pasta, remover, config)
        if da_pasta:
            return da_pasta
    return (limpar_descricao(arquivo.base, remover, config)
            or limpar_descricao(arquivo.base, (), config)
            or "PECA")


def especificacao_do_nome(arquivo, config=None):
    """
    O que o nome do arquivo (e a pasta dele) especifica: quantidade e
    material. Devolve (quantidade, material, de_onde, avisos). O que não
    estiver lá sai 1 e A DEFINIR — regra do usuário, sem perguntar.
    """
    from dimensoes import extrair_quantidade
    config = config or carregar_config()
    de_onde, avisos = {}, []

    quantidade, achou = extrair_quantidade(arquivo.nome)
    if achou:
        de_onde["quantidade"] = "nome do arquivo"
    else:
        quantidade = 1
        de_onde["quantidade"] = "sem especificação: 1 unidade"

    material = None
    pasta = arquivo.grupo.split(" / ")[-1] if arquivo.grupo else ""
    for texto, rotulo in ((arquivo.base, "nome do arquivo"), (pasta, "nome da pasta")):
        if not texto:
            continue
        from dimensoes import identificar_categoria
        _, candidatas = identificar_categoria(
            caderno_arte._sem_acento(texto).upper(), config["materiais"],
            config.get("sinonimos_categoria", {}))
        if len(set(candidatas)) > 1:
            avisos.append("o %s cita mais de um material (%s)" % (rotulo, ", ".join(sorted(set(candidatas)))))
            break
        categoria = caderno_arte.categoria_do_material(texto, config)
        if categoria and categoria != caderno_arte.MATERIAL_A_DEFINIR:
            material, de_onde["material"] = categoria, rotulo
            break
    if not material:
        material = caderno_arte.MATERIAL_A_DEFINIR
        de_onde.setdefault("material", "sem especificação: A DEFINIR")
    return int(quantidade), material, de_onde, avisos


# ------------------------------------------------------------- caderno

_SANGRIA_NO_TEXTO = re.compile(r"\bSANGRIA\s*\d+(?:[.,]\d+)?\s*(?:MM|CM|M)?\b", re.I)
# Nome de arquivo que não diz qual é a peça: aí vale o nome da ficha.
_DESCRICOES_GENERICAS = {"ARTE", "ARTE FINAL", "FINAL", "ARQUIVO", "IMPRESSAO", "LAYOUT", "PDF",
                         "IMG", "IMAGEM", "PECA"}


def _palavras(texto):
    return re.findall(r"[A-Z0-9]+", caderno_arte._sem_acento(texto or "").upper())


def _nome_sem_medidas(texto):
    """
    Maiúsculo, sem acento, '_' virando espaço e sem medida nem 'sangria15cm'.
    O '_' sai ANTES: ele é letra pro regex, e em '..._vibra_sangria15cm' a
    sangria não era achada — o trecho comum saía com ela grudada e não batia
    com mais nada (visto no ensaio de 2026-10-02).
    """
    t = caderno_arte._sem_acento(texto or "").upper().replace("_", " ")
    return _SANGRIA_NO_TEXTO.sub(" ", _MEDIDA_NO_TEXTO.sub(" ", t))


def trecho_comum(nomes, fracao=0.6, minimo=3):
    """
    A sequência de palavras que se repete em quase todo nome de arquivo de
    um lote — o nome do projeto que a agência põe em todos. No caderno da
    LOJINHA (2026-10-02) 56 dos 57 arquivos terminam em
    '_loja_de_incoveniencia_vibra': não diz nada sobre a peça, e sem tirar
    toda descrição sairia com as mesmas quatro palavras. () quando não há.
    """
    seqs = [_palavras(_nome_sem_medidas(n)) for n in nomes]
    seqs = [s for s in seqs if s]
    if len(seqs) < minimo:
        return ()
    contagem = collections.Counter()
    for s in seqs:
        vistas = set()
        for i in range(len(s)):
            for j in range(i + 1, min(len(s), i + 8) + 1):
                trecho = tuple(s[i:j])
                if trecho not in vistas:
                    vistas.add(trecho)
                    contagem[trecho] += 1
    candidatos = [t for t, c in contagem.items()
                  if c >= fracao * len(seqs) and not all(p.isdigit() for p in t)
                  and (len(t) >= 2 or len(t[0]) >= 6)]
    if not candidatos:
        return ()
    return max(candidatos, key=lambda t: (len(t), contagem[t]))


def _tirar_trecho(texto, trecho):
    if not trecho:
        return texto
    return re.sub(r"\b" + r"[^A-Z0-9]+".join(re.escape(p) for p in trecho) + r"\b", " ", texto)


def _palavras_de_material(config):
    """{palavra (sem acento, maiúscula): categoria} — os materiais e os sinônimos."""
    mapa = {caderno_arte._sem_acento(c).upper(): c for c in config["materiais"]}
    for sinonimo, categoria in (config.get("sinonimos_categoria") or {}).items():
        mapa[caderno_arte._sem_acento(sinonimo).upper()] = categoria
    return mapa


def _sem_outro_material(texto, categoria, config):
    """
    Tira da descrição a palavra de material que NÃO é o da peça — o leitor
    do nome do arquivo pegaria a errada ('PLACA PS' numa peça de ADESIVO).
    A do próprio material fica: 'LONA A' é como o cliente chama a lona.
    Em 'PS ADESIVADO' só o PS fica; A DEFINIR não guarda nenhuma, senão a
    pendência viraria um material escolhido pelo nome.
    """
    mapa = _palavras_de_material(config)
    proprias = {mapa[p] for p in _palavras(categoria)[:1] if p in mapa}
    saida = []
    for palavra in texto.split():
        chave = palavra.strip(".,-;")
        cat = mapa.get(chave) or (mapa.get(chave[:-1]) if chave.endswith("S") else None)
        if cat and cat not in proprias:
            continue
        saida.append(palavra)
    return re.sub(r"\s+", " ", " ".join(saida)).strip(" -_.,;")


def descricao_do_caderno(arquivo, ficha, categoria, trecho=(), cliente="", area="", config=None):
    """
    A descrição de uma peça do caderno — do NOME DO ARQUIVO que a ficha
    aponta: 'LONA_A_7,14x1,10m_loja_de_incoveniencia_vibra_sangria15cm'
    vira 'LONA A'. É o arquivo que distingue a peça: no caderno da LOJINHA,
    15 fichas se chamam só 'PLACA PS', e os arquivos são PLACA_PS_1 a
    PLACA_PS_11, CUPOM_FISCAL, ADESIVO_ESPELHOS. Nome de arquivo genérico
    ('arte final') cai no nome da ficha.
    """
    config = config or carregar_config()

    def limpar(texto):
        t = limpar_descricao(_tirar_trecho(_nome_sem_medidas(texto), trecho), remover=(cliente, area))
        return _sem_outro_material(t, categoria, config)

    descricao = limpar(arquivo.base if arquivo else "")
    if not descricao or descricao in _DESCRICOES_GENERICAS or re.fullmatch(r"[\d\s.\-]+", descricao):
        descricao = limpar(ficha.get("nome") or "")
    return descricao or "PECA PAGINA %s" % ficha.get("pagina")


def _aviso_chapa_com_adesivo(ficha, arquivo, material, config):
    """
    A peça se chama 'PLACA PS' e o caderno pede ADESIVO: vale o material do
    caderno (regra de 2026-09-11), mas a chapa existe e não está no nome.
    Quem decide é ele — PS ADESIVADO, ou PS impresso direto.
    """
    gatilho_de = {extra: gatilho for gatilho, extra in (config.get("materiais_compostos") or {}).items()}
    if material not in gatilho_de:
        return None
    from dimensoes import contem_palavra
    texto = caderno_arte._sem_acento("%s %s" % (ficha.get("nome") or "",
                                                (arquivo.base if arquivo else "").replace("_", " "))).upper()
    for palavra, categoria in _palavras_de_material(config).items():
        if (categoria != material and config["materiais"].get(categoria, {}).get("tipo") == "chapa"
                and contem_palavra(texto, palavra)):
            return ("a peça cita %s e o caderno pede %s: se o adesivo vai aplicado na chapa, escolha "
                    "'%s %s'; se é impresso direto na chapa, '%s'"
                    % (categoria, material, categoria, gatilho_de[material], categoria))
    return None


def especificacao_do_caderno(ficha, arquivo, config=None):
    """
    (quantidade, material, de_onde, avisos) de uma peça do caderno. A ficha
    manda; o que ela não tiver vem do nome do arquivo, como sem caderno.
    """
    config = config or carregar_config()
    quantidade, material, de_onde, avisos = especificacao_do_nome(arquivo, config)
    onde = "caderno (página %s)" % ficha.get("pagina")
    digitos = re.sub(r"\D", "", str(ficha.get("quantidade") or ""))
    if digitos and int(digitos) > 0:
        quantidade, de_onde["quantidade"] = int(digitos), onde
    do_caderno = caderno_arte.categoria_do_material(ficha.get("material"), config) if ficha.get("material") else None
    if do_caderno:
        material, de_onde["material"] = do_caderno, onde
        # o que o NOME do arquivo cita deixa de importar: quem diz é a ficha
        avisos = [a for a in avisos if "mais de um material" not in a]
        aviso = _aviso_chapa_com_adesivo(ficha, arquivo, material, config)
        if aviso:
            avisos.append(aviso)
    elif ficha.get("material"):
        # o cliente pediu um material, só que não é nenhum dos cadastrados
        avisos.append("o caderno pede '%s', que não é um material cadastrado — ficou %s"
                      % (ficha["material"], material))
    return quantidade, material, de_onde, avisos


# Regra do usuário (2026-10-02), respondendo às 17 placas da LOJINHA que o
# caderno pedia como ADESIVO: "quando falar placa pode colocar o PS + adesivo".
# Placa é chapa de PS com o adesivo aplicado — PS ADESIVADO, que o resto do
# sistema lê como PS mais ADESIVO. E é cortada no tamanho FINAL (ver
# medidas_do_nome).
PALAVRA_PLACA = "PLACA"


def e_placa(*textos):
    """Algum dos textos (nome da ficha, nome do arquivo, descrição) fala em placa?"""
    from dimensoes import contem_palavra
    return any(contem_palavra(caderno_arte._sem_acento(t).upper(), PALAVRA_PLACA) for t in textos if t)


def regra_da_placa(textos, material, config):
    """
    (material, de_onde | None). A placa vira PS ADESIVADO quando o material
    é ADESIVO, A DEFINIR ou PS. Placa que cita OUTRA chapa ('PLACA PVC')
    não entra na regra — ela é de PS —, e o material fica como estava.
    """
    if not e_placa(*textos):
        return material, None
    gatilho = next((g for g, extra in (config.get("materiais_compostos") or {}).items()
                    if extra in config["materiais"]), None)
    if "PS" not in config["materiais"] or not gatilho:
        return material, None
    from dimensoes import contem_palavra
    texto = caderno_arte._sem_acento(" ".join(t for t in textos if t)).upper().replace("_", " ")
    for palavra, categoria in _palavras_de_material(config).items():
        if (categoria != "PS" and config["materiais"].get(categoria, {}).get("tipo") == "chapa"
                and contem_palavra(texto, palavra)):
            return material, None
    extra = config["materiais_compostos"][gatilho]
    composto = "PS %s" % gatilho
    if material in (extra, caderno_arte.MATERIAL_A_DEFINIR, "PS", composto):
        return composto, "regra da placa: PS + adesivo (02/10)"
    return material, None


def medidas_do_nome(peca):
    """
    (a medida que vai na frente do nome, a segunda, o rótulo da segunda).

    Regra do usuário (2026-10-02): "o restante manter o tamanho maior sempre
    que é com sangria". Peça com sangria leva na frente o tamanho COM
    sangria — é o que sai da máquina e o que se gasta, e é como a equipe já
    nomeia as lonas na produção ('7.44X1.40M_LONA_C_7,14x1,10m') — e a final
    vai atrás, como '_final'. A placa é a exceção: a chapa é cortada no
    tamanho final, que vai na frente, e a sangria atrás (o adesivo é que é
    impresso com ela). Vale sempre a primeira medida do nome.
    """
    if not peca.arte_m:
        return None, None, None
    final = caderno_arte.medida_metros_para_nome(peca.arte_m)
    tem_sangria = bool(peca.sangria_m) and (peca.sangria_m[0] - peca.arte_m[0] > _SANGRIA_MINIMA_M
                                            or peca.sangria_m[1] - peca.arte_m[1] > _SANGRIA_MINIMA_M)
    if not tem_sangria:
        return final, None, None
    com_sangria = caderno_arte.medida_metros_para_nome(peca.sangria_m)
    if e_placa(peca.descricao, peca.arquivo.base if peca.arquivo else "", (peca.ficha or {}).get("nome")):
        return final, com_sangria, "sangria"
    return com_sangria, final, "final"


def medida_que_conta(peca):
    """(largura, altura) em metros da medida da frente do nome — a que vira m²."""
    principal, _, rotulo = medidas_do_nome(peca)
    if principal is None:
        return None
    return peca.sangria_m if rotulo == "final" else peca.arte_m


def materiais_para_escolher(config=None):
    """
    O que a tela oferece: A DEFINIR, cada material, e a chapa com adesivo
    aplicado ('PS ADESIVADO') — nome que o resto do sistema já lê como PS
    mais ADESIVO (config 'materiais_compostos').
    """
    config = config or carregar_config()
    materiais = config["materiais"]
    escolhas = [caderno_arte.MATERIAL_A_DEFINIR] + list(materiais)
    for gatilho, extra in (config.get("materiais_compostos") or {}).items():
        if extra in materiais:
            escolhas += ["%s %s" % (c, gatilho) for c, info in materiais.items()
                         if info.get("tipo") == "chapa" and c != extra]
    return escolhas


# -------------------------------------------------------------- escala

# A agência desenha a peça grande em ESCALA: o Illustrator não passa de
# 5,77 m de prancheta. A LONA A da LOJINHA tem 7,14 x 1,10 m no caderno e
# 0,714 x 0,110 m no PDF (2026-10-02) — lida ao pé da letra, o nome sairia
# com um décimo do tamanho.
#
# Regra do usuário de 2026-08-29 (dimensoes.dimensao_da_arte): SEM uma
# referência confiável, "avisar quando desconfiar, não multiplicar
# sozinho". Aqui só multiplica quando HÁ referência — a medida do caderno,
# ou a escrita no nome do arquivo — e a arte vezes o fator BATE com ela
# nos dois lados: é a prova, como o "arquivo batendo 100×" do relatório
# (CLAUDE.md). A linha sai assinalada, o nome leva 'ESCALA 1-10' e a tela
# deixa desligar.
ESCALAS = (10,)
_TOLERANCIA_ESCALA = 0.02
# Um lado bate exato e o outro não: escala, se o outro estiver perto (é a
# arte que difere do caderno, e isso vira o aviso de sempre). Longe disso é
# medida trocada, e aí não se multiplica nada.
_PERTO = 1.5


def _bate(a, b):
    return abs(a - b) <= max(0.005, abs(b) * _TOLERANCIA_ESCALA)


def _confere(paginas, referencia, fator):
    """
    As páginas × fator são a peça da referência? None, ou o tipo da prova:
      'total'   os dois lados batem;
      'partes'  páginas de tamanhos diferentes que são PARTES da peça (o
                piso de 7,00 x 6,00 em três lonas): todas cabem nela, e
                alguma tem um lado inteiro dela;
      'parcial' um lado bate exato e o outro está perto (a LONA 18 da
                LOJINHA: 6,00 bate, a altura dá 2,40 contra 2,70).
    """
    ref = sorted(referencia)
    lados = [sorted((p[0] * fator, p[1] * fator)) for p in paginas if p]
    if not lados or min(ref) <= 0:
        return None
    if all(_mesmo_tamanho(l, lados[0]) for l in lados):
        menor, maior = lados[0]
        if _bate(menor, ref[0]) and _bate(maior, ref[1]):
            return "total"
        for lado, outro, r_lado, r_outro in ((menor, maior, ref[0], ref[1]), (maior, menor, ref[1], ref[0])):
            if _bate(lado, r_lado) and outro > 0 and 1 / _PERTO <= outro / r_outro <= _PERTO:
                return "parcial"
        return None
    cabem = all(l[0] <= ref[0] * (1 + _TOLERANCIA_ESCALA) + 0.005
                and l[1] <= ref[1] * (1 + _TOLERANCIA_ESCALA) + 0.005 for l in lados)
    if cabem and any(_bate(lado, r) for l in lados for lado in l for r in ref):
        return "partes"
    return None


def escala_provada(paginas, referencias):
    """
    (fator, prova): o fator (10) quando a arte, vezes ele, bate com uma das
    referências — ver _confere pro que conta como prova. (1, None) quando a
    arte já bate como está, ou quando nada prova escala nenhuma.
    'paginas' são as medidas (largura, altura) de cada página do PDF.
    """
    paginas = [p for p in paginas if p]
    for referencia in referencias:
        if not referencia or not paginas:
            continue
        if _confere(paginas, referencia, 1):
            return 1, None
        for fator in ESCALAS:
            prova = _confere(paginas, referencia, fator)
            if prova:
                return fator, prova
    return 1, None


def _vezes(medida, fator):
    return (medida[0] * fator, medida[1] * fator) if medida else None


def aplicar_escala(peca, ligada):
    """Liga (o fator achado) ou desliga (1) a escala: medida e sangria = PDF × fator."""
    if peca.arte_pdf_m is None:
        peca.arte_pdf_m, peca.sangria_pdf_m = peca.arte_m, peca.sangria_m
    fator = peca.escala_achada if ligada else 1
    peca.escala = fator
    peca.arte_m = _vezes(peca.arte_pdf_m, fator)
    peca.sangria_m = _vezes(peca.sangria_pdf_m, fator)
    if fator > 1:
        peca.de_onde["medida"] = "da arte × %d (escala 1:%d, provada pela medida do %s)" % (
            fator, fator, "caderno" if peca.ficha else "nome")
    else:
        peca.de_onde["medida"] = "da arte"
    return peca


# ------------------------------------------------------------- propor

def propor(baixados, todos=None, cliente="", area="", config=None):
    """
    As linhas do passo 2. 'baixados' é [(Arquivo, caminho_local, chave)];
    'todos' é tudo o que a origem listou (pra saber o que cada arquivo É
    olhando os vizinhos, inclusive os que ele não marcou).

    PDF com páginas de TAMANHOS diferentes vira uma peça por página — era
    o TOTEM do Mandarin (0,80x1,90 + um quadrado de 0,50x0,50), e num
    arquivo só a máquina imprime a primeira página e o resto nunca sai.
    Páginas do MESMO tamanho ficam juntas (podem ser frente e verso), com
    aviso; separar_paginas() desfaz se ele quiser.

    Arquivo de CADERNO (Arquivo.ficha): material, quantidade e descrição
    vêm da ficha (especificacao_do_caderno, descricao_do_caderno), e a
    medida do caderno confere a arte — inclusive a escala. Várias fichas
    apontando o MESMO PDF (os três QUADROS da LOJINHA num PDF de 3 páginas)
    repartem as páginas pela ordem do caderno.
    """
    import origem_artes
    config = config or carregar_config()
    todos = list(todos) if todos is not None else [a for a, _, _ in baixados]
    por_grupo = origem_artes.agrupar(todos)
    # as fichas que apontam o mesmo arquivo, na ordem do caderno
    colegas = collections.defaultdict(list)
    for a in todos:
        if getattr(a, "ficha", None) and getattr(a, "mesmo_arquivo", ""):
            colegas[a.mesmo_arquivo].append(a)
    trecho = trecho_comum([a.base for a in todos if getattr(a, "ficha", None)])

    pecas = []
    for arquivo, local, chave in baixados:
        irmaos = por_grupo.get(arquivo.grupo) or [arquivo]
        papel = origem_artes.papel(arquivo, irmaos)
        base = Peca(arquivo=arquivo, local=pathlib.Path(local), chave=chave, papel=papel)
        if papel != "arte":
            pecas.append(base)
            continue

        ficha = getattr(arquivo, "ficha", None)
        if ficha:
            base.ficha = ficha
            base.quantidade, base.material, base.de_onde, base.avisos = especificacao_do_caderno(
                ficha, arquivo, config)
            textos = (ficha.get("nome"), arquivo.base)
        else:
            base.quantidade, base.material, base.de_onde, base.avisos = especificacao_do_nome(arquivo, config)
            textos = (arquivo.base, arquivo.grupo.split(" / ")[-1] if arquivo.grupo else "")
        # placa é PS + adesivo (regra de 02/10) — antes da descrição, que
        # guarda a palavra do material da peça e tira a dos outros
        material, regra = regra_da_placa(textos, base.material, config)
        if regra:
            base.material, base.de_onde["material"] = material, regra
            base.avisos = [a for a in base.avisos
                           if "escolha '" not in a and "mais de um material" not in a]
        if ficha:
            base.descricao = descricao_do_caderno(arquivo, ficha, base.material, trecho, cliente, area, config)
        else:
            base.descricao = descricao_sugerida(arquivo, irmaos, cliente, area, config)
        base.medida_no_nome = _medida_do_nome(arquivo.nome)
        medida_do_caderno = caderno_arte.medida_em_metros(ficha.get("medidas")) if ficha else None

        ext = arquivo.ext
        paginas = None
        if ext in ("PDF", "AI"):
            paginas = _medir_pdf(local)
            if paginas == [] and ext == "AI":
                base.avisos.append(".ai salvo sem compatibilidade PDF: o tamanho só se lê no Illustrator")
            paginas = paginas or None
        elif ext in ("TIF", "TIFF", "JPG", "JPEG", "PNG", "PSD"):
            medida = _medir_imagem(local)
            if medida:
                paginas = [_medir_imagem_com_marca(local, medida, base)]
            else:
                base.avisos.append("a imagem não tem resolução (DPI) gravada: não dá pra saber o tamanho")
        elif ext == "EPS":
            medida = _medir_eps(local)
            if medida:
                paginas = [(medida, medida, "nao sei")]

        if not paginas:
            # a arte não diz o tamanho: aí vale o que o caderno ou o nome disser
            if medida_do_caderno:
                base.arte_m = medida_do_caderno
                base.de_onde["medida"] = "caderno (a arte não diz o tamanho)"
            elif base.medida_no_nome:
                base.arte_m = base.medida_no_nome
                base.de_onde["medida"] = "nome do arquivo (a arte não diz o tamanho)"
            else:
                base.avisos.append("sem medida na arte nem no nome: fica com o nome do cliente")
            base.marca = "nao sei"
            pecas.append(base)
            continue

        base.paginas = len(paginas)
        base.de_onde["medida"] = "da arte"
        fator, prova = escala_provada([p[0] for p in paginas], (medida_do_caderno, base.medida_no_nome))
        if fator > 1:
            no_pdf = paginas[0][0]
            paginas = [(_vezes(arte, fator), _vezes(sang, fator), marca) for arte, sang, marca in paginas]
            base.escala = base.escala_achada = fator
            quem = "caderno" if (ficha and medida_do_caderno) else "nome"
            base.de_onde["medida"] = "da arte × %d (escala 1:%d, provada pela medida do %s)" % (fator, fator, quem)
            ref = medida_do_caderno if quem == "caderno" else base.medida_no_nome
            if prova == "partes":
                explica = ("as %d páginas do PDF, × %d, são partes da peça de %s do %s"
                           % (len(paginas), fator, formatar_medida(ref), quem))
            elif prova == "parcial":
                explica = ("o PDF mede %s; × %d dá %s — um lado bate com o %s (%s), o outro não: confira"
                           % (formatar_medida(no_pdf), fator, formatar_medida(paginas[0][0]), quem,
                              formatar_medida(ref)))
            else:
                explica = ("o PDF mede %s; × %d dá %s, que bate com a medida do %s"
                           % (formatar_medida(no_pdf), fator, formatar_medida(paginas[0][0]), quem))
            base.avisos.append("arte em escala 1:%d — %s. O nome leva 'ESCALA 1-%d'." % (fator, explica, fator))
        referencia, de_quem = ((medida_do_caderno, "o caderno") if medida_do_caderno
                               else (base.medida_no_nome, "o nome"))
        mesmo_tamanho = all(_mesmo_tamanho(p[0], paginas[0][0]) for p in paginas)
        if (referencia and paginas[0][0] and mesmo_tamanho
                and not _mesmo_tamanho(referencia, paginas[0][0])
                and not _mesmo_tamanho(referencia, tuple(reversed(paginas[0][0])))):
            base.avisos.append("%s diz %s e a arte mede %s — vale a arte"
                               % (de_quem, formatar_medida(referencia), formatar_medida(paginas[0][0])))

        def guardar_pdf(peca):
            """A medida como está no PDF, pra tela poder desligar a escala."""
            if fator > 1:
                peca.arte_pdf_m = _vezes(peca.arte_m, 1 / fator)
                peca.sangria_pdf_m = _vezes(peca.sangria_m, 1 / fator)
            return peca

        # o mesmo PDF apontado por várias fichas: cada uma leva a sua página
        juntas = (colegas.get(arquivo.mesmo_arquivo) if ficha else None) or [arquivo]
        if len(juntas) > 1:
            posicao = next((i for i, a in enumerate(juntas) if a.id == arquivo.id), 0)
            paginas_do_caderno = ", ".join(str(a.ficha.get("pagina")) for a in juntas)
            if len(paginas) == len(juntas):
                arte, sang, marca = paginas[posicao]
                p = dataclasses.replace(base, pagina=posicao + 1, arte_m=arte, sangria_m=sang, marca=marca,
                                        paginas=len(paginas), avisos=list(base.avisos),
                                        de_onde=dict(base.de_onde))
                if posicao:
                    p.descricao = "%s - PAGINA %d" % (base.descricao, posicao + 1)
                p.avisos.append("as páginas %s do caderno apontam o mesmo PDF de %d páginas: pela ordem do "
                                "caderno esta é a página %d dele — confira a prévia"
                                % (paginas_do_caderno, len(paginas), posicao + 1))
                pecas.append(guardar_pdf(p))
                continue
            base.avisos.append("as páginas %s do caderno apontam este mesmo arquivo (%d página%s): se não "
                               "for a mesma arte, o link de uma delas está errado no caderno"
                               % (paginas_do_caderno, len(paginas), "s" if len(paginas) != 1 else ""))
            if posicao:
                base.descricao = "%s %d" % (base.descricao, posicao + 1)

        diferentes = len(paginas) > 1 and not mesmo_tamanho
        if diferentes:
            for i, (arte, sang, marca) in enumerate(paginas, start=1):
                p = dataclasses.replace(base, pagina=i, arte_m=arte, sangria_m=sang, marca=marca,
                                        avisos=list(base.avisos), de_onde=dict(base.de_onde))
                if i > 1:
                    p.descricao = "%s - PAGINA %d" % (base.descricao, i)
                p.avisos.append("página %d de %d do mesmo PDF (tamanhos diferentes: virou peça própria)"
                                % (i, len(paginas)))
                pecas.append(guardar_pdf(p))
            continue

        base.arte_m, base.sangria_m, base.marca = paginas[0]
        if len(paginas) > 1:
            aviso = "%d páginas do mesmo tamanho — frente e verso? Dá pra separar." % len(paginas)
            if base.quantidade == len(paginas) and ficha:
                aviso += (" O caderno pede %d unidades: se cada página é uma unidade, separe e deixe 1 un "
                          "em cada." % base.quantidade)
            base.avisos.append(aviso)
        pecas.append(guardar_pdf(base))
    for peca in pecas:
        aviso = _aviso_maior_que_a_chapa(peca, config)
        if aviso:
            peca.avisos.append(aviso)
    return pecas


def _aviso_maior_que_a_chapa(peca, config):
    """
    Peça de chapa maior que a chapa cadastrada não sai de uma chapa só — e
    quase sempre é material trocado: o CUPOM FISCAL da LOJINHA (3,10 m) caiu
    na regra da placa, e a chapa de PS é 2,00 x 1,00 (2026-10-02).
    """
    if not peca.leva_nome_do_padrao:
        return None
    categoria = (_palavras(peca.material) or [""])[0]
    info = config["materiais"].get(categoria) or {}
    medida = medida_que_conta(peca)
    if info.get("tipo") != "chapa" or not medida or not info.get("largura_cm") or not info.get("comprimento_cm"):
        return None
    chapa = sorted((info["largura_cm"] / 100, info["comprimento_cm"] / 100))
    lados = sorted(medida)
    if lados[0] <= chapa[0] + 0.005 and lados[1] <= chapa[1] + 0.005:
        return None
    return ("a peça (%s) é maior que a chapa de %s cadastrada (%s): sai em partes — confira o material"
            % (formatar_medida(medida), categoria, formatar_medida(tuple(chapa))))


def formatar_medida(medida):
    return ("%.2f x %.2f m" % medida).replace(".", ",") if medida else "?"


def separar_paginas(peca):
    """Páginas do mesmo tamanho que ele decidiu que são peças separadas."""
    if peca.paginas <= 1 or peca.pagina:
        return [peca]
    saida = []
    for i in range(1, peca.paginas + 1):
        p = dataclasses.replace(peca, pagina=i, avisos=[a for a in peca.avisos if "páginas" not in a],
                                de_onde=dict(peca.de_onde))
        if i > 1:
            p.descricao = "%s - PAGINA %d" % (peca.descricao, i)
        saida.append(p)
    return saida


def duplicar(peca, todas):
    """
    A mesma arte servindo outra peça do projeto — o [+] da tela. No LANDMARK
    uma arte só era a lateral do fundo, do esquerdo e do direito; sem
    caderno, o sistema não tem como saber disso sozinho.
    """
    copias = [p.copia for p in todas if p.local == peca.local and p.pagina == peca.pagina]
    return dataclasses.replace(peca, copia=max(copias + [1]) + 1, avisos=list(peca.avisos),
                               de_onde=dict(peca.de_onde))


# -------------------------------------------------------------- nomear

_CONFIG_DOS_NOMES = None


def _config_dos_nomes():
    """
    O config pra tirar palavra de material do nome — lido uma vez: o nome é
    refeito a cada tecla na tela, e ler o config.json a cada vez não precisa.
    """
    global _CONFIG_DOS_NOMES
    if _CONFIG_DOS_NOMES is None:
        _CONFIG_DOS_NOMES = carregar_config()
    return _CONFIG_DOS_NOMES


def _area_no_nome(area):
    return re.sub(r"\s+", " ", caderno_arte._sem_acento(area or "").upper()).strip()


def nome_final(peca, area=""):
    """
    Arte com medida: o nome da casa, com a área na frente da descrição
    (como as áreas do Mercado Livre: 'LANDMARK - PAINEL FRONTAL FUNDO').
    O resto — .ai de trabalho, prévia, arte sem medida — fica com o nome
    do cliente, junto (decisão de 21/09).
    """
    if not peca.leva_nome_do_padrao:
        return peca.arquivo.nome
    descricao = re.sub(r"\s+", " ", (peca.descricao or "PECA").strip()) or "PECA"
    # O material pode ter mudado na tela depois da descrição pronta: 'ADESIVO
    # ESPELHOS' passado pra PS ADESIVADO seria lido como ADESIVO pelo leitor
    # do nome (visto em 2026-10-02), e o PS sumiria da OS e do estoque.
    descricao = _sem_outro_material(descricao, peca.material, _config_dos_nomes()) or "PECA"
    prefixo = _area_no_nome(area)
    if prefixo and not caderno_arte._sem_acento(descricao).upper().startswith(prefixo):
        descricao = "%s - %s" % (prefixo, descricao)
    # arte em escala: o PDF tem um décimo do tamanho que o nome diz, e quem
    # abre o arquivo no RIP precisa saber disso pelo nome
    if peca.escala > 1 and not re.search(r"\bESC(ALA)?\b", caderno_arte._sem_acento(descricao).upper()):
        descricao = "%s ESCALA 1-%d" % (descricao, peca.escala)
    principal, segunda, rotulo = medidas_do_nome(peca)
    extensao = ".pdf" if peca.pagina else "." + (peca.arquivo.ext.lower() or "pdf")
    return caderno_arte.montar_nome(peca.quantidade, peca.material, principal, descricao,
                                    segunda, rotulo_segunda=rotulo or "sangria") + extensao


def nomes_do_lote(pecas, area=""):
    """
    {peca: nome} do lote inteiro. Arquivo de apoio com o mesmo nome vindo
    de pastas diferentes ('mockup.jpg' em cada pasta de peça) ganha o nome
    da pasta entre parênteses — sem isso um apagaria o outro.
    """
    nomes = {id(p): nome_final(p, area) for p in pecas}
    apoio = [p for p in pecas if not p.leva_nome_do_padrao]
    contagem = {}
    for p in apoio:
        contagem[nomes[id(p)].lower()] = contagem.get(nomes[id(p)].lower(), 0) + 1
    for p in apoio:
        if contagem[nomes[id(p)].lower()] > 1 and p.arquivo.grupo:
            base, ext = (nomes[id(p)].rsplit(".", 1) + [""])[:2]
            nomes[id(p)] = "%s (%s)%s" % (base, p.arquivo.grupo.split(" / ")[-1], "." + ext if ext else "")
    return nomes


def repetidos(pecas, area=""):
    """Nomes que sairiam iguais — um arquivo comeria o outro. {nome: [pecas]}."""
    nomes = nomes_do_lote(pecas, area)
    por_nome = {}
    for p in pecas:
        por_nome.setdefault(nomes[id(p)].lower(), []).append(p)
    return {nomes[id(ps[0])]: ps for ps in por_nome.values() if len(ps) > 1}


# ------------------------------------------------------------ arquivar

@dataclasses.dataclass
class ResumoRecebimento:
    arquivadas: list = dataclasses.field(default_factory=list)   # (peca, caminho)
    ja_estavam: list = dataclasses.field(default_factory=list)   # (peca, caminho)
    falharam: list = dataclasses.field(default_factory=list)     # (peca, motivo)
    originais: list = dataclasses.field(default_factory=list)
    avisos: list = dataclasses.field(default_factory=list)


def _sha(caminho):
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1024 * 1024), b""):
            h.update(bloco)
    return h.hexdigest()


def extrair_pagina(origem, indice, destino):
    """
    Uma página do PDF num PDF próprio, e a prova de que ela desenha
    exatamente o que desenhava: render lado a lado e medida da arte igual.
    A página é copiada inteira (insert_pdf) — caixas, sangria e tudo.
    """
    import marcas_de_corte
    import pymupdf
    from PIL import Image, ImageChops

    def imagem(doc, i, largura=1000):
        pg = doc[i]
        esc = largura / pg.rect.width
        px = pg.get_pixmap(matrix=pymupdf.Matrix(esc, esc))
        return Image.frombytes("RGB" if px.n < 4 else "RGBA", (px.width, px.height), px.samples).convert("RGB")

    destino = pathlib.Path(destino)
    with pymupdf.open(str(origem)) as doc:
        novo = pymupdf.open()
        novo.insert_pdf(doc, from_page=indice, to_page=indice)
        novo.save(str(destino), garbage=4, deflate=True)
        novo.close()
        antes = imagem(doc, indice)
        medida_antes = marcas_de_corte.medidas_da_pagina(doc, indice).get("TrimBox_pt")
    with pymupdf.open(str(destino)) as doc2:
        depois = imagem(doc2, 0)
        medida_depois = marcas_de_corte.medidas_da_pagina(doc2, 0).get("TrimBox_pt")
    pior = max(ImageChops.difference(antes, depois.resize(antes.size)).convert("L").getextrema())
    medida_ok = (medida_antes is None and medida_depois is None) or (
        medida_antes and medida_depois
        and max(abs(a - b) for a, b in zip(medida_antes, medida_depois)) < 0.5)
    if pior > 2 or not medida_ok:
        destino.unlink(missing_ok=True)
        raise ErroRecebimento("a página %d separada não ficou igual à original (diferença %d/255)"
                              % (indice + 1, pior))
    return destino


def _preparar(peca, prontas, trabalho, remover_marcas, logger):
    """
    O arquivo que vai pra ARTES, pronto: página separada, marca tirada,
    imagem cortada. Feito UMA vez por arte — a mesma arte servindo três
    peças passa uma vez só pelo Illustrator.
    """
    if not peca.leva_nome_do_padrao:
        return peca.local, False
    chave = (str(peca.local), peca.pagina, peca.corte_px)
    if chave in prontas:
        return prontas[chave]
    trabalho.mkdir(parents=True, exist_ok=True)
    nome = "%03d_%s" % (len(prontas), peca.local.name)
    alvo = trabalho / (nome if not peca.pagina else pathlib.Path(nome).stem + "_p%d.pdf" % peca.pagina)
    if peca.pagina:
        extrair_pagina(peca.local, peca.pagina - 1, alvo)
    else:
        shutil.copy2(peca.local, alvo)

    removida = False
    imagem = alvo.suffix.lower() != ".pdf"
    if remover_marcas and peca.marca == "tem" and imagem and not peca.corte_px:
        raise ErroRecebimento("a imagem tem marca de corte e o corte ainda não foi aprovado — clique em "
                              "'ver corte' (ou desmarque 'Tirar a marca de corte').")
    if remover_marcas and peca.marca == "tem" and not imagem:
        import marcas_de_corte
        ok, msg = marcas_de_corte.remover_marcas_com_limite(alvo, logger=logger)
        if not ok:
            raise ErroRecebimento("a marca de corte não saiu (%s). A arte NÃO entrou em ARTES pela "
                                  "metade — tente de novo." % msg)
        removida = True
    if remover_marcas and peca.corte_px:
        import marcas_de_corte
        ok, msg = marcas_de_corte.cortar_imagem(alvo, peca.corte_px, logger=logger)
        if not ok:
            raise ErroRecebimento("o corte da imagem não foi feito (%s). A imagem NÃO entrou em "
                                  "ARTES — o original continua intacto." % msg)
        removida = True
    prontas[chave] = (alvo, removida)
    return prontas[chave]


def _chave_da_peca(peca):
    chave = peca.chave
    if peca.pagina:
        chave += "|pagina %d" % peca.pagina
    if peca.copia > 1:
        chave += "|copia %d" % peca.copia
    return chave


def _nome_de_pasta(texto):
    return (re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", texto or "").strip(" .") or "recebido")[:80]


def arquivar(pecas, cliente, destino, area="", origem=None, guardar_original=True,
             remover_marcas=True, logger=None, quando=None, pasta_trabalho=None):
    """
    As peças do passo 2 em 'destino' (ARTES do cliente, ou a pasta que ele
    escolheu), cada uma com o seu nome; o registro em _baixados.json; e o
    que chegou guardado como chegou em _sistema/recebidos/ quando a origem
    é descartável (link de WeTransfer morre em dias).

    Nunca sobrescreve: arquivo com o mesmo nome e o mesmo conteúdo é "já
    estava"; com conteúdo diferente, falha e diz — ele decide.
    """
    def aviso(nivel, texto):
        if logger:
            logger(nivel, texto)

    quando = quando or datetime.datetime.now()
    destino = pathlib.Path(destino)
    ruins = repetidos(pecas, area)
    if ruins:
        raise ErroRecebimento("Estes nomes sairiam iguais e um arquivo apagaria o outro: %s. "
                              "Mude a descrição de uma delas." % "; ".join(sorted(ruins)))
    destino.mkdir(parents=True, exist_ok=True)
    # Onde a página é separada e o Illustrator tira a marca: na espera
    # LOCAL, nunca dentro de ARTES — lá é OneDrive, e ia sincronizar
    # arquivo pela metade enquanto o Illustrator trabalha.
    trabalho = pathlib.Path(pasta_trabalho) if pasta_trabalho else (
        caminhos.PASTA_RECEBENDO / ("_preparando %s" % quando.strftime("%Y-%m-%d %H%M%S")))
    nomes = nomes_do_lote(pecas, area)
    resumo = ResumoRecebimento()
    prontas = {}
    registro = {}
    try:
        for peca in pecas:
            alvo = destino / nomes[id(peca)]
            try:
                fonte, removida = _preparar(peca, prontas, trabalho, remover_marcas, logger)
            except (ErroRecebimento, OSError) as e:
                resumo.falharam.append((peca, str(e)))
                aviso("warn", "%s — %s" % (alvo.name, e))
                continue
            peca.marca_removida = removida
            if alvo.exists():
                if _sha(alvo) == _sha(fonte):
                    resumo.ja_estavam.append((peca, alvo))
                else:
                    resumo.falharam.append((peca, "já existe outro arquivo com esse nome em %s" % destino.name))
                    aviso("warn", "%s já existe com outro conteúdo — não sobrescrevi" % alvo.name)
                    continue
            else:
                parcial = alvo.with_name("~montando~" + alvo.name)
                shutil.copy2(fonte, parcial)
                parcial.replace(alvo)
                resumo.arquivadas.append((peca, alvo))
                aviso("ok", "arquivado: %s" % alvo.name)

            falta = [] if peca.material_definido or not peca.leva_nome_do_padrao else ["material"]
            registro[_chave_da_peca(peca)] = {
                "origem": peca.chave.split("|")[0],
                "de": getattr(origem, "rotulo", ""),
                "arquivo_original": peca.arquivo.nome,
                "grupo": peca.arquivo.grupo,
                "pagina": peca.pagina,
                "arquivo": alvo.name,
                # relativo ao OneDrive: o usuário do Windows muda de PC pra PC
                "pasta": caminhos.relativo_ao_onedrive(destino),
                "area": area or None,
                "quando": quando.strftime("%Y-%m-%dT%H:%M:%S"),
                "papel": peca.papel,
                "material": peca.material if peca.leva_nome_do_padrao else None,
                "quantidade": peca.quantidade if peca.leva_nome_do_padrao else None,
                "medida_conferida_m": [round(v, 3) for v in peca.arte_m] if peca.arte_m else None,
                "sangria_m": [round(v, 3) for v in peca.sangria_m] if peca.sangria_m else None,
                "medida_no_nome_m": [round(v, 3) for v in peca.medida_no_nome] if peca.medida_no_nome else None,
                "marca_removida": peca.marca_removida,
                "de_onde": peca.de_onde,
                "falta_confirmar": falta,
            }
            if peca.leva_nome_do_padrao and medidas_do_nome(peca)[2] == "final":
                # a medida da frente do nome é a COM sangria (regra de 02/10)
                registro[_chave_da_peca(peca)]["medida_no_nome"] = "com sangria"
            if origem is not None:
                # de onde a arte foi pega — o relatório de recebimento mostra o link (02/10)
                for campo, metodo in (("link_origem", "link_de"), ("link_caderno", "link_do_caderno")):
                    link = getattr(origem, metodo, lambda a: "")(peca.arquivo)
                    if link:
                        registro[_chave_da_peca(peca)][campo] = link
            if peca.escala > 1:
                registro[_chave_da_peca(peca)].update({
                    "escala": peca.escala,
                    "medida_no_arquivo_m": [round(v, 4) for v in peca.arte_pdf_m] if peca.arte_pdf_m else None,
                })
            if peca.ficha:
                # o que a ficha dizia: o cliente edita o caderno quando quiser
                registro[_chave_da_peca(peca)]["caderno"] = {
                    c: peca.ficha.get(c) for c in ("pagina", "secao", "nome", "medidas", "sangria",
                                                   "material", "quantidade", "obs")}
    finally:
        shutil.rmtree(trabalho, ignore_errors=True)

    if guardar_original and origem is not None:
        pasta = cliente.pasta_sistema / "recebidos" / _nome_de_pasta(
            "%s %s" % (quando.strftime("%Y-%m-%d"), getattr(origem, "rotulo", "") or origem.tipo))
        try:
            resumo.originais = origem.guardar_original(pasta) or []
            if not resumo.originais:
                try:
                    pasta.rmdir()
                except OSError:
                    pass
        except Exception as e:
            resumo.avisos.append("não consegui guardar o original: %s" % e)
            aviso("warn", "não consegui guardar o original: %s" % e)

    if registro:
        caminho = cliente.pasta / arte_recebida.NOME_ESTADO
        estado = arte_recebida.ler_baixados(cliente.pasta)
        estado.update(registro)
        caminho.write_text(json.dumps(estado, ensure_ascii=False, indent=2), encoding="utf-8")
    return resumo


def ja_recebidos(cliente):
    """{chave: registro} do que já entrou por aqui — pra tela marcar 'já recebido'."""
    return arte_recebida.ler_baixados(cliente.pasta) if cliente else {}


def foi_recebido(chave_arquivo, recebidos):
    """Algum registro veio deste arquivo da origem (inteiro, página ou cópia)?"""
    return any(k == chave_arquivo or k.startswith(chave_arquivo + "|") for k in recebidos)


if __name__ == "__main__":
    import argparse
    import datetime

    parser = argparse.ArgumentParser(description="Baixa as artes liberadas do caderno.")
    parser.add_argument("caderno", help="caminho do .pptx do caderno de arte")
    parser.add_argument("pasta", help="pasta de recebimento (onde ficam _entrada e ARTES)")
    parser.add_argument("--limite", type=int, default=None, help="baixa só as N primeiras que faltam")
    parser.add_argument("--refazer", action="store_true", help="baixa de novo o que já foi baixado")
    args = parser.parse_args()

    def registrar(nivel, texto):
        print("[%s] %-5s %s" % (datetime.datetime.now().strftime("%H:%M:%S"), nivel, texto), flush=True)

    resumo = baixar_lote(args.caderno, args.pasta, limite=args.limite,
                         refazer=args.refazer, logger=registrar)
    print(flush=True)
    print("=" * 60, flush=True)
    print("BAIXADAS: %d  |  PULADAS (já tinha): %d  |  FALHARAM: %d"
          % (len(resumo["baixadas"]), len(resumo["puladas"]), len(resumo["falharam"])), flush=True)
    if resumo["falharam"]:
        print("\nFALHARAM (pra conferir e tentar de novo):", flush=True)
        for nome, motivo in resumo["falharam"]:
            print("  - %s: %s" % (nome, motivo), flush=True)
