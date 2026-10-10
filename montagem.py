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

DUAS PASTAS, UMA POR M�?QUINA DE ROLO
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
import contextlib
import json
import math
import pathlib
import re
import tempfile
import uuid

import caminhos
from config import carregar_config
from dimensoes import extrair_dimensoes, extrair_quantidade, identificar_categoria, contem_palavra
import aproveitamento
import retomada_montagem as retomada
import tempo_impressao
from rasterlink_hotfolder import MAQUINAS, _config_maquina
from seguranca_montagem import PublicacaoMontagem, trava_montagem

PT_M = 72 / 0.0254   # pontos por metro: a unidade do PDF é o ponto

# --- as pastas, UMA POR M�?QUINA, igual à fila -----------------------
#
# Desenho dele (04/10/2026): *"precisa ter separação das máquinas igual a
# pasta FILA PARA IMPRESSÃO MAQUINAS"*. Então é uma pasta-mãe com uma
# subpasta por máquina, e o nome da subpasta é o NOME DA M�?QUINA — o
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
# O rótulo tem 300 mm de largura, SEMPRE (ele, 04/10/2026: *"os nomes
# precisa ficar todos com 300mm de largura"*). É também a largura mínima
# que cada peça reserva no encaixe, pra o rótulo nunca invadir a vizinha.
ROTULO_LARGURA_M = 0.30
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
# dava 1,5% de desvio e era recusada; em milímetros, a diferença era de
# 7 mm no lado. A régua errada recusava arte boa.
#
# O limite é no COMPRIMENTO porque é lá que a diferença cai: a largura é
# âncora e fecha sempre (regra dele, 05/10/2026). E ele é generoso de
# propósito — nada mais é cortado, então o que sobra é material, não
# arte perdida; quem recusa arte trocada é a trava relativa logo abaixo.
DIFERENCA_MAXIMA_M = 0.10
# E uma trava de bom senso por cima, pra peça pequena: 5% de desvio ainda
# é a mesma arte exportada torta; mais que isso é OUTRA arte, e aí o
# problema é o nome ou o arquivo, não o encaixe.
# A franja branca que a exportação deixa em volta da arte é descontada
# (ver caixa_da_arte). Mas só quando é FRANJA: acima desta fração do lado
# é design — um logo no meio de uma folha branca tem caixa de tinta
# pequena, e esticá-la até a medida do nome seria desastre.
FRANJA_MAXIMA_FRACAO = 0.10
TOLERANCIA_PROPORCAO = 0.05

# OS FORMATOS SÃO OS DO SISTEMA, não uma lista própria (ele, 05/10/2026:
# *"as pastas precisa ler também todos os formatos de arquivos que já
# usamos no sistema, pra depois sair em PDF"*). Três caminhos:
#
#   COMO_PDF      abre direto — o .ai salvo com compatibilidade PDF é PDF
#   IMAGENS       vira PDF com o convert_to_pdf do PyMuPDF
#   PRECISA_ADOBE só abre passando pelo Illustrator/Photoshop
#                 (conversao_adobe), e por isso é um passo À PARTE: ele
#                 ESCREVE, e a prévia não pode escrever nada
COMO_PDF = (".pdf", ".ai")
IMAGENS = (".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp")
PRECISA_ADOBE = (".eps", ".psd")
EXTENSOES_DE_ARTE = COMO_PDF + IMAGENS + PRECISA_ADOBE

# Desde 08/10/2026 não há teto de comprimento nem divisão automática.
# A largura da máquina e a integridade das peças continuam sendo respeitadas.
FOLGA_MINIMA_M = 0.01
ROTULO_LETRA_MINIMA_MM = 2.0


def folga_da_montagem(nome_maquina=None, maquinas=None, folga_m=None, config=None):
    """Espaço do lote, do cadastro ou o padrão; nunca modifica globais."""
    if folga_m is None:
        cadastro = _config(nome_maquina, maquinas).get("folga_montagem_m", FOLGA_M)
        if nome_maquina is not None:
            config = carregar_config() if config is None else config
            cadastro = config.get("montagem", {}).get(nome_maquina, {}).get("folga_m", cadastro)
        folga_m = cadastro
    try:
        valor = float(folga_m)
    except (TypeError, ValueError) as erro:
        raise ValueError("O espaço entre artes precisa ser um número em metros.") from erro
    if not math.isfinite(valor) or valor < FOLGA_MINIMA_M:
        raise ValueError("Use pelo menos 1 cm entre artes para preservar a identificação.")
    return valor


def _arquivos_selecionados(pasta, arquivos=None):
    """Lista de entrada filtrada; [] significa nenhuma arte, nunca todas."""
    pasta = pathlib.Path(pasta)
    if not pasta.is_dir():
        return []
    nomes = None
    if arquivos is not None:
        nomes = set()
        for arquivo in arquivos:
            caminho = pathlib.Path(arquivo)
            if caminho.is_absolute() and caminho.parent.resolve() != pasta.resolve():
                raise ValueError(f"A arte {caminho.name!r} não pertence à pasta desta máquina.")
            if not caminho.is_absolute() and caminho.parent != pathlib.Path("."):
                raise ValueError("Selecione arquivos diretamente da pasta da máquina.")
            nomes.add(caminho.name.casefold())
    return [arquivo for arquivo in sorted(pasta.iterdir())
            if arquivo.is_file() and not arquivo.name.startswith("~")
            and arquivo.suffix.lower() in EXTENSOES_DE_ARTE
            and (nomes is None or arquivo.name.casefold() in nomes)
            and not e_folha_montada(arquivo)]


def versoes_da_selecao(pasta, arquivos=None):
    """Identidade por tamanho e modificação para conferir o lote exibido."""
    versoes = {}
    for arquivo in _arquivos_selecionados(pasta, arquivos):
        info = arquivo.stat()
        versoes[arquivo.name] = {"tamanho": info.st_size, "mtime_ns": info.st_mtime_ns}
    return versoes


def conferir_versoes(pasta, arquivos=None, versoes_esperadas=None):
    atuais = versoes_da_selecao(pasta, arquivos)
    if versoes_esperadas is not None and atuais != versoes_esperadas:
        raise ValueError("As artes selecionadas mudaram desde a prévia. Recalcule antes de montar.")
    return atuais


def _pymupdf():
    """Tardio: montar é conforto, e quem não tem a biblioteca não pode quebrar por isso."""
    import pymupdf

    return pymupdf


# --- a pasta --------------------------------------------------------


NOMES_PASTA_MAQUINA = {"UJV 100 UNY CV": "UJV 100"}

def nome_pasta_maquina(nome_maquina):
    """Nome curto usado na tela e nas pastas de montagem."""
    return NOMES_PASTA_MAQUINA.get(nome_maquina, nome_maquina)

def pasta_da_maquina(nome_maquina, raiz=None):
    """A pasta de montagem desta máquina: <raiz>/<nome da máquina>."""
    return pathlib.Path(raiz or PASTA_RAIZ) / nome_pasta_maquina(nome_maquina)


def maquina_da_pasta(pasta, maquinas=None):
    """
    A máquina a que uma pasta de montagem pertence, pelo nome dela.

    Comparação sem diferenciar maiúscula: o Windows não diferencia, e
    quem renomeia a pasta na mão sempre erra uma letra.
    """
    nome = pathlib.PurePath(pasta).name.strip().upper()
    for maquina in (MAQUINAS if maquinas is None else maquinas):
        # Aceita tanto a pasta curta nova quanto o identificador antigo,
        # para reconhecer lotes que já existiam antes do alias ser criado.
        if nome_pasta_maquina(maquina).upper() == nome or maquina.upper() == nome:
            return maquina
    return None


def maquinas_que_montam(maquinas=None):
    """
    As máquinas que têm pasta de montagem: as marcadas com 'montagem' no
    cadastro.

    DOCAN, SWJ e UJV estão habilitadas por decisão de 09/10/2026. O
    campo escolhe abas e pastas; a opção global 'montagem_automatica'
    decide se o vigia monta sem clique.

    O código da PLANA continua aqui e testado (ver encaixar_na_mesa): a
    H2525 monta em chapas no dia em que ele quiser, e aí é só o campo.
    """
    maquinas = MAQUINAS if maquinas is None else maquinas
    return [nome for nome, config in maquinas.items()
            if isinstance(config, dict) and config.get("montagem")
            and (config.get("largura_util_m") or config.get("mesa_util_m"))]


def pasta_de_saida(nome_maquina, raiz=None):
    """
    Onde a folha PRONTA vai parar: `<raiz>/SAIDA <nome da máquina>`.

    Pedido dele de 05/10/2026: *"precisamos de uma pasta de saída depois
    de montado — saída DOCAN, saída SWJ"*. Separar entrada de saída
    resolve de vez o que já mordeu em 05/10 às 01:45: a folha pronta
    ficava na pasta de entrada e a passada seguinte a lia como peça, e
    montava a folha dentro de outra folha. `e_folha_montada` continua
    valendo como cinto de segurança, pra quem arrastar a folha de volta.
    """
    return pathlib.Path(raiz or PASTA_RAIZ) / f"SAIDA {nome_pasta_maquina(nome_maquina)}"


def garantir_pastas(raiz=None, maquinas=None):
    """Cria a pasta de entrada e a de saída de cada máquina; devolve {máquina: pasta}."""
    criadas = {}
    for nome_maquina in maquinas_que_montam(maquinas):
        pasta = pasta_da_maquina(nome_maquina, raiz)
        pasta.mkdir(parents=True, exist_ok=True)
        pasta_de_saida(nome_maquina, raiz).mkdir(parents=True, exist_ok=True)
        criadas[nome_maquina] = pasta
    return criadas


def _config(nome_maquina, maquinas=None):
    config = (MAQUINAS if maquinas is None else maquinas).get(nome_maquina)
    return config if isinstance(config, dict) else {}


