"""
Montagem de artes numa folha só, pra aproveitar a largura do rolo.

O QUE ELE PEDIU (04/10/2026)
    "se a lona tem 500cm largura preciso jogar diversos arquivos dentro,
    preciso que redimensione esses arquivos para ter o melhor
    aproveitamento... se eu jogar 10 arquivos que tenha 10 nomes
    diferentes precisa ir um do lado de cada arte"
e, fechando a regra:
    "ESSAS PASTAS DEVEM FAZER A LEITURA PELO NOME, VER O TAMANHO DO
    ARQUIVO E REDIMENSIONAR PARA A MEDIDA QUE PEDE NO NOME CONFORME A
    REGRA ANTES DE MONTAR... o nome do arquivo de saída precisa ser
    coletado dos arquivos inseridos, nome do cliente deve conter no nome"

DUAS PASTAS, UMA POR MÁQUINA DE ROLO
Ele larga arquivo em `MONTAGEM ARTES DOCAN 5200` ou `MONTAGEM ARTES SWJ
3200` e a pasta resolve sozinha. A pasta diz a LARGURA, que é o teto do
encaixe — 5,00 m e 3,20 m, lidas de MAQUINAS, nunca escritas aqui.

O NOME MANDA NO TAMANHO (é a inversão que ele pediu)
No recebimento vale a medida da ARTE (regra de 21/09). Aqui é o
contrário, e de propósito: o arquivo já foi recebido, conferido e
nomeado, então o nome é a medida combinada com o cliente. Arte que
chega fora dessa medida está errada, e a montagem conserta —
`ajuste_para` escala pro tamanho do nome.

MAS NÃO DISTORCE, NUNCA. Quando a PROPORÇÃO não bate, não existe escala
que conserte: ou a arte está errada, ou o nome está. A peça fica de fora
com o motivo escrito, e ele decide. Distorcer calado entregaria peça
deformada que só se descobre impressa.

UMA FOLHA POR MATERIAL
Lona e adesivo não dividem bobina. O agrupamento é por material (a
mesma regra do m² subtotalizado), e cada material vira uma folha.

A CANALETA É ESPAÇO RESERVADO, NÃO SOBRA
Os 5 cm de dados embaixo de cada peça entram no encaixe somados à altura
da peça. No primeiro desenho (04/10) o rótulo foi escrito num vão de
1 cm e invadiu a peça de baixo.
"""
import datetime
import json
import pathlib
import re

import caminhos
from config import carregar_config
from dimensoes import extrair_dimensoes, extrair_quantidade, identificar_categoria
import aproveitamento
from rasterlink_hotfolder import MAQUINAS, _config_maquina

PT_M = 72 / 0.0254   # pontos por metro: a unidade do PDF é o ponto

# --- as pastas, UMA POR MÁQUINA, igual à fila -----------------------
#
# Desenho dele (04/10/2026): *"precisa ter separação das máquinas igual a
# pasta FILA PARA IMPRESSÃO MAQUINAS"*. Então é uma pasta-mãe com uma
# subpasta por máquina, e o nome da subpasta é o NOME DA MÁQUINA — o
# mesmo da fila, o mesmo do cadastro, o mesmo que aparece no relatório.
# Nome igual em todo lugar é o que deixa ligar arquivo a máquina sem
# tabela de conversão.
#
# As medidas NÃO entram no nome da pasta: elas vêm de MAQUINAS. Nome de
# pasta com medida dentro vira mentira no dia em que a medida muda — e
# mudou duas vezes só nesta semana (a DOCAN de 5,00 pra 5,20 e a UJV de
# 1,48 pra 1,27).
PASTA_RAIZ = caminhos.ONEDRIVE_UNY / "MONTAGEM ARTES MAQUINAS"
NOME_SUBPASTA_ORIGINAIS = "_originais"
NOME_SUBPASTA_PROBLEMAS = "_conferir"

# --- as medidas do desenho, que ele deu ----------------------------
#
# Os 5 cm entre peças fazem as duas coisas: é por onde passa a lâmina do
# refile e é onde mora o nome. Antes eram 1 cm de folga MAIS 5 cm de
# canaleta reservada à parte — juntar as duas gasta menos bobina, não
# mais ("entre um arquivo e outro vamos usar espaço de 5cm, ali já
# podemos fazer anotação com nome do arquivo", 04/10/2026).
FOLGA_M = 0.05            # entre peças: passa a lâmina E leva o nome
MARGEM_M = 0.02           # a borda LATERAL da folha, que ninguém usa
ROTULO_LARGURA_M = 0.20   # largura MÍNIMA reservada pro nome
# O tamanho da letra do rótulo, em milímetros. Era "o maior que couber",
# e numa peça larga isso dava 20 mm — letra de 2 cm de altura, que ele
# recusou em 04/10/2026: *"não quero os nomes grandes"*. 10 mm lê de pé,
# com a peça no chão, sem roubar a atenção da arte.
ROTULO_LETRA_MM = 10
CABECALHO_M = 0.08        # faixa própria no topo: escrever sobre a arte estraga a peça
MARCA_CORTE_M = 0.02      # o braço da cruz de corte

# A linha de corte passa no MEIO da folga (pedido dele, 04/10/2026), ou
# seja a 2,5 cm da arte. Cada peça fica com 2,5 cm de branco de cada
# lado depois do refile.
#
# Isso decide onde o nome pode ficar: ABAIXO da linha de corte, nos
# 2,5 cm que ficam com ESTA peça. Escrito acima dela, o nome sairia
# junto com a peça de cima, e cada pedaço ficaria com o nome do vizinho.
RECUO_CORTE_M = FOLGA_M / 2

