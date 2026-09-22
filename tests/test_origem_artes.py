"""
De onde as artes chegam (origem_artes): o que cada origem lista, a prévia,
o download pra espera, e as regras de o que vem marcado.

Nenhum teste toca a internet nem pasta real: Drive e WeTransfer são
dublês, e a pasta de espera aponta pra tmp_path. Se algum teste tentar
autenticar no Google de verdade, a fixture derruba ele na hora.
"""
import datetime
import hashlib
import io
import json
import pathlib
import re
import sys
import zipfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import pymupdf
import pytest

import caminhos
import drive_artes
import origem_artes as oa


@pytest.fixture(autouse=True)
def nada_real(tmp_path, monkeypatch):
    monkeypatch.setattr(caminhos, "PASTA_RECEBENDO", tmp_path / "recebendo")
    monkeypatch.setattr(caminhos, "RECEBIMENTO_DE_ARTES", tmp_path / "Recebimento de Artes")

    def proibido(*a, **k):
        raise AssertionError("teste tentou autenticar no Google de verdade")
    monkeypatch.setattr(drive_artes, "autenticar", proibido)


def _pdf(caminho, texto="ARTE", largura=400, altura=200):
    doc = pymupdf.open()
    pg = doc.new_page(width=largura, height=altura)
    pg.insert_text((20, 40), texto, fontsize=20)
    caminho = pathlib.Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(caminho))
    doc.close()
    return caminho


def _pdf_bytes(texto="ARTE"):
    doc = pymupdf.open()
    doc.new_page(width=300, height=150).insert_text((20, 40), texto, fontsize=18)
    dados = doc.tobytes()
    doc.close()
    return dados


def _a(nome, grupo=""):
    return oa.Arquivo(id=nome, nome=nome, grupo=grupo)


# ================================================== o que cada arquivo É

def test_pasta_do_mercado_livre_pdf_e_arte_ai_e_trabalho_png_e_previa():
    """Cada pasta de peça do ML trazia os três — e só o PDF é a arte final."""
    pdf = _a("AF_LANDMARK_PAINEL_9,5x4,5m.pdf")
    ai = _a("AF_LANDMARK_PAINEL_9,5x4,5m.ai")
    png = _a("AF_LANDMARK_PAINEL_9,5x4,5mArtboard 1.png")
    irmaos = [pdf, ai, png]

    assert oa.papel(pdf, irmaos) == "arte"
    assert oa.papel(ai, irmaos) == "trabalho"
    assert oa.papel(png, irmaos) == "previa"


def test_vem_marcado_tudo_que_e_arte_e_o_ai_junto_mas_nao_a_previa():
    """Decisão de 21/09: 'tudo que é arte' marcado; mockup/Artboard desmarcado."""
    pdf, ai, png = _a("X.pdf"), _a("X.ai"), _a("XArtboard 1.png")
    irmaos = [pdf, ai, png]

    assert [oa.marcado_por_padrao(a, irmaos) for a in irmaos] == [True, True, False]


def test_ai_sozinho_e_a_propria_arte():
    ai = _a("LOGO.ai")
    assert oa.papel(ai, [ai]) == "arte"


def test_jpg_sozinho_e_arte_e_vem_marcado():
    """Cliente que manda a arte só em JPG não pode ter ela desmarcada."""
    jpg = _a("BACKDROP.jpg")
    assert oa.papel(jpg, [jpg]) == "arte"
    assert oa.marcado_por_padrao(jpg, [jpg])


def test_formato_que_o_sistema_nao_trabalha_aparece_mas_desmarcado():
    doc = _a("briefing.docx")
    assert oa.papel(doc, [doc]) == "outro"
    assert not oa.marcado_por_padrao(doc, [doc])


def test_previa_do_ai_vem_emprestada_do_pdf_irmao():
    """O .ai salvo sem PDF só mostraria o aviso do Illustrator."""
    pdf, ai = _a("X.pdf"), _a("X.ai")

    fonte, emprestada = oa.fonte_da_previa(ai, [pdf, ai])

    assert fonte is pdf and emprestada