def largura_util(nome_maquina, maquinas=None, largura_m=None):
    """
    O limite de largura para encaixar as artes, em metros.

    Não é a mesma coisa que a largura útil da máquina, e ele separou as
    duas em 05/10/2026: *"quando fechar a arte não vai poder passar de
    5 metros na largura; a folga de 2 cm de cada lado eu coloco
    manualmente na máquina na hora da impressão. Todo fechamento deve ter
    5 metros de largura na DOCAN e na SWJ 320 cm de largura — eu me
    preocupo com a folga"*.

    Então `largura_montagem_m` é o número REDONDO que ele quer fechar
    (5,00 e 3,20) e `largura_util_m` continua sendo o que a máquina
    consegue imprimir, que é quem responde "cabe?" lá no vigia. Sem o
    campo, vale a largura da máquina. No fechamento, a sobra lateral é
    removida: a largura do PDF é a ocupada pelas artes e identificações.
    """
    maquinas = MAQUINAS if maquinas is None else maquinas
    config = maquinas.get(nome_maquina)
    if config is None:
        return None
    maxima = config.get("largura_montagem_m") or _config_maquina(config)[1]
    if largura_m is None:
        return maxima
    try:
        escolhida = float(largura_m)
    except (TypeError, ValueError) as erro:
        raise ValueError("Informe a largura de montagem em metros.") from erro
    minima = ROTULO_LARGURA_M + 2 * margem(nome_maquina, maquinas)
    if not math.isfinite(escolhida) or escolhida < minima:
        raise ValueError(f"A largura precisa ser de pelo menos {minima:.2f} m nesta máquina.")
    if escolhida > maxima + 1e-9:
        raise ValueError(f"A largura não pode passar de {maxima:.2f} m nesta máquina.")
    return escolhida


def mesa(nome_maquina, maquinas=None):
    """(largura, altura) da mesa, ou None quando a máquina é de rolo."""
    medida = _config(nome_maquina, maquinas).get("mesa_util_m")
    return tuple(medida) if medida else None


def margem(nome_maquina, maquinas=None):
    """
    Montagens de rolo fecham sem borda lateral, em todas as máquinas.

    A centralização e a folga da bobina são ajustadas na impressora.
    A mesa conserva o afastamento físico das bordas da chapa.
    """
    if mesa(nome_maquina, maquinas) is None:
        return 0.0
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
    if not dimensao or any(not math.isfinite(dimensao.get(chave, 0))
                          or dimensao.get(chave, 0) <= 0
                          for chave in ("largura_m", "altura_m")):
        return None
    return dimensao["largura_m"], dimensao["altura_m"]


# --- resolução: até que distância a peça fica limpa -------------------
#
# A conta NÃO é inventada, é a ACUIDADE VISUAL: o olho com visão 20/20
# separa detalhe de 1 minuto de arco, e daí sai
#
#     dpi necessário = 3438 / distância (em polegadas)
#     distância em que a peça fica limpa = 3438 / dpi (em polegadas)
#
# As M�?QUINAS não são o limite, e isso foi conferido no fabricante: a
# DOCAN R5200 imprime de 600 × 600 a 720 × 1440 dpi conforme a cabeça
# (Kyocera KJ4A, Ricoh Gen5 ou KM-1024i — docanuv.com), e as Mimaki
# chegam a 1200–1440 dpi. As duas põem muito mais ponto do que qualquer
# arte grande traz de pixel: quem limita é SEMPRE o arquivo do cliente e
# a distância de quem olha, nunca a impressora. Por isso o aviso fala de
# distância, não de "qualidade".
ACUIDADE_POLEGADAS = 3438
METROS_POR_POLEGADA = 0.0254

# Os dois limites são DISTÂNCIA de propósito: é o que ele conhece da
# peça, e dpi solto não quer dizer nada sem ela.
DISTANCIA_DE_PERTO_M = 0.50    # placa, adesivo, totem: dá pra encostar
DISTANCIA_DE_LONGE_M = 1.50    # lona de fachada, painel alto


def dpi_necessario(distancia_m):
    """Quantos dpi o olho pede pra não ver pixel a esta distância."""
    if distancia_m <= 0:
        return float("inf")
    return ACUIDADE_POLEGADAS / (distancia_m / METROS_POR_POLEGADA)


def distancia_limpa_m(dpi):
    """De que distância pra frente esta resolução deixa de aparecer."""
    if dpi <= 0:
        return float("inf")
    return ACUIDADE_POLEGADAS / dpi * METROS_POR_POLEGADA


def _resolucao_detalhada(arquivo, numero_pagina, fator, pymupdf=None):
    """
    O MENOR dpi efetivo da arte no tamanho final, acompanhado do estado
    da análise. "sem_raster" indica ausência de imagens rastreáveis;
    "nao_verificada" indica falha de leitura, sem afirmar qualidade.

    Mede a MENOR das imagens colocadas, nos dois eixos: uma foto de
    fundo em 300 dpi não salva o logo de 40 dpi em cima dela.
    """
    pymupdf = pymupdf or _pymupdf()
    arquivo = pathlib.Path(arquivo)
    fator = fator or 1.0
    try:
        if arquivo.suffix.lower() in IMAGENS:
            with pymupdf.open(str(arquivo)) as imagem:
                bytes_pdf = imagem.convert_to_pdf()
            doc = pymupdf.open("pdf", bytes_pdf)
            numero_pagina = 0
        else:
            doc = pymupdf.open(str(arquivo))
        try:
            pagina = doc.load_page(numero_pagina)
            pior = None
            for info in pagina.get_image_info():
                caixa = pymupdf.Rect(info["bbox"])
                largura_m = caixa.width / PT_M * fator
                altura_m = caixa.height / PT_M * fator
                for pixels, medida in ((info["width"], largura_m),
                                       (info["height"], altura_m)):
                    if medida <= 0 or not pixels:
                        continue
                    dpi = pixels / (medida / METROS_POR_POLEGADA)
                    pior = dpi if pior is None else min(pior, dpi)
            return {"dpi": pior, "estado": "sem_raster" if pior is None else "medida",
                    "motivo": ""}
        finally:
            doc.close()
    except Exception as erro:       # noqa: BLE001 - aviso, sem inventar qualidade
        return {"dpi": None, "estado": "nao_verificada",
                "motivo": f"Não consegui verificar a resolução: {type(erro).__name__}."}


def resolucao_da_arte(arquivo, numero_pagina, fator, pymupdf=None):
    """DPI efetivo, mantendo a API anterior; diagnóstico guarda falhas à parte."""
    return _resolucao_detalhada(arquivo, numero_pagina, fator, pymupdf)["dpi"]


def qualidade_da_resolucao(dpi):
    """'vetor', 'ok', 'atencao' ou 'aviso' — pelos dois limites de distância."""
    if dpi is None:
        return "vetor"
    if dpi >= dpi_necessario(DISTANCIA_DE_PERTO_M):
        return "ok"
    if dpi >= dpi_necessario(DISTANCIA_DE_LONGE_M):
        return "atencao"
    return "aviso"


def _itens_desenhados(pagina):
    """Os traçados da página com o recorte ativo de cada um, ou [] se a
    versão do PyMuPDF não souber dizer o recorte."""
    try:
        return pagina.get_drawings(extended=True)
    except (TypeError, ValueError, RuntimeError):
        return []


def caixa_da_arte(pagina, pymupdf):
    """
    O retângulo que a ARTE ocupa dentro da página — não a página.

    Regra dele, 05/10/2026: *"a arte deve bater o tamanho exato na largura
    que pede no nome... conferi na arte, sempre falta medida na largura"*.
    Ele estava certo, e a causa é a página: as oito lonas da LOJINHA têm
    **1 ponto de branco em volta** (0,35 mm; 7,1 mm depois do ×10 da
    escala), sobra da exportação. Medindo a P�?GINA, a arte entrava
    encolhida por essa franja e faltava exatamente isso na largura.

    Medindo a ARTE, as oito batem o nome CRAVADO: a de `0.40x3.00m` dá
    113,386 × 850,394 pt, que é 0,0400 × 0,3000 m — ×10, os 0,40 × 3,00
    do nome. O "+0,7 mm constante da exportação" que eu tinha anotado em
    04/10 era essa franja o tempo todo; a resposta certa nunca foi tolerar
    o desvio, era não contar o branco.

    Vem do `get_bboxlog`, que lê o conteúdo sem renderizar — rasterizar
    uma lona de 29 m pra achar a borda derrubaria a máquina.

    **Franja grande não é franja, é design.** Arte que é um logo no meio
    de uma folha branca tem caixa de tinta pequena, e esticá-la até a
    medida do nome seria desastre. Por isso só vale quando a arte cobre
    pelo menos `(1 - FRANJA_MAXIMA_FRACAO)` de cada lado; acima disso,
    manda a página, como antes.
    """
    uniao = None

    # TRAÇADO RECORTADO, não traçado: nestes arquivos o Illustrator deixa
    # um `re W* n` 0,6 pt fora de esquadro com o desenho, e ele apara
    # 2,2 mm (depois do ×10) do lado direito. Quem mede o traçado acha a
    # medida do nome e imprime uma tira branca no refile; quem mede a
    # TINTA acerta os dois. O 'scissor' do `get_drawings(extended=True)`
    # é esse recorte, e o 'level' diz até onde ele vale.
    tesouras = {}
    for item in _itens_desenhados(pagina):
        nivel = item.get("level", 0)
        for aberto in [n for n in tesouras if n >= nivel]:
            del tesouras[aberto]
        tipo = item.get("type")
        if tipo == "clip":
            recorte = item.get("scissor")
            if recorte is not None:
                tesouras[nivel] = pymupdf.Rect(recorte)
            continue
        if tipo == "group":
            continue
        caixa = item.get("rect")
        if caixa is None:
            continue
        caixa = pymupdf.Rect(caixa)
        for recorte in tesouras.values():
            caixa = caixa & recorte
        if caixa.is_empty:
            continue
        uniao = caixa if uniao is None else (uniao | caixa)

    # texto e imagem não saem no get_drawings. Entram sem recorte: é o
    # lado conservador (caixa maior), que no pior caso devolve a página
    for tipo, caixa in pagina.get_bboxlog():
        if tipo.startswith("clip") or tipo.startswith("ignore") or "path" in tipo:
            continue
        retangulo = pymupdf.Rect(caixa)
        uniao = retangulo if uniao is None else (uniao | retangulo)

    if uniao is None:
        return pagina.rect
    uniao = uniao & pagina.rect
    if uniao.is_empty or uniao.width <= 0 or uniao.height <= 0:
        return pagina.rect
    if (uniao.width < pagina.rect.width * (1 - FRANJA_MAXIMA_FRACAO)
            or uniao.height < pagina.rect.height * (1 - FRANJA_MAXIMA_FRACAO)):
        return pagina.rect
    return uniao


