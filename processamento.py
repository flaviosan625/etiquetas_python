"""
Núcleo do processamento: lê os PDFs da pasta de entrada, separa por
categoria de material, monta as etiquetas em folhas A4, gera o PDF
unificado, o log CSV e a Ordem de Serviço.

Principais diferenças em relação à versão original de main.py:
  - As categorias/medidas de material vêm do config.json (editável pela
    tela de configurações), não mais fixas no código. Isso permite
    cadastrar rolos/chapas de medidas novas, ou categorias de material
    inteiramente novas, sem editar código.
  - Os erros de digitação de unidade (ex: "XM" -> "CM") também vêm do
    config.json, então dá pra cadastrar novos padrões conforme forem
    aparecendo.
  - Cada etapa de salvamento (PDF individual, unificado, log, OS) é
    protegida por try/except: se uma falhar (por exemplo, um arquivo
    aberto no Adobe Reader travando a escrita), as outras ainda são
    tentadas, e o motivo do erro fica registrado no log — em vez do
    programa simplesmente travar e perder tudo.
  - O nome do cliente é "sanitizado" antes de virar nome de arquivo,
    evitando erro se alguém digitar um caractere que o Windows não
    aceita em nome de arquivo (barra, dois-pontos, etc.).
  - Cada execução salva em uma pasta com data/hora
    (etiquetas_geradas/CLIENTE_20260817_143000/), então rodar de novo
    pro mesmo cliente não sobrescreve o resultado anterior.
  - Nunca deixa uma seção "sumir" do PDF unificado por ter sido
    esquecida na lista de ordem do config.json — qualquer categoria com
    arquivos aparece, mesmo que só no final.
  - Em vez de só usar print(), aceita um callback on_log(nivel, msg) e
    on_progress(atual, total), para que a interface gráfica possa
    mostrar tudo em tempo real. Sem callback, cai de volta pra print()
    (usado no modo linha de comando).
"""
import os
import math
import pathlib
import re
from datetime import datetime

import pymupdf

from conversao_adobe import CONVERSORES_POR_EXTENSAO, converter_se_necessario
from dimensoes import (
    contem_palavra, extrair_dimensoes, calcular_desperdicio_item, extrair_quantidade,
    identificar_categoria, identificar_categoria_extra, identificar_variante, formatar_variante,
    calcular_desperdicio_chapa_grande, dimensao_da_arte, nome_sem_prefixo_reconhecido, remover_palavra,
    FATORES_UNIDADE,
)
from estado_pedido import carregar_estado, nomes_ja_processados, salvar_estado
from pdf_layout import iniciar_pagina_com_banner, numerar_paginas_a_partir_de, estampar_conferencia_local
from relatorios import salvar_log, gerar_os, salvar_dados_os
from utils import nome_cliente_da_pasta, remover_acentos, sanitizar_nome_arquivo

LARGURA_A4 = 595.27
ALTURA_A4 = 841.89

# A arte de cada etiqueta é rasterizada (em vez de embutida como vetor)
# pra controlar o tamanho do arquivo final — PDFs de origem prontos pra
# impressão em grande formato costumam ter imagens embutidas em
# resolução bem mais alta do que qualquer coisa precisa numa folha A4
# ou numa tela de celular. 150 DPI já é nitido o bastante pra impressão
# de referência nesse tamanho, e reduz drasticamente o peso do arquivo
# final (que também precisa ser leve o bastante pra mandar por
# WhatsApp).
DPI_ETIQUETA = 150
QUALIDADE_JPG_ETIQUETA = 78

# Formatos que o PyMuPDF abre de verdade nesse ambiente (testado
# diretamente, 2026-08-29) — PDF sempre foi suportado; ".AI" entra
# porque um arquivo Illustrator exportado com "Compatibilidade PDF"
# (padrão do programa) é um PDF de verdade por dentro, então abre igual;
# PNG/JPG são imagem crua, o PyMuPDF trata como documento de 1 página.
EXTENSOES_SUPORTADAS = (".pdf", ".ai", ".png", ".jpg", ".jpeg")

# EPS/PSD/TIF não entram em EXTENSOES_SUPORTADAS acima — têm conversão
# automática pra PDF via Illustrator/Photoshop (ver conversao_adobe.py)
# antes de chegar no resto do processamento. TIF em especial: mesmo
# quando o PyMuPDF TECNICAMENTE consegue abrir um TIF, arte de
# impressão nesse formato costuma vir gigante (visto na prática,
# 2026-08-31: arquivo de 3,1GB não terminou de abrir nem depois de
# vários minutos) — o Photoshop dá conta bem melhor desse tamanho.
# CDR não tem conversão nenhuma (decisão do usuário, 2026-08-29: "não
# precisa mexer") — só avisa que foi visto, não lido.
EXTENSOES_RECONHECIDAS_SEM_SUPORTE = (".cdr",)

# Onde vai o arquivo original depois de convertido com sucesso (ver
# conversao_adobe.converter_se_necessario) — nunca apagado, só sai da
# vista pra não tentar converter de novo na rodada seguinte.
NOME_SUBPASTA_ORIGINAIS_CONVERTIDOS = "_originais_convertidos"

# Onde fica a cópia com resolução reduzida de um PDF grande demais pra
# processar direto (ver _obter_pdf_reduzido) — o original NUNCA entra
# aqui nem é tocado, só a cópia derivada.
NOME_SUBPASTA_REDUZIDOS = "_reduzidos_para_processar"

_PREFIXOS_CONSOLE = {"ok": "✅", "warn": "⚠️", "err": "❌", "info": "ℹ️"}


class _Logger:
    """
    Centraliza o log: manda pro callback da interface gráfica (se
    houver), imprime no console (se não houver), e guarda as linhas
    referentes a um arquivo específico para o CSV final.
    """

    def __init__(self, on_log=None):
        self.on_log = on_log
        self.registro = []

    def emitir(self, nivel, mensagem, arquivo=None, status_csv=None):
        if self.on_log:
            self.on_log(nivel, mensagem)
        else:
            print(f"{_PREFIXOS_CONSOLE.get(nivel, '')} {mensagem}")

        if arquivo is not None:
            self.registro.append({
                "arquivo": arquivo,
                "status": status_csv or nivel.upper(),
                "detalhe": mensagem,
            })


def _novo_estado_categoria():
    return {
        "pdf_saida": pymupdf.open(),
        "pagina_atual": None,
        "posicao_na_pagina": 0,
        # 'contem_arquivos': tem CONSUMO de material a reportar (área/
        # desperdício), inclusive quando é só categoria extra de material
        # composto (ver 'categoria_extra' mais abaixo) — pode ser True
        # sem nenhuma etiqueta própria. 'tem_etiqueta': tem PÁGINA de
        # verdade em 'pdf_saida' — só essa controla inserir no checklist/
        # banner; inserir um pdf_saida vazio (sem nenhuma página) trava o
        # PyMuPDF com "malformed page tree".
        "contem_arquivos": False,
        "tem_etiqueta": False,
        "total_etiquetas": 0,
        "area_total_m2": 0.0,
        "area_desperdicio_m2": 0.0,
        "comprimento_rolo_usado_m": 0.0,
        "itens_fora_do_rolo": [],
        "chapas_extras": 0,  # chapas estimadas pras peças maiores que uma chapa (calcular_desperdicio_chapa_grande)
        "sobra_rodape": [],  # espaço vertical que sobrou no rodapé de cada etiqueta, na ordem em que foram montadas
        "posicoes_etiquetas": [],  # (índice_da_página, y_inicial, y_final) de cada etiqueta, na ordem em que foram montadas
        "caixa_contagem_banner": None,  # retângulo reservado no banner pra escrever "N etiquetas" depois
    }


# Comparado sem acento (ver utils.remover_acentos), então cobre
# "reposição"/"reposicao"/"reposiçao" e "refação"/"refacao"/"refaçao"
# com uma palavra só cada — não precisa listar cada combinação de
# acento. "REF" sozinho também conta (abreviação comum de "refação"),
# mas cuidado: é curto o bastante pra colidir com um nome de arquivo
# real que use "REF" com outro sentido (ex: imagem de referência do
# cliente) — se isso acontecer na prática, é só tirar da lista.
_PALAVRAS_REPOSICAO = ("REPOSICAO", "REFACAO", "REF")


