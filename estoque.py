"""
Controle de estoque de materiais: catálogo de produtos, movimentos
(entrada/saída/ajuste) e saldo sempre calculado a partir do histórico
— nunca um número solto guardado à parte, senão um lançamento errado
não teria como ser desfeito de forma confiável.

Arquivo separado do config.json de propósito: estoque muda a cada
pedido, configuração muda raramente. Se o estoque.json corromper, a
recuperação (que recria do zero) não some com a configuração dos
materiais junto — e vice-versa.

Catálogo baseado na planilha real de controle de estoque da empresa
(materiais → cad produtos), com os produtos e variantes confirmados
para acompanhamento: Lona Fosca Front 440g 3,20m, Adesivo 1,27m
(Branco Fosco / Preto Fosco / Cristal / Vinil Jateado), MDF cru
6/9/15mm, PVC 3/10/20mm × Branco/Preto, PS 1/2/3mm × Branco/Preto,
Acrílico 1-10mm × Cristal/Leitoso, além dos insumos (tintas, máscaras,
ilhós) já cadastrados na planilha. Todo produto começa com saldo ZERO
— os volumes reais são lançados do zero via entrada manual, não
importados da planilha (decisão do usuário: a planilha pode estar
desatualizada, prefere um levantamento físico novo).

O arquivo mora em caminhos.ESTOQUE (lido na hora do uso, pra teste poder
apontar pra outro lugar — um teste distraído já apagou o estoque real).

ROLO: saldo em rolos, com fração. Cada baixa pela OS é um movimento com a
fração de rolo que o pedido gastou (12,40 m de um rolo de 50 m = −0,248),
então 2,752 rolos quer dizer dois fechados e um aberto com 37,60 m. Até
28/09/2026 os metros do rolo aberto ficavam num contador solto
('acumulado_m') e só virava movimento quando um rolo inteiro fechava:
pedido pequeno não deixava rastro no histórico, não dava pra desfazer e o
aviso de baixa repetida não enxergava. O contador antigo, se houver, vira
um ajuste na primeira carga (ver carregar_estoque).
"""
import copy
import json
import math
import re
from datetime import datetime

import caminhos
from aproveitamento import consumo_por_material
import custos_tinta


def _produto_rolo(descricao, categoria, comprimento_rolo_m, minimo=0, maximo=0, codigo_planilha=None, custo=None):
    return {
        "descricao": descricao, "tipo": "rolo", "unidade": "rolo",
        "comprimento_rolo_m": comprimento_rolo_m,
        "categoria_vinculada": categoria, "variante_vinculada": None,
        "minimo": minimo, "maximo": maximo, "codigo_planilha": codigo_planilha,
        "custo": custo,  # R$ por rolo — None quando ainda não informado (ver [[project-backlog-ideas]])
    }


def _produto_chapa(descricao, categoria, variante, minimo=0, maximo=0, codigo_planilha=None, custo=None):
    return {
        "descricao": descricao, "tipo": "chapa", "unidade": "chapa",
        "categoria_vinculada": categoria, "variante_vinculada": variante,
        "minimo": minimo, "maximo": maximo, "codigo_planilha": codigo_planilha,
        "custo": custo,  # R$ por chapa — None quando ainda não informado
    }


def _produto_insumo(descricao, unidade="un", minimo=0, maximo=0, codigo_planilha=None, capacidade_ml=None, custo=None):
    produto = {
        "descricao": descricao, "tipo": "insumo", "unidade": unidade,
        "categoria_vinculada": None, "variante_vinculada": None,
        "minimo": minimo, "maximo": maximo, "codigo_planilha": codigo_planilha,
        "custo": custo,  # R$ por unidade — None quando ainda não informado
    }
    # só as tintas usam isso — quantos mL tem 1 unidade (frasco) do
    # produto, pra converter "quantos frascos saíram" em "quantos mL
    # foram consumidos" na hora de calcular o rendimento por máquina
    if capacidade_ml:
        produto["capacidade_ml"] = capacidade_ml
    return produto


# Regra do usuário (2026-08-19): tudo que é ADESIVO sai pela Plotter UV
# UJV100-160, tudo que é LONA sai pela SWJ-320EA. Essa ligação categoria
# → máquina é o que permite calcular o rendimento real de tinta (mL/m²)
# de cada máquina — não existe um número fixo publicado pelo fabricante
# (a Mimaki não divulga isso, depende da cobertura de cada arte), então
# calculamos empiricamente cruzando tinta consumida com m² produzido no
# mesmo período. Ver `rendimento_tinta_mensal`.
MAQUINA_POR_CATEGORIA = {
    "LONA": "SWJ-320EA",
    "ADESIVO": "UJV100-160",
}
TINTAS_POR_MAQUINA = {
    "UJV100-160": ["TINTA_UV_160_CIANO", "TINTA_UV_160_MAGENTA", "TINTA_UV_160_YELLOW", "TINTA_UV_160_BLACK"],
    "SWJ-320EA": ["TINTA_SWJ_320_CIANO", "TINTA_SWJ_320_MAGENTA", "TINTA_SWJ_320_YELLOW", "TINTA_SWJ_320_BLACK"],
    custos_tinta.R5200: [custos_tinta.codigo_produto(custos_tinta.R5200, cor) for cor in custos_tinta.CORES],
    custos_tinta.H2525: [custos_tinta.codigo_produto(custos_tinta.H2525, cor) for cor in custos_tinta.CORES],
}