# Quanto a medida do arquivo pode diferir da do nome e ainda ser "a
# mesma": 5 mm. Abaixo disso é arredondamento de quem exportou.
TOLERANCIA_MEDIDA_M = 0.005
# QUANDO A PROPORÇÃO DO ARQUIVO DIFERE DA DO NOME, quem decide é quanto
# de arte seria APARADO — em milímetros, não em porcentagem.
#
# A arte nunca é esticada: ela entra com escala uniforme e COBRE a caixa,
# e o que passa sai no refile. Então a pergunta certa não é "a proporção
# bate?", é "o que sobra cabe na folga de corte?".
#
# Isso veio de arte real (04/10/2026). Oito lonas da LOJINHA tinham TODAS
# as medidas exatamente +0,7 mm acima do nome — offset constante da
# exportação, não erro de proporção. Em porcentagem a peça mais estreita
# dava 1,5% de desvio e era recusada; em milímetros, a sobra era de 3 mm
# por lado, dentro dos 25 mm de folga. A régua errada recusava arte boa.
SOBRA_MAXIMA_M = 0.025
# E uma trava de bom senso por cima, pra peça pequena: 5% de desvio ainda
# é a mesma arte exportada torta; mais que isso é OUTRA arte, e aí o
# problema é o nome ou o arquivo, não o encaixe.
TOLERANCIA_PROPORCAO = 0.05

IMAGENS = (".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp")


def _pymupdf():
    """Tardio: montar é conforto, e quem não tem a biblioteca não pode quebrar por isso."""
    import pymupdf

    return pymupdf


# --- a pasta --------------------------------------------------------


def pasta_da_maquina(nome_maquina, raiz=None):
    """A pasta de montagem desta máquina: <raiz>/<nome da máquina>."""
    return pathlib.Path(raiz or PASTA_RAIZ) / nome_maquina


def maquina_da_pasta(pasta, maquinas=None):
    """
    A máquina a que uma pasta de montagem pertence, pelo nome dela.

    Comparação sem diferenciar maiúscula: o Windows não diferencia, e
    quem renomeia a pasta na mão sempre erra uma letra.
    """
    nome = pathlib.PurePath(pasta).name.strip().upper()
    for maquina in (MAQUINAS if maquinas is None else maquinas):
        if maquina.upper() == nome:
            return maquina
    return None


def maquinas_que_montam(maquinas=None):
    """
    As máquinas que têm pasta de montagem: as marcadas com 'montagem' no
    cadastro.

    São duas, por decisão dele (04/10/2026): *"deixar apenas a DOCAN 5200
    e a SWJ 320A, o restante nós fazemos manualmente"*. O campo é o
    interruptor — máquina sem ele não ganha pasta, e máquina nova não
    passa a montar sozinha sem alguém decidir.

    O código da PLANA continua aqui e testado (ver encaixar_na_mesa): a
    H2525 monta em chapas no dia em que ele quiser, e aí é só o campo.
    """
    maquinas = MAQUINAS if maquinas is None else maquinas
    return [nome for nome, config in maquinas.items()
            if isinstance(config, dict) and config.get("montagem")
            and (config.get("largura_util_m") or config.get("mesa_util_m"))]


def garantir_pastas(raiz=None, maquinas=None):
    """Cria uma pasta por máquina e devolve {máquina: pasta}."""
    criadas = {}
    for nome_maquina in maquinas_que_montam(maquinas):
        pasta = pasta_da_maquina(nome_maquina, raiz)
        pasta.mkdir(parents=True, exist_ok=True)
        criadas[nome_maquina] = pasta
    return criadas


def _config(nome_maquina, maquinas=None):
    config = (MAQUINAS if maquinas is None else maquinas).get(nome_maquina)
    return config if isinstance(config, dict) else {}


def largura_util(nome_maquina, maquinas=None):
    """A largura útil da máquina, em metros — de MAQUINAS, nunca escrita aqui."""
    maquinas = MAQUINAS if maquinas is None else maquinas
    config = maquinas.get(nome_maquina)
    if config is None:
        return None
    return _config_maquina(config)[1]


def mesa(nome_maquina, maquinas=None):
    """(largura, altura) da mesa, ou None quando a máquina é de rolo."""
    medida = _config(nome_maquina, maquinas).get("mesa_util_m")
    return tuple(medida) if medida else None


def margem(nome_maquina, maquinas=None):
    """
    A borda de branco que esta máquina pede, em metros.

    Vem do cadastro porque ele deu uma por máquina (04/10/2026): 2 cm nas
    DOCAN, 3 cm na UJV, 5 cm na SWJ. Sem cadastro, MARGEM_M.
    """
    return _config(nome_maquina, maquinas).get("margem_montagem_m", MARGEM_M)


# --- ler o nome e o arquivo ----------------------------------------


def medida_do_nome(nome, config=None):
    """
    (largura_m, altura_m) que o NOME pede, ou None.

    É a PRIMEIRA medida do nome, sempre — com duas, a primeira é a do
    cliente e a segunda é acréscimo da produção (regra fixada do
    projeto), e desde 02/10/2026 a primeira é a COM sangria, que é
    justamente a que se imprime.
    """
    config = config or carregar_config()
    dimensao = extrair_dimensoes(nome, config.get("typos_unidade"))
    if not dimensao or not dimensao.get("largura_m") or not dimensao.get("altura_m"):
        return None
    return dimensao["largura_m"], dimensao["altura_m"]


def medida_do_arquivo(caminho):
    """
    (largura_m, altura_m, páginas) do arquivo, ou None quando não dá pra
    abrir. Em imagem a medida física vem dos pixels e do DPI declarado;
    sem DPI, o padrão de 96 é chute — por isso imagem sem DPI nunca
    manda na medida, só o nome.
    """
    caminho = pathlib.Path(caminho)
    pymupdf = _pymupdf()
    try:
        if caminho.suffix.lower() in IMAGENS:
            with pymupdf.open(str(caminho)) as doc:
                pagina = doc.load_page(0)
                return (pagina.rect.width / PT_M, pagina.rect.height / PT_M, 1)
        with pymupdf.open(str(caminho)) as doc:
            if not doc.page_count:
                return None
            pagina = doc.load_page(0)
            return (pagina.rect.width / PT_M, pagina.rect.height / PT_M, doc.page_count)
    except Exception:
        return None


def _perto(a, b, tolerancia):
    return abs(a - b) <= tolerancia


