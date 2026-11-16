"""
Onde as coisas moram — num lugar só.

Por que existe (2026-09-13): o sistema vai virar um executável ("na hora de
migrar para um executável já está quase tudo reaproveitável", pedido do
usuário). Num .exe, `__file__` aponta pra uma pasta temporária de
descompactação e caminho relativo depende de onde o atalho foi aberto —
exatamente como `etiquetas_geradas` era resolvido até aqui. Então todo
caminho que o sistema usa passa a ser perguntado a este módulo, e é SÓ
AQUI que a diferença entre "rodando do código" e "rodando do .exe" existe.

Ler os valores SEMPRE como `caminhos.X` na hora de usar (e não com
`from caminhos import X`, que copia o valor na carga): é assim que os
testes conseguem apontar tudo pra uma pasta temporária. Teste nunca toca
pasta real — ver CLAUDE.md.

FICA DE FORA: rasterlink_hotfolder.py. Ele é levado sozinho pro PC do RIP,
que não tem o resto do projeto, e por isso monta os caminhos dele.
"""
import os
import pathlib
import sys
import tempfile


def _pasta_do_programa():
    """A pasta do programa: a do .exe quando empacotado, a do código quando não."""
    if getattr(sys, "frozen", False):
        return pathlib.Path(sys.executable).resolve().parent
    return pathlib.Path(__file__).resolve().parent


PASTA_PROGRAMA = _pasta_do_programa()


def _obter_pasta_base():
    """
    Pasta base onde moram os dados de produção, montagem e recebimento.
    100% local, funcionando no computador do cliente sem depender de OneDrive.
    Pode ser customizada em config.json ('pasta_base' ou 'pasta_dados').
    Padrão: ~/AutomacaoGrafica (ex: C:\\Users\\<usuario>\\AutomacaoGrafica).
    """
    try:
        from config import carregar_config
        cfg = carregar_config()
        if isinstance(cfg, dict):
            p = cfg.get("pasta_base") or cfg.get("pasta_dados")
            if p:
                caminho = pathlib.Path(p)
                if caminho.is_absolute():
                    return caminho
    except Exception:
        pass
    return pathlib.Path.home() / "AutomacaoGrafica"


PASTA_BASE = _obter_pasta_base()
PASTA_DADOS = PASTA_BASE

# Pastas locais de trabalho (desacopladas de nuvem / OneDrive)
RECEBIMENTO_DE_ARTES = PASTA_BASE / "Recebimento de Artes"
EVENTOS = PASTA_BASE / "EVENTOS"

# Fluxo unificado de montagem: artes soltas para montar e saída centralizada
ARTES_PARA_MONTAR = PASTA_BASE / "ARTES PARA MONTAR"
ARTES_MONTADAS = PASTA_BASE / "ARTES MONTADAS"

# Aliases de compatibilidade para código que referencia os caminhos anteriores
MONTAGEM_ARTES = PASTA_BASE / "MONTAGEM ARTES MAQUINAS"
FILA_IMPRESSAO = PASTA_BASE / "FILA PARA IMPRESSAO MAQUINAS"
ONEDRIVE_UNY = PASTA_BASE

# Onde saem OS, checklist e etiquetas. Ao lado do programa, sempre — nunca
# relativo à pasta onde alguém abriu o atalho.
ETIQUETAS_GERADAS = PASTA_PROGRAMA / "etiquetas_geradas"

# O estoque (estoque.py): catálogo e histórico de movimentos. Ao lado do
# programa e fora do OneDrive — um arquivo inteiro regravado a cada
# lançamento é o caso em que o OneDrive fica com uma versão só e a outra
# evapora (ver o registro de 17 a 22/09 no CLAUDE.md).
ESTOQUE = PASTA_PROGRAMA / "estoque.json"

# Banco relacional SQLite com modo WAL para pedidos, montagens, histórico e estoque.
BANCO_DADOS = PASTA_BASE / "dados.db"

# Onde a tela de receber artes deixa o que baixou ANTES de ele confirmar
# (2026-09-21). Local e fora do OneDrive de propósito: arte que ele ainda
# pode recusar não deve ficar sincronizando, e cliente novo só nasce na
# hora de arquivar. É espera, não guarda — lote velho é apagado sozinho.
PASTA_RECEBENDO = (pathlib.Path(os.environ.get("LOCALAPPDATA") or tempfile.gettempdir())
                   / "AutomacaoGrafica" / "recebendo")


def relativo_ao_onedrive(caminho):
    """
    'EVENTOS\\REPSOL\\PRODUCAO' quando o caminho está dentro do OneDrive da
    empresa; o caminho inteiro quando não está. É o que se grava em
    configuração: o nome de usuário do Windows muda de um PC pro outro, o
    pedaço dentro do OneDrive não.
    """
    caminho = pathlib.Path(caminho)
    try:
        return str(caminho.resolve().relative_to(ONEDRIVE_UNY.resolve()))
    except ValueError:
        return str(caminho)


def resolver_do_onedrive(texto):
    """O contrário de relativo_ao_onedrive. None quando vazio."""
    if not texto:
        return None
    caminho = pathlib.Path(texto)
    return caminho if caminho.is_absolute() else ONEDRIVE_UNY / caminho


relativo_a_base = relativo_ao_onedrive
resolver_da_base = resolver_do_onedrive


def comando_python(*argumentos, com_console=True):
    """
    Como disparar uma passada de um módulo do sistema.

    Rodando do código: o python.exe (ou pythonw.exe) da mesma venv.
    QUANDO VIRAR EXECUTÁVEL, é aqui — e só aqui — que muda: o .exe vai
    chamar a si mesmo com um argumento que diz qual passada rodar.
    """
    atual = pathlib.Path(sys.executable)
    nome = "python.exe" if com_console else "pythonw.exe"
    candidato = atual.with_name(nome)
    return [str(candidato if candidato.exists() else atual), *argumentos]
