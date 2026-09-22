"""
De onde as artes chegam — e o que tem lá dentro — ANTES de baixar.

Por que existe (2026-09-21): arte chega de todo jeito — link do Drive,
link do WeTransfer, pasta sincronizada do OneDrive, ZIP, pendrive — e
"organização de cada cliente vai ser diferente". O pedido do usuário foi
uma prévia onde ele "possa demarcar o que realmente quer que baixe", com
a miniatura de cada arte na primeira tela, sem limitar formato.

Cada origem responde às mesmas três perguntas, e a tela não precisa saber
de qual origem se trata:
    listar()            -> o que tem lá (nome, pasta, tamanho), sem baixar
    miniatura(arquivo)  -> a imagem pra prévia (bytes), ou None
    baixar(arquivo, ..) -> traz UM arquivo pra pasta de espera

O QUE SE DESCOBRIU SONDANDO (2026-09-21)
  - Drive: todo arquivo tem 'thumbnailLink' — miniatura pronta, gerada
    pelo Google. Uma pasta de 31,5 MB foi listada trazendo só 644 KB.
  - .ai salvo SEM compatibilidade PDF não tem prévia: a miniatura é o
    aviso "This is an Adobe Illustrator File that was saved without PDF
    Content". Nesse caso a prévia vem do PDF irmão (fonte_da_previa).
  - WeTransfer: a API pública deles é só de ENVIO, mas o site usa
    endereços próprios que respondem sem login (prepare-download dá a
    lista; download dá o endereço direto). O endereço direto aceita
    Range, e o índice de um ZIP mora no FIM dele: a lista de dentro de um
    ZIP de 28 MB saiu lendo 64 KB. O endereço não é oficial e pode mudar
    sem aviso — o plano B é baixar o ZIP no navegador e abrir como ZIP.

Nada aqui escreve fora da pasta de espera: baixar() nunca move o
original (pasta local é COPIADA), e arquivar é com receber_artes.
"""
import collections
import dataclasses
import datetime
import hashlib
import io
import os
import pathlib
import re
import shutil
import threading
import zipfile

import caminhos

# "Tudo que é arte vem marcado" (decisão do usuário, 2026-09-21). Cai a
# regra antiga "somente o PDF": todos os formatos que o sistema trabalha
# entram, e qualquer outro aparece na lista pra ele marcar se quiser.
EXT_ARTE = {"PDF", "AI", "EPS", "TIF", "TIFF", "PSD"}
EXT_IMAGEM = {"PNG", "JPG", "JPEG"}
EXT_DO_SISTEMA = EXT_ARTE | EXT_IMAGEM

# Arquivo que o sistema operacional ou o compactador cria sozinho.
_IGNORAR_NOMES = {"desktop.ini", "thumbs.db", ".ds_store"}
_IGNORAR_PREFIXOS = ("._", "~$", "~baixando~", "~montando~")
_IGNORAR_PASTAS = {"__macosx"}

# Prévia é pra olhar, não pra conferir: pequena de propósito.
MINIATURA_PX = 320
# Acima disto, gerar a prévia custaria mais que ela vale. Local: abrir um
# TIF de GB já travou o PyMuPDF por minutos (2026-08-31). Remoto: seria
# baixar o arquivo inteiro só pra olhar.
LIMITE_PREVIA_LOCAL = 300 * 1024 * 1024
LIMITE_PREVIA_REMOTA = 80 * 1024 * 1024
# Imagem aberta pelo Pillow sem modo rascunho: acima disto de pixels, não.
LIMITE_PREVIA_PIXELS = 150_000_000

# Arquivo na nuvem que o OneDrive ainda não trouxe pro disco. Ler o
# conteúdo dispara o download — pra prévia, não; só se ele marcar.
_ATRIBUTOS_SO_NA_NUVEM = 0x400000 | 0x40000 | 0x1000

_AVISO_AI_SEM_PDF = "saved without pdf content"

_NAVEGADOR = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/128.0 Safari/537.36")


class ErroOrigem(Exception):
    """Mensagem pronta pra tela: o que deu errado e o que fazer."""


@dataclasses.dataclass
class Arquivo:
    id: str                 # estável dentro da origem
    nome: str
    grupo: str = ""         # a pasta dentro da origem, "" = raiz
    bytes: int = 0
    modificado: str = ""    # "AAAA-MM-DD HH:MM"
    na_nuvem: bool = False  # OneDrive: só o marcador, sem o conteúdo no disco
    ref: object = None      # uso interno de cada origem

    @property
    def ext(self):
        return self.nome.rsplit(".", 1)[-1].upper() if "." in self.nome else ""

    @property
    def base(self):
        return self.nome.rsplit(".", 1)[0] if "." in self.nome else self.nome


