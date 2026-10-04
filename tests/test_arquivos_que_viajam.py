"""
Os arquivos que VIAJAM pras maquinas, e as duas regras que os mantem
viajaveis.

Quais sao: o vigia (rasterlink_hotfolder.py) e os tres que ele usa pra
separar o ripado por maquina. Eles sao copiados pra C:\\RasterLink (PC do
RIP) e C:\\VigiaDocan (maquina da DOCAN), onde NAO existe repositorio,
NAO existe .venv e NAO ha nada instalado alem do Python do sistema.

REGRA 1: so biblioteca padrao (e eles entre si).
Um 'import pymupdf' no topo de qualquer um deles quebra as tres
impressoras de uma vez, e quebra LA, na mao dele -- aqui passaria
despercebido, porque aqui tudo esta instalado.

REGRA 2: nem um aviso de sintaxe.
Em 04/10/2026 um '\\P' meu numa docstring virou SyntaxWarning. O modulo
importava normalmente, mas o PowerShell 5.1 embrulha cada linha de stderr
num NativeCommandError e DERRUBOU o atualizador no meio, depois de ele ja
ter copiado os arquivos. Aviso que ninguem le aqui vira script morto la.
"""
import ast
import pathlib
import py_compile
import sys
import warnings

import pytest

RAIZ = pathlib.Path(__file__).resolve().parent.parent

# A mesma lista que os kits copiam (maquina_docan/atualizar.ps1,
# maquina_docan/instalar_tarefa.ps1). Mudar aqui pede mudar la.
QUE_VIAJAM = (
    "rasterlink_hotfolder.py",
    "separar_ripados.py",
    "ripados_para_nuvem.py",
    "caminhos.py",
)

# O que o Python do sistema tem sem instalar nada. Os quatro tambem podem
# importar uns aos outros: sao copiados juntos.
PERMITIDOS = set(sys.stdlib_module_names) | {p[:-3] for p in QUE_VIAJAM}


def _imports_do_topo(caminho):
    """
    So os imports de NIVEL DE MODULO. Import tardio dentro de funcao e
    justamente o jeito certo de usar algo que pode nao existir la (o
    pymupdf do giro, o aviso_fila, o separador), e todos estao dentro de
    try -- esses nao contam.
    """
    arvore = ast.parse(caminho.read_text(encoding="utf-8"), filename=str(caminho))
    nomes = []
    for no in arvore.body:
        if isinstance(no, ast.Import):
            nomes += [a.name.split(".")[0] for a in no.names]
        elif isinstance(no, ast.ImportFrom) and no.level == 0 and no.module:
            nomes.append(no.module.split(".")[0])
    return nomes


@pytest.mark.parametrize("nome", QUE_VIAJAM)
def test_so_importa_biblioteca_padrao(nome):
    fora = sorted(set(_imports_do_topo(RAIZ / nome)) - PERMITIDOS)
    assert not fora, (
        f"{nome} importa {fora} no topo. Esse arquivo e copiado pra uma maquina sem .venv e sem "
        f"o projeto: o import vai falhar la e a impressora para de receber. Se precisar mesmo, "
        f"importe DENTRO da funcao, em try/except Exception."
    )


@pytest.mark.parametrize("nome", QUE_VIAJAM)
def test_compila_sem_um_unico_aviso(nome, tmp_path):
    with warnings.catch_warnings(record=True) as avisados:
        warnings.simplefilter("always")
        py_compile.compile(str(RAIZ / nome), cfile=str(tmp_path / f"{nome}c"), doraise=True)
    recado = [f"{a.category.__name__}: {a.message}" for a in avisados]
    assert not recado, (
        f"{nome} compila com aviso: {recado}. O modulo importa, mas o aviso vai pro stderr e o "
        f"PowerShell 5.1 derruba o instalador por causa dele (04/10/2026)."
    )


def test_a_lista_bate_com_o_que_os_kits_copiam():
    """Arquivo novo na lista daqui e esquecido no .ps1 chega como 'ModuleNotFoundError' la."""
    for kit in ("maquina_docan/atualizar.ps1", "maquina_docan/instalar_tarefa.ps1"):
        texto = (RAIZ / kit).read_text(encoding="utf-8-sig")
        faltando = [n for n in QUE_VIAJAM if f'"{n}"' not in texto]
        assert not faltando, f"{kit} nao copia {faltando}"
