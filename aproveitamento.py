"""
Quanto material um LOTE de peças consome, encaixando tudo junto — rolo ou chapa.

Por que existe (28/09/2026, pedido do usuário): *"tirar melhor proveito do
material sempre, independente se for chapa ou rolo, a intenção sempre é
economizar ao máximo; o desperdício deve ser calculado como um todo, assim
podemos calcular melhor nossa saída de material do estoque"*.

Até aqui a conta era POR PEÇA (dimensoes.calcular_desperdicio_item): cada peça
ocupava a largura inteira do rolo sozinha e o que sobrava do lado dela contava
como perdido. Duas peças de 1,00 m num rolo de 3,20 davam 4,40 m² de
desperdício, quando na máquina elas saem lado a lado. E chapa era tratada como
rolo — uma fila de faixas —, então um PS de 1,80 × 0,50 numa chapa de
2,00 × 1,00 "perdia" 2,70 m² que na bancada viram a peça seguinte.

Aqui o lote inteiro de um mesmo material (categoria + variante) é encaixado
junto:

- ROLO: a largura é teto, o comprimento anda. Minimiza os METROS de rolo.
- CHAPA: os dois lados são teto. Minimiza o número de CHAPAS.

O encaixe é sempre de GUILHOTINA: todo corte vai de uma borda à outra da sobra,
como estilete na régua, serra ou guilhotina fazem. Um encaixe que só a fresa
cortaria pareceria economia no papel e seria impossível na bancada.

Peça maior que o material (lona de 5 m de lado num rolo de 3,20; painel maior
que a chapa) entra DIVIDIDA — faixas no rolo, grade de chapas — e as partes
encaixam como qualquer outra peça. A emenda (sobreposição, solda) NÃO é
contada; por isso o resultado diz quantas peças foram divididas, e quem mostra
o número tem que dizer isso.

É sempre estimativa: o encaixe de verdade sai do RIP ou da mão de quem corta.
O número daqui é o consumo de um encaixe bom e POSSÍVEL, pra baixa de estoque
e custo — e sai escrito como estimativa (regra da casa: número deduzido nunca
se passa por declarado).

Tudo em milímetros inteiros por dentro: 1,26 + 0,94 tem que caber em 2,20 sem
a vírgula flutuante decidir que não cabe.
"""
import math

# Acima disto (peças somadas no lote), peças iguais entram em BLOCOS já
# arrumados em grade, pra conta de 500 adesivos de 10 × 10 cm caber em
# segundos. Abaixo, cada peça é encaixada uma a uma.
LIMITE_PECAS = 300

# Quantos blocos, no máximo, uma arte repetida vira quando entra em blocos.
_BLOCOS_POR_ARTE = 8

# Acima de tantas peças (ou blocos) num lote de chapa, tenta menos variações.
_LOTE_GRANDE = 400

# Ordens em que as peças são tentadas; o melhor resultado vence.
_ORDENS = (
    lambda p: (-max(p), -min(p)),         # lado maior primeiro
    lambda p: (-p[0] * p[1], -max(p)),    # área maior primeiro
    lambda p: (-min(p), -max(p)),         # lado menor primeiro
)


def _mm(metros):
    return int(round(float(metros) * 1000))


