"""
Leitura do PMSetups.ini do SAi Production Manager.

Todos os testes escrevem o .ini em tmp_path — nenhum lê o arquivo de
verdade dentro de Program Files.
"""
import sai_setups

INI = """Device:xkeda-XLF_HS_NET_EPS3200UV_LM
Hotfolder:C:\\Program Files\\SAi\\SAi Production Suite 22\\Jobs and Settings\\Jobs\\xkeda\\XLF_HS_NET_E
PresetFolder:C:\\Program Files\\SAi\\SAi Production Suite 22\\Devices\\XLF_HS_NET_EPS3200UV_LM\\Presets
ICCFolder:xkeda
Device:Docan-Docan
Hotfolder:C:\\Program Files\\SAi\\SAi Production Suite 22\\Jobs and Settings\\Jobs\\Docan\\Docan
PresetFolder:C:\\Program Files\\SAi\\SAi Production Suite 22\\Devices\\Docan\\Presets
ICCFolder:Docan
"""


def escrever(tmp_path, texto=INI):
    caminho = tmp_path / "PMSetups.ini"
    caminho.write_text(texto, encoding="utf-8")
    return caminho


def test_le_todos_os_setups(tmp_path):
    setups = sai_setups.ler(escrever(tmp_path))
    assert [s["device"] for s in setups] == ["xkeda-XLF_HS_NET_EPS3200UV_LM", "Docan-Docan"]


def test_a_letra_do_drive_nao_se_perde_no_dois_pontos(tmp_path):
    """'Hotfolder:C:\\...' tem dois ':' — cortar no errado comeria o drive."""
    setups = sai_setups.ler(escrever(tmp_path))
    assert setups[1]["hot_folder"].startswith("C:\\Program Files")


def test_guarda_o_nome_cortado_em_12_letras_como_esta(tmp_path):
    """
    O SAi corta a pasta em 12 letras: XLF_HS_NET_EPS3200UV_LM virou
    XLF_HS_NET_E. Ler o arquivo é justamente pra não ter que adivinhar
    isso — o valor sai daqui como está escrito.
    """
    setups = sai_setups.ler(escrever(tmp_path))
    assert setups[0]["hot_folder"].endswith("XLF_HS_NET_E")


def test_hot_folder_por_device(tmp_path):
    caminho = escrever(tmp_path)
    assert sai_setups.hot_folder_de("Docan-Docan", caminho).endswith(r"Jobs\Docan\Docan")
    assert sai_setups.hot_folder_de("nao-existe", caminho) is None


def test_arquivo_ausente_nao_e_defeito(tmp_path):
    """Este módulo roda em PC que pode não ter o SAi instalado."""
    assert sai_setups.ler(tmp_path / "nao_existe.ini") == []
    assert sai_setups.conferir_maquinas({}, tmp_path / "nao_existe.ini") == []


def test_cadastro_certo_nao_acusa_divergencia(tmp_path):
    maquinas = {
        "DOCAN": {
            "hot_folder": r"C:\Program Files\SAi\SAi Production Suite 22\Jobs and Settings\Jobs\Docan\Docan",
            "largura_util_m": 5.00,
        },
    }
    assert sai_setups.conferir_maquinas(maquinas, escrever(tmp_path)) == []


def test_hot_folder_que_o_sai_nao_conhece_vira_divergencia(tmp_path):
    """
    O erro que este módulo existe pra pegar: a pasta cadastrada parece
    certa pelo nome do setup, mas não é a que o Production Manager vigia.
    """
    maquinas = {
        "DOCAN H2525": {
            "hot_folder": r"C:\Program Files\SAi\SAi Production Suite 22\Jobs and Settings\Jobs\Docan\DocanH2525",
            "mesa_util_m": (2.5, 2.5),
        },
    }
    (divergencia,) = sai_setups.conferir_maquinas(maquinas, escrever(tmp_path))
    assert divergencia["maquina"] == "DOCAN H2525"
    assert divergencia["cadastrada"].endswith("DocanH2525")


def test_maquina_que_nao_e_do_sai_fica_de_fora(tmp_path):
    """A hot folder das Mimaki é do RasterLink7 e não está neste arquivo."""
    maquinas = {"SWJ320A": {"hot_folder": r"C:\MijCtrl\Hot\SWJ320A", "largura_util_m": 3.20}}
    assert sai_setups.conferir_maquinas(maquinas, escrever(tmp_path)) == []


def test_o_cadastro_de_hoje_bate_com_o_sai_desta_maquina():
    """
    Contra o arquivo REAL, só leitura: se alguém refizer o setup e a
    pasta mudar de lugar, este teste avisa antes de a fila encalhar.
    Pula sozinho onde o SAi não está instalado.
    """
    import pytest

    import rasterlink_hotfolder as rl_hf

    if not sai_setups.CAMINHO_PMSETUPS.exists():
        pytest.skip("SAi não instalado nesta máquina")
    assert sai_setups.conferir_maquinas(rl_hf.MAQUINAS) == []