# ----------------------------------------------------------------------
# O que cada arquivo É, olhando os vizinhos da mesma pasta
# ----------------------------------------------------------------------

def _mesma_arte(a, b):
    """
    Dois arquivos da mesma arte: mesmo nome sem extensão, ou um começando
    pelo outro — o Illustrator exporta a prévia como
    'X_9,5x4,5mArtboard 1.png' ao lado de 'X_9,5x4,5m.pdf'.
    """
    x, y = a.base.strip().lower(), b.base.strip().lower()
    return bool(x and y) and (x == y or x.startswith(y) or y.startswith(x))


def papel(arquivo, irmaos):
    """
    'arte'     -> é o que vai pra produção (ganha o nome do padrão)
    'trabalho' -> .ai de trabalho ao lado da arte final
    'previa'   -> imagem exportada ao lado da arte (mockup, Artboard)
    'outro'    -> formato que o sistema não trabalha

    O .ai só é 'trabalho' quando existe a arte final ao lado; sozinho, ele
    É a arte. Imagem idem: sozinha, um JPG pode ser a arte de impressão.
    """
    ext = arquivo.ext
    finais = [o for o in irmaos if o is not arquivo and o.ext in (EXT_ARTE - {"AI"})]
    if ext in EXT_ARTE - {"AI"}:
        return "arte"
    if ext == "AI":
        return "trabalho" if any(_mesma_arte(arquivo, o) for o in finais) else "arte"
    if ext in EXT_IMAGEM:
        vetores = [o for o in irmaos if o is not arquivo and o.ext in EXT_ARTE]
        return "previa" if any(_mesma_arte(arquivo, o) for o in vetores) else "arte"
    return "outro"


def marcado_por_padrao(arquivo, irmaos):
    """Tudo que é arte vem marcado, o .ai de trabalho junto (decisão de 21/09)."""
    return papel(arquivo, irmaos) in ("arte", "trabalho")


def fonte_da_previa(arquivo, irmaos):
    """
    De qual arquivo mostrar a miniatura. Devolve (arquivo, emprestada).

    O .ai dos clientes costuma vir salvo sem compatibilidade PDF, e aí a
    miniatura dele é o aviso do Illustrator em vez da arte (visto em todos
    os .ai do Mercado Livre). Tendo um PDF ou imagem da mesma arte ao lado,
    a prévia vem de lá — e a tela avisa que é emprestada.
    """
    if arquivo.ext == "AI":
        preferencia = ("PDF", "PNG", "JPG", "JPEG", "TIF", "TIFF", "PSD")
        irmas = sorted((o for o in irmaos if o is not arquivo and o.ext in preferencia
                        and _mesma_arte(arquivo, o)),
                       key=lambda o: preferencia.index(o.ext))
        if irmas:
            return irmas[0], True
    return arquivo, False


def agrupar(arquivos):
    """{grupo: [arquivos]} na ordem em que aparecem."""
    grupos = collections.OrderedDict()
    for a in arquivos:
        grupos.setdefault(a.grupo, []).append(a)
    return grupos


def _ignorar(nome):
    n = nome.lower()
    return n in _IGNORAR_NOMES or n.startswith(_IGNORAR_PREFIXOS)


# ----------------------------------------------------------------------
# Miniatura a partir do conteúdo (origens locais e ZIP)
# ----------------------------------------------------------------------

def _png(imagem):
    buf = io.BytesIO()
    imagem.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def _miniatura(fonte, nome, px):
    """
    'fonte' é um caminho (abre direto do disco, sem trazer tudo pra
    memória) ou bytes (o que veio de dentro de um ZIP).
    """
    ext = nome.rsplit(".", 1)[-1].upper() if "." in nome else ""
    em_bytes = isinstance(fonte, (bytes, bytearray))
    try:
        if ext in ("PDF", "AI"):
            import pymupdf
            doc = pymupdf.open(stream=fonte, filetype="pdf") if em_bytes else pymupdf.open(str(fonte))
            with doc:
                pagina = doc[0]
                # o aviso vem quebrado em linhas: compara com os espaços juntados
                if _AVISO_AI_SEM_PDF in " ".join(pagina.get_text().split()).lower():
                    return None
                escala = px / max(pagina.rect.width, pagina.rect.height)
                return pagina.get_pixmap(matrix=pymupdf.Matrix(escala, escala)).tobytes("png")
        if ext in EXT_IMAGEM | {"TIF", "TIFF", "PSD"}:
            from PIL import Image
            with Image.open(io.BytesIO(fonte) if em_bytes else str(fonte)) as img:
                if img.format == "JPEG":
                    img.draft("RGB", (px, px))   # decodifica já reduzido: barato
                elif img.width * img.height > LIMITE_PREVIA_PIXELS:
                    return None
                reduzida = img.convert("RGB")
            reduzida.thumbnail((px, px))
            return _png(reduzida)
    except Exception:
        return None
    return None


