"""
Checklist de etiquetas (meia A4) da pasta de produção — só do que é NOVO.

Pedido do usuário (2026-09-12): "o checklist não atualiza; ele precisa,
quando entrar material novo, cruzar com a lista antiga e gerar um novo
checklist, pra eu imprimir as etiquetas sem repetir".

NÃO REDESENHA NADA. Quem monta é o gerador de sempre —
`processamento.processar_etiquetas` — então o documento sai idêntico ao de
qualquer pedido: etiqueta meia A4 (2 por folha), banner de categoria, OS
junto, e o `Checklist <CLIENTE>.pdf` na pasta
`etiquetas_geradas/<CLIENTE>_<data_hora>/`. Ver a regra "OS e Checklist são
MODELOS PADRÃO" no CLAUDE.md.

COMO O "SEM REPETIR" FUNCIONA
Um arquivo de estado guarda o NOME de cada arte que já virou etiqueta. A
cada rodada, só o que não está nessa lista é entregue ao gerador — e como
cada rodada cria a sua própria pasta, o checklist daquele lote tem só as
etiquetas novas. A chave é o NOME do arquivo, não o caminho: quando a arte
vai de 'UV' pra 'UV/PRONTOS' ela continua sendo a mesma peça já impressa, e
não pode voltar a gerar etiqueta.

POR QUE HARDLINK, E NÃO CÓPIA
`processar_etiquetas` escreve na pasta de entrada que recebe (renomeia pro
padrão da casa e cria subpasta de reduzidos). Apontá-lo pra PRODUCAO
escreveria dentro da produção — proibido, e ainda por cima a organização
automática está congelada. Copiar também não serve: a pasta tem 1,1 GB.
Hardlink resolve os dois: é instantâneo, não ocupa espaço nenhum, e o que o
gerador faz no link (renomear) não toca no arquivo original. Se o hardlink
não der (volume diferente, arquivo ainda só na nuvem do OneDrive), cai pra
cópia daquele arquivo só.
"""
import datetime
import json
import os
import pathlib
import shutil
import tempfile

import caminhos
import processamento
from config import carregar_config

NOME_ESTADO = "checklist_impressos.json"


def _ler_estado(caminho_estado):
    try:
        dados = json.loads(pathlib.Path(caminho_estado).read_text(encoding="utf-8"))
        return set(dados.get("ja_impressos", []))
    except (OSError, json.JSONDecodeError):
        return set()


def _gravar_estado(caminho_estado, ja_impressos, lote):
    caminho_estado = pathlib.Path(caminho_estado)
    caminho_estado.parent.mkdir(parents=True, exist_ok=True)
    caminho_estado.write_text(json.dumps({
        "ja_impressos": sorted(ja_impressos),
        "ultimo_lote": lote,
    }, ensure_ascii=False, indent=2), encoding="utf-8")


def artes_novas(pasta_producao, caminho_estado):
    """
    As artes que ainda não viraram etiqueta, na ordem da pasta.

    Identifica pelo NOME do arquivo: a mesma peça muda de pasta quando vai
    pra 'Prontos', e isso não a torna nova de novo.
    """
    ja = _ler_estado(caminho_estado)
    novas, vistos = [], set()
    for pdf in sorted(pathlib.Path(pasta_producao).rglob("*.pdf")):
        if pdf.name in ja or pdf.name in vistos:
            continue
        vistos.add(pdf.name)
        novas.append(pdf)
    return novas


def _entregar(origem, destino):
    """Hardlink quando dá; cópia quando não dá. Nunca mexe no original."""
    try:
        os.link(str(origem), str(destino))
        return "link"
    except OSError:
        shutil.copy2(str(origem), str(destino))
        return "copia"


def arquivo_estado(cliente):
    """
    A lista do que já virou etiqueta mora na pasta do CLIENTE, nunca em
    etiquetas_geradas: aquela pasta é saída e o usuário apaga cliente de lá
    quando o trabalho termina ("preciso manter somente o que está em
    andamento", 2026-09-13). Em 2026-09-13 ela estava lá e foi pra Lixeira
    numa limpeza — o próximo lote teria reimpresso as 50 etiquetas.
    """
    return cliente.pasta_sistema / NOME_ESTADO


def artes_novas_do_cliente(cliente):
    if not cliente.producao_existe:
        return []
    return artes_novas(cliente.pasta_producao, arquivo_estado(cliente))


