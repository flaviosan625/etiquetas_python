"""
Baixa a arte da pasta do cliente no Google Drive — SÓ o PDF.

Por que existe (2026-09-11): o caderno aponta, em cada peça, uma PASTA do
Drive (mockup + JPG de prévia + .ai de trabalho + o PDF). Baixar pelo
navegador traz a pasta inteira; a API deixa listar e pegar SÓ o
'application/pdf' — regra do usuário: "somente o PDF, não trazer junto
nada além desse material".

É a única parte do fluxo que precisa de credencial. Tudo depois dela
(identificar, tirar a marca, renomear, registrar) já roda sem nada disso,
em arte_recebida.py — quando este módulo entrega o PDF em '_entrada', o
resto acontece igual ao que já foi feito na mão.

ACESSO
Conta pessoal @gmail.com do Flávio, com quem as pastas são compartilhadas.
Escopo drive.readonly: lê metadados e baixa conteúdo, não escreve nada no
Drive de ninguém. A credencial (o JSON do Google Cloud) e o token ficam em
'.google/', que o .gitignore mantém fora do versionamento — são segredo,
não código.

O QUE NÃO FAZ
Não decide sozinho quando a pasta tem mais de um PDF, e não baixa nada que
não seja PDF. Pasta ambígua vira aviso pra decidir, nunca palpite.
"""
import pathlib
import re

PASTA_SEGREDOS = pathlib.Path(__file__).parent / ".google"
CAMINHO_CREDENCIAL = PASTA_SEGREDOS / "credenciais.json"
CAMINHO_TOKEN = PASTA_SEGREDOS / "token.json"

# Só leitura. Lê a ficha do arquivo e baixa o conteúdo; não cria, não
# apaga, não move nada no Drive. É o mínimo que o trabalho pede.
ESCOPOS = ["https://www.googleapis.com/auth/drive.readonly"]

MIME_PDF = "application/pdf"
# Pasta do Drive: pra distinguir link de pasta de link de arquivo solto.
MIME_PASTA = "application/vnd.google-apps.folder"


def id_do_link(link):
    """
    O id do Drive dentro de um link, seja ele qual for a forma:
    'open?id=X', '/folders/X', '/file/d/X/...' ou 'id=X&...'. None se não
    houver id reconhecível.
    """
    if not link:
        return None
    for padrao in (r"/folders/([\w-]{10,})",
                   r"/file/d/([\w-]{10,})",
                   r"[?&]id=([\w-]{10,})"):
        m = re.search(padrao, link)
        if m:
            return m.group(1)
    return None


def _fluxo_oauth():
    from google_auth_oauthlib.flow import InstalledAppFlow
    return InstalledAppFlow.from_client_secrets_file(str(CAMINHO_CREDENCIAL), ESCOPOS)


def autenticar(abrir_navegador=True):
    """
    Devolve credenciais válidas, guardando o token pra não pedir login de
    novo. Na primeira vez abre o navegador uma vez; depois renova sozinho
    com o refresh token.

    Levanta FileNotFoundError com instrução clara se a credencial ainda
    não foi baixada do Google Cloud — é o único passo manual do setup.
    """
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request

    if not CAMINHO_CREDENCIAL.is_file():
        raise FileNotFoundError(
            "Falta a credencial do Google em '%s'. Baixe o JSON do OAuth "
            "(Aplicativo para computador) no Google Cloud e salve com esse "
            "nome. Ver o passo a passo no topo de drive_artes." % CAMINHO_CREDENCIAL)

    credenciais = None
    if CAMINHO_TOKEN.is_file():
        credenciais = Credentials.from_authorized_user_file(str(CAMINHO_TOKEN), ESCOPOS)

    if not credenciais or not credenciais.valid:
        if credenciais and credenciais.expired and credenciais.refresh_token:
            credenciais.refresh(Request())
        elif abrir_navegador:
            credenciais = _fluxo_oauth().run_local_server(port=0)
        else:
            raise RuntimeError("token ausente ou expirado e abrir_navegador=False")
        PASTA_SEGREDOS.mkdir(parents=True, exist_ok=True)
        CAMINHO_TOKEN.write_text(credenciais.to_json(), encoding="utf-8")
    return credenciais