def miniatura_de_conteudo(dados, nome, px=MINIATURA_PX):
    """
    Miniatura (PNG, bytes) de um arquivo que já está na memória. None
    quando o formato não tem prévia (EPS) ou quando é um .ai salvo sem PDF
    — nesse caso a tela usa a do irmão (fonte_da_previa).
    """
    return _miniatura(dados, nome, px)


def miniatura_da_pagina(caminho, indice, px=MINIATURA_PX):
    """Miniatura de uma página qualquer de um PDF — a peça que saiu da página 2."""
    try:
        import pymupdf
        with pymupdf.open(str(caminho)) as doc:
            pagina = doc[indice]
            escala = px / max(pagina.rect.width, pagina.rect.height)
            return pagina.get_pixmap(matrix=pymupdf.Matrix(escala, escala)).tobytes("png")
    except Exception:
        return None


def miniatura_de_caminho(caminho, px=MINIATURA_PX):
    caminho = pathlib.Path(caminho)
    try:
        st = caminho.stat()
    except OSError:
        return None
    if st.st_size > LIMITE_PREVIA_LOCAL:
        return None
    if getattr(st, "st_file_attributes", 0) & _ATRIBUTOS_SO_NA_NUVEM:
        return None
    return _miniatura(caminho, caminho.name, px)


# ----------------------------------------------------------------------
# Um "arquivo" que mora na internet e se lê em pedaços
# ----------------------------------------------------------------------

class ArquivoHttp(io.RawIOBase):
    """
    Arquivo remoto que se lê por pedaço (HTTP Range), com cara de arquivo
    do disco: seek, tell, read. É o que deixa o zipfile do próprio Python
    abrir um ZIP que está no WeTransfer — ele pula pro fim, lê o índice e
    depois só o arquivo pedido, sem trazer o resto.

    'obter_url(renovar)' devolve o endereço; o do WeTransfer tem token que
    vence, e o 403 pede um novo uma vez antes de desistir.
    """
    BLOCO = 256 * 1024

    def __init__(self, obter_url, tamanho, sessao, max_blocos=64):
        super().__init__()
        self._obter_url = obter_url
        self._url = obter_url(False)
        self._tamanho = int(tamanho)
        self._sessao = sessao
        self._pos = 0
        self._blocos = collections.OrderedDict()
        self._max_blocos = max_blocos
        self._trava = threading.Lock()

    def readable(self):
        return True

    def seekable(self):
        return True

    def tell(self):
        return self._pos

    def seek(self, deslocamento, de_onde=io.SEEK_SET):
        if de_onde == io.SEEK_SET:
            novo = deslocamento
        elif de_onde == io.SEEK_CUR:
            novo = self._pos + deslocamento
        else:
            novo = self._tamanho + deslocamento
        if novo < 0:
            raise ValueError("posição negativa")
        self._pos = novo
        return self._pos

    def _pedaco(self, inicio, fim):
        """Bytes [inicio, fim) do servidor."""
        for tentativa in (0, 1):
            r = self._sessao.get(self._url, headers={"Range": "bytes=%d-%d" % (inicio, fim - 1)},
                                 timeout=120)
            if r.status_code in (401, 403, 410) and tentativa == 0:
                self._url = self._obter_url(True)
                continue
            if r.status_code != 206:
                raise OSError("o servidor não entregou o pedaço pedido (HTTP %s)" % r.status_code)
            return r.content
        raise OSError("o endereço de download venceu e não renovou")

    def _bloco(self, n):
        if n in self._blocos:
            self._blocos.move_to_end(n)
            return self._blocos[n]
        inicio = n * self.BLOCO
        dados = self._pedaco(inicio, min(inicio + self.BLOCO, self._tamanho))
        self._blocos[n] = dados
        while len(self._blocos) > self._max_blocos:
            self._blocos.popitem(last=False)
        return dados

    def readinto(self, destino):
        with self._trava:
            quer = len(destino)
            if quer == 0 or self._pos >= self._tamanho:
                return 0
            fim = min(self._pos + quer, self._tamanho)
            if fim - self._pos > self.BLOCO:
                # pedaço grande (o arquivo de dentro do ZIP): vai direto,
                # sem encher o cache de blocos que não se relê
                dados = self._pedaco(self._pos, fim)
            else:
                partes = []
                pos = self._pos
                while pos < fim:
                    n = pos // self.BLOCO
                    bloco = self._bloco(n)
                    ini = pos - n * self.BLOCO
                    pega = bloco[ini:ini + (fim - pos)]
                    partes.append(pega)
                    pos += len(pega)
                    if not pega:
                        break
                dados = b"".join(partes)
            destino[:len(dados)] = dados
            self._pos += len(dados)
            return len(dados)


