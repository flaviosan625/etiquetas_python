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
import re
import pathlib

# Como a peça é usinada em relação à linha do desenho. Confirmado na
# tela do Flávio (06/09/2026): "Fora / Direita" no contorno.
LADO_FORA = "fora"
LADO_DENTRO = "dentro"
# Convencional, nao subida. O Flavio foi explicito duas vezes ("o corte
# pode ser padrao convencional", "corte precisa ser convencional"), e a
# tela do Aspire confirmou: mandando CutDirection = 0 acendeu
# "Convencional". A primeira versao daqui dizia "subida" — estava
# errado, e so nao virou peca torta porque o gadget ja usava o valor
# certo. Cadastro que contradiz a maquina e pior que cadastro nenhum.
DIRECAO_CONVENCIONAL = "convencional"

# Os números que a API do Aspire 8.5 espera. Não estão documentados em
# lugar nenhum — foram confirmados criando um percurso por script e o
# Flávio olhando o resultado na tela (06/09/2026).
#
# O achado que simplificou tudo: com ProfileSide = 0 o Aspire **já
# resolve sozinho** o dentro/fora. Num círculo dentro de outro ele passou
# por fora do externo e por dentro do interno, sem ninguém mandar. Eu ia
# montar dois percursos separados pra isso — não precisa.
API_PROFILE_SIDE = 0        # confirmado na tela: externo por fora, interno por dentro
API_CUT_DIRECTION = 0       # = "Convencional" na tela. Exigido: "corte precisa ser convencional"
API_RAMP_TYPE = 0           # "Suave", e ele confirmou: suave de 10mm pra todos os cortes

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
#
# DOIS PERCURSOS É A ÚNICA FORMA, e isso foi verificado (06/09/2026).
# Circulou a sugestão de usar a aba "Ordem" do formulário de perfil, que
# supostamente teria "De Dentro para Fora". A aba foi aberta e não tem:
# oferece só ordem da seleção, esquerda→direita, baixo→cima, grelha e
# percurso mais curto — e o próprio texto da aba diz que escolhe "a
# opção que resultar num movimento rápido mais curto". É otimização de
# DESLOCAMENTO, não de hierarquia. Nenhuma delas sabe o que é furo e o
# que é contorno.
#
# Ou seja: não existe atalho. Um percurso por família, o interno acima
# na lista — que ainda tem a vantagem de a ordem ficar visível pra quem
# operar a máquina.
ORDEM_DE_USINAGEM = (
    {"camada": "CORTE INTERNO", "lado": LADO_DENTRO},
    {"camada": "CORTE EXTERNO", "lado": LADO_FORA},
)

# Rampa de entrada: em vez de furar reto, a fresa entra descendo ao longo
# do caminho. Poupa a ponta da ferramenta e o motor.
RAMPA_SUAVE_MM = 10.0

# Quanto passar além da chapa pra garantir corte passante — 1 mm em tudo.
#
# Houve uma exceção por algumas horas em 06/09/2026: PVC de 3 mm com
# folga de 0,5, porque 1 mm numa chapa de 3 é um terço da espessura. O
# Flávio cancelou o material antes de usar, então o mecanismo saiu junto:
# campo configurável sem ninguém configurando é peso morto. Se o PVC de
# 3 mm voltar, a razão da folga menor está escrita aqui.
FOLGA_PASSANTE_MM = 1.0

# (material, espessura em mm) -> ferramenta e passada.
# 'grupo' e 'ferramenta' têm que bater LETRA POR LETRA com o banco de
# ferramentas do Aspire — é assim que GetTool(grupo, nome) acha. Lidos do
# arquivo real do banco em 06/09/2026.
# Avanço, ataque e rotação são os mesmos em todos os materiais — o
# usuário foi direto: "deixar com mesmo parâmetro, só mudar a fresa"
# (06/09/2026). O que muda de material pra material é a fresa e a
# passada.
AVANCO_MM_MIN = 2000.0        # Feed Rate
ATAQUE_MM_MIN = 1000.0        # Velocidade de Ataque (descida)
ROTACAO_RPM = 18000.0
PASSO_LATERAL_MM = 2.0

# TUDO AQUI É MILÍMETRO. Não é observação decorativa: o Tool do Aspire
# nasce em POLEGADA, e num teste de 06/09/2026 o diâmetro 4 virou 4
# polegadas — 101,6 mm, com raio de 50,8 marcado sobre o vetor. A passada
# de 11 teria virado 279 mm de profundidade numa chapa de 10 mm. Quem
# consumir estes valores TEM que declarar milímetro antes de escrevê-los
# (no gadget: ferramenta.InMM = true, antes de qualquer número).
UNIDADE = "mm"