def ajuste_para(alvo, atual):
    """
    O que fazer com a arte pra ela virar a medida do nome:
    {'acao', 'girar', 'fator', 'motivo'}.

      igual     já está na medida (dentro de 5 mm)
      girar     está certa, só deitada
      escalar   a proporção bate: multiplica (é a arte em escala, ou
                exportada fora de medida)
      recusar   a proporção NÃO bate — não existe escala que conserte,
                e distorcer entregaria peça deformada

    'fator' é quanto a arte cresce (10.0 numa arte em 1:10). Sai escrito
    na folha e no registro: número deduzido nunca se passa por declarado.
    """
    largura_alvo, altura_alvo = alvo
    largura, altura = atual[0], atual[1]
    if largura <= 0 or altura <= 0:
        return {"acao": "recusar", "girar": False, "fator": None,
                "motivo": "não consegui medir o arquivo"}

    for girar, (w, h) in ((False, (largura, altura)), (True, (altura, largura))):
        if _perto(w, largura_alvo, TOLERANCIA_MEDIDA_M) and _perto(h, altura_alvo, TOLERANCIA_MEDIDA_M):
            return {"acao": "girar" if girar else "igual", "girar": girar,
                    "fator": 1.0, "motivo": ""}

    # A arte entra com escala UNIFORME e cobrindo a caixa, então a
    # pergunta não é "a proporção bate?" e sim "o que sobra cabe na folga
    # de corte?". Fica com a orientação que apara menos.
    melhor = None
    for girar, (w, h) in ((False, (largura, altura)), (True, (altura, largura))):
        fator_w, fator_h = largura_alvo / w, altura_alvo / h
        fator = max(fator_w, fator_h)
        sobra = max(w * fator - largura_alvo, h * fator - altura_alvo) / 2
        desvio = abs(fator_w / fator_h - 1)
        if melhor is None or sobra < melhor[0]:
            melhor = (sobra, desvio, girar, fator)

    sobra, desvio, girar, fator = melhor
    if sobra <= SOBRA_MAXIMA_M and desvio <= TOLERANCIA_PROPORCAO:
        # arredondado: 9,999999805 é 10x, e número feio num documento de
        # produção faz quem lê duvidar do resto
        return {"acao": "escalar", "girar": girar, "fator": round(fator, 3),
                "motivo": f"arquivo {largura:.3f} x {altura:.3f} m ajustado {fator:.2f}x pro "
                          f"tamanho do nome ({sobra * 1000:.0f} mm aparados por lado)"}

    return {"acao": "recusar", "girar": False, "fator": None,
            "motivo": f"o arquivo tem {largura:.2f} x {altura:.2f} m e o nome pede "
                      f"{largura_alvo:.2f} x {altura_alvo:.2f} m — pondo no tamanho do nome sem "
                      f"deformar, sobrariam {sobra * 1000:.0f} mm por lado (o limite é "
                      f"{SOBRA_MAXIMA_M * 1000:.0f} mm, a folga de corte). Confira a arte ou o nome"}


# --- juntar tudo o que a pasta tem ---------------------------------


def pecas_da_pasta(pasta, config=None, maquinas=None):
    """
    Lê a pasta e devolve (peças, recusadas).

    Peça: {'arquivo', 'nome', 'pagina', 'largura_m', 'altura_m',
           'quantidade', 'categoria', 'ajuste'}
    Recusada: {'arquivo', 'motivo'}

    PDF de várias páginas vira uma peça por página — a máquina imprime só
    a primeira, e um quadrado escondido na página 2 já custou material
    (regra do recebimento).
    """
    config = config or carregar_config()
    materiais = config["materiais"]
    sinonimos = config.get("sinonimos_categoria")
    pecas, recusadas = [], []

    for arquivo in sorted(pathlib.Path(pasta).iterdir()):
        if not arquivo.is_file() or arquivo.name.startswith("~"):
            continue
        if arquivo.suffix.lower() not in (".pdf",) + IMAGENS:
            continue

        alvo = medida_do_nome(arquivo.name, config)
        if alvo is None:
            recusadas.append({"arquivo": arquivo,
                              "motivo": "o nome não traz medida, e aqui é o nome que manda"})
            continue
        atual = medida_do_arquivo(arquivo)
        if atual is None:
            recusadas.append({"arquivo": arquivo, "motivo": "não consegui abrir pra medir"})
            continue

        ajuste = ajuste_para(alvo, atual)
        if ajuste["acao"] == "recusar":
            recusadas.append({"arquivo": arquivo, "motivo": ajuste["motivo"]})
            continue

        quantidade = extrair_quantidade(arquivo.name)[0] or 1
        categoria = identificar_categoria(arquivo.name.upper(), materiais, sinonimos)[0]
        if not categoria:
            recusadas.append({"arquivo": arquivo,
                              "motivo": "não reconheci o material no nome — ele escolhe a bobina"})
            continue

        for pagina in range(atual[2]):
            for copia in range(int(quantidade)):
                pecas.append({
                    "arquivo": arquivo, "nome": arquivo.name, "pagina": pagina,
                    "largura_m": alvo[0], "altura_m": alvo[1],
                    # a medida do ARQUIVO, não a do nome: é dela que sai a
                    # PROPORÇÃO na hora de desenhar. Sem guardá-la, quem
                    # desenha só tem a medida do nome e não tem como
                    # manter a proporção da arte (defeito de 04/10/2026)
                    "arquivo_m": (atual[0], atual[1]),
                    "quantidade": int(quantidade), "copia": copia + 1,
                    "categoria": categoria, "ajuste": ajuste,
                })
    return pecas, recusadas