def test_ai_sem_irmao_mostra_a_propria_previa():
    ai = _a("X.ai")
    assert oa.fonte_da_previa(ai, [ai]) == (ai, False)


def test_arte_de_outra_peca_nao_vira_irma():
    """'PAINEL VERSO' não é versão de 'PAINEL FRENTE' só por estar na mesma pasta."""
    frente, verso_ai = _a("PAINEL FRENTE.pdf"), _a("PAINEL VERSO.ai")
    assert oa.papel(verso_ai, [frente, verso_ai]) == "arte"


# ================================================================ prévia

def test_miniatura_de_pdf_sai_em_png(tmp_path):
    dados = oa.miniatura_de_caminho(_pdf(tmp_path / "a.pdf"))
    assert dados and dados[:8] == b"\x89PNG\r\n\x1a\n"


def test_ai_salvo_sem_pdf_nao_tem_miniatura(tmp_path):
    """
    É o aviso do Illustrator, não a arte — a tela usa a do PDF irmão. O
    aviso de verdade vem quebrado em linhas ("...File that was" / "saved
    without PDF Content."), então o teste quebra igual.
    """
    doc = pymupdf.open()
    pg = doc.new_page(width=400, height=200)
    pg.insert_text((10, 30), "This is an Adobe Illustrator File that was", fontsize=10)
    pg.insert_text((10, 45), "saved without PDF Content.", fontsize=10)
    doc.save(str(tmp_path / "x.ai"))
    doc.close()

    assert oa.miniatura_de_caminho(tmp_path / "x.ai") is None


def test_miniatura_de_imagem(tmp_path):
    from PIL import Image
    Image.new("RGB", (1200, 600), "orange").save(tmp_path / "a.jpg")
    dados = oa.miniatura_de_caminho(tmp_path / "a.jpg")
    from PIL import Image as I
    with I.open(io.BytesIO(dados)) as img:
        assert max(img.size) <= oa.MINIATURA_PX


def test_arquivo_grande_demais_nao_gera_miniatura(tmp_path, monkeypatch):
    monkeypatch.setattr(oa, "LIMITE_PREVIA_LOCAL", 10)
    assert oa.miniatura_de_caminho(_pdf(tmp_path / "a.pdf")) is None


# ================================================================ pasta

def test_pasta_lista_com_as_subpastas_como_grupo(tmp_path):
    raiz = tmp_path / "cliente"
    _pdf(raiz / "PAINEL" / "painel.pdf")
    _pdf(raiz / "solto.pdf")
    (raiz / "desktop.ini").write_text("x")
    (raiz / "_sistema").mkdir()
    _pdf(raiz / "_sistema" / "nao_e_arte.pdf")

    itens = oa.OrigemPasta(raiz).listar()

    assert sorted((a.grupo, a.nome) for a in itens) == [("", "solto.pdf"), ("PAINEL", "painel.pdf")]


def test_pasta_baixar_copia_e_o_original_fica(tmp_path):
    raiz = tmp_path / "origem"
    original = _pdf(raiz / "PAINEL" / "painel.pdf")
    origem = oa.OrigemPasta(raiz)
    item = origem.listar()[0]

    salvo = origem.baixar(item, tmp_path / "espera")

    assert original.is_file(), "o original nunca sai do lugar"
    assert salvo == tmp_path / "espera" / "PAINEL" / "painel.pdf"
    assert salvo.read_bytes() == original.read_bytes()


def test_dois_arquivos_com_o_mesmo_nome_em_pastas_diferentes_nao_se_atropelam(tmp_path):
    raiz = tmp_path / "origem"
    _pdf(raiz / "A" / "arte.pdf", texto="A")
    _pdf(raiz / "B" / "arte.pdf", texto="B")
    origem = oa.OrigemPasta(raiz)

    destinos = {origem.baixar(i, tmp_path / "espera") for i in origem.listar()}

    assert len(destinos) == 2


