"""
Envio das OS (Ordem de Serviço) geradas pra uma pasta fora do PC —
por padrão, a pasta do OneDrive já usada pelo negócio — sem apagar
nada localmente. Só o PDF da OS (nunca o checklist inteiro — miniaturas,
muito mais pesado, e o checklist marcado à caneta na produção não tem
por que sair do PC). Os arquivos JSON que acompanham a OS (usados só
internamente pelo controle de estoque — ver relatorios.salvar_dados_os)
NÃO são enviados (decisão do usuário, 2026-08-26): quem abre essa pasta
de fora quer ver a OS, não um arquivo de log/máquina.

Decisão do usuário (2026-08-25): mandar é sempre uma ação manual, com
confirmação antes de copiar — nunca acontece sozinho ao gerar uma OS
nova, mesmo espírito já usado no resto do sistema (baixa de estoque
também é sempre manual e sempre com prévia antes de confirmar).

Organização dentro da pasta de destino (2026-08-26): material chega
aos poucos, o mesmo cliente pode gerar várias pastas de pedido ao
longo do tempo (uma por rodada de processamento — ver
estado_pedido.py) — cada uma vira uma SUBPASTA dentro da pasta do
CLIENTE, nunca pastas soltas misturadas. Precisa da subpasta por
pedido porque o nome do arquivo da OS se repete a cada rodada
("OS - CLIENTE.pdf"); sem isso, o pedido mais novo sobrescreveria o
mais antigo no mesmo destino. O nome da subpasta é só a data/hora (ver
utils.data_hora_da_pasta) — o nome do cliente já não precisa repetir,
é a pasta de fora — com hora e segundo incluídos de propósito: mais de
um pedido do mesmo cliente pode acontecer no mesmo dia, só a data
sozinha colidiria.

A pasta de cliente reaproveita uma já existente no destino, comparando
sem diferença de espaço (ver utils.chave_comparacao_cliente) — mesmo
problema real já visto no processamento local (cliente digitado
"SUPERBET" numa vez e "Super Bet" noutra não pode virar duas pastas
de cliente diferentes aqui também).
"""
import pathlib
import shutil

from utils import chave_comparacao_cliente, data_hora_da_pasta, nome_cliente_da_pasta

PASTA_DESTINO_PADRAO = pathlib.Path.home() / "OneDrive" / "UNYCOMUNICACAO" / "Ordem de Serviço"


def _arquivos_os(pasta_pedido):
    """Só o PDF da OS ('OS - CLIENTE.pdf') — nunca os JSON que acompanham (esses ficam só localmente, ver módulo)."""
    return sorted(pathlib.Path(pasta_pedido).glob("OS - *.pdf"))


def _pasta_cliente_no_destino(pasta_destino, nome_cliente):
    """
    Acha, dentro de 'pasta_destino', uma pasta de cliente já existente
    cujo nome bate com 'nome_cliente' ignorando diferença de espaço. Se
    achar, devolve o nome dela como já está lá (preserva a grafia que
    já foi usada da primeira vez); senão, devolve 'nome_cliente' como
    veio — vira a grafia canônica pra esse cliente dali em diante.
    """
    pasta_destino = pathlib.Path(pasta_destino)
    chave_alvo = chave_comparacao_cliente(nome_cliente)
    if pasta_destino.exists():
        for pasta_existente in pasta_destino.iterdir():
            if pasta_existente.is_dir() and chave_comparacao_cliente(pasta_existente.name) == chave_alvo:
                return pasta_existente.name
    return nome_cliente


def _resolver_nomes_clientes(nomes_pasta_pedido, pasta_destino):
    """
    Decide o nome de pasta de cliente pra cada pasta de pedido, o lote
    inteiro de uma vez — não um de cada vez isolado. Isso importa
    quando dois pedidos do MESMO cliente, digitados com espaço
    diferente (ex: "SUPERBET" e "Super Bet"), aparecem juntos e NENHUM
    dos dois foi enviado antes: olhando um de cada vez, cada um cairia
    numa grafia diferente (nenhum acha o outro no disco, porque nenhum
    foi criado ainda). Resolvendo o lote junto, o primeiro que aparece
    decide a grafia, e o resto do lote (mesmo sem nada no destino
    ainda) reaproveita essa decisão.
    """
    chave_ja_resolvida = {}
    resolvido = {}
    for nome_pasta in nomes_pasta_pedido:
        nome_bruto = nome_cliente_da_pasta(nome_pasta)
        chave = chave_comparacao_cliente(nome_bruto)
        if chave not in chave_ja_resolvida:
            chave_ja_resolvida[chave] = _pasta_cliente_no_destino(pasta_destino, nome_bruto)
        resolvido[nome_pasta] = chave_ja_resolvida[chave]
    return resolvido