class _Pedaco:
    """
    Um pedaço de material com os retângulos livres da guilhotina: uma chapa,
    ou o rolo (altura praticamente sem fim). Retângulo = (x, y, largura, altura).
    """
    __slots__ = ("largura", "altura", "livres", "topo", "ocupado", "maior_descartado",
                 "postas", "marcas")

    def __init__(self, largura, altura):
        self.largura = largura
        self.altura = altura
        self.livres = [(0, 0, largura, altura)]
        self.topo = 0
        self.ocupado = 0
        self.maior_descartado = (0, 0, 0)  # (área, largura, altura): conta como retalho
        self.postas = []  # (x, y, largura, altura) de cada peça — é o que os testes conferem
        # Quem é cada posta, na mesma ordem. Duas peças de mesma medida NÃO
        # são intercambiáveis quando a arte é outra: a LATERAL_ESQUERDA e a
        # LATERAL_DIREITA têm 0,90 x 2,40 as duas, e casar por medida depois
        # poria o rótulo de uma na outra (04/10/2026).
        self.marcas = []

    def melhor_lugar(self, orientacoes, regra):
        """(nota, índice do livre, largura, altura) do melhor lugar, ou None."""
        melhor = None
        for i, (x, y, lw, lh) in enumerate(self.livres):
            for pw, ph in orientacoes:
                if pw > lw or ph > lh:
                    continue
                if regra == "baixo":
                    nota = (y + ph, x)
                elif regra == "area":
                    nota = (lw * lh - pw * ph, min(lw - pw, lh - ph))
                else:  # "lado": a sobra mais justa de um dos lados
                    a, b = lw - pw, lh - ph
                    nota = (min(a, b), max(a, b))
                if melhor is None or nota < melhor[0]:
                    melhor = (nota, i, pw, ph)
        return melhor

    def colocar(self, i, pw, ph, divisao, menor_lado, marca=None):
        """
        Põe a peça no canto do retângulo livre 'i' e corta a sobra em dois
        retângulos por um corte reto de ponta a ponta (guilhotina). Sobra onde
        nenhuma peça do lote cabe (lado menor que o menor lado de qualquer peça)
        sai da busca — não é desperdício diferente, só não adianta procurar lá
        (mas continua valendo como retalho).
        """
        x, y, lw, lh = self.livres.pop(i)
        sobra_w, sobra_h = lw - pw, lh - ph
        if divisao == "prateleira":
            horizontal = True
        elif divisao == "coluna":
            horizontal = False
        elif divisao == "menor_sobra":
            horizontal = sobra_w <= sobra_h
        elif divisao == "maior_sobra":
            horizontal = sobra_w > sobra_h
        else:  # "maior_area": o corte que deixa o maior retângulo inteiro
            horizontal = lw * sobra_h >= sobra_w * lh
        if horizontal:
            novos = ((x + pw, y, sobra_w, ph), (x, y + ph, lw, sobra_h))
        else:
            novos = ((x + pw, y, sobra_w, lh), (x, y + ph, pw, sobra_h))
        for r in novos:
            if r[2] >= menor_lado and r[3] >= menor_lado:
                self.livres.append(r)
            elif r[2] > 0 and r[3] > 0:
                self.maior_descartado = max(self.maior_descartado, (r[2] * r[3], r[2], r[3]))
        self.topo = max(self.topo, y + ph)
        self.ocupado += pw * ph
        self.postas.append((x, y, pw, ph))
        self.marcas.append(marca)

    def fechar_faixa(self):
        """
        Rolo sem lugar pra peça: corta o rolo de ponta a ponta acima de tudo o
        que já foi posto e abre uma faixa nova, da largura inteira. Os livres de
        baixo são aparados até o corte — continuam valendo pra peça menor.
        """
        aparados = []
        for x, y, lw, lh in self.livres:
            if y < self.topo:
                aparados.append((x, y, lw, min(lh, self.topo - y)))
        aparados.append((0, self.topo, self.largura, self.altura - self.topo))
        self.livres = aparados

    def maior_livre(self):
        """O maior retângulo que sobrou inteiro: (área, largura, altura)."""
        return max([(lw * lh, lw, lh) for _, _, lw, lh in self.livres] + [self.maior_descartado])


def _orientacoes(w, h, largura, altura, politica="livre", fixa=False):
    """
    As orientações da peça que cabem no pedaço (sem repetir quadrado).

    'fixa' tranca a peça como ela entrou. Quem usa é a montagem, pra peça
    que enche a bobina: ela só cabe deitada, e deitada o retângulo
    reservado não tem folga sobrando — virada de volta, o rótulo ficaria
    sem a faixa dele e sairia por cima da peça vizinha.
    """
    if fixa:
        candidatas = [(w, h)]
    elif politica == "estreita":
        # como se corta por hábito: o lado menor atravessando a largura do rolo
        candidatas = [(min(w, h), max(w, h))]
    else:
        candidatas = [(w, h)] if w == h else [(w, h), (h, w)]
    return [(pw, ph) for pw, ph in candidatas if pw <= largura and ph <= altura]


# ------------------------------------------------------------ peça grande

def _dividir_no_rolo(w, h, largura):
    """
    Peça com os dois lados maiores que o rolo vira faixas. Testa dividir o lado
    menor (faixas compridas) e o lado maior (faixas curtas) e fica com o que
    gasta menos rolo sozinho. As faixas vão cheias e a última leva o resto —
    faixa estreita encaixa ao lado de outra peça.
    """
    s, comprido = min(w, h), max(w, h)
    if s <= largura:
        return [(w, h)]
    opcoes = []
    for lado_dividido, outro in ((s, comprido), (comprido, s)):
        n = math.ceil(lado_dividido / largura)
        partes = [(largura, outro)] * (n - 1) + [(lado_dividido - (n - 1) * largura, outro)]
        opcoes.append((n * outro, partes))
    return min(opcoes, key=lambda o: o[0])[1]