def cliente_das_pecas(pecas, raiz=None):
    """
    O cliente que aparece nos nomes, ou "" quando nenhum cadastrado
    aparece. A arte da produção leva "<especificação>_<CLIENTE>_<descrição>"
    (regra de 2026-09-30), então o cliente está escrito no nome — e é por
    isso que ele pediu o cliente no nome de saída.
    """
    import clientes

    try:
        cadastrados = clientes.listar(raiz)
    except OSError:
        # só falta de pasta é esperada aqui. Um 'except Exception' aqui
        # escondeu um 'c["nome"]' num objeto Cliente por uma rodada
        # inteira, e o cliente sumia do nome de saída calado (04/10/2026).
        return ""

    juntos = " ".join(p["nome"] for p in pecas).upper()
    achados = []
    for cliente in cadastrados:
        for candidato in (cliente.nome_documento, cliente.nome):
            if candidato and candidato.upper() in juntos:
                achados.append(cliente.nome)
                break
        else:
            # o nome na arte costuma ser a primeira palavra do cadastro
            # ("VIBRA" pra "VIBRA LOJA CONVENIÊNCIA"), porque é isso que
            # a agência escreve no arquivo
            primeira = cliente.nome.split()[0] if cliente.nome.split() else ""
            if len(primeira) >= 4 and re.search(rf"\b{re.escape(primeira.upper())}\b", juntos):
                achados.append(cliente.nome)
    # o mais específico ganha: "VIBRA LOJA CONVENIÊNCIA" antes de "VIBRA"
    return max(achados, key=len) if achados else ""


def nome_da_folha(cliente, categoria, largura_m, comprimento_m, quantas,
                  quando=None, chapas=None):
    """
    O nome do arquivo de saída, no MESMO padrão que o resto do sistema lê.

    Começa com a especificação (1UN + material + medida) porque é dali
    que a etiqueta, a OS, o relatório e a escolha de máquina leem — uma
    folha montada é UMA peça de material, de 5,00 x 9,86 m. O cliente
    entra em seguida, como ele pediu, e a descrição diz que é montagem e
    de quantas peças.
    """
    quando = quando or datetime.datetime.now()
    partes = [f"1UN {categoria} {largura_m:.2f}X{comprimento_m:.2f}M"]
    if cliente:
        partes.append(re.sub(r"[^\w .-]", "", cliente).strip().replace(" ", "_"))
    miolo = f"MONTAGEM_{quantas}pecas"
    if chapas:
        miolo += f"_{chapas}chapas"
    partes.append(f"{miolo}_{quando:%d-%m-%Y_%H-%M}")
    return "_".join(partes) + ".pdf"


# --- encaixar e desenhar -------------------------------------------


def encaixar(pecas, largura_util_m, margem_m=None):
    """
    Onde cada peça fica na folha: (postas, comprimento_m).

    Posta: (índice da peça, x_m, y_m, largura_m, altura_m, girada) — já
    descontada a folga e a canaleta, ou seja, é o retângulo da ARTE.

    A folga e a canaleta entram INFLANDO a peça antes do encaixe: elas
    são espaço reservado, não sobra. Sem isso o rótulo de 5 cm cai dentro
    da peça de baixo (visto no desenho de 04/10/2026).
    """
    # A peça reserva a folga nos DOIS lados, e não só embaixo. É isso que
    # faz o rótulo continuar no lugar certo quando o encaixe gira a peça:
    # com (largura+folga) x (altura+folga), girado vira
    # (altura+folga) x (largura+folga) — sobra folga nos dois sentidos de
    # qualquer jeito, então a arte vai sempre no canto de BAIXO e a faixa
    # do nome sempre no topo. Reservar só embaixo punha o rótulo dentro da
    # peça vizinha quando ela girava (visto em 04/10/2026).
    #
    # Na largura ainda vale o piso do RÓTULO: peça estreita (o rodapé de
    # 0,30 m) teria rótulo maior que ela. O teto é a bobina — uma peça de
    # 5,00 m numa bobina de 5,00 não pode ser inflada, senão deixa de
    # caber deitada e o encaixe a obriga a girar à toa.
    rotulo = ROTULO_LARGURA_M
    margem_m = MARGEM_M if margem_m is None else margem_m
    util = largura_util_m - 2 * margem_m
    inflar = []
    for i, peca in enumerate(pecas):
        largura = max(peca["largura_m"] + FOLGA_M, rotulo)
        # O teto é a largura útil, MAS NUNCA ABAIXO DA PRÓPRIA PEÇA. Com
        # o teto cru, uma lona de 7,14 m virava um retângulo reservado de
        # 4,96 e o encaixe "cabia" com ela deitada — a arte saía 2,18 m
        # pra fora da folha, calada (visto em 04/10/2026). O teto existe
        # só pra peça que cabe e cuja FOLGA é que não caberia.
        largura = min(largura, max(util, peca["largura_m"]))
        inflar.append((largura, peca["altura_m"] + FOLGA_M, i))
    postas, comprimento = aproveitamento.posicoes_no_rolo(inflar, util)

    arte = []
    for indice, x, y, largura, altura, girada in postas:
        peca = pecas[indice]
        largura_arte = peca["altura_m"] if girada else peca["largura_m"]
        altura_arte = peca["largura_m"] if girada else peca["altura_m"]
        # 'largura'/'altura' são o RETÂNGULO RESERVADO como ele foi posto.
        # Quem desenha precisa dos dois: a arte encosta no canto de baixo
        # e o que sobra em cima é a faixa do nome.
        arte.append((indice, x, y, largura_arte, altura_arte, girada, largura, altura))
    return arte, comprimento


