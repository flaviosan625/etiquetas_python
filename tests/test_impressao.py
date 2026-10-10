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


def test_um_comando_envia_etiquetas_os_e_retirada_em_arquivos_separados(monkeypatch):
    import gui
    chamadas = []
    monkeypatch.setattr(gui, "imprimir_pdf", lambda arquivo, impressora: chamadas.append((arquivo, impressora)))
    resultado = dict(unificado="Checklist CLIENTE.pdf", os="OS - CLIENTE.pdf", retirada="RETIRADA - CLIENTE.pdf")
    gui.JanelaPrincipal._imprimir_os_checklist(None, resultado, "HP", lambda *args: None)
    assert chamadas == [("Checklist CLIENTE.pdf", "HP"), ("OS - CLIENTE.pdf", "HP"),
                        ("RETIRADA - CLIENTE.pdf", "HP")]


def test_falha_ao_imprimir_os_nao_impede_retirada(monkeypatch):
    import gui
    chamadas, mensagens = [], []

    def imprimir(arquivo, impressora):
        chamadas.append(arquivo)
        if arquivo == "OS.pdf":
            raise RuntimeError("Falha na impressão da OS")

    monkeypatch.setattr(gui, "imprimir_pdf", imprimir)
    gui.JanelaPrincipal._imprimir_os_checklist(
        None, dict(unificado="Etiquetas.pdf", os="OS.pdf", retirada="Retirada.pdf"),
        "HP", lambda nivel, msg: mensagens.append((nivel, msg)))
    assert chamadas == ["Etiquetas.pdf", "OS.pdf", "Retirada.pdf"]
    assert ("err", "Falha na impressão da OS") in mensagens


def test_reimpressao_encontra_os_etiquetas_e_retirada(tmp_path):
    import gui
    pasta = tmp_path / "CLIENTE"
    pasta.mkdir()
    for nome in ["Checklist CLIENTE.pdf", "OS - CLIENTE.pdf", "RETIRADA - CLIENTE.pdf"]:
        (pasta / nome).write_bytes(b"PDF de teste")
    pedidos = gui._pedidos_para_impressao(tmp_path)
    assert len(pedidos) == 1
    assert pedidos[0]["retirada"] == [pasta / "RETIRADA - CLIENTE.pdf"]
    assert pedidos[0]["os"] == [pasta / "OS - CLIENTE.pdf"]
    assert pedidos[0]["checklist"] == [pasta / "Checklist CLIENTE.pdf"]