# ----------------------------------------------------------------------
# ZIP (local ou remoto): o que tem dentro
# ----------------------------------------------------------------------

def _nome_no_zip(info):
    """
    Nome como o autor escreveu. ZIP sem a marca de UTF-8 vem decodificado
    como cp437 pelo Python — e "PRAÇA" vira "PRAÃ\x87A". Quase todo ZIP
    brasileiro sem a marca foi escrito em UTF-8 ou cp850: tenta os dois.
    """
    if info.flag_bits & 0x800:
        return info.filename
    bruto = info.filename.encode("cp437")
    for cod in ("utf-8", "cp850"):
        try:
            return bruto.decode(cod)
        except UnicodeDecodeError:
            continue
    return info.filename


def arquivos_do_zip(z, prefixo_id="", ref=lambda info: info):
    saida = []
    for info in z.infolist():
        if info.is_dir():
            continue
        caminho = _nome_no_zip(info).replace("\\", "/")
        partes = [p for p in caminho.split("/") if p]
        if not partes or any(p.lower() in _IGNORAR_PASTAS for p in partes[:-1]) or _ignorar(partes[-1]):
            continue
        quando = "%04d-%02d-%02d %02d:%02d" % info.date_time[:5]
        saida.append(Arquivo(id=prefixo_id + caminho, nome=partes[-1], grupo=" / ".join(partes[:-1]),
                             bytes=info.file_size, modificado=quando, ref=ref(info)))
    return saida


def _gravar_atomico(destino, escrever):
    """Monta em '~baixando~<nome>' e só entra com o nome final no fim."""
    destino = pathlib.Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    parcial = destino.with_name("~baixando~" + destino.name)
    try:
        with open(parcial, "wb") as f:
            escrever(f)
        os.replace(parcial, destino)
    except BaseException:
        parcial.unlink(missing_ok=True)
        raise
    return destino


def _copiar_de(abrir_origem):
    """Escritor pra _gravar_atomico que abre a origem e fecha no fim."""
    def escrever(saida):
        with abrir_origem() as entrada:
            shutil.copyfileobj(entrada, saida, 1024 * 1024)
    return escrever


def _iso_local(iso):
    """'2026-09-19T17:02:11.000Z' -> '2026-09-19 14:02' no fuso deste PC."""
    if not iso:
        return ""
    try:
        quando = datetime.datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return quando.astimezone().strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return iso[:16].replace("T", " ")


def _destino_na_espera(pasta, arquivo):
    """A pasta de espera espelha as pastas da origem: dois 'arte.pdf' não se atropelam."""
    partes = [re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", p).strip(" .") or "_"
              for p in arquivo.grupo.split(" / ") if p]
    return pathlib.Path(pasta).joinpath(*partes, arquivo.nome)


# ----------------------------------------------------------------------
# As origens
# ----------------------------------------------------------------------

class Origem:
    tipo = ""

    def __init__(self):
        self.rotulo = ""          # o que a tela mostra como "de onde"
        self.area_sugerida = ""   # nome da pasta, quando faz sentido como área
        self.id_origem = ""
        self.ignorados = []       # (nome, motivo) do que ficou de fora da lista
        self.aviso = ""           # algo que ele precisa saber (validade, etc.)

    def listar(self):
        raise NotImplementedError

    def miniatura(self, arquivo):
        return None

    def baixar(self, arquivo, pasta_espera):
        raise NotImplementedError

    def chave(self, arquivo):
        """Chave de 'já baixei isto' no registro — não depende de slide de caderno."""
        return "%s|%s|%s" % (self.tipo, self.id_origem, arquivo.id)

    def pacote_original(self):
        """(nome, bytes) do que chegou, quando a origem é descartável. [] quando não é."""
        return []

    def guardar_original(self, pasta):
        """Guarda o que chegou, como chegou. Devolve os caminhos gravados."""
        return []

    def fechar(self):
        pass


