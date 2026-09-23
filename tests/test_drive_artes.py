import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import drive_artes as da


# ----------------------------------------------------- id dentro do link

def test_extrai_id_de_open_id():
    assert da.id_do_link("https://drive.google.com/open?id=1gyVJBnpkTk6LXaDKX8oWj2") \
        == "1gyVJBnpkTk6LXaDKX8oWj2"


def test_extrai_id_de_open_id_com_parametro_extra():
    # é assim que o caderno real traz: open?id=X&usp=drive_fs
    assert da.id_do_link("https://drive.google.com/open?id=1ADGujSAO5T08QmgUt2qHL&usp=drive_fs") \
        == "1ADGujSAO5T08QmgUt2qHL"


def test_extrai_id_de_folders():
    assert da.id_do_link("https://drive.google.com/drive/folders/1C3J4bU5d-gfuh2CNzjl4hIY") \
        == "1C3J4bU5d-gfuh2CNzjl4hIY"


def test_extrai_id_de_file_d():
    assert da.id_do_link("https://drive.google.com/file/d/1Bx7KqABCDEFGH/view") \
        == "1Bx7KqABCDEFGH"


def test_link_sem_id_devolve_none():
    assert da.id_do_link("https://exemplo.com/qualquer") is None
    assert da.id_do_link("") is None
    assert da.id_do_link(None) is None


# ---------------------------------------- escolha do PDF (drive fingido)

class _DriveFake:
    """
    Um dublê do serviço do Drive: guarda o que cada id É e o que cada
    pasta contém, e responde às três chamadas que resolver_pdf usa.
    """
    def __init__(self, tipos, conteudo=None, infos=None):
        self._tipos = tipos            # id -> "pasta" | mimeType do arquivo
        self._conteudo = conteudo or {}  # id_pasta -> [arquivos]
        self._infos = infos or {}      # id_arquivo -> dict

    def files(self):
        return self

    def get(self, fileId, fields, supportsAllDrives=True):
        tipo = self._tipos.get(fileId)
        mime = da.MIME_PASTA if tipo == "pasta" else tipo
        info = dict(self._infos.get(fileId, {}), id=fileId, mimeType=mime)
        return _Exec(info)

    def list(self, q, fields, pageSize, supportsAllDrives,
             includeItemsFromAllDrives, pageToken):
        import re
        id_pasta = re.search(r"'([^']+)' in parents", q).group(1)
        return _Exec({"files": self._conteudo.get(id_pasta, []), "nextPageToken": None})


class _Exec:
    def __init__(self, valor):
        self._valor = valor

    def execute(self):
        return self._valor


def test_pasta_com_um_pdf_e_resolvida():
    drive = _DriveFake(
        tipos={"pastaAAAAAAAAAA1": "pasta"},
        conteudo={"pastaAAAAAAAAAA1": [{"id": "pdf1", "name": "arte final.pdf", "size": "500"}]})

    arquivo, motivo = da.resolver_pdf_da_pasta(drive, "https://drive.google.com/open?id=pastaAAAAAAAAAA1")

    assert motivo is None
    assert arquivo["id"] == "pdf1"


def test_pasta_com_varios_pdfs_nao_escolhe_no_chute():
    drive = _DriveFake(
        tipos={"pastaAAAAAAAAAA1": "pasta"},
        conteudo={"pastaAAAAAAAAAA1": [
            {"id": "a", "name": "arte_v1.pdf"},
            {"id": "b", "name": "arte_v2.pdf"}]})

    arquivo, motivo = da.resolver_pdf_da_pasta(drive, "https://drive.google.com/open?id=pastaAAAAAAAAAA1")

    assert arquivo is None
    assert "2 PDFs" in motivo


def test_ai_reportado_como_pdf_nao_conta_como_segundo_pdf():
    """
    O Drive rotula o .ai (arquivo de trabalho do Illustrator) como
    'application/pdf'. Sem filtrar pela extensão, a pasta parecia ter 2
    PDFs e a peça não baixava (LATERAL 02 e L08 do Mercado Livre,
    2026-09-12). O .ai não é o material de entrega — sai fora.
    """
    drive = _DriveFake(
        tipos={"pastaAAAAAAAAAA1": "pasta"},
        conteudo={"pastaAAAAAAAAAA1": [
            {"id": "pdf1", "name": "AF_LAT_2x3m.pdf", "size": "500"},
            {"id": "ai1", "name": "AF_LAT_2x3m.ai", "size": "900"}]})

    arquivo, motivo = da.resolver_pdf_da_pasta(drive, "https://drive.google.com/open?id=pastaAAAAAAAAAA1")

    assert motivo is None
    assert arquivo["id"] == "pdf1"


