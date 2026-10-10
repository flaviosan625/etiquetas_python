"""Estimativa da DOCAN R5200, sem alterar o perfil escolhido no RIP.

Fonte: estimativa_tempo_impressao_passadas.pdf entregue pelo usuário.
Medição de referência: 4,85 × 27,251 m, 8 passadas, 30% em 47 minutos.
Outras passadas são projeções proporcionais; preparação, RIP, limpeza
e pausas não estão incluídos. Passadas aqui são as do perfil de qualidade,
não a contagem de trabalhos/reimpressões no registro da máquina.
"""
import math

MAQUINA_DOCAN = "DOCAN R5200"
PASSADAS_REFERENCIA = 8
PASSADAS_DISPONIVEIS = (2, 4, 5, 6, 8, 10, 12, 16, 24, 32)
AREA_REFERENCIA_M2 = 4.85 * 27.251
MINUTOS_REFERENCIA = 47 / 0.30
MINUTOS_POR_M2 = MINUTOS_REFERENCIA / AREA_REFERENCIA_M2
FONTE = "estimativa_tempo_impressao_passadas.pdf"
OPCOES_PASSADAS = ("8 (referência)",) + tuple(str(p) for p in PASSADAS_DISPONIVEIS)


def passadas_da_escolha(valor):
    return None if valor == OPCOES_PASSADAS[0] else int(valor)


def estimar(maquina, area_m2, passadas=None):
    """None para outra máquina/área desconhecida; 8 como referência explícita."""
    if maquina != MAQUINA_DOCAN or area_m2 is None:
        return None
    try:
        area = float(area_m2)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(area) or area < 0:
        return None
    referencia = passadas is None
    if referencia:
        passadas = PASSADAS_REFERENCIA
    if isinstance(passadas, bool):
        raise ValueError("Escolha um número de passadas da tabela da DOCAN.")
    try:
        numero = float(passadas)
    except (TypeError, ValueError) as erro:
        raise ValueError("Escolha um número de passadas da tabela da DOCAN.") from erro
    if numero not in PASSADAS_DISPONIVEIS:
        raise ValueError("Escolha um número de passadas da tabela da DOCAN.")
    taxa = MINUTOS_POR_M2 * numero / PASSADAS_REFERENCIA
    return {"maquina": maquina, "passadas": int(numero),
            "passadas_referencia": referencia, "projecao_passadas": numero != 8,
            "area_m2": area, "minutos_por_m2": taxa, "m2_por_hora": 60 / taxa,
            "minutos": area * taxa, "segundos": area * taxa * 60,
            "fonte": FONTE, "tipo": "estimativa"}


def duracao(segundos):
    total = max(0, int(float(segundos) + 0.5))
    horas, resto = divmod(total, 3600)
    minutos, segundos = divmod(resto, 60)
    return (f"{horas}h" if horas else "") + f"{minutos:02d}min{segundos:02d}s"


def texto(estimativa):
    if not estimativa:
        return ""
    modo = "referência" if estimativa["passadas_referencia"] else "planejamento"
    return (f"Est. DOCAN {estimativa['passadas']} passadas ({modo}): "
            f"{duracao(estimativa['segundos'])}")


def do_registro(registro, campo_area="area_total_m2"):
    """Reutiliza a conta gravada; registros antigos usam a referência declarada."""
    if registro.get("maquina") != MAQUINA_DOCAN:
        return None
    gravada = registro.get("estimativa_impressao")
    if isinstance(gravada, dict) and gravada.get("tipo") == "estimativa":
        return gravada
    return estimar(registro.get("maquina"), registro.get(campo_area),
                   registro.get("passadas_impressao"))
