import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from utils import remover_acentos, sanitizar_nome_arquivo


def test_sanitizar_remove_caracteres_invalidos_do_windows():
    resultado = sanitizar_nome_arquivo('Cliente: Teste/2026?"<>|*')
    for c in '<>:"/\\|?*':
        assert c not in resultado


def test_sanitizar_nome_vazio_retorna_fallback():
    assert sanitizar_nome_arquivo("   ") == "SEM_NOME"


def test_sanitizar_mantem_nome_normal_intacto():
    assert sanitizar_nome_arquivo("Construtora Alvorada") == "Construtora Alvorada"


def test_remover_acentos_normaliza_vogais_e_cedilha():
    assert remover_acentos("REPOSIÇÃO") == "REPOSICAO"
    assert remover_acentos("reposiçao") == "reposicao"
    assert remover_acentos("REFAÇÃO") == "REFACAO"


def test_remover_acentos_mantem_texto_sem_acento_intacto():
    assert remover_acentos("CONSTRUTORA ALVORADA") == "CONSTRUTORA ALVORADA"
