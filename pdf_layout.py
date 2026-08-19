"""
Funções de montagem visual do PDF (páginas de título e numeração de
página), separadas do fluxo principal de processamento.
"""
import pymupdf

from branding import inserir_logo

# largura reservada para o logo dentro da faixa de título, com uma
# margem interna própria (não encosta na borda nem no texto)
_LARGURA_LOGO = 110
_MARGEM_LOGO = 12


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

    # Logo no canto esquerdo da faixa, com uma margem própria
    caixa_logo = pymupdf.Rect(
        faixa.x0 + _MARGEM_LOGO, faixa.y0 + _MARGEM_LOGO,
        faixa.x0 + _MARGEM_LOGO + _LARGURA_LOGO, faixa.y1 - _MARGEM_LOGO,
    )
    inserir_logo(pagina, caixa_logo, alinhamento="left")

    # O texto do título continua centralizado no espaço que sobra à
    # direita do logo, para o logo não invadir nem descentralizar o
    # título em relação ao restante da faixa.
    caixa_titulo = pymupdf.Rect(caixa_logo.x1 + _MARGEM_LOGO, faixa.y0, faixa.x1, faixa.y1)
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
    pagina.insert_htmlbox(caixa_titulo, html_titulo)


def estampar_conferencia_local(pagina, largura, y_inicial, y_final, sobra_rodape):
    """
    Acrescenta, numa etiqueta, uma linha extra dentro do rodapé já
    existente com um checkbox de "conferido no local" e um aviso em
    vermelho sobre a responsabilidade do produtor. Usada só na cópia
    das páginas que vai para o PDF unificado (os checklists individuais
    por categoria continuam sem isso).

    Reaproveita o espaço que já sobra no rodapé (as duas linhas de
    texto atuais — material/cliente e data/gerente/produtor — não
    preenchem toda a faixa reservada), então a área da arte do produto
    não muda de tamanho. 'sobra_rodape' é o valor devolvido pelo
    insert_htmlbox() daquelas duas linhas — como o nome do arquivo pode
    ser longo e quebrar em 2 linhas, um deslocamento fixo causava
    sobreposição; usar a sobra real garante que a linha nova sempre
    comece logo depois do texto existente, não importa quantas linhas
    ele ocupou.
    """
    margem_rodape = 65  # mesmo valor usado em processamento.py ao montar a etiqueta
    altura_caixa_rodape = margem_rodape - 10
    x0, x1 = 15, largura - 15
    y0 = (y_final - margem_rodape + 5) + (altura_caixa_rodape - sobra_rodape) + 2
    y1 = y_final - 5
    if y1 - y0 < 12:
        y0 = y1 - 12

    caixa = pymupdf.Rect(x0, y0, x1, y1)
    html = """
    <table style="width: 100%; border-collapse: collapse;">
        <tr>
            <td style="width: 76%; padding-right: 6px; vertical-align: middle;">
                <div style="border: 1px solid #cc0000; padding: 2px 5px;">
                    <p style="font-family: sans-serif; font-size: 6.5pt; font-weight: bold; color: #cc0000; margin: 0; line-height: 1.25;">
                        Confer&ecirc;ncia do material &eacute; de responsabilidade do produtor.
                        Trabalho extra n&atilde;o consta nessa lista!
                    </p>
                </div>
            </td>
            <td style="width: 24%; text-align: center; vertical-align: middle;">
                <p style="font-family: sans-serif; font-size: 9pt; margin: 0; color: #1a1a1a;">☐</p>
                <p style="font-family: sans-serif; font-size: 5.5pt; margin: 0; color: #444444;">CONFERIDO NO LOCAL</p>
            </td>
        </tr>
    </table>
    """
    pagina.insert_htmlbox(caixa, html)


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
