"""
Checklist de Produção — a OS do que está dentro da pasta PRODUCAO de um
evento, no MESMO padrão de sempre.

Pedido do usuário (2026-09-12): "faça um checklist de tudo que contém
dentro dessa pasta ...\\MERCADO LIVRE 26\\PRODUCAO. Atualizar a cada
movimento — se entrar algo novo, atualizar OS e Checklist."

NÃO INVENTA LAYOUT. O documento sai por 'relatorios.gerar_os' — o mesmo
gerador da OS do pedido: agrupado por material, miniatura da arte à
esquerda, quadrinho pra marcar à caneta na conferência, e a página final de
"Subtotal por material" com m² por material (nunca somado entre materiais)
e a estimativa de tempo de máquina. A única diferença é de ONDE vêm os
itens: aqui é a pasta de produção, não a pasta de entrada de um pedido.

O QUE ESTE MÓDULO ACRESCENTA é o STATUS, que vem da posição do arquivo na
árvore de pastas — e é o que faz o documento valer a pena ser regerado a
cada movimento:

  - dentro de 'Prontos'/'PRONTOS'  -> PRONTO   (já saiu da máquina)
  - dentro de 'NAO RODAR AINDA'    -> ESPERA   (não rodar ainda)
  - em qualquer outro lugar        -> A FAZER

O nome do arquivo continua sendo o banco de dados: dele saem quantidade,
material, medida e m² (mesmo leitor do resto do sistema).
"""
import collections
import datetime
import pathlib

import pymupdf

import dimensoes
import relatorios
from config import carregar_config

# Pastas cujo nome é só marcação de fluxo, não uma "máquina".
_PASTAS_PRONTO = ("PRONTOS", "PRONTO")
_MARCA_ESPERA = "NAO RODAR"

STATUS_PRONTO, STATUS_FAZER, STATUS_ESPERA = "PRONTO", "A FAZER", "ESPERA"
_ORDEM_STATUS = {STATUS_FAZER: 0, STATUS_ESPERA: 1, STATUS_PRONTO: 2}

# Cores dos selos de status, no tom dos selos que a OS já usa.
_SELOS = {
    STATUS_PRONTO: {"texto": "PRONTO", "cor": "#2d6a45", "fundo": "#e3f0e8"},
    STATUS_FAZER: {"texto": "A FAZER", "cor": "#0b5f7d", "fundo": "#e2eef4"},
    STATUS_ESPERA: {"texto": "ESPERA", "cor": "#8a5300", "fundo": "#fdf0dc"},
}

_LADO_MINIATURA = 300      # px no maior lado, igual ao que a OS já usa
_QUALIDADE_MINIATURA = 70


def _status_da_peca(partes):
    up = [p.upper() for p in partes]
    if any(_MARCA_ESPERA in p for p in up):
        return STATUS_ESPERA
    if any(p in _PASTAS_PRONTO for p in up):
        return STATUS_PRONTO
    return STATUS_FAZER


def _maquina_da_peca(subpastas):
    """Primeira subpasta que não seja marcação de status; '' se não houver."""
    for p in subpastas:
        up = p.upper()
        if up in _PASTAS_PRONTO or _MARCA_ESPERA in up:
            continue
        return p
    return ""


def miniatura(caminho_pdf, lado=_LADO_MINIATURA):
    """
    JPG da primeira página, no maior lado 'lado'. Renderiza já na escala
    final (e não em tamanho cheio pra depois reduzir): tem lona de 29 m
    nessa pasta, e render cheio delas custaria caro à toa.

    Devolve None se não der pra abrir — miniatura é conforto visual, nunca
    motivo pra o documento não sair.
    """
    try:
        doc = pymupdf.open(str(caminho_pdf))
        try:
            pagina = doc[0]
            maior = max(pagina.rect.width, pagina.rect.height) or 1
            escala = min(lado / maior, 1.0)
            px = pagina.get_pixmap(matrix=pymupdf.Matrix(escala, escala))
            return px.tobytes("jpg", jpg_quality=_QUALIDADE_MINIATURA)
        finally:
            doc.close()
    except Exception:
        return None


