"""
Extrai as linhas de corte de um PDF e grava um DXF ao lado dele, pro
Aspire importar.

Três regras que vieram do usuário e que o código respeita literalmente
(2026-09-06):

  - **O PDF nunca é tocado.** O DXF é arquivo NOVO, mesmo nome, mesma
    pasta. Mesma regra do envio pras máquinas: original não sai do lugar.
  - **A linha de corte é a magenta.** É a convenção da casa pra marcar
    contorno de recorte. Tudo que não é magenta fica de fora.
  - **Imagem se descarta.** Só vetor vira corte — e o DXF é vetorial por
    natureza, então imagem simplesmente não entra. O relatório avisa
    quando havia alguma, pra ninguém descobrir depois.

Por que ler o PDF direto em vez de mandar o Illustrator exportar: é
determinístico (mesmo arquivo, mesmo resultado, sempre), roda em
milissegundos, não depende do Illustrator estar instalado nem aberto, e
principalmente — deixa a gente ESCOLHER o que entra. Exportar pelo
Illustrator traria a arte inteira e alguém teria que limpar na mão do
outro lado.

O DXF sai em R12 ASCII, o dialeto mais antigo e mais bem aceito, com
tudo numa camada chamada CORTE. Medidas em milímetros, escala 1:1 com
a página do PDF.
"""
import colorsys
import math
import pathlib

import pymupdf

# Faixa que conta como "magenta". Medida nos arquivos reais de corte da
# casa (2026-09-06): os contornos aparecem entre 329° e 336°, com
# saturação de 0,71 a 0,79. O magenta puro de CMYK cai em 324°.
#
# Os dois limites de baixo não são preciosismo, são o que separa corte
# de não-corte nesta casa:
#   - saturação: há arquivos com traço quase preto (0.137, 0.122, 0.125)
#     cuja matiz calcula 346° — dentro da faixa! Só a saturação (0,11)
#     denuncia que é preto, não magenta.
#   - matiz até 350: as letras-caixa usam preenchimento vermelho, que
#     cai em 357°. Um grau a mais na faixa e o vermelho entraria.
MATIZ_MIN, MATIZ_MAX = 300.0, 350.0
SATURACAO_MIN = 0.35
VALOR_MIN = 0.30

# Erro máximo ao transformar curva de Bézier em segmentos de reta.
# 0,05 mm é menos que a folga da própria fresa.
TOLERANCIA_MM = 0.05

_PT_PARA_MM = 25.4 / 72.0
NOME_CAMADA = "CORTE"


def e_cor_de_corte(cor):
    """
    True se esta cor é o magenta que a casa usa pra marcar corte.

    'cor' é a tupla (r, g, b) de 0 a 1 que o PyMuPDF devolve, ou None
    quando o desenho não tem traço/preenchimento.
    """
    if not cor or len(cor) != 3:
        return False
    matiz, saturacao, valor = colorsys.rgb_to_hsv(*cor)
    return (MATIZ_MIN <= matiz * 360.0 <= MATIZ_MAX
            and saturacao >= SATURACAO_MIN
            and valor >= VALOR_MIN)


def _passos_da_curva(p0, p1, p2, p3, tolerancia_pt):
    """
    Quantos segmentos usar pra achatar esta Bézier.

    Estima pelo comprimento do polígono de controle, que é sempre maior
    ou igual ao da curva — errar pra mais só gasta pontos, errar pra
    menos deixa canto visível na peça cortada.
    """
    perimetro = sum(math.dist(a, b) for a, b in ((p0, p1), (p1, p2), (p2, p3)))
    if perimetro <= 0:
        return 1
    return max(2, min(64, math.ceil(math.sqrt(perimetro / max(tolerancia_pt, 1e-6)))))


def _achatar_curva(p0, p1, p2, p3, tolerancia_pt):
    """Pontos da Bézier cúbica, sem repetir o ponto inicial."""
    n = _passos_da_curva(p0, p1, p2, p3, tolerancia_pt)
    pontos = []
    for i in range(1, n + 1):
        t = i / n
        u = 1.0 - t
        x = (u * u * u * p0[0] + 3 * u * u * t * p1[0]
             + 3 * u * t * t * p2[0] + t * t * t * p3[0])
        y = (u * u * u * p0[1] + 3 * u * u * t * p1[1]
             + 3 * u * t * t * p2[1] + t * t * t * p3[1])
        pontos.append((x, y))
    return pontos