def _catalogo_padrao():
    catalogo = {
        # ---- ROLO (LONA / ADESIVO) ----
        "LONA_FOSCA_440_320": _produto_rolo(
            "Lona Fosca Front 440g 3,20x50m", "LONA", 50, minimo=6, maximo=60, custo=1250.00,
        ),
        "ADESIVO_BRANCO_FOSCO_127": _produto_rolo(
            "Adesivo Branco Fosco 1,27x50m", "ADESIVO", 50, minimo=3, maximo=60,
        ),
        "ADESIVO_PRETO_FOSCO_127": _produto_rolo(
            "Adesivo Preto Fosco 1,27x50m", "ADESIVO", 50, minimo=3, maximo=60, codigo_planilha="5C_025",
        ),
        "ADESIVO_CRISTAL_127": _produto_rolo(
            "Adesivo Cristal (transparente) 1,27x50m", "ADESIVO", 50, minimo=3, maximo=60,
        ),
        "VINIL_JATEADO_127": _produto_rolo(
            "Vinil Jateado 1,27x50m", "ADESIVO", 50, minimo=6, maximo=60, codigo_planilha="5C_040",
        ),

        # ---- CHAPA — MDF (cru) ----
        "MDF_6MM": _produto_chapa("MDF 6mm", "MDF", {"espessura": "6MM"}, minimo=10, maximo=60, codigo_planilha="5C_055"),
        "MDF_9MM": _produto_chapa("MDF 9mm", "MDF", {"espessura": "9MM"}, minimo=10, maximo=60, codigo_planilha="5C_056"),
        "MDF_15MM": _produto_chapa("MDF 15mm", "MDF", {"espessura": "15MM"}, minimo=10, maximo=60, codigo_planilha="5C_057"),

        # ---- CHAPA — PVC ----
        "PVC_3MM_BRANCO": _produto_chapa("PVC 3mm Branco", "PVC", {"espessura": "3MM", "cor": "BRANCO"}, minimo=10, maximo=10, codigo_planilha="5C_005"),
        "PVC_3MM_PRETO": _produto_chapa("PVC 3mm Preto", "PVC", {"espessura": "3MM", "cor": "PRETO"}, minimo=3, maximo=10),
        "PVC_10MM_BRANCO": _produto_chapa("PVC 10mm Branco", "PVC", {"espessura": "10MM", "cor": "BRANCO"}, minimo=10, maximo=15, codigo_planilha="5C_006", custo=280.00),
        "PVC_10MM_PRETO": _produto_chapa("PVC 10mm Preto", "PVC", {"espessura": "10MM", "cor": "PRETO"}, minimo=3, maximo=8, codigo_planilha="5C_008", custo=280.00),
        "PVC_20MM_BRANCO": _produto_chapa("PVC 20mm Branco", "PVC", {"espessura": "20MM", "cor": "BRANCO"}, minimo=5, maximo=10, codigo_planilha="5C_007"),
        "PVC_20MM_PRETO": _produto_chapa("PVC 20mm Preto", "PVC", {"espessura": "20MM", "cor": "PRETO"}, minimo=3, maximo=10, codigo_planilha="5C_009"),

        # ---- CHAPA — PS ----
        "PS_1MM_BRANCO": _produto_chapa("PS 1mm Branco", "PS", {"espessura": "1MM", "cor": "BRANCO"}, minimo=6, maximo=60, codigo_planilha="5C_001", custo=50.00),
        "PS_1MM_PRETO": _produto_chapa("PS 1mm Preto", "PS", {"espessura": "1MM", "cor": "PRETO"}, minimo=6, maximo=60, custo=50.00),
        "PS_2MM_BRANCO": _produto_chapa("PS 2mm Branco", "PS", {"espessura": "2MM", "cor": "BRANCO"}, minimo=6, maximo=60, codigo_planilha="5C_002", custo=75.00),
        "PS_2MM_PRETO": _produto_chapa("PS 2mm Preto", "PS", {"espessura": "2MM", "cor": "PRETO"}, minimo=3, maximo=60, codigo_planilha="5C_003", custo=75.00),
        "PS_3MM_BRANCO": _produto_chapa("PS 3mm Branco", "PS", {"espessura": "3MM", "cor": "BRANCO"}, minimo=6, maximo=60),
        "PS_3MM_PRETO": _produto_chapa("PS 3mm Preto", "PS", {"espessura": "3MM", "cor": "PRETO"}, minimo=6, maximo=60),

        # ---- INSUMOS (já cadastrados na planilha, sem vínculo com etiqueta) ----
        "MASCARA_VINIL_PAPEL": _produto_insumo("Máscara Vinil Papel 1,27x50m", unidade="rolo", minimo=6, maximo=60, codigo_planilha="5C_041"),
        "MASCARA_VINIL_TRANSPARENTE": _produto_insumo("Máscara Vinil Transparente 1,27x50m", unidade="rolo", minimo=6, maximo=60, codigo_planilha="5C_042"),
        "ILHOS_ZERO_AT": _produto_insumo("Ilhós Zero AT C/ARR FN - 0.5 MI (caixa 500un)", unidade="caixa", minimo=6, maximo=60, codigo_planilha="5C_052"),
        # tinta LUS-170/190/210 real da UJV100-160, vendida em frasco de 1L
        "TINTA_UV_160_CIANO": _produto_insumo("Tinta Uv UJV-100-160Plus Ciano", minimo=10, maximo=60, codigo_planilha="5C_043", capacidade_ml=1000),
        "TINTA_UV_160_MAGENTA": _produto_insumo("Tinta Uv UJV-100-160Plus Magenta", minimo=10, maximo=60, codigo_planilha="5C_044", capacidade_ml=1000),
        "TINTA_UV_160_YELLOW": _produto_insumo("Tinta Uv UJV-100-160Plus Yellow", minimo=10, maximo=60, codigo_planilha="5C_045", capacidade_ml=1000),
        "TINTA_UV_160_BLACK": _produto_insumo("Tinta Uv UJV-100-160Plus Black", minimo=10, maximo=60, codigo_planilha="5C_046", capacidade_ml=1000),
        # tinta CS100/CS200 real da SWJ-320EA, vendida em frasco de 2L
        "TINTA_SWJ_320_CIANO": _produto_insumo("Tinta SWJ-320EA Ciano", minimo=10, maximo=60, codigo_planilha="5C_047", capacidade_ml=2000),
        "TINTA_SWJ_320_MAGENTA": _produto_insumo("Tinta SWJ-320EA Magenta", minimo=10, maximo=60, codigo_planilha="5C_048", capacidade_ml=2000),
        "TINTA_SWJ_320_YELLOW": _produto_insumo("Tinta SWJ-320EA Yellow", minimo=10, maximo=60, codigo_planilha="5C_049", capacidade_ml=2000),
        "TINTA_SWJ_320_BLACK": _produto_insumo("Tinta SWJ-320EA Black", minimo=10, maximo=60, codigo_planilha="5C_050", capacidade_ml=2000),
        "POLICARBONATO_5MM": _produto_insumo("Policarbonato 5mm", unidade="chapa", minimo=20, maximo=60, codigo_planilha="5C_058"),
        "POLICARBONATO_ALVEOLAR_5MM": _produto_insumo("Policarbonato Alveolar 5mm", unidade="chapa", minimo=20, maximo=60, codigo_planilha="5C_059"),
    }

    # Acrílico: 1-10mm (sem 9mm, que não foi pedido) × Cristal/Leitoso.
    # Códigos da planilha só existem pra "Cristal" de 3 a 10mm — 1mm e
    # 2mm Cristal, e todo o Leitoso, são combinações novas (sem produto
    # equivalente cadastrado na planilha original).
    codigos_acrilico_cristal = {
        "3MM": "5C_010", "4MM": "5C_011", "5MM": "5C_012",
        "6MM": "5C_013", "7MM": "5C_014", "8MM": "5C_015", "10MM": "5C_016",
    }
    for espessura in ["1MM", "2MM", "3MM", "4MM", "5MM", "6MM", "7MM", "8MM", "10MM"]:
        for cor in ["CRISTAL", "LEITOSO"]:
            codigo = f"ACRILICO_{espessura}_{cor}"
            codigo_planilha = codigos_acrilico_cristal.get(espessura) if cor == "CRISTAL" else None
            catalogo[codigo] = _produto_chapa(
                f"Acrílico {espessura.replace('MM', 'mm')} {cor.capitalize()}", "ACRILICO",
                {"espessura": espessura, "cor": cor}, minimo=6, maximo=60, codigo_planilha=codigo_planilha,
            )

    custos_tinta.sincronizar_catalogo({"produtos": catalogo}, custos_tinta.CONFIGURACAO_PADRAO)
    return catalogo