def _escrever_rotulo(pagina, x0_pt, base_pt, largura_m, texto, pymupdf,
                     altura_max_m=None):
    """
    O rótulo numa LINHA só, encostado por BAIXO em 'base_pt' (o topo da
    arte). Devolve (milímetros, o que ficou escrito).

    Encostar por baixo, e não por cima da faixa, é o que deixa o nome
    junto da peça — ele pediu *"pode ser mais encostado na peça um
    pouco"* (04/10/2026). A caixa é recalculada a cada tamanho de letra
    justamente pra isso: o texto desce junto quando encolhe.

    Encolher vem ANTES de cortar. O nome tem que sair EXATO, igual ao do
    arquivo (regra dele no mesmo dia) — cortar é último recurso, e só
    quando nem a menor letra couber.

    O insert_textbox NÃO avisa quando desiste: devolve negativo e não
    desenha nada. O número da peça sumiu assim duas vezes, e as duas só
    apareceram ampliando a prévia; por isso aqui ele ESTOURA em vez de
    deixar a peça sem identificação.
    """
    # começa no tamanho PEDIDO e só desce: o rótulo não cresce porque a
    # peça é larga. "Não quero os nomes grandes" (ele, 04/10/2026).
    tamanhos = tuple(mm for mm in (20, 18, 16, 15, 14, 13, 12, 11, 10, 9, 8, 7, 6, 5)
                     if mm <= ROTULO_LETRA_MM) or (5,)

    def tentar(milimetros, conteudo):
        # 1,8x a letra, medido: o insert_textbox precisa da linha MAIS o
        # espaço do acento e do rabo, e com 1,4x ele recusava tudo — e
        # recusa devolvendo negativo, sem desenhar nada.
        #
        # E o teto é a meia-folga: o rótulo tem que caber nos 2,5 cm que
        # ficam com ESTA peça. Passando disso, metade do nome sairia
        # junto com a peça de cima no refile.
        teto = RECUO_CORTE_M if altura_max_m is None else altura_max_m
        alto = min(milimetros * 1.8 / 1000, teto) * PT_M
        caixa = pymupdf.Rect(x0_pt, base_pt - alto, x0_pt + largura_m * PT_M, base_pt)
        return pagina.insert_textbox(caixa, conteudo, fontsize=milimetros / 1000 * PT_M,
                                     fontname="hebo", color=(0, 0, 0))

    for milimetros in tamanhos:
        if tentar(milimetros, texto) >= 0:
            return milimetros, texto
    # nem na menor letra: aí corta, porque nome cortado ainda identifica
    # a peça e rótulo que some, não
    for corte in (60, 48, 40, 32, 24, 16, 10):
        curto = texto[:corte - 1] + "~"
        if tentar(tamanhos[-1], curto) >= 0:
            return tamanhos[-1], curto
    raise AssertionError(f"o rótulo {texto!r} não coube em {largura_m * 100:.0f} cm")


def descricao_e_especificacao(nome):
    """
    Parte o nome em (descrição, especificação): o que identifica a peça e
    o que diz quantidade/material/medida.

    O nome é "<especificação>_<CLIENTE>_<descrição>", então a descrição
    vem DEPOIS da medida. Cortar o nome pelo fim — que foi o primeiro
    desenho — deixava "1UN DECORFLEX 4.30X0.80M_~" e jogava fora o
    "SPFW26_PASSARELA_PISO", que é o que diz qual peça é.
    """
    base = pathlib.PurePath(nome).stem
    # (?![A-Za-z]) e não \b: depois do "M" vem "_", que conta como letra,
    # então \b não casa e a divisão falhava em todos os nomes.
    achado = re.search(r"\d+[.,]\d+\s*[Xx]\s*\d+[.,]\d+\s*(?:MM|CM|M)(?![A-Za-z])", base, re.I)
    if not achado:
        return base, ""
    descricao = base[achado.end():].strip(" _-")
    return (descricao or base), base[:achado.start()].strip(" _-")


def posicao_na_folha(posta, margem_m=None, deslocamento_m=None):
    """
    (x_m, y_m) do canto superior esquerdo da ARTE na folha — não do
    retângulo reservado.

    Os dois diferem: a arte encosta embaixo da reserva (pra sobrar a
    faixa do nome em cima) e a folha ainda tem o cabeçalho e a margem.
    O JSON guarda ESTA posição, não a do encaixe: ele é a planta de
    quem vai procurar a peça 07 na lona de 9 m, e um metro de diferença
    manda a pessoa procurar no lugar errado.
    """
    _indice, x, y, _largura, altura, _girada, _reservada_l, reservada_a = posta
    margem_m = MARGEM_M if margem_m is None else margem_m
    # nas chapas o deslocamento e ZERO: a pagina e a chapa e nao
    # ha faixa de cabecalho nenhuma em cima
    deslocamento_m = CABECALHO_M if deslocamento_m is None else deslocamento_m
    return x + margem_m, y + deslocamento_m + margem_m + (reservada_a - altura)


def _caixa_que_a_arte_cobre(caixa, largura_arte, altura_arte, pymupdf):
    """
    O retângulo a passar pro PyMuPDF pra arte COBRIR a caixa sem ser
    esticada, centrada nela.

    A escala é uniforme — um fator só pros dois lados —, então a arte
    nunca deforma: "as artes não podem ser mexidas em absolutamente nada"
    (regra dele, 04/10/2026). Quando a proporção do arquivo difere um
    tiquinho da do nome (até TOLERANCIA_PROPORCAO), o que sobra passa das
    marcas de corte e sai no refile, que é o destino dele de qualquer
    jeito. Encaixar POR DENTRO deixaria uma tira branca na peça.
    """
    if largura_arte <= 0 or altura_arte <= 0:
        return caixa
    fator = max(caixa.width / largura_arte, caixa.height / altura_arte)
    largura, altura = largura_arte * fator, altura_arte * fator
    meio_x, meio_y = (caixa.x0 + caixa.x1) / 2, (caixa.y0 + caixa.y1) / 2
    return pymupdf.Rect(meio_x - largura / 2, meio_y - altura / 2,
                        meio_x + largura / 2, meio_y + altura / 2)


def encaixar_na_mesa(pecas, mesa_m, margem_m=None):
    """
    Onde cada peça fica, chapa por chapa, numa máquina PLANA.

    Devolve ([[posta, ...], ...], quantas_chapas) — uma lista por chapa,
    com a mesma posta do rolo.

    A diferença pro rolo é que aqui os DOIS lados são teto: não existe
    "a bobina anda". O que a montagem economiza é número de chapas, e
    chapa é material que sai inteiro do estoque.
    """
    margem_m = MARGEM_M if margem_m is None else margem_m
    largura_m, altura_m = mesa_m
    util_l = largura_m - 2 * margem_m
    util_a = altura_m - 2 * margem_m

    rotulo = ROTULO_LARGURA_M
    inflar = []
    for i, peca in enumerate(pecas):
        largura = max(peca["largura_m"] + FOLGA_M, rotulo)
        largura = min(largura, max(util_l, peca["largura_m"]))
        inflar.append((largura, peca["altura_m"] + FOLGA_M, i))
    chapas = aproveitamento.posicoes_em_chapas(inflar, util_l, util_a)

    saida = []
    for postas in chapas:
        arte = []
        for indice, x, y, largura, altura, girada in postas:
            peca = pecas[indice]
            largura_arte = peca["altura_m"] if girada else peca["largura_m"]
            altura_arte = peca["largura_m"] if girada else peca["altura_m"]
            arte.append((indice, x, y, largura_arte, altura_arte, girada, largura, altura))
        saida.append(arte)
    return saida