def _mesmo_ponto(a, b, folga=1e-6):
    return a is not None and b is not None and math.dist(a, b) <= folga


def _polilinhas_do_desenho(desenho, tolerancia_pt):
    """
    Quebra os itens de um desenho em polilinhas.

    Um desenho do PyMuPDF pode ter vários subcaminhos (o furo de um 'A',
    por exemplo). Eles vêm em sequência e o corte entre um e outro é
    justamente onde o próximo item NÃO começa onde o anterior terminou.
    """
    polilinhas = []
    atual = []

    def fechar():
        if len(atual) >= 2:
            polilinhas.append(list(atual))
        atual.clear()

    for item in desenho.get("items", []):
        tipo = item[0]
        if tipo == "l":
            p1, p2 = tuple(item[1]), tuple(item[2])
            if not atual or not _mesmo_ponto(atual[-1], p1):
                fechar()
                atual.append(p1)
            atual.append(p2)
        elif tipo == "c":
            p0, p1, p2, p3 = (tuple(item[i]) for i in range(1, 5))
            if not atual or not _mesmo_ponto(atual[-1], p0):
                fechar()
                atual.append(p0)
            atual.extend(_achatar_curva(p0, p1, p2, p3, tolerancia_pt))
        elif tipo in ("re", "qu"):
            # retângulo e quadrilátero são fechados por definição e não
            # se ligam ao traço anterior
            fechar()
            if tipo == "re":
                r = item[1]
                cantos = [(r.x0, r.y0), (r.x1, r.y0), (r.x1, r.y1), (r.x0, r.y1)]
            else:
                q = item[1]
                cantos = [tuple(q.ul), tuple(q.ur), tuple(q.lr), tuple(q.ll)]
            polilinhas.append(cantos + [cantos[0]])
    fechar()
    return polilinhas


def _mascaras_suspeitas(pagina):
    """
    Máscaras de recorte com forma complexa — candidatas a serem contorno
    de corte que perdeu a cor.

    No PDF, máscara de recorte não pinta nada, e por isso **não guarda
    cor**. Se alguém no Illustrator usou o contorno magenta como máscara,
    a geometria continua no arquivo mas o magenta some, e a busca por cor
    nunca acha (hipótese do usuário, 2026-09-06 — conferida e descartada
    nos arquivos daquele dia, mas é questão de tempo até acontecer).

    O que separa uma da outra é o número de segmentos: borda de página e
    recorte de imagem são retângulos, com 1 item de caminho. Contorno de
    logo tem dezenas. Acima de 4 já não é retângulo.
    """
    achadas = []
    for desenho in pagina.get_drawings(extended=True):
        if desenho.get("type") != "clip":
            continue
        itens = len(desenho.get("items", []))
        if itens > 4:
            achadas.append(itens)
    return achadas


def extrair_contornos(caminho_pdf, tolerancia_mm=TOLERANCIA_MM):
    """
    Lê o PDF e devolve (polilinhas_em_mm, relatorio).

    As polilinhas já vêm em milímetros e com o Y virado pra cima, que é
    como o DXF conta — o PDF conta de cima pra baixo.
    """
    caminho_pdf = pathlib.Path(caminho_pdf)
    tolerancia_pt = tolerancia_mm / _PT_PARA_MM
    relatorio = {
        "paginas": 0, "desenhos": 0, "de_corte": 0,
        "descartados": 0, "imagens": 0, "contornos": 0, "mascaras": [],
    }
    saida = []

    with pymupdf.open(caminho_pdf) as doc:
        relatorio["paginas"] = doc.page_count
        for pagina in doc:
            altura = pagina.rect.height
            relatorio["imagens"] += len(pagina.get_images())
            relatorio["mascaras"].extend(_mascaras_suspeitas(pagina))
            for desenho in pagina.get_drawings():
                relatorio["desenhos"] += 1
                if not (e_cor_de_corte(desenho.get("color"))
                        or e_cor_de_corte(desenho.get("fill"))):
                    relatorio["descartados"] += 1
                    continue
                relatorio["de_corte"] += 1
                for poli in _polilinhas_do_desenho(desenho, tolerancia_pt):
                    saida.append([((x * _PT_PARA_MM), ((altura - y) * _PT_PARA_MM))
                                  for x, y in poli])

    relatorio["contornos"] = len(saida)
    return saida, relatorio