class OrigemPasta(Origem):
    """Pasta no computador: OneDrive sincronizado, pendrive, download manual."""
    tipo = "pasta"
    LIMITE_ARQUIVOS = 5000

    def __init__(self, pasta):
        super().__init__()
        self.raiz = pathlib.Path(pasta)
        if not self.raiz.is_dir():
            raise ErroOrigem("Não achei a pasta '%s'." % pasta)
        self.id_origem = str(self.raiz.resolve())
        self.rotulo = str(self.raiz)
        # Sem área sugerida, de propósito: pasta local costuma se chamar
        # "Downloads" ou "arte do cliente", e a área vai na frente de TODO
        # nome de arquivo — sugestão errada que passa despercebida custa
        # caro (visto no teste de 21/09). No Drive a pasta É a área do
        # cliente (LANDMARK), e lá a sugestão fica.
        self.area_sugerida = ""

    def listar(self):
        saida = []
        for raiz, pastas, nomes in os.walk(self.raiz):
            pastas[:] = sorted(p for p in pastas
                               if p.lower() not in _IGNORAR_PASTAS and not p.startswith((".", "_")))
            rel = pathlib.Path(raiz).relative_to(self.raiz)
            grupo = " / ".join(rel.parts)
            for nome in sorted(nomes):
                if _ignorar(nome):
                    continue
                caminho = pathlib.Path(raiz) / nome
                try:
                    st = caminho.stat()
                except OSError:
                    continue
                saida.append(Arquivo(
                    id=(rel / nome).as_posix(), nome=nome, grupo=grupo, bytes=st.st_size,
                    modificado=datetime.datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M"),
                    na_nuvem=bool(getattr(st, "st_file_attributes", 0) & _ATRIBUTOS_SO_NA_NUVEM),
                    ref=caminho))
                if len(saida) >= self.LIMITE_ARQUIVOS:
                    self.aviso = ("A pasta tem mais de %d arquivos — mostrei os primeiros. "
                                  "Escolha uma pasta mais de dentro." % self.LIMITE_ARQUIVOS)
                    return saida
        return saida

    def miniatura(self, arquivo):
        return miniatura_de_caminho(arquivo.ref)

    def baixar(self, arquivo, pasta_espera):
        # CÓPIA: o original fica onde está, como na tela de envio.
        destino = _destino_na_espera(pasta_espera, arquivo)
        return _gravar_atomico(destino, _copiar_de(lambda: open(arquivo.ref, "rb")))


class OrigemZip(Origem):
    """ZIP no computador — inclusive o do WeTransfer baixado pelo navegador."""
    tipo = "zip"

    def __init__(self, caminho):
        super().__init__()
        self.caminho = pathlib.Path(caminho)
        try:
            self.zip = zipfile.ZipFile(self.caminho)
        except (zipfile.BadZipFile, OSError) as e:
            raise ErroOrigem("'%s' não abriu como ZIP: %s" % (self.caminho.name, e))
        self.id_origem = self.caminho.name
        self.rotulo = "ZIP  ·  %s" % self.caminho.name

    def listar(self):
        return arquivos_do_zip(self.zip)

    def miniatura(self, arquivo):
        if arquivo.bytes > LIMITE_PREVIA_LOCAL:
            return None
        try:
            return miniatura_de_conteudo(self.zip.read(arquivo.ref), arquivo.nome)
        except Exception:
            return None

    def baixar(self, arquivo, pasta_espera):
        destino = _destino_na_espera(pasta_espera, arquivo)
        return _gravar_atomico(destino, _copiar_de(lambda: self.zip.open(arquivo.ref)))

    def guardar_original(self, pasta):
        destino = pathlib.Path(pasta) / self.caminho.name
        if destino.exists():
            return [destino]
        return [_gravar_atomico(destino, _copiar_de(lambda: open(self.caminho, "rb")))]

    def fechar(self):
        self.zip.close()


