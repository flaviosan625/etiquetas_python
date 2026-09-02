import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import impressao


def test_imprimir_pdf_levanta_erro_se_arquivo_nao_existe(tmp_path):
    with pytest.raises(RuntimeError, match="não encontrado"):
        impressao.imprimir_pdf(tmp_path / "nao_existe.pdf")


def test_imprimir_pdf_sem_impressora_usa_verbo_print(tmp_path, monkeypatch):
    arquivo = tmp_path / "OS - CLIENTE.pdf"
    arquivo.write_text("conteudo")
    monkeypatch.setattr(impressao, "DISPONIVEL", True)

    chamadas = []

    class FakeWin32Api:
        @staticmethod
        def ShellExecute(hwnd, verbo, caminho, params, diretorio, show):
            chamadas.append((verbo, caminho, params))
            return 42

    monkeypatch.setattr(impressao, "win32api", FakeWin32Api)

    impressao.imprimir_pdf(arquivo)

    assert chamadas == [("print", str(arquivo), None)]


def test_imprimir_pdf_com_impressora_usa_verbo_printto(tmp_path, monkeypatch):
    arquivo = tmp_path / "Checklist CLIENTE.pdf"
    arquivo.write_text("conteudo")
    monkeypatch.setattr(impressao, "DISPONIVEL", True)

    chamadas = []

    class FakeWin32Api:
        @staticmethod
        def ShellExecute(hwnd, verbo, caminho, params, diretorio, show):
            chamadas.append((verbo, caminho, params))
            return 42

    monkeypatch.setattr(impressao, "win32api", FakeWin32Api)

    impressao.imprimir_pdf(arquivo, impressora="HP Color LaserJet Pro 4203")

    assert chamadas == [("printto", str(arquivo), '"HP Color LaserJet Pro 4203"')]


def test_imprimir_pdf_levanta_erro_se_windows_recusar(tmp_path, monkeypatch):
    arquivo = tmp_path / "OS - CLIENTE.pdf"
    arquivo.write_text("conteudo")
    monkeypatch.setattr(impressao, "DISPONIVEL", True)

    class FakeWin32Api:
        @staticmethod
        def ShellExecute(hwnd, verbo, caminho, params, diretorio, show):
            return 2  # ShellExecute devolve <= 32 em caso de erro

    monkeypatch.setattr(impressao, "win32api", FakeWin32Api)

    with pytest.raises(RuntimeError, match="recusou o pedido"):
        impressao.imprimir_pdf(arquivo)


def test_imprimir_pdf_indisponivel_sem_pywin32(tmp_path, monkeypatch):
    arquivo = tmp_path / "OS - CLIENTE.pdf"
    arquivo.write_text("conteudo")
    monkeypatch.setattr(impressao, "DISPONIVEL", False)

    with pytest.raises(RuntimeError, match="não disponível"):
        impressao.imprimir_pdf(arquivo)


def test_listar_impressoras_devolve_lista():
    resultado = impressao.listar_impressoras()
    assert isinstance(resultado, list)


def test_impressora_padrao_devolve_string_ou_none():
    resultado = impressao.impressora_padrao()
    assert resultado is None or isinstance(resultado, str)
