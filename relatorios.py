"""
Geração dos relatórios de saída: o log CSV do processamento e a Ordem
de Serviço (OS) resumida em PDF.
"""
import csv
import os
import re
from datetime import datetime

import pymupdf

from branding import inserir_logo, CAMINHO_LOGO_GUI
from dimensoes import formatar_variante

LARGURA_OS = 595.27  # A4
ALTURA_OS = 841.89
MARGEM_OS = 36
ALTURA_THUMB_OS = 42
LARGURA_CHECKBOX_OS = 20
ALTURA_ITEM_OS = 54
ALTURA_GRUPO_OS = 16
ALTURA_LOGO_OS = 24

# paletas (fundo claro, texto escuro da mesma família) pra colorir a
# etiqueta de categoria de cada item, atribuídas por posição na ordem
# configurada — assim funciona pra qualquer categoria cadastrada, sem
# precisar mapear cor por nome de material
_PALETA_CATEGORIAS = [
    ("#E6F1FB", "#0C447C"),
    ("#FAEEDA", "#633806"),
    ("#FAECE7", "#712B13"),
    ("#EEEDFE", "#3C3489"),
    ("#E1F5EE", "#085041"),
    ("#FBEAF0", "#72243E"),
]


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


def _cor_categoria(categoria, ordem_categorias):
    indice = ordem_categorias.index(categoria) if categoria in ordem_categorias else 0
    return _PALETA_CATEGORIAS[indice % len(_PALETA_CATEGORIAS)]


def _descricao_arquivo(nome_arquivo):
    """
    Nome do arquivo sem o prefixo de quantidade ("1UN ") e sem a
    extensão, só como referência visual do item. Evita tentar adivinhar
    qual pedaço do nome é "o nome do produto" — isso varia demais de
    pedido pra pedido pra ter uma regra confiável.
    """
    sem_qtd = re.sub(r'^\s*\d+\s*UN\s*', '', nome_arquivo, flags=re.IGNORECASE)
    sem_extensao = re.sub(r'\.pdf$', '', sem_qtd, flags=re.IGNORECASE)
    return sem_extensao.strip() or nome_arquivo


def _nova_pagina_os(pdf_os, nome_cliente, nome_gerente, nome_produtor, data_hora_atual, caixas_pagina):
    """
    Cria uma página A4 nova com o cabeçalho (logo + cliente + gerente/
    produtor/data), repetido em toda página — impressa em folhas soltas,
    cada uma precisa se identificar sozinha. O número da página só é
    escrito depois, quando o total de páginas for conhecido; por isso
    guarda a caixa reservada em 'caixas_pagina' pra preencher no final.
    """
    pagina = pdf_os.new_page(width=LARGURA_OS, height=ALTURA_OS)
    y = MARGEM_OS

    caixa_logo = pymupdf.Rect(MARGEM_OS, y, MARGEM_OS + 70, y + ALTURA_LOGO_OS)
    inserir_logo(pagina, caixa_logo, alinhamento="left", caminho=CAMINHO_LOGO_GUI)

    caixa_texto = pymupdf.Rect(MARGEM_OS + 80, y - 2, LARGURA_OS - MARGEM_OS - 65, y + 42)
    html_texto = f"""
    <div style="font-family: sans-serif;">
        <p style="font-size: 7pt; color: #999999; margin: 0 0 1px 0; letter-spacing: 0.5px;">ORDEM DE SERVIÇO &mdash; IMPRESSA</p>
        <p style="font-size: 13pt; font-weight: bold; margin: 0; color: #141414;">{nome_cliente.upper()}</p>
        <p style="font-size: 7.5pt; color: #666666; margin: 2px 0 0 0;">Gerente: {nome_gerente} &nbsp;·&nbsp; Produtor: {nome_produtor} &nbsp;·&nbsp; {data_hora_atual}</p>
    </div>
    """
    pagina.insert_htmlbox(caixa_texto, html_texto)

    # guarda o ÍNDICE da página (não o objeto Page) — o objeto fica
    # inválido depois que outras páginas são criadas no mesmo documento
    caixa_pagina = pymupdf.Rect(LARGURA_OS - MARGEM_OS - 65, y, LARGURA_OS - MARGEM_OS, y + 12)
    caixas_pagina.append((len(pdf_os) - 1, caixa_pagina))

    y += ALTURA_LOGO_OS + 18
    pagina.draw_line(pymupdf.Point(MARGEM_OS, y), pymupdf.Point(LARGURA_OS - MARGEM_OS, y),
                      color=(0.2, 0.2, 0.2), width=1)
    y += 10

    return pagina, y