def medida_do_arquivo(caminho, numero_pagina=0):
    """
    (largura_m, altura_m, páginas) da ARTE no arquivo, ou None quando não
    dá pra abrir. Em imagem a medida física vem dos pixels e do DPI
    declarado; sem DPI, o padrão de 96 é chute — por isso imagem sem DPI
    nunca manda na medida, só o nome.
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
            pagina = doc.load_page(numero_pagina)
            if not pagina.get_bboxlog():
                return None
            arte = caixa_da_arte(pagina, pymupdf)
            return (arte.width / PT_M, arte.height / PT_M, doc.page_count)
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

    # A ÂNCORA É O MAIOR LADO DA PEÇA. Regra dele de 05/10/2026: *"quando
    # me refiro ajustar pela largura, pode criar a regra que é sempre
    # pelo maior lado — ou seja, 3,20 m precisa ser cravado. Isso serve
    # para a DOCAN também: ajustar pelo lado maior da peça"*.
    #
    # Antes a âncora era a LARGURA (a primeira medida do nome), e numa
    # peça de 2,12 x 3,20 isso deixava o erro cair justamente no 3,20 —
    # que é o lado que encosta na bobina e o que a produção confere.
    #
    # O fator sai desse lado e o outro é o que a proporção da arte der.
    # Nada é esticado e nada é cortado: o maior lado fecha redondo e a
    # diferença, quando existe, aparece no menor.
    #
    # Fica com a orientação cujo OUTRO lado chega mais perto do nome.
    ancora_na_largura = largura_alvo >= altura_alvo
    melhor = None
    for girar, (w, h) in ((False, (largura, altura)), (True, (altura, largura))):
        if ancora_na_largura:
            fator = largura_alvo / w
            diferenca = h * fator - altura_alvo
            outro_alvo = altura_alvo
        else:
            fator = altura_alvo / h
            diferenca = w * fator - largura_alvo
            outro_alvo = largura_alvo
        relativa = abs(diferenca) / outro_alvo if outro_alvo else 1.0
        if melhor is None or abs(diferenca) < abs(melhor[0]):
            melhor = (diferenca, relativa, girar, fator)

    diferenca, relativa, girar, fator = melhor
    if abs(diferenca) <= DIFERENCA_MAXIMA_M and relativa <= TOLERANCIA_PROPORCAO:
        # arredondado: 9,999999805 é 10x, e número feio num documento de
        # produção faz quem lê duvidar do resto
        maior = max(largura_alvo, altura_alvo)
        motivo = (f"arquivo {largura:.3f} x {altura:.3f} m ajustado {fator:.2f}x pelo "
                  f"MAIOR LADO do nome ({maior:.2f} m)")
        if abs(diferenca) >= 0.001:
            motivo += f"; o outro lado saiu {diferenca * 1000:+.0f} mm do que o nome diz"
        return {"acao": "escalar", "girar": girar, "fator": round(fator, 3),
                "motivo": motivo}

    return {"acao": "recusar", "girar": False, "fator": None,
            "motivo": f"o arquivo tem {largura:.2f} x {altura:.2f} m e o nome pede "
                      f"{largura_alvo:.2f} x {altura_alvo:.2f} m — pondo no MAIOR LADO do nome "
                      f"sem deformar, o outro sai {diferenca * 1000:+.0f} mm fora (o limite é "
                      f"{DIFERENCA_MAXIMA_M * 1000:.0f} mm, ou {TOLERANCIA_PROPORCAO:.0%}). "
                      f"Confira a arte ou o nome"}


# --- juntar tudo o que a pasta tem ---------------------------------


def e_folha_montada(arquivo):
    """
    Se este arquivo é uma folha que a montagem J�? produziu.

    Aconteceu em 05/10/2026, às 01:45, na pasta de verdade: a folha
    pronta fica na própria pasta da máquina, e a passada seguinte a leu
    como peça — nome com medida e material, como todas as outras. Montou
    a folha de 8 peças DENTRO de outra folha, de uma peça só, com 6,68 m
    e sem o cliente no nome. Sozinho isso repetiria pra sempre, a cada
    passada, e o que ele mandaria pra máquina seria uma folha com os
    rótulos das peças enterrados no meio.

    Duas provas, porque uma delas pode faltar: a ficha `.json` ao lado
    (que só a montagem escreve) e o padrão do nome de saída (que vale
    mesmo se ele apagar a ficha).
    """
    arquivo = pathlib.Path(arquivo)
    if arquivo.with_suffix(".json").is_file():
        return True
    return re.search(r"_MONTAGEM_\d+pecas", arquivo.stem) is not None


def pecas_da_pasta(pasta, config=None, maquinas=None, arquivos=None):
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
    ja_montados = retomada.originais_confirmados(pasta)

    for arquivo in _arquivos_selecionados(pasta, arquivos):
        if arquivo.name in ja_montados:
            recusadas.append({"arquivo": arquivo, "origem": "arquivamento",
                              "motivo": "PDF já salvo; original aguarda arquivamento e não será montado novamente"})
            continue
        if arquivo.suffix.lower() in PRECISA_ADOBE:
            recusadas.append({"arquivo": arquivo, "origem": "conversao",
                              "motivo": "EPS/PSD aguarda conversão Adobe; o original foi mantido na entrada"})
            continue
        alvo = medida_do_nome(arquivo.name, config)
        if alvo is None:
            recusadas.append({"arquivo": arquivo,
                              "motivo": "o nome não traz medida, e aqui é o nome que manda"})
            continue
        atual = medida_do_arquivo(arquivo)
        if atual is None:
            recusadas.append({"arquivo": arquivo,
                              "motivo": "página 1 sem conteúdo de arte ou ilegível; não consegui medir"})
            continue

        quantidade_lida = extrair_quantidade(arquivo.name)[0]
        quantidade = 1 if quantidade_lida is None else quantidade_lida
        if quantidade <= 0:
            recusadas.append({"arquivo": arquivo, "motivo": "a quantidade do nome precisa ser maior que zero"})
            continue
        categoria = identificar_categoria(arquivo.name.upper(), materiais, sinonimos)[0]
        if not categoria:
            recusadas.append({"arquivo": arquivo,
                              "motivo": "não reconheci o material no nome — ele escolhe a bobina"})
            continue

        do_arquivo = []
        for pagina in range(atual[2]):
            medida = atual if pagina == 0 else medida_do_arquivo(arquivo, pagina)
            if medida is None:
                recusadas.append({"arquivo": arquivo,
                                  "motivo": f"página {pagina + 1} sem conteúdo de arte ou ilegível; não consegui medir"})
                do_arquivo = []
                break
            ajuste = ajuste_para(alvo, medida)
            if ajuste["acao"] == "recusar":
                recusadas.append({"arquivo": arquivo,
                                  "motivo": f"página {pagina + 1}: {ajuste['motivo']}"})
                do_arquivo = []
                break
            largura_peca, altura_peca = alvo
            w_arte, h_arte = medida[:2]
            if ajuste["girar"]:
                w_arte, h_arte = h_arte, w_arte
            # O maior lado é a âncora, o outro preserva a proporção real.
            if alvo[0] >= alvo[1]:
                altura_peca = alvo[0] * h_arte / w_arte
                fator_real = alvo[0] / w_arte
            else:
                largura_peca = alvo[1] * w_arte / h_arte
                fator_real = alvo[1] / h_arte
            resolucao = _resolucao_detalhada(arquivo, pagina, fator_real)
            for copia in range(int(quantidade)):
                do_arquivo.append({
                    "arquivo": arquivo, "nome": arquivo.name, "pagina": pagina,
                    "largura_m": largura_peca, "altura_m": altura_peca,
                    # o que o NOME pede, pro documento poder dizer as duas
                    # coisas quando elas diferem — número deduzido nunca
                    # se passa por declarado
                    "nome_m": (alvo[0], alvo[1]),
                    # o dpi que a arte TEM depois de posta no tamanho
                    # final; None quando é vetor e não há pixel que acabe
                    "dpi": resolucao["dpi"], "resolucao_estado": resolucao["estado"],
                    "resolucao_motivo": resolucao["motivo"],
                    "quantidade": int(quantidade), "copia": copia + 1,
                    "categoria": categoria, "ajuste": ajuste,
                })
        pecas.extend(do_arquivo)
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
                  quando=None, chapas=None, parte=None):
    """
    O nome do arquivo de saída, no MESMO padrão que o resto do sistema lê.

    Começa com a especificação (1UN + material + medida) porque é dali
    que a etiqueta, a OS, o relatório e a escolha de máquina leem — uma
    folha montada é UMA peça de material, de 5,00 x 9,86 m. O cliente
    entra em seguida, como ele pediu, e a descrição diz que é montagem e
    de quantas peças.

    'parte' é (qual, de quantas) se uma divisão for solicitada explicitamente.
    A MEDIDA do nome é a DESTA parte, não a do conjunto: cada
    arquivo é uma peça de material por si, e é assim que o m² e o estoque
    o leem. O carimbo de hora é o mesmo nas partes do mesmo lote, então
    elas ficam juntas na listagem.
    """
    quando = quando or datetime.datetime.now()
    partes = [f"1UN {categoria} {largura_m:.2f}X{comprimento_m:.2f}M"]
    if cliente:
        partes.append(re.sub(r"[^\w .-]", "", cliente).strip().replace(" ", "_"))
    miolo = f"MONTAGEM_{quantas}pecas"
    if chapas:
        miolo += f"_{chapas}chapas"
    if parte and parte[1] > 1:
        miolo += f"_parte{parte[0]}de{parte[1]}"
    partes.append(f"{miolo}_{quando:%d-%m-%Y_%H-%M}")
    return "_".join(partes) + ".pdf"


# --- encaixar e desenhar -------------------------------------------


def _formas_reservadas(peca, largura_util_m, folga_m, altura_util_m=None):
    """Cada orientação reserva a faixa de identificação acima da arte."""
    w, h = peca["largura_m"], peca["altura_m"]
    if w <= 0 or h <= 0 or not math.isfinite(w) or not math.isfinite(h):
        return []
    formas = []
    deitar = (h > w and h <= largura_util_m and h + folga_m > largura_util_m
              and w + folga_m <= largura_util_m)
    for girada, (larga, alta) in ((False, (w, h)), (True, (h, w))):
        if deitar and not girada:
            continue
        if larga > largura_util_m or (altura_util_m is not None and alta > altura_util_m):
            continue
        reservada_l = min(max(larga + folga_m, ROTULO_LARGURA_M), largura_util_m)
        reservada_a = alta + folga_m
        if reservada_l < ROTULO_LARGURA_M:
            continue
        # Arredondar para cima preserva a faixa; inteiros evitam falsos não-cabe.
        pw = int(math.ceil(reservada_l * 1000 - 1e-7))
        ph = int(math.ceil(reservada_a * 1000 - 1e-7))
        if altura_util_m is not None and ph > round(altura_util_m * 1000):
            continue
        if (pw, ph) not in [(a, b) for a, b, _ in formas]:
            formas.append((pw, ph, girada))
    return formas


def _postas_com_rotulos(pecas, largura_m, folga_m, altura_m=None):
    """Busca guilhotina com reservas específicas por orientação, sem rasterizar."""
    largura = int(round(largura_m * 1000))
    formas = {i: _formas_reservadas(p, largura_m, folga_m, altura_m)
              for i, p in enumerate(pecas)}
    indices = [i for i, opcoes in formas.items() if opcoes]
    if not indices:
        return [] if altura_m is not None else ([], 0.0)
    altura = (int(round(altura_m * 1000)) if altura_m is not None else
              sum(max(max(w, h) for w, h, _ in formas[i]) for i in indices) + 1)
    menor = min(min(w, h) for i in indices for w, h, _ in formas[i])
    melhor = None
    for ordem in aproveitamento._ORDENS:
        politicas = ("livre", "estreita") if altura_m is None else ("livre",)
        regras = ("baixo",) if altura_m is None else ("area", "lado", "baixo")
        divisoes = (("prateleira", "coluna") if altura_m is None else
                    ("menor_sobra", "maior_sobra", "maior_area"))
        for politica in politicas:
            for regra in regras:
                for divisao in divisoes:
                    pedacos = [aproveitamento._Pedaco(largura, altura)]
                    ordenados = sorted(indices, key=lambda i: ordem(formas[i][0][:2]))
                    for indice in ordenados:
                        opcoes = formas[indice]
                        if politica == "estreita":
                            opcoes = [min(opcoes, key=lambda f: (f[0], f[1]))]
                        orientacoes = [(w, h) for w, h, _ in opcoes]
                        escolhido = None
                        for pedaco in pedacos:
                            lugar = pedaco.melhor_lugar(orientacoes, regra)
                            if lugar is not None and (escolhido is None or lugar[0] < escolhido[1][0]):
                                escolhido = (pedaco, lugar)
                                if regra == "baixo":
                                    break
                        if escolhido is None:
                            if altura_m is None:
                                pedaco = pedacos[0]
                                pedaco.fechar_faixa()
                            else:
                                pedaco = aproveitamento._Pedaco(largura, altura)
                                pedacos.append(pedaco)
                            escolhido = (pedaco, pedaco.melhor_lugar(orientacoes, regra))
                        pedaco, (_nota, livre, pw, ph) = escolhido
                        girada = next(g for w, h, g in opcoes if (w, h) == (pw, ph))
                        pedaco.colocar(livre, pw, ph, divisao, menor, (indice, girada))
                    nota = ((pedacos[0].topo, max(x + w for x, _y, w, _h in pedacos[0].postas))
                            if altura_m is None else
                            (len(pedacos), -max(p.maior_livre()[0] for p in pedacos)))
                    if melhor is None or nota < melhor[0]:
                        melhor = (nota, pedacos)
    resultado = []
    for pedaco in melhor[1]:
        postas = []
        for (x, y, pw, ph), (indice, girada) in zip(pedaco.postas, pedaco.marcas):
            p = pecas[indice]
            w, h = ((p["altura_m"], p["largura_m"]) if girada else
                    (p["largura_m"], p["altura_m"]))
            postas.append((indice, x / 1000, y / 1000, w, h, girada, pw / 1000, ph / 1000))
        resultado.append(postas)
    return resultado if altura_m is not None else (resultado[0], melhor[1][0].topo / 1000)


def encaixar(pecas, largura_util_m, margem_m=None, folga_m=None):
    """
    Onde cada peça fica na folha: (postas, comprimento_m).

    Posta: (índice da peça, x_m, y_m, largura_m, altura_m, girada) — já
    descontada a folga e a canaleta, ou seja, é o retângulo da ARTE.

    A folga e a canaleta entram INFLANDO a peça antes do encaixe: elas
    são espaço reservado, não sobra. Sem isso o rótulo de 5 cm cai dentro
    da peça de baixo (visto no desenho de 04/10/2026).
    """
    margem_m = MARGEM_M if margem_m is None else margem_m
    folga_m = folga_da_montagem(folga_m=folga_m)
    return _postas_com_rotulos(pecas, largura_util_m - 2 * margem_m, folga_m)




def _texto_do_rotulo(peca, numero):
    nome = pathlib.PurePath(peca["nome"]).stem
    if peca["quantidade"] > 1:
        nome = f"{nome} ({peca['copia']}/{peca['quantidade']})"
    return f"{numero:02d}  {nome}"


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
    # O RÓTULO TEM 300 mm DE LARGURA, SEMPRE (ele, 04/10/2026: *"os nomes
    # precisa ficar todos com 300mm de largura... preciso só que a
    # informação seja visível na hora da impressão"*).
    #
    # Então a letra não é escolhida, é CALCULADA: o tamanho que faz este
    # texto medir 300 mm. Nome comprido sai com letra menor, nome curto
    # com letra maior, e toda etiqueta ocupa a mesma faixa. O teto é a
    # altura disponível — letra que não cabe na meia-folga sairia junto
    # com a peça de cima no refile.
    largura_1pt = pymupdf.get_text_length(texto, fontname="hebo", fontsize=1)
    if largura_1pt > 0:
        pedido = min(ROTULO_LARGURA_M, largura_m) / largura_1pt * 1000   # em mm
        teto = (altura_max_m if altura_max_m is not None else RECUO_CORTE_M) / 1.8 * 1000
        # arredonda pra BAIXO: 0,05 mm de letra a mais estoura os 300 mm,
        # o insert_textbox quebra a linha e aí o nome sai CORTADO
        tamanhos = (int(min(pedido, teto) * 100) / 100,)
    else:
        tamanhos = (ROTULO_LETRA_MM,)
    if tamanhos[0] < ROTULO_LETRA_MINIMA_MM:
        raise AssertionError("O nome inteiro não cabe em um rótulo legível de 30 cm; "
                             "aumente o espaço ou confira o nome da arte.")

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


def colocar_arte(pagina, caixa, arquivo, numero_pagina, girar, pymupdf):
    """
    Põe a arte INTEIRA na caixa, com escala uniforme.

    Não há recorte nenhum: a caixa já nasce com a proporção da arte,
    porque a largura é a do nome e o comprimento veio dessa proporção
    (`pecas_da_pasta`). Então `keep_proportion` preenche a caixa exata
    sem esticar e sem deixar tira branca.

    Imagem vira PDF antes (`convert_to_pdf`), pra PDF e imagem seguirem o
    mesmo caminho — dois caminhos diferentes pra mesma regra é como a
    medida de um deles sai errada sem ninguém ver.
    """
    arquivo = pathlib.Path(arquivo)
    if arquivo.suffix.lower() in IMAGENS:
        with pymupdf.open(str(arquivo)) as imagem:
            bytes_pdf = imagem.convert_to_pdf()
        origem = pymupdf.open("pdf", bytes_pdf)
        numero_pagina = 0
    else:
        origem = pymupdf.open(str(arquivo))
    try:
        # recorta a FRANJA BRANCA da exportação (ver caixa_da_arte): sem
        # isso a arte entra encolhida por ela e falta medida na largura
        recorte = caixa_da_arte(origem.load_page(numero_pagina), pymupdf)
        pagina.show_pdf_page(caixa, origem, numero_pagina, clip=recorte,
                             rotate=girar, keep_proportion=True)
    finally:
        origem.close()


def encaixar_na_mesa(pecas, mesa_m, margem_m=None, folga_m=None):
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

    folga_m = folga_da_montagem(folga_m=folga_m)
    return _postas_com_rotulos(pecas, util_l, folga_m, util_a)


def comprimento_da_folha(comprimento_m, margem_m, folga_m=None):
    """
    O comprimento da folha IMPRESSA: o encaixe, mais o cabeçalho, mais a
    margem de baixo e a folga.

    Fonte única de propósito. É esta medida que vai no NOME do arquivo, e
    é pelo nome que o m², a escolha de máquina e a baixa de estoque
    contam — enquanto ela era calculada em dois lugares, o nome dizia
    6,45 m numa folha de 6,52 m, e 7 cm de lona saíam do rolo por folha
    sem aparecer em lugar nenhum.
    """
    return comprimento_m + CABECALHO_M + margem_m + folga_da_montagem(folga_m=folga_m)


def _escrever_cabecalho(pagina, titulo, largura_m, pymupdf):
    """Mantém o título completo na área do cabeçalho, mesmo em folha estreita."""
    caixa = pymupdf.Rect(0.02 * PT_M, 0.018 * PT_M,
                        (largura_m - 0.02) * PT_M, CABECALHO_M * PT_M)
    for tamanho_mm in (30, 25, 20, 15, 12, 10, 8, 6, 4, 3, 2):
        if pagina.insert_textbox(caixa, titulo, fontsize=tamanho_mm / 1000 * PT_M,
                                fontname="hebo", color=(0.35, 0.35, 0.35)) >= 0:
            return
    raise ValueError("O cabeçalho completo não coube. Confira o nome do cliente e o lote.")


def desenhar(pecas, postas, comprimento_m, largura_util_m, titulo, margem_m=None,
             folga_m=None):
    """
    A folha pronta: cada arte no tamanho do NOME, o nome no canto
    superior esquerdo dela.

    A arte encosta no canto de BAIXO do espaço reservado, então a folga
    de 5 cm sobra em cima — e é ali, alinhado à esquerda da peça, que vai
    o nome. É a convenção do RasterLink, que ele pediu pra seguir: o
    material vai ser refilado e cada pedaço precisa sair com o nome dele.
    """
    pymupdf = _pymupdf()
    margem_m = MARGEM_M if margem_m is None else margem_m
    folga_m = folga_da_montagem(folga_m=folga_m)
    doc = pymupdf.open()
    # o CABECALHO em cima, e embaixo a folga inteira: a arte da ultima
    # fileira encosta no fim do encaixe e a marca de corte dela fica
    # 2,5 cm abaixo disso
    pagina = doc.new_page(
        width=largura_util_m * PT_M,
        height=comprimento_da_folha(comprimento_m, margem_m, folga_m) * PT_M)
    pagina.draw_rect(pagina.rect, color=None, fill=(1, 1, 1))

    for numero, posta in enumerate(postas, start=1):
        _desenhar_peca(pagina, pecas, posta, numero, margem_m, largura_util_m,
                       CABECALHO_M, pymupdf, folga_m)

    _escrever_cabecalho(pagina, titulo, largura_util_m, pymupdf)
    return doc


def _desenhar_peca(pagina, pecas, posta, numero, margem_m, largura_pagina_m,
                   deslocamento_m, pymupdf, folga_m=None):
    """
    Uma peça na página: a arte, as marcas de corte e o nome.

    É a mesma coisa pro rolo e pra mesa — o que muda entre os dois é só a
    página e o deslocamento do topo. O rolo tem cabeçalho; a chapa não
    tem, porque a página É a chapa e a faixa roubaria área dela.
    """
    indice, x, y, largura, altura, girada, reservada_l, reservada_a = posta
    peca = pecas[indice]
    recuo = folga_da_montagem(folga_m=folga_m) / 2
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
        # A arte entra INTEIRA e preenche a caixa exata: a caixa já tem a
        # proporção dela (largura do nome, comprimento pela proporção da
        # arte), então não há o que recortar nem o que esticar.
        colocar_arte(pagina, caixa, arquivo, peca["pagina"], girar, pymupdf)

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
        # a folguinha de 1 mm entre o texto e a arte entra no teto: o
        # rótulo inteiro tem que caber na meia-folga, senão o pedaço de
        # cima sai com a peça vizinha no refile
        _escrever_rotulo(pagina, caixa.x0, caixa.y0 - 0.001 * PT_M, largura_rotulo,
                         _texto_do_rotulo(peca, numero), pymupdf, recuo - 0.001)


def desenhar_chapas(pecas, chapas, mesa_m, titulo, margem_m=None, folga_m=None):
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
            _desenhar_peca(pagina, pecas, posta, numero, margem_m, largura_m, 0.0,
                           pymupdf, folga_m)
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


def converter_o_que_precisa(pasta, logger=None, conversores=None, arquivos=None):
    """Conversão manual usa a mesma trava da montagem automática."""
    with trava_montagem(pasta):
        return _converter_o_que_precisa(pasta, logger, conversores, arquivos)


def _converter_o_que_precisa(pasta, logger=None, conversores=None, arquivos=None,
                            guardar_original=True, pasta_pdf=None, conversoes=None):
    """
    Passa pelo Illustrator/Photoshop o que o PyMuPDF não abre (`.eps`,
    `.psd`) e devolve os PDFs gerados.

    É um passo À PARTE, e nunca dentro da prévia: isto ESCREVE (gera o
    PDF e tira o original da vista, em `_originais`), e a prévia só pode
    olhar. Quem chama é a montagem de verdade — e a tela, num botão, pra
    ele ver o resultado antes de montar.

    Programa fechado ou pywin32 faltando vira aviso, nunca exceção: o
    resto da pasta continua montando sem o que não deu pra converter.
    """
    pasta = pathlib.Path(pasta)
    logger = logger or (lambda nivel, mensagem: None)
    gerados = []
    confirmados = retomada.originais_confirmados(pasta)
    pendentes = [a for a in _arquivos_selecionados(pasta, arquivos)
                 if a.suffix.lower() in PRECISA_ADOBE and a.name not in confirmados]
    if not pendentes:
        return gerados
    try:
        import conversao_adobe
    except Exception as erro:   # noqa: BLE001
        logger("warn", f"não consegui carregar a conversão Adobe: "
                       f"{type(erro).__name__}: {erro}")
        return gerados

    def contar(nivel, mensagem, *_resto):
        logger("warn" if nivel == "err" else "ok", mensagem)

    for arquivo in pendentes:
        try:
            novo = conversao_adobe.converter_se_necessario(
                pasta, arquivo.name, pasta / NOME_SUBPASTA_ORIGINAIS, contar,
                conversores=conversores, guardar_original=guardar_original,
                pasta_pdf=pasta_pdf)
        except Exception as erro:   # noqa: BLE001
            logger("warn", f"'{arquivo.name}' não converteu: "
                           f"{type(erro).__name__}: {erro}")
            continue
        if novo:
            derivada = pathlib.Path(pasta_pdf or pasta) / novo
            gerados.append(derivada)
            if conversoes is not None:
                conversoes[derivada.name] = arquivo
    return gerados


def a_converter(pasta, arquivos=None):
    """Os arquivos da pasta que só entram depois de passar pelo Adobe."""
    pasta = pathlib.Path(pasta)
    if not pasta.is_dir():
        return []
    return [a for a in _arquivos_selecionados(pasta, arquivos)
            if a.suffix.lower() in PRECISA_ADOBE]


def dividir_por_fileira(postas, maximo_m=None):
    """
    Divide o encaixe em folhas de no máximo `maximo_m`, devolvendo
    [(postas rebaixadas pro topo da folha, comprimento), ...].

    O corte é só ENTRE FILEIRAS — peça nenhuma é partida. Regra dele de
    05/10/2026: *"jamais deve cortar algum pedaço da imagem"*. Por isso
    uma fileira mais alta que o máximo sai inteira e estoura o limite:
    entre quebrar a regra do tamanho e cortar arte, quem cede é o
    tamanho. Sem máximo explícito, conserva o encaixe numa folha contínua.
    """
    maximo = math.inf if maximo_m is None else maximo_m
    if not postas:
        return []
    fileiras = {}
    for posta in postas:
        fileiras.setdefault(round(posta[2], 6), []).append(posta)

    grupos, atual, topo = [], [], None
    for y in sorted(fileiras):
        da_fileira = fileiras[y]
        fundo = max(p[2] + p[7] for p in da_fileira)
        if atual and (fundo - topo) > maximo:
            grupos.append((atual, topo))
            atual, topo = [], None
        if topo is None:
            topo = y
        atual.extend(da_fileira)
    if atual:
        grupos.append((atual, topo))

    folhas = []
    for da_folha, topo in grupos:
        rebaixadas = [(p[0], p[1], p[2] - topo) + tuple(p[3:]) for p in da_folha]
        folhas.append((rebaixadas, max(p[2] + p[7] for p in rebaixadas)))
    return folhas


def _reencaixar(pecas, postas, comprimento, largura_util_m, margem_m):
    """
    Reencaixa uma parte SOZINHA e fica com o resultado só se ele gastar
    menos bobina. Devolve (postas, comprimento).

    A divisão herda as posições de um encaixe feito pra bobina SEM
    limite: a peça que sobra pro fim vai do jeito que estava lá. Numa
    folha real da SWJ (05/10/2026) isso custou 1,20 m — uma lona de
    1,20 × 2,40 ficou EM PÉ sozinha numa folha de 2,58, quando deitada
    sozinha cabe em 1,38.

    Reencaixar só a sobra foi medido contra as alternativas: encaixar
    direto com teto de 10 m (como chapa) é PIOR, porque aquele encaixe
    minimiza NÚMERO DE FOLHAS e não metros — gastou 4,72 m a mais em dez
    lotes sorteados. Este aqui nunca piora, por construção: se o encaixe
    novo não for menor, fica o antigo.
    """
    indices = [p[0] for p in postas]
    refeitas, novo = encaixar([pecas[i] for i in indices], largura_util_m, margem_m)
    if len(refeitas) != len(postas) or novo >= comprimento:
        return postas, comprimento
    # o encaixe devolve índice da lista NOVA: desfaz o mapeamento, senão
    # cada peça sai com o rótulo de outra
    return [(indices[p[0]],) + tuple(p[1:]) for p in refeitas], novo


def largura_usada(postas, margem_m=0.0):
    """
    A largura que a folha realmente ocupa — e é com ela que a folha FECHA.

    Regra dele de 05/10/2026: *"depois que montar a arte precisa salvar
    ela sempre centralizada, ou sem margem em branco nas laterais — eu
    centralizo ela na máquina... temos até 5,00 m na DOCAN; se a arte
    bater 4,70, pode fechar sem branco em volta"*. Folha de 5,00 m não
    dá pra centralizar na máquina: ela ocupa tudo. Fechando em 4,70,
    sobram 17 cm de cada lado pra ele acertar o alinhamento.

    O RÓTULO entra na conta: ele começa na borda esquerda da peça e tem
    300 mm, então numa peça estreita no canto direito é ELE quem manda
    na largura. Cortar o nome pra economizar 10 cm de branco deixaria o
    refile sem saber que peça é aquela.
    """
    if not postas:
        return 0.0
    direita = max(x + max(largura, ROTULO_LARGURA_M)
                  for _i, x, _y, largura, *_resto in postas)
    return direita + 2 * margem_m


def planejar_pasta(pasta, nome_maquina=None, config=None, maquinas=None,
                   raiz_clientes=None, arquivos=None, folga_m=None,
                   pecas_adicionais=None, recusadas_adicionais=None, convertidos=None,
                   largura_m=None):
    """
    O que a montagem FARIA com esta pasta — sem escrever nada, sem mover
    nada.

    Devolve {'maquina', 'largura_util_m', 'mesa_m', 'margem_m', 'cliente',
    'folhas': [...], 'recusadas': [...]}, e cada folha já traz o encaixe
    pronto: as peças, onde cada uma fica, o tamanho que a folha vai ter e
    o aproveitamento.

    É a MESMA conta que monta de verdade — `montar_pasta` chama esta —, e
    isso é de propósito: prévia calculada por fora é prévia que mente no
    dia em que uma das duas mudar.

    A recusa diz de onde veio: `leitura` é arte que o leitor não aceitou
    (essa vai pra `_conferir`), `encaixe` é arte que não coube na bobina
    (essa fica com as outras, e só vira aviso).
    """
    pasta = pathlib.Path(pasta)
    config = config or carregar_config()
    nome_maquina = nome_maquina or maquina_da_pasta(pasta)
    largura = largura_util(nome_maquina, maquinas, largura_m)
    chapa = mesa(nome_maquina, maquinas)
    margem_m = margem(nome_maquina, maquinas)
    folga_m = folga_da_montagem(nome_maquina, maquinas, folga_m, config)
    versoes = versoes_da_selecao(pasta, arquivos)
    plano = {"maquina": nome_maquina, "largura_util_m": largura, "mesa_m": chapa,
             "margem_m": margem_m, "cliente": "", "pasta": pasta,
             "folga_m": folga_m, "versoes": versoes, "arquivos": arquivos,
             "folhas": [], "recusadas": []}
    # máquina de MESA não tem largura de rolo, e é o caso da H2525: pedir
    # 'largura' aqui a deixava de fora da montagem inteira, calada
    if not pasta.is_dir() or not (largura or chapa):
        return plano

    arquivos_leitura = arquivos
    if convertidos:
        arquivos_leitura = [a.name for a in _arquivos_selecionados(pasta, arquivos)
                            if a.name not in convertidos]
    pecas, recusadas = pecas_da_pasta(pasta, config, maquinas, arquivos_leitura)
    pecas.extend(pecas_adicionais or [])
    recusadas.extend(recusadas_adicionais or [])
    plano["recusadas"] = [{"arquivo": r["arquivo"], "motivo": r["motivo"],
                           "origem": r.get("origem", "leitura")} for r in recusadas]
    if not pecas:
        conferir_versoes(pasta, arquivos, versoes)
        return plano

    plano["cliente"] = cliente_das_pecas(pecas, raiz_clientes)
    # O material final pode ser PS, mas sua arte é impressa em adesivo
    # para aplicação. A escolha explícita por máquina define a bobina;
    # o material e o nome originais continuam nas peças e na ficha.
    materiais_impressao = (config.get("montagem", {}).get(nome_maquina, {}).get(
        "materiais_impressao", {}) if not chapa else {})
    por_material = {}
    for peca in pecas:
        material = materiais_impressao.get(peca["categoria"], peca["categoria"])
        if material != peca["categoria"] and config.get("materiais", {}).get(
                material, {}).get("tipo") != "rolo":
            raise ValueError(f"Material de impressão inválido para {nome_maquina}: {material}")
        peca["material_impressao"] = material
        por_material.setdefault(material, []).append(peca)

    for categoria, do_material in sorted(por_material.items()):
        # Um arquivo é uma unidade: todas as páginas e cópias entram ou ele fica de fora.
        while do_material:
            if chapa:
                paginas = encaixar_na_mesa(do_material, chapa, margem_m, folga_m)
                postas = [p for pagina in paginas for p in pagina]
                comprimento = chapa[1]
            else:
                postas, comprimento = encaixar(do_material, largura, margem_m, folga_m)
                paginas = [postas]
            colocadas = {posta[0] for posta in postas}
            problemas = {}
            for indice, peca in enumerate(do_material):
                if indice not in colocadas:
                    teto = (f"{chapa[0]:.2f} x {chapa[1]:.2f} m de mesa" if chapa
                            else f"largura útil {largura:.2f} m")
                    problemas[peca["arquivo"]] = (
                        f"{peca['largura_m']:.2f} x {peca['altura_m']:.2f} m não cabe na "
                        f"{nome_maquina} nem girada ({teto}, menos "
                        f"{margem_m * 100:.0f} cm de borda de cada lado)")
            for numero, posta in enumerate(postas, 1):
                peca = do_material[posta[0]]
                texto = _texto_do_rotulo(peca, numero)
                largura_1pt = _pymupdf().get_text_length(texto, fontname="hebo", fontsize=1)
                corpo = min(min(ROTULO_LARGURA_M, posta[6]) / max(largura_1pt, 1e-9) * 1000,
                            (folga_m / 2 - 0.001) / 1.8 * 1000)
                if corpo < ROTULO_LETRA_MINIMA_MM:
                    problemas[peca["arquivo"]] = (
                        "O nome inteiro não cabe no rótulo com letra legível. "
                        "Aumente o espaço entre artes ou confira o nome do arquivo.")
            if not problemas:
                break
            origens = {p["arquivo"]: p.get("arquivo_original", p["arquivo"]) for p in do_material}
            plano["recusadas"].extend({"arquivo": origens[arquivo], "origem": "encaixe", "motivo": motivo}
                                     for arquivo, motivo in problemas.items())
            do_material = [p for p in do_material if p["arquivo"] not in problemas]
        if not do_material:
            continue
        if chapa:
            # a plana já sai uma página por chapa: nada a dividir nem a aparar
            area_pecas = sum(p["largura_m"] * p["altura_m"] for p in do_material)
            area_folha = chapa[0] * chapa[1] * len(paginas)
            plano["folhas"].append({
                "categoria": categoria, "pecas": do_material, "postas": postas,
                "paginas": paginas, "comprimento_m": chapa[1], "folha_m": chapa[1],
                "largura_m": chapa[0], "chapas": len(paginas),
                "parte": 1, "partes": 1,
                "area_pecas_m2": area_pecas, "area_folha_m2": area_folha,
                "aproveitamento": (area_pecas / area_folha) if area_folha else 0.0,
                "tamanho": f"{len(paginas)} chapa(s) de {chapa[0]:.2f} x {chapa[1]:.2f} m",
            })
            continue

        # O lote de rolo sai inteiro; a divisão em 10 m deixou de ser uma regra.
        partes = [(postas, comprimento)]
        for numero, (da_parte, comprimento_parte) in enumerate(partes, start=1):
            # a folha FECHA na largura que usa, sem branco nas laterais
            largura_parte = min(largura_usada(da_parte, margem_m), largura)
            folha_m = comprimento_da_folha(comprimento_parte, margem_m, folga_m)
            area_folha = largura_parte * folha_m
            indices = {p[0] for p in da_parte}
            area_pecas = sum(do_material[i]["largura_m"] * do_material[i]["altura_m"]
                             for i in indices)
            plano["folhas"].append({
                "categoria": categoria, "pecas": do_material, "postas": da_parte,
                "paginas": [da_parte], "comprimento_m": comprimento_parte,
                "folha_m": folha_m, "largura_m": largura_parte, "chapas": None,
                "parte": numero, "partes": len(partes),
                "area_pecas_m2": area_pecas, "area_folha_m2": area_folha,
                "aproveitamento": (area_pecas / area_folha) if area_folha else 0.0,
                "tamanho": f"{largura_parte:.2f} x {folha_m:.2f} m",
            })
    conferir_versoes(pasta, arquivos, versoes)
    return plano


def _guardar_recusadas(recusadas, pasta, logger=None):
    """Mantém o fluxo de revisão sem mover recusas por falta de encaixe."""
    logger = logger or (lambda nivel, mensagem: None)
    avisos = []
    for recusada in recusadas:
        if recusada["origem"] != "leitura":
            continue
        arquivo = pathlib.Path(recusada["arquivo"])
        try:
            alvo = _mover_para(arquivo, pasta / NOME_SUBPASTA_PROBLEMAS)
            alvo.with_suffix(alvo.suffix + ".motivo.txt").write_text(
                recusada["motivo"] + "\n", encoding="utf-8")
        except OSError as erro:
            aviso = f"{arquivo.name}: não consegui guardar a recusa para revisão ({erro})."
            avisos.append(aviso)
            logger("warn", aviso)
    return avisos


def montar_pasta(pasta, nome_maquina=None, config=None, maquinas=None, logger=None,
                 guardar_originais=True, quando=None, raiz_clientes=None,
                 arquivos=None, folga_m=None, versoes_esperadas=None, passadas_docan=None,
                 largura_m=None):
    """
    Monta tudo o que está na pasta e devolve
    {'folhas': [...], 'recusadas': [...], 'maquina', 'largura_util_m'}.

    UMA FOLHA POR MATERIAL: lona e adesivo não dividem bobina, e o m²
    deste projeto nunca mistura material.

    Os originais vão pra `_originais/<carimbo>` depois de montados — se
    ficassem na pasta, a próxima passada montaria tudo de novo. O que foi
    recusado na LEITURA vai pra `_conferir`, com o motivo num .txt ao
    lado: peça que some sem explicação é peça que não vai ser produzida.
    """
    pasta = pathlib.Path(pasta)
    quando = quando or datetime.datetime.now()
    logger = logger or (lambda nivel, mensagem: None)
    folga_m = folga_da_montagem(nome_maquina or maquina_da_pasta(pasta), maquinas,
                               folga_m, config)
    nome_maquina = nome_maquina or maquina_da_pasta(pasta)
    largura_util(nome_maquina, maquinas, largura_m)
    tempo_impressao.estimar(nome_maquina or maquina_da_pasta(pasta), 0, passadas_docan)
    with trava_montagem(pasta), contextlib.ExitStack() as preparacao:
        conferir_versoes(pasta, arquivos, versoes_esperadas)
        avisos_pendentes = (retomada.retomar_arquivamento(pasta, _mover_para, logger)
                           if guardar_originais else [])
        # EPS e PSD viram PDF antes de qualquer conta: o PyMuPDF não os abre,
        # e sem isto eles seriam recusados por "não consegui abrir pra medir"
        conversoes, extras, recusas_extras = {}, [], []
        if a_converter(pasta, arquivos):
            temporaria = pathlib.Path(preparacao.enter_context(
                tempfile.TemporaryDirectory(prefix=".conversao-", dir=pasta)))
            gerados = _converter_o_que_precisa(
                pasta, logger, arquivos=arquivos, guardar_original=False,
                pasta_pdf=temporaria, conversoes=conversoes)
            if gerados:
                extras, recusas_extras = pecas_da_pasta(
                    temporaria, config, maquinas, [a.name for a in gerados])
                for peca in extras:
                    original = conversoes[peca["nome"]]
                    peca["arquivo_original"] = original
                    peca["nome"] = original.name
                for recusa in recusas_extras:
                    recusa["arquivo"] = conversoes[pathlib.Path(recusa["arquivo"]).name]
        arquivos_trabalho = arquivos
        plano = planejar_pasta(pasta, nome_maquina, config, maquinas, raiz_clientes,
                              arquivos_trabalho, folga_m, extras, recusas_extras,
                              {a.name for a in conversoes.values()}, largura_m)
        nome_maquina, largura = plano["maquina"], plano["largura_util_m"]
        chapa, margem_m, cliente = plano["mesa_m"], plano["margem_m"], plano["cliente"]
        folga_m = plano["folga_m"]
        resultado = {"maquina": nome_maquina, "largura_util_m": largura,
                     "mesa_m": chapa, "margem_m": margem_m, "folga_m": folga_m,
                     "folhas": [], "recusadas": [], "avisos": avisos_pendentes}

        for recusada in plano["recusadas"]:
            arquivo = pathlib.Path(recusada["arquivo"])
            logger("warn", f"'{arquivo.name}' ficou de fora: {recusada['motivo']}")
            resultado["recusadas"].append({"arquivo": arquivo.name,
                                           "motivo": recusada["motivo"]})
        if not plano["folhas"]:
            if guardar_originais:
                resultado["avisos"].extend(_guardar_recusadas(plano["recusadas"], pasta, logger))
            return resultado

        pecas = [folha["pecas"][posta[0]] for folha in plano["folhas"]
                 for posta in folha["postas"]]
        saida = pasta_de_saida(nome_maquina, pasta.parent)
        lote_id = f"{quando:%Y-%m-%d_%H-%M-%S}_{uuid.uuid4().hex[:8]}"
        avisos_concluidos = []
        with PublicacaoMontagem(saida) as publicacao:
            for folha in plano["folhas"]:
                categoria, do_material = folha["categoria"], folha["pecas"]
                postas, paginas = folha["postas"], folha["paginas"]
                comprimento, folha_m = folha["comprimento_m"], folha["folha_m"]
                area_pecas, area_folha = folha["area_pecas_m2"], folha["area_folha_m2"]
                tamanho, largura_folha = folha["tamanho"], folha["largura_m"]
                de_quantas = (f"  ·  parte {folha['parte']} de {folha['partes']}"
                              if folha["partes"] > 1 else "")
                titulo = (f"MONTAGEM  ·  {cliente or 'SEM CLIENTE NO NOME'}  ·  {categoria}  ·  "
                          f"{len(postas)} pecas  ·  {tamanho}{de_quantas}  ·  "
                          f"aproveitamento {area_pecas / area_folha * 100:.0f}%  ·  "
                          f"RIPAR A 100%, NAO REDIMENSIONAR")
                if chapa:
                    doc = desenhar_chapas(do_material, paginas, chapa, titulo, margem_m, folga_m)
                else:
                    doc = desenhar(do_material, postas, comprimento, largura_folha, titulo,
                                    margem_m, folga_m)
                # A folha PRONTA sai da pasta de entrada (ele, 05/10/2026). Era de
                # lá que a passada seguinte a lia como peça, e montava folha
                # dentro de folha.
                if chapa:
                    destino = saida / nome_da_folha(cliente, categoria, chapa[0], chapa[1],
                                                    len(postas), quando, len(paginas))
                else:
                    # O comprimento do NOME é o da folha que vai ser IMPRESSA, o
                    # mesmo que a página tem — e a largura também, que agora é a
                    # APARADA. É por eles que o m², a escolha de máquina e a baixa
                    # de estoque contam.
                    destino = saida / nome_da_folha(
                        cliente, categoria, largura_folha, folha_m, len(postas), quando,
                        parte=(folha["parte"], folha["partes"]))
                # deflate_images=False EXPL�?CITO, e não por padrão da biblioteca:
                # a arte sai da montagem com os mesmos bytes que entrou (regra dele,
                # 05/10/2026: *"a qualidade precisa ser 100% igual o cliente
                # entregou"*). Hoje o PyMuPDF já não mexe em imagem sem pedir, mas
                # um padrão que muda numa atualização reescreveria a arte de todo
                # mundo calado — e recompressão não se desfaz.

                # O JSON ao lado é o que impede a montagem de APAGAR a comprovação:
                # pro registro de produção a folha é UM arquivo entregue, e sem
                # isto as peças sumiriam do relatório do cliente.
                ficha = {
                    "lote_id": lote_id,
                    "originais": {do_material[posta[0]]["nome"]:
                                  plano["versoes"][do_material[posta[0]]["nome"]]
                                  for posta in postas},
                    "quando": quando.strftime("%Y-%m-%dT%H:%M:%S"),
                    "cliente": cliente, "maquina": nome_maquina, "categoria": categoria,
                    "folha_m": ([round(chapa[0], 3), round(chapa[1], 3)] if chapa
                                else [round(largura_folha, 3), round(folha_m, 3)]),
                    "parte": folha["parte"], "partes": folha["partes"],
                    "chapas": len(paginas) if chapa else None,
                    "area_folha_m2": round(area_folha, 3), "area_pecas_m2": round(area_pecas, 3),
                    "folga_m": folga_m, "margem_m": margem_m,
                    "pecas": [{
                        "numero": numero, "arquivo": do_material[i]["nome"],
                        "material_no_nome": do_material[i]["categoria"],
                        "material_impressao": do_material[i]["material_impressao"],
                        "pagina": do_material[i]["pagina"],
                        "copia": do_material[i]["copia"],
                        "quantidade": do_material[i]["quantidade"],
                        "dpi": do_material[i].get("dpi"),
                        "resolucao_estado": do_material[i].get("resolucao_estado", "nao_verificada"),
                        "resolucao_motivo": do_material[i].get("resolucao_motivo", ""),
                        # a medida REAL da peça na folha: largura do nome,
                        # comprimento pela proporção da arte
                        "medida_m": [round(do_material[i]["largura_m"], 3),
                                     round(do_material[i]["altura_m"], 3)],
                        # e o que o nome pedia, quando não é a mesma coisa —
                        # número deduzido nunca se passa por declarado. Confere os
                        # DOIS lados: a âncora é o maior, então quem anda é ora a
                        # altura, ora a largura
                        "medida_do_nome_m": (
                            [round(v, 3) for v in do_material[i]["nome_m"]]
                            if (abs(do_material[i]["nome_m"][0]
                                    - do_material[i]["largura_m"]) >= 0.001
                                or abs(do_material[i]["nome_m"][1]
                                       - do_material[i]["altura_m"]) >= 0.001) else None),
                        "posicao_m": [round(v, 3) for v in
                                      posicao_na_folha(posta, margem_m, 0.0 if chapa else None)],
                        "girada": girada,
                        "ajuste": do_material[i]["ajuste"]["acao"],
                        "fator": do_material[i]["ajuste"]["fator"],
                    } for numero, posta in enumerate(postas, start=1)
                       for i, girada in ((posta[0], posta[5]),)],
                }
                estimativa = tempo_impressao.estimar(nome_maquina, area_folha, passadas_docan)
                if estimativa is not None:
                    ficha["estimativa_impressao"] = estimativa
                    ficha["estimativa_impressao"]["base_area"] = "folha completa, incluindo espaços e cabeçalho"
                try:
                    destino = publicacao.salvar(doc, destino, ficha)
                finally:
                    doc.close()
                avisos_concluidos.append(
                    f"Montagem de {categoria}: {len(postas)} peças em {tamanho} "
                    f"({area_pecas / area_folha * 100:.0f}% de aproveitamento) — {destino.name}")
                resultado["folhas"].append({
                    "arquivo": destino, "categoria": categoria, "pecas": len(postas),
                    "comprimento_m": comprimento, "chapas": len(paginas) if chapa else None,
                    "aproveitamento": area_pecas / area_folha,
                    "cliente": cliente,
                    "estimativa_impressao": estimativa,
                })

            conferir_versoes(pasta, arquivos_trabalho, plano["versoes"])
            registro = None
            destinos = [folha["arquivo"].resolve() for folha in resultado["folhas"]]
            if guardar_originais:
                versoes_usadas = {peca["nome"]: plano["versoes"][peca["nome"]] for peca in pecas}
                registro = retomada.criar_registro(pasta, versoes_usadas, destinos, lote_id)
            try:
                publicacao.publicar()
            except BaseException:
                if registro is not None and not any(
                        destino.exists() or destino.with_suffix(".json").exists() for destino in destinos):
                    registro.unlink(missing_ok=True)
                raise
        for aviso in avisos_concluidos:
            logger("ok", aviso)
        if guardar_originais:
            resultado["avisos"].extend(retomada.retomar_arquivamento(pasta, _mover_para, logger))
            resultado["avisos"].extend(_guardar_recusadas(plano["recusadas"], pasta, logger))
        resultado["avisos"] = list(dict.fromkeys(resultado["avisos"]))
        return resultado


def prever_pasta(pasta, nome_maquina=None, config=None, maquinas=None,
                 raiz_clientes=None, arquivos=None, folga_m=None, passadas_docan=None,
                 largura_m=None):
    """
    A PRÉVIA, em números prontos pra tela: como a folha vai ficar e qual
    a margem de erro de cada peça.

    Pedido dele de 05/10/2026: *"antes de gerar quero que me passe os
    dados como um aviso de como vai ficar depois de montado, mostrando a
    margem de erro"*, e depois *"ele vai pegar os arquivos que joguei na
    pasta, calcular e passar os dados na tela"*.

    Cada item traz o que o NOME pede, o que vai SAIR e a diferença, em
    milímetros. A do MAIOR LADO é zero por construção — é a âncora —, e
    ela sai escrita justamente por isso: é a prova de que a regra está
    valendo, no documento que ele lê antes de mandar imprimir. 'ancorado'
    diz qual dos dois lados é o maior nesta peça.

    Nada é escrito nem movido: isto só olha.
    """
    plano = planejar_pasta(pasta, nome_maquina, config, maquinas, raiz_clientes,
                          arquivos, folga_m, largura_m=largura_m)
    previa = {"pasta": plano["pasta"], "maquina": plano["maquina"],
              "passadas_docan": passadas_docan,
              "saida": pasta_de_saida(plano["maquina"], plano["pasta"].parent),
               "cliente": plano["cliente"], "folhas": [], "avisos": [],
              "folga_m": plano["folga_m"], "largura_m": plano["largura_util_m"],
              "versoes": plano["versoes"],
               "largura_util_m": plano["largura_util_m"],
               "metragem_rolo": 0.0, "aproveitamento_rolo": 0.0,
              "recusadas": [{"arquivo": pathlib.Path(r["arquivo"]).name,
                             "motivo": r["motivo"]} for r in plano["recusadas"]],
              # o que só entra depois de passar pelo Illustrator/Photoshop:
              # a prévia não converte nada, então ele precisa ver que estão ali
               "a_converter": [a.name for a in a_converter(plano["pasta"], arquivos)],
              "pior_diferenca_mm": 0.0, "pior_resolucao": None}

    for folha in plano["folhas"]:
        itens = []
        for numero, posta in enumerate(folha["postas"], start=1):
            peca = folha["pecas"][posta[0]]
            pede_l, pede_a = peca["nome_m"]
            sai_l, sai_a = peca["largura_m"], peca["altura_m"]
            # a ÂNCORA é o maior lado: ele fecha cravado, e o que anda é o
            # outro. Os dois saem escritos, porque qual deles é o maior
            # muda de peça pra peça
            ancorado = "largura" if pede_l >= pede_a else "altura"
            diferenca = ((sai_l - pede_l) if ancorado == "altura"
                         else (sai_a - pede_a)) * 1000
            previa["pior_diferenca_mm"] = max(previa["pior_diferenca_mm"],
                                              abs(diferenca))
            dpi = peca.get("dpi")
            qualidade = ("nao_verificada" if peca.get("resolucao_estado") == "nao_verificada"
                         else qualidade_da_resolucao(dpi))
            avisos = []
            if peca["material_impressao"] != peca["categoria"]:
                avisos.append(f"Impressão em {peca['material_impressao']}; "
                              f"material final no nome: {peca['categoria']}.")
            if abs(diferenca) >= 0.5:
                avisos.append(f"O outro lado difere {diferenca:+.1f} mm do nome; a proporção foi preservada.")
            if qualidade in ("atencao", "aviso"):
                avisos.append(f"Resolução efetiva {dpi:.0f} dpi: confira a distância de visualização.")
            if qualidade == "nao_verificada":
                avisos.append(peca.get("resolucao_motivo") or "A resolução não pôde ser verificada.")
            if (contem_palavra(peca["nome"].upper(), "DECORFLEX")
                    and plano["maquina"] != "DOCAN R5200"):
                avisos.append("Para Decorflex a impressora indicada é DOCAN R5200; confira o destino selecionado.")
            estado = ("nao_verificada" if qualidade == "nao_verificada" else
                      "aviso" if qualidade == "aviso" else "atencao" if avisos else "ok")
            if qualidade == "aviso":
                previa["pior_resolucao"] = (
                    dpi if previa["pior_resolucao"] is None
                    else min(previa["pior_resolucao"], dpi))
            itens.append({
                "numero": numero, "arquivo": peca["nome"],
                "material_no_nome": peca["categoria"],
                "material_impressao": peca["material_impressao"],
                "nome_completo": peca["nome"], "rotulo": _texto_do_rotulo(peca, numero),
                "pagina": peca["pagina"], "copia": peca["copia"],
                "quantidade": peca["quantidade"],
                "posicao_m": list(posicao_na_folha(
                    posta, plano["margem_m"], 0.0 if plano["mesa_m"] else None))
                    + [posta[3], posta[4]],
                "avisos": avisos, "estado": estado,
                "nome_m": (pede_l, pede_a), "medida_m": (sai_l, sai_a),
                "ancorado": ancorado,
                "erro_ancora_mm": ((sai_l - pede_l) if ancorado == "largura"
                                   else (sai_a - pede_a)) * 1000,
                "diferenca_mm": diferenca,
                "dpi": dpi, "qualidade": qualidade,
                "distancia_limpa_m": None if dpi is None else distancia_limpa_m(dpi),
                "girada": posta[5], "ajuste": peca["ajuste"]["acao"],
                "fator": peca["ajuste"]["fator"],
            })
            for aviso in avisos:
                if aviso not in previa["avisos"]:
                    previa["avisos"].append(aviso)
        comprimento_rolo = 0.0 if folha["chapas"] else folha["folha_m"]
        # O PDF pode fechar na largura realmente ocupada, mas o rolo
        # continua tendo a largura escolhida para a máquina. São métricas
        # diferentes: a primeira mede o aproveitamento da folha aparada;
        # a segunda mede o material efetivamente consumido.
        largura_rolo = plano["largura_util_m"] if not folha["chapas"] else folha["largura_m"]
        area_rolo = largura_rolo * comprimento_rolo
        previa["folhas"].append({
            "categoria": folha["categoria"], "tamanho": folha["tamanho"],
            "largura_m": folha["largura_m"], "folha_m": folha["folha_m"],
            "chapas": folha["chapas"], "pecas": len(folha["postas"]),
            "parte": folha["parte"], "partes": folha["partes"],
            "aproveitamento": folha["aproveitamento"],
            "area_pecas_m2": folha["area_pecas_m2"],
            "area_folha_m2": folha["area_folha_m2"],
            "metragem_rolo": comprimento_rolo,
            "largura_rolo_m": largura_rolo,
            "aproveitamento_rolo": folha["area_pecas_m2"] / area_rolo if area_rolo else 0.0,
            "sobra_rolo_m2": max(0.0, area_rolo - folha["area_pecas_m2"]),
            "consumo_rolo_estimado": True,
            "estimativa_impressao": tempo_impressao.estimar(
                plano["maquina"], folha["area_folha_m2"], passadas_docan),
            "itens": itens,
        })
        previa["metragem_rolo"] += comprimento_rolo
    area_rolo = sum(f.get("largura_rolo_m", f["largura_m"]) * f["metragem_rolo"]
                    for f in previa["folhas"])
    area_pecas = sum(f["area_pecas_m2"] for f in previa["folhas"] if not f["chapas"])
    previa["aproveitamento_rolo"] = area_pecas / area_rolo if area_rolo else 0.0
    previa["sobra_rolo_m2"] = max(0.0, area_rolo - area_pecas)
    previa["consumo_rolo_estimado"] = True
    return previa


def resumo_da_previa(previa):
    """
    A prévia em poucas linhas, pro aviso do Windows — que não cabe tabela.

    Curto de propósito: quem quer a tabela abre a tela. Aqui vale o que
    decide se ele precisa olhar agora.
    """
    linhas = [f"{previa['maquina']}"
              + (f" · {previa['cliente']}" if previa["cliente"] else "")]
    for folha in previa["folhas"]:
        qual = (f" (parte {folha['parte']} de {folha['partes']})"
                if folha["partes"] > 1 else "")
        linhas.append(f"{folha['categoria']}: {folha['pecas']} peças em "
                      f"{folha['tamanho']}{qual} ({folha['aproveitamento'] * 100:.0f}%)")
        if folha.get("estimativa_impressao"):
            linhas.append(tempo_impressao.texto(folha["estimativa_impressao"]))
    if previa["folhas"]:
        pior = previa["pior_diferenca_mm"]
        linhas.append("maior lado bate o nome; diferença no outro lado até "
                      f"{pior:.0f} mm fora do nome" if pior >= 0.5
                      else "os dois lados batem o nome")
    if previa["pior_resolucao"] is not None:
        # a resolução vem ANTES das recusadas: recusada ele vê na pasta
        # _conferir, mas arte de pouco pixel entra calada e só aparece
        # impressa
        linhas.append(
            f"ATENÇÃO: peça com {previa['pior_resolucao']:.0f} dpi — só fica "
            f"limpa a {distancia_limpa_m(previa['pior_resolucao']):.1f} m")
    if previa["recusadas"]:
        linhas.append(f"{len(previa['recusadas'])} ficaram de fora — veja _conferir")
    for aviso in previa.get("avisos", []):
        if "resolução" in aviso.lower() or "Decorflex" in aviso:
            linhas.append("ATENÇÃO: " + aviso)
    return "\n".join(linhas)


def montar_todas(raiz=None, config=None, maquinas=None, logger=None, quando=None):
    """Uma passada por todas as pastas de montagem. Devolve [resultado por pasta]."""
    resultados = []
    for nome_maquina in maquinas_que_montam(maquinas):
        pasta = pasta_da_maquina(nome_maquina, raiz)
        if not pasta.is_dir():
            continue
        if not any(a.is_file() and a.suffix.lower() in EXTENSOES_DE_ARTE
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
        if not arquivo.is_file() or arquivo.suffix.lower() not in EXTENSOES_DE_ARTE:
            continue
        tem_o_que_montar = True
        try:
            if datetime.datetime.fromtimestamp(arquivo.stat().st_mtime) > limite:
                return False   # ainda chegando
        except OSError:
            return False
    return tem_o_que_montar


def _avisar_o_que_vai_sair(pasta, nome_maquina, config, maquinas, logger,
                           notificar=None):
    """
    O aviso do Windows com a prévia, ANTES de a folha ser gerada.

    Pedido dele de 05/10/2026: *"eu jogo os arquivos na pasta,
    automaticamente já vai ser montado e salvo em um PDF; antes de gerar,
    quero que me passe os dados como um aviso de como vai ficar depois de
    montado, mostrando a margem de erro"*. Na tela ele vê a tabela
    inteira; aqui, que é notificação, vai o que decide se ele precisa
    olhar agora.

    Nunca derruba a montagem: avisar é conforto, montar é o trabalho.
    E registra a falha no log — `except` calado aqui esconderia um aviso
    que parou de sair, que é o pior resultado possível num alarme.
    """
    try:
        previa = prever_pasta(pasta, nome_maquina, config, maquinas)
        if not previa["folhas"]:
            return None
        if notificar is None:
            from monitor_onedrive import notificar_windows
            notificar = notificar_windows
        texto = resumo_da_previa(previa)
        notificar(texto, titulo="Montagem de arte")
        logger("info", f"Montagem da {nome_maquina}: avisei o que vai sair")
        return texto
    except Exception as erro:   # noqa: BLE001 - ver docstring
        logger("warn", f"não consegui avisar a prévia da montagem: "
                       f"{type(erro).__name__}: {erro}")
        return None


def conferir(raiz=None, config=None, maquinas=None, logger=None, agora=None, minutos=None,
             automatico=True):
    """
    Uma passada pelas pastas de montagem: monta as que pararam de
    receber arquivo. Devolve [resultado por pasta montada].

    Nunca levanta por pasta: uma pasta com arte problemática não pode
    impedir a outra de montar.
    """
    logger = logger or (lambda nivel, mensagem: None)
    if not automatico:
        return []
    feitas = []
    for nome_maquina in maquinas_que_montam(maquinas):
        pasta = pasta_da_maquina(nome_maquina, raiz)
        if not pasta_parada(pasta, minutos, agora):
            continue
        try:
            _avisar_o_que_vai_sair(pasta, nome_maquina, config, maquinas, logger)
            feitas.append(montar_pasta(pasta, nome_maquina, config, maquinas, logger,
                                       quando=agora))
        except Exception as erro:   # noqa: BLE001 - ver docstring
            logger("warn", f"a montagem de '{pasta.name}' parou: "
                           f"{type(erro).__name__}: {erro}")
    return feitas