def test_dois_pdfs_de_verdade_continuam_ambiguos():
    """Filtrar .ai não pode mascarar ambiguidade real (LOGO ML x MP)."""
    drive = _DriveFake(
        tipos={"pastaAAAAAAAAAA1": "pasta"},
        conteudo={"pastaAAAAAAAAAA1": [
            {"id": "ml", "name": "LOGO_ML_1,5M.pdf"},
            {"id": "mp", "name": "LOGO_MP_1,5M.pdf"}]})

    arquivo, motivo = da.resolver_pdf_da_pasta(drive, "https://drive.google.com/open?id=pastaAAAAAAAAAA1")

    assert arquivo is None
    assert "2 PDFs" in motivo


def test_pasta_sem_pdf_avisa():
    drive = _DriveFake(tipos={"pastaAAAAAAAAAA1": "pasta"}, conteudo={"pastaAAAAAAAAAA1": []})

    arquivo, motivo = da.resolver_pdf_da_pasta(drive, "https://drive.google.com/open?id=pastaAAAAAAAAAA1")

    assert arquivo is None
    assert "nenhum PDF" in motivo


def test_link_que_aponta_o_pdf_direto_tambem_serve():
    drive = _DriveFake(
        tipos={"arqAAAAAAAAAA1": da.MIME_PDF},
        infos={"arqAAAAAAAAAA1": {"name": "arte.pdf", "size": "300"}})

    arquivo, motivo = da.resolver_pdf_da_pasta(drive, "https://drive.google.com/file/d/arqAAAAAAAAAA1/view")

    assert motivo is None
    assert arquivo["name"] == "arte.pdf"


def test_link_que_aponta_arquivo_que_nao_e_pdf_e_recusado():
    drive = _DriveFake(tipos={"arqAAAAAAAAAA1": "image/jpeg"}, infos={"arqAAAAAAAAAA1": {"name": "previa.jpg"}})

    arquivo, motivo = da.resolver_pdf_da_pasta(drive, "https://drive.google.com/file/d/arqAAAAAAAAAA1/view")

    assert arquivo is None
    assert "não é PDF" in motivo


def test_credencial_ausente_da_instrucao_clara(tmp_path, monkeypatch):
    monkeypatch.setattr(da, "CAMINHO_CREDENCIAL", tmp_path / "nao_existe.json")
    try:
        da.autenticar()
        assert False, "devia ter levantado FileNotFoundError"
    except FileNotFoundError as e:
        assert "Google Cloud" in str(e)


# ------------------------------------------- prazo da autorizacao (23/09/2026)
# O app esta em "Testing" no Google Cloud e o Google derruba o refresh
# token a cada 7 dias. Publicar tiraria o prazo, mas o botao do console
# ficou travado -- entao o sistema avisa o prazo e refaz o login num
# clique. Ver drive_artes.reautorizar / estado_do_token.

import datetime
import json

import pytest


@pytest.fixture(autouse=True)
def _isolar_segredos(tmp_path, monkeypatch):
    """
    O .google/ de VERDADE mora ao lado do modulo. Um teste distraido
    apagaria o token que o usuario usa pra trabalhar -- e refazer exige
    ele na frente do navegador.
    """
    monkeypatch.setattr(da, "PASTA_SEGREDOS", tmp_path / ".google")
    monkeypatch.setattr(da, "CAMINHO_CREDENCIAL", tmp_path / ".google" / "credenciais.json")
    monkeypatch.setattr(da, "CAMINHO_TOKEN", tmp_path / ".google" / "token.json")


class _CredencialFalsa:
    def to_json(self):
        return json.dumps({"token": "abc", "refresh_token": "xyz"})


def _escrever_token(dados):
    da.CAMINHO_TOKEN.parent.mkdir(parents=True, exist_ok=True)
    da.CAMINHO_TOKEN.write_text(json.dumps(dados), encoding="utf-8")