def servico(credenciais=None):
    from googleapiclient.discovery import build
    return build("drive", "v3", credentials=credenciais or autenticar(),
                 cache_discovery=False)


def _tipo_do_id(drive, id_drive):
    """'pasta', 'arquivo' ou None (não achou / sem acesso)."""
    try:
        info = drive.files().get(
            fileId=id_drive, fields="mimeType",
            supportsAllDrives=True).execute()
    except Exception:
        return None
    return "pasta" if info.get("mimeType") == MIME_PASTA else "arquivo"


def _e_pdf_de_entrega(arquivo):
    """
    Um .ai é PDF-compatível, e o Drive costuma reportá-lo com
    mimeType 'application/pdf' — então a consulta por mimeType traz o
    arquivo de trabalho do Illustrator junto do PDF de entrega, e a pasta
    parece ter "2 PDFs" (visto no Mercado Livre, 2026-09-12). O .ai não é o
    material que a gente pega ("somente o PDF"), então sai pela extensão.
    """
    nome = (arquivo.get("name") or "").lower()
    return not nome.endswith((".ai", ".eps", ".psd"))


def listar_pdfs(drive, id_pasta):
    """
    Os PDFs de ENTREGA de uma pasta do Drive (nome, id, tamanho, quando
    mudou). Ignora o que não é PDF e também o .ai/.eps/.psd que o Drive
    rotula como PDF. Paginado — pasta grande não trunca.
    """
    pdfs = []
    pagina = None
    consulta = "'%s' in parents and mimeType='%s' and trashed=false" % (id_pasta, MIME_PDF)
    while True:
        resposta = drive.files().list(
            q=consulta,
            fields="nextPageToken, files(id, name, size, modifiedTime, md5Checksum)",
            pageSize=100, supportsAllDrives=True, includeItemsFromAllDrives=True,
            pageToken=pagina).execute()
        pdfs.extend(a for a in resposta.get("files", []) if _e_pdf_de_entrega(a))
        pagina = resposta.get("nextPageToken")
        if not pagina:
            break
    return pdfs


def baixar_arquivo(drive, id_arquivo, destino):
    """
    Baixa um arquivo do Drive pro caminho 'destino', via arquivo temporário
    no mesmo lugar — nunca deixa um PDF pela metade com o nome final.
    Devolve o caminho salvo.
    """
    import io
    from googleapiclient.http import MediaIoBaseDownload

    destino = pathlib.Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    parcial = destino.with_name("~baixando~" + destino.name)

    pedido = drive.files().get_media(fileId=id_arquivo, supportsAllDrives=True)
    with open(parcial, "wb") as saida:
        baixador = MediaIoBaseDownload(saida, pedido)
        terminou = False
        while not terminou:
            _, terminou = baixador.next_chunk()
    import os
    os.replace(parcial, destino)
    return destino


def resolver_pdf_da_pasta(drive, link):
    """
    Do link do caderno até o único PDF que deve ser baixado.

    Devolve (arquivo, motivo):
      - (arquivo, None)      => achou um PDF só; é ele.
      - (None, "texto")      => nada, ou mais de um: o texto diz o quê.

    O link normalmente é uma pasta. Se por acaso apontar direto um PDF,
    também serve. Mais de um PDF na pasta não se escolhe no chute.
    """
    id_drive = id_do_link(link)
    if not id_drive:
        return None, "link sem id reconhecível: %s" % link

    tipo = _tipo_do_id(drive, id_drive)
    if tipo is None:
        return None, "não consegui abrir o id %s (sem acesso, ou não existe)" % id_drive
    if tipo == "arquivo":
        info = drive.files().get(fileId=id_drive, fields="id, name, mimeType, size, md5Checksum",
                                 supportsAllDrives=True).execute()
        if info.get("mimeType") != MIME_PDF:
            return None, "o link aponta um arquivo que não é PDF (%s)" % info.get("mimeType")
        return info, None

    pdfs = listar_pdfs(drive, id_drive)
    if not pdfs:
        return None, "a pasta não tem nenhum PDF"
    if len(pdfs) > 1:
        nomes = ", ".join(p["name"] for p in pdfs)
        return None, "a pasta tem %d PDFs (%s); me diga qual" % (len(pdfs), nomes)
    return pdfs[0], None