def desenhar(pecas, postas, comprimento_m, largura_util_m, titulo, margem_m=None):
    """
    A folha pronta: cada arte no tamanho do NOME, o nome no canto
    superior esquerdo dela.

    A arte encosta no canto de BAIXO do espaço reservado, então a folga
    de 5 cm sobra em cima — e é ali, alinhado à esquerda da peça, que vai
    o nome. É a convenção do RasterLink, que ele pediu pra seguir: o
    material vai ser refilado e cada pedaço precisa sair com o nome dele.
    """
    pymupdf = _pymupdf()
    doc = pymupdf.open()
    # o CABECALHO em cima, e embaixo a folga inteira: a arte da ultima
    # fileira encosta no fim do encaixe e a marca de corte dela fica
    # 2,5 cm abaixo disso
    pagina = doc.new_page(
        width=largura_util_m * PT_M,
        height=(comprimento_m + CABECALHO_M + margem_m + FOLGA_M) * PT_M)
    pagina.draw_rect(pagina.rect, color=None, fill=(1, 1, 1))

    for numero, posta in enumerate(postas, start=1):
        _desenhar_peca(pagina, pecas, posta, numero, margem_m, largura_util_m,
                       CABECALHO_M, pymupdf)

    pagina.insert_textbox(
        pymupdf.Rect(0.02 * PT_M, 0.018 * PT_M, (largura_util_m - 0.02) * PT_M,
                     CABECALHO_M * PT_M),
        titulo, fontsize=0.030 * PT_M, fontname="hebo", color=(0.35, 0.35, 0.35))
    return doc


def _desenhar_peca(pagina, pecas, posta, numero, margem_m, largura_pagina_m,
                   deslocamento_m, pymupdf):
    """
    Uma peça na página: a arte, as marcas de corte e o nome.

    É a mesma coisa pro rolo e pra mesa — o que muda entre os dois é só a
    página e o deslocamento do topo. O rolo tem cabeçalho; a chapa não
    tem, porque a página É a chapa e a faixa roubaria área dela.
    """
    indice, x, y, largura, altura, girada, reservada_l, reservada_a = posta
    peca = pecas[indice]
    if True:
        # a arte encosta embaixo do retângulo reservado: o que sobra em
        # cima é a faixa do nome, e ela existe igual com a peça girada
        px = x + margem_m
        py = y + deslocamento_m + margem_m + (reservada_a - altura)
        esquerda, topo = px * PT_M, py * PT_M
        caixa = pymupdf.Rect(esquerda, topo, esquerda + largura * PT_M, topo + altura * PT_M)
        girar = 90 if girada != peca["ajuste"]["girar"] else 0

        # A ARTE ENTRA NO TAMANHO DO NOME, e só. Nada é reescrito no
        # arquivo de origem: o PDF entra por referência e a imagem é
        # embutida como está.
        arquivo = peca["arquivo"]
        # A PROPORÇÃO é a do ARQUIVO, nunca a da caixa. Passar a medida do
        # nome aqui (que foi o que eu fiz primeiro) torna a conta um
        # no-op: ela devolve a própria caixa, e a arte com proporção um
        # tiquinho diferente entra encaixada POR DENTRO, deixando tira
        # branca na peça. Girada, a proporção inverte junto.
        arquivo_l, arquivo_a = peca["arquivo_m"]
        if girar:
            arquivo_l, arquivo_a = arquivo_a, arquivo_l
        onde = _caixa_que_a_arte_cobre(caixa, arquivo_l, arquivo_a, pymupdf)
        if arquivo.suffix.lower() in IMAGENS:
            pagina.insert_image(onde, filename=str(arquivo), rotate=girar,
                                keep_proportion=True)
        else:
            with pymupdf.open(str(arquivo)) as origem:
                pagina.show_pdf_page(onde, origem, peca["pagina"], rotate=girar,
                                     keep_proportion=True)

        # SEM MARCA DE CORTE: ele tirou em 04/10/2026, olhando a primeira
        # folha com elas. A folga de 5 cm entre as peças já diz onde a
        # lâmina passa, e as cruzinhas só sujavam a sobra.

        # O NOME NO CANTO SUPERIOR ESQUERDO DA ARTE, numa linha só,
        # encostado nela. É o NOME DO ARQUIVO, EXATO (regra dele,
        # 04/10/2026): antes eu escrevia só o fim do nome e isso mostrava
        # a SEGUNDA medida ao lado de uma peça feita na PRIMEIRA — o
        # rótulo dizia "1,50x0,25m" numa peça de 1,80 x 0,55, e parecia
        # que o tamanho estava errado quando não estava.
        #
        # A largura é a da própria peça (o espaço reservado dela), não os
        # 20 cm fixos: nome exato é longo, e em peça larga ele cabe
        # inteiro com letra grande em vez de sair cortado.
        largura_rotulo = min(reservada_l, largura_pagina_m - 2 * margem_m)
        nome = pathlib.PurePath(peca["nome"]).stem
        if peca["quantidade"] > 1:
            nome = f"{nome} ({peca['copia']}/{peca['quantidade']})"
        # a folguinha de 1 mm entre o texto e a arte entra no teto: o
        # rótulo inteiro tem que caber na meia-folga, senão o pedaço de
        # cima sai com a peça vizinha no refile
        _escrever_rotulo(pagina, caixa.x0, caixa.y0 - 0.001 * PT_M, largura_rotulo,
                         f"{numero:02d}  {nome}", pymupdf, RECUO_CORTE_M - 0.001)