class OrigemDrive(Origem):
    """
    Link de pasta (ou de arquivo) do Google Drive. Lê a árvore inteira e a
    miniatura que o próprio Google gera, sem baixar arte nenhuma.
    'servico' e 'buscar' existem pro teste poder passar dublês.
    """
    tipo = "drive"
    PROFUNDIDADE = 8
    LIMITE_ARQUIVOS = 3000

    def __init__(self, link, servico=None, buscar=None):
        super().__init__()
        import drive_artes
        self._drive_artes = drive_artes
        self.id_origem = drive_artes.id_do_link(link)
        if not self.id_origem:
            raise ErroOrigem("Não achei o id da pasta nesse link do Drive.")
        if servico is None or buscar is None:
            cred = drive_artes.autenticar()
            servico = servico or drive_artes.servico(cred)
            if buscar is None:
                from google.auth.transport.requests import AuthorizedSession
                sessao = AuthorizedSession(cred)

                def buscar(url):
                    r = sessao.get(url, timeout=40)
                    r.raise_for_status()
                    return r.content
        self.drive = servico
        self._buscar = buscar

    _CAMPOS = "id,name,mimeType,size,modifiedTime,thumbnailLink,parents"

    def _filhos(self, id_pasta):
        itens, pagina = [], None
        while True:
            r = self.drive.files().list(
                q="'%s' in parents and trashed=false" % id_pasta,
                fields="nextPageToken, files(%s)" % self._CAMPOS,
                pageSize=200, supportsAllDrives=True, includeItemsFromAllDrives=True,
                pageToken=pagina).execute()
            itens.extend(r.get("files", []))
            pagina = r.get("nextPageToken")
            if not pagina:
                return itens

    def _caminho_acima(self, pais):
        partes, atual = [], (pais or [None])[0]
        for _ in range(6):
            if not atual:
                break
            try:
                d = self.drive.files().get(fileId=atual, fields="name,parents",
                                           supportsAllDrives=True).execute()
            except Exception:
                break   # pasta de cima não compartilhada com ele: para aqui
            partes.append(d["name"])
            atual = (d.get("parents") or [None])[0]
        return list(reversed(partes))

    def _arquivo(self, f, grupo):
        mime = f.get("mimeType", "")
        if mime.startswith("application/vnd.google-apps."):
            self.ignorados.append((f.get("name"), "documento do Google, não é arquivo de arte"))
            return None
        return Arquivo(id=f["id"], nome=f.get("name") or f["id"], grupo=grupo,
                       bytes=int(f.get("size") or 0), modificado=_iso_local(f.get("modifiedTime")), ref=f)

    def listar(self):
        try:
            raiz = self.drive.files().get(fileId=self.id_origem, fields=self._CAMPOS,
                                          supportsAllDrives=True).execute()
        except Exception as e:
            raise ErroOrigem("Não consegui abrir esse link do Drive (sem acesso, ou não existe): %s" % e)
        acima = self._caminho_acima(raiz.get("parents"))
        self.rotulo = " > ".join(acima + [raiz.get("name", "")])
        if raiz.get("mimeType") != self._drive_artes.MIME_PASTA:
            a = self._arquivo(raiz, "")
            return [a] if a else []

        self.area_sugerida = raiz.get("name", "")
        saida = []
        fila = collections.deque([(self.id_origem, [], 0)])
        while fila:
            id_pasta, caminho, nivel = fila.popleft()
            for f in sorted(self._filhos(id_pasta), key=lambda x: x.get("name", "").lower()):
                if f.get("mimeType") == self._drive_artes.MIME_PASTA:
                    if nivel + 1 <= self.PROFUNDIDADE:
                        fila.append((f["id"], caminho + [f.get("name", "")], nivel + 1))
                    continue
                if _ignorar(f.get("name", "")):
                    continue
                a = self._arquivo(f, " / ".join(caminho))
                if a:
                    saida.append(a)
                if len(saida) >= self.LIMITE_ARQUIVOS:
                    self.aviso = "A pasta tem mais de %d arquivos — mostrei os primeiros." % self.LIMITE_ARQUIVOS
                    return saida
        return saida

    def miniatura(self, arquivo):
        link = (arquivo.ref or {}).get("thumbnailLink")
        if not link:
            return None
        try:
            return self._buscar(re.sub(r"=s\d+$", "=s%d" % MINIATURA_PX, link))
        except Exception:
            return None

    def baixar(self, arquivo, pasta_espera):
        destino = _destino_na_espera(pasta_espera, arquivo)
        return self._drive_artes.baixar_arquivo(self.drive, arquivo.id, destino)