def _par(codigo, valor):
    return f"{codigo}\n{valor}\n"


def escrever_dxf(polilinhas, caminho_dxf):
    """
    Grava as polilinhas como DXF R12 ASCII, camada CORTE, em milímetros.

    POLYLINE/VERTEX em vez de LWPOLYLINE de propósito: LWPOLYLINE é de
    1997 pra cá e o importador aqui é um Aspire 8.5. O formato antigo é
    mais verboso e entra em qualquer lugar.
    """
    caminho_dxf = pathlib.Path(caminho_dxf)
    partes = [
        _par(0, "SECTION"), _par(2, "HEADER"),
        _par(9, "$INSUNITS"), _par(70, 4),          # 4 = milímetros
        _par(0, "ENDSEC"),
        _par(0, "SECTION"), _par(2, "ENTITIES"),
    ]
    for poli in polilinhas:
        fechada = len(poli) > 2 and _mesmo_ponto(poli[0], poli[-1], folga=1e-4)
        pontos = poli[:-1] if fechada else poli
        partes += [
            _par(0, "POLYLINE"), _par(8, NOME_CAMADA),
            _par(66, 1), _par(70, 1 if fechada else 0),
        ]
        for x, y in pontos:
            partes += [
                _par(0, "VERTEX"), _par(8, NOME_CAMADA),
                _par(10, f"{x:.4f}"), _par(20, f"{y:.4f}"), _par(30, "0.0"),
            ]
        partes += [_par(0, "SEQEND"), _par(8, NOME_CAMADA)]

    partes += [_par(0, "ENDSEC"), _par(0, "EOF")]
    caminho_dxf.write_text("".join(partes), encoding="ascii")
    return caminho_dxf


def converter(caminho_pdf, caminho_dxf=None, tolerancia_mm=TOLERANCIA_MM):
    """
    Gera o DXF de corte ao lado do PDF, com o mesmo nome.

    NUNCA escreve no PDF nem o apaga — o DXF é arquivo novo.

    Devolve o relatório com 'dxf' preenchido, ou com 'dxf': None e
    'motivo' explicando por que não deu. Recusar é a resposta certa
    quando não há magenta: um DXF vazio parece que funcionou, vai pra
    fresa e só se descobre com a chapa na máquina.
    """
    caminho_pdf = pathlib.Path(caminho_pdf)
    polilinhas, relatorio = extrair_contornos(caminho_pdf, tolerancia_mm)
    relatorio["pdf"] = str(caminho_pdf)
    relatorio["dxf"] = None
    relatorio["motivo"] = None

    if not polilinhas:
        if relatorio["desenhos"] == 0:
            relatorio["motivo"] = ("não achei vetor nenhum neste PDF — se ele é imagem, "
                                   "não há o que cortar")
        elif relatorio["mascaras"]:
            relatorio["motivo"] = (
                f"nenhum contorno magenta entre os {relatorio['desenhos']} vetores, MAS há "
                f"máscara de recorte com forma complexa ({', '.join(str(m) for m in relatorio['mascaras'])} "
                f"segmentos) — máscara não guarda cor, então pode ser o contorno de corte com o "
                f"magenta perdido. Abra no Illustrator e libere a máscara de recorte")
        else:
            relatorio["motivo"] = (
                f"nenhum contorno magenta entre os {relatorio['desenhos']} vetores — "
                f"ou a linha de corte está em outra cor, ou a peça é o próprio "
                f"desenho preenchido (letra caixa)")
        return relatorio

    destino = pathlib.Path(caminho_dxf) if caminho_dxf else caminho_pdf.with_suffix(".dxf")
    escrever_dxf(polilinhas, destino)
    relatorio["dxf"] = str(destino)
    return relatorio
