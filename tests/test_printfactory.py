import pytest

from printfactory import enviar_para_hot_folder


def test_copia_arquivo_pra_hot_folder_sem_mexer_no_original(tmp_path):
    hot_folder = tmp_path / "hotfolder"
    hot_folder.mkdir()
    origem = tmp_path / "arte.pdf"
    origem.write_bytes(b"conteudo")

    destino = enviar_para_hot_folder(str(origem), pasta_hot_folder=str(hot_folder))

    assert destino == hot_folder / "arte.pdf"
    assert destino.read_bytes() == b"conteudo"
    assert origem.exists(), "original nunca pode sumir — so copia, nunca move"


def test_hot_folder_nao_configurada_da_erro_claro(tmp_path):
    origem = tmp_path / "arte.pdf"
    origem.write_bytes(b"x")
    with pytest.raises(RuntimeError, match="ainda não configurada"):
        enviar_para_hot_folder(str(origem))


def test_pasta_hot_folder_inexistente_da_erro_claro(tmp_path):
    origem = tmp_path / "arte.pdf"
    origem.write_bytes(b"x")
    with pytest.raises(FileNotFoundError):
        enviar_para_hot_folder(str(origem), pasta_hot_folder=str(tmp_path / "nao_existe"))


def test_arquivo_origem_inexistente_da_erro_claro(tmp_path):
    hot_folder = tmp_path / "hotfolder"
    hot_folder.mkdir()
    with pytest.raises(FileNotFoundError):
        enviar_para_hot_folder(str(tmp_path / "nao_existe.pdf"), pasta_hot_folder=str(hot_folder))


def test_sobrescreve_se_ja_existir_arquivo_com_mesmo_nome(tmp_path):
    hot_folder = tmp_path / "hotfolder"
    hot_folder.mkdir()
    (hot_folder / "arte.pdf").write_bytes(b"versao antiga")
    origem = tmp_path / "arte.pdf"
    origem.write_bytes(b"versao nova")

    destino = enviar_para_hot_folder(str(origem), pasta_hot_folder=str(hot_folder))

    assert destino.read_bytes() == b"versao nova"