CATALOGO_PADRAO = _catalogo_padrao()


def carregar_estoque():
    """
    Carrega o estoque.json. Se não existir, cria um novo com o catálogo
    padrão (todos com saldo zero). Se existir mas estiver faltando algum
    produto novo do catálogo (por exemplo, depois de uma atualização do
    programa que adicionou uma variante), completa sem apagar os
    movimentos já registrados. Se o arquivo estiver corrompido, guarda
    uma cópia de segurança e recria do zero — mesmo padrão do config.py.
    """
    arquivo = caminhos.ESTOQUE
    if not arquivo.exists():
        estoque_novo = {"produtos": copy.deepcopy(CATALOGO_PADRAO), "movimentos": [], "proximo_id": 1, "producao_mensal": []}
        salvar_estoque(estoque_novo)
        return estoque_novo

    try:
        with open(arquivo, "r", encoding="utf-8") as f:
            estoque = json.load(f)
    except (json.JSONDecodeError, OSError):
        backup = arquivo.with_suffix(".json.bak")
        try:
            arquivo.replace(backup)
        except OSError:
            pass
        estoque_novo = {"produtos": copy.deepcopy(CATALOGO_PADRAO), "movimentos": [], "proximo_id": 1, "producao_mensal": []}
        salvar_estoque(estoque_novo)
        return estoque_novo

    estoque.setdefault("produtos", {})
    estoque.setdefault("movimentos", [])
    estoque.setdefault("producao_mensal", [])
    ids_existentes = [m["id"] for m in estoque["movimentos"]]
    estoque.setdefault("proximo_id", max(ids_existentes, default=0) + 1)

    alterado = False
    for codigo, produto_padrao in CATALOGO_PADRAO.items():
        if codigo not in estoque["produtos"]:
            estoque["produtos"][codigo] = copy.deepcopy(produto_padrao)
            alterado = True
        else:
            # preenche campo novo que uma atualização do catálogo padrão
            # tenha adicionado (ex: capacidade_ml) sem sobrescrever nada
            # que já existia (saldo é sempre derivado dos movimentos, não
            # fica aqui — só metadado de cadastro é completado)
            for chave, valor in produto_padrao.items():
                if chave not in estoque["produtos"][codigo]:
                    estoque["produtos"][codigo][chave] = copy.deepcopy(valor)
                    alterado = True

    # o contador solto de rolo aberto (modelo antigo, ver o topo do módulo)
    # vira movimento: o que ele guardava são metros JÁ gastos
    for codigo, produto in estoque["produtos"].items():
        if "acumulado_m" not in produto:
            continue
        acumulado = produto.pop("acumulado_m") or 0.0
        alterado = True
        comprimento = produto.get("comprimento_rolo_m") or 0
        if acumulado > 0 and comprimento > 0:
            _acrescentar_movimento(
                estoque, codigo, "ajuste", -round(acumulado / comprimento, 4),
                observacao=f"Metros já gastos do rolo aberto ({acumulado:.2f} m), do contador antigo",
            )
    if alterado:
        salvar_estoque(estoque)

    return estoque


