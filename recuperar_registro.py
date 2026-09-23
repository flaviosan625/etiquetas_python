"""
Devolve ao registro as entregas que sumiram dele.

A prova de que uma entrega aconteceu NÃO é a linha do registro: é o
arquivo guardado em `Fila\\<máquina>\\Enviados`, que só chega lá depois
de entrar na hot folder. Quando as duas coisas discordam, quem manda é o
Enviados — e é daí que este módulo refaz a linha que falta.

Já foi preciso duas vezes:

  - 09 a 16/09/2026: 61 entregas (1.311 m² de lona) fora do relatório,
    recuperadas na mão. Virou a fila local do `registrar_envio`.
  - 17 a 22/09/2026: 108 entregas, com DOIS vigias antigos rodando no PC
    do RIP em paralelo com a tarefa nova. Cada um gravava direto no
    OneDrive; o arquivo é o mesmo e o OneDrive resolve conflito ficando
    com UMA versão — as linhas do outro sumiam sem erro nenhum.

Da segunda vez virou este módulo, porque na primeira a recuperação foi um
script descartável: ficou o campo `recuperado` no registro sem nada no
código que o escrevesse.

A linha refeita é marcada com `recuperado` dizendo de onde veio cada
número, e nunca se passa por linha declarada: a hora é a do arquivo em
Enviados (quando ele entrou na fila, não quando a máquina recebeu) e o
giro é o PREVISTO pela medida, não o que a máquina fez.

Sem Tk aqui: é lógica, dá pra chamar de uma tela depois.
"""
import collections
import datetime
import json
import pathlib
import re

import envio_impressao
import rasterlink_hotfolder as vigia

NOTA = ("hora = data do arquivo em Enviados (entrada na fila); giro previsto pela medida. "
        "Entrega comprovada pelo arquivo, sem linha no registro.")


# O vigia registra o arquivo com o nome que ele tem na FILA e só depois
# move pra "Enviados"; se lá já houver um com esse nome (a mesma arte
# entregue de novo), o que entra ganha um _<epoch> no fim
# (rasterlink_hotfolder._processar_arquivo_da_fila). Quem compara as duas
# listas tem que desfazer isso.
_SUFIXO_DE_COLISAO = re.compile(r"^(.*)_\d{10}(\.[^.]+)$")


def nome_no_registro(nome):
    """
    O nome com que a entrega deste arquivo FOI registrada, quando ele
    ganhou o sufixo ao entrar em "Enviados" — ou None quando não ganhou.

    Sem isto, a segunda entrega de um mesmo nome parece nunca ter sido
    registrada, e "recuperar" ela grava uma linha DUPLICADA: no relatório
    isso é material contado duas vezes, num documento que é comprovação
    pro cliente. Aconteceu em 23/09/2026, com 21 linhas.
    """
    achado = _SUFIXO_DE_COLISAO.match(nome)
    return achado.group(1) + achado.group(2) if achado else None


def _meses_dos_arquivos(arquivos):
    return sorted({datetime.datetime.fromtimestamp(a.stat().st_mtime).strftime("%Y-%m")
                   for a in arquivos})


def _ja_registradas(meses, pasta_relatorios=None):
    """Quantas linhas cada (máquina, arquivo) já tem no registro dos meses."""
    pasta = (pathlib.Path(pasta_relatorios or vigia.PASTA_RELATORIOS)
             / vigia.NOME_SUBPASTA_REGISTRO)
    contagem = collections.Counter()
    for mes in meses:
        caminho = pasta / f"{mes}.jsonl"
        if not caminho.is_file():
            continue
        for linha in caminho.read_text(encoding="utf-8").splitlines():
            if not linha.strip():
                continue
            try:
                dados = json.loads(linha)
                contagem[(dados["maquina"], dados["arquivo"])] += 1
            except (json.JSONDecodeError, KeyError, TypeError):
                continue
    return contagem


def _arquivos_enviados(pasta_fila=None, maquinas=None):
    """Tudo que está guardado em Enviados, por máquina."""
    raiz = pathlib.Path(pasta_fila or vigia.PASTA_FILA_ONEDRIVE)
    nomes = list(maquinas or vigia.MAQUINAS)
    por_maquina = {}
    for nome in nomes:
        pasta = raiz / nome / vigia.NOME_SUBPASTA_ENVIADOS
        if not pasta.is_dir():
            continue
        por_maquina[nome] = sorted((a for a in pasta.iterdir() if a.is_file()),
                                   key=lambda a: a.stat().st_mtime)
    return por_maquina


