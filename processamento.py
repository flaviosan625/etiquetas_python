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

from dimensoes import (
    contem_palavra, extrair_dimensoes, calcular_desperdicio_item, extrair_quantidade,
    identificar_categoria, identificar_variante, formatar_variante, calcular_desperdicio_chapa_grande,
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
        "contem_arquivos": False,
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


_PADRAO_VERSAO_CHECKLIST = re.compile(r" V(\d+)\.pdf$", re.IGNORECASE)


def _proxima_versao_checklist(pasta_saida, nome_cliente_seguro):
    """
    Cada rodada de processamento (arquivo novo OU reposição) vira um
    checklist SEPARADO — "Checklist CLIENTE.pdf" na primeira rodada,
    "Checklist CLIENTE V2.pdf", "V3.pdf" etc nas seguintes — em vez de
    colar páginas no mesmo PDF de sempre. Decisão do usuário
    (2026-08-26): o checklist já impresso e marcado à caneta na
    produção não muda mais depois; cada leva nova de material vira uma
    folha própria, só com o que precisa ser feito naquela rodada — sem
    reimprimir o que já foi produzido antes. A OS continua sendo UM
    documento só, sempre com o pedido inteiro (ver 'itens_para_os' mais
    abaixo) — só o checklist (o documento de produção, físico) é que
    passa a ser por rodada.

    Desde 2026-08-28, só existe UM checklist por rodada (o que antes
    era "- UNIFICADO") — os arquivos separados por categoria pararam de
    ser salvos em disco (o usuário pediu pra buscar item individual por
    aqui, quando precisar, em vez de gerar arquivo a mais toda rodada).

    A primeira rodada de um pedido não leva sufixo (mantém o nome já
    usado antes); a segunda vira V2, a terceira V3 — sempre o maior
    número já usado em qualquer checklist dessa pasta, mais um. Não
    guarda esse número em nenhum estado à parte: conta pelos arquivos
    que já existem em disco.
    """
    pasta = pathlib.Path(pasta_saida)
    nome_base = f"Checklist {nome_cliente_seguro.upper()}"
    arquivos = list(pasta.glob(f"{nome_base}.pdf")) + list(pasta.glob(f"{nome_base} V*.pdf"))
    if not arquivos:
        return 1
    maior = 1
    for caminho in arquivos:
        m = _PADRAO_VERSAO_CHECKLIST.search(caminho.name)
        if m:
            maior = max(maior, int(m.group(1)))
    return maior + 1


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
    Só o que é realmente novo vira etiqueta, ganha o selo "NOVO" e
    entra nos totais que alimentam a baixa de estoque; o checklist dessa
    rodada vira um arquivo À PARTE, versionado (V2, V3... — ver
    _proxima_versao_checklist), nunca mexe num checklist já gerado
    antes. A OS continua sendo um documento só, sempre com o pedido
    inteiro atualizado.
    """
    logger = _Logger(on_log)

    materiais = config["materiais"]
    categorias = list(materiais.keys())
    sinonimos_categoria = config.get("sinonimos_categoria", {})
    typos_unidade = config.get("typos_unidade", {})

    ordem_configurada = [c for c in config.get("ordem_unificado", []) if c in materiais]
    ordem_unificado = ordem_configurada + [c for c in categorias if c not in ordem_configurada]

    nome_cliente_seguro = sanitizar_nome_arquivo((nome_cliente or "").strip())
    if not (nome_cliente or "").strip():
        logger.emitir("err", "Nome do cliente vazio.")
        return None

    try:
        arquivos_pdf = [f for f in os.listdir(pasta_entrada) if f.lower().endswith(".pdf")]
    except FileNotFoundError:
        logger.emitir("err", f"A pasta '{pasta_entrada}' não foi encontrada.")
        return None
    except PermissionError:
        logger.emitir("err", f"Sem permissão para acessar a pasta '{pasta_entrada}'.")
        return None
    except OSError as e:
        logger.emitir("err", f"Não foi possível ler a pasta '{pasta_entrada}': {e}")
        return None

    if not arquivos_pdf:
        logger.emitir("err", f"Nenhum arquivo PDF encontrado na pasta '{pasta_entrada}'.")
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
        for arquivo in arquivos_pdf:
            if arquivo in nomes_conhecidos:
                arquivos_ignorados += 1
                logger.emitir(
                    "info", f"Ignorado (já processado antes nesse pedido): {arquivo}",
                    arquivo=arquivo, status_csv="JA_PROCESSADO",
                )
            else:
                arquivos_novos.append(arquivo)
        arquivos_pdf = arquivos_novos

        if not arquivos_pdf:
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

    versao_checklist = _proxima_versao_checklist(pasta_saida, nome_cliente_seguro)
    sufixo_versao_checklist = "" if versao_checklist == 1 else f" V{versao_checklist}"

    ALTURA_ETIQUETA = ALTURA_A4 / 2

    dados_categorias = {cat: _novo_estado_categoria() for cat in categorias}
    itens_os = []

    agora = datetime.now()
    data_hora_atual = agora.strftime("%d/%m/%Y %H:%M:%S")
    data_chegada_curta = agora.strftime("%d/%m")
    total_arquivos = len(arquivos_pdf)

    for indice, arquivo in enumerate(arquivos_pdf, start=1):
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

        dimensao = extrair_dimensoes(arquivo, typos_unidade)
        if dimensao:
            cat_info["area_total_m2"] += dimensao["area_m2"]
            detalhe_area = (
                f" | Medida: {dimensao['medida_bruta']} → "
                f"{dimensao['largura_m']:.2f}m x {dimensao['altura_m']:.2f}m = "
                f"{dimensao['area_m2']:.2f}m²"
            )
            if dimensao["unidade_corrigida"]:
                detalhe_area += f" (unidade corrigida de {dimensao['unidade_bruta']} para {dimensao['unidade_usada']})"

            info_material = materiais[categoria_encontrada]
            largura_rolo_m = info_material["largura_cm"] / 100
            resultado_corte = calcular_desperdicio_item(dimensao, largura_rolo_m)
            if resultado_corte:
                cat_info["area_desperdicio_m2"] += resultado_corte["desperdicio_m2"]
                cat_info["comprimento_rolo_usado_m"] += resultado_corte["peca_comprimento_m"]
                detalhe_area += f" | Desperdício estimado: {resultado_corte['desperdicio_m2']:.2f}m²"
            else:
                cat_info["itens_fora_do_rolo"].append(arquivo)
                tipo_material = info_material["tipo"]
                if tipo_material == "chapa":
                    # rolo tem comprimento livre (sempre cabe na área de
                    # impressão), então essa estimativa por grade só faz
                    # sentido pra chapa, que tem largura E comprimento fixos
                    comprimento_chapa_m = info_material["comprimento_cm"] / 100
                    estimativa = calcular_desperdicio_chapa_grande(dimensao, largura_rolo_m, comprimento_chapa_m)
                    cat_info["area_desperdicio_m2"] += estimativa["desperdicio_m2"]
                    cat_info["chapas_extras"] += estimativa["total_chapas"]
                    texto_girada = " (peça girada 90°)" if estimativa["girada"] else ""
                    detalhe_area += (
                        f" | Peça maior que a chapa — estimativa: {estimativa['colunas']}x{estimativa['linhas']}"
                        f" = {estimativa['total_chapas']} chapas{texto_girada}, "
                        f"~{estimativa['desperdicio_m2']:.2f}m² de desperdício "
                        f"(confira o posicionamento das emendas manualmente)"
                    )
                else:
                    detalhe_area += " | ⚠️ Peça mais larga que o rolo — desperdício não calculado"
        else:
            detalhe_area = " | Medida não reconhecida no nome do arquivo"

        quantidade, qtd_encontrada = extrair_quantidade(arquivo)
        detalhe_qtd = f" | Qtd: {quantidade} UN" if qtd_encontrada else " | Qtd não informada (assumida 1 UN)"

        variantes_config = materiais[categoria_encontrada].get("variantes", [])
        variante = identificar_variante(nome_arquivo_upper, variantes_config)
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
            "quantidade": quantidade,
            "dimensao": dimensao,
            "thumbnail_bytes": thumbnail_bytes,
            "variante": variante,
            "reposicao": eh_reposicao,
        })

        detalhe_reposicao = " | REPOSIÇÃO (material refeito, nome renomeado de propósito)" if eh_reposicao else ""
        logger.emitir(
            "ok",
            f"{arquivo} — Categoria: {categoria_encontrada} | Páginas: {num_pag + 1}{detalhe_area}{detalhe_qtd}{detalhe_variante}{detalhe_reposicao}",
            arquivo=arquivo, status_csv="OK",
        )

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

    # Monta o checklist único da rodada (variável ainda chamada
    # "unificado" — nome de antes de virar o único checklist gerado,
    # ver histórico da função) respeitando a ordem configurada, com
    # sumário (TOC) clicável, numerando as páginas ao final. O banner de cada
    # categoria já está embutido na primeira página copiada de
    # cat_info["pdf_saida"] — não precisa mais de uma página de título
    # separada (isso desperdiçava uma folha inteira na impressão).
    #
    # Sempre um documento NOVO — só com o que foi processado NESSA
    # rodada, com o sufixo de versão no nome (V2, V3...) quando não for
    # a primeira (ver _proxima_versao_checklist).
    caminho_unificado = pasta_saida / f"Checklist {nome_cliente_seguro.upper()}{sufixo_versao_checklist}.pdf"
    pdf_unificado = pymupdf.open()
    toc = []

    for cat in ordem_unificado:
        cat_info = dados_categorias[cat]
        if cat_info["contem_arquivos"]:
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
            numerar_paginas_a_partir_de(pdf_unificado, 0)
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
    dados_categorias_os = {
        cat: {
            "contem_arquivos": any(i["categoria"] == cat for i in itens_para_os),
            "area_total_m2": sum(
                i["dimensao"]["area_m2"] for i in itens_para_os if i["categoria"] == cat and i.get("dimensao")
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
        "arquivos_novos": len(arquivos_pdf),
        "arquivos_ignorados": arquivos_ignorados,
        "atualizacao": modo_atualizacao,
    }