def salvar_estoque(estoque):
    """
    Grava por arquivo temporário + troca: um travamento no meio da gravação
    deixaria o estoque.json pela metade, e a carga seguinte o daria por
    corrompido e recomeçaria do zero.
    """
    arquivo = caminhos.ESTOQUE
    temporario = arquivo.with_name(arquivo.name + ".tmp")
    with open(temporario, "w", encoding="utf-8") as f:
        json.dump(estoque, f, ensure_ascii=False, indent=2)
    temporario.replace(arquivo)


_ACENTOS = str.maketrans("ÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇ", "AAAAAEEEEIIIIOOOOOUUUUC")


def _slugificar(descricao):
    """Código interno legível a partir da descrição digitada (maiúsculas, sem acento, tudo que não é letra/número vira '_')."""
    texto = descricao.upper().translate(_ACENTOS)
    texto = re.sub(r"[^A-Z0-9]+", "_", texto).strip("_")
    return texto or "PRODUTO"


def novo_produto(tipo, descricao, unidade=None, categoria_vinculada=None, variante=None,
                  comprimento_rolo_m=None, minimo=0, maximo=0, codigo_planilha=None):
    """
    Monta o dicionário de um produto novo, cadastrado manualmente pela
    tela de estoque (em vez de já vir no CATALOGO_PADRAO). Mesmo formato
    dos produtos do catálogo padrão — só passa a existir mesmo no
    estoque quando `adicionar_produto` for chamado.
    """
    if tipo == "rolo":
        produto = _produto_rolo(descricao, categoria_vinculada or None, comprimento_rolo_m or 0, minimo, maximo, codigo_planilha)
    elif tipo == "chapa":
        produto = _produto_chapa(descricao, categoria_vinculada or None, variante, minimo, maximo, codigo_planilha)
    else:
        produto = _produto_insumo(descricao, unidade or "un", minimo, maximo, codigo_planilha)
    if unidade and tipo != "insumo":
        produto["unidade"] = unidade
    return produto


def adicionar_produto(estoque, produto):
    """
    Gera um código interno único a partir da descrição e adiciona o
    produto ao catálogo — saldo sempre começa em zero, como qualquer
    produto do estoque (quem quiser um saldo inicial lança uma entrada
    manual logo em seguida). Devolve o código gerado.
    """
    base = _slugificar(produto["descricao"])
    codigo = base
    contador = 2
    while codigo in estoque["produtos"]:
        codigo = f"{base}_{contador}"
        contador += 1
    estoque["produtos"][codigo] = produto
    salvar_estoque(estoque)
    return codigo


def atualizar_produto(estoque, codigo, tipo, descricao, unidade=None, categoria_vinculada=None,
                       variante=None, comprimento_rolo_m=None, minimo=0, maximo=0, codigo_planilha=None):
    """
    Atualiza o cadastro de um produto já existente (edição, não criação
    — o código interno não muda). Nunca mexe no histórico de movimentos
    — só o cadastro é substituído.
    """
    produto = novo_produto(
        tipo, descricao, unidade=unidade, categoria_vinculada=categoria_vinculada,
        variante=variante, comprimento_rolo_m=comprimento_rolo_m, minimo=minimo,
        maximo=maximo, codigo_planilha=codigo_planilha,
    )
    # custo não tem campo na tela de cadastro: editar não pode apagá-lo
    produto["custo"] = estoque["produtos"][codigo].get("custo")
    estoque["produtos"][codigo] = produto
    salvar_estoque(estoque)
    return produto


def remover_produto(estoque, codigo):
    """
    Remove um produto cadastrado por engano. Recusa remover se já
    existir movimento (entrada/saída/ajuste) pra esse produto — pra não
    deixar histórico órfão apontando pra um código que some do
    catálogo. Devolve True se removeu, False se recusou ou não achou.
    """
    if any(m["produto"] == codigo for m in estoque["movimentos"]):
        return False
    if codigo not in estoque["produtos"]:
        return False
    del estoque["produtos"][codigo]
    salvar_estoque(estoque)
    return True


