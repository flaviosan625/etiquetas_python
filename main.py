import os
import csv
import re
import math
import argparse
from datetime import datetime
import pymupdf  # Biblioteca principal para manipulação de PDFs (fitz)


def contem_palavra(texto, termo):
    """
    Verifica se 'termo' aparece em 'texto' como palavra inteira, e não
    como parte de outra palavra. Evita falso positivo como "PS" sendo
    encontrado dentro de "XPS" (que na verdade deve virar PVC).
    Considera como "fim de palavra" qualquer caractere que não seja
    letra ou número (espaço, underscore, hífen, ponto, etc.).
    """
    padrao = r'(?<![A-Z0-9])' + re.escape(termo) + r'(?![A-Z0-9])'
    return re.search(padrao, texto) is not None


# Unidades reconhecidas no nome do arquivo, e seu fator de conversão pra metros
FATORES_UNIDADE = {"MM": 0.001, "CM": 0.01, "M": 1.0}

# Erros de digitação comuns que aparecem no lugar da unidade real.
# "XM" normalmente é "CM" digitado errado (X e C são vizinhos no teclado).
TYPOS_UNIDADE = {"XM": "CM"}


def extrair_dimensoes(nome_arquivo):
    """
    Procura no nome do arquivo um padrão do tipo "NUMEROxNUMERO" seguido
    (ou não) de uma unidade (MM, CM, M), pega a ÚLTIMA ocorrência (a
    medida costuma vir no final do nome), converte tudo pra metros e
    calcula a área em m².

    Corrige automaticamente o erro de digitação "XM" -> "CM"
    (ex: "52X60XM" é interpretado como "52X60CM").

    Se nenhuma unidade for encontrada, assume CM por padrão (unidade
    mais comum nos nomes de arquivo da fábrica).

    Retorna um dicionário com os detalhes, ou None se não encontrar
    nenhum padrão de medida no nome.
    """
    nome_upper = nome_arquivo.upper()
    padrao = r'(\d+(?:[.,]\d+)?)\s*X\s*(\d+(?:[.,]\d+)?)\s*(MM|CM|M|XM)?(?![A-Z])'
    matches = list(re.finditer(padrao, nome_upper))
    if not matches:
        return None

    m = matches[-1]  # última ocorrência no nome
    valor1 = float(m.group(1).replace(',', '.'))
    valor2 = float(m.group(2).replace(',', '.'))
    unidade_bruta = m.group(3)

    unidade_corrigida = False
    if unidade_bruta is None:
        unidade_usada = "CM"
    elif unidade_bruta in TYPOS_UNIDADE:
        unidade_usada = TYPOS_UNIDADE[unidade_bruta]
        unidade_corrigida = True
    else:
        unidade_usada = unidade_bruta

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
    }