class OrigemWeTransfer(Origem):
    """
    Link do WeTransfer (we.tl/... ou wetransfer.com/downloads/...).

    ZIP dentro do transfer é aberto por dentro sem baixar (ArquivoHttp), e
    cada arquivo de dentro vira um item da lista. Pedaço trazido pra gerar
    miniatura fica guardado na espera, pra não baixar duas vezes quando
    ele marcar.
    """
    tipo = "wetransfer"
    _API = "https://wetransfer.com/api/v4/transfers/%s/%s"

    def __init__(self, link, sessao=None, pasta_cache=None):
        super().__init__()
        self.link = link.strip()
        if sessao is None:
            import requests
            sessao = requests.Session()
            sessao.headers["User-Agent"] = _NAVEGADOR
        self.sessao = sessao
        self._cache = pathlib.Path(pasta_cache) if pasta_cache else None
        self._links = {}
        self._zips = {}
        self._itens = {}
        self.info = {}

    def _resolver(self):
        try:
            r = self.sessao.get(self.link, allow_redirects=True, timeout=30)
        except Exception as e:
            raise ErroOrigem("Não consegui abrir o link do WeTransfer: %s" % e)
        m = re.search(r"/downloads/([0-9a-f]+)/(?:([0-9a-f]+)/)?([0-9a-f]+)", r.url)
        if not m:
            raise ErroOrigem("Esse link do WeTransfer não abriu num transfer — pode ter expirado "
                             "ou sido apagado.")
        self.transfer_id, self.recipient_id, self.security_hash = m.groups()
        self.id_origem = self.transfer_id
        self._cabecalho = {"x-requested-with": "XMLHttpRequest", "Content-Type": "application/json",
                           "Origin": "https://wetransfer.com", "Referer": r.url}

    def _post(self, acao, corpo):
        corpo = dict(corpo, security_hash=self.security_hash)
        if self.recipient_id:
            corpo["recipient_id"] = self.recipient_id
        r = self.sessao.post(self._API % (self.transfer_id, acao), json=corpo,
                             headers=self._cabecalho, timeout=30)
        if r.status_code in (404, 410):
            raise ErroOrigem("O WeTransfer diz que esse transfer não existe mais (expirou ou foi apagado).")
        if r.status_code >= 400:
            raise ErroOrigem("O WeTransfer recusou o pedido (HTTP %s). Se o site mudou, baixe o ZIP "
                             "pelo navegador e abra como ZIP." % r.status_code)
        return r.json()

    def listar(self):
        self._resolver()
        info = self._post("prepare-download", {})
        self.info = info
        if info.get("password_protected"):
            raise ErroOrigem("Esse transfer tem SENHA. Baixe pelo navegador e abra o ZIP aqui.")
        if info.get("state") not in (None, "downloadable"):
            raise ErroOrigem("Esse transfer não está disponível pra baixar (estado: %s)." % info.get("state"))
        expira = info.get("expires_at") or ""
        quando = _data_local(expira)
        nome = info.get("display_name") or info.get("recommended_filename") or "transfer"
        self.rotulo = "WeTransfer  ·  %s" % nome + ("  ·  expira %s" % quando if quando else "")
        if quando:
            self.aviso = ("O link do WeTransfer expira em %s. Depois disso o original só existe "
                          "no que for guardado aqui." % quando)

        saida = []
        for item in info.get("items") or []:
            self._itens[item["id"]] = item
            nome_item = (item.get("name") or item["id"]).replace("\\", "/")
            if nome_item.lower().endswith(".zip"):
                try:
                    z = self._zip(item)
                    saida.extend(arquivos_do_zip(
                        z, prefixo_id=item["id"] + "/",
                        ref=lambda info, i=item["id"]: ("zip", i, info)))
                    continue
                except Exception:
                    pass   # ZIP que não abriu por dentro entra como arquivo solto
            partes = [p for p in nome_item.split("/") if p]
            saida.append(Arquivo(id=item["id"], nome=partes[-1], grupo=" / ".join(partes[:-1]),
                                 bytes=int(item.get("size") or 0), ref=("item", item["id"], None)))
        return saida

    def _link_direto(self, item_id, renovar=False):
        if renovar or item_id not in self._links:
            dados = self._post("download", {"intent": "single_file", "file_ids": [item_id]})
            if not dados.get("direct_link"):
                raise ErroOrigem("O WeTransfer não devolveu o endereço de download.")
            self._links[item_id] = dados["direct_link"]
        return self._links[item_id]

    def _zip(self, item):
        if item["id"] not in self._zips:
            fonte = ArquivoHttp(lambda renovar, i=item["id"]: self._link_direto(i, renovar),
                                int(item.get("size") or 0), self.sessao)
            self._zips[item["id"]] = zipfile.ZipFile(fonte)
        return self._zips[item["id"]]

    def _no_cache(self, arquivo):
        if not self._cache:
            return None
        return self._cache / hashlib.sha1(arquivo.id.encode("utf-8")).hexdigest()

    def _conteudo(self, arquivo):
        """Todos os bytes do arquivo — do cache, ou trazidos agora e guardados."""
        cache = self._no_cache(arquivo)
        if cache and cache.is_file():
            return cache.read_bytes()
        tipo, item_id, info = arquivo.ref
        if tipo == "zip":
            dados = self._zips[item_id].read(info)
        else:
            r = self.sessao.get(self._link_direto(item_id), timeout=300)
            r.raise_for_status()
            dados = r.content
        if cache:
            _gravar_atomico(cache, lambda f: f.write(dados))
        return dados

    def miniatura(self, arquivo):
        if arquivo.bytes > LIMITE_PREVIA_REMOTA:
            return None
        try:
            return miniatura_de_conteudo(self._conteudo(arquivo), arquivo.nome)
        except Exception:
            return None

    def baixar(self, arquivo, pasta_espera):
        destino = _destino_na_espera(pasta_espera, arquivo)
        cache = self._no_cache(arquivo)
        if cache and cache.is_file():
            return _gravar_atomico(destino, _copiar_de(lambda: open(cache, "rb")))
        tipo, item_id, info = arquivo.ref
        if tipo == "zip":
            return _gravar_atomico(destino, _copiar_de(lambda: self._zips[item_id].open(info)))
        return _gravar_atomico(destino, lambda f: self._baixar_item(item_id, f))

    def _baixar_item(self, item_id, saida):
        for tentativa in (0, 1):
            with self.sessao.get(self._link_direto(item_id, renovar=tentativa == 1),
                                 stream=True, timeout=300) as r:
                if r.status_code in (401, 403, 410) and tentativa == 0:
                    continue
                r.raise_for_status()
                for bloco in r.iter_content(1024 * 1024):
                    saida.write(bloco)
                return

    def guardar_original(self, pasta):
        """O transfer inteiro, como chegou: o link morre em dias."""
        gravados = []
        for item_id, item in self._itens.items():
            nome = (item.get("name") or item_id).replace("\\", "/").split("/")[-1]
            destino = pathlib.Path(pasta) / nome
            if destino.exists() and destino.stat().st_size == int(item.get("size") or -1):
                gravados.append(destino)
                continue
            gravados.append(_gravar_atomico(destino, lambda f, i=item_id: self._baixar_item(i, f)))
        return gravados

    def fechar(self):
        for z in self._zips.values():
            try:
                z.close()
            except Exception:
                pass


