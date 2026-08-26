"""
Funções relacionadas à leitura de medidas no nome do arquivo e ao
cálculo de desperdício de material. São funções "puras" (não mexem em
arquivo, não imprimem nada) de propósito, para serem fáceis de testar
isoladamente — veja tests/test_dimensoes.py.
"""
import math
import re

# Unidades reconhecidas no nome do arquivo, e seu fator de conversão pra metros.
# Isso é físico (mm/cm/m), não precisa ser configurável pelo usuário.
FATORES_UNIDADE = {"MM": 0.001, "CM": 0.01, "M": 1.0}


def contem_palavra(texto, termo):
    """
    Verifica se 'termo' aparece em 'texto' como palavra inteira, e não
    como parte de outra palavra. Evita falso positivo como "PS" sendo
    encontrado dentro de "XPS" (que na verdade deve virar PVC) — por
    isso, antes do termo não pode vir letra nem número.

    Depois do termo, um número colado é permitido (mas não uma letra):
    nomes reais do dia a dia colam a medida direto no material, tipo
    "VINIL150" (Vinil, 150cm de largura) sem espaço ou underscore
    separando. Se essa checagem fosse simétrica, esse arquivo real
    ficaria sem categoria nenhuma e seria ignorado inteiro — pior que o
    risco (bem menor) de uma coincidência tipo "PS2" nunca visto na
    prática.
    """
    padrao = r'(?<![A-Z0-9])' + re.escape(termo) + r'(?![A-Z])'
    return re.search(padrao, texto) is not None


def identificar_categoria(nome_arquivo_upper, materiais, sinonimos_categoria=None):
    """
    Descobre qual categoria de material o nome do arquivo indica,
    verificando tanto o nome da categoria direto (ex: "LONA") quanto os
    sinônimos configurados (ex: "VINIL" -> "ADESIVO"). Quando mais de
    uma categoria bate no nome, a mais específica (nome mais longo)
    vence — categorias com nome curto como "PS" têm mais chance de
    coincidir com uma sigla de projeto sem relação nenhuma com o
    material (ex: um código como "..._PS_01_..." num arquivo que na
    verdade é PVC), então não faz sentido a primeira da lista ganhar só
    por causa da ordem no config.json.

    Retorna (categoria_mais_especifica_ou_None, lista_de_categorias_
    candidatas) — a lista com mais de um item sinaliza nome ambíguo,
    pra quem chamar decidir se quer avisar sobre isso.
    """
    sinonimos_categoria = sinonimos_categoria or {}
    categorias_encontradas = []
    for cat in materiais:
        if contem_palavra(nome_arquivo_upper, cat) and cat not in categorias_encontradas:
            categorias_encontradas.append(cat)
    for sinonimo, cat_real in sinonimos_categoria.items():
        if cat_real not in materiais:
            continue
        if contem_palavra(nome_arquivo_upper, sinonimo) and cat_real not in categorias_encontradas:
            categorias_encontradas.append(cat_real)

    if not categorias_encontradas:
        return None, categorias_encontradas

    return max(categorias_encontradas, key=len), categorias_encontradas


