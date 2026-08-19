import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from utils import sanitizar_nome_arquivo


def test_sanitizar_remove_caracteres_invalidos_do_windows():
    resultado = sanitizar_nome_arquivo('Cliente: Teste/2026?"<>|*')
    for c in '<>:"/\\|?*':
        assert c not in resultado


def test_sanitizar_nome_vazio_retorna_fallback():
    assert sanitizar_nome_arquivo("   ") == "SEM_NOME"


def test_sanitizar_mantem_nome_normal_intacto():
    assert sanitizar_nome_arquivo("Construtora Alvorada") == "Construtora Alvorada"