def _eh_reposicao(nome_arquivo_upper):
    """
    Marca um arquivo como reposição de material estragado quando o
    próprio nome (renomeado manualmente pelo usuário antes de jogar de
    novo na pasta de entrada) contém uma das palavras de
    _PALAVRAS_REPOSICAO. Não precisa de tela de confirmação nem de
    estado à parte: o nome mudado já é o suficiente pra passar pelo
    filtro de "já processado" como se fosse novo (ver 'arquivos_novos'
    em processar_etiquetas), e o próprio nome fica registrado no
    checklist/OS/estado como prova de que essa etiqueta foi refeita.
    """
    nome_sem_acento = remover_acentos(nome_arquivo_upper)
    return any(contem_palavra(nome_sem_acento, palavra) for palavra in _PALAVRAS_REPOSICAO)


# Extensão original -> conversor de redução certo (ver conversao_adobe):
# PDF pede a resolução já na abertura; imagem crua (PNG/JPG) precisa
# abrir no tamanho nativo e reduzir depois (Document.ResizeImage) —
# são caminhos diferentes no Photoshop, por isso dois conversores.
# Pedido do usuário (2026-09-01): "preciso adicionar a extensão png,
# preciso que leia esse formato também via Photoshop" — mesmo caminho
# de resgate por falta de memória já usado pro PDF, agora também pra
# PNG/JPG.
def _reduzir_conforme_extensao(caminho_original, caminho_reduzido, extensao):
    from conversao_adobe import reduzir_pdf_grande, reduzir_imagem_grande
    if extensao == ".pdf":
        reduzir_pdf_grande(caminho_original, caminho_reduzido)
    else:
        reduzir_imagem_grande(caminho_original, caminho_reduzido)


def _obter_pdf_reduzido(pasta_entrada, arquivo, logger, reduzir=None):
    """
    Cria (ou reaproveita, se uma tentativa anterior nessa mesma pasta
    já criou) uma cópia de 'arquivo' com resolução reduzida, numa
    subpasta separada (NOME_SUBPASTA_REDUZIDOS) — nunca mexe no
    original. A cópia é sempre um PDF (mesmo se o original for PNG/JPG
    — ver _reduzir_conforme_extensao), então o nome do arquivo na
    cópia troca de extensão pra ".pdf". Devolve o caminho completo da
    cópia reduzida, ou None se não foi possível (Photoshop indisponível
    ou a própria redução falhou).

    'reduzir' (opcional) sobrescreve o conversor escolhido por
    _reduzir_conforme_extensao — só existe pra teste automatizado poder
    simular sem abrir o Photoshop de verdade.
    """
    from conversao_adobe import COM_DISPONIVEL
    if reduzir is None:
        extensao = pathlib.Path(arquivo).suffix.lower()
        reduzir = lambda origem, destino: _reduzir_conforme_extensao(origem, destino, extensao)
    if not COM_DISPONIVEL:
        return None

    pasta_reduzidos = pathlib.Path(pasta_entrada).resolve() / NOME_SUBPASTA_REDUZIDOS
    caminho_original = pathlib.Path(pasta_entrada).resolve() / arquivo
    nome_reduzido = pathlib.Path(arquivo).stem + ".pdf"
    caminho_reduzido = pasta_reduzidos / nome_reduzido
    if caminho_reduzido.exists():
        return str(caminho_reduzido)

    try:
        pasta_reduzidos.mkdir(parents=True, exist_ok=True)
        reduzir(str(caminho_original), str(caminho_reduzido))
    except Exception as e:
        logger.emitir(
            "err", f"'{arquivo}': não foi possível reduzir a resolução pra processar: {e}",
            arquivo=arquivo, status_csv="ERRO - REDUCAO FALHOU",
        )
        return None
    return str(caminho_reduzido)


def _nome_padronizado(nome_original, quantidade, categoria, dimensao, typos_unidade, nome_cliente_seguro):
    """
    Nome de arquivo padrão da oficina (pedido do usuário, 2026-08-29):
    sempre "{QTD} UN {MATERIAL} {LARGURAxALTURA}{UNIDADE} {CLIENTE}
    {resto do nome original}" — quantidade, material e cliente sempre
    visíveis de cara, sem precisar abrir o arquivo pra saber o que é.
    O cliente já é conhecido nesse ponto (quem processa digita antes de
    gerar as etiquetas, não precisa adivinhar do nome do arquivo). O
    resto do nome original (descrição do projeto, marca de reposição
    etc.) é mantido depois — nada é excluído, só a quantidade/medida
    que já existiam soltas no nome saem de onde estavam (senão
    duplicaria a informação, já que elas voltam formatadas no início).

    'dimensao' pode ser None (nem o nome nem a arte tinham medida
    reconhecível) — nesse caso o bloco de medida simplesmente não
    entra no nome. Quando a medida veio da arte (não do nome), o nome
    ganha "(medida pela arte)" — sinaliza uma medida menos certa que
    uma escrita à mão pelo cliente/produção, fácil de achar depois se
    precisar conferir.

    O nome do material e do cliente não repetem no "resto" (ex: nome
    original "LONA IMPRESSA..." já tem a palavra, que volta formatada
    no prefixo) — tirados por palavra inteira, igual
    dimensoes.contem_palavra. Isso também cobre o caso de rodar duas
    vezes em cima do mesmo arquivo (ex: pasta de entrada reprocessada
    depois de já ter sido padronizada): a marca "(medida pela arte)"
    de uma rodada anterior e o material/cliente repetidos saem, o nome
    final não fica empilhando prefixo em cima de prefixo.
    """
    resto = nome_sem_prefixo_reconhecido(nome_original, typos_unidade)
    extensao = pathlib.Path(resto).suffix or ".pdf"
    if extensao and resto.lower().endswith(extensao.lower()):
        resto = resto[: -len(extensao)]

    for termo in (categoria, nome_cliente_seguro):
        resto = remover_palavra(resto, termo)
    resto = re.sub(re.escape("(medida pela arte)"), '', resto, flags=re.IGNORECASE)
    resto = re.sub(r'[\s._,\-]{2,}', ' ', resto).strip(" ._-")

    prefixo = f"{quantidade} UN {categoria}"
    if dimensao is not None:
        fator = FATORES_UNIDADE.get(dimensao["unidade_usada"], 1.0)
        largura_na_unidade = dimensao["largura_m"] / fator
        altura_na_unidade = dimensao["altura_m"] / fator
        prefixo += f" {largura_na_unidade:.2f}x{altura_na_unidade:.2f}{dimensao['unidade_usada']}"
        if dimensao.get("origem") == "arte":
            prefixo += " (medida pela arte)"
    prefixo += f" {nome_cliente_seguro.upper()}"

    if resto:
        return f"{prefixo} {resto}{extensao}"
    return f"{prefixo}{extensao}"


def _renomear_para_padrao(pasta_entrada, nome_antigo, nome_novo, logger):
    """
    Renomeia o arquivo de origem, direto na pasta de entrada, pro nome
    padronizado — pedido do usuário (2026-08-29): quer os arquivos já
    organizados na origem, não só a etiqueta/OS gerada depois.

    Nunca sobrescreve nada: se o nome novo já existe (colidiu com
    outro arquivo), acrescenta um sufixo numérico. Se o rename falhar
    por qualquer motivo (permissão, arquivo aberto em outro programa),
    avisa e segue processando com o nome ORIGINAL — nunca trava a
    rodada inteira por causa disso.

    Retorna o nome final do arquivo (novo, ou o original se não deu
    pra renomear).
    """
    if nome_novo == nome_antigo:
        return nome_antigo

    pasta = pathlib.Path(pasta_entrada)
    caminho_antigo = pasta / nome_antigo
    caminho_novo = pasta / nome_novo

    if caminho_novo.exists():
        base = caminho_novo.stem
        extensao = caminho_novo.suffix
        contador = 2
        while caminho_novo.exists():
            caminho_novo = pasta / f"{base} ({contador}){extensao}"
            contador += 1

    try:
        caminho_antigo.rename(caminho_novo)
    except OSError as e:
        logger.emitir(
            "warn",
            f"Não foi possível renomear '{nome_antigo}' pro padrão: {e}. Seguindo com o nome original.",
            arquivo=nome_antigo, status_csv="AVISO - RENOME FALHOU",
        )
        return nome_antigo

    logger.emitir("info", f"Renomeado pro padrão: {caminho_novo.name}")
    return caminho_novo.name