def saldo_produto(estoque, codigo):
    """Saldo é sempre a soma do histórico — nunca um contador solto."""
    # arredonda o ruído da soma de frações de rolo (0,1 + 0,2 = 0,30000000000000004)
    return round(sum(m["quantidade"] for m in estoque["movimentos"] if m["produto"] == codigo), 4)


def _numero(valor, casas=2):
    """12.4 -> '12,4'; 3.0 -> '3'. Sem zero sobrando, com vírgula."""
    texto = f"{valor:.{casas}f}".rstrip("0").rstrip(".")
    return (texto if texto not in ("", "-0") else "0").replace(".", ",")


def formatar_quantidade(produto, quantidade):
    """
    Uma quantidade desse produto em texto. Rolo diz também os metros — é o
    que se mede na bancada; '0,248 rolo' sozinho não diz nada a ninguém.
    """
    unidade = (produto or {}).get("unidade", "")
    comprimento = (produto or {}).get("comprimento_rolo_m") or 0
    if (produto or {}).get("tipo") == "rolo" and comprimento > 0:
        return f"{_numero(quantidade, 3)} {unidade} ({_numero(quantidade * comprimento)} m)"
    return f"{_numero(quantidade, 3)} {unidade}".strip()


def descrever_saldo(produto, saldo):
    """
    O saldo como se conta na prateleira. Rolo: '2 fechados + aberto com
    37,6 m (137,6 m)' — o aberto é o que sobrou do rolo em uso.
    """
    comprimento = produto.get("comprimento_rolo_m") or 0
    if produto.get("tipo") != "rolo" or comprimento <= 0 or saldo <= 0:
        return formatar_quantidade(produto, saldo)
    fechados = math.floor(saldo + 1e-6)
    aberto_m = round((saldo - fechados) * comprimento, 2)
    total_m = _numero(saldo * comprimento)
    if aberto_m < 0.01:
        return f"{fechados} {produto['unidade']} ({total_m} m)"
    return f"{fechados} fechado(s) + aberto com {_numero(aberto_m)} m ({total_m} m)"


def interpretar_quantidade(produto, texto):
    """
    O que se digita na entrada/saída manual. Número puro é na unidade do
    produto; rolo aceita também metros com 'm' no fim ('37,6m'), que é como
    se conta rolo aberto na contagem física. Devolve a quantidade na unidade
    do produto; ValueError quando não dá pra entender ou não é maior que zero.
    """
    limpo = str(texto).strip().lower().replace(",", ".").replace(" ", "")
    em_metros = limpo.endswith("m")
    if em_metros:
        limpo = limpo[:-1]
    quantidade = float(limpo)
    if quantidade <= 0:
        raise ValueError("a quantidade precisa ser maior que zero")
    if not em_metros:
        return quantidade
    comprimento = produto.get("comprimento_rolo_m") or 0
    if produto.get("tipo") != "rolo" or comprimento <= 0:
        raise ValueError("metros só valem pra rolo com comprimento cadastrado")
    return round(quantidade / comprimento, 4)


def conferir_cadastro(estoque, materiais):
    """
    Onde o estoque e o config.json não conversam — cada um vira baixa que
    não acontece:
      'sem_produto': material/espessura que o sistema reconhece no nome do
                     arquivo, mas sem produto no estoque (a baixa pela OS
                     fica "sem produto vinculado");
      'sem_material': produto de chapa/rolo cujo material ou espessura o
                     config não reconhece (nunca recebe baixa pela OS).
    """
    from dimensoes import formatar_variante

    produtos = estoque["produtos"]
    sem_produto, sem_material = [], []
    for categoria, info in (materiais or {}).items():
        vinculados = [p for p in produtos.values() if p.get("categoria_vinculada") == categoria]
        variantes = info.get("variantes") or []
        if info.get("tipo") == "rolo" or not variantes:
            if not vinculados:
                sem_produto.append(categoria)
            continue
        for variante in variantes:
            if not any(_mesma_variante(p.get("variante_vinculada"), variante) for p in vinculados):
                sem_produto.append(f"{categoria} {formatar_variante(variante)}")
    for produto in produtos.values():
        categoria = produto.get("categoria_vinculada")
        if not categoria or produto.get("tipo") == "insumo":
            continue
        info = (materiais or {}).get(categoria)
        if info is None:
            sem_material.append(produto["descricao"])
        elif produto.get("tipo") == "chapa" and info.get("variantes") and not any(
                _mesma_variante(produto.get("variante_vinculada"), v) for v in info["variantes"]):
            sem_material.append(produto["descricao"])
    return {"sem_produto": sem_produto, "sem_material": sorted(sem_material)}


def registrar_movimento(estoque, codigo, tipo, quantidade, observacao="", origem_pedido=None, estorno_de=None):
    """
    tipo: 'entrada' (quantidade positiva), 'saida' (quantidade negativa
    — quem chama já manda o sinal certo), 'ajuste' (qualquer sinal,
    usado inclusive pelo desfazer). Nunca edita um movimento existente,
    só acrescenta — assim o histórico continua confiável.
    """
    mov = _acrescentar_movimento(estoque, codigo, tipo, quantidade, observacao, origem_pedido, estorno_de)
    salvar_estoque(estoque)
    return mov