def test_pasta_que_nao_existe(tmp_path):
    with pytest.raises(oa.ErroOrigem):
        oa.OrigemPasta(tmp_path / "nao existe")


# ================================================================== ZIP

def _zip(caminho, arquivos):
    with zipfile.ZipFile(caminho, "w", zipfile.ZIP_DEFLATED) as z:
        for nome, dados in arquivos.items():
            z.writestr(nome, dados)
    return caminho


def test_zip_lista_por_dentro_com_as_pastas(tmp_path):
    z = _zip(tmp_path / "t.zip", {
        "AFs_CENOGRAFIA/BACKDROP.pdf": _pdf_bytes(),
        "AFs_CENOGRAFIA/TOTEM.pdf": _pdf_bytes(),
        "__MACOSX/AFs_CENOGRAFIA/._BACKDROP.pdf": b"lixo do mac",
    })

    itens = oa.OrigemZip(z).listar()

    assert sorted(a.nome for a in itens) == ["BACKDROP.pdf", "TOTEM.pdf"]
    assert {a.grupo for a in itens} == {"AFs_CENOGRAFIA"}


def test_zip_baixar_tira_so_o_arquivo_marcado(tmp_path):
    dados = _pdf_bytes("TOTEM")
    z = _zip(tmp_path / "t.zip", {"X/TOTEM.pdf": dados, "X/OUTRO.pdf": _pdf_bytes()})
    origem = oa.OrigemZip(z)
    totem = next(a for a in origem.listar() if a.nome == "TOTEM.pdf")

    salvo = origem.baixar(totem, tmp_path / "espera")

    assert salvo.read_bytes() == dados
    assert not (tmp_path / "espera" / "X" / "OUTRO.pdf").exists()


def test_zip_guardar_original_copia_o_zip_inteiro(tmp_path):
    z = _zip(tmp_path / "t.zip", {"a.pdf": _pdf_bytes()})
    gravados = oa.OrigemZip(z).guardar_original(tmp_path / "recebidos")
    assert gravados[0].read_bytes() == z.read_bytes()


def _desligar_utf8(caminho):
    """Apaga a marca de UTF-8 do ZIP, como fazem compactadores antigos."""
    dados = bytearray(pathlib.Path(caminho).read_bytes())
    for assinatura, pos_flag in ((b"PK\x03\x04", 6), (b"PK\x01\x02", 8)):
        i = dados.find(assinatura)
        while i >= 0:
            flag = int.from_bytes(dados[i + pos_flag:i + pos_flag + 2], "little") & ~0x800
            dados[i + pos_flag:i + pos_flag + 2] = flag.to_bytes(2, "little")
            i = dados.find(assinatura, i + 4)
    pathlib.Path(caminho).write_bytes(bytes(dados))


def test_zip_sem_marca_de_utf8_nao_estraga_o_acento(tmp_path):
    """Sem isso 'PRAÇA' vira 'PRAÃ‡A' e o nome da peça sai torto."""
    z = _zip(tmp_path / "t.zip", {"PRAÇA 02/FRONTAL.pdf": _pdf_bytes()})
    _desligar_utf8(z)

    item = oa.OrigemZip(z).listar()[0]

    assert item.grupo == "PRAÇA 02"


def test_arquivo_que_nao_e_zip(tmp_path):
    falso = tmp_path / "t.zip"
    falso.write_bytes(b"nao sou zip")
    with pytest.raises(oa.ErroOrigem):
        oa.OrigemZip(falso)


# ======================================= arquivo remoto lido por pedaços

class _Resposta:
    def __init__(self, status, conteudo=b"", url="", dados_json=None, cabecalhos=None):
        self.status_code = status
        self.content = conteudo
        self.url = url
        self._json = dados_json
        self.headers = cabecalhos or {}

    def json(self):
        return self._json

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


