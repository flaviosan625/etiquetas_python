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


_ALTURA_BANNER_CATEGORIA = 60
_MARGEM_BANNER = 15
_LARGURA_LOGO_BANNER = 75


def iniciar_pagina_com_banner(pdf_destino, largura, altura, nome_categoria):
    """
    Cria uma página nova de etiquetas com uma faixa compacta no topo
    (logo + nome da categoria) em vez de uma página de título separada
    só pra isso — na impressão, uma página só pro título gastava uma
    folha A4 inteira quase em branco antes das etiquetas de verdade.
    Essa faixa fica na mesma folha da primeira etiqueta da categoria.

    A contagem de etiquetas só é conhecida no final do processamento
    (os arquivos ainda estão sendo lidos quando essa função é chamada),
    então o texto "N etiquetas" é preenchido depois, numa caixa
    reservada — por isso a função devolve essa caixa junto.

    Devolve (y_conteudo, caixa_contagem): y_conteudo é a partir de onde
    o conteúdo abaixo do banner pode começar; caixa_contagem é o
    retângulo reservado pro texto da contagem.
    """
    pagina = pdf_destino.new_page(width=largura, height=altura)

    faixa = pymupdf.Rect(10, _MARGEM_BANNER, largura - 10, _MARGEM_BANNER + _ALTURA_BANNER_CATEGORIA)
    pagina.draw_rect(faixa, color=(0.2, 0.2, 0.2), fill=(0.93, 0.93, 0.93), width=1)

    caixa_logo = pymupdf.Rect(
        faixa.x0 + 10, faixa.y0 + 8, faixa.x0 + 10 + _LARGURA_LOGO_BANNER, faixa.y1 - 8,
    )
    inserir_logo(pagina, caixa_logo, alinhamento="left")

    caixa_contagem = pymupdf.Rect(faixa.x1 - 140, faixa.y0, faixa.x1 - 12, faixa.y1)

    caixa_nome = pymupdf.Rect(caixa_logo.x1 + 14, faixa.y0, caixa_contagem.x0 - 8, faixa.y1)
    html_nome = f"""
    <div style="font-family: sans-serif; color: #1a1a1a;">
        <p style="font-size: 20pt; font-weight: bold; margin: 17px 0 0 0;">{nome_categoria}</p>
    </div>
    """
    pagina.insert_htmlbox(caixa_nome, html_nome)

    y_conteudo = faixa.y1 + 12
    return pagina, y_conteudo, caixa_contagem


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


def numerar_paginas_a_partir_de(pdf_documento, indice_inicio):
    """
    Como numerar_paginas, mas só escreve nas páginas a partir de
    'indice_inicio' (0-based) — usada ao colar páginas novas num
    checklist unificado que já existe em disco, pra nunca desenhar em
    cima de uma página antiga (pode já estar impressa fisicamente). As
    páginas antigas mantêm o "de Y" de quando foram numeradas a
    primeira vez, mesmo que o total do documento tenha crescido desde
    então — é o preço de nunca reabrir uma página já gerada.
    """
    total_paginas = len(pdf_documento)

    for i in range(indice_inicio, total_paginas):
        pagina = pdf_documento[i]
        largura_pag = pagina.rect.width
        altura_pag = pagina.rect.height

        caixa_numero = pymupdf.Rect(largura_pag - 110, altura_pag - 18, largura_pag - 10, altura_pag - 4)
        texto = f"Página {i + 1} de {total_paginas}"
        pagina.insert_textbox(
            caixa_numero, texto,
            fontsize=7, fontname="helv", color=(0.4, 0.4, 0.4),
            align=pymupdf.TEXT_ALIGN_RIGHT
        )
