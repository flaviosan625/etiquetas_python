"""
Testes de conformidade de licenças e dependências (ISSUE-01).
Garante que dependências LGPLv3 / GPL não retornem ao repositório.
"""

import pathlib
import re
import pytest


def test_requirements_sem_pystray():
    caminho_req = pathlib.Path(__file__).parent.parent / "requirements.txt"
    conteudo = caminho_req.read_text(encoding="utf-8")

    assert "pystray" not in conteudo.lower(), "pystray (LGPLv3) não deve estar no requirements.txt"


def test_codigo_fonte_nao_depende_obrigatoriamente_de_pystray():
    """Garante que nenhum módulo exija o pystray para importar ou rodar."""
    raiz = pathlib.Path(__file__).parent.parent
    arquivos_py = [
        p for p in raiz.glob("*.py")
        if not p.name.startswith(".") and p.is_file()
    ]

    for p in arquivos_py:
        texto = p.read_text(encoding="utf-8", errors="ignore")
        # Procura por 'import pystray' ou 'from pystray import' que não estejam dentro de try/except ou comentários
        for num_linha, linha in enumerate(texto.splitlines(), start=1):
            linha_strip = linha.strip()
            if linha_strip.startswith("import pystray") or linha_strip.startswith("from pystray import"):
                pytest.fail(f"Import direto de pystray encontrado em {p.name}:{num_linha}: '{linha_strip}'")