_FRESA_4 = {"grupo": "Fresa 4 mm", "ferramenta": "Topo Raso (4 mm)", "diametro_mm": 4.0}
_FRESA_6 = {"grupo": "Fresa 6 mm", "ferramenta": "Topo Raso (6 mm)", "diametro_mm": 6.0}

PARAMETROS = {
    ("PVC", 10): dict(_FRESA_4, passada_mm=11.0),
    ("PVC", 20): dict(_FRESA_4, passada_mm=11.0),
    ("MDF", 6):  dict(_FRESA_6, passada_mm=7.0),
    ("MDF", 9):  dict(_FRESA_6, passada_mm=6.0),
    ("MDF", 15): dict(_FRESA_6, passada_mm=6.0),
    # Acrílico é o material mais delicado da casa: passada de 3 mm, menos
    # da metade das outras, porque calor derrete a borda e o corte
    # forçado trinca a chapa. Todas as espessuras do estoque, mesma fresa
    # e mesma passada — aqui a espessura muda só o número de passes.
    **{("ACRILICO", e): dict(_FRESA_6, passada_mm=3.0)
       for e in (1, 2, 3, 4, 5, 6, 7, 8, 10)},
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
        "diametro_mm": base["diametro_mm"],
        "passada_mm": base["passada_mm"],
        "passo_lateral_mm": PASSO_LATERAL_MM,
        "avanco_mm_min": AVANCO_MM_MIN,
        "ataque_mm_min": ATAQUE_MM_MIN,
        "rotacao_rpm": ROTACAO_RPM,
        "unidade": UNIDADE,
        "profundidade_mm": profundidade_de_corte(espessura),
        "passes": quantidade_de_passes(espessura, base["passada_mm"]),
        "direcao": DIRECAO_CONVENCIONAL,
        "ordem": ORDEM_DE_USINAGEM,
        "rampa_mm": RAMPA_SUAVE_MM,
    }


def combinacoes_cadastradas():
    """Lista o que já está definido — pra tela mostrar o que falta."""
    return sorted(PARAMETROS)


def exportar_para_lua(destino=None):
    """
    Escreve a tabela num arquivo Lua que o gadget do Aspire lê.

    Existe pra não haver dois lugares com os mesmos números. Antes disso
    o gadget tinha o PVC 10 mm escrito na mão, e a tabela daqui era
    enfeite — bastava alguém corrigir uma passada aqui pra máquina
    continuar cortando com a antiga.

    Grava 'unidade = "mm"' junto de propósito: quem lê tem que declarar
    milímetro antes de escrever os valores na ferramenta, senão o Aspire
    entende polegada (ver UNIDADE).
    """
    destino = pathlib.Path(destino or pathlib.Path(__file__).parent / "aspire" / "parametros_corte.lua")
    destino.parent.mkdir(parents=True, exist_ok=True)

    linhas = [
        # Sem acento de proposito: arquivo lido por um Lua de 2016.
        "-- GERADO por corte_parametros.exportar_para_lua() - nao edite a mao.",
        "-- Editar aqui nao muda o sistema: a proxima exportacao apaga.",
        "-- A fonte e corte_parametros.py, no raiz do projeto.",
        "",
        "return {",
        f'   unidade = "{UNIDADE}",',
        f"   avanco = {AVANCO_MM_MIN}, ataque = {ATAQUE_MM_MIN}, rotacao = {ROTACAO_RPM},",
        f"   passo_lateral = {PASSO_LATERAL_MM}, rampa = {RAMPA_SUAVE_MM},",
        "   materiais = {",
    ]
    for material, espessura in combinacoes_cadastradas():
        p = buscar(material, espessura)
        linhas.append(
            f'      ["{material} {espessura}"] = {{ '
            f'ferramenta = "{p["ferramenta"]}", diametro = {p["diametro_mm"]}, '
            f'passada = {p["passada_mm"]}, profundidade = {p["profundidade_mm"]}, '
            f'passes = {p["passes"]} }},')
    linhas += ["   },", "}", ""]

    destino.write_text("\n".join(linhas), encoding="utf-8")
    return destino


# Onde o Aspire 8.5 procura gadgets nesta maquina. Nao e a pasta que a
# documentacao da Vectric cita — aquela aqui tem so um readme.
PASTA_GADGETS = pathlib.Path(r"C:\ProgramData\Vectric\Aspire\V8.5\Gadgets")
NUCLEO = "C:/Users/flavi/Desktop/etiquetas_python/aspire/corte_nucleo.lua"