def extrair_dimensoes(nome_arquivo, typos_unidade=None):
    """
    Procura no nome do arquivo um padrão do tipo "NUMEROxNUMERO" seguido
    (ou não) de uma unidade (MM, CM, M, ou um dos erros de digitação
    conhecidos em 'typos_unidade'), pega a PRIMEIRA ocorrência, converte
    tudo pra metros e calcula a área em m².

    Quando o nome tem duas medidas, a primeira é sempre a medida real
    que o cliente mandou; a segunda (se houver) é um acréscimo que a
    produção coloca depois (por exemplo, uma margem extra) — por isso
    a primeira é a que vale pra etiqueta, OS e cálculo de desperdício,
    nunca a segunda.

    'typos_unidade' é um dicionário configurável (vem do config.json)
    mapeando um erro de digitação comum para a unidade real, por exemplo
    {"XM": "CM"} — assim, se no futuro aparecer outro erro de digitação
    recorrente, basta cadastrar no config.json, sem mexer em código.

    Se nenhuma unidade for encontrada, assume CM por padrão (unidade
    mais comum nos nomes de arquivo da fábrica).

    Retorna um dicionário com os detalhes, ou None se não encontrar
    nenhum padrão de medida no nome.
    """
    if typos_unidade is None:
        typos_unidade = {}

    nome_upper = nome_arquivo.upper()

    # Tokens de unidade reconhecidos no regex: as unidades válidas +
    # os erros de digitação configurados. Ordenado do mais longo pro
    # mais curto para o regex não "parar" num token curto (ex: "M")
    # quando na verdade era um token mais longo (ex: "MM").
    tokens_unidade = sorted(
        set(list(FATORES_UNIDADE.keys()) + list(typos_unidade.keys())),
        key=len, reverse=True,
    )
    grupo_unidades = "|".join(re.escape(t) for t in tokens_unidade)

    padrao = rf'(\d+(?:[.,]\d+)?)\s*X\s*(\d+(?:[.,]\d+)?)\s*({grupo_unidades})?(?![A-Z])'
    matches = list(re.finditer(padrao, nome_upper))
    if not matches:
        return None

    m = matches[0]  # primeira ocorrência no nome — é a medida real do cliente
    valor1 = float(m.group(1).replace(',', '.'))
    valor2 = float(m.group(2).replace(',', '.'))
    unidade_bruta = m.group(3)

    unidade_corrigida = False
    if unidade_bruta is None:
        unidade_usada = "CM"
    elif unidade_bruta in typos_unidade:
        unidade_usada = typos_unidade[unidade_bruta]
        unidade_corrigida = True
    else:
        unidade_usada = unidade_bruta

    if unidade_usada not in FATORES_UNIDADE:
        # segurança: se o config.json mapear um typo para algo que não é
        # uma unidade válida, não deixa o script quebrar — assume CM.
        unidade_usada = "CM"

    fator = FATORES_UNIDADE[unidade_usada]
    largura_m = valor1 * fator
    altura_m = valor2 * fator
    area_m2 = largura_m * altura_m

    return {
        "largura_m": largura_m,
        "altura_m": altura_m,
        "area_m2": area_m2,
        "unidade_usada": unidade_usada,
        "medida_bruta": m.group(0).strip(),
        "unidade_corrigida": unidade_corrigida,
        "unidade_bruta": unidade_bruta,
    }


def extrair_quantidade(nome_arquivo):
    """
    Procura a quantidade no início do nome do arquivo, no padrão "NUN"
    (ex: "1UN", "2UN"), do jeito que já vem nos arquivos da fábrica.

    Se não encontrar, assume 1 e sinaliza isso pra quem chamou poder
    avisar no log — mesmo espírito de tolerância a erro usado em
    extrair_dimensoes.

    Retorna (quantidade, encontrada).
    """
    m = re.match(r'\s*(\d+)\s*UN\b', nome_arquivo.upper())
    if m:
        return int(m.group(1)), True
    return 1, False


def identificar_variante(nome_arquivo, variantes):
    """
    Procura, no nome do arquivo, qual das 'variantes' cadastradas para
    a categoria (espessura, e opcionalmente cor — ex: chapas especiais
    de PVC/PS/Acrílico/MDF) combina com o nome.

    A 'cor' é opcional numa variante: quando presente, tanto a espessura
    quanto a cor precisam aparecer como palavra inteira no nome (ex:
    MDF 6mm verde = "MDF Hidro"); quando ausente, só a espessura precisa
    bater (o caso padrão, sem distinção de cor — ex: MDF cru, que nunca
    tem cor no nome do arquivo). Variantes com cor são conferidas
    primeiro, pra um arquivo "MDF 6MM VERDE" não cair na variante crua
    de 6mm só porque a espessura também bate ali.

    O tamanho da chapa não muda entre variantes (é o mesmo já cadastrado
    na categoria), então isso serve só para identificar/rotular qual
    variante é, não para o cálculo de desperdício.

    Retorna o dicionário da variante encontrada, ou None se nenhuma
    bater (ou se a categoria não tem variantes cadastradas).
    """
    if not variantes:
        return None

    nome_upper = nome_arquivo.upper()

    for variante in variantes:
        if variante.get("cor") and contem_palavra(nome_upper, variante["espessura"]) and contem_palavra(nome_upper, variante["cor"]):
            return variante
    for variante in variantes:
        if not variante.get("cor") and contem_palavra(nome_upper, variante["espessura"]):
            return variante
    return None


