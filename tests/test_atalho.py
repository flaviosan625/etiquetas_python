"""
Testes do atalho da área de trabalho.

Nenhum deles pode escrever na área de trabalho de verdade nem em
assets/: o ícone vai pro tmp_path e o atalho é escrito num shell de
mentira, que só guarda o que foi pedido.
"""
from PIL import Image, ImageDraw

import atalho


def _logo_falso(largura=1000, altura=500, vao=(400, 520)):
    """Dois borrões com um vão transparente no meio — igual ao logo real."""
    im = Image.new("RGBA", (largura, altura), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rectangle((0, 50, vao[0] - 1, altura - 50), fill=(0, 120, 200, 255))
    d.rectangle((vao[1], 100, largura - 1, altura - 100), fill=(200, 0, 100, 255))
    return im


class ShellFalso:
    """O mínimo do WScript.Shell: guarda o que foi pedido, não escreve nada."""

    def __init__(self, area="C:\\AreaDeTrabalhoFalsa"):
        self.area = area
        self.atalhos = {}

    def SpecialFolders(self, nome):       # noqa: N802  (nome é da API do Windows)
        assert nome == "Desktop"
        return self.area

    def CreateShortCut(self, caminho):    # noqa: N802
        atalho_falso = type("AtalhoFalso", (), {"Save": lambda s: None})()
        self.atalhos[caminho] = atalho_falso
        return atalho_falso


def test_simbolo_e_so_a_parte_antes_do_vao():
    caixa = atalho._caixa_do_simbolo(_logo_falso())
    assert caixa == (0, 0, 400, 500)


def test_logo_sem_vao_vira_o_logo_inteiro():
    im = Image.new("RGBA", (300, 200), (10, 10, 10, 255))
    assert atalho._caixa_do_simbolo(im) == (0, 0, 300, 200)


def test_o_icone_sai_quadrado_e_com_todos_os_tamanhos(tmp_path):
    destino = atalho.gerar_icone(tmp_path / "uny.ico")
    with Image.open(destino) as ico:
        assert sorted(ico.info["sizes"]) == [(n, n) for n in atalho.TAMANHOS]
        assert ico.size == (256, 256)


def test_o_icone_nao_sai_em_branco(tmp_path):
    """O símbolo tem que estar mesmo lá dentro — e a plaquinha, branca."""
    destino = atalho.gerar_icone(tmp_path / "uny.ico")
    with Image.open(destino) as ico:
        cores = {cor for _, cor in ico.convert("RGB").getcolors(maxcolors=1 << 20)}
    assert (255, 255, 255) in cores
    assert len(cores) > 20          # o símbolo é colorido, não um quadrado só


def test_nao_regera_o_icone_que_ja_existe(tmp_path):
    destino = atalho.gerar_icone(tmp_path / "uny.ico")
    antes = destino.stat().st_mtime_ns
    assert atalho.gerar_icone(destino).stat().st_mtime_ns == antes
    assert atalho.gerar_icone(destino, forcar=True).stat().st_mtime_ns != antes


def test_o_atalho_aponta_pro_pythonw_e_pro_main(tmp_path):
    shell = ShellFalso()
    icone = tmp_path / "uny.ico"
    icone.write_bytes(b"")
    caminho = atalho.criar(pasta=tmp_path, shell=shell, icone=icone)

    assert caminho == tmp_path / atalho.NOME_ATALHO
    criado = shell.atalhos[str(caminho)]
    # pythonw: com python.exe sobra uma janela de console aberta atrás
    assert criado.TargetPath.lower().endswith("pythonw.exe")
    assert criado.Arguments.endswith('main.py"')
    assert criado.IconLocation == str(icone)


def test_sem_pasta_vai_pra_area_de_trabalho_que_o_windows_informa(tmp_path):
    """E não em ~/Desktop cravado, que erra com a pasta redirecionada."""
    shell = ShellFalso(area=str(tmp_path / "Outra Area"))
    icone = tmp_path / "uny.ico"
    icone.write_bytes(b"")
    caminho = atalho.criar(shell=shell, icone=icone)
    assert caminho.parent == tmp_path / "Outra Area"


def test_descricao_e_ascii_puro():
    # o campo de descrição do .lnk é gravado em ANSI: acento vira "?"
    assert atalho.DESCRICAO.isascii()
    assert atalho.NOME_ATALHO.isascii()