def _dividir_na_chapa(w, h, largura, altura):
    """
    Peça que não cabe na chapa em pé nem deitada vira grade de chapas (como
    dimensoes.calcular_desperdicio_chapa_grande, que continua existindo pra
    peça sozinha); as partes da borda são menores e encaixam com as outras.
    """
    if (w <= largura and h <= altura) or (h <= largura and w <= altura):
        return [(w, h)]
    melhor = None
    for pw, ph in ((w, h), (h, w)):
        colunas, linhas = math.ceil(pw / largura), math.ceil(ph / altura)
        if melhor is None or colunas * linhas < melhor[0]:
            melhor = (colunas * linhas, pw, ph, colunas, linhas)
    _, pw, ph, colunas, linhas = melhor
    partes = []
    for c in range(colunas):
        pedaco_w = largura if c < colunas - 1 else pw - (colunas - 1) * largura
        for r in range(linhas):
            pedaco_h = altura if r < linhas - 1 else ph - (linhas - 1) * altura
            partes.append((pedaco_w, pedaco_h))
    return partes


def partes_da_peca(largura_m, altura_m, tipo, largura_material_m, comprimento_material_m):
    """Em quantas partes a peça entra no cálculo (1 = cabe inteira)."""
    w, h = _mm(largura_m), _mm(altura_m)
    if tipo == "rolo":
        return len(_dividir_no_rolo(w, h, _mm(largura_material_m)))
    return len(_dividir_na_chapa(w, h, _mm(largura_material_m), _mm(comprimento_material_m)))


# ----------------------------------------------------------- muitas iguais

