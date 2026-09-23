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
"""
import hashlib
import pathlib

import pymupdf

LADO_PADRAO = 300          # px no maior lado — o mesmo que a OS usa
QUALIDADE_PADRAO = 70

# Acima disto nem tenta: um TIF de 1,8 GB (já apareceu no registro) é
# decodificado inteiro pela MuPDF antes de virar quadradinho, e a
# máquina que gera o relatório é a mesma que o usuário está usando.
LIMITE_BYTES = 300 * 1024 * 1024

NOME_PASTA_CACHE = "_miniaturas"


def de_arquivo(caminho, lado=LADO_PADRAO, qualidade=QUALIDADE_PADRAO, limite_bytes=LIMITE_BYTES):
    """JPEG da primeira página/imagem do arquivo, ou None se não der."""
    caminho = pathlib.Path(caminho)
    try:
        if not caminho.is_file() or (limite_bytes and caminho.stat().st_size > limite_bytes):
            return None
        doc = pymupdf.open(str(caminho))
    except Exception:
        return None
    try:
        pagina = doc.load_page(0)
        maior = max(pagina.rect.width, pagina.rect.height) or 1
        escala = min(lado / maior, 1.0)
        pix = pagina.get_pixmap(matrix=pymupdf.Matrix(escala, escala))
        return pix.tobytes("jpg", jpg_quality=qualidade)
    except Exception:
        return None
    finally:
        doc.close()


def proporcao(dados):
    """(largura, altura) em px da miniatura, ou None — pra não distorcer."""
    try:
        pix = pymupdf.Pixmap(dados)
        return pix.width, pix.height
    except Exception:
        return None


def encaixar(dados, largura_max, altura_max):
    """
    (largura, altura) pra desenhar dentro da caixa MANTENDO a proporção.
    Arte esticada num documento de gráfica é defeito, não detalhe.
    """
    tamanho = proporcao(dados)
    if not tamanho:
        return largura_max, altura_max
    largura, altura = tamanho
    escala = min(largura_max / largura, altura_max / altura)
    return max(1, round(largura * escala)), max(1, round(altura * escala))


def _nome_guardado(chave):
    """Nome curto e sem surpresa: nome de arte tem acento, barra e 200 letras."""
    return hashlib.sha1("|".join(str(p) for p in chave).encode("utf-8")).hexdigest()[:16] + ".jpg"


def caminho_guardada(pasta_cache, mes, chave):
    return pathlib.Path(pasta_cache) / NOME_PASTA_CACHE / str(mes) / _nome_guardado(chave)


def guardada(pasta_cache, mes, chave):
    """A miniatura que já foi guardada, ou None."""
    caminho = caminho_guardada(pasta_cache, mes, chave)
    try:
        return caminho.read_bytes() if caminho.is_file() else None
    except OSError:
        return None


def guardar(pasta_cache, mes, chave, dados):
    """Guarda pra quando o arquivo da arte já não existir mais."""
    if not dados:
        return None
    caminho = caminho_guardada(pasta_cache, mes, chave)
    try:
        caminho.parent.mkdir(parents=True, exist_ok=True)
        temporario = caminho.with_suffix(".tmp")
        temporario.write_bytes(dados)
        temporario.replace(caminho)
    except OSError:
        return None
    return caminho


def obter(caminho_arte, pasta_cache=None, mes=None, chave=None, lado=LADO_PADRAO,
          qualidade=QUALIDADE_PADRAO):
    """
    A miniatura, do cache ou do arquivo — e guardando quando faz do
    arquivo. Sem `pasta_cache` é só a miniatura, sem guardar nada.
    """
    if pasta_cache and chave:
        ja = guardada(pasta_cache, mes, chave)
        if ja:
            return ja
    dados = de_arquivo(caminho_arte, lado=lado, qualidade=qualidade)
    if dados and pasta_cache and chave:
        guardar(pasta_cache, mes, chave, dados)
    return dados