def formatar_variante(variante):
    """
    Texto de exibição de uma variante — ex: "10MM · PRETO", ou
    "6MM · MDF HIDRO" quando a variante tem um rótulo próprio (nome
    comercial diferente da cor usada pra identificar, como o MDF verde
    que na prática é vendido como "MDF Hidro"), ou só "9MM" quando a
    variante não tem cor/rótulo (caso padrão).
    """
    if not variante:
        return ""
    complemento = variante.get("rotulo") or variante.get("cor")
    if complemento:
        return f"{variante['espessura']} · {complemento}"
    return variante["espessura"]


def calcular_desperdicio_item(dimensao, largura_rolo_m):
    """
    Calcula o desperdício de material ao cortar UMA peça de um rolo,
    seguindo o modelo de corte SEQUENCIAL: a peça usa a largura toda do
    rolo, orientada de forma que seu lado menor fique alinhado à largura
    do rolo (jeito mais comum de cortar lona/adesivo).

    O trecho do rolo consumido em comprimento é igual ao lado maior da
    peça; a sobra de largura (rolo - peça) ao longo desse comprimento
    todo é o desperdício.

    Retorna None se a peça for mais larga que o próprio rolo/chapa (não
    cabe, precisa de conferência manual).
    """
    peca_largura_m = min(dimensao["largura_m"], dimensao["altura_m"])
    peca_comprimento_m = max(dimensao["largura_m"], dimensao["altura_m"])

    if peca_largura_m > largura_rolo_m:
        return None

    desperdicio_m2 = (largura_rolo_m - peca_largura_m) * peca_comprimento_m

    return {
        "peca_largura_m": peca_largura_m,
        "peca_comprimento_m": peca_comprimento_m,
        "desperdicio_m2": desperdicio_m2,
    }


def calcular_desperdicio_chapa_grande(dimensao, largura_chapa_m, comprimento_chapa_m):
    """
    Estima quantas chapas são necessárias quando a peça não cabe numa
    chapa só (só faz sentido pra material tipo 'chapa' — rolo tem
    comprimento livre, então isso não se aplica a rolo).

    Monta a peça como uma grade de chapas (colunas x linhas), testando
    as duas orientações da peça (como veio, e girada 90°) e escolhendo
    a que usa menos chapas no total.

    É só uma estimativa por grade simples — não sabe se o desenho pode
    ser cortado bem nas emendas, então continua sendo necessário
    conferir manualmente antes de cortar de verdade.
    """
    largura_peca = dimensao["largura_m"]
    altura_peca = dimensao["altura_m"]

    def _grade(largura_p, altura_p):
        colunas = math.ceil(largura_p / largura_chapa_m)
        linhas = math.ceil(altura_p / comprimento_chapa_m)
        return colunas, linhas

    colunas_normal, linhas_normal = _grade(largura_peca, altura_peca)
    colunas_girada, linhas_girada = _grade(altura_peca, largura_peca)

    if colunas_normal * linhas_normal <= colunas_girada * linhas_girada:
        colunas, linhas, girada = colunas_normal, linhas_normal, False
    else:
        colunas, linhas, girada = colunas_girada, linhas_girada, True

    total_chapas = colunas * linhas
    area_chapas_m2 = total_chapas * largura_chapa_m * comprimento_chapa_m
    area_peca_m2 = largura_peca * altura_peca

    return {
        "colunas": colunas,
        "linhas": linhas,
        "total_chapas": total_chapas,
        "girada": girada,
        "desperdicio_m2": area_chapas_m2 - area_peca_m2,
    }