# O que vira atalho no menu do Aspire. É menor que PARAMETROS de
# propósito: o Flávio apontou as combinações que a casa realmente corta
# (06/09/2026), e menu com material que ninguém usa é menu que atrapalha.
#
# O cadastro continua completo — acrílico de 1, 2, 3, 5, 7 e 10 mm segue a
# mesma regra e não custa nada guardar. O que polui é o menu, não o
# cadastro: quando aparecer um trabalho nessas espessuras, é só acrescentar
# aqui e regerar, sem precisar descobrir parâmetro de novo.
MENU_FOCO = (
    ("PVC", 10), ("PVC", 20),
    ("MDF", 6), ("MDF", 9), ("MDF", 15),
    ("ACRILICO", 4), ("ACRILICO", 6), ("ACRILICO", 8),
)


def gerar_gadgets(pasta=None, instalar=False, apenas=None):
    """
    Gera um atalho por material, pra cada um virar uma entrada no menu
    Gadgets do Aspire: "Corte Automatico PVC 10", "Corte Automatico MDF 9"...

    Pedido do usuário (06/09/2026): escolher pelo menu em vez de editar
    uma linha do script. A alternativa seria o gadget ler o material do
    nome do arquivo — mais elegante e bem mais demorado, e ele foi direto
    ao ponto: "se for esperar desenho é mais complexo de resolver e vamos
    ficar travado".

    Cada atalho tem três linhas e nenhuma lógica: diz o material e chama
    o núcleo. A lógica mora num arquivo só (corte_nucleo.lua), fora da
    pasta de gadgets — se morasse dentro, viraria uma entrada de menu
    inútil, porque o Aspire lista todo .lua que encontra lá.

    O nome do arquivo vira o nome no menu, com os '_' virando espaço — é
    assim que 'DXF_Batch_Processor.lua' aparece como 'DXF Batch Processor'.
    """
    pasta = pathlib.Path(pasta) if pasta else PASTA_GADGETS
    if instalar:
        pasta.mkdir(parents=True, exist_ok=True)

    escolhidas = list(apenas) if apenas is not None else list(MENU_FOCO)
    gerados, faltando = [], []
    for material, espessura in escolhidas:
        if buscar(material, espessura) is None:
            faltando.append((material, espessura))
            continue
        chave = f"{material} {espessura}"
        nome = f"Corte_Automatico_{material}_{espessura}.lua"
        conteudo = "\n".join([
            # O Aspire recusa o arquivo inteiro se a PRIMEIRA linha nao for
            # esta: "Error: Script does not start with -- VECTRIC LUA SCRIPT".
            "-- VECTRIC LUA SCRIPT",
            "--",
            "-- GERADO por corte_parametros.gerar_gadgets() - nao edite a mao.",
            "-- Editar aqui nao muda nada: a proxima geracao apaga.",
            f"-- Aparece no menu como: Corte Automatico {material} {espessura}",
            "--",
            "-- Tres linhas e nenhuma logica: diz o material e chama o nucleo.",
            "",
            f'MATERIAL_DO_GADGET = "{chave}"',
            f'dofile("{NUCLEO}")',
            "",
        ])
        destino = pasta / nome
        if instalar:
            destino.write_text(conteudo, encoding="ascii")
        gerados.append((chave, destino, conteudo))
    return gerados, faltando


def material_e_espessura(nome_arquivo, config=None):
    """
    Descobre material e espessura pelo NOME do arquivo, do jeito que o
    resto do sistema já faz.

    Devolve (material, espessura) ou None. Nunca chuta: se o nome não
    disser a espessura, ou se a combinação não estiver cadastrada, é None
    e quem chamou decide o que fazer.

    A espessura não sai de qualquer "NNmm" do nome, e sim do cruzamento
    com o que está cadastrado pra aquele material. Sem isso, um nome como
    "PVC 10MM ... 1500MM de largura" daria espessura 1500.
    """
    import json

    import dimensoes

    if config is None:
        caminho = pathlib.Path(__file__).parent / "config.json"
        config = json.loads(caminho.read_text(encoding="utf-8"))

    nome = str(nome_arquivo).upper()
    material, _ = dimensoes.identificar_categoria(
        nome, config["materiais"], config.get("sinonimos_categoria", {}))
    if material is None:
        return None

    conhecidas = {e for m, e in PARAMETROS if m == material}
    achadas = [int(n) for n in re.findall(r"(\d{1,3})\s*MM", nome)]
    candidatas = [e for e in achadas if e in conhecidas]
    if not candidatas:
        return None
    return (material, candidatas[0])


def atalho_do_menu(nome_arquivo, config=None):
    """
    Qual entrada do menu Gadgets usar pra este arquivo — ou None.

    Existe pra tirar a escolha do material da cabeça de quem opera. Clicar
    no atalho errado corta com a passada errada, e isso não dá erro: dá
    peça estragada.
    """
    achado = material_e_espessura(nome_arquivo, config)
    if achado is None or achado not in MENU_FOCO:
        return None
    return f"Corte Automatico {achado[0]} {achado[1]}"
