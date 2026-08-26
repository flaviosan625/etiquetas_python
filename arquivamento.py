"""
Envio das OS (Ordem de Serviço) geradas pra uma pasta fora do PC —
por padrão, a pasta do OneDrive já usada pelo negócio — sem apagar
nada localmente. Só as OS (PDF + JSON, tudo que começa com "OS - "),
nunca o checklist inteiro (miniaturas, muito mais pesado, e o
checklist marcado à caneta na produção não tem por que sair do PC).

Decisão do usuário (2026-08-25): mandar é sempre uma ação manual, com
confirmação antes de copiar — nunca acontece sozinho ao gerar uma OS
nova, mesmo espírito já usado no resto do sistema (baixa de estoque
também é sempre manual e sempre com prévia antes de confirmar).
"""
import pathlib
import shutil

PASTA_DESTINO_PADRAO = pathlib.Path.home() / "OneDrive" / "UNYCOMUNICACAO" / "Ordem de Serviço"


def _arquivos_os(pasta_pedido):
    """Todo arquivo da pasta que começa com 'OS - ' (PDF da OS + os JSON, legado e por rodada)."""
    return sorted(pathlib.Path(pasta_pedido).glob("OS - *"))


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

    pedidos = []
    for pasta_pedido in sorted(base.iterdir(), reverse=True):
        if not pasta_pedido.is_dir():
            continue
        arquivos = _arquivos_os(pasta_pedido)
        if not arquivos:
            continue

        pasta_destino_pedido = pathlib.Path(pasta_destino) / pasta_pedido.name
        ja_enviados = all((pasta_destino_pedido / a.name).exists() for a in arquivos)

        pedidos.append({
            "pasta": pasta_pedido,
            "nome": pasta_pedido.name,
            "arquivos": arquivos,
            "tamanho_bytes": sum(a.stat().st_size for a in arquivos),
            "ja_enviado": ja_enviados,
        })
    return pedidos


def enviar_os(pedidos_selecionados, pasta_destino=PASTA_DESTINO_PADRAO):
    """
    Copia (nunca move — o arquivo local continua existindo, inclusive
    porque a tela de baixa de estoque lê o JSON da OS direto da pasta
    local) os arquivos de OS de cada pedido selecionado pra uma
    subpasta com o mesmo nome do pedido dentro de 'pasta_destino'.
    Quem chama já deve ter confirmado com o usuário antes de invocar
    isso — essa função não pede confirmação nenhuma, só executa.

    Devolve um resumo por pedido: quantos arquivos copiados e o erro
    de qualquer arquivo que falhar (não interrompe os demais).
    """
    pasta_destino = pathlib.Path(pasta_destino)
    resumo = []
    for pedido in pedidos_selecionados:
        pasta_destino_pedido = pasta_destino / pedido["nome"]
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