def _data_local(iso):
    """'2026-09-24T13:09:43Z' -> '24/09 10:09' no fuso deste PC."""
    if not iso:
        return ""
    try:
        quando = datetime.datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return quando.astimezone().strftime("%d/%m %H:%M")
    except ValueError:
        return ""


# ----------------------------------------------------------------------
# Qual origem é, pelo que ele colou
# ----------------------------------------------------------------------

def abrir(texto, pasta_espera=None):
    """
    A origem certa pro que ele colou ou escolheu: link do Drive, link do
    WeTransfer, pasta ou ZIP. Levanta ErroOrigem com o que fazer quando
    não reconhece.
    """
    t = (texto or "").strip().strip('"').strip()
    if not t:
        raise ErroOrigem("Cole um link ou escolha uma pasta ou ZIP.")
    if re.match(r"https?://", t, re.I):
        baixo = t.lower()
        if "drive.google.com" in baixo or "docs.google.com" in baixo:
            return OrigemDrive(t)
        if "we.tl/" in baixo or "wetransfer.com" in baixo:
            return OrigemWeTransfer(t, pasta_cache=pathlib.Path(pasta_espera) / "_cache" if pasta_espera else None)
        if "1drv.ms" in baixo or "onedrive" in baixo or "sharepoint.com" in baixo:
            raise ErroOrigem("Link compartilhado do OneDrive ainda não é lido direto. Se a pasta está "
                             "sincronizada no seu OneDrive, clique em 'Pasta ou ZIP...' e escolha ela.")
        raise ErroOrigem("Não sei ler esse link. Funciona: Google Drive, WeTransfer, ou uma pasta/ZIP "
                         "no computador.")
    caminho = pathlib.Path(t)
    if caminho.is_dir():
        return OrigemPasta(caminho)
    if caminho.is_file() and caminho.suffix.lower() == ".zip":
        return OrigemZip(caminho)
    if caminho.is_file():
        raise ErroOrigem("Escolha a PASTA onde o arquivo está (ou um ZIP), não o arquivo sozinho.")
    raise ErroOrigem("Não achei '%s'." % t)


# ----------------------------------------------------------------------
# A pasta de espera
# ----------------------------------------------------------------------

DIAS_NA_ESPERA = 7


def novo_lote(agora=None):
    """Uma pasta de espera por leitura de origem, com a hora no nome."""
    agora = agora or datetime.datetime.now()
    pasta = caminhos.PASTA_RECEBENDO / agora.strftime("%Y-%m-%d %H%M%S")
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta


def limpar_lotes_velhos(dias=DIAS_NA_ESPERA, agora=None):
    """
    Apaga lote de espera com mais de 'dias'. Só dentro de PASTA_RECEBENDO,
    e só pasta cujo nome é uma data de lote — nunca outra coisa.
    """
    raiz = caminhos.PASTA_RECEBENDO
    if not raiz.is_dir():
        return []
    agora = agora or datetime.datetime.now()
    apagados = []
    for pasta in raiz.iterdir():
        try:
            quando = datetime.datetime.strptime(pasta.name, "%Y-%m-%d %H%M%S")
        except ValueError:
            continue
        if pasta.is_dir() and agora - quando > datetime.timedelta(days=dias):
            shutil.rmtree(pasta, ignore_errors=True)
            apagados.append(pasta)
    return apagados
