"""Estimativa de custo CMYK das Docan, pela área impressa e por cor."""
import copy
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import hashlib
import json
import re
import unicodedata

R5200 = "DOCAN R5200"
H2525 = "DOCAN H2525"
CORES = {"CIANO": "Ciano", "MAGENTA": "Magenta", "YELLOW": "Amarelo", "BLACK": "Preto"}
VOLUMES_REFERENCIA = {"CIANO": 2.46, "MAGENTA": 1.38, "YELLOW": 3.28, "BLACK": 5.43}
AREA_REFERENCIA_M2 = 2.5

CONFIGURACAO_PADRAO = {
    "referencia": {"maquina": R5200, "largura_m": 5.0, "altura_m": 0.5,
                   "area_m2": AREA_REFERENCIA_M2, "resolucao": "726x1080",
                   "icc": "Eterna_R5200_6Pass.icc", "passos": 1,
                   "volumes_ml": dict(VOLUMES_REFERENCIA)},
    "maquinas_por_material": {"DECORFLEX": R5200, "PS": H2525, "PVC": H2525, "ACRILICO": H2525},
    "maquinas": {
        maquina: {"referencia_consumo": R5200, "referencia_provisoria": maquina == H2525,
                  "cores": {cor: {"capacidade_ml": 1000.0, "preco_frasco": None,
                                  "consumo_ml_m2": float(Decimal(str(volume)) / Decimal("2.5"))}
                            for cor, volume in VOLUMES_REFERENCIA.items()}}
        for maquina in (R5200, H2525)
    },
}


def codigo_produto(maquina, cor):
    return f"TINTA_{maquina.replace(' ', '_')}_{cor}"


def _numero(valor, zero=False):
    try:
        numero = Decimal(str(valor).strip().replace(",", "."))
    except (InvalidOperation, ValueError, TypeError):
        return None
    return numero if numero.is_finite() and (numero >= 0 if zero else numero > 0) else None


def _normalizar(texto):
    sem_acento = unicodedata.normalize("NFKD", str(texto or ""))
    return re.sub(r"[^A-Z0-9]", "", sem_acento.encode("ascii", "ignore").decode().upper())


def maquina_da_peca(item, configuracao):
    """Máquina explícita vence a previsão; chapas só entram quando impressas.

    PS/PVC/ACRÍLICO adesivados não contam como impressão direta na H2525.
    Lona e adesivo da Mimaki continuam fora desta conta.
    """
    declarada = _normalizar(item.get("maquina"))
    for maquina in (R5200, H2525):
        if _normalizar(maquina) in declarada or maquina.split()[-1] in declarada:
            return maquina, False
    if any(outra in declarada for outra in ("SWJ", "UJV", "MIMAKI", "SOLVENTE")):
        return None, False
    nome = _normalizar(item.get("arquivo"))
    if "CORTEDIRETO" in nome or "SEMIMPRESS" in nome:
        return None, False
    categoria = item.get("categoria")
    prevista = configuracao.get("maquinas_por_material", {}).get(categoria)
    if prevista not in (R5200, H2525):
        return None, False
    if item.get("categoria_extra") or "ADESIVADO" in nome:
        return None, False
    if categoria != "DECORFLEX" and "IMPRESS" not in nome:
        return None, False
    return prevista, True


def assinatura(configuracao):
    return hashlib.sha256(json.dumps(configuracao or {}, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def calcular(itens, configuracao):
    """Área da arte × quantidade × mL/m² por cor × preço por mL.

    A sobra sem impressão do rolo/chapa não consome tinta. O total soma
    valores sem arredondar as cores e só então arredonda para centavos.
    A referência não é consumo real medido nem muda com as passadas do RIP.
    """
    areas, previstas, faltantes = {}, {}, []
    for item in itens:
        maquina, prevista = maquina_da_peca(item, configuracao)
        if not maquina:
            continue
        dimensao = item.get("dimensao") or {}
        area = _numero(dimensao.get("area_m2"), zero=True)
        quantidade = _numero(item.get("quantidade", 1))
        if area is None or quantidade is None:
            faltantes.append(f"{maquina}: medida/quantidade não informada em {item.get('arquivo', '')}")
            continue
        areas[maquina] = areas.get(maquina, Decimal(0)) + area * quantidade
        previstas[maquina] = previstas.get(maquina, False) or prevista
    resultados = {}
    total = Decimal(0)
    for maquina, area in areas.items():
        if not area:
            continue
        perfil = configuracao.get("maquinas", {}).get(maquina, {})
        cores, volume_total, valor_total = {}, Decimal(0), Decimal(0)
        for cor, nome in CORES.items():
            dados = perfil.get("cores", {}).get(cor, {})
            capacidade = _numero(dados.get("capacidade_ml"))
            preco = _numero(dados.get("preco_frasco"))
            taxa = _numero(dados.get("consumo_ml_m2"), zero=True)
            if capacidade is None or preco is None or taxa is None:
                faltantes.append(f"{maquina} / {nome}: preço ou consumo não cadastrado")
                continue
            volume = area * taxa
            valor = volume * preco / capacidade
            volume_total += volume
            valor_total += valor
            cores[cor] = {"nome": nome, "consumo_ml_m2": float(taxa), "volume_ml": float(volume),
                          "preco_ml": float(preco / capacidade),
                          "valor": float(valor.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))}
        resultados[maquina] = {"area_m2": float(area), "cores": cores, "maquina_prevista": previstas[maquina],
                               "referencia_consumo": perfil.get("referencia_consumo", ""),
                               "referencia_provisoria": bool(perfil.get("referencia_provisoria")),
                               "volume_ml": float(volume_total),
                               "valor": float(valor_total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))}
        total += valor_total
    return {"por_maquina": resultados, "total": float(total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
            "completo": not faltantes, "faltantes": faltantes}


def sincronizar_catalogo(estoque, configuracao):
    """Cadastra/atualiza os oito frascos sem criar movimentos de estoque."""
    for maquina, perfil in configuracao.get("maquinas", {}).items():
        if maquina not in (R5200, H2525):
            continue
        for cor, dados in perfil.get("cores", {}).items():
            if cor not in CORES:
                continue
            codigo = codigo_produto(maquina, cor)
            produto = estoque.setdefault("produtos", {}).setdefault(codigo, {
                "descricao": f"Tinta {maquina} {CORES[cor]} 1000 mL", "tipo": "insumo", "unidade": "frasco",
                "categoria_vinculada": None, "variante_vinculada": None,
                "minimo": 0, "maximo": 0, "codigo_planilha": None})
            produto["capacidade_ml"] = dados["capacidade_ml"]
            if dados.get("preco_frasco") is None:
                produto.pop("custo", None)
            else:
                produto["custo"] = dados["preco_frasco"]
    return estoque


def configuracao_padrao():
    return copy.deepcopy(CONFIGURACAO_PADRAO)