class _ServidorDeArquivo:
    """Serve um blob com Range, e conta quantos bytes entregou."""
    def __init__(self, blob, aceita_range=True, nega_primeira=False):
        self.blob = blob
        self.aceita_range = aceita_range
        self.nega_primeira = nega_primeira
        self.entregue = 0
        self.pedidos = 0

    def get(self, url, headers=None, timeout=None, stream=False, allow_redirects=True):
        self.pedidos += 1
        if self.nega_primeira and "velho" in url:
            return _Resposta(403)
        r = (headers or {}).get("Range")
        if r and self.aceita_range:
            ini, fim = map(int, re.match(r"bytes=(\d+)-(\d+)", r).groups())
            pedaco = self.blob[ini:fim + 1]
            self.entregue += len(pedaco)
            return _Resposta(206, pedaco)
        self.entregue += len(self.blob)
        return _Resposta(200, self.blob)


def _zip_em_memoria(arquivos):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as z:
        for nome, dados in arquivos.items():
            z.writestr(nome, dados)
    return buf.getvalue()


def test_lista_de_dentro_do_zip_remoto_sem_baixar_o_zip():
    """
    O ponto de ArquivoHttp: o índice do ZIP mora no fim, e o zipfile vai
    direto lá. Um ZIP de ~6 MB listado trazendo uma fração disso.
    """
    blob = _zip_em_memoria({"A/grande.pdf": b"x" * 6_000_000, "A/pequeno.pdf": b"y" * 100})
    servidor = _ServidorDeArquivo(blob)

    z = zipfile.ZipFile(oa.ArquivoHttp(lambda renovar: "http://x", len(blob), servidor))
    nomes = sorted(z.namelist())

    assert nomes == ["A/grande.pdf", "A/pequeno.pdf"]
    assert servidor.entregue < len(blob) / 10


def test_ler_um_arquivo_de_dentro_do_zip_remoto_traz_so_ele():
    blob = _zip_em_memoria({"grande.pdf": b"x" * 6_000_000, "pequeno.pdf": b"conteudo certo"})
    servidor = _ServidorDeArquivo(blob)
    z = zipfile.ZipFile(oa.ArquivoHttp(lambda renovar: "http://x", len(blob), servidor))

    assert z.read("pequeno.pdf") == b"conteudo certo"
    assert servidor.entregue < 1_000_000


def test_endereco_vencido_pede_outro_uma_vez():
    """O endereço do WeTransfer tem token; o 403 renova e segue."""
    blob = _zip_em_memoria({"a.pdf": b"ok"})
    servidor = _ServidorDeArquivo(blob, nega_primeira=True)
    renovou = []

    def obter(renovar):
        if renovar:
            renovou.append(True)
            return "http://novo"
        return "http://velho"

    z = zipfile.ZipFile(oa.ArquivoHttp(obter, len(blob), servidor))

    assert z.read("a.pdf") == b"ok" and renovou == [True]


def test_servidor_que_ignora_pedaco_nao_se_passa_por_zip_valido():
    blob = _zip_em_memoria({"a.pdf": b"ok"})
    with pytest.raises((OSError, zipfile.BadZipFile)):
        zipfile.ZipFile(oa.ArquivoHttp(lambda r: "http://x", len(blob),
                                       _ServidorDeArquivo(blob, aceita_range=False)))


# ============================================================ WeTransfer