def entregas_sem_registro(pasta_fila=None, pasta_relatorios=None, maquinas=None):
    """
    O que está em Enviados e não tem linha no registro, em ordem de hora.

    Compara por (máquina, nome do arquivo) CONTANDO repetições: o mesmo
    nome entregue duas vezes no mês precisa de duas linhas — refação
    consome material igual e conta no subtotal.
    """
    por_maquina = _arquivos_enviados(pasta_fila, maquinas)
    todos = [a for lista in por_maquina.values() for a in lista]
    se_tem = _ja_registradas(_meses_dos_arquivos(todos), pasta_relatorios)

    # DUAS VOLTAS. Na primeira, cada arquivo consome a linha do seu nome
    # exato; só o que sobra tenta o nome sem o sufixo de colisão. Numa
    # volta só, um arquivo com sufixo podia tomar a linha do arquivo de
    # nome igual que ainda vinha depois, e o de nome igual — que tem
    # linha — apareceria como perdido.
    sobrou = []
    for maquina, arquivos in por_maquina.items():
        for arquivo in arquivos:
            chave = (maquina, arquivo.name)
            if se_tem[chave]:
                se_tem[chave] -= 1          # essa entrega já tem a linha dela
                continue
            sobrou.append((maquina, arquivo))

    faltando = []
    for maquina, arquivo in sobrou:
        sem_sufixo = nome_no_registro(arquivo.name)
        if sem_sufixo and se_tem[(maquina, sem_sufixo)]:
            se_tem[(maquina, sem_sufixo)] -= 1
            continue
        faltando.append({
            "maquina": maquina,
            "caminho": arquivo,
            "quando": datetime.datetime.fromtimestamp(arquivo.stat().st_mtime).replace(
                microsecond=0),
            "bytes": arquivo.stat().st_size,
        })
    faltando.sort(key=lambda e: (e["quando"], e["maquina"]))
    return faltando


def _medir(entrega, maquinas=None):
    """Mede a folha e prevê o giro — o que o vigia teria anotado."""
    pagina = vigia.medida_da_pagina(entrega["caminho"])
    girado = False
    if pagina:
        dimensao = {"largura_m": pagina[0], "altura_m": pagina[1]}
        girado = bool(envio_impressao.prever_giro(dimensao, entrega["maquina"], maquinas))
    return pagina, girado


def recuperar(pasta_fila=None, pasta_relatorios=None, maquinas=None, aplicar=False,
              logger=None):
    """
    Devolve (e, com `aplicar`, grava) as linhas que faltam.

    `aplicar=False` é ensaio: não escreve nada, só diz o que entraria —
    é assim que se confere antes, porque o registro é permanente.

    A gravação passa pelo `registrar_envio` de sempre, não por um jeito
    próprio: é ele que põe a linha na fila local, confere relendo o
    arquivo e continua conferindo por 20 dias. Recuperação gravada de
    um jeito paralelo poderia se perder do mesmo jeito que a original.
    """
    entregas = entregas_sem_registro(pasta_fila, pasta_relatorios, maquinas)
    por_dia = collections.Counter()
    gravadas = 0
    linhas = []
    for entrega in entregas:
        pagina, girado = _medir(entrega, maquinas)
        dia = entrega["quando"].date().isoformat()
        por_dia[dia] += 1
        linhas.append({**entrega, "pagina": pagina, "girado": girado, "dia": dia})
        if not aplicar:
            continue
        if vigia.registrar_envio(entrega["maquina"], entrega["caminho"], girado,
                                 pasta_relatorios=pasta_relatorios, quando=entrega["quando"],
                                 logger=logger, pagina=pagina, recuperado=NOTA):
            gravadas += 1
    return {"encontradas": len(entregas), "gravadas": gravadas,
            "por_dia": dict(sorted(por_dia.items())), "linhas": linhas}


def _resumo(resultado):
    linhas = ["%d entrega(s) em Enviados sem linha no registro." % resultado["encontradas"]]
    for dia, quantas in resultado["por_dia"].items():
        linhas.append("  %s  %3d" % (dia, quantas))
    if resultado["gravadas"]:
        linhas.append("%d linha(s) gravada(s)." % resultado["gravadas"])
    return "\n".join(linhas)


if __name__ == "__main__":
    import sys

    print(_resumo(recuperar(aplicar="--aplicar" in sys.argv, logger=None)))