def _acumular_consumo_categoria(cat_info, info_material, dimensao, quantidade):
    """
    Soma o consumo de UMA peça (medida x quantidade) nos totais de uma
    categoria — área, desperdício, comprimento de rolo usado ou chapas
    extras. Reaproveitado tanto pra categoria principal do item quanto
    pra categoria extra de material composto (ex: "PS ADESIVADO" conta
    pra PS e pra ADESIVO, mesma medida — ver dimensoes.identificar_
    categoria_extra) — cada categoria usa sua própria largura de
    rolo/chapa, então a mesma peça pode caber numa e não na outra.

    Retorna um dict com 'resultado_corte' (quando a peça coube no
    rolo/chapa normal) ou 'estimativa_chapa_grande' (quando não coube
    e é chapa — estimativa por grade) — os dois None quando não coube
    e é rolo (peça mais larga que o rolo, sem estimativa possível).
    Quem chama decide o texto de log a partir disso.
    """
    cat_info["area_total_m2"] += dimensao["area_m2"] * quantidade
    largura_m = info_material["largura_cm"] / 100
    resultado_corte = calcular_desperdicio_item(dimensao, largura_m)
    if resultado_corte:
        cat_info["area_desperdicio_m2"] += resultado_corte["desperdicio_m2"] * quantidade
        cat_info["comprimento_rolo_usado_m"] += resultado_corte["peca_comprimento_m"] * quantidade
        return {"resultado_corte": resultado_corte, "estimativa_chapa_grande": None}

    if info_material["tipo"] == "chapa":
        # rolo tem comprimento livre (sempre cabe na área de impressão),
        # então essa estimativa por grade só faz sentido pra chapa, que
        # tem largura E comprimento fixos
        comprimento_chapa_m = info_material["comprimento_cm"] / 100
        estimativa = calcular_desperdicio_chapa_grande(dimensao, largura_m, comprimento_chapa_m)
        cat_info["area_desperdicio_m2"] += estimativa["desperdicio_m2"] * quantidade
        cat_info["chapas_extras"] += estimativa["total_chapas"] * quantidade
        return {"resultado_corte": None, "estimativa_chapa_grande": estimativa}

    return {"resultado_corte": None, "estimativa_chapa_grande": None}