def inventariar(pasta_producao, config=None, com_miniatura=True):
    """
    Varre a pasta e devolve um item por PDF, no formato que
    relatorios.gerar_os espera (categoria, quantidade, arquivo, dimensao,
    thumbnail_bytes, selo), mais o que é nosso (area, maquina, status).
    Só LÊ — não move, não renomeia, não organiza nada.
    """
    config = config or carregar_config()
    typos = config.get("typos_unidade", {})
    materiais = config.get("materiais", {})
    sinonimos = config.get("sinonimos_categoria", {})
    pasta_producao = pathlib.Path(pasta_producao)

    itens = []
    for pdf in sorted(pasta_producao.rglob("*.pdf")):
        partes = pdf.relative_to(pasta_producao).parts
        nome = pdf.name
        quantidade, _ = dimensoes.extrair_quantidade(nome)      # (qtd, achou)
        categoria = dimensoes.identificar_categoria(nome.upper(), materiais, sinonimos)[0]
        dim = dimensoes.extrair_dimensoes(nome, typos)
        status = _status_da_peca(partes)

        dimensao = None
        if dim:
            dimensao = {
                "largura_m": dim["largura_m"],
                "altura_m": dim["altura_m"],
                "area_m2": dim["largura_m"] * dim["altura_m"],   # POR UNIDADE
            }

        variantes = (materiais.get(categoria) or {}).get("variantes") or []
        itens.append({
            # o que a OS lê
            "categoria": categoria,
            "quantidade": quantidade,
            "arquivo": nome,
            "dimensao": dimensao,
            "variante": dimensoes.identificar_variante(nome, variantes) if variantes else None,
            "thumbnail_bytes": miniatura(pdf) if com_miniatura else None,
            "selo": _SELOS[status],
            # o que é nosso
            "area": partes[0] if len(partes) > 1 else "(raiz)",
            "maquina": _maquina_da_peca(partes[1:-1]),
            "status": status,
            "m2_total": round(dimensao["area_m2"] * quantidade, 2) if dimensao else 0.0,
        })
    return itens


def dados_por_categoria(itens, ordem_categorias):
    """
    O resumo que a OS usa no 'Subtotal por material': m² TOTAL (já com a
    quantidade) por material. Nunca um número somando materiais diferentes.
    """
    dados = {}
    for cat in ordem_categorias:
        do_material = [i for i in itens if i["categoria"] == cat]
        dados[cat] = {
            "contem_arquivos": bool(do_material),
            "area_total_m2": round(sum(i["m2_total"] for i in do_material), 2),
        }
    return dados


def ordem_das_categorias(itens, config):
    """A ordem do config.json primeiro; o que aparecer fora dela vai no fim."""
    configurada = [c for c in config.get("ordem_unificado", [])]
    presentes = []
    for i in itens:
        if i["categoria"] and i["categoria"] not in presentes:
            presentes.append(i["categoria"])
    return ([c for c in configurada if c in presentes]
            + [c for c in presentes if c not in configurada])


def resumo(itens):
    """Contagens por status e m² por material — pro log e pra quem chamar."""
    por_status = collections.Counter(i["status"] for i in itens)
    m2 = collections.defaultdict(float)
    for i in itens:
        m2[i["categoria"] or "?"] += i["m2_total"]
    return {
        "total": len(itens),
        "unidades": sum(i["quantidade"] for i in itens),
        "prontos": por_status.get(STATUS_PRONTO, 0),
        "a_fazer": por_status.get(STATUS_FAZER, 0),
        "em_espera": por_status.get(STATUS_ESPERA, 0),
        "m2_por_material": {k: round(v, 2) for k, v in m2.items()},
    }


def gerar(pasta_saida, pasta_producao, nome_cliente="MERCADO LIVRE 26",
          nome_gerente=None, nome_produtor=None, quando=None, config=None,
          com_miniatura=True):
    """
    Escreve a OS/Checklist da pasta de produção e devolve o caminho do PDF
    (pasta_saida/'OS - <CLIENTE>.pdf', como manda a convenção da casa).
    """
    config = config or carregar_config()
    quando = quando or datetime.datetime.now()
    nome_gerente = nome_gerente or config.get("ultimo_gerente") or ""
    nome_produtor = nome_produtor or config.get("ultimo_produtor") or ""

    itens = inventariar(pasta_producao, config, com_miniatura=com_miniatura)
    ordem = ordem_das_categorias(itens, config)
    # Dentro de cada material, o que falta fazer vem primeiro — é o que a
    # produção precisa ver de relance; o que já está pronto desce.
    itens.sort(key=lambda i: (_ORDEM_STATUS.get(i["status"], 9), i["area"], i["arquivo"]))

    pasta_saida = pathlib.Path(pasta_saida)
    pasta_saida.mkdir(parents=True, exist_ok=True)

    # A OS espera a data JÁ FORMATADA (é string que entra no cabeçalho,
    # igual processamento.py faz). Mandar o datetime cru imprime
    # "2026-09-12 20:44:42.538633" no lugar de "12/09/2026 20:44:42".
    caminho = relatorios.gerar_os(
        str(pasta_saida), nome_cliente, nome_gerente, nome_produtor,
        itens, dados_por_categoria(itens, ordem), ordem,
        quando.strftime("%d/%m/%Y %H:%M:%S"),
        materiais_config=config.get("materiais", {}),
    )
    return pathlib.Path(caminho)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Gera a OS/Checklist da pasta de produção.")
    parser.add_argument("pasta", help="pasta PRODUCAO do evento")
    parser.add_argument("saida", help="pasta onde gravar a OS")
    parser.add_argument("--cliente", default="MERCADO LIVRE 26")
    args = parser.parse_args()
    caminho = gerar(args.saida, args.pasta, nome_cliente=args.cliente)
    print("Gerado:", caminho)