def _acrescentar_movimento(estoque, codigo, tipo, quantidade, observacao="", origem_pedido=None, estorno_de=None):
    mov = {
        "id": estoque["proximo_id"],
        "data": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
        "produto": codigo,
        "tipo": tipo,
        "quantidade": quantidade,
        "observacao": observacao,
        "origem_pedido": origem_pedido,
        "estorno_de": estorno_de,
    }
    estoque["movimentos"].append(mov)
    estoque["proximo_id"] += 1
    return mov


def desfazer_movimento(estoque, movimento_id):
    """
    Cria um lançamento de ajuste que anula um movimento anterior (nunca
    apaga o original, pra manter o histórico completo). Devolve None se
    o movimento não existir ou já tiver sido estornado.
    """
    original = next((m for m in estoque["movimentos"] if m["id"] == movimento_id), None)
    if original is None:
        return None
    ja_estornado = any(m.get("estorno_de") == movimento_id for m in estoque["movimentos"])
    if ja_estornado:
        return None
    return registrar_movimento(
        estoque, original["produto"], "ajuste", -original["quantidade"],
        observacao=f"Estorno do movimento #{movimento_id}", estorno_de=movimento_id,
    )


def _mesma_variante(cadastrada, da_peca):
    """
    A variante pelo que ela É — espessura e cor. A da peça é uma cópia da
    variante do config.json, que pode carregar preço e rótulo; comparar o
    dicionário inteiro fazia a chapa com preço cadastrado perder o produto
    do estoque (mesma regra de custos._mesma_variante).
    """
    if not cadastrada or not da_peca:
        return not cadastrada and not da_peca
    return ((cadastrada.get("espessura") or "") == (da_peca.get("espessura") or "")
            and (cadastrada.get("cor") or "") == (da_peca.get("cor") or ""))


def _produto_vinculado(estoque, categoria, variante):
    """
    Acha o produto do estoque vinculado a uma categoria de etiqueta (e,
    pra chapa, à variante espessura/cor — casamento exato). Devolve
    (codigo, produto, ambiguo). 'ambiguo' vem True quando existe mais de
    um produto cadastrado pra mesma categoria sem dar pra saber qual
    pelo nome do arquivo — caso do ADESIVO, que tem 4 acabamentos
    cadastrados (Branco Fosco/Preto Fosco/Cristal/Jateado) mas o nome do
    arquivo não indica qual foi usado (só a categoria "ADESIVO"). Nesse
    caso o sistema não adivinha: fica sem produto resolvido, pra dar
    baixa manual depois escolhendo o certo.

    Chapa cujo nome de arquivo não disse espessura/cor (variante None —
    "PS 1,00X0,50M" sem o "2MM") é o mesmo caso: qualquer chapa do
    material pode ser, então é ambígua e quem dá baixa escolhe. Antes
    ficava "sem produto vinculado", sem jeito de baixar pela OS.
    """
    candidatos = [
        (codigo, produto) for codigo, produto in estoque["produtos"].items()
        if produto["categoria_vinculada"] == categoria
    ]
    if not candidatos:
        return None, None, False

    rolos = [(c, p) for c, p in candidatos if p["tipo"] == "rolo"]
    if rolos:
        if len(rolos) == 1:
            codigo, produto = rolos[0]
            return codigo, produto, False
        return None, None, True

    chapas = [(c, p) for c, p in candidatos if _mesma_variante(p["variante_vinculada"], variante)]
    if len(chapas) == 1:
        codigo, produto = chapas[0]
        return codigo, produto, False
    return None, None, bool(chapas) or not variante


def produtos_por_categoria(estoque, categoria):
    """
    Lista (codigo, produto) cadastrados pra essa categoria de etiqueta —
    usado pra deixar o usuário escolher manualmente qual produto baixar
    quando há mais de um vinculado à mesma categoria sem jeito de saber
    qual pelo nome do arquivo (caso do ADESIVO, com 4 acabamentos).
    """
    return [
        (codigo, produto) for codigo, produto in estoque["produtos"].items()
        if produto["categoria_vinculada"] == categoria
    ]


def calcular_consumo(itens, materiais_config):
    """
    Quanto cada material que sai do estoque consome nesta OS — metros de
    rolo ou chapas inteiras —, agrupado por categoria + variante.

    Desde 28/09/2026 a conta é do LOTE (aproveitamento.consumo_por_material):
    as peças do mesmo material encaixadas juntas, como saem na máquina e na
    bancada. Antes cada peça gastava sozinha a largura inteira do rolo, e a
    baixa saía maior do que o material que de fato foi usado.

    Material composto (ex: "PS ADESIVADO"): a mesma peça entra no lote de PS
    e no de ADESIVO — consome os dois de verdade, não é escolha entre um ou
    outro. 'dimensao' é de UMA peça e a quantidade multiplica (regressão de
    2026-08-29: "4UN PVC..." baixava como 1).
    """
    resultados = []
    for lote in consumo_por_material(itens, materiais_config):
        linha = {
            "categoria": lote["categoria"], "variante": lote["variante"], "tipo": lote["tipo"],
            "area_m2": lote["area_pecas_m2"], "desperdicio_m2": lote["desperdicio_m2"],
            "aproveitamento": lote["aproveitamento"], "pecas_divididas": lote["pecas_divididas"],
        }
        if lote["tipo"] == "rolo":
            linha["metros"] = lote["metros"]
        else:
            linha["chapas"] = lote["chapas"]
            linha["maior_retalho_m"] = lote.get("maior_retalho_m")
        resultados.append(linha)
    return resultados


