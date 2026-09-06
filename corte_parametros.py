"""
Parâmetros de usinagem por material e espessura — o que estava só na
cabeça do Flávio até 06/09/2026.

Isto aqui é o coração do corte automático. Sem ele não há percurso: o
gadget do Aspire precisa saber QUAL fresa pegar do banco, QUANTO descer
por passada e ATÉ ONDE cortar. Enquanto esse conhecimento morar só na
memória de uma pessoa, a fresadora para quando essa pessoa faltar.

Três regras, todas ditadas pelo usuário:

  - **Corta sempre 1 mm além da espessura da chapa.** Chapa de 10 vira
    profundidade 11. É o que garante corte passante — parar exatamente na
    espessura deixa a peça presa por um filme.
  - **A passada é por MATERIAL E ESPESSURA, não só por material.** MDF de
    6 mm usa passada de 7 (sai de uma vez); MDF de 9 e 15 usam 6. Não dá
    pra guardar isso só por material.
  - **O número de passes não se cadastra** — sai de
    arredonda_pra_cima(profundidade ÷ passada). Guardar os dois seria
    guardar a mesma verdade duas vezes, e um dia elas discordariam.

O resto dos parâmetros (avanço, rotação, diâmetro) mora no **banco de
ferramentas do Aspire**, que é onde a Vectric espera que morem. Aqui só
fica o que aponta pra lá: o grupo e o nome da ferramenta.
"""
import math

# Como a peça é usinada em relação à linha do desenho. Confirmado no
# print da tela do Flávio (06/09/2026): "Fora / Direita", "Subida".
LADO_FORA = "fora"
LADO_DENTRO = "dentro"
DIRECAO_SUBIDA = "subida"       # climb

# A ordem de usinagem, e ela não é detalhe: é o que impede a peça de se
# soltar antes da hora.
#
# Regra do usuário (2026-09-06), literal: "dentro por dentro e fora por
# fora". Corte de letra tem duas famílias de contorno e cada uma quer um
# lado diferente:
#   - o buraco do 'O' se usina POR DENTRO da linha, senão o furo sai
#     maior que o desenho
#   - o contorno da letra se usina POR FORA, senão a letra sai menor
#
# E o INTERNO vem PRIMEIRO. Assim que o contorno externo fecha, a peça
# solta da chapa e passa a se mexer — furo feito depois disso sai torto,
# quando não arranca a peça.
ORDEM_DE_USINAGEM = (
    {"camada": "CORTE INTERNO", "lado": LADO_DENTRO},
    {"camada": "CORTE EXTERNO", "lado": LADO_FORA},
)

# Rampa de entrada: em vez de furar reto, a fresa entra descendo ao longo
# do caminho. Poupa a ponta da ferramenta e o motor.
RAMPA_SUAVE_MM = 10.0

# Quanto passar além da chapa pra garantir corte passante.
FOLGA_PASSANTE_MM = 1.0

# (material, espessura em mm) -> ferramenta e passada.
# 'grupo' e 'ferramenta' têm que bater LETRA POR LETRA com o banco de
# ferramentas do Aspire — é assim que GetTool(grupo, nome) acha. Lidos do
# arquivo real do banco em 06/09/2026.
PARAMETROS = {
    ("PVC", 10): {"grupo": "Fresa 4 mm", "ferramenta": "Topo Raso (4 mm)", "passada_mm": 11.0},
    ("PVC", 20): {"grupo": "Fresa 4 mm", "ferramenta": "Topo Raso (4 mm)", "passada_mm": 11.0},
    ("MDF", 6):  {"grupo": "Fresa 6 mm", "ferramenta": "Topo Raso (6 mm)", "passada_mm": 7.0},
    ("MDF", 9):  {"grupo": "Fresa 6 mm", "ferramenta": "Topo Raso (6 mm)", "passada_mm": 6.0},
    ("MDF", 15): {"grupo": "Fresa 6 mm", "ferramenta": "Topo Raso (6 mm)", "passada_mm": 6.0},
}


def profundidade_de_corte(espessura_mm):
    """Até onde a fresa desce: a chapa mais 1 mm, pra cortar passante."""
    return float(espessura_mm) + FOLGA_PASSANTE_MM


def quantidade_de_passes(espessura_mm, passada_mm):
    """
    Quantas descidas a fresa faz. Não se cadastra: se cadastrasse, um dia
    alguém mudaria a passada e esqueceria de mudar o número de passes.
    """
    if passada_mm <= 0:
        raise ValueError("passada tem que ser maior que zero")
    return max(1, math.ceil(profundidade_de_corte(espessura_mm) / passada_mm))


def buscar(material, espessura_mm):
    """
    Parâmetros pra cortar esta chapa, ou None se a combinação não foi
    cadastrada.

    Devolver None é de propósito: material sem parâmetro é material que
    ninguém definiu como cortar, e chutar isso quebra fresa. Quem chama
    tem que tratar a ausência, não receber um palpite.
    """
    chave = (str(material).strip().upper(), int(round(float(espessura_mm))))
    base = PARAMETROS.get(chave)
    if base is None:
        return None

    espessura = chave[1]
    return {
        "material": chave[0],
        "espessura_mm": espessura,
        "grupo": base["grupo"],
        "ferramenta": base["ferramenta"],
        "passada_mm": base["passada_mm"],
        "profundidade_mm": profundidade_de_corte(espessura),
        "passes": quantidade_de_passes(espessura, base["passada_mm"]),
        "direcao": DIRECAO_SUBIDA,
        "ordem": ORDEM_DE_USINAGEM,
        "rampa_mm": RAMPA_SUAVE_MM,
    }


def combinacoes_cadastradas():
    """Lista o que já está definido — pra tela mostrar o que falta."""
    return sorted(PARAMETROS)