class _WeTransferFingido(_ServidorDeArquivo):
    """
    Responde como o site do WeTransfer respondeu em 21/09: o link curto
    redireciona pra /downloads/<id>/<hash>, prepare-download dá a lista,
    download dá o endereço direto.
    """
    TID = "6b8f808e12099f23c5199d520ef6eb9a20260921130923"

    def __init__(self, blob, **info):
        super().__init__(blob)
        self.info = {"state": "downloadable", "password_protected": False,
                     "display_name": "MANDARIN SESSIONS - 23.09",
                     "expires_at": "2026-09-24T13:09:43Z",
                     "items": [{"id": "item1", "name": "AFs_CENOGRAFIA.zip", "size": len(blob)}]}
        self.info.update(info)
        self.posts = []

    def get(self, url, headers=None, timeout=None, stream=False, allow_redirects=True):
        if "we.tl" in url:
            return _Resposta(200, url="https://wetransfer.com/downloads/%s/641af1?t=1" % self.TID)
        return super().get(url, headers=headers, timeout=timeout, stream=stream)

    def post(self, url, json=None, headers=None, timeout=None):
        self.posts.append((url.rsplit("/", 1)[-1], json))
        if url.endswith("prepare-download"):
            return _Resposta(200, dados_json=self.info)
        return _Resposta(200, dados_json={"direct_link": "https://download.wetransfer.com/x.zip?token=1"})


# Bytes FIXOS: o PyMuPDF carimba data e id em cada PDF, então dois
# _pdf_bytes("TOTEM") nunca são iguais byte a byte.
TOTEM = _pdf_bytes("TOTEM")
PAINEL = _pdf_bytes("PAINEL")


def _mandarin():
    return _zip_em_memoria({
        "AFs_CENOGRAFIA/AF_MANDARIN_SESSIONS_TOTEM.pdf": TOTEM,
        "AFs_CENOGRAFIA/AF_MANDARIN_SESSIONS_PAINEL.pdf": PAINEL,
    })


def test_wetransfer_lista_o_que_tem_dentro_do_zip(tmp_path):
    servidor = _WeTransferFingido(_mandarin())
    origem = oa.OrigemWeTransfer("https://we.tl/t-45FZ768DrtTycVk2", sessao=servidor)

    itens = origem.listar()

    assert sorted(a.nome for a in itens) == ["AF_MANDARIN_SESSIONS_PAINEL.pdf",
                                            "AF_MANDARIN_SESSIONS_TOTEM.pdf"]
    assert "MANDARIN SESSIONS - 23.09" in origem.rotulo
    assert "expira" in origem.aviso
    assert origem.chave(itens[0]).startswith("wetransfer|%s|" % servidor.TID)


def test_wetransfer_baixa_um_arquivo_de_dentro(tmp_path):
    origem = oa.OrigemWeTransfer("https://we.tl/t-x", sessao=_WeTransferFingido(_mandarin()))
    totem = next(a for a in origem.listar() if "TOTEM" in a.nome)

    salvo = origem.baixar(totem, tmp_path / "espera")

    assert salvo.read_bytes() == TOTEM


def test_wetransfer_sem_pedaco_mostra_o_zip_inteiro_como_um_arquivo(tmp_path):
    """
    Se o servidor parar de aceitar Range, não dá pra olhar dentro do ZIP
    sem baixar — mas ele continua aparecendo, inteiro, pra baixar.
    """
    servidor = _WeTransferFingido(_mandarin())
    servidor.aceita_range = False
    origem = oa.OrigemWeTransfer("https://we.tl/t-x", sessao=servidor)

    assert [a.nome for a in origem.listar()] == ["AFs_CENOGRAFIA.zip"]


def test_wetransfer_o_que_veio_pra_previa_nao_se_baixa_de_novo(tmp_path):
    servidor = _WeTransferFingido(_mandarin())
    origem = oa.OrigemWeTransfer("https://we.tl/t-x", sessao=servidor, pasta_cache=tmp_path / "cache")
    totem = next(a for a in origem.listar() if "TOTEM" in a.nome)

    assert origem.miniatura(totem)
    antes = servidor.pedidos
    origem.baixar(totem, tmp_path / "espera")

    assert servidor.pedidos == antes


def test_wetransfer_com_senha_diz_o_que_fazer():
    origem = oa.OrigemWeTransfer("https://we.tl/t-x",
                                 sessao=_WeTransferFingido(_mandarin(), password_protected=True))
    with pytest.raises(oa.ErroOrigem, match="SENHA"):
        origem.listar()


