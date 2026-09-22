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
"""
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
    """
    import origem_artes
    config = config or carregar_config()
    todos = list(todos) if todos is not None else [a for a, _, _ in baixados]
    por_grupo = origem_artes.agrupar(todos)

    pecas = []
    for arquivo, local, chave in baixados:
        irmaos = por_grupo.get(arquivo.grupo) or [arquivo]
        papel = origem_artes.papel(arquivo, irmaos)
        base = Peca(arquivo=arquivo, local=pathlib.Path(local), chave=chave, papel=papel)
        if papel != "arte":
            pecas.append(base)
            continue

        base.descricao = descricao_sugerida(arquivo, irmaos, cliente, area, config)
        base.quantidade, base.material, base.de_onde, base.avisos = especificacao_do_nome(arquivo, config)
        base.medida_no_nome = _medida_do_nome(arquivo.nome)

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
            # a arte não diz o tamanho: aí vale o que o nome disser
            if base.medida_no_nome:
                base.arte_m = base.medida_no_nome
                base.de_onde["medida"] = "nome do arquivo (a arte não diz o tamanho)"
            else:
                base.avisos.append("sem medida na arte nem no nome: fica com o nome do cliente")
            base.marca = "nao sei"
            pecas.append(base)
            continue

        base.paginas = len(paginas)
        base.de_onde["medida"] = "da arte"
        if (base.medida_no_nome and paginas[0][0]
                and not _mesmo_tamanho(base.medida_no_nome, paginas[0][0])
                and not _mesmo_tamanho(base.medida_no_nome, tuple(reversed(paginas[0][0])))):
            base.avisos.append("o nome diz %s e a arte mede %s — vale a arte"
                               % (formatar_medida(base.medida_no_nome), formatar_medida(paginas[0][0])))

        diferentes = len(paginas) > 1 and not all(_mesmo_tamanho(p[0], paginas[0][0]) for p in paginas)
        if diferentes:
            for i, (arte, sang, marca) in enumerate(paginas, start=1):
                p = dataclasses.replace(base, pagina=i, arte_m=arte, sangria_m=sang, marca=marca,
                                        avisos=list(base.avisos), de_onde=dict(base.de_onde))
                if i > 1:
                    p.descricao = "%s - PAGINA %d" % (base.descricao, i)
                p.avisos.append("página %d de %d do mesmo PDF (tamanhos diferentes: virou peça própria)"
                                % (i, len(paginas)))
                pecas.append(p)
            continue

        base.arte_m, base.sangria_m, base.marca = paginas[0]
        if len(paginas) > 1:
            base.avisos.append("%d páginas do mesmo tamanho — frente e verso? Dá pra separar."
                               % len(paginas))
        pecas.append(base)
    return pecas


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
    prefixo = _area_no_nome(area)
    if prefixo and not caderno_arte._sem_acento(descricao).upper().startswith(prefixo):
        descricao = "%s - %s" % (prefixo, descricao)
    sangria = None
    if peca.sangria_m and (peca.sangria_m[0] - peca.arte_m[0] > _SANGRIA_MINIMA_M
                           or peca.sangria_m[1] - peca.arte_m[1] > _SANGRIA_MINIMA_M):
        sangria = caderno_arte.medida_metros_para_nome(peca.sangria_m)
    extensao = ".pdf" if peca.pagina else "." + (peca.arquivo.ext.lower() or "pdf")
    return caderno_arte.montar_nome(peca.quantidade, peca.material,
                                    caderno_arte.medida_metros_para_nome(peca.arte_m),
                                    descricao, sangria) + extensao


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
