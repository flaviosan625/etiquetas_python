"""
Local do logotipo da empresa (Uny CV) e função utilitária para inserir
o logo em páginas de PDF (PyMuPDF). Usada tanto na Ordem de Serviço
quanto nas páginas de título do PDF unificado.

Se o arquivo do logo não existir (por exemplo, a pasta 'assets' foi
apagada ou não veio junto num clone novo do repositório), a função não
quebra o programa — só deixa de desenhar o logo, silenciosamente.
"""
import pathlib

import pymupdf

BASE_DIR = pathlib.Path(__file__).resolve().parent
CAMINHO_LOGO = BASE_DIR / "assets" / "logo_uny_cv.png"
# versão já reduzida (230px de largura), pensada para a tela do programa
# (tkinter) — evita depender do Pillow só para redimensionar em tempo real
CAMINHO_LOGO_GUI = BASE_DIR / "assets" / "logo_uny_cv_gui.png"


def logo_disponivel():
    return CAMINHO_LOGO.exists()


def inserir_logo(pagina, rect, alinhamento="left", caminho=None):
    """
    Insere o logo da Uny CV dentro de 'rect', mantendo a proporção
    original da imagem (nunca distorce) e centralizado verticalmente
    dentro do espaço disponível.

    'alinhamento' controla onde a imagem fica dentro de 'rect' quando a
    proporção do logo não preenche o espaço todo: "left", "right" ou
    "center".

    'caminho' permite usar uma variante menor do logo (ex: a versão já
    reduzida usada na tela) em documentos onde tamanho de arquivo importa
    mais do que resolução — por padrão usa a versão em alta resolução.

    Não faz nada se o arquivo do logo não existir.
    """
    caminho_logo = caminho or CAMINHO_LOGO
    if not caminho_logo.exists():
        return

    pix = pymupdf.Pixmap(str(caminho_logo))
    proporcao = pix.width / pix.height

    largura_disponivel = rect.width
    altura_disponivel = rect.height

    if largura_disponivel / altura_disponivel > proporcao:
        altura_final = altura_disponivel
        largura_final = altura_final * proporcao
    else:
        largura_final = largura_disponivel
        altura_final = largura_final / proporcao

    if alinhamento == "right":
        x0 = rect.x1 - largura_final
    elif alinhamento == "center":
        x0 = rect.x0 + (largura_disponivel - largura_final) / 2
    else:
        x0 = rect.x0

    y0 = rect.y0 + (altura_disponivel - altura_final) / 2
    rect_final = pymupdf.Rect(x0, y0, x0 + largura_final, y0 + altura_final)
    pagina.insert_image(rect_final, filename=str(caminho_logo))
