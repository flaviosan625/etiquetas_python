"""Tabela de chapas 2 × 1 m informada pelo usuário em 10/10/2026.

Preço do estoque é por chapa; o centro de custos usa o equivalente por m².
A aplicação da tabela é explícita: não substitui preços editados a cada carga.
"""
from decimal import Decimal, ROUND_HALF_UP


CRISTAL = {
    "2MM": "212.83", "3MM": "290.30", "4MM": "387.05", "5MM": "483.80",
    "6MM": "580.56", "8MM": "774.08", "10MM": "921.53",
}
CORES_ESPELHADAS = (
    "AZUL", "BRONZE", "ROSE", "CINZA", "LILAS", "LARANJA", "AMARELO",
    "ALUMINIZADO", "VERDE", "PINK", "VERMELHO",
)
CORES = ("PRETO",) + CORES_ESPELHADAS


def variantes():
    """Variantes precificadas; centavos arredondados na chapa, antes do m²."""
    resultado = []

    def adicionar(espessura, cor, valor, **extras):
        chapa = Decimal(valor).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        resultado.append(dict(espessura=espessura, cor=cor,
                              preco_m2=float(chapa / 2), **extras))

    for espessura, valor in CRISTAL.items():
        adicionar(espessura, "CRISTAL", valor)
        adicionar(espessura, "LEITOSO", Decimal(valor) * Decimal("1.08"),
                  aliases_cor=["BRANCO", "TRANSLUCIDO"])
        for cor in CORES:
            adicionar(espessura, cor, Decimal(valor) * Decimal("1.15"))
    for cor, precos in (
        ("PRATA", {"1.5MM": "192.63", "1.8MM": "225.79", "2MM": "249.77", "3MM": "327.99"}),
        ("DOURADO", {"1.5MM": "221.53", "2MM": "272.18", "3MM": "356.18"}),
    ):
        for espessura, valor in precos.items():
            adicionar(espessura, "ESPELHADO " + cor, valor, acabamento="ESPELHADO",
                      aliases_cor=[cor, cor + " ESPELHADO", "ESPELHO " + cor])
    for espessura, valor in {"2MM": "315.00", "2.5MM": "342.00"}.items():
        adicionar(espessura, "FUNDO INFINITO", valor, acabamento="FUNDO INFINITO")
    for cor in CORES_ESPELHADAS:
        adicionar("2MM", "ESPELHADO " + cor, "293.95", acabamento="ESPELHADO",
                  aliases_cor=[cor, cor + " ESPELHADO", "ESPELHO " + cor])
    return resultado


def configuracao():
    return dict(tipo="chapa", largura_cm=200, comprimento_cm=100, variantes=variantes())


def sincronizar_produtos(produtos):
    """Atualiza apenas cadastro/preços; não cria movimentos nem muda saldos."""
    novos, atualizados = 0, 0
    for variante in variantes():
        vinculo = {k: variante[k] for k in ("espessura", "cor")}
        codigo = next((c for c, p in produtos.items()
                       if p.get("categoria_vinculada") == "ACRILICO"
                       and all((p.get("variante_vinculada") or {}).get(k) == v
                               for k, v in vinculo.items())), None)
        if codigo is None:
            codigo = "ACRILICO_" + variante["espessura"].replace(".", "_") + "_" + variante["cor"].replace(" ", "_")
            if codigo in produtos:
                raise ValueError(f"Código já utilizado por outro produto: {codigo}")
            produtos[codigo] = dict(minimo=0, maximo=0, codigo_planilha=None)
            novos += 1
        else:
            atualizados += 1
        produtos[codigo].update(
            descricao=f"Acrílico {variante['espessura'].replace('MM', 'mm')} {variante['cor'].title()} 2x1m",
            tipo="chapa", unidade="chapa", categoria_vinculada="ACRILICO",
            variante_vinculada=vinculo, largura_cm=200, comprimento_cm=100,
            custo=float(Decimal(str(variante["preco_m2"])) * 2),
        )
    return dict(novos=novos, atualizados=atualizados)


def cadastrar(config, estoque):
    """Importa a tabela preservando outros materiais, variantes e histórico."""
    material = config.setdefault("materiais", {}).setdefault("ACRILICO", {})
    atuais = material.setdefault("variantes", [])
    for nova in variantes():
        existente = next((v for v in atuais if
                          (v.get("espessura"), v.get("cor")) == (nova["espessura"], nova["cor"])), None)
        if existente is None:
            atuais.append(nova)
        else:
            existente.update(nova)
    material.update(tipo="chapa", largura_cm=200, comprimento_cm=100)
    return sincronizar_produtos(estoque.setdefault("produtos", {}))
