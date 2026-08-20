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
"""
import copy
import json
import math
import pathlib
import re
from datetime import datetime

from dimensoes import calcular_desperdicio_chapa_grande, calcular_desperdicio_item

BASE_DIR = pathlib.Path(__file__).resolve().parent
ESTOQUE_PATH = BASE_DIR / "estoque.json"


def _produto_rolo(descricao, categoria, comprimento_rolo_m, minimo=0, maximo=0, codigo_planilha=None):
    return {
        "descricao": descricao, "tipo": "rolo", "unidade": "rolo",
        "comprimento_rolo_m": comprimento_rolo_m,
        "categoria_vinculada": categoria, "variante_vinculada": None,
        "minimo": minimo, "maximo": maximo, "codigo_planilha": codigo_planilha,
        "acumulado_m": 0.0,
    }


def _produto_chapa(descricao, categoria, variante, minimo=0, maximo=0, codigo_planilha=None):
    return {
        "descricao": descricao, "tipo": "chapa", "unidade": "chapa",
        "categoria_vinculada": categoria, "variante_vinculada": variante,
        "minimo": minimo, "maximo": maximo, "codigo_planilha": codigo_planilha,
    }


def _produto_insumo(descricao, unidade="un", minimo=0, maximo=0, codigo_planilha=None, capacidade_ml=None):
    produto = {
        "descricao": descricao, "tipo": "insumo", "unidade": unidade,
        "categoria_vinculada": None, "variante_vinculada": None,
        "minimo": minimo, "maximo": maximo, "codigo_planilha": codigo_planilha,
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
}


def _catalogo_padrao():
    catalogo = {
        # ---- ROLO (LONA / ADESIVO) ----
        "LONA_FOSCA_440_320": _produto_rolo(
            "Lona Fosca Front 440g 3,20x50m", "LONA", 50, minimo=6, maximo=60,
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
        "PVC_10MM_BRANCO": _produto_chapa("PVC 10mm Branco", "PVC", {"espessura": "10MM", "cor": "BRANCO"}, minimo=10, maximo=15, codigo_planilha="5C_006"),
        "PVC_10MM_PRETO": _produto_chapa("PVC 10mm Preto", "PVC", {"espessura": "10MM", "cor": "PRETO"}, minimo=3, maximo=8, codigo_planilha="5C_008"),
        "PVC_20MM_BRANCO": _produto_chapa("PVC 20mm Branco", "PVC", {"espessura": "20MM", "cor": "BRANCO"}, minimo=5, maximo=10, codigo_planilha="5C_007"),
        "PVC_20MM_PRETO": _produto_chapa("PVC 20mm Preto", "PVC", {"espessura": "20MM", "cor": "PRETO"}, minimo=3, maximo=10, codigo_planilha="5C_009"),

        # ---- CHAPA — PS ----
        "PS_1MM_BRANCO": _produto_chapa("PS 1mm Branco", "PS", {"espessura": "1MM", "cor": "BRANCO"}, minimo=6, maximo=60, codigo_planilha="5C_001"),
        "PS_1MM_PRETO": _produto_chapa("PS 1mm Preto", "PS", {"espessura": "1MM", "cor": "PRETO"}, minimo=6, maximo=60),
        "PS_2MM_BRANCO": _produto_chapa("PS 2mm Branco", "PS", {"espessura": "2MM", "cor": "BRANCO"}, minimo=6, maximo=60, codigo_planilha="5C_002"),
        "PS_2MM_PRETO": _produto_chapa("PS 2mm Preto", "PS", {"espessura": "2MM", "cor": "PRETO"}, minimo=3, maximo=60, codigo_planilha="5C_003"),
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
    if not ESTOQUE_PATH.exists():
        estoque_novo = {"produtos": copy.deepcopy(CATALOGO_PADRAO), "movimentos": [], "proximo_id": 1, "producao_mensal": []}
        salvar_estoque(estoque_novo)
        return estoque_novo

    try:
        with open(ESTOQUE_PATH, "r", encoding="utf-8") as f:
            estoque = json.load(f)
    except (json.JSONDecodeError, OSError):
        backup = ESTOQUE_PATH.with_suffix(".json.bak")
        try:
            ESTOQUE_PATH.replace(backup)
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
    if alterado:
        salvar_estoque(estoque)

    return estoque


def salvar_estoque(estoque):
    with open(ESTOQUE_PATH, "w", encoding="utf-8") as f:
        json.dump(estoque, f, ensure_ascii=False, indent=2)


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
    — o código interno não muda). Preserva o progresso do acumulador de
    rolo se o produto continuar sendo tipo rolo, e nunca mexe no
    histórico de movimentos — só o cadastro é substituído.
    """
    acumulado_anterior = estoque["produtos"][codigo].get("acumulado_m", 0.0)
    produto = novo_produto(
        tipo, descricao, unidade=unidade, categoria_vinculada=categoria_vinculada,
        variante=variante, comprimento_rolo_m=comprimento_rolo_m, minimo=minimo,
        maximo=maximo, codigo_planilha=codigo_planilha,
    )
    if tipo == "rolo":
        produto["acumulado_m"] = acumulado_anterior
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
    return sum(m["quantidade"] for m in estoque["movimentos"] if m["produto"] == codigo)