def _processar_saida_os(estoque, itens, materiais_config, nome_pedido, persistir, resolucoes_manuais=None):
    resolucoes_manuais = resolucoes_manuais or {}
    consumo = calcular_consumo(itens, materiais_config)
    resumo = []
    for grupo in consumo:
        codigo, produto, ambiguo = _produto_vinculado(estoque, grupo["categoria"], grupo["variante"])
        if codigo is None and ambiguo:
            # usuário escolheu manualmente qual dos produtos ambíguos
            # baixar (ex: qual dos 4 acabamentos de ADESIVO) — resolvido
            # na tela de Saída pela OS, chave é só a categoria porque é
            # o único caso real de ambiguidade hoje (rolo, sem variante)
            codigo_manual = resolucoes_manuais.get(grupo["categoria"])
            if codigo_manual and codigo_manual in estoque["produtos"]:
                codigo = codigo_manual
                produto = estoque["produtos"][codigo]
                ambiguo = False
        if codigo is None:
            resumo.append({
                "categoria": grupo["categoria"], "variante": grupo["variante"], "produto": None,
                "codigo": None, "descontado": None, "unidade": None, "saldo_resultante": None,
                "ambiguo": ambiguo, "problema": None, "consumo": grupo,
            })
            continue

        saldo_atual = saldo_produto(estoque, codigo)
        estimativa = f"{grupo['aproveitamento']:.0%} aproveitado, lote encaixado — estimativa"
        if grupo["pecas_divididas"]:
            estimativa += f"; {grupo['pecas_divididas']} peça(s) em partes, emenda não contada"

        problema = None
        if grupo["tipo"] == "rolo":
            comprimento_rolo = produto.get("comprimento_rolo_m") or 0
            if comprimento_rolo > 0:
                # fração de rolo: 12,40 m de um rolo de 50 m = 0,248 (ver o topo do módulo)
                descontado = round(grupo["metros"] / comprimento_rolo, 4)
            else:
                descontado = 0
                problema = "rolo sem comprimento cadastrado — edite o produto antes de dar baixa"
            observacao = f"Saída pela OS: {grupo['metros']:.2f} m de rolo ({estimativa})"
        else:
            descontado = grupo["chapas"]
            observacao = f"Saída pela OS: {descontado} chapa(s) ({estimativa})"
        if persistir and descontado > 0:
            registrar_movimento(
                estoque, codigo, "saida", -descontado, observacao=observacao, origem_pedido=nome_pedido,
            )

        resumo.append({
            "categoria": grupo["categoria"], "variante": grupo["variante"], "produto": produto["descricao"],
            "codigo": codigo, "descontado": descontado, "unidade": produto["unidade"],
            "saldo_resultante": saldo_atual - descontado, "ambiguo": False, "problema": problema,
            "consumo": grupo,
        })

        # só LONA e ADESIVO têm máquina vinculada (ver MAQUINA_POR_CATEGORIA)
        # — registra quanto m² foi impresso nesse pedido, pra depois cruzar
        # com a tinta consumida e calcular o rendimento real por máquina
        if persistir and grupo["categoria"] in MAQUINA_POR_CATEGORIA and grupo["area_m2"] > 0:
            registrar_producao(estoque, grupo["categoria"], grupo["area_m2"], nome_pedido)

    if persistir:
        salvar_estoque(estoque)
    return resumo


def registrar_producao(estoque, categoria, area_m2, origem_pedido, data=None):
    """
    Registra quantos m² foram impressos numa categoria vinculada a uma
    máquina (LONA/ADESIVO — ver MAQUINA_POR_CATEGORIA), pra depois
    calcular o rendimento de tinta real (mL/m²). Não é um movimento de
    estoque (não desconta nada) — é só um registro de produção, salvo
    à parte em estoque["producao_mensal"].
    """
    registro = {
        "data": data or datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
        "categoria": categoria,
        "area_m2": area_m2,
        "origem_pedido": origem_pedido,
    }
    estoque.setdefault("producao_mensal", []).append(registro)
    salvar_estoque(estoque)
    return registro


def _ano_mes(registro):
    """Extrai (ano, mes) do campo 'data' (formato 'DD/MM/AAAA HH:MM:SS') de um movimento ou registro de produção. Devolve None se o formato não bater."""
    partes = registro["data"].split(" ")[0].split("/")
    if len(partes) != 3:
        return None
    try:
        return int(partes[2]), int(partes[1])
    except ValueError:
        return None


def meses_disponiveis(estoque):
    """Lista (ano, mês) distintos presentes no histórico de movimentos, mais recente primeiro."""
    vistos = {_ano_mes(m) for m in estoque["movimentos"]}
    vistos.discard(None)
    return sorted(vistos, reverse=True)


