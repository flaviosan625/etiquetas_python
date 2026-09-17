"""
Custo de material de uma OS — o valor que vai na cópia da GERÊNCIA.

Pedido do usuário (2026-09-14): "vamos fazer o custo por evento, colocar os
valores no rodapé da OS". Decisões dele, tomadas vendo a prévia:
  - só numa CÓPIA DA GERÊNCIA — a OS impressa pra produção sai igual;
  - custo = PEÇAS + SOBRA do rolo/chapa (o material que sai de verdade);
  - preço POR ESPESSURA/COR quando o material tem variante.

A CÓPIA NÃO SE CHAMA "OS - ..."
Chama "CUSTOS - <CLIENTE>.pdf" de propósito. A tela "Imprimir OS/Checklist
de um pedido" (gui._pedidos_para_impressao) e o arquivamento
(arquivamento._arquivos_os) acham OS procurando "OS - *.pdf". Com o nome de
OS, a cópia com os valores apareceria na lista de impressão da produção.
Um teste trava isso.

A CONTA
Pra cada peça: a área dela e a sobra estimada, pela MESMA conta que o
sistema já usa pro desperdício (processamento._acumular_consumo_categoria),
vezes o preço por m² cadastrado pra aquele material/espessura. Material
composto ("PS ADESIVADO") consome também o material extra, ao preço dele.

VALOR EM REAIS SOMA ENTRE MATERIAIS — é a mesma moeda. O que nunca se soma
é m² de materiais diferentes (regra da casa), e isso continua separado.

NÚMERO DEDUZIDO NÃO SE PASSA POR DECLARADO (regra da casa): a sobra é
estimativa e sai escrita como "sobra est."; material sem preço cadastrado
não vira zero calado — o total sai marcado como PARCIAL e diz o que falta.

É SÓ MATERIAL: não inclui tinta, máquina nem mão de obra. A cópia diz isso.
"""
import os
import pathlib

PREFIXO_ARQUIVO = "CUSTOS - "


def nome_arquivo(nome_cliente):
    return "%s%s.pdf" % (PREFIXO_ARQUIVO, str(nome_cliente).upper())


def _positivo(valor):
    try:
        numero = float(str(valor).replace(",", "."))
    except (TypeError, ValueError):
        return None
    return numero if numero > 0 else None


def _mesma_variante(cadastrada, da_peca):
    return ((cadastrada.get("espessura") or "") == (da_peca.get("espessura") or "")
            and (cadastrada.get("cor") or "") == (da_peca.get("cor") or ""))


def preco_m2(materiais, categoria, variante=None):
    """
    Preço por m² da peça. Com variante: o preço daquela espessura/cor; se
    ela não tiver preço, o do material. Sem nada cadastrado: None.

    Compara a variante pelo que ela É (espessura e cor), e não pelo objeto:
    item de rodada anterior vem do estado_pedido.json, com uma cópia da
    variante gravada antes de o preço existir.
    """
    info = (materiais or {}).get(categoria) or {}
    if variante:
        for cadastrada in info.get("variantes") or []:
            if _mesma_variante(cadastrada, variante):
                preco = _positivo(cadastrada.get("preco_m2"))
                if preco is not None:
                    return preco
                break
    return _positivo(info.get("preco_m2"))


def tem_algum_preco(materiais):
    for info in (materiais or {}).values():
        if _positivo(info.get("preco_m2")) is not None:
            return True
        if any(_positivo(v.get("preco_m2")) is not None for v in info.get("variantes") or []):
            return True
    return False


def assinatura_precos(materiais):
    """
    Resumo dos preços cadastrados. O vigia do checklist compara isto com a
    última passada: preço mudou = a cópia de custos está com valor velho e
    precisa sair de novo, mesmo sem nada mexer na pasta de produção.
    Vazia ("") quando não há preço nenhum — aí não há cópia pra atualizar.
    """
    import hashlib

    precos = []
    for categoria, info in sorted((materiais or {}).items()):
        if _positivo(info.get("preco_m2")) is not None:
            precos.append("%s|%s" % (categoria, _positivo(info["preco_m2"])))
        for v in info.get("variantes") or []:
            if _positivo(v.get("preco_m2")) is not None:
                precos.append("%s|%s|%s|%s" % (categoria, v.get("espessura"), v.get("cor") or "",
                                                _positivo(v["preco_m2"])))
    return hashlib.sha256("\n".join(precos).encode("utf-8")).hexdigest() if precos else ""