def gerar_lote_do_cliente(cliente, config=None, on_log=None):
    """O lote de um cliente do cadastro: produção, nome e memória vêm dele."""
    if not cliente.producao_existe:
        return {"gerou": False, "quantidade": 0, "arquivos": [],
                "motivo": "o cliente não tem pasta de produção configurada"}
    return gerar_lote(cliente.pasta_producao, cliente.documento,
                      caminho_estado=arquivo_estado(cliente), config=config, on_log=on_log)


def gerar_lote(pasta_producao, nome_cliente, *, caminho_estado,
               pasta_saida_base=None, config=None,
               nome_gerente=None, nome_produtor=None, on_log=None):
    """
    Monta o checklist do que é novo e devolve um resumo:
    {gerou, quantidade, arquivos, pasta_saida, checklist, os, motivo}.

    Não gera nada quando não há arte nova — é o caso comum, e criar uma
    pasta de pedido vazia só sujaria 'etiquetas_geradas'.

    'caminho_estado' é obrigatório de propósito: não existe mais um lugar
    "padrão" dentro de etiquetas_geradas pra ele cair calado (ver
    arquivo_estado).

    O estado só é atualizado se o gerador tiver ido até o fim: se ele
    falhar no meio, as artes continuam "não impressas" e entram no próximo
    lote, em vez de sumirem sem nunca virar etiqueta.
    """
    config = config or carregar_config()
    pasta_producao = pathlib.Path(pasta_producao)
    caminho_estado = pathlib.Path(caminho_estado)
    pasta_saida_base = pathlib.Path(pasta_saida_base or caminhos.ETIQUETAS_GERADAS)
    nome_gerente = nome_gerente or config.get("ultimo_gerente") or ""
    nome_produtor = nome_produtor or config.get("ultimo_produtor") or ""

    novas = artes_novas(pasta_producao, caminho_estado)
    if not novas:
        return {"gerou": False, "quantidade": 0, "arquivos": [],
                "motivo": "nenhuma arte nova desde o último checklist"}

    # A entrada é uma pasta temporária FORA da produção: é nela que o
    # gerador pode renomear e criar subpasta à vontade.
    staging = pathlib.Path(tempfile.mkdtemp(prefix="checklist_lote_"))
    try:
        for arte in novas:
            _entregar(arte, staging / arte.name)

        resultado = processamento.processar_etiquetas(
            str(staging), nome_cliente, nome_gerente, nome_produtor, config,
            pasta_saida_base=str(pasta_saida_base), on_log=on_log,
        )
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    if not resultado or not resultado.get("unificado"):
        return {"gerou": False, "quantidade": len(novas),
                "arquivos": [a.name for a in novas],
                "motivo": "o gerador não produziu checklist (nada foi marcado como impresso)"}

    nomes = [a.name for a in novas]
    _gravar_estado(caminho_estado, _ler_estado(caminho_estado) | set(nomes), {
        "quando": datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "quantidade": len(nomes),
        "pasta": resultado.get("pasta_saida"),
        "artes": nomes,
    })
    return {
        "gerou": True,
        "quantidade": len(nomes),
        "arquivos": nomes,
        "pasta_saida": resultado.get("pasta_saida"),
        "checklist": resultado.get("unificado"),
        "os": resultado.get("os"),
        "motivo": None,
    }


if __name__ == "__main__":
    import argparse
    import clientes

    parser = argparse.ArgumentParser(
        description="Gera o checklist de etiquetas só do que entrou de novo na produção.")
    parser.add_argument("--cliente", required=True,
                        help='nome do cliente em Recebimento de Artes (ex.: "Mercado Livre")')
    args = parser.parse_args()

    cliente = clientes.obter(args.cliente)
    if cliente is None:
        raise SystemExit('Não existe o cliente "%s" em %s' % (args.cliente, caminhos.RECEBIMENTO_DE_ARTES))

    def registrar(nivel, texto):
        print("[%-4s] %s" % (nivel, texto), flush=True)

    r = gerar_lote_do_cliente(cliente, on_log=registrar)
    print()
    if r["gerou"]:
        print("Checklist do lote: %s" % r["checklist"])
        print("Etiquetas novas..: %d" % r["quantidade"])
    else:
        print("Nada a fazer: %s" % r["motivo"])