def desenhar_chapas(pecas, chapas, mesa_m, titulo, margem_m=None):
    """
    A montagem de uma máquina PLANA: uma página por chapa, do tamanho
    exato da chapa.

    Sem faixa de cabeçalho: a página É a chapa, e uma faixa em cima
    roubaria área dela. O que o cabeçalho diria vai pro rodapé da última
    linha de peças? Não — vai pro nome do arquivo e pro JSON, que é onde
    não atrapalha material.
    """
    margem_m = MARGEM_M if margem_m is None else margem_m
    pymupdf = _pymupdf()
    doc = pymupdf.open()
    largura_m, altura_m = mesa_m
    numero = 0
    for postas in chapas:
        pagina = doc.new_page(width=largura_m * PT_M, height=altura_m * PT_M)
        pagina.draw_rect(pagina.rect, color=None, fill=(1, 1, 1))
        for posta in postas:
            numero += 1
            _desenhar_peca(pagina, pecas, posta, numero, margem_m, largura_m, 0.0, pymupdf)
    return doc


# --- a montagem da pasta inteira -----------------------------------


def _mover_para(arquivo, destino):
    """Move sem sobrescrever: homônimo ganha sufixo em vez de apagar o anterior."""
    destino.mkdir(parents=True, exist_ok=True)
    alvo = destino / arquivo.name
    if alvo.exists():
        alvo = destino / f"{arquivo.stem}_{int(datetime.datetime.now().timestamp())}{arquivo.suffix}"
    arquivo.rename(alvo)
    return alvo


def montar_pasta(pasta, nome_maquina=None, config=None, maquinas=None, logger=None,
                 guardar_originais=True, quando=None, raiz_clientes=None):
    """
    Monta tudo o que está na pasta e devolve
    {'folhas': [...], 'recusadas': [...], 'maquina', 'largura_util_m'}.

    UMA FOLHA POR MATERIAL: lona e adesivo não dividem bobina, e o m²
    deste projeto nunca mistura material.

    Os originais vão pra `_originais/<carimbo>` depois de montados — se
    ficassem na pasta, a próxima passada montaria tudo de novo. O que foi
    recusado vai pra `_conferir`, com o motivo num .txt ao lado: peça que
    some sem explicação é peça que não vai ser produzida.
    """
    pasta = pathlib.Path(pasta)
    quando = quando or datetime.datetime.now()
    logger = logger or (lambda nivel, mensagem: None)
    nome_maquina = nome_maquina or maquina_da_pasta(pasta)
    largura = largura_util(nome_maquina, maquinas)
    chapa = mesa(nome_maquina, maquinas)
    resultado = {"maquina": nome_maquina, "largura_util_m": largura,
                 "mesa_m": chapa, "margem_m": margem(nome_maquina, maquinas),
                 "folhas": [], "recusadas": []}
    # máquina de MESA não tem largura de rolo, e é o caso da H2525: pedir
    # 'largura' aqui a deixava de fora da montagem inteira, calada
    if not pasta.is_dir() or not (largura or chapa):
        return resultado

    margem_m = margem(nome_maquina, maquinas)
    pecas, recusadas = pecas_da_pasta(pasta, config, maquinas)
    for recusada in recusadas:
        logger("warn", f"'{recusada['arquivo'].name}' ficou de fora: {recusada['motivo']}")
        if guardar_originais:
            alvo = _mover_para(recusada["arquivo"], pasta / NOME_SUBPASTA_PROBLEMAS)
            alvo.with_suffix(alvo.suffix + ".motivo.txt").write_text(
                recusada["motivo"] + "\n", encoding="utf-8")
        resultado["recusadas"].append({"arquivo": recusada["arquivo"].name,
                                       "motivo": recusada["motivo"]})
    if not pecas:
        return resultado

    cliente = cliente_das_pecas(pecas, raiz_clientes)
    por_material = {}
    for peca in pecas:
        por_material.setdefault(peca["categoria"], []).append(peca)

    for categoria, do_material in sorted(por_material.items()):
        if chapa:
            # MÁQUINA PLANA: o encaixe devolve uma lista por chapa, e cada
            # chapa vira uma página do tamanho dela. 'postas' aqui é a
            # soma de todas, só pra contar e pra recusar o que não coube.
            paginas = encaixar_na_mesa(do_material, chapa, margem_m)
            postas = [p for pagina in paginas for p in pagina]
            comprimento = chapa[1]
        else:
            postas, comprimento = encaixar(do_material, largura, margem_m)
            paginas = [postas]

        # Peça que não cabe na bobina de jeito nenhum NÃO pode sumir da
        # folha em silêncio: o encaixe simplesmente a ignora, e aí ela
        # não é produzida e ninguém fica sabendo. Vira recusa, com o
        # motivo escrito, como todas as outras.
        colocadas = {posta[0] for posta in postas}
        for indice, peca in enumerate(do_material):
            if indice in colocadas:
                continue
            teto = f"{chapa[0]:.2f} x {chapa[1]:.2f} m de mesa" if chapa else f"largura útil {largura:.2f} m"
            motivo = (f"{peca['largura_m']:.2f} x {peca['altura_m']:.2f} m não cabe na "
                      f"{nome_maquina} nem girada ({teto}, menos "
                      f"{margem_m * 100:.0f} cm de borda de cada lado)")
            logger("warn", f"'{peca['nome']}' ficou de fora: {motivo}")
            resultado["recusadas"].append({"arquivo": peca["nome"], "motivo": motivo})
        if not postas:
            continue
        area_pecas = sum(p["largura_m"] * p["altura_m"] for p in do_material)
        area_folha = (chapa[0] * chapa[1] * len(paginas)) if chapa else largura * comprimento
        tamanho = (f"{len(paginas)} chapa(s) de {chapa[0]:.2f} x {chapa[1]:.2f} m"
                   if chapa else f"{largura:.2f} x {comprimento:.2f} m")
        titulo = (f"MONTAGEM  ·  {cliente or 'SEM CLIENTE NO NOME'}  ·  {categoria}  ·  "
                  f"{len(postas)} pecas  ·  {tamanho}  ·  "
                  f"aproveitamento {area_pecas / area_folha * 100:.0f}%  ·  "
                  f"RIPAR A 100%, NAO REDIMENSIONAR")
        if chapa:
            doc = desenhar_chapas(do_material, paginas, chapa, titulo, margem_m)
        else:
            doc = desenhar(do_material, postas, comprimento, largura, titulo, margem_m)
        if chapa:
            destino = pasta / nome_da_folha(cliente, categoria, chapa[0], chapa[1],
                                            len(postas), quando, len(paginas))
        else:
            destino = pasta / nome_da_folha(cliente, categoria, largura,
                                            comprimento + CABECALHO_M, len(postas), quando)
        doc.save(str(destino), garbage=4, deflate=True)
        doc.close()

        # O JSON ao lado é o que impede a montagem de APAGAR a comprovação:
        # pro registro de produção a folha é UM arquivo entregue, e sem
        # isto as peças sumiriam do relatório do cliente.
        ficha = {
            "quando": quando.strftime("%Y-%m-%dT%H:%M:%S"),
            "cliente": cliente, "maquina": nome_maquina, "categoria": categoria,
            "folha_m": ([round(chapa[0], 3), round(chapa[1], 3)] if chapa
                        else [round(largura, 3), round(comprimento + CABECALHO_M, 3)]),
            "chapas": len(paginas) if chapa else None,
            "area_folha_m2": round(area_folha, 3), "area_pecas_m2": round(area_pecas, 3),
            "folga_m": FOLGA_M, "margem_m": margem_m,
            "pecas": [{
                "numero": numero, "arquivo": do_material[i]["nome"],
                "pagina": do_material[i]["pagina"],
                "medida_m": [round(do_material[i]["largura_m"], 3),
                             round(do_material[i]["altura_m"], 3)],
                "posicao_m": [round(v, 3) for v in
                              posicao_na_folha(posta, margem_m, 0.0 if chapa else None)],
                "girada": girada,
                "ajuste": do_material[i]["ajuste"]["acao"],
                "fator": do_material[i]["ajuste"]["fator"],
            } for numero, posta in enumerate(postas, start=1)
               for i, girada in ((posta[0], posta[5]),)],
        }
        destino.with_suffix(".json").write_text(
            json.dumps(ficha, ensure_ascii=False, indent=2), encoding="utf-8")

        logger("ok", f"Montagem de {categoria}: {len(postas)} peças em "
                     f"{tamanho} "
                     f"({area_pecas / area_folha * 100:.0f}% de aproveitamento) — {destino.name}")
        resultado["folhas"].append({
            "arquivo": destino, "categoria": categoria, "pecas": len(postas),
            "comprimento_m": comprimento, "chapas": len(paginas) if chapa else None,
            "aproveitamento": area_pecas / area_folha,
            "cliente": cliente,
        })

    if guardar_originais:
        guardados = pasta / NOME_SUBPASTA_ORIGINAIS / f"{quando:%d-%m-%Y_%H-%M-%S}"
        for arquivo in {peca["arquivo"] for peca in pecas}:
            if arquivo.is_file():
                _mover_para(arquivo, guardados)
    return resultado


