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