def processar_etiquetas(pasta_entrada, nome_cliente, nome_gerente, nome_produtor,
                         config, pasta_saida_base="etiquetas_geradas",
                         on_log=None, on_progress=None, pasta_saida_existente=None):
    """
    Processa todos os PDFs de 'pasta_entrada' e gera os arquivos de
    saída. Retorna um dicionário com os caminhos gerados em caso de
    sucesso (mesmo que parcial), ou None se nem foi possível começar
    (pasta não encontrada, nenhum PDF, cliente inválido, etc.).

    'pasta_saida_existente' liga o modo atualização: em vez de criar
    uma pasta nova, reaproveita uma pasta de cliente já existente,
    reconhece pelo nome do arquivo o que já foi processado nela antes
    (estado_pedido.json) e ignora — não importa se a pasta de entrada
    for jogada inteira de novo, misturada com o que já foi mandado.
    Só o que é realmente novo vira etiqueta, ganha o selo "NOVO" (ou
    "REPOSIÇÃO", ver '_eh_reposicao') e entra nos totais que alimentam
    a baixa de estoque. Desde 2026-09-02 (pedido do usuário — antes um
    checklist por pedido virava vários arquivos versionados, V2, V3...,
    e ele queria só UM pra mandar pra produção), o checklist passou a
    se comportar como a OS: um documento só por pedido, que cada rodada
    ACRESCENTA página no final (nunca reabre/reordena o que já existia
    — o que já foi impresso e marcado à caneta na produção continua
    exatamente como estava, só entra página nova depois). Os selos
    NOVO/REPOSIÇÃO em cada etiqueta continuam sendo o jeito de saber
    visualmente o que foi acrescentado em qual rodada.
    """
    logger = _Logger(on_log)

    materiais = config["materiais"]
    categorias = list(materiais.keys())
    sinonimos_categoria = config.get("sinonimos_categoria", {})
    typos_unidade = config.get("typos_unidade", {})
    materiais_compostos = config.get("materiais_compostos", {})

    ordem_configurada = [c for c in config.get("ordem_unificado", []) if c in materiais]
    ordem_unificado = ordem_configurada + [c for c in categorias if c not in ordem_configurada]

    nome_cliente_seguro = sanitizar_nome_arquivo((nome_cliente or "").strip())
    if not (nome_cliente or "").strip():
        logger.emitir("err", "Nome do cliente vazio.")
        return None

    try:
        nomes_pasta = os.listdir(pasta_entrada)
    except FileNotFoundError:
        logger.emitir("err", f"A pasta '{pasta_entrada}' não foi encontrada.")
        return None
    except PermissionError:
        logger.emitir("err", f"Sem permissão para acessar a pasta '{pasta_entrada}'.")
        return None
    except OSError as e:
        logger.emitir("err", f"Não foi possível ler a pasta '{pasta_entrada}': {e}")
        return None

    arquivos_arte = [f for f in nomes_pasta if f.lower().endswith(EXTENSOES_SUPORTADAS)]

    # EPS/PSD não abrem direto no PyMuPDF nesse ambiente, mas o
    # Illustrator/Photoshop já instalados na máquina convertem — cada um
    # vira um PDF novo na própria pasta de entrada (entra na lista dessa
    # mesma rodada) e o original vai pra NOME_SUBPASTA_ORIGINAIS_
    # CONVERTIDOS (nunca apagado, só sai da vista pra não tentar
    # converter nele de novo na rodada seguinte).
    # Arquivo que precisava de conversão (EPS/PSD/TIF) mas falhou nunca
    # chega a entrar em 'arquivos_arte' (só o PDF convertido entraria,
    # e não existe) — sem isso registrado à parte, a regra de
    # reconciliação de quantidade lá embaixo não tem como saber que
    # esse arquivo devia ter virado etiqueta e não virou (bug real de
    # produção, 2026-09-01: conversão de TIF falhou por "CoInitialize
    # não foi chamado" — ver conversao_adobe._garantir_com_iniciado —
    # e a OS/Checklist saíram "completos" com 1 item a menos, sem
    # ninguém perceber).
    arquivos_com_falha_conversao = []
    for nome in nomes_pasta:
        if pathlib.Path(nome).suffix.lower() in CONVERSORES_POR_EXTENSAO:
            pasta_originais = pathlib.Path(pasta_entrada) / NOME_SUBPASTA_ORIGINAIS_CONVERTIDOS
            pdf_gerado = converter_se_necessario(pasta_entrada, nome, pasta_originais, logger.emitir)
            if pdf_gerado:
                arquivos_arte.append(pdf_gerado)
            else:
                arquivos_com_falha_conversao.append(nome)

    for nome in nomes_pasta:
        if nome.lower().endswith(EXTENSOES_RECONHECIDAS_SEM_SUPORTE):
            extensao = pathlib.Path(nome).suffix.upper()
            logger.emitir(
                "warn",
                f"'{nome}': formato {extensao} reconhecido, mas ainda não suportado — não foi lido. "
                f"Exporte pra PDF (ou AI com compatibilidade PDF) antes de colocar na pasta de entrada.",
                arquivo=nome, status_csv=f"AVISO - FORMATO {extensao} NAO SUPORTADO",
            )

    if not arquivos_arte:
        logger.emitir("err", f"Nenhum arquivo suportado (PDF/AI/PNG/JPG) encontrado na pasta '{pasta_entrada}'.")
        return None

    modo_atualizacao = pasta_saida_existente is not None
    itens_anteriores = []
    arquivos_ignorados = 0
    if modo_atualizacao:
        pasta_saida = pathlib.Path(pasta_saida_existente)
        # Sempre o nome JÁ USADO nessa pasta (o mesmo que já está no nome
        # dela), nunca o que foi digitado nessa rodada — sem isso, digitar
        # "SUPERBET" numa rodada e "SUPER BET" (com espaço) na seguinte
        # faz OS e checklist se PARTIREM em dois arquivos com nomes
        # diferentes, cada um só com metade do pedido (bug real visto em
        # produção, 2026-08-28 — a OS parou de ser um documento só). A
        # pasta em si já foi resolvida ignorando diferença de espaço (ver
        # estado_pedido.localizar_pastas_cliente); o nome usado pra
        # arquivo/conteúdo precisa seguir a MESMA decisão.
        nome_cliente_seguro = nome_cliente_da_pasta(pasta_saida.name)
        itens_anteriores = carregar_estado(pasta_saida, config)
        nomes_conhecidos = nomes_ja_processados(itens_anteriores)

        arquivos_novos = []
        for arquivo in arquivos_arte:
            if arquivo in nomes_conhecidos:
                arquivos_ignorados += 1
                logger.emitir(
                    "info", f"Ignorado (já processado antes nesse pedido): {arquivo}",
                    arquivo=arquivo, status_csv="JA_PROCESSADO",
                )
            else:
                arquivos_novos.append(arquivo)
        arquivos_arte = arquivos_novos

        if not arquivos_arte:
            logger.emitir(
                "info",
                "Nenhum arquivo novo — todos os arquivos da pasta de entrada já tinham sido "
                "processados nesse pedido.",
            )
            return {
                "pasta_saida": str(pasta_saida), "unificado": None, "log_csv": None,
                "os": None, "os_json": None, "arquivos_novos": 0,
                "arquivos_ignorados": arquivos_ignorados, "atualizacao": True,
            }
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        pasta_saida = pathlib.Path(pasta_saida_base) / f"{nome_cliente_seguro.upper()}_{timestamp}"
        try:
            pasta_saida.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            logger.emitir("err", f"Não foi possível criar a pasta de saída: {e}")
            return None

    ALTURA_ETIQUETA = ALTURA_A4 / 2

    dados_categorias = {cat: _novo_estado_categoria() for cat in categorias}
    itens_os = []
    nomes_processados_com_sucesso = set()

    agora = datetime.now()
    data_hora_atual = agora.strftime("%d/%m/%Y %H:%M:%S")
    data_chegada_curta = agora.strftime("%d/%m")
    total_arquivos = len(arquivos_arte)

    for indice, arquivo in enumerate(arquivos_arte, start=1):
        # nome ANTES de qualquer renomeação padronizada (ver
        # _renomear_para_padrao mais abaixo, que reatribui 'arquivo') —
        # é esse nome que aparece em 'arquivos_arte', então é ele que
        # precisa ser comparado no final pra saber se bateu a
        # quantidade (ver 'nomes_processados_com_sucesso' abaixo).
        arquivo_original = arquivo
        if on_progress:
            on_progress(indice, total_arquivos)

        nome_arquivo_upper = arquivo.upper()
        eh_reposicao = _eh_reposicao(nome_arquivo_upper)

        # Já convertendo sinônimos (ex: "VINIL" -> "ADESIVO") pra
        # categoria real — ver dimensoes.identificar_categoria (mesma
        # função reaproveitada por estado_pedido.py pra reconstruir
        # itens legado a partir só do nome do arquivo).
        categoria_encontrada, categorias_encontradas = identificar_categoria(
            nome_arquivo_upper, materiais, sinonimos_categoria
        )

        # Material composto: mesma peça consome uma categoria extra além
        # da principal (ex: "PS ADESIVADO" também consome ADESIVO) — ver
        # _acumular_consumo_categoria mais abaixo, onde isso é usado.
        categoria_extra = identificar_categoria_extra(nome_arquivo_upper, materiais, materiais_compostos)

        if categoria_encontrada is None and categoria_extra is not None:
            # Nome só tem a palavra-gatilho do composto (ex: "ADESIVADO"
            # sozinho, sem MDF/PS/ACRILICO junto — caso real: peça de
            # adesivo impresso pra colar, sem chapa base nenhuma nesse
            # arquivo). Sem categoria base pra compor, a categoria extra
            # vira a principal, em vez de descartar o arquivo inteiro
            # (2026-08-29: 3 arquivos "ADESIVADO" da Unilever sumiam da
            # OS/checklist por causa disso).
            categoria_encontrada = categoria_extra
            categoria_extra = None

        if categoria_encontrada is None:
            logger.emitir("err", f"Ignorado (sem categoria no nome): {arquivo}",
                           arquivo=arquivo, status_csv="IGNORADO")
            continue

        if len(categorias_encontradas) > 1:
            logger.emitir(
                "warn",
                f"Nome ambíguo em '{arquivo}': {', '.join(categorias_encontradas)} — "
                f"usando '{categoria_encontrada}' (nome mais específico)",
                arquivo=arquivo, status_csv="AVISO - CATEGORIA AMBIGUA",
            )

        cat_info = dados_categorias[categoria_encontrada]
        cat_info["contem_arquivos"] = True
        cat_info["tem_etiqueta"] = True

        if categoria_extra == categoria_encontrada:
            categoria_extra = None

        # Medida vem do nome sempre que possível; só recorre à arte
        # (ver dimensoes.dimensao_da_arte) quando o nome não tem
        # NENHUMA medida — decisão do usuário (2026-08-29): o nome, se
        # tiver medida, é sempre a fonte da verdade.
        dimensao = extrair_dimensoes(arquivo, typos_unidade)

        # Exceção — medida do nome fisicamente impossível: geometria,
        # não um chute de escala (ver a regra 1:10 testada e
        # descartada) — pedido do usuário (2026-08-29): "todo caso de
        # dúvida... use sempre o tamanho da arte como referência".
        #   - chapa (MDF/PVC/PS/ACRÍLICO): peça cortada não pode ser
        #     maior que a chapa crua cadastrada, em nenhuma orientação.
        #   - rolo (LONA/ADESIVO): só a LARGURA do rolo é um limite
        #     físico de verdade (é a largura de impressão da máquina);
        #     o comprimento não tem teto (dá pra imprimir/emendar
        #     quanto precisar). Por isso o teste é só "o lado mais
        #     estreito da peça cabe na largura do rolo, em alguma
        #     orientação" — nunca as duas dimensões como na chapa.
        #     Achado ao vivo (2026-08-30): "1.46X094M" (zero à esquerda
        #     engolido pelo float(), devia ser 0,94m) virou 94 METROS
        #     de altura pra um item de totem — nem a largura nem a
        #     "altura" de 94m cabiam no rolo de 1,27m, sinal claro de
        #     erro de digitação.
        info_material_atual = materiais.get(categoria_encontrada, {})
        tipo_material_atual = info_material_atual.get("tipo")
        if dimensao is not None and tipo_material_atual == "chapa":
            largura_max_cm = info_material_atual.get("largura_cm")
            comprimento_max_cm = info_material_atual.get("comprimento_cm")
            if largura_max_cm and comprimento_max_cm:
                largura_peca_cm = dimensao["largura_m"] * 100
                altura_peca_cm = dimensao["altura_m"] * 100
                cabe_direto = largura_peca_cm <= largura_max_cm and altura_peca_cm <= comprimento_max_cm
                cabe_rotacionado = largura_peca_cm <= comprimento_max_cm and altura_peca_cm <= largura_max_cm
                if not cabe_direto and not cabe_rotacionado:
                    logger.emitir(
                        "warn",
                        f"'{arquivo}': medida do nome ({dimensao['largura_m']:.2f}x{dimensao['altura_m']:.2f}m) "
                        f"não cabe na chapa de {categoria_encontrada} cadastrada "
                        f"({largura_max_cm / 100:.2f}x{comprimento_max_cm / 100:.2f}m) — provável erro de "
                        f"digitação no nome, medindo pela arte em vez de confiar nele.",
                        arquivo=arquivo, status_csv="AVISO - MEDIDA IMPOSSIVEL, USANDO ARTE",
                    )
                    dimensao = None
        elif dimensao is not None and tipo_material_atual == "rolo":
            # Largura MAIOR que o rolo não entra aqui — isso é cenário
            # real e legítimo (peça grande, emenda de mais de um rolo;
            # já existe aviso separado "mais larga que o rolo" pra
            # conferência manual, sem descartar a medida do nome). O
            # que pega aqui é só o comprimento implausível: nenhuma
            # peça de verdade processada até hoje passou do
            # 'comprimento_cm' cadastrado (quanto tem num rolo típico)
            # — usar isso como teto generoso pega o erro de digitação
            # (ex: "094M" virando 94 metros) sem incomodar peça grande
            # de verdade.
            comprimento_rolo_cm = info_material_atual.get("comprimento_cm")
            if comprimento_rolo_cm:
                lado_maior_cm = max(dimensao["largura_m"], dimensao["altura_m"]) * 100
                if lado_maior_cm > comprimento_rolo_cm:
                    logger.emitir(
                        "warn",
                        f"'{arquivo}': medida do nome ({dimensao['largura_m']:.2f}x{dimensao['altura_m']:.2f}m) "
                        f"passa do comprimento de rolo cadastrado pra {categoria_encontrada} "
                        f"({comprimento_rolo_cm / 100:.2f}m) — provável erro de digitação no nome, medindo "
                        f"pela arte em vez de confiar nele.",
                        arquivo=arquivo, status_csv="AVISO - MEDIDA IMPOSSIVEL, USANDO ARTE",
                    )
                    dimensao = None

        arte_sem_conteudo = False
        if dimensao is None:
            caminho_medicao = os.path.join(pasta_entrada, arquivo)
            try:
                with pymupdf.open(caminho_medicao) as doc_medicao:
                    if len(doc_medicao) > 0:
                        dimensao = dimensao_da_arte(doc_medicao[0])
                        arte_sem_conteudo = dimensao is None
            except Exception as e:
                logger.emitir(
                    "warn",
                    f"Não foi possível abrir '{arquivo}' pra medir pela arte: {e}",
                    arquivo=arquivo, status_csv="AVISO - ERRO AO MEDIR",
                )

        if arte_sem_conteudo:
            logger.emitir(
                "warn",
                f"'{arquivo}': PDF sem nenhum conteúdo visível (nem imagem, nem desenho, nem "
                f"texto) — não deu pra medir pela arte. Um arquivo pra impressão deveria ter "
                f"conteúdo; confira se ele não está corrompido ou com exportação incompleta.",
                arquivo=arquivo, status_csv="AVISO - PDF SEM CONTEUDO",
            )

        quantidade, qtd_encontrada = extrair_quantidade(arquivo)
        variantes_config = materiais[categoria_encontrada].get("variantes", [])
        variante = identificar_variante(nome_arquivo_upper, variantes_config)

        # Padroniza o nome do arquivo de origem, direto na pasta de
        # entrada — pedido do usuário (2026-08-29): quer os arquivos já
        # organizados, não só a etiqueta/OS gerada. Falha de rename
        # (permissão, arquivo aberto em outro programa) nunca trava a
        # rodada — só segue com o nome original.
        nome_padronizado = _nome_padronizado(
            arquivo, quantidade, categoria_encontrada, dimensao, typos_unidade, nome_cliente_seguro,
        )
        arquivo = _renomear_para_padrao(pasta_entrada, arquivo, nome_padronizado, logger)
        nome_arquivo_upper = arquivo.upper()

        caminho_completo = os.path.join(pasta_entrada, arquivo)

        try:
            pdf_original = pymupdf.open(caminho_completo)
        except Exception as e:
            logger.emitir("err", f"Erro ao abrir '{arquivo}': {e}", arquivo=arquivo, status_csv="ERRO")
            continue

        if len(pdf_original) == 0:
            logger.emitir("warn", f"Arquivo vazio (0 páginas): {arquivo}",
                           arquivo=arquivo, status_csv="AVISO - ARQUIVO VAZIO")
            pdf_original.close()
            continue

        # Pré-checagem: renderiza a primeira página ANTES de comprometer
        # qualquer página/posição no documento da categoria (cat_info) —
        # se a arte tem imagem embutida grande demais pra essa máquina
        # processar (achado real, 2026-09-01: PDF de produção nascido de
        # TIF gigante, "malloc failed" mesmo com pouca memória de
        # sobra), troca pra uma cópia com resolução reduzida ANTES de
        # desenhar qualquer coisa — nunca no meio da montagem, pra nunca
        # sobrar página parcial de uma tentativa que falhou no documento
        # final. A cópia nunca sobrescreve nem move o original (pedido
        # do usuário: "reduza o que precisar... não mexer nos arquivos
        # originais" — ver conversao_adobe.reduzir_pdf_grande).
        try:
            pymupdf.TOOLS.reset_mupdf_warnings()
            _rect_teste = pdf_original[0].rect
            _caixa_largura_teste = LARGURA_A4 - 20
            _caixa_altura_teste = ALTURA_ETIQUETA - 75
            if _rect_teste.width > 0 and _rect_teste.height > 0:
                _escala_teste = min(_caixa_largura_teste / _rect_teste.width, _caixa_altura_teste / _rect_teste.height)
            else:
                _escala_teste = 1.0
            _escala_teste *= DPI_ETIQUETA / 72.0
            pdf_original[0].get_pixmap(matrix=pymupdf.Matrix(_escala_teste, _escala_teste))
        except Exception:
            pdf_original.close()
            logger.emitir(
                "warn",
                f"'{arquivo}': imagem grande demais pra processar direto — reduzindo resolução numa "
                f"cópia à parte (arquivo original fica intocado)...",
                arquivo=arquivo, status_csv="AVISO - REDUZINDO RESOLUCAO",
            )
            caminho_reduzido = _obter_pdf_reduzido(pasta_entrada, arquivo, logger)
            if caminho_reduzido is None:
                logger.emitir(
                    "err", f"'{arquivo}': não foi possível processar mesmo depois de tentar reduzir a resolução.",
                    arquivo=arquivo, status_csv="ERRO",
                )
                continue
            try:
                pdf_original = pymupdf.open(caminho_reduzido)
            except Exception as e:
                logger.emitir(
                    "err", f"'{arquivo}': erro ao abrir a versão reduzida: {e}",
                    arquivo=arquivo, status_csv="ERRO",
                )
                continue

        thumbnail_bytes = None
        try:
            num_pag = 0
            for num_pag in range(len(pdf_original)):
                # a primeiríssima etiqueta da categoria ganha uma página
                # com o banner (logo + nome da categoria) no topo, só ela
                # sozinha na página — as próximas etiquetas voltam ao
                # layout normal de 2 por folha
                eh_pagina_banner = cat_info["total_etiquetas"] == 0 and num_pag == 0

                if eh_pagina_banner:
                    cat_info["pagina_atual"], y_inicial, cat_info["caixa_contagem_banner"] = (
                        iniciar_pagina_com_banner(cat_info["pdf_saida"], LARGURA_A4, ALTURA_A4, categoria_encontrada)
                    )
                    y_final = y_inicial + ALTURA_ETIQUETA
                else:
                    if cat_info["posicao_na_pagina"] == 0:
                        cat_info["pagina_atual"] = cat_info["pdf_saida"].new_page(
                            width=LARGURA_A4, height=ALTURA_A4
                        )
                    y_inicial = 0 if cat_info["posicao_na_pagina"] == 0 else ALTURA_ETIQUETA
                    y_final = ALTURA_ETIQUETA if cat_info["posicao_na_pagina"] == 0 else ALTURA_A4

                cat_info["posicoes_etiquetas"].append((len(cat_info["pdf_saida"]) - 1, y_inicial, y_final))

                margem_rodape = 65
                caixa_destino = pymupdf.Rect(10, y_inicial + 10, LARGURA_A4 - 10, y_final - margem_rodape)

                # Rasteriza a arte (em vez de embutir o PDF de origem como
                # vetor) pra controlar o tamanho do arquivo final — ver
                # DPI_ETIQUETA acima. Mantém a proporção original dentro de
                # caixa_destino, do mesmo jeito que show_pdf_page(
                # keep_proportion=True) fazia.
                pagina_fonte = pdf_original[num_pag]
                rect_fonte = pagina_fonte.rect
                if rect_fonte.width > 0 and rect_fonte.height > 0:
                    escala_fit = min(caixa_destino.width / rect_fonte.width, caixa_destino.height / rect_fonte.height)
                else:
                    escala_fit = 1.0
                largura_final = rect_fonte.width * escala_fit
                altura_final = rect_fonte.height * escala_fit
                x0 = caixa_destino.x0 + (caixa_destino.width - largura_final) / 2
                y0 = caixa_destino.y0 + (caixa_destino.height - altura_final) / 2
                rect_arte = pymupdf.Rect(x0, y0, x0 + largura_final, y0 + altura_final)

                # Alguns PDFs de origem (banners muito grandes) têm uma
                # imagem embutida tão grande que o MuPDF se recusa a
                # decodificar — isso não levanta uma exceção Python, só um
                # aviso interno, e o resultado seria uma etiqueta em branco
                # se a gente não conferisse. TOOLS.mupdf_warnings() é a
                # única forma de detectar isso.
                pymupdf.TOOLS.reset_mupdf_warnings()
                escala_render = escala_fit * (DPI_ETIQUETA / 72.0)
                pix_etiqueta = pagina_fonte.get_pixmap(matrix=pymupdf.Matrix(escala_render, escala_render))

                if pymupdf.TOOLS.mupdf_warnings():
                    # não deu pra rasterizar — e embutir o PDF de origem
                    # como vetor (o jeito antigo) arrastaria a imagem
                    # gigante de origem pro checklist inteiro (já vimos
                    # caso real de +150MB só de um arquivo), o que quebra
                    # o objetivo de arquivo leve. Em vez disso, deixa um
                    # aviso visual no lugar da arte — a etiqueta continua
                    # com todos os dados (material/cliente/data) no rodapé,
                    # só sem a prévia visual desse item específico.
                    pymupdf.TOOLS.reset_mupdf_warnings()
                    cat_info["pagina_atual"].draw_rect(
                        caixa_destino, color=(0.8, 0.8, 0.8), fill=(0.96, 0.96, 0.96), width=0.7
                    )
                    html_aviso = """
                    <div style="font-family: sans-serif; text-align: center; color: #888888;">
                        <p style="font-size: 11pt; margin: 0;">Arte não pôde ser reduzida</p>
                        <p style="font-size: 9pt; margin: 4px 0 0 0;">(imagem de origem grande demais) — confira no arquivo original</p>
                    </div>
                    """
                    cat_info["pagina_atual"].insert_htmlbox(caixa_destino, html_aviso)
                    if num_pag == 0:
                        logger.emitir(
                            "warn",
                            f"'{arquivo}': imagem de origem grande demais pra reduzir — "
                            f"etiqueta ficou sem a prévia visual desse item (confira o arquivo original)",
                            arquivo=arquivo, status_csv="AVISO - IMAGEM GRANDE",
                        )
                else:
                    cat_info["pagina_atual"].insert_image(
                        rect_arte, stream=pix_etiqueta.tobytes("jpg", jpg_quality=QUALIDADE_JPG_ETIQUETA)
                    )

                    if num_pag == 0:
                        # a miniatura da OS é derivada do mesmo pixmap já
                        # renderizado acima, em vez de renderizar a página
                        # de novo — importante pra processar mais rápido
                        # com pastas de entrada grandes (até 200 arquivos)
                        try:
                            escala_thumb = min(300 / pix_etiqueta.width, 300 / pix_etiqueta.height, 1.0)
                            if escala_thumb < 1.0:
                                pix_thumb = pymupdf.Pixmap(
                                    pix_etiqueta,
                                    max(1, int(pix_etiqueta.width * escala_thumb)),
                                    max(1, int(pix_etiqueta.height * escala_thumb)),
                                )
                            else:
                                pix_thumb = pix_etiqueta
                            thumbnail_bytes = pix_thumb.tobytes("jpg", jpg_quality=70)
                        except Exception:
                            thumbnail_bytes = None

                if not eh_pagina_banner and cat_info["posicao_na_pagina"] == 0:
                    cat_info["pagina_atual"].draw_line(
                        pymupdf.Point(0, ALTURA_ETIQUETA),
                        pymupdf.Point(LARGURA_A4, ALTURA_ETIQUETA),
                        color=(0.5, 0.5, 0.5), width=1,
                    )

                caixa_rodape = pymupdf.Rect(15, y_final - margem_rodape + 5, LARGURA_A4 - 15, y_final - 5)
                # em rodada de atualização, TODO arquivo que passa por esse
                # laço é novo por construção (o que já era conhecido foi
                # filtrado antes do laço começar — ver 'arquivos_novos'
                # acima) — a única distinção que falta checar por arquivo
                # é se é reposição (nome renomeado de propósito, ver
                # _eh_reposicao) ou material novo do cliente
                if eh_reposicao:
                    selo_novo_html = (
                        f'<span style="font-size: 7pt; font-weight: bold; color: #40506b; '
                        f'background-color: #e7eaf2; display: inline-block; padding: 1px 6px; '
                        f'margin-right: 6px;">REPOSIÇÃO &middot; {data_chegada_curta}</span>'
                    )
                elif modo_atualizacao:
                    selo_novo_html = (
                        f'<span style="font-size: 7pt; font-weight: bold; color: #b5490b; '
                        f'background-color: #fbe6d6; display: inline-block; padding: 1px 6px; '
                        f'margin-right: 6px;">NOVO &middot; {data_chegada_curta}</span>'
                    )
                else:
                    selo_novo_html = ""
                html_conteudo = f"""
                <div style="font-family: sans-serif; color: black; line-height: 1.3;">
                    <p style="font-size: 9pt; margin: 0; font-weight: bold;">
                        {selo_novo_html}MATERIAL: {arquivo} &nbsp;|&nbsp; CLIENTE: {nome_cliente_seguro.upper()}
                    </p>
                    <p style="font-size: 8pt; margin: 2px 0 0 0; color: #333333;">
                        DATA/HORA: {data_hora_atual} &nbsp;|&nbsp; GERENTE OP: {nome_gerente} &nbsp;|&nbsp; PRODUTOR RESP: {nome_produtor}
                    </p>
                </div>
                """
                sobra, _ = cat_info["pagina_atual"].insert_htmlbox(caixa_rodape, html_conteudo)
                cat_info["sobra_rodape"].append(sobra)
                # a página do banner só tem essa etiqueta sozinha — a
                # próxima sempre começa uma folha nova, nunca preenche o
                # espaço em branco que sobrou embaixo do banner
                cat_info["posicao_na_pagina"] = 0 if eh_pagina_banner else 1 - cat_info["posicao_na_pagina"]
                cat_info["total_etiquetas"] += 1
        except Exception as e:
            logger.emitir("err", f"Erro ao montar etiqueta de '{arquivo}': {e}",
                           arquivo=arquivo, status_csv="ERRO")
            pdf_original.close()
            continue

        pdf_original.close()

        if dimensao:
            # 'dimensao' é sempre a medida de UMA peça — todo acúmulo de
            # área/desperdício/comprimento de rolo precisa multiplicar por
            # 'quantidade' (ex: "4UN PVC..." consome material de 4 peças,
            # não de 1), senão o total fica sempre como se fosse 1 peça
            # só, mesmo quando o nome diz outra coisa (confirmado pelo
            # usuário, 2026-08-29).
            if dimensao["origem"] == "arte":
                detalhe_area = (
                    f" | Medida (nome sem medida, extraída da arte): "
                    f"{dimensao['largura_m']:.2f}m x {dimensao['altura_m']:.2f}m = "
                    f"{dimensao['area_m2']:.2f}m²"
                )
            else:
                detalhe_area = (
                    f" | Medida: {dimensao['medida_bruta']} → "
                    f"{dimensao['largura_m']:.2f}m x {dimensao['altura_m']:.2f}m = "
                    f"{dimensao['area_m2']:.2f}m²"
                )
                if dimensao["unidade_corrigida"]:
                    detalhe_area += f" (unidade corrigida de {dimensao['unidade_bruta']} para {dimensao['unidade_usada']})"

            resultado = _acumular_consumo_categoria(cat_info, materiais[categoria_encontrada], dimensao, quantidade)
            if resultado["resultado_corte"]:
                resultado_corte = resultado["resultado_corte"]
                detalhe_area += f" | Desperdício estimado: {resultado_corte['desperdicio_m2']:.2f}m²"
                if quantidade > 1:
                    detalhe_area += f" por peça ({resultado_corte['desperdicio_m2'] * quantidade:.2f}m² no total das {quantidade})"
            elif resultado["estimativa_chapa_grande"]:
                estimativa = resultado["estimativa_chapa_grande"]
                cat_info["itens_fora_do_rolo"].append(arquivo)
                texto_girada = " (peça girada 90°)" if estimativa["girada"] else ""
                texto_total_chapas = (
                    f" ({estimativa['total_chapas'] * quantidade} chapas no total das {quantidade})"
                    if quantidade > 1 else ""
                )
                detalhe_area += (
                    f" | Peça maior que a chapa — estimativa: {estimativa['colunas']}x{estimativa['linhas']}"
                    f" = {estimativa['total_chapas']} chapas{texto_girada} por peça{texto_total_chapas}, "
                    f"~{estimativa['desperdicio_m2']:.2f}m² de desperdício por peça "
                    f"(confira o posicionamento das emendas manualmente)"
                )
            else:
                cat_info["itens_fora_do_rolo"].append(arquivo)
                detalhe_area += " | ⚠️ Peça mais larga que o rolo — desperdício não calculado"

            # Material composto (ex: "PS ADESIVADO", "ACRÍLICO ADESIVADO"):
            # a MESMA peça consome dois materiais diferentes ao mesmo tempo
            # (a chapa base + o adesivo colado em cima) — nunca confundir
            # com "IMPRESSO" (impressão direto na chapa, sem adesivo, conta
            # só a categoria principal; ver dimensoes.identificar_categoria_
            # extra). Só a categoria principal ganha etiqueta/checklist —
            # a extra só entra no subtotal de material da OS.
            if categoria_extra:
                cat_info_extra = dados_categorias[categoria_extra]
                cat_info_extra["contem_arquivos"] = True
                _acumular_consumo_categoria(cat_info_extra, materiais[categoria_extra], dimensao, quantidade)
                logger.emitir(
                    "info",
                    f"'{arquivo}': material composto — consumo de {categoria_extra} também contabilizado "
                    f"({dimensao['largura_m']:.2f}m x {dimensao['altura_m']:.2f}m, mesma medida da peça)",
                )
        elif arte_sem_conteudo:
            detalhe_area = " | Medida não reconhecida (nome sem medida, e PDF sem conteúdo pra medir pela arte)"
        else:
            detalhe_area = " | Medida não reconhecida no nome do arquivo"

        detalhe_qtd = f" | Qtd: {quantidade} UN" if qtd_encontrada else " | Qtd não informada (assumida 1 UN)"

        if variantes_config:
            detalhe_variante = (
                f" | Variante: {formatar_variante(variante)}" if variante
                else " | Variante não identificada (confira espessura/cor manualmente)"
            )
        else:
            detalhe_variante = ""

        itens_os.append({
            "arquivo": arquivo,
            "categoria": categoria_encontrada,
            "categoria_extra": categoria_extra,
            "quantidade": quantidade,
            "dimensao": dimensao,
            "thumbnail_bytes": thumbnail_bytes,
            "variante": variante,
            "reposicao": eh_reposicao,
        })
        nomes_processados_com_sucesso.add(arquivo_original)

        detalhe_reposicao = " | REPOSIÇÃO (material refeito, nome renomeado de propósito)" if eh_reposicao else ""
        logger.emitir(
            "ok",
            f"{arquivo} — Categoria: {categoria_encontrada} | Páginas: {num_pag + 1}{detalhe_area}{detalhe_qtd}{detalhe_variante}{detalhe_reposicao}",
            arquivo=arquivo, status_csv="OK",
        )

    # Regra de segurança: OS e Checklist só são gerados se a quantidade
    # bater exatamente com a pasta de entrada — cada arquivo de
    # 'arquivos_arte' precisa ter virado um item de verdade em
    # 'itens_os'. Se algum foi pulado no meio do laço acima (sem
    # categoria no nome, PDF corrompido/vazio, erro ao montar a
    # etiqueta...), NENHUM documento sai — em vez de gerar uma OS/
    # Checklist "quase completo" com um item faltando sem ninguém
    # perceber (pedido do usuário, 2026-08-31, depois do caso real
    # "temos 32 itens na pasta de entrada, a OS e o Checklist não
    # bate" — 2026-08-30). Nada é salvo em disco (nem o estado do
    # pedido) além do log, pra próxima tentativa — depois de corrigido
    # o arquivo problemático — pegar TODOS os arquivos de novo, não só
    # os que faltaram.
    arquivos_sem_etiqueta = arquivos_com_falha_conversao + [
        a for a in arquivos_arte if a not in nomes_processados_com_sucesso
    ]
    if arquivos_sem_etiqueta:
        for cat in categorias:
            dados_categorias[cat]["pdf_saida"].close()
        logger.emitir(
            "err",
            f"OS e Checklist NÃO foram gerados — a quantidade não bate com a pasta de entrada. "
            f"{len(arquivos_sem_etiqueta)} de {len(arquivos_arte)} arquivo(s) não viraram etiqueta "
            f"(motivo de cada um no log acima): {', '.join(arquivos_sem_etiqueta)}. Corrija e rode de novo.",
        )
        try:
            salvar_log(str(pasta_saida), nome_cliente_seguro, logger.registro)
        except Exception:
            pass
        return None

    # Preenche a contagem de etiquetas no banner de cada categoria — só
    # dá pra saber o total depois que todos os arquivos já foram lidos.
    # Busca a página pelo índice (0, é sempre a primeira), não guarda o
    # objeto Page: ele fica inválido depois que mais páginas são criadas
    # no mesmo documento.
    for cat in categorias:
        cat_info = dados_categorias[cat]
        if cat_info["contem_arquivos"] and cat_info["caixa_contagem_banner"] is not None:
            total = cat_info["total_etiquetas"]
            html_contagem = (
                f'<p style="font-family: sans-serif; font-size: 11pt; color: #444444; margin: 21px 0 0 0; '
                f'text-align: right;">{total} etiqueta{"s" if total != 1 else ""}</p>'
            )
            cat_info["pdf_saida"][0].insert_htmlbox(cat_info["caixa_contagem_banner"], html_contagem)

    # Monta o checklist único do PEDIDO (variável ainda chamada
    # "unificado" — nome de antes de virar o único checklist gerado,
    # ver histórico da função) respeitando a ordem configurada, com
    # sumário (TOC) clicável, numerando as páginas ao final. O banner de cada
    # categoria já está embutido na primeira página copiada de
    # cat_info["pdf_saida"] — não precisa mais de uma página de título
    # separada (isso desperdiçava uma folha inteira na impressão).
    #
    # Um documento só por pedido, como a OS: se já existe um checklist
    # dessa pasta (rodada anterior), essa rodada ACRESCENTA página nele
    # em vez de criar um arquivo "V2" à parte — as páginas antigas nunca
    # são reabertas/renumeradas de novo (podem já estar impressas e
    # marcadas à caneta na produção), só o TOC ganha as novas entradas
    # no final (ver numerar_paginas_a_partir_de).
    caminho_unificado = pasta_saida / f"Checklist {nome_cliente_seguro.upper()}.pdf"
    pdf_unificado = pymupdf.open()
    toc = []
    if modo_atualizacao and caminho_unificado.exists():
        pdf_checklist_anterior = pymupdf.open(str(caminho_unificado))
        toc = pdf_checklist_anterior.get_toc()
        pdf_unificado.insert_pdf(pdf_checklist_anterior)
        pdf_checklist_anterior.close()
    indice_inicio_rodada = len(pdf_unificado)

    for cat in ordem_unificado:
        cat_info = dados_categorias[cat]
        # 'tem_etiqueta' (não 'contem_arquivos'): uma categoria extra de
        # material composto (ex: ADESIVO em "PS ADESIVADO") tem consumo a
        # reportar mas NUNCA página própria — inserir um pdf_saida vazio
        # (sem página nenhuma) trava o PyMuPDF ("malformed page tree").
        if cat_info["tem_etiqueta"]:
            pagina_inicio = len(pdf_unificado) + 1
            toc.append([1, f"{cat} ({cat_info['total_etiquetas']} etiquetas)", pagina_inicio])

            indice_inicio_paginas = len(pdf_unificado)
            pdf_unificado.insert_pdf(cat_info["pdf_saida"])

            # checkbox de conferência no local + aviso de responsabilidade
            # do produtor, em cada etiqueta. Usa a posição real de cada
            # etiqueta (guardada durante a montagem) em vez de assumir
            # sempre 2 por página — a página do banner tem só 1.
            sobras = cat_info["sobra_rodape"]
            for indice_etiqueta, (indice_pagina, y_ini, y_fim) in enumerate(cat_info["posicoes_etiquetas"]):
                pagina_unificada = pdf_unificado[indice_inicio_paginas + indice_pagina]
                estampar_conferencia_local(pagina_unificada, LARGURA_A4, y_ini, y_fim, sobras[indice_etiqueta])

            logger.emitir("info", f"Seção adicionada ao unificado: {cat} ({cat_info['total_etiquetas']} etiquetas)")

    for cat in categorias:
        dados_categorias[cat]["pdf_saida"].close()

    if len(pdf_unificado) > 0:
        try:
            pdf_unificado.set_toc(toc)
            numerar_paginas_a_partir_de(pdf_unificado, indice_inicio_rodada)
            # garbage=4/deflate: sem isso, cada insert_htmlbox deixa uma cópia
            # de fonte solta no arquivo e o PDF fica ordens de grandeza maior
            # do que precisa (mesmo problema resolvido antes na OS)
            pdf_unificado.save(str(caminho_unificado), garbage=4, deflate=True)
            pdf_unificado.close()
            logger.emitir("ok", f"Checklist gerado: {caminho_unificado.name}")
        except Exception as e:
            logger.emitir("err", f"Não foi possível salvar o checklist: {e}")
            caminho_unificado = None
            try:
                pdf_unificado.close()
            except Exception:
                pass
    else:
        caminho_unificado = None
        pdf_unificado.close()

    caminho_log = None
    try:
        caminho_log = salvar_log(str(pasta_saida), nome_cliente_seguro, logger.registro)
        logger.emitir("info", f"Log salvo em: {pathlib.Path(caminho_log).name}")
    except Exception as e:
        logger.emitir("err", f"Não foi possível salvar o log CSV: {e}")

    # A OS em PDF mostra o pedido inteiro — itens de rodadas anteriores
    # (vindos do estado salvo) + os novos desta rodada, com o selo NOVO
    # só nos novos — sempre a versão mais recente por cima da anterior,
    # só pra referência visual (nunca fica "impressa e marcada à caneta"
    # do jeito que o checklist fica, então reconstruir ela inteira não é
    # problema). 'dados_categorias_os' é recalculado a partir da lista
    # combinada porque 'dados_categorias' (usado pro checklist acima) só
    # reflete os itens processados NESTA rodada.
    itens_os_com_selo = []
    for item in itens_os:
        if item.get("reposicao"):
            itens_os_com_selo.append(dict(item, reposicao_em=data_chegada_curta))
        elif modo_atualizacao:
            itens_os_com_selo.append(dict(item, novo_em=data_chegada_curta))
        else:
            itens_os_com_selo.append(item)
    itens_para_os = itens_anteriores + itens_os_com_selo
    # Material composto (ex: "PS ADESIVADO" também consome ADESIVO — ver
    # 'categoria_extra', dimensoes.identificar_categoria_extra): conta na
    # categoria extra também, mesma medida/quantidade da peça — só não
    # entra em 'total_etiquetas' (isso continua sendo só a categoria
    # principal, já que é uma etiqueta física só).
    dados_categorias_os = {
        cat: {
            "contem_arquivos": any(
                i["categoria"] == cat or i.get("categoria_extra") == cat for i in itens_para_os
            ),
            "area_total_m2": sum(
                i["dimensao"]["area_m2"] * i.get("quantidade", 1)
                for i in itens_para_os
                if i.get("dimensao") and (i["categoria"] == cat or i.get("categoria_extra") == cat)
            ),
            "total_etiquetas": sum(1 for i in itens_para_os if i["categoria"] == cat),
        }
        for cat in categorias
    }

    caminho_os = None
    caminho_os_json = None
    try:
        caminho_os = gerar_os(
            str(pasta_saida), nome_cliente_seguro, nome_gerente, nome_produtor,
            itens_para_os, dados_categorias_os, ordem_unificado, data_hora_atual, materiais,
        )
        logger.emitir("ok", f"OS gerada: {pathlib.Path(caminho_os).name}")
        # arquivo complementar, lido pelo controle de estoque pra baixa
        # automática (ver estoque.py) — nunca acontece sozinho, é sempre
        # o usuário quem escolhe enviar esse arquivo lá na tela de estoque.
        # Leva só 'itens_os' (nunca 'itens_para_os'/itens de rodadas
        # anteriores) e o nome do arquivo carrega data E hora dessa
        # rodada (não só a data, que sozinha colide se o mesmo pedido
        # for atualizado mais de uma vez no mesmo dia — sobrescreveria o
        # JSON de uma rodada anterior ainda não usada no estoque). O
        # selo visual na etiqueta/OS continua só dia/mês; é só o nome do
        # arquivo que precisa da hora, pra nunca colidir.
        rotulo_arquivo_os = f"novos {agora.strftime('%d-%m_%H%M%S')}"
        caminho_os_json = salvar_dados_os(
            str(pasta_saida), nome_cliente_seguro, itens_os, data_hora_atual, rotulo_arquivo_os,
        )
    except Exception as e:
        logger.emitir("err", f"Não foi possível gerar a Ordem de Serviço: {e}")

    # Estado desta pasta pra próxima rodada: itens de antes + os que
    # acabaram de ser processados agora, sem o selo (que é só pra exibir
    # a OS desta rodada — ver estado_pedido.salvar_estado). Salvo mesmo
    # se a geração da OS acima tiver falhado, porque as etiquetas e o
    # checklist já foram gravados em disco nesse ponto — o que importa
    # pro filtro de "já processado" é isso, não a OS.
    salvar_estado(str(pasta_saida), itens_anteriores + itens_os)

    # Resumo de área por categoria
    total_geral_area = 0.0
    for cat in ordem_unificado:
        cat_info = dados_categorias[cat]
        if cat_info["contem_arquivos"]:
            logger.emitir("info", f"Área {cat}: {cat_info['area_total_m2']:.2f} m²")
            total_geral_area += cat_info["area_total_m2"]
    if total_geral_area > 0:
        logger.emitir("info", f"Área TOTAL: {total_geral_area:.2f} m²")

    # Estimativa de desperdício de material (modelo de corte sequencial)
    for cat in ordem_unificado:
        cat_info = dados_categorias[cat]
        if not cat_info["contem_arquivos"]:
            continue
        if cat_info["comprimento_rolo_usado_m"] == 0 and cat_info["chapas_extras"] == 0:
            continue
        info_material = materiais[cat]
        tipo = info_material["tipo"]
        comprimento_estoque_m = info_material["comprimento_cm"] / 100
        comprimento_usado = cat_info["comprimento_rolo_usado_m"]
        unidades_necessarias = math.ceil(comprimento_usado / comprimento_estoque_m) if comprimento_estoque_m > 0 else 0
        # peças maiores que uma chapa só já entram como um número exato de
        # chapas (calcular_desperdicio_chapa_grande), não como comprimento —
        # soma direto no total (não se aplica a rolo, que não usa isso)
        unidades_necessarias += cat_info["chapas_extras"]
        unidade_label = "rolo(s)" if tipo == "rolo" else "chapa(s)"

        logger.emitir(
            "info",
            f"Desperdício {cat}: {cat_info['area_desperdicio_m2']:.2f} m² "
            f"| {comprimento_usado:.2f} m usados (~{unidades_necessarias} {unidade_label} de {comprimento_estoque_m:.2f}m)",
        )
        if cat_info["itens_fora_do_rolo"]:
            if tipo == "chapa":
                logger.emitir(
                    "warn",
                    f"{len(cat_info['itens_fora_do_rolo'])} peça(s) de {cat} maior(es) que uma chapa — "
                    f"estimativa por chapas já somada acima, mas confira o posicionamento das emendas: "
                    f"{', '.join(cat_info['itens_fora_do_rolo'])}",
                )
            else:
                logger.emitir(
                    "warn",
                    f"{len(cat_info['itens_fora_do_rolo'])} peça(s) de {cat} mais larga(s) que o rolo, "
                    f"conferir manualmente: {', '.join(cat_info['itens_fora_do_rolo'])}",
                )

    return {
        "pasta_saida": str(pasta_saida),
        "unificado": str(caminho_unificado) if caminho_unificado else None,
        "log_csv": caminho_log,
        "os": caminho_os,
        "os_json": caminho_os_json,
        "arquivos_novos": len(arquivos_arte),
        "arquivos_ignorados": arquivos_ignorados,
        "atualizacao": modo_atualizacao,
    }