def montar_todas(raiz=None, config=None, maquinas=None, logger=None, quando=None):
    """Uma passada por todas as pastas de montagem. Devolve [resultado por pasta]."""
    resultados = []
    for nome_maquina in maquinas_que_montam(maquinas):
        pasta = pasta_da_maquina(nome_maquina, raiz)
        if not pasta.is_dir():
            continue
        if not any(a.is_file() and a.suffix.lower() in (".pdf",) + IMAGENS
                   for a in pasta.iterdir()):
            continue
        resultados.append(montar_pasta(pasta, nome_maquina, config, maquinas, logger,
                                       quando=quando))
    return resultados


# --- a pasta se resolvendo sozinha ---------------------------------
#
# "A pasta precisa resolver a montagem para evitar de eu fazer
# manualmente" (04/10/2026). Então a montagem não espera botão: ela
# acontece na passada do Checklist de Produção, a tarefa que já percorre
# tudo de minuto em minuto neste PC.
#
# Mas NÃO na hora que o primeiro arquivo cai. Ele larga dez arquivos
# seguidos, e pelo OneDrive eles chegam um a um: montar no primeiro
# produziria uma folha com uma peça e mandaria as outras nove pra uma
# segunda folha. Por isso a pasta tem que ficar PARADA um tempo antes.
MINUTOS_PARADA = 3


def pasta_parada(pasta, minutos=None, agora=None):
    """
    True quando nada entrou na pasta nos últimos 'minutos' — e há o que
    montar. É o que separa "ele terminou de largar os arquivos" de "ele
    está no meio".
    """
    pasta = pathlib.Path(pasta)
    if not pasta.is_dir():
        return False
    minutos = MINUTOS_PARADA if minutos is None else minutos
    agora = agora or datetime.datetime.now()
    limite = agora - datetime.timedelta(minutes=minutos)

    tem_o_que_montar = False
    for arquivo in pasta.iterdir():
        if not arquivo.is_file() or arquivo.suffix.lower() not in (".pdf",) + IMAGENS:
            continue
        tem_o_que_montar = True
        try:
            if datetime.datetime.fromtimestamp(arquivo.stat().st_mtime) > limite:
                return False   # ainda chegando
        except OSError:
            return False
    return tem_o_que_montar


def conferir(raiz=None, config=None, maquinas=None, logger=None, agora=None, minutos=None):
    """
    Uma passada pelas pastas de montagem: monta as que pararam de
    receber arquivo. Devolve [resultado por pasta montada].

    Nunca levanta por pasta: uma pasta com arte problemática não pode
    impedir a outra de montar.
    """
    logger = logger or (lambda nivel, mensagem: None)
    feitas = []
    for nome_maquina in maquinas_que_montam(maquinas):
        pasta = pasta_da_maquina(nome_maquina, raiz)
        if not pasta_parada(pasta, minutos, agora):
            continue
        try:
            feitas.append(montar_pasta(pasta, nome_maquina, config, maquinas, logger,
                                       quando=agora))
        except Exception as erro:   # noqa: BLE001 - ver docstring
            logger("warn", f"a montagem de '{pasta.name}' parou: "
                           f"{type(erro).__name__}: {erro}")
    return feitas