def registrar_movimento(estoque, codigo, tipo, quantidade, observacao="", origem_pedido=None, estorno_de=None):
    """
    tipo: 'entrada' (quantidade positiva), 'saida' (quantidade negativa
    — quem chama já manda o sinal certo), 'ajuste' (qualquer sinal,
    usado inclusive pelo desfazer). Nunca edita um movimento existente,
    só acrescenta — assim o histórico continua confiável.
    """
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
    salvar_estoque(estoque)
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

    chapas = [(c, p) for c, p in candidatos if p["variante_vinculada"] == variante]
    if len(chapas) == 1:
        codigo, produto = chapas[0]
        return codigo, produto, False
    return None, None, bool(chapas)


def calcular_consumo(itens, materiais_config):
    """
    Agrupa os itens de uma OS por categoria+variante e calcula quanto
    cada grupo consumiu — em metros lineares (rolo) ou em chapas
    inteiras (chapa) — reaproveitando as mesmas contas de corte que o
    processamento normal já usa (dimensoes.calcular_desperdicio_item /
    calcular_desperdicio_chapa_grande), só que agrupadas por variante
    em vez de por categoria inteira.
    """
    grupos = {}
    for item in itens:
        chave = (item["categoria"], json.dumps(item.get("variante"), sort_keys=True))
        grupos.setdefault(chave, {"itens": [], "variante": item.get("variante")})
        grupos[chave]["itens"].append(item)

    resultados = []
    for (categoria, _), grupo in grupos.items():
        info_material = materiais_config.get(categoria)
        if not info_material:
            continue
        largura_m = info_material["largura_cm"] / 100
        comprimento_m = info_material["comprimento_cm"] / 100

        comprimento_acumulado = 0.0
        chapas_extras = 0
        desperdicio_total = 0.0
        area_total_m2 = 0.0
        for item in grupo["itens"]:
            dimensao = item.get("dimensao")
            if not dimensao:
                continue
            area_total_m2 += dimensao.get("area_m2", 0.0)
            calculo = calcular_desperdicio_item(dimensao, largura_m)
            if calculo:
                comprimento_acumulado += calculo["peca_comprimento_m"]
                desperdicio_total += calculo["desperdicio_m2"]
            elif info_material["tipo"] == "chapa":
                estimativa = calcular_desperdicio_chapa_grande(dimensao, largura_m, comprimento_m)
                chapas_extras += estimativa["total_chapas"]
                desperdicio_total += estimativa["desperdicio_m2"]

        if info_material["tipo"] == "rolo":
            resultados.append({
                "categoria": categoria, "variante": grupo["variante"], "tipo": "rolo",
                "metros": comprimento_acumulado, "desperdicio_m2": desperdicio_total, "area_m2": area_total_m2,
            })
        else:
            unidades = math.ceil(comprimento_acumulado / comprimento_m) if comprimento_m > 0 else 0
            unidades += chapas_extras
            resultados.append({
                "categoria": categoria, "variante": grupo["variante"], "tipo": "chapa",
                "chapas": unidades, "desperdicio_m2": desperdicio_total, "area_m2": area_total_m2,
            })
    return resultados


def _processar_saida_os(estoque, itens, materiais_config, nome_pedido, persistir):
    consumo = calcular_consumo(itens, materiais_config)
    resumo = []
    for grupo in consumo:
        codigo, produto, ambiguo = _produto_vinculado(estoque, grupo["categoria"], grupo["variante"])
        if codigo is None:
            resumo.append({
                "categoria": grupo["categoria"], "variante": grupo["variante"], "produto": None,
                "codigo": None, "descontado": None, "unidade": None, "saldo_resultante": None,
                "ambiguo": ambiguo,
            })
            continue

        saldo_atual = saldo_produto(estoque, codigo)

        if grupo["tipo"] == "rolo":
            acumulado_novo = produto.get("acumulado_m", 0.0) + grupo["metros"]
            comprimento_rolo = produto["comprimento_rolo_m"]
            descontado = int(acumulado_novo // comprimento_rolo)
            if persistir:
                produto["acumulado_m"] = acumulado_novo - descontado * comprimento_rolo
                if descontado > 0:
                    registrar_movimento(
                        estoque, codigo, "saida", -descontado,
                        observacao=f"Saída pela OS ({grupo['metros']:.2f}m consumidos nesse pedido)",
                        origem_pedido=nome_pedido,
                    )
        else:
            descontado = grupo["chapas"]
            if persistir and descontado > 0:
                registrar_movimento(
                    estoque, codigo, "saida", -descontado,
                    observacao="Saída pela OS", origem_pedido=nome_pedido,
                )

        resumo.append({
            "categoria": grupo["categoria"], "variante": grupo["variante"], "produto": produto["descricao"],
            "codigo": codigo, "descontado": descontado, "unidade": produto["unidade"],
            "saldo_resultante": saldo_atual - descontado, "ambiguo": False,
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


def prever_saida_os(estoque, itens, materiais_config):
    """Só calcula o que SERIA descontado, sem gravar nada no estoque real."""
    copia = copy.deepcopy(estoque)
    return _processar_saida_os(copia, itens, materiais_config, nome_pedido=None, persistir=False)


def confirmar_saida_os(estoque, itens, materiais_config, nome_pedido):
    """Desconta de verdade (rolo: acumula e só baixa rolo fechado; chapa: baixa direto) e grava."""
    return _processar_saida_os(estoque, itens, materiais_config, nome_pedido, persistir=True)
