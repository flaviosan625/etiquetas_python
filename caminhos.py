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
import pathlib
import sys


def _pasta_do_programa():
    """A pasta do programa: a do .exe quando empacotado, a do código quando não."""
    if getattr(sys, "frozen", False):
        return pathlib.Path(sys.executable).resolve().parent
    return pathlib.Path(__file__).resolve().parent


PASTA_PROGRAMA = _pasta_do_programa()

# O OneDrive da empresa — o mesmo em qualquer PC que tenha a conta
# sincronizada, por isso a partir da pasta do usuário e não de um nome fixo.
ONEDRIVE_UNY = pathlib.Path.home() / "OneDrive" / "UNYCOMUNICACAO"

# Cada subpasta é um cliente (ver clientes.py). Renomeada de
# "Flavio Recebimento de Artes" em 2026-09-13, a pedido do usuário: o
# recebimento é da empresa, e roda vários clientes em paralelo.
RECEBIMENTO_DE_ARTES = ONEDRIVE_UNY / "Recebimento de Artes"

EVENTOS = ONEDRIVE_UNY / "EVENTOS"

# Onde saem OS, checklist e etiquetas. Ao lado do programa, sempre — nunca
# relativo à pasta onde alguém abriu o atalho.
ETIQUETAS_GERADAS = PASTA_PROGRAMA / "etiquetas_geradas"


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