def _desenhar_item_os(pagina, y, x_thumb, x_texto, largura_texto, item, cor_fundo, cor_texto):
    rect_thumb = pymupdf.Rect(
        x_thumb, y + (ALTURA_ITEM_OS - ALTURA_THUMB_OS) / 2,
        x_thumb + ALTURA_THUMB_OS, y + (ALTURA_ITEM_OS - ALTURA_THUMB_OS) / 2 + ALTURA_THUMB_OS,
    )
    inseriu_thumb = False
    if item.get("thumbnail_bytes"):
        try:
            pagina.insert_image(rect_thumb, stream=item["thumbnail_bytes"])
            inseriu_thumb = True
        except Exception:
            inseriu_thumb = False
    if not inseriu_thumb:
        pagina.draw_rect(rect_thumb, color=(0.85, 0.85, 0.85), fill=(0.94, 0.94, 0.94), width=0.5)

    dimensao = item.get("dimensao")
    if dimensao:
        area_texto = f"{dimensao['area_m2']:.2f} m² ({dimensao['largura_m']:.2f} x {dimensao['altura_m']:.2f} m)"
    else:
        area_texto = "Medida não informada"

    variante = item.get("variante")
    html_variante = (
        f'<span style="font-size: 7pt; color: #666666; margin-left: 5px;">{formatar_variante(variante)}</span>'
        if variante else ""
    )

    caixa_texto = pymupdf.Rect(x_texto, y, x_texto + largura_texto, y + ALTURA_ITEM_OS)
    html_item = f"""
    <div style="font-family: sans-serif;">
        <div style="font-size: 7.5pt; font-weight: bold; color: {cor_texto}; background-color: {cor_fundo}; display: inline-block; padding: 2px 7px;">{item['categoria']}</div>{html_variante}
        <span style="float: right; font-size: 8pt; color: #666666;">{item['quantidade']} UN</span>
        <p style="font-size: 8.5pt; margin: 4px 0 2px 0; color: #444444; line-height: 1.25;">{_descricao_arquivo(item['arquivo'])}</p>
        <p style="font-size: 9pt; font-weight: bold; margin: 0; color: #1a1a1a;">{area_texto}</p>
    </div>
    """
    pagina.insert_htmlbox(caixa_texto, html_item)

    rect_checkbox = pymupdf.Rect(
        LARGURA_OS - MARGEM_OS - LARGURA_CHECKBOX_OS, y + (ALTURA_ITEM_OS - LARGURA_CHECKBOX_OS) / 2,
        LARGURA_OS - MARGEM_OS, y + (ALTURA_ITEM_OS - LARGURA_CHECKBOX_OS) / 2 + LARGURA_CHECKBOX_OS,
    )
    pagina.draw_rect(rect_checkbox, color=(0.1, 0.1, 0.1), width=1.8)

    y += ALTURA_ITEM_OS
    pagina.draw_line(pymupdf.Point(MARGEM_OS, y), pymupdf.Point(LARGURA_OS - MARGEM_OS, y),
                      color=(0.88, 0.89, 0.9), width=0.6)
    return y