def calcular_desperdicio_item(dimensao, largura_rolo_m):
    """
    Calcula o desperdício de material ao cortar UMA peça de um rolo,
    seguindo o modelo de corte SEQUENCIAL: a peça usa a largura toda do
    rolo, orientada de forma que seu lado menor fique alinhado à largura
    do rolo (jeito mais comum de cortar lona/adesivo).

    O trecho do rolo consumido em comprimento é igual ao lado maior da
    peça; a sobra de largura (rolo - peça) ao longo desse comprimento
    todo é o desperdício.

    Retorna None se a peça for mais larga que o próprio rolo (não cabe,
    precisa de conferência manual).
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


def processar_etiquetas(pasta_entrada, nome_cliente, nome_gerente, nome_produtor):
    # Cria a pasta de saída se ela não existir
    pasta_saida = "etiquetas_geradas"
    os.makedirs(pasta_saida, exist_ok=True)

    try:
        arquivos_pdf = [f for f in os.listdir(pasta_entrada) if f.endswith(".pdf")]
    except FileNotFoundError:
        print(f"❌ A pasta '{pasta_entrada}' não foi encontrada.")
        return

    if not arquivos_pdf:
        print(f"❌ Nenhum arquivo PDF encontrado na pasta '{pasta_entrada}'.")
        return

    # Dimensões padrão A4 em pontos (points)
    LARGURA_A4 = 595.27
    ALTURA_A4 = 841.89
    ALTURA_ETIQUETA = ALTURA_A4 / 2

    # Categorias solicitadas para separação
    categorias = ["LONA", "ADESIVO", "PS", "MDF", "PVC", "ACRILICO"]

    # Sinônimos: se o nome do arquivo contiver a chave, é tratado como a
    # categoria do valor. Ex: clientes que mandam "VINIL" no nome do
    # arquivo em vez de "ADESIVO" caem na mesma categoria automaticamente.
    # "XPS" também vira "PVC", pois a fábrica não produz em XPS: quando o
    # cliente pede em XPS, é produzido em PVC.
    SINONIMOS_CATEGORIA = {
        "VINIL": "ADESIVO",
        "XPS": "PVC",
        "ACRÍLICO": "ACRILICO",
    }

    # Ordem fixa em que as categorias devem aparecer no PDF unificado
    ORDEM_UNIFICADO = ["LONA", "ADESIVO", "PVC", "PS", "MDF", "ACRILICO"]

    # Medidas do estoque de cada material, usadas pra estimar desperdício
    # (modelo de corte sequencial: cada peça usa a largura toda do
    # material). LONA e ADESIVO vêm em rolo (comprimento bem maior que a
    # largura); PS e ACRILICO vêm em chapa (tamanho fixo).
    # Só categorias listadas aqui entram no cálculo de desperdício.
    ROLOS_MATERIAL = {
        "LONA": {"largura_cm": 320, "comprimento_cm": 5000, "tipo": "rolo"},
        "ADESIVO": {"largura_cm": 152, "comprimento_cm": 5000, "tipo": "rolo"},
        "PS": {"largura_cm": 200, "comprimento_cm": 100, "tipo": "chapa"},
        "ACRILICO": {"largura_cm": 300, "comprimento_cm": 200, "tipo": "chapa"},
        "PVC": {"largura_cm": 122, "comprimento_cm": 244, "tipo": "chapa"},
        "MDF": {"largura_cm": 185, "comprimento_cm": 270, "tipo": "chapa"},
    }

    # Criar um documento mestre para o PDF unificado
    pdf_unificado = pymupdf.open()

    # Inicializa estrutura para cada PDF de saída por categoria
    dados_categorias = {}
    for cat in categorias:
        dados_categorias[cat] = {
            "pdf_saida": pymupdf.open(),
            "pagina_atual": None,
            "posicao_na_pagina": 0,
            "contem_arquivos": False,
            "total_etiquetas": 0,
            "area_total_m2": 0.0,
            "area_desperdicio_m2": 0.0,
            "comprimento_rolo_usado_m": 0.0,
            "itens_fora_do_rolo": []
        }

    data_hora_atual = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

    # Registro de tudo que acontece no processamento, pra virar log no final
    registro_log = []  # cada item: {"arquivo": ..., "status": ..., "detalhe": ...}

    for arquivo in arquivos_pdf:
        nome_arquivo_upper = arquivo.upper()

        # Verifica em quantas categorias o nome do arquivo se encaixa,
        # já convertendo sinônimos (ex: "VINIL" -> "ADESIVO") pra
        # categoria real usada no restante do script.
        # Usa "palavra inteira" (não substring solta) pra evitar falso
        # positivo, como "PS" sendo encontrado dentro de "XPS".
        categorias_encontradas = []
        for cat in categorias:
            if contem_palavra(nome_arquivo_upper, cat) and cat not in categorias_encontradas:
                categorias_encontradas.append(cat)
        for sinonimo, cat_real in SINONIMOS_CATEGORIA.items():
            if contem_palavra(nome_arquivo_upper, sinonimo) and cat_real not in categorias_encontradas:
                categorias_encontradas.append(cat_real)

        if not categorias_encontradas:
            print(f"⚠️ Ignorado (sem categoria no nome): {arquivo}")
            registro_log.append({
                "arquivo": arquivo,
                "status": "IGNORADO",
                "detalhe": "Nenhuma categoria encontrada no nome do arquivo"
            })
            continue

        categoria_encontrada = categorias_encontradas[0]

        if len(categorias_encontradas) > 1:
            print(f"⚠️ Nome ambíguo, mais de uma categoria encontrada em '{arquivo}': "
                  f"{', '.join(categorias_encontradas)} — usando '{categoria_encontrada}'")
            registro_log.append({
                "arquivo": arquivo,
                "status": "AVISO - CATEGORIA AMBÍGUA",
                "detalhe": f"Categorias encontradas: {', '.join(categorias_encontradas)}. "
                           f"Usada: {categoria_encontrada}"
            })

        cat_info = dados_categorias[categoria_encontrada]
        cat_info["contem_arquivos"] = True

        caminho_completo = os.path.join(pasta_entrada, arquivo)

        try:
            pdf_original = pymupdf.open(caminho_completo)
        except Exception as e:
            print(f"❌ Erro ao abrir '{arquivo}': {e}")
            registro_log.append({
                "arquivo": arquivo,
                "status": "ERRO",
                "detalhe": f"Falha ao abrir o arquivo: {e}"
            })
            continue

        if len(pdf_original) == 0:
            print(f"⚠️ Arquivo vazio (0 páginas): {arquivo}")
            registro_log.append({
                "arquivo": arquivo,
                "status": "AVISO - ARQUIVO VAZIO",
                "detalhe": "PDF não contém páginas"
            })
            pdf_original.close()
            continue

        for num_pag in range(len(pdf_original)):
            if cat_info["posicao_na_pagina"] == 0:
                cat_info["pagina_atual"] = cat_info["pdf_saida"].new_page(
                    width=LARGURA_A4, height=ALTURA_A4
                )

            y_inicial = 0 if cat_info["posicao_na_pagina"] == 0 else ALTURA_ETIQUETA
            y_final = ALTURA_ETIQUETA if cat_info["posicao_na_pagina"] == 0 else ALTURA_A4

            margem_rodape = 65
            caixa_destino = pymupdf.Rect(10, y_inicial + 10, LARGURA_A4 - 10, y_final - margem_rodape)

            cat_info["pagina_atual"].show_pdf_page(
                caixa_destino, pdf_original, num_pag, keep_proportion=True
            )

            if cat_info["posicao_na_pagina"] == 0:
                cat_info["pagina_atual"].draw_line(
                    pymupdf.Point(0, ALTURA_ETIQUETA),
                    pymupdf.Point(LARGURA_A4, ALTURA_ETIQUETA),
                    color=(0.5, 0.5, 0.5),
                    width=1
                )

            caixa_rodape = pymupdf.Rect(15, y_final - margem_rodape + 5, LARGURA_A4 - 15, y_final - 5)

            html_conteudo = f"""
            <div style="font-family: sans-serif; color: black; line-height: 1.3;">
                <p style="font-size: 9pt; margin: 0; font-weight: bold;">
                    MATERIAL: {arquivo} &nbsp;|&nbsp; CLIENTE: {nome_cliente.upper()}
                </p>
                <p style="font-size: 8pt; margin: 2px 0 0 0; color: #333333;">
                    DATA/HORA: {data_hora_atual} &nbsp;|&nbsp; GERENTE OP: {nome_gerente} &nbsp;|&nbsp; PRODUTOR RESP: {nome_produtor}
                </p>
            </div>
            """
            cat_info["pagina_atual"].insert_htmlbox(caixa_rodape, html_conteudo)
            cat_info["posicao_na_pagina"] = 1 - cat_info["posicao_na_pagina"]
            cat_info["total_etiquetas"] += 1

        pdf_original.close()

        dimensao = extrair_dimensoes(arquivo)
        if dimensao:
            cat_info["area_total_m2"] += dimensao["area_m2"]
            detalhe_area = (
                f" | Medida: {dimensao['medida_bruta']} → "
                f"{dimensao['largura_m']:.2f}m x {dimensao['altura_m']:.2f}m = "
                f"{dimensao['area_m2']:.2f}m²"
            )
            if dimensao["unidade_corrigida"]:
                detalhe_area += " (unidade corrigida de XM para CM)"

            if categoria_encontrada in ROLOS_MATERIAL:
                largura_rolo_m = ROLOS_MATERIAL[categoria_encontrada]["largura_cm"] / 100
                resultado_corte = calcular_desperdicio_item(dimensao, largura_rolo_m)
                if resultado_corte:
                    cat_info["area_desperdicio_m2"] += resultado_corte["desperdicio_m2"]
                    cat_info["comprimento_rolo_usado_m"] += resultado_corte["peca_comprimento_m"]
                    detalhe_area += f" | Desperdício estimado: {resultado_corte['desperdicio_m2']:.2f}m²"
                else:
                    cat_info["itens_fora_do_rolo"].append(arquivo)
                    tipo_material = ROLOS_MATERIAL[categoria_encontrada]["tipo"]
                    artigo, ref = ("o", "rolo") if tipo_material == "rolo" else ("a", "chapa")
                    detalhe_area += f" | ⚠️ Peça mais larga que {artigo} {ref} — desperdício não calculado"
        else:
            detalhe_area = " | Medida não reconhecida no nome do arquivo"

        registro_log.append({
            "arquivo": arquivo,
            "status": "OK",
            "detalhe": f"Categoria: {categoria_encontrada} | Páginas processadas: {num_pag + 1}{detalhe_area}"
        })

    # Salva os arquivos individuais por categoria
    print("\n💾 Gerando arquivos individuais:")
    for cat in categorias:
        cat_info = dados_categorias[cat]
        if cat_info["contem_arquivos"]:
            nome_individual = os.path.join(pasta_saida, f"Checklist {nome_cliente.upper()} - {cat}.pdf")
            cat_info["pdf_saida"].save(nome_individual)
            print(f"✨ Gerado: {nome_individual}")

    # Monta o PDF unificado respeitando a ordem fixa: LONA, ADESIVO, PVC, PS, MDF
    # Também monta o sumário (TOC) e numera as páginas conforme vai inserindo o conteúdo
    print("\n📎 Montando PDF unificado:")
    toc = []  # lista de [nivel, titulo, numero_da_pagina] para pdf.set_toc()

    for cat in ORDEM_UNIFICADO:
        cat_info = dados_categorias[cat]
        if cat_info["contem_arquivos"]:
            pagina_inicio = len(pdf_unificado) + 1  # +1 porque set_toc usa páginas 1-indexed
            toc.append([1, f"{cat} ({cat_info['total_etiquetas']} etiquetas)", pagina_inicio])

            inserir_pagina_titulo(pdf_unificado, cat, cat_info["total_etiquetas"], LARGURA_A4, ALTURA_A4)
            pdf_unificado.insert_pdf(cat_info["pdf_saida"])
            print(f"  ➕ Seção adicionada: {cat} ({cat_info['total_etiquetas']} etiquetas)")

    # Fecha todos os PDFs individuais (agora que já foram usados no unificado)
    for cat in categorias:
        dados_categorias[cat]["pdf_saida"].close()

    if len(pdf_unificado) > 0:
        # Aplica o sumário (aparece como índice clicável em leitores de PDF)
        pdf_unificado.set_toc(toc)

        # Numera todas as páginas do unificado, no canto inferior direito
        numerar_paginas(pdf_unificado, LARGURA_A4, ALTURA_A4)

        nome_unificado = os.path.join(pasta_saida, f"Checklist {nome_cliente.upper()} - UNIFICADO.pdf")
        pdf_unificado.save(nome_unificado)
        print(f"\n🚀 UNIFICADO CRIADO: {nome_unificado}")

    pdf_unificado.close()

    # Gera o log de processamento em CSV na pasta de saída
    caminho_log = salvar_log(pasta_saida, nome_cliente, registro_log)
    print(f"📝 Log de processamento salvo em: {caminho_log}")

    # Gera a Ordem de Serviço (OS) resumida, em arquivo separado
    caminho_os = gerar_os(
        pasta_saida, nome_cliente, nome_gerente, nome_produtor,
        dados_categorias, categorias, ORDEM_UNIFICADO,
        LARGURA_A4, ALTURA_A4, data_hora_atual
    )
    print(f"📋 OS gerada em: {caminho_os}")

    # Resumo de área (m²) por categoria, pra conferência rápida de consumo de material
    print("\n📐 Resumo de área por categoria:")
    total_geral_area = 0.0
    for cat in ORDEM_UNIFICADO:
        cat_info = dados_categorias[cat]
        if cat_info["contem_arquivos"]:
            print(f"   {cat}: {cat_info['area_total_m2']:.2f} m²")
            total_geral_area += cat_info["area_total_m2"]
    print(f"   TOTAL GERAL: {total_geral_area:.2f} m²")

    # Estimativa de desperdício de material (modelo de corte sequencial)
    categorias_com_rolo = [c for c in ROLOS_MATERIAL if dados_categorias.get(c, {}).get("contem_arquivos")]
    if categorias_com_rolo:
        print("\n♻️  Estimativa de desperdício (corte sequencial, largura toda do material):")
        for cat in categorias_com_rolo:
            cat_info = dados_categorias[cat]
            tipo = ROLOS_MATERIAL[cat]["tipo"]
            comprimento_estoque_m = ROLOS_MATERIAL[cat]["comprimento_cm"] / 100
            comprimento_usado = cat_info["comprimento_rolo_usado_m"]
            unidades_necessarias = math.ceil(comprimento_usado / comprimento_estoque_m) if comprimento_estoque_m > 0 else 0
            unidade_label = "rolo(s)" if tipo == "rolo" else "chapa(s)"

            print(f"   {cat}: {cat_info['area_desperdicio_m2']:.2f} m² desperdiçados "
                  f"| {comprimento_usado:.2f} m usados "
                  f"(~{unidades_necessarias} {unidade_label} de {comprimento_estoque_m:.2f}m)")
            if cat_info["itens_fora_do_rolo"]:
                artigo, item_ref = ("o", "rolo") if tipo == "rolo" else ("a", "chapa")
                print(f"      ⚠️ {len(cat_info['itens_fora_do_rolo'])} peça(s) mais larga(s) que {artigo} {item_ref}, "
                      f"conferir manualmente: {', '.join(cat_info['itens_fora_do_rolo'])}")


def inserir_pagina_titulo(pdf_destino, nome_categoria, total_etiquetas, largura, altura):
    """
    Insere uma página de título compacta para separar cada categoria
    dentro do PDF unificado. A página fica bem menor que uma A4 inteira,
    com apenas 2cm de espaço abaixo da caixa de título antes do
    conteúdo seguinte começar.
    """
    CM = 28.35  # 1 cm em pontos (pt)

    altura_caixa_titulo = 100        # altura da caixa com o texto do título
    margem_topo = 15
    margem_inferior = 2 * CM         # 2 cm de distância até o conteúdo seguinte

    altura_titulo = margem_topo + altura_caixa_titulo + margem_inferior

    pagina = pdf_destino.new_page(width=largura, height=altura_titulo)

    # Faixa colorida de fundo, só para dar destaque visual
    faixa = pymupdf.Rect(10, margem_topo, largura - 10, margem_topo + altura_caixa_titulo)
    pagina.draw_rect(faixa, color=(0.2, 0.2, 0.2), fill=(0.93, 0.93, 0.93), width=1)

    html_titulo = f"""
    <div style="
        font-family: sans-serif;
        text-align: center;
        color: #1a1a1a;
    ">
        <p style="font-size: 28pt; font-weight: bold; margin: 0;">
            {nome_categoria}
        </p>
        <p style="font-size: 12pt; font-weight: normal; margin: 4px 0 0 0; color: #444444;">
            {total_etiquetas} etiqueta{"s" if total_etiquetas != 1 else ""}
        </p>
    </div>
    """
    pagina.insert_htmlbox(faixa, html_titulo)


def numerar_paginas(pdf_documento, largura_referencia, altura_referencia):
    """
    Adiciona 'Página X de Y' no canto inferior direito de cada página
    do documento. Como as páginas de título têm altura diferente das
    páginas de etiquetas, o número é sempre ancorado a partir do
    rodapé de cada página (não de uma altura fixa).
    """
    total_paginas = len(pdf_documento)

    for i, pagina in enumerate(pdf_documento, start=1):
        largura_pag = pagina.rect.width
        altura_pag = pagina.rect.height

        caixa_numero = pymupdf.Rect(largura_pag - 110, altura_pag - 18, largura_pag - 10, altura_pag - 4)
        texto = f"Página {i} de {total_paginas}"
        pagina.insert_textbox(
            caixa_numero, texto,
            fontsize=7, fontname="helv", color=(0.4, 0.4, 0.4),
            align=pymupdf.TEXT_ALIGN_RIGHT
        )


def salvar_log(pasta_saida, nome_cliente, registro_log):
    """
    Salva um CSV com o resultado do processamento de cada arquivo:
    OK, IGNORADO, ERRO ou AVISO, com detalhes de cada caso.
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    caminho_log = os.path.join(pasta_saida, f"log_processamento_{nome_cliente.upper()}_{timestamp}.csv")

    with open(caminho_log, mode="w", newline="", encoding="utf-8-sig") as f:
        escritor = csv.DictWriter(f, fieldnames=["arquivo", "status", "detalhe"])
        escritor.writeheader()
        for linha in registro_log:
            escritor.writerow(linha)

    return caminho_log