def test_login_novo_grava_a_data_da_autorizacao():
    quando = datetime.datetime(2026, 9, 23, 19, 0, 0)

    da._gravar_token(_CredencialFalsa(), autorizado_em=quando)

    dados = json.loads(da.CAMINHO_TOKEN.read_text(encoding="utf-8"))
    assert dados[da.CHAVE_AUTORIZADO_EM] == "2026-09-23T19:00:00"


def test_renovar_o_acesso_preserva_a_data_do_login():
    """
    Sem isto o prazo nunca venceria na conta: o arquivo e reescrito a
    cada renovacao, e a data viraria sempre 'agora'.
    """
    _escrever_token({"token": "velho", da.CHAVE_AUTORIZADO_EM: "2026-09-20T08:00:00"})

    da._gravar_token(_CredencialFalsa())

    dados = json.loads(da.CAMINHO_TOKEN.read_text(encoding="utf-8"))
    assert dados[da.CHAVE_AUTORIZADO_EM] == "2026-09-20T08:00:00"
    assert dados["token"] == "abc", "o token novo tem que entrar"


def test_dias_ate_vencer_conta_os_sete_dias():
    _escrever_token({da.CHAVE_AUTORIZADO_EM: "2026-09-20T08:00:00"})

    assert da.dias_ate_vencer(datetime.datetime(2026, 9, 20, 9, 0)) == 6
    assert da.dias_ate_vencer(datetime.datetime(2026, 9, 26, 9, 0)) == 0
    assert da.dias_ate_vencer(datetime.datetime(2026, 9, 30, 9, 0)) == 0, "nunca negativo"


def test_token_antigo_sem_a_data_nao_quebra():
    """Token de antes desta mudanca: nao da pra saber, e tudo bem."""
    _escrever_token({"token": "sem data"})

    assert da.dias_ate_vencer(datetime.datetime(2026, 9, 23)) is None


def test_estado_sem_credencial_explica_o_que_falta():
    estado = da.estado_do_token()

    assert estado["situacao"] == "sem_credencial"
    assert "credenciais.json" in estado["texto"]


def test_estado_sem_token_manda_reconectar():
    da.CAMINHO_CREDENCIAL.parent.mkdir(parents=True, exist_ok=True)
    da.CAMINHO_CREDENCIAL.write_text("{}", encoding="utf-8")

    estado = da.estado_do_token()

    assert estado["situacao"] == "sem_token"
    assert "Reconectar" in estado["texto"]


def test_estado_avisa_quando_esta_perto_de_vencer(monkeypatch):
    da.CAMINHO_CREDENCIAL.parent.mkdir(parents=True, exist_ok=True)
    da.CAMINHO_CREDENCIAL.write_text("{}", encoding="utf-8")
    _escrever_token({da.CHAVE_AUTORIZADO_EM: "2026-09-20T08:00:00"})
    monkeypatch.setattr(da, "autenticar", lambda abrir_navegador=True: object())

    estado = da.estado_do_token(datetime.datetime(2026, 9, 25, 9, 0))

    assert estado["situacao"] == "vence_logo"
    assert estado["dias"] == 1


def test_estado_vencido_quando_a_autenticacao_falha(monkeypatch):
    da.CAMINHO_CREDENCIAL.parent.mkdir(parents=True, exist_ok=True)
    da.CAMINHO_CREDENCIAL.write_text("{}", encoding="utf-8")
    _escrever_token({"token": "qualquer"})

    def _explode(abrir_navegador=True):
        raise RuntimeError("token expirado")
    monkeypatch.setattr(da, "autenticar", _explode)

    estado = da.estado_do_token()

    assert estado["situacao"] == "vencido"
    assert "Reconectar" in estado["texto"]


def test_reautorizar_guarda_o_token_velho_antes_de_trocar(monkeypatch):
    """Se o login novo for cancelado no meio, o velho ainda esta la."""
    _escrever_token({"token": "o velho"})
    monkeypatch.setattr(da, "_fluxo_oauth",
                        lambda: type("F", (), {"run_local_server": lambda s, port=0: _CredencialFalsa()})())

    da.reautorizar(agora=datetime.datetime(2026, 9, 23, 20, 0))

    guardado = da.CAMINHO_TOKEN.with_suffix(".json.vencido")
    assert json.loads(guardado.read_text(encoding="utf-8"))["token"] == "o velho"
    novo = json.loads(da.CAMINHO_TOKEN.read_text(encoding="utf-8"))
    assert novo[da.CHAVE_AUTORIZADO_EM] == "2026-09-23T20:00:00"