def resumo_mensal(estoque, ano, mes):
    """
    Resumo do mês pro dashboard — sempre agrupado por produto, nunca
    somando quantidade entre produtos de unidade diferente (mesmo
    princípio já usado no resto do sistema: nunca misturar chapa com
    rolo com caixa num único número). Devolve os rankings de produto
    mais comprado (entrada) e mais consumido (saída) no mês, contagem
    de lançamentos, e os produtos com saldo abaixo do mínimo (esse
    último é o status atual, não é limitado ao mês).
    """
    movimentos_mes = [m for m in estoque["movimentos"] if _ano_mes(m) == (ano, mes)]

    por_produto = {}
    for m in movimentos_mes:
        codigo = m["produto"]
        if codigo not in estoque["produtos"]:
            continue
        dados = por_produto.setdefault(codigo, {"entradas": 0.0, "saidas": 0.0, "lancamentos": 0})
        dados["lancamentos"] += 1
        if m["quantidade"] > 0:
            dados["entradas"] += m["quantidade"]
        else:
            dados["saidas"] += -m["quantidade"]

    ranking_entradas = sorted(
        ((codigo, dados["entradas"]) for codigo, dados in por_produto.items() if dados["entradas"] > 0),
        key=lambda item: item[1], reverse=True,
    )
    ranking_saidas = sorted(
        ((codigo, dados["saidas"]) for codigo, dados in por_produto.items() if dados["saidas"] > 0),
        key=lambda item: item[1], reverse=True,
    )
    produtos_abaixo_minimo = [
        codigo for codigo, produto in estoque["produtos"].items()
        if produto.get("minimo", 0) > 0 and saldo_produto(estoque, codigo) < produto["minimo"]
    ]

    return {
        "total_lancamentos": len(movimentos_mes),
        "total_entradas_lancamentos": sum(1 for m in movimentos_mes if m["quantidade"] > 0),
        "total_saidas_lancamentos": sum(1 for m in movimentos_mes if m["quantidade"] < 0),
        "ranking_entradas": ranking_entradas,
        "ranking_saidas": ranking_saidas,
        "produtos_abaixo_minimo": produtos_abaixo_minimo,
    }


def rendimento_tinta_mensal(estoque, ano, mes):
    """
    Rendimento real de tinta por máquina no mês: mL de tinta consumida
    (saída das 4 cores, convertendo frasco → mL pela capacidade de cada
    produto) dividido pelos m² produzidos na categoria vinculada àquela
    máquina (ver MAQUINA_POR_CATEGORIA) no mesmo mês.

    Calculado empiricamente porque a Mimaki não publica um mL/m² fixo
    (depende da cobertura de tinta de cada arte) — cruzando consumo
    real de tinta com produção real, o número fica específico do mix de
    trabalho da empresa, mais preciso que qualquer tabela genérica.

    Devolve None em 'rendimento_ml_m2' quando ainda não há os dois lados
    (tinta consumida E produção) nesse mês — não inventa um número.
    """
    movimentos_mes = [m for m in estoque["movimentos"] if _ano_mes(m) == (ano, mes)]
    producao_mes = [p for p in estoque.get("producao_mensal", []) if _ano_mes(p) == (ano, mes)]

    resultados = {}
    for categoria, maquina in MAQUINA_POR_CATEGORIA.items():
        tinta_ml = 0.0
        for codigo in TINTAS_POR_MAQUINA.get(maquina, []):
            produto = estoque["produtos"].get(codigo)
            if not produto:
                continue
            capacidade = produto.get("capacidade_ml", 0)
            consumida = sum(-m["quantidade"] for m in movimentos_mes if m["produto"] == codigo and m["quantidade"] < 0)
            tinta_ml += consumida * capacidade

        area_m2 = sum(p["area_m2"] for p in producao_mes if p["categoria"] == categoria)

        resultados[maquina] = {
            "categoria": categoria,
            "tinta_ml": tinta_ml,
            "area_m2": area_m2,
            "rendimento_ml_m2": (tinta_ml / area_m2) if area_m2 > 0 and tinta_ml > 0 else None,
        }
    return resultados


def pedido_ja_teve_saida(estoque, nome_pedido):
    """
    Diz se esse pedido (mesma string usada em 'origem_pedido' — cliente
    + data/hora da OS) já teve baixa registrada antes. Escolher o mesmo
    arquivo de OS duas vezes (ou clicar em confirmar duas vezes sem
    querer) dobraria o consumo silenciosamente sem esse aviso — só
    verifica, não impede: quem chama decide se deixa prosseguir mesmo
    assim (pode ser uma correção deliberada).
    """
    return any(m.get("origem_pedido") == nome_pedido for m in estoque["movimentos"])


def prever_saida_os(estoque, itens, materiais_config, resolucoes_manuais=None):
    """Só calcula o que SERIA descontado, sem gravar nada no estoque real."""
    copia = copy.deepcopy(estoque)
    return _processar_saida_os(copia, itens, materiais_config, nome_pedido=None, persistir=False, resolucoes_manuais=resolucoes_manuais)


def confirmar_saida_os(estoque, itens, materiais_config, nome_pedido, resolucoes_manuais=None):
    """Desconta de verdade (rolo: a fração de rolo gasta; chapa: chapas inteiras) e grava."""
    return _processar_saida_os(estoque, itens, materiais_config, nome_pedido, persistir=True, resolucoes_manuais=resolucoes_manuais)