def gerar_os(pasta_saida, nome_cliente, nome_gerente, nome_produtor,
             dados_categorias, categorias, ordem_categorias,
             largura, altura, data_hora_atual):
    """
    Gera um PDF separado com a Ordem de Serviço (OS) resumida: dados do
    cliente/gerente/produtor, checklist de materiais com a quantidade de
    etiquetas de cada categoria, campo de observações e assinaturas.
    """
    CM = 28.35

    pdf_os = pymupdf.open()
    pagina = pdf_os.new_page(width=largura, height=altura)

    margem = 40
    y = margem

    # Cabeçalho
    caixa_cabecalho = pymupdf.Rect(margem, y, largura - margem, y + 70)
    html_cabecalho = f"""
    <div style="font-family: sans-serif;">
        <p style="font-size: 22pt; font-weight: bold; margin: 0; color: #1a1a1a;">
            ORDEM DE SERVIÇO UNY CV
        </p>
        <p style="font-size: 16pt; margin: 4px 0 0 0; color: #333333;">
            {nome_cliente.upper()}
        </p>
    </div>
    """
    pagina.insert_htmlbox(caixa_cabecalho, html_cabecalho)
    y += 80

    pagina.draw_line(pymupdf.Point(margem, y), pymupdf.Point(largura - margem, y),
                      color=(0.6, 0.6, 0.6), width=1)
    y += 18

    # Dados gerais: data, gerente, produtor
    caixa_dados = pymupdf.Rect(margem, y, largura - margem, y + 50)
    html_dados = f"""
    <div style="font-family: sans-serif; font-size: 11pt; color: #1a1a1a;">
        <p style="margin: 0 0 4px 0;"><b>Data:</b> {data_hora_atual}</p>
        <p style="margin: 0 0 4px 0;"><b>Gerente operacional:</b> {nome_gerente}</p>
        <p style="margin: 0;"><b>Produtor responsável:</b> {nome_produtor}</p>
    </div>
    """
    pagina.insert_htmlbox(caixa_dados, html_dados)
    y += 65

    # Checklist de materiais com quantidade de etiquetas por categoria
    caixa_titulo_materiais = pymupdf.Rect(margem, y, largura - margem, y + 22)
    pagina.insert_htmlbox(
        caixa_titulo_materiais,
        '<p style="font-family: sans-serif; font-size: 12pt; font-weight: bold; margin: 0;">MATERIAIS</p>'
    )
    y += 30

    for cat in ordem_categorias:
        cat_info = dados_categorias[cat]
        marcado = "☑" if cat_info["contem_arquivos"] else "☐"
        qtd = cat_info["total_etiquetas"]
        area = cat_info["area_total_m2"]

        caixa_linha = pymupdf.Rect(margem, y, largura - margem, y + 20)
        html_linha = f"""
        <div style="font-family: sans-serif; font-size: 12pt; color: #1a1a1a;">
            {marcado}&nbsp;&nbsp;{cat}
            <span style="float: right; color: #444444;">{qtd} etiqueta{'s' if qtd != 1 else ''} · {area:.2f} m²</span>
        </div>
        """
        pagina.insert_htmlbox(caixa_linha, html_linha)
        y += 24

    total_area_geral = sum(dados_categorias[c]["area_total_m2"] for c in ordem_categorias)
    caixa_total = pymupdf.Rect(margem, y, largura - margem, y + 20)
    html_total = f"""
    <div style="font-family: sans-serif; font-size: 12pt; font-weight: bold; color: #1a1a1a;">
        TOTAL
        <span style="float: right;">{total_area_geral:.2f} m²</span>
    </div>
    """
    pagina.insert_htmlbox(caixa_total, html_total)
    y += 26

    y += 15
    pagina.draw_line(pymupdf.Point(margem, y), pymupdf.Point(largura - margem, y),
                      color=(0.6, 0.6, 0.6), width=1)
    y += 20

    # Campo de observações (caixa vazia para preenchimento manual)
    caixa_titulo_obs = pymupdf.Rect(margem, y, largura - margem, y + 20)
    pagina.insert_htmlbox(
        caixa_titulo_obs,
        '<p style="font-family: sans-serif; font-size: 12pt; font-weight: bold; margin: 0;">OBSERVAÇÕES</p>'
    )
    y += 26

    altura_caixa_obs = 4 * CM
    caixa_obs = pymupdf.Rect(margem, y, largura - margem, y + altura_caixa_obs)
    pagina.draw_rect(caixa_obs, color=(0.6, 0.6, 0.6), width=1)
    y += altura_caixa_obs + 40

    # Assinaturas, lado a lado
    largura_util = largura - 2 * margem
    metade = largura_util / 2

    linha_assinatura_1 = pymupdf.Rect(margem, y, margem + metade - 20, y)
    linha_assinatura_2 = pymupdf.Rect(margem + metade + 20, y, largura - margem, y)

    pagina.draw_line(pymupdf.Point(margem, y), pymupdf.Point(margem + metade - 20, y),
                      color=(0.3, 0.3, 0.3), width=1)
    pagina.draw_line(pymupdf.Point(margem + metade + 20, y), pymupdf.Point(largura - margem, y),
                      color=(0.3, 0.3, 0.3), width=1)

    caixa_label_1 = pymupdf.Rect(margem, y + 5, margem + metade - 20, y + 22)
    caixa_label_2 = pymupdf.Rect(margem + metade + 20, y + 5, largura - margem, y + 22)

    pagina.insert_htmlbox(
        caixa_label_1,
        '<p style="font-family: sans-serif; font-size: 10pt; color: #444444; margin: 0;">Assinatura Produção</p>'
    )
    pagina.insert_htmlbox(
        caixa_label_2,
        '<p style="font-family: sans-serif; font-size: 10pt; color: #444444; margin: 0;">Assinatura Conferência</p>'
    )

    nome_os = os.path.join(pasta_saida, f"OS - {nome_cliente.upper()}.pdf")
    pdf_os.save(nome_os)
    pdf_os.close()

    return nome_os


def parse_argumentos():
    parser = argparse.ArgumentParser(
        description="Gera etiquetas separadas por categoria (Lona, Adesivo, PVC, PS, MDF) "
                    "a partir de PDFs de uma pasta de entrada, e monta um PDF unificado."
    )
    parser.add_argument(
        "--pasta-entrada", dest="pasta_entrada", default="entrada",
        help="Pasta com os PDFs de origem (padrão: 'entrada')"
    )
    parser.add_argument(
        "--cliente", dest="cliente", required=True,
        help="Nome do cliente (aparece no rodapé das etiquetas e no nome dos arquivos)"
    )
    parser.add_argument(
        "--gerente", dest="gerente", required=True,
        help="Nome do gerente operacional"
    )
    parser.add_argument(
        "--produtor", dest="produtor", required=True,
        help="Nome do produtor responsável"
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_argumentos()
    processar_etiquetas(
        pasta_entrada=args.pasta_entrada,
        nome_cliente=args.cliente,
        nome_gerente=args.gerente,
        nome_produtor=args.produtor,
    )