def gerar_os(pasta_saida, nome_cliente, nome_gerente, nome_produtor,
             itens, dados_categorias, ordem_categorias, data_hora_atual):
    """
    Gera a Ordem de Serviço (OS) paginada em folhas A4, pronta pra
    impressão: logo da empresa repetido em cada página, itens agrupados
    por material (mesma ordem do checklist unificado) com um cabeçalho
    de texto simples antes de cada grupo, miniatura da arte de cada
    produto como referência visual, e um checkbox grande o bastante pra
    ser marcado à caneta durante a conferência no local. A quantidade de
    itens por página é calculada pra aproveitar bem a folha, não é um
    número fixo. No final, o mesmo resumo de sempre com o subtotal de
    m² separado por material (nunca somando materiais diferentes).
    """
    categorias_com_item = [c for c in ordem_categorias if dados_categorias[c]["contem_arquivos"]]

    x_thumb = MARGEM_OS
    x_texto = x_thumb + ALTURA_THUMB_OS + 10
    largura_texto = LARGURA_OS - MARGEM_OS - LARGURA_CHECKBOX_OS - 8 - x_texto
    limite_y = ALTURA_OS - MARGEM_OS

    pdf_os = pymupdf.open()
    caixas_pagina = []
    pagina, y = _nova_pagina_os(pdf_os, nome_cliente, nome_gerente, nome_produtor, data_hora_atual, caixas_pagina)

    for cat in categorias_com_item:
        cor_fundo, cor_texto = _cor_categoria(cat, ordem_categorias)
        itens_categoria = [i for i in itens if i["categoria"] == cat]

        if y + ALTURA_GRUPO_OS + ALTURA_ITEM_OS > limite_y:
            pagina, y = _nova_pagina_os(pdf_os, nome_cliente, nome_gerente, nome_produtor, data_hora_atual, caixas_pagina)

        pagina.insert_htmlbox(
            pymupdf.Rect(MARGEM_OS, y, LARGURA_OS - MARGEM_OS, y + ALTURA_GRUPO_OS - 4),
            f'<p style="font-family: sans-serif; font-size: 10pt; font-weight: bold; color: {cor_texto}; margin: 0;">{cat}</p>'
        )
        y += ALTURA_GRUPO_OS

        for item in itens_categoria:
            if y + ALTURA_ITEM_OS > limite_y:
                pagina, y = _nova_pagina_os(pdf_os, nome_cliente, nome_gerente, nome_produtor, data_hora_atual, caixas_pagina)
                # a categoria continua na página nova: repete o cabeçalho
                # simples pra não perder o contexto de qual material é
                pagina.insert_htmlbox(
                    pymupdf.Rect(MARGEM_OS, y, LARGURA_OS - MARGEM_OS, y + ALTURA_GRUPO_OS - 4),
                    f'<p style="font-family: sans-serif; font-size: 10pt; font-weight: bold; color: {cor_texto}; margin: 0;">{cat} (continuação)</p>'
                )
                y += ALTURA_GRUPO_OS

            y = _desenhar_item_os(pagina, y, x_thumb, x_texto, largura_texto, item, cor_fundo, cor_texto)

    # Resumo: subtotal de m² separado por material — nunca soma
    # materiais diferentes num único número
    altura_resumo = 24 + len(categorias_com_item) * 20 + 30
    if y + altura_resumo > limite_y:
        pagina, y = _nova_pagina_os(pdf_os, nome_cliente, nome_gerente, nome_produtor, data_hora_atual, caixas_pagina)
    else:
        y += 10

    pagina.insert_htmlbox(
        pymupdf.Rect(MARGEM_OS, y, LARGURA_OS - MARGEM_OS, y + 14),
        '<p style="font-family: sans-serif; font-size: 8pt; font-weight: bold; color: #999999; margin: 0; text-transform: uppercase;">Subtotal por material</p>'
    )
    y += 20

    for cat in categorias_com_item:
        cat_info = dados_categorias[cat]
        qtd_itens_categoria = sum(1 for i in itens if i["categoria"] == cat)
        _, cor_texto = _cor_categoria(cat, ordem_categorias)

        if y + 20 > limite_y:
            pagina, y = _nova_pagina_os(pdf_os, nome_cliente, nome_gerente, nome_produtor, data_hora_atual, caixas_pagina)

        html_linha = f"""
        <div style="font-family: sans-serif; font-size: 9pt; color: #333333;">
            <span style="color: {cor_texto};">●</span>&nbsp;
            {cat} · {qtd_itens_categoria} item{'s' if qtd_itens_categoria != 1 else ''}
            <span style="float: right; font-weight: bold; color: #1a1a1a;">{cat_info['area_total_m2']:.2f} m²</span>
        </div>
        """
        pagina.insert_htmlbox(pymupdf.Rect(MARGEM_OS, y, LARGURA_OS - MARGEM_OS, y + 16), html_linha)
        y += 20

    if y + 26 > limite_y:
        pagina, y = _nova_pagina_os(pdf_os, nome_cliente, nome_gerente, nome_produtor, data_hora_atual, caixas_pagina)
    else:
        y += 4
    pagina.draw_line(pymupdf.Point(MARGEM_OS, y), pymupdf.Point(LARGURA_OS - MARGEM_OS, y),
                      color=(0.85, 0.87, 0.89), width=0.7)
    y += 6
    pagina.insert_htmlbox(
        pymupdf.Rect(MARGEM_OS, y, LARGURA_OS - MARGEM_OS, y + 16),
        f'<p style="font-family: sans-serif; font-size: 8pt; color: #999999; margin: 0;">{len(itens)} itens no total</p>'
    )

    # numera as páginas só agora, que o total já é conhecido — busca a
    # página pelo índice de novo, em vez de reusar o objeto Page salvo
    # antes (fica inválido depois que outras páginas são criadas)
    total_paginas = len(pdf_os)
    for i, (indice_pagina, caixa) in enumerate(caixas_pagina, start=1):
        pdf_os[indice_pagina].insert_htmlbox(
            caixa,
            f'<p style="font-family: sans-serif; font-size: 7.5pt; color: #999999; margin: 0; text-align: right;">Página {i} de {total_paginas}</p>'
        )

    nome_os = os.path.join(pasta_saida, f"OS - {nome_cliente.upper()}.pdf")
    # garbage=4 remove os objetos de fonte duplicados que o insert_htmlbox
    # cria a cada chamada (sem isso o arquivo fica ordens de grandeza
    # maior do que precisa)
    pdf_os.save(nome_os, garbage=4, deflate=True)
    pdf_os.close()

    return nome_os