def _em_blocos(w, h, quantidade, largura, altura):
    """
    'quantidade' peças iguais viram poucos blocos já em grade (colunas ×
    linhas), no máximo _BLOCOS_POR_ARTE. Escolhe a orientação que põe mais
    peças por fileira. Só usado acima de LIMITE_PECAS.
    """
    opcoes = _orientacoes(w, h, largura, altura)
    if not opcoes:
        return [(w, h)] * quantidade
    pw, ph = max(opcoes, key=lambda o: (largura // o[0], -o[1]))
    por_fileira = max(1, largura // pw)
    fileiras_cheias, resto = divmod(quantidade, por_fileira)
    fileiras_por_bloco = max(1, math.ceil(fileiras_cheias / _BLOCOS_POR_ARTE))
    fileiras_por_bloco = min(fileiras_por_bloco, max(1, altura // ph))
    blocos = []
    while fileiras_cheias > 0:
        n = min(fileiras_por_bloco, fileiras_cheias)
        blocos.append((por_fileira * pw, n * ph))
        fileiras_cheias -= n
    if resto:
        blocos.append((resto * pw, ph))
    return blocos


# --------------------------------------------------------------- encaixes

def _encaixar_no_rolo(pecas, largura, ordem, politica, divisao):
    """
    O rolo (_Pedaco) encaixado — 'topo' é o que ele gasta —, ou None se a
    política não serve.

    'pecas' é [(w, h)], [(w, h, marca)] ou [(w, h, marca, fixa)]. A marca
    atravessa o encaixe sem participar da conta e volta em _Pedaco.marcas:
    é o que deixa quem desenha saber qual arte é cada posição (ver
    posicoes_no_rolo). 'fixa' tranca a orientação daquela peça.
    """
    altura = sum(max(p[0], p[1]) for p in pecas) + 1
    rolo = _Pedaco(largura, altura)
    menor_lado = min(min(p[0], p[1]) for p in pecas)
    for peca in sorted(pecas, key=lambda p: ordem(p[:2])):
        w, h = peca[0], peca[1]
        marca = peca[2] if len(peca) > 2 else None
        orientacoes = _orientacoes(w, h, largura, altura, politica,
                                   fixa=len(peca) > 3 and peca[3])
        if not orientacoes:
            return None
        lugar = rolo.melhor_lugar(orientacoes, "baixo")
        if lugar is None:
            rolo.fechar_faixa()
            lugar = rolo.melhor_lugar(orientacoes, "baixo")
        _, i, pw, ph = lugar
        rolo.colocar(i, pw, ph, divisao, menor_lado, marca)
    return rolo


def _encaixar_em_chapas(pecas, largura, altura, ordem, regra, divisao):
    """As chapas (_Pedaco) que o encaixe usa. Aceita (w, h) ou (w, h, marca)."""
    chapas = []
    menor_lado = min(min(p[0], p[1]) for p in pecas)
    for peca in sorted(pecas, key=lambda p: ordem(p[:2])):
        w, h = peca[0], peca[1]
        marca = peca[2] if len(peca) > 2 else None
        orientacoes = _orientacoes(w, h, largura, altura)
        escolhido = None
        for chapa in chapas:
            lugar = chapa.melhor_lugar(orientacoes, regra)
            if lugar is None:
                continue
            if regra == "baixo":
                # "baixo" não compara chapas entre si: fica na primeira que cabe
                escolhido = (chapa, lugar)
                break
            if escolhido is None or lugar[0] < escolhido[1][0]:
                escolhido = (chapa, lugar)
        if escolhido is None:
            chapa = _Pedaco(largura, altura)
            chapas.append(chapa)
            escolhido = (chapa, chapa.melhor_lugar(orientacoes, regra))
        chapa, (_, i, pw, ph) = escolhido
        chapa.colocar(i, pw, ph, divisao, menor_lado, marca)
    return chapas


def posicoes_no_rolo(pecas, largura_m):
    """
    ONDE cada peça fica no rolo, não só quantos metros ele gasta. Devolve
    ([(marca, x_m, y_m, largura_m, altura_m, girada)], metros) — ou
    ([], 0.0) quando não há peça utilizável.

    'pecas' é [(largura_m, altura_m, marca)]. A marca é obrigatória e volta
    junto: duas peças de mesma medida não são intercambiáveis quando a arte
    é outra (a LATERAL_ESQUERDA e a LATERAL_DIREITA têm 0,90 x 2,40 as
    duas), então casar por medida depois poria o rótulo de uma na outra.

    É a MESMA conta de calcular_lote, com a mesma busca pela melhor
    estratégia — o que muda é só o que se guarda no fim. Até 04/10/2026 as
    coordenadas eram calculadas e descartadas, porque ninguém desenhava
    nada: só o número de metros alimentava o custo e o estoque.

    Quem monta a folha precisa somar a folga de corte e a canaleta de
    dados à medida de cada peça ANTES de chamar — aqui as peças se tocam.
    """
    largura = _mm(largura_m)
    entrada = []
    for item in pecas:
        w, h = _mm(item[0]), _mm(item[1])
        if w <= 0 or h <= 0 or w > largura and h > largura:
            continue
        entrada.append((w, h, item[2] if len(item) > 2 else None,
                        len(item) > 3 and item[3]))
    if not entrada:
        return [], 0.0

    melhor = None
    for ordem in _ORDENS:
        for politica in ("livre", "estreita"):
            for divisao in ("prateleira", "coluna"):
                rolo = _encaixar_no_rolo(entrada, largura, ordem, politica, divisao)
                if rolo is not None and (melhor is None or rolo.topo < melhor.topo):
                    melhor = rolo
    if melhor is None:
        return [], 0.0

    # a peça saiu girada quando a largura posta não é a que entrou
    medida = {}
    for w, h, marca, _fixa in entrada:
        medida.setdefault(marca, (w, h))
    postas = []
    for (x, y, pw, ph), marca in zip(melhor.postas, melhor.marcas):
        original = medida.get(marca, (pw, ph))
        girada = (pw, ph) != original
        postas.append((marca, x / 1000, y / 1000, pw / 1000, ph / 1000, girada))
    return postas, melhor.topo / 1000


def posicoes_em_chapas(pecas, largura_m, altura_m):
    """
    ONDE cada peça fica, chapa por chapa:
    [[(marca, x_m, y_m, largura_m, altura_m, girada), ...], ...] — uma
    lista por chapa, na ordem em que elas são usadas.

    Irmã de posicoes_no_rolo, pra máquina PLANA: aqui os dois lados são
    teto, então não existe "o rolo anda" — o que sobra é número de
    chapas. A marca volta junto pelo mesmo motivo (duas peças de mesma
    medida não são intercambiáveis quando a arte é outra).
    """
    largura, altura = _mm(largura_m), _mm(altura_m)
    entrada = []
    for item in pecas:
        w, h = _mm(item[0]), _mm(item[1])
        cabe = (w <= largura and h <= altura) or (h <= largura and w <= altura)
        if w <= 0 or h <= 0 or not cabe:
            continue
        entrada.append((w, h, item[2] if len(item) > 2 else None))
    if not entrada:
        return []

    melhor = None
    for ordem in _ORDENS:
        for regra in ("area", "lado", "baixo"):
            for divisao in ("menor_sobra", "maior_sobra", "maior_area"):
                chapas = _encaixar_em_chapas(entrada, largura, altura, ordem, regra, divisao)
                nota = (len(chapas), -max(c.maior_livre() for c in chapas)[0])
                if melhor is None or nota < melhor[0]:
                    melhor = (nota, chapas)
    if melhor is None:
        return []

    medida = {}
    for w, h, marca in entrada:
        medida.setdefault(marca, (w, h))
    saida = []
    for chapa in melhor[1]:
        postas = []
        for (x, y, pw, ph), marca in zip(chapa.postas, chapa.marcas):
            original = medida.get(marca, (pw, ph))
            postas.append((marca, x / 1000, y / 1000, pw / 1000, ph / 1000,
                           (pw, ph) != original))
        saida.append(postas)
    return saida


# ------------------------------------------------------------------- lote

def calcular_lote(pecas, tipo, largura_m, comprimento_m):
    """
    Consumo do lote inteiro de UM material.

    'pecas': [(largura_m, altura_m, quantidade), ...] — uma entrada por arte.
    'tipo': "rolo" ou "chapa"; 'largura_m' × 'comprimento_m' é o rolo (largura
    útil × comprimento da bobina) ou a chapa.

    Devolve None quando nenhuma peça tem medida; senão:
      area_pecas_m2       o que vira peça
      area_consumida_m2   o que sai do estoque (metros × largura, ou chapas × área da chapa)
      desperdicio_m2      a diferença — do LOTE, não por peça
      aproveitamento      área das peças ÷ área consumida
      metros, rolos       (rolo) metros de bobina e a fração de bobina que isso é
      chapas              (chapa) chapas inteiras
      maior_retalho_m     (chapa) (largura, altura) do maior pedaço inteiro que sobra, ou None
      pecas               quantas peças físicas
      pecas_divididas     quantas eram maiores que o material e entraram em partes
                          (a emenda NÃO está contada)
    """
    largura, altura = _mm(largura_m), _mm(comprimento_m)
    if largura <= 0 or (tipo != "rolo" and altura <= 0):
        return None

    area_pecas = 0
    total_pecas = 0
    divididas = 0
    arrumadas = []  # (w, h, quantidade) já cabendo no material
    for largura_peca, altura_peca, quantidade in pecas:
        w, h = _mm(largura_peca), _mm(altura_peca)
        quantidade = int(quantidade or 1)
        if w <= 0 or h <= 0 or quantidade <= 0:
            continue
        area_pecas += w * h * quantidade
        total_pecas += quantidade
        if tipo == "rolo":
            partes = _dividir_no_rolo(w, h, largura)
        else:
            partes = _dividir_na_chapa(w, h, largura, altura)
        if len(partes) > 1:
            divididas += quantidade
        for pw, ph in partes:
            arrumadas.append((pw, ph, quantidade))
    if not arrumadas:
        return None

    lista = []
    em_blocos = sum(q for _, _, q in arrumadas) > LIMITE_PECAS
    altura_bloco = altura if tipo != "rolo" else sum(max(w, h) * q for w, h, q in arrumadas)
    for w, h, q in arrumadas:
        if em_blocos and q > 1:
            lista.extend(_em_blocos(w, h, q, largura, altura_bloco))
        else:
            lista.extend([(w, h)] * q)

    resultado = {
        "tipo": tipo, "largura_m": largura / 1000, "comprimento_m": altura / 1000,
        "area_pecas_m2": area_pecas / 1e6, "pecas": total_pecas, "pecas_divididas": divididas,
    }
    if tipo == "rolo":
        melhor = None
        for ordem in _ORDENS:
            for politica in ("livre", "estreita"):
                for divisao in ("prateleira", "coluna"):
                    rolo = _encaixar_no_rolo(lista, largura, ordem, politica, divisao)
                    if rolo is not None and (melhor is None or rolo.topo < melhor):
                        melhor = rolo.topo
        consumida = melhor * largura
        resultado["metros"] = melhor / 1000
        resultado["rolos"] = melhor / altura if altura > 0 else None
    else:
        # lote grande tenta só as combinações que mais ganham (medido em
        # 28/09/2026 em 120 lotes sorteados): as outras quase nunca mudam a conta
        grande = len(lista) > _LOTE_GRANDE
        ordens = _ORDENS[:2] if grande else _ORDENS
        regras = ("area", "lado") if grande else ("area", "lado", "baixo")
        divisoes = ("menor_sobra", "maior_sobra") if grande else ("menor_sobra", "maior_sobra", "maior_area")
        melhor = None
        for ordem in ordens:
            for regra in regras:
                for divisao in divisoes:
                    chapas = _encaixar_em_chapas(lista, largura, altura, ordem, regra, divisao)
                    retalho = max(c.maior_livre() for c in chapas)
                    # menos chapas; empate: a sobra mais inteira (retalho que ainda serve)
                    nota = (len(chapas), -retalho[0])
                    if melhor is None or nota < melhor[0]:
                        melhor = (nota, chapas, retalho)
        _, chapas, retalho = melhor
        consumida = len(chapas) * largura * altura
        resultado["chapas"] = len(chapas)
        resultado["maior_retalho_m"] = (retalho[1] / 1000, retalho[2] / 1000) if retalho[0] else None

    resultado["area_consumida_m2"] = consumida / 1e6
    resultado["desperdicio_m2"] = (consumida - area_pecas) / 1e6
    resultado["aproveitamento"] = area_pecas / consumida if consumida else 0.0
    return resultado


# --------------------------------------------------------------- materiais

def _chave_variante(variante):
    """A variante pelo que ela É: espessura e cor. Preço, rótulo etc. não separam lote."""
    if not variante:
        return None
    return (variante.get("espessura") or "", variante.get("cor") or "")


def consumo_por_material(itens, materiais):
    """
    Agrupa os itens (da OS, do estado do pedido ou do JSON da baixa) pelo
    material que sai do estoque — categoria + variante — e encaixa cada grupo
    como um lote só. Material composto ("PS ADESIVADO"): a mesma peça entra no
    lote de PS (com a variante dela) e no de ADESIVO (sem variante — a espessura
    é da chapa, não do adesivo colado nela).

    Devolve, na ordem em que os materiais aparecem:
      [{'categoria', 'variante', **calcular_lote(...)}]
    Item sem medida ou de categoria sem cadastro não entra.
    """
    grupos = {}
    for item in itens:
        dimensao = item.get("dimensao")
        if not dimensao:
            continue
        peca = (dimensao["largura_m"], dimensao["altura_m"], item.get("quantidade") or 1)
        destinos = [(item.get("categoria"), item.get("variante"))]
        if item.get("categoria_extra"):
            destinos.append((item["categoria_extra"], None))
        for categoria, variante in destinos:
            if categoria not in (materiais or {}):
                continue
            grupo = grupos.setdefault((categoria, _chave_variante(variante)),
                                      {"categoria": categoria, "variante": variante, "pecas": []})
            grupo["pecas"].append(peca)

    consumos = []
    for grupo in grupos.values():
        info = materiais[grupo["categoria"]]
        lote = calcular_lote(grupo["pecas"], info["tipo"], info["largura_cm"] / 100,
                             info["comprimento_cm"] / 100)
        if lote:
            consumos.append({"categoria": grupo["categoria"], "variante": grupo["variante"], **lote})
    return consumos


def descrever(consumo):
    """Uma linha pro log: quanto sai do estoque, a sobra do lote e o aproveitamento."""
    from dimensoes import formatar_variante

    nome = consumo["categoria"]
    if consumo.get("variante"):
        nome += " " + formatar_variante(consumo["variante"])
    if consumo["tipo"] == "rolo":
        saida = (f"{consumo['metros']:.2f} m de rolo de {consumo['largura_m']:.2f} m"
                 + (f" (~{consumo['rolos']:.2f} de uma bobina de {consumo['comprimento_m']:.0f} m)"
                    if consumo.get("rolos") is not None else ""))
    else:
        saida = (f"{consumo['chapas']} chapa(s) de "
                 f"{consumo['largura_m']:.2f} x {consumo['comprimento_m']:.2f} m")
    texto = (f"Consumo {nome}: {saida} para {consumo['area_pecas_m2']:.2f} m² de peças — "
             f"sobra {consumo['desperdicio_m2']:.2f} m², {consumo['aproveitamento']:.0%} aproveitado "
             f"(estimativa, peças encaixadas juntas)")
    if consumo.get("maior_retalho_m"):
        texto += "; maior retalho %.2f x %.2f m" % consumo["maior_retalho_m"]
    if consumo["pecas_divididas"]:
        texto += (f"; {consumo['pecas_divididas']} peça(s) maior(es) que o material entraram "
                  f"divididas, emenda não contada")
    return texto