def listar_pedidos(pasta_saida_base="etiquetas_geradas", pasta_destino=PASTA_DESTINO_PADRAO):
    """
    Lista cada pasta de pedido em 'pasta_saida_base' que tem pelo menos
    um arquivo de OS, com o tamanho total desses arquivos e se já foram
    todos enviados antes (checando se já existe, com o mesmo nome, na
    pasta de destino — não precisa de nenhum estado novo pra isso).
    """
    base = pathlib.Path(pasta_saida_base)
    if not base.exists():
        return []

    pastas_com_os = [
        (p, _arquivos_os(p)) for p in sorted(base.iterdir(), reverse=True) if p.is_dir()
    ]
    pastas_com_os = [(p, arquivos) for p, arquivos in pastas_com_os if arquivos]
    nomes_clientes = _resolver_nomes_clientes([p.name for p, _ in pastas_com_os], pasta_destino)

    pedidos = []
    for pasta_pedido, arquivos in pastas_com_os:
        nome_cliente = nomes_clientes[pasta_pedido.name]
        nome_subpasta = data_hora_da_pasta(pasta_pedido.name)
        pasta_destino_pedido = pathlib.Path(pasta_destino) / nome_cliente / nome_subpasta
        ja_enviados = all((pasta_destino_pedido / a.name).exists() for a in arquivos)

        pedidos.append({
            "pasta": pasta_pedido,
            "nome": pasta_pedido.name,
            "cliente": nome_cliente,
            "subpasta": nome_subpasta,
            "arquivos": arquivos,
            "tamanho_bytes": sum(a.stat().st_size for a in arquivos),
            "ja_enviado": ja_enviados,
        })
    return pedidos


def enviar_os(pedidos_selecionados, pasta_destino=PASTA_DESTINO_PADRAO):
    """
    Copia (nunca move — o arquivo local continua existindo, inclusive
    porque a tela de baixa de estoque lê o JSON da OS direto da pasta
    local) os arquivos de OS de cada pedido selecionado pra
    'pasta_destino/CLIENTE/DD-MM-AAAA HH-MM-SS/' — agrupado por
    cliente (reaproveitando a pasta já existente, mesmo que o nome
    tenha sido digitado com espaço diferente dessa vez — ver
    _pasta_cliente_no_destino), com uma subpasta por pedido pra nunca
    um sobrescrever o outro. Quem chama já deve ter confirmado com o
    usuário antes de invocar isso — essa função não pede confirmação
    nenhuma, só executa.

    Devolve um resumo por pedido: quantos arquivos copiados e o erro
    de qualquer arquivo que falhar (não interrompe os demais).
    """
    pasta_destino = pathlib.Path(pasta_destino)
    resumo = []
    for pedido in pedidos_selecionados:
        nome_cliente = pedido.get("cliente") or _pasta_cliente_no_destino(pasta_destino, nome_cliente_da_pasta(pedido["nome"]))
        nome_subpasta = pedido.get("subpasta") or data_hora_da_pasta(pedido["nome"])
        pasta_destino_pedido = pasta_destino / nome_cliente / nome_subpasta
        copiados = []
        erros = []
        try:
            pasta_destino_pedido.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            resumo.append({"nome": pedido["nome"], "copiados": [], "erros": [f"Não foi possível criar a pasta de destino: {e}"]})
            continue

        for arquivo in pedido["arquivos"]:
            try:
                shutil.copy2(str(arquivo), str(pasta_destino_pedido / arquivo.name))
                copiados.append(arquivo.name)
            except OSError as e:
                erros.append(f"{arquivo.name}: {e}")

        resumo.append({"nome": pedido["nome"], "copiados": copiados, "erros": erros})
    return resumo