def baixar_arte_para_entrada(ficha, pasta_entrada, drive=None):
    """
    Baixa o PDF da peça pra '_entrada', de onde arte_recebida o processa.

    Devolve (caminho_ou_None, mensagem). Não baixa quando a pasta é
    ambígua — devolve o motivo pra decidir.
    """
    drive = drive or servico()
    links = ficha.get("links") or []
    if not links:
        return None, "a peça '%s' não tem link de pasta no caderno" % ficha.get("nome")

    arquivo, motivo = resolver_pdf_da_pasta(drive, links[0])
    if arquivo is None:
        return None, "peça '%s': %s" % (ficha.get("nome"), motivo)

    destino = pathlib.Path(pasta_entrada) / arquivo["name"]
    baixar_arquivo(drive, arquivo["id"], destino)
    return destino, "baixado '%s' (%s bytes)" % (arquivo["name"], arquivo.get("size", "?"))


# ---------------------------------------------------------------------
# Link que abre direto o slide da peça no caderno (Google Slides)
# ---------------------------------------------------------------------
import re as _re
import unicodedata as _ud


def _norm_etiqueta(texto):
    t = _ud.normalize("NFKD", str(texto or ""))
    t = "".join(c for c in t if not _ud.combining(c)).upper()
    return _re.sub(r"\s+", " ", _re.sub(r"[^A-Z0-9 ]+", " ", t)).strip()


def servico_slides(credenciais=None):
    from googleapiclient.discovery import build
    return build("slides", "v1", credentials=credenciais or autenticar(),
                 cache_discovery=False)


def mapa_slides_por_etiqueta(presentation_id, slides=None):
    """
    {etiqueta_do_link normalizada -> objectId do slide}, lido do caderno
    no Google Slides.

    A âncora é a etiqueta 'AF - ...' de cada peça, não a posição: o
    caderno tem slides copiados de decks diferentes, então a ordem do
    .pptx exportado não bate com a do Slides (só 65 de 154 alinham por
    posição; por etiqueta, 127 de 127 — conferido em 2026-09-11).
    """
    slides = slides or servico_slides()
    campos = ("slides(objectId,pageElements("
              "shape(text(textElements(textRun(content)))),"
              "table(tableRows(tableCells(text(textElements(textRun(content)))))))")
    pres = slides.presentations().get(
        presentationId=presentation_id, fields=campos + ")").execute()

    mapa = {}
    for slide in pres.get("slides", []):
        for etiqueta in _etiquetas_do_slide(slide):
            mapa.setdefault(etiqueta, slide["objectId"])
    return mapa


def _etiquetas_do_slide(slide):
    achadas = []

    def varrer(elementos):
        buffer = "".join(e.get("textRun", {}).get("content", "") for e in elementos)
        for linha in buffer.splitlines():
            if linha.strip().upper().startswith("AF"):
                achadas.append(_norm_etiqueta(linha))

    for pe in slide.get("pageElements", []):
        varrer(pe.get("shape", {}).get("text", {}).get("textElements", []))
        for row in pe.get("table", {}).get("tableRows", []):
            for cell in row.get("tableCells", []):
                varrer(cell.get("text", {}).get("textElements", []))
    return achadas


def link_do_slide(presentation_id, object_id):
    return ("https://docs.google.com/presentation/d/%s/edit#slide=id.%s"
            % (presentation_id, object_id))


def link_da_peca(ficha, presentation_id, mapa_etiquetas):
    """
    Link que abre direto o slide da peça. Cai no caderno inteiro quando a
    peça não tem etiqueta reconhecível — melhor o caderno que link quebrado.
    """
    etiqueta = _norm_etiqueta(ficha.get("etiqueta_link"))
    obj = mapa_etiquetas.get(etiqueta)
    if obj:
        return link_do_slide(presentation_id, obj)
    return "https://docs.google.com/presentation/d/%s/edit" % presentation_id
