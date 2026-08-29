import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from conversao_adobe import converter_se_necessario


def _logger():
    mensagens = []

    def emitir(nivel, msg, arquivo=None, status_csv=None):
        mensagens.append((nivel, msg, arquivo, status_csv))

    return mensagens, emitir


def test_arquivo_sem_conversor_devolve_none(tmp_path):
    mensagens, emitir = _logger()
    (tmp_path / "1UN LONA 1,00X1,00M.pdf").write_bytes(b"pdf de verdade nao importa aqui")

    resultado = converter_se_necessario(tmp_path, "1UN LONA 1,00X1,00M.pdf", tmp_path / "_originais", emitir)

    assert resultado is None
    assert mensagens == []


def test_converte_e_move_original_pra_subpasta(tmp_path):
    def conversor_fake(caminho_origem, caminho_pdf_destino):
        pathlib.Path(caminho_pdf_destino).write_bytes(b"pdf fake gerado pelo conversor")

    mensagens, emitir = _logger()
    (tmp_path / "arte.eps").write_bytes(b"conteudo eps fake")

    resultado = converter_se_necessario(
        tmp_path, "arte.eps", tmp_path / "_originais", emitir, conversores={".eps": conversor_fake},
    )

    assert resultado == "arte.pdf"
    assert (tmp_path / "arte.pdf").exists()
    assert (tmp_path / "_originais" / "arte.eps").exists()
    assert not (tmp_path / "arte.eps").exists()
    assert any(nivel == "ok" for nivel, *_ in mensagens)


def test_colisao_de_nome_ganha_sufixo_numerico(tmp_path):
    def conversor_fake(caminho_origem, caminho_pdf_destino):
        pathlib.Path(caminho_pdf_destino).write_bytes(b"novo pdf")

    _, emitir = _logger()
    (tmp_path / "arte.pdf").write_bytes(b"pdf que ja existia, nao pode ser sobrescrito")
    (tmp_path / "arte.eps").write_bytes(b"conteudo eps fake")

    resultado = converter_se_necessario(
        tmp_path, "arte.eps", tmp_path / "_originais", emitir, conversores={".eps": conversor_fake},
    )

    assert resultado == "arte (2).pdf"
    assert (tmp_path / "arte.pdf").read_bytes() == b"pdf que ja existia, nao pode ser sobrescrito"
    assert (tmp_path / "arte (2).pdf").exists()


def test_falha_na_conversao_avisa_e_nao_apaga_original(tmp_path):
    def conversor_que_falha(caminho_origem, caminho_pdf_destino):
        raise RuntimeError("Illustrator não respondeu")

    mensagens, emitir = _logger()
    (tmp_path / "arte.eps").write_bytes(b"conteudo eps fake")

    resultado = converter_se_necessario(
        tmp_path, "arte.eps", tmp_path / "_originais", emitir, conversores={".eps": conversor_que_falha},
    )

    assert resultado is None
    assert (tmp_path / "arte.eps").exists(), "original nunca pode sumir se a conversão falhou"
    assert not (tmp_path / "arte.pdf").exists()
    assert any(nivel == "err" for nivel, *_ in mensagens)
