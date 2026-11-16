"""
A miniatura da arte — uma função só, pra todos os documentos.

Pedido do usuário (2026-09-23): *"relatório de produção e impressão, todos
precisam conter prévia da arte — afinal somos uma gráfica, o nome é a
arte, é sempre muito importante"*. OS, checklist e o documento de
"Enviados" já mostravam a arte, cada um com sua cópia da MESMA função; o
relatório diário de produção, que é a comprovação que vai pro cliente,
mostrava só o nome do arquivo. Em vez de uma quarta cópia, a função
passou a morar aqui.

Duas regras vieram das cópias antigas e não podem se perder:

  - renderiza JÁ na escala final, nunca em tamanho cheio pra depois
    encolher — há TIF de mais de 1 GB e lona de 29 m nessas pastas, e
    rasterizar isso inteiro pra fazer um quadradinho derruba a máquina;
  - **nunca levanta exceção**: miniatura é conforto visual, e arte que
    não abre (EPS, arquivo corrompido, arquivo já apagado) não pode
    impedir o documento de sair. Sem ela o documento desenha o quadrado
    cinza, como a OS sempre fez.

O CACHE existe por causa do relatório diário: ele é REGERADO a partir do
registro a qualquer momento, e o arquivo da arte só fica 15 dias em
"Enviados". Sem guardar, refazer o relatório de um dia velho devolveria
um documento sem arte nenhuma — justamente a comprovação do cliente.
Guardada, a arte daquele dia fica pra sempre, em alguns KB.

Atualização ISSUE-05: Utiliza o gerador autônomo motor_pdf.miniaturas
como motor primário livre de licenças restritivas (Pillow + motor_pdf nativo),
mantendo PyMuPDF apenas como fallback secundário opcional e transparente.
"""
import pathlib
from typing import Any, Optional, Tuple

import motor_pdf.miniaturas as _motor_miniaturas

try:
    import pymupdf
except ImportError:
    pymupdf = None

LADO_PADRAO = _motor_miniaturas.LADO_PADRAO          # px no maior lado — o mesmo que a OS usa
QUALIDADE_PADRAO = _motor_miniaturas.QUALIDADE_PADRAO
LIMITE_BYTES = _motor_miniaturas.LIMITE_BYTES
NOME_PASTA_CACHE = _motor_miniaturas.NOME_PASTA_CACHE


def de_arquivo(caminho, lado=LADO_PADRAO, qualidade=QUALIDADE_PADRAO, limite_bytes=LIMITE_BYTES):
    """JPEG da primeira página/imagem do arquivo, ou None se não der."""
    caminho = pathlib.Path(caminho)
    try:
        if not caminho.is_file() or (limite_bytes and caminho.stat().st_size > limite_bytes):
            return None
    except OSError:
        return None

    # Motor primário: motor_pdf.miniaturas (independente e livre de licenças restritivas)
    dados = _motor_miniaturas.de_arquivo(caminho, lado=lado, qualidade=qualidade, limite_bytes=limite_bytes)
    if dados:
        return dados

    # Fallback transparente para pymupdf se instalado e se motor_pdf não conseguiu decodificar
    if pymupdf is not None:
        try:
            doc = pymupdf.open(str(caminho))
            try:
                pagina = doc.load_page(0)
                maior = max(pagina.rect.width, pagina.rect.height) or 1
                escala = min(lado / maior, 1.0)
                pix = pagina.get_pixmap(matrix=pymupdf.Matrix(escala, escala))
                return pix.tobytes("jpg", jpg_quality=qualidade)
            finally:
                doc.close()
        except Exception:
            return None

    return None


def proporcao(dados):
    """(largura, altura) em px da miniatura, ou None — pra não distorcer."""
    tam = _motor_miniaturas.proporcao(dados)
    if tam:
        return tam
    if pymupdf is not None:
        try:
            pix = pymupdf.Pixmap(dados)
            return pix.width, pix.height
        except Exception:
            return None
    return None


def encaixar(dados, largura_max, altura_max):
    """
    (largura, altura) pra desenhar dentro da caixa MANTENDO a proporção.
    Arte esticada num documento de gráfica é defeito, não detalhe.
    """
    return _motor_miniaturas.encaixar(dados, largura_max, altura_max)


def caminho_guardada(pasta_cache, mes, chave):
    return _motor_miniaturas.caminho_guardada(pasta_cache, mes, chave)


def guardada(pasta_cache, mes, chave):
    """A miniatura que já foi guardada, ou None."""
    return _motor_miniaturas.guardada(pasta_cache, mes, chave)


def guardar(pasta_cache, mes, chave, dados):
    """Guarda pra quando o arquivo da arte já não existir mais."""
    return _motor_miniaturas.guardar(pasta_cache, mes, chave, dados)


def obter(caminho_arte, pasta_cache=None, mes=None, chave=None, lado=LADO_PADRAO,
          qualidade=QUALIDADE_PADRAO):
    """
    A miniatura, do cache ou do arquivo — e guardando quando faz do
    arquivo. Sem `pasta_cache` é só a miniatura, sem guardar nada.
    """
    return _motor_miniaturas.obter(
        caminho_arte,
        pasta_cache=pasta_cache,
        mes=mes,
        chave=chave,
        lado=lado,
        qualidade=qualidade,
    )
