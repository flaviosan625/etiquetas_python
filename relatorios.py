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

LARGURA_OS = 420

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


def gerar_os(pasta_saida, nome_cliente, nome_gerente, nome_produtor,
             itens, dados_categorias, ordem_categorias, data_hora_atual):
    """
    Gera a Ordem de Serviço (OS) em formato de lista rolável, pensada
    pra ser aberta e conferida pelo celular (não para impressão): logo
    da empresa, um cartão por produto — miniatura da arte, categoria,
    quantidade, medida e m², e um checkbox pra ir marcando conforme vai
    sendo produzido — e um resumo final com o subtotal de m² separado
    por material (nunca somando materiais diferentes num único número).
    """
    margem = 18
    altura_thumb = 52
    altura_item = 80
    altura_cabecalho = 118

    altura_cabecalho_grupo = 22

    categorias_com_item = [c for c in ordem_categorias if dados_categorias[c]["contem_arquivos"]]
    altura_rodape = 40 + len(categorias_com_item) * 20 + 34
    altura_pagina = max(
        altura_cabecalho + len(categorias_com_item) * altura_cabecalho_grupo
        + len(itens) * altura_item + altura_rodape + margem,
        300,
    )

    pdf_os = pymupdf.open()
    pagina = pdf_os.new_page(width=LARGURA_OS, height=altura_pagina)

    y = margem

    # Cabeçalho: logo + cliente + gerente/produtor/data
    caixa_logo = pymupdf.Rect(margem, y, margem + 90, y + 34)
    inserir_logo(pagina, caixa_logo, alinhamento="left", caminho=CAMINHO_LOGO_GUI)
    y += 42

    caixa_cliente = pymupdf.Rect(margem, y, LARGURA_OS - margem, y + 40)
    html_cliente = f"""
    <div style="font-family: sans-serif;">
        <p style="font-size: 8pt; color: #999999; margin: 0 0 1px 0;">ORDEM DE SERVIÇO</p>
        <p style="font-size: 13pt; font-weight: bold; margin: 0; color: #141414;">{nome_cliente.upper()}</p>
    </div>
    """
    pagina.insert_htmlbox(caixa_cliente, html_cliente)
    y += 40

    caixa_meta = pymupdf.Rect(margem, y, LARGURA_OS - margem, y + 14)
    html_meta = f"""
    <div style="font-family: sans-serif; font-size: 7.5pt; color: #666666;">
        Gerente: {nome_gerente} &nbsp;·&nbsp; Produtor: {nome_produtor} &nbsp;·&nbsp; {data_hora_atual}
    </div>
    """
    pagina.insert_htmlbox(caixa_meta, html_meta)
    y += 20

    pagina.draw_line(pymupdf.Point(margem, y), pymupdf.Point(LARGURA_OS - margem, y),
                      color=(0.85, 0.87, 0.89), width=0.7)
    y += 4

    # Cartões por produto, agrupados por material — mesma ordem de
    # separação usada no PDF unificado das etiquetas, só que num
    # cabeçalho simples de texto em vez de uma página de título inteira
    # (aqui é uma lista pra rolar no celular, não faz sentido ter tanto
    # destaque quanto lá).
    largura_checkbox = 18
    x_thumb = margem
    x_texto = x_thumb + altura_thumb + 10
    largura_texto = LARGURA_OS - margem - largura_checkbox - 8 - x_texto

    for cat in categorias_com_item:
        cor_fundo, cor_texto = _cor_categoria(cat, ordem_categorias)

        caixa_grupo = pymupdf.Rect(margem, y, LARGURA_OS - margem, y + altura_cabecalho_grupo - 6)
        pagina.insert_htmlbox(
            caixa_grupo,
            f'<p style="font-family: sans-serif; font-size: 10pt; font-weight: bold; color: {cor_texto}; margin: 0;">{cat}</p>'
        )
        y += altura_cabecalho_grupo

        for item in [i for i in itens if i["categoria"] == cat]:
            rect_thumb = pymupdf.Rect(
                x_thumb, y + (altura_item - altura_thumb) / 2,
                x_thumb + altura_thumb, y + (altura_item - altura_thumb) / 2 + altura_thumb,
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
            if variante:
                html_variante = f'<span style="font-size: 7pt; color: #666666; margin-left: 5px;">{formatar_variante(variante)}</span>'
            else:
                html_variante = ""

            caixa_texto = pymupdf.Rect(x_texto, y, x_texto + largura_texto, y + altura_item)
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
                LARGURA_OS - margem - largura_checkbox, y + (altura_item - largura_checkbox) / 2,
                LARGURA_OS - margem, y + (altura_item - largura_checkbox) / 2 + largura_checkbox,
            )
            pagina.draw_rect(rect_checkbox, color=(0.65, 0.65, 0.65), width=1.2)

            y += altura_item
            pagina.draw_line(pymupdf.Point(margem, y), pymupdf.Point(LARGURA_OS - margem, y),
                              color=(0.92, 0.93, 0.94), width=0.6)

    # Resumo: subtotal de m² separado por material — nunca soma
    # materiais diferentes num único número
    y += 10
    caixa_titulo_resumo = pymupdf.Rect(margem, y, LARGURA_OS - margem, y + 14)
    pagina.insert_htmlbox(
        caixa_titulo_resumo,
        '<p style="font-family: sans-serif; font-size: 8pt; font-weight: bold; color: #999999; margin: 0; text-transform: uppercase;">Subtotal por material</p>'
    )
    y += 20

    for cat in categorias_com_item:
        cat_info = dados_categorias[cat]
        qtd_itens_categoria = sum(1 for i in itens if i["categoria"] == cat)
        _, cor_texto = _cor_categoria(cat, ordem_categorias)

        caixa_linha = pymupdf.Rect(margem, y, LARGURA_OS - margem, y + 16)
        html_linha = f"""
        <div style="font-family: sans-serif; font-size: 9pt; color: #333333;">
            <span style="color: {cor_texto};">●</span>&nbsp;
            {cat} · {qtd_itens_categoria} item{'s' if qtd_itens_categoria != 1 else ''}
            <span style="float: right; font-weight: bold; color: #1a1a1a;">{cat_info['area_total_m2']:.2f} m²</span>
        </div>
        """
        pagina.insert_htmlbox(caixa_linha, html_linha)
        y += 20

    y += 4
    pagina.draw_line(pymupdf.Point(margem, y), pymupdf.Point(LARGURA_OS - margem, y),
                      color=(0.85, 0.87, 0.89), width=0.7)
    y += 6
    caixa_total_itens = pymupdf.Rect(margem, y, LARGURA_OS - margem, y + 16)
    pagina.insert_htmlbox(
        caixa_total_itens,
        f'<p style="font-family: sans-serif; font-size: 8pt; color: #999999; margin: 0;">{len(itens)} itens no total</p>'
    )

    nome_os = os.path.join(pasta_saida, f"OS - {nome_cliente.upper()}.pdf")
    # garbage=4 remove os objetos de fonte duplicados que o insert_htmlbox
    # cria a cada chamada (sem isso o arquivo fica ordens de grandeza
    # maior do que precisa — ruim justamente pra um documento pensado
    # pra ser leve e aberto pelo celular)
    pdf_os.save(nome_os, garbage=4, deflate=True)
    pdf_os.close()

    return nome_os