def test_wetransfer_expirado(tmp_path):
    class Expirado(_WeTransferFingido):
        def post(self, url, json=None, headers=None, timeout=None):
            return _Resposta(410)
    with pytest.raises(oa.ErroOrigem, match="não existe mais"):
        oa.OrigemWeTransfer("https://we.tl/t-x", sessao=Expirado(_mandarin())).listar()


def test_wetransfer_guarda_o_transfer_como_chegou(tmp_path):
    blob = _mandarin()
    origem = oa.OrigemWeTransfer("https://we.tl/t-x", sessao=_WeTransferFingido(blob))
    origem.listar()

    gravados = origem.guardar_original(tmp_path / "recebidos")

    assert [g.name for g in gravados] == ["AFs_CENOGRAFIA.zip"]
    assert gravados[0].read_bytes() == blob


# ================================================================= Drive

class _Pedido:
    def __init__(self, resultado):
        self._r = resultado

    def execute(self):
        if isinstance(self._r, Exception):
            raise self._r
        return self._r


class _DriveFingido:
    """id -> ficha; conteudo: id_pasta -> [ids]."""
    def __init__(self, fichas, conteudo):
        self.fichas, self.conteudo = fichas, conteudo

    def files(self):
        return self

    def get(self, fileId, fields=None, supportsAllDrives=None):
        return _Pedido(self.fichas.get(fileId) or Exception("sem acesso"))

    def list(self, q, fields=None, pageSize=None, supportsAllDrives=None,
             includeItemsFromAllDrives=None, pageToken=None):
        pasta = re.match(r"'([^']+)'", q).group(1)
        return _Pedido({"files": [self.fichas[i] for i in self.conteudo.get(pasta, [])]})


PASTA = drive_artes.MIME_PASTA
# ids com o comprimento dos de verdade: drive_artes.id_do_link exige 10+
LAND, CEN, AF, PAINEL_ID = "1LandMarkXX", "1CenografiaX", "1AFpastaXXXX", "1PainelFundo"
P1, P2, DOC = "1ArquivoPDF1", "1ArquivoAI22", "1DocGoogleX3"


def _drive_landmark():
    fichas = {
        CEN: {"id": CEN, "name": "CENOGRAFIA", "mimeType": PASTA, "parents": [AF]},
        AF: {"id": AF, "name": "[AF]", "mimeType": PASTA},
        LAND: {"id": LAND, "name": "LANDMARK", "mimeType": PASTA, "parents": [CEN]},
        PAINEL_ID: {"id": PAINEL_ID, "name": "PAINEL FRONTAL FUNDO", "mimeType": PASTA, "parents": [LAND]},
        P1: {"id": P1, "name": "AF_PAINEL.pdf", "mimeType": "application/pdf", "size": "727109",
             "modifiedTime": "2026-09-19T17:02:11.000Z", "thumbnailLink": "https://lh3/x=s220"},
        P2: {"id": P2, "name": "AF_PAINEL.ai", "mimeType": "application/illustrator", "size": "10"},
        DOC: {"id": DOC, "name": "briefing", "mimeType": "application/vnd.google-apps.document"},
    }
    conteudo = {LAND: [PAINEL_ID, DOC], PAINEL_ID: [P1, P2]}
    return _DriveFingido(fichas, conteudo)


def _link_pasta(id_):
    return "https://drive.google.com/drive/folders/" + id_


def test_drive_le_a_arvore_e_o_caminho_acima():
    origem = oa.OrigemDrive(_link_pasta(LAND), servico=_drive_landmark(), buscar=lambda url: b"img")

    itens = origem.listar()

    assert origem.rotulo == "[AF] > CENOGRAFIA > LANDMARK"
    assert origem.area_sugerida == "LANDMARK"
    assert sorted((a.grupo, a.nome) for a in itens) == [
        ("PAINEL FRONTAL FUNDO", "AF_PAINEL.ai"), ("PAINEL FRONTAL FUNDO", "AF_PAINEL.pdf")]