def _descricao(categoria, variante):
    from dimensoes import formatar_variante
    return "%s %s" % (categoria, formatar_variante(variante)) if variante else categoria


def calcular(itens, materiais):
    """
    {'por_material': {cat: {area_pecas_m2, area_sobra_m2, valor, completo}},
     'total', 'completo', 'faltando_preco': [descrições]}
    """
    from processamento import _acumular_consumo_categoria

    por_material, faltando = {}, []

    def consumir(categoria, variante, dimensao, quantidade):
        info = (materiais or {}).get(categoria)
        if not info or not dimensao:
            return
        acumulado = {"area_total_m2": 0.0, "area_desperdicio_m2": 0.0,
                     "comprimento_rolo_usado_m": 0.0, "chapas_extras": 0}
        _acumular_consumo_categoria(acumulado, info, dimensao, quantidade)

        linha = por_material.setdefault(categoria, {
            "area_pecas_m2": 0.0, "area_sobra_m2": 0.0, "valor": 0.0, "completo": True})
        linha["area_pecas_m2"] += acumulado["area_total_m2"]
        linha["area_sobra_m2"] += acumulado["area_desperdicio_m2"]

        preco = preco_m2(materiais, categoria, variante)
        if preco is None:
            linha["completo"] = False
            descricao = _descricao(categoria, variante)
            if descricao not in faltando:
                faltando.append(descricao)
            return
        linha["valor"] += (acumulado["area_total_m2"] + acumulado["area_desperdicio_m2"]) * preco

    for item in itens:
        quantidade = item.get("quantidade") or 1
        consumir(item.get("categoria"), item.get("variante"), item.get("dimensao"), quantidade)
        if item.get("categoria_extra"):
            # a peça é uma só; o material composto consome os dois
            consumir(item["categoria_extra"], None, item.get("dimensao"), quantidade)

    for linha in por_material.values():
        for chave in ("area_pecas_m2", "area_sobra_m2", "valor"):
            linha[chave] = round(linha[chave], 2)
    return {
        "por_material": por_material,
        "total": round(sum(l["valor"] for l in por_material.values()), 2),
        "completo": not faltando,
        "faltando_preco": faltando,
    }


def formatar_reais(valor):
    """49157.64 -> 'R$ 49.157,64'."""
    inteiro, _, centavos = ("%.2f" % float(valor)).partition(".")
    negativo = inteiro.startswith("-")
    inteiro = inteiro.lstrip("-")
    grupos = []
    while len(inteiro) > 3:
        grupos.insert(0, inteiro[-3:])
        inteiro = inteiro[:-3]
    grupos.insert(0, inteiro)
    return "%sR$ %s,%s" % ("-" if negativo else "", ".".join(grupos), centavos)


def gerar_copia(pasta_saida, nome_cliente, nome_gerente, nome_produtor,
                itens, dados_categorias, ordem_categorias, data_hora_atual, materiais):
    """
    Escreve a cópia da gerência ao lado da OS e devolve o caminho — ou None
    quando nenhum preço está cadastrado. Nesse caso também apaga uma cópia
    antiga, se houver: valor de preço que não existe mais seria pior que
    nenhum valor.
    """
    from relatorios import gerar_os

    destino = pathlib.Path(pasta_saida) / nome_arquivo(nome_cliente)
    if not tem_algum_preco(materiais):
        try:
            destino.unlink()
        except OSError:
            pass
        return None

    return gerar_os(
        str(pasta_saida), nome_cliente, nome_gerente, nome_produtor,
        itens, dados_categorias, ordem_categorias, data_hora_atual, materiais,
        custos=calcular(itens, materiais), nome_arquivo=destino.name,
    )