def test_drive_documento_do_google_fica_de_fora_e_avisa():
    origem = oa.OrigemDrive(_link_pasta(LAND), servico=_drive_landmark(), buscar=lambda url: b"img")
    origem.listar()
    assert [n for n, _ in origem.ignorados] == ["briefing"]


def test_drive_miniatura_pede_o_tamanho_da_previa():
    pedidas = []
    origem = oa.OrigemDrive(_link_pasta(LAND), servico=_drive_landmark(),
                            buscar=lambda url: pedidas.append(url) or b"img")
    pdf = next(a for a in origem.listar() if a.ext == "PDF")

    assert origem.miniatura(pdf) == b"img"
    assert pedidas == ["https://lh3/x=s%d" % oa.MINIATURA_PX]


def test_drive_link_de_um_arquivo_so():
    origem = oa.OrigemDrive("https://drive.google.com/file/d/%s/view" % P1,
                            servico=_drive_landmark(), buscar=lambda url: b"")
    assert [a.nome for a in origem.listar()] == ["AF_PAINEL.pdf"]


def test_drive_sem_acesso_diz_isso():
    origem = oa.OrigemDrive(_link_pasta("1NaoExisteNada"), servico=_drive_landmark(),
                            buscar=lambda url: b"")
    with pytest.raises(oa.ErroOrigem, match="sem acesso"):
        origem.listar()


def test_link_do_drive_sem_id():
    with pytest.raises(oa.ErroOrigem, match="id"):
        oa.OrigemDrive("https://drive.google.com/drive/my-drive", servico=_drive_landmark(),
                       buscar=lambda url: b"")


# ======================================================== qual origem é

def test_abrir_reconhece_pasta_e_zip(tmp_path):
    (tmp_path / "p").mkdir()
    z = _zip(tmp_path / "t.zip", {"a.pdf": b"x"})

    assert isinstance(oa.abrir(str(tmp_path / "p")), oa.OrigemPasta)
    assert isinstance(oa.abrir('"%s"' % z), oa.OrigemZip), "aspas do 'copiar como caminho' do Windows"


def test_abrir_link_do_wetransfer_e_do_drive_vai_pro_leitor_certo(monkeypatch):
    chamados = []
    monkeypatch.setattr(oa, "OrigemDrive", lambda t: chamados.append(("drive", t)))
    monkeypatch.setattr(oa, "OrigemWeTransfer", lambda t, pasta_cache=None: chamados.append(("wt", t)))

    oa.abrir("https://drive.google.com/drive/folders/abc")
    oa.abrir("https://we.tl/t-45FZ768DrtTycVk2")

    assert [c[0] for c in chamados] == ["drive", "wt"]


def test_link_do_onedrive_explica_o_caminho_da_pasta_sincronizada():
    with pytest.raises(oa.ErroOrigem, match="sincronizada"):
        oa.abrir("https://1drv.ms/f/s!abc")


def test_arquivo_solto_pede_a_pasta(tmp_path):
    _pdf(tmp_path / "a.pdf")
    with pytest.raises(oa.ErroOrigem, match="PASTA"):
        oa.abrir(str(tmp_path / "a.pdf"))


def test_nada_colado():
    with pytest.raises(oa.ErroOrigem):
        oa.abrir("   ")


# ====================================================== pasta de espera

def test_lote_velho_sai_e_o_resto_fica(tmp_path):
    agora = datetime.datetime(2026, 9, 21, 12, 0, 0)
    novo = oa.novo_lote(agora - datetime.timedelta(days=1))
    velho = oa.novo_lote(agora - datetime.timedelta(days=30))
    outra = caminhos.PASTA_RECEBENDO / "nao sou lote"
    outra.mkdir()

    apagados = oa.limpar_lotes_velhos(agora=agora)

    assert apagados == [velho]
    assert novo.is_dir() and outra.is_dir()
