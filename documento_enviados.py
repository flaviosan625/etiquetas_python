"""
O documento "Enviados" de um cliente: a lista, com miniatura, de tudo
que já subiu pra fila das máquinas — atualizada a cada envio.

Mora numa pasta 'Enviados' na RAIZ do cliente (pedido do usuário,
2026-09-05), não dentro de cada produção:

    EVENTOS\\FESTA ALEMA\\
        Enviados\\
            ENVIADOS - FESTA ALEMA.pdf   <- o documento
            _envios.json                 <- os dados que o geram
        PRODUCAO 03_09\\                  <- os arquivos, intactos
        PRODUCAO 02_09\\

Por que dois arquivos, e não só o PDF:

  O JSON é a fonte de verdade; o PDF é só o desenho dele. Isso importa
  na hora do envio — se você estiver com o PDF aberto no leitor, o
  Windows trava a regravação. Gravando o JSON primeiro, o envio já
  está registrado e o PDF pode ser refeito depois (ver
  regravar_pdf). Se fosse tudo no PDF, um documento aberto na hora
  errada faria você perder o registro de um envio que aconteceu de
  verdade — que é justamente o que este documento existe pra impedir.

  A miniatura vai dentro do JSON, em base64. Ocupa uns 15 KB por linha
  e torna o documento reproduzível pra sempre, sem nunca mais precisar
  abrir o arquivo original — que pode ter virado placeholder "só na
  nuvem" de 1,83 GB, ou nem existir mais.

Cada linha é UM ENVIO, não um item de pedido: reenviar o mesmo arquivo
gera outra linha, com a hora dela, e soma no subtotal — porque material
foi gasto de novo (regra do usuário, mesma do relatório diário).
"""
import base64
import datetime
import json
import pathlib

import pymupdf

from branding import inserir_logo, CAMINHO_LOGO_GUI
from envio_impressao import NOME_PASTA_ENVIADOS
from relatorios import _cor_categoria, _descricao_arquivo

NOME_ARQUIVO_DADOS = "_envios.json"

LARGURA = 595.27  # A4
ALTURA = 841.89
MARGEM = 36
ALTURA_LOGO = 24
ALTURA_THUMB = 44
ALTURA_ITEM = 62
ALTURA_GRUPO = 18

# Fontes base do PDF (Helvetica normal e negrito). NÃO são embutidas no
# arquivo — e é por isso que este módulo desenha com insert_textbox em
# vez do insert_htmlbox que a OS usa.
#
# Medido aqui (2026-09-05): cada chamada de insert_htmlbox embute um
# subconjunto próprio da fonte, ~91 KB. Um documento de 30 linhas saiu
# com 3,5 MB e 76 fontes embutidas. Este documento fica salvo o ano
# todo e cresce a cada envio, então esse custo por linha era proibitivo
# — a OS pode pagá-lo porque é gerada uma vez e fica daquele tamanho.
# Mesma família de problema já vista em relatorio_producao.py.
_FONTE = "helv"
_FONTE_NEGRITO = "hebo"

# Cinzas e tinta do documento, iguais aos da OS.
_TINTA = (0.08, 0.08, 0.08)
_TINTA_SUAVE = (0.27, 0.27, 0.27)
_CINZA = (0.4, 0.4, 0.4)
_CINZA_CLARO = (0.6, 0.6, 0.6)
_LINHA_FINA = (0.88, 0.89, 0.9)
_SELO_GIRO = ("#E9F5ED", "#0F7A3D")
_SELO_REENVIO = ("#E7EAF2", "#40506B")

# Arquivo cujo nome não diz o material cai neste grupo. Ganha cor
# neutra de propósito: pintado com a cor da primeira categoria (que é
# o que _cor_categoria devolve pra nome desconhecido) ele passaria por
# um material de verdade na leitura rápida.
_SEM_MATERIAL = "SEM MATERIAL"
_COR_SEM_MATERIAL = ("#EFEFF1", "#5A5F66")

# Extensões tiradas do nome antes de montar a descrição — a limpeza da
# OS só conhece '.pdf', e aqui entra .tif/.jpg/.png o tempo todo.
_EXTENSOES = (".pdf", ".ai", ".png", ".jpg", ".jpeg", ".eps", ".tif", ".tiff")

# Miniatura no mesmo tamanho e qualidade da que a OS já usa (ver
# processamento.py) — o documento é lido do lado da OS, não faz sentido
# ter duas qualidades de imagem diferentes pra mesma arte.
_LADO_MAX_THUMB = 300
_QUALIDADE_THUMB = 70


def pasta_documento(raiz_cliente):
    return pathlib.Path(raiz_cliente) / NOME_PASTA_ENVIADOS


def caminho_dados(raiz_cliente):
    return pasta_documento(raiz_cliente) / NOME_ARQUIVO_DADOS


def caminho_pdf(raiz_cliente):
    raiz = pathlib.Path(raiz_cliente)
    return pasta_documento(raiz) / f"ENVIADOS - {raiz.name}.pdf"


def carregar(raiz_cliente):
    """
    Lê os envios já registrados desse cliente. Devolve a estrutura
    vazia quando ainda não existe nenhum — a pasta só nasce no primeiro
    envio, nunca antes (senão toda pasta de cliente ganharia uma
    'Enviados' vazia).

    Arquivo corrompido não estoura erro nem some com o histórico: guarda
    uma cópia .bak e começa de novo, mesmo padrão de estoque.py e
    config.py.
    """
    raiz = pathlib.Path(raiz_cliente)
    caminho = caminho_dados(raiz)
    vazio = {"cliente": raiz.name, "envios": []}
    if not caminho.exists():
        return vazio

    try:
        with open(caminho, "r", encoding="utf-8") as f:
            dados = json.load(f)
    except (json.JSONDecodeError, OSError):
        try:
            caminho.replace(caminho.with_suffix(".json.bak"))
        except OSError:
            pass
        return vazio

    dados.setdefault("cliente", raiz.name)
    dados.setdefault("envios", [])
    return dados


def salvar(raiz_cliente, dados):
    """
    Grava o JSON de forma atômica: escreve num temporário ao lado e só
    então troca pelo definitivo. Sem isso, uma queda de energia no meio
    da gravação deixaria o histórico de envios truncado — e ele é a
    fonte de verdade do documento, não dá pra perder.
    """
    pasta = pasta_documento(raiz_cliente)
    pasta.mkdir(parents=True, exist_ok=True)
    destino = caminho_dados(raiz_cliente)
    temporario = destino.with_suffix(".json.tmp")
    with open(temporario, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)
    temporario.replace(destino)
    return destino


def miniatura(caminho_arquivo):
    """
    JPEG pequeno da primeira página/imagem do arquivo, ou None se não
    der — EPS não abre no pymupdf, e arte quebrada acontece. Sem
    miniatura o documento desenha o quadrado cinza, igual à OS.

    Renderiza JÁ na escala reduzida (matriz), nunca em tamanho cheio
    pra depois encolher: tem TIF de mais de 1 GB nessas pastas e
    rasterizar isso inteiro pra fazer um quadradinho de 300 px derrubaria
    a memória da máquina.
    """
    try:
        doc = pymupdf.open(str(caminho_arquivo))
    except Exception:
        return None
    try:
        pagina = doc.load_page(0)
        rect = pagina.rect
        maior_lado = max(rect.width, rect.height) or 1
        escala = min(_LADO_MAX_THUMB / maior_lado, 1.0)
        pix = pagina.get_pixmap(matrix=pymupdf.Matrix(escala, escala))
        return pix.tobytes("jpg", jpg_quality=_QUALIDADE_THUMB)
    except Exception:
        return None
    finally:
        doc.close()


def registrar(raiz_cliente, registros, miniaturas=None):
    """
    Acrescenta os envios ao histórico e regrava o JSON. Nunca substitui
    linha existente: reenvio do mesmo arquivo entra como linha nova.

    'miniaturas' é {nome_do_arquivo: bytes JPEG} — só pra quem ainda não
    tem miniatura guardada. Arquivo já enviado antes reaproveita a
    miniatura do primeiro envio, então não precisa ser aberto de novo.
    """
    dados = carregar(raiz_cliente)
    miniaturas = miniaturas or {}
    ja_tem = {e["arquivo"]: e.get("miniatura_b64") for e in dados["envios"] if e.get("miniatura_b64")}

    for registro in registros:
        linha = dict(registro)
        b64 = ja_tem.get(linha["arquivo"])
        if not b64 and miniaturas.get(linha["arquivo"]):
            b64 = base64.b64encode(miniaturas[linha["arquivo"]]).decode("ascii")
            ja_tem[linha["arquivo"]] = b64
        linha["miniatura_b64"] = b64
        dados["envios"].append(linha)

    salvar(raiz_cliente, dados)
    return dados


def _data_curta(quando_iso):
    try:
        return datetime.datetime.fromisoformat(quando_iso).strftime("%d/%m %H:%M")
    except (TypeError, ValueError):
        return str(quando_iso)


def _cores_do_selo(categoria, ordem_categorias):
    """Cores da etiqueta de material — neutras quando o nome não disse qual material é."""
    if categoria == _SEM_MATERIAL:
        return _COR_SEM_MATERIAL
    return _cor_categoria(categoria, ordem_categorias)


def _descricao(arquivo, categoria, cliente):
    """
    Descrição limpa, reaproveitando a da OS mas tirando a extensão
    antes: _descricao_arquivo só conhece '.pdf', e aqui .tif/.jpg/.png
    são a maioria — sem isso a linha termina em 'sangria tif'.
    """
    nome = arquivo
    for extensao in _EXTENSOES:
        if nome.lower().endswith(extensao):
            nome = nome[: -len(extensao)]
            break
    return _descricao_arquivo(nome, categoria if categoria != _SEM_MATERIAL else None, cliente)


def _rgb(cor_hex):
    """'#E6F1FB' -> (0.90, 0.94, 0.98) — as cores de categoria vêm da OS em hexadecimal."""
    cor_hex = cor_hex.lstrip("#")
    return tuple(int(cor_hex[i:i + 2], 16) / 255 for i in (0, 2, 4))


def _escrever(pagina, x, topo, texto, tamanho, cor, negrito=False, direita_em=None):
    """
    Uma linha de texto posicionada pelo TOPO dos caracteres.

    Usa insert_text (ancorado na linha de base), não insert_textbox: a
    caixa recusa em SILÊNCIO quando tem menos de 1,8x o corpo da fonte
    de altura — não levanta erro, não escreve nada, e o texto some do
    documento sem ninguém perceber (medido aqui, 2026-09-05). Ancorar na
    linha de base também dá o controle exato de posição que este layout
    precisa pra alinhar selo, texto e carimbo na mesma linha.

    'direita_em' alinha o fim do texto nessa coordenada, em vez do
    começo. Devolve a largura ocupada, pra encadear um pedaço atrás do
    outro na mesma linha.
    """
    fonte = _FONTE_NEGRITO if negrito else _FONTE
    largura = pymupdf.get_text_length(texto, fontname=fonte, fontsize=tamanho)
    if direita_em is not None:
        x = direita_em - largura
    pagina.insert_text(
        pymupdf.Point(x, topo + tamanho * 0.78), texto,
        fontsize=tamanho, fontname=fonte, color=cor,
    )
    return largura


def _encurtar(texto, tamanho, largura_max, negrito=False):
    """
    Corta o texto pra caber numa linha, terminando em '...'. Descrição de
    arte tem nome comprido de verdade nesta casa — sem isso, ela vazaria
    por cima da linha de baixo.
    """
    fonte = _FONTE_NEGRITO if negrito else _FONTE
    if pymupdf.get_text_length(texto, fontname=fonte, fontsize=tamanho) <= largura_max:
        return texto
    while texto and pymupdf.get_text_length(texto + "...", fontname=fonte, fontsize=tamanho) > largura_max:
        texto = texto[:-1]
    return texto.rstrip() + "..."


def _selo(pagina, x, topo, texto, cor_fundo_hex, cor_texto_hex, tamanho=6.5):
    """
    Etiqueta colorida (categoria, GIROU 90°, 2º ENVIO) — retângulo
    pintado com o texto centralizado por cima. Devolve o x onde o
    próximo selo da mesma linha pode começar.
    """
    largura_texto = pymupdf.get_text_length(texto, fontname=_FONTE_NEGRITO, fontsize=tamanho)
    largura = largura_texto + 10
    altura = tamanho + 5
    pagina.draw_rect(
        pymupdf.Rect(x, topo, x + largura, topo + altura),
        color=None, fill=_rgb(cor_fundo_hex), width=0,
    )
    # centralizado na vertical pela altura de caixa alta (~0,72 do corpo
    # em Helvetica), não pela altura total da fonte — senão o texto
    # parece afundado dentro do selo
    pagina.insert_text(
        pymupdf.Point(x + 5, topo + (altura + tamanho * 0.72) / 2), texto,
        fontsize=tamanho, fontname=_FONTE_NEGRITO, color=_rgb(cor_texto_hex),
    )
    return x + largura + 4


def _nova_pagina(pdf, cliente, cabecalho_extra, caixas_pagina, xref_logo=None):
    """
    Página A4 nova com o cabeçalho repetido — o documento é impresso em
    folhas soltas e cada uma precisa se identificar sozinha, mesma
    razão da OS. O número da página só é escrito no fim, quando o total
    é conhecido.

    'xref_logo' reaproveita o logo já embutido nas páginas seguintes:
    são 24 KB por página que seriam duplicados à toa num documento que
    cresce o ano todo. Devolve (pagina, y, xref_logo).
    """
    pagina = pdf.new_page(width=LARGURA, height=ALTURA)
    y = MARGEM

    xref_logo = inserir_logo(
        pagina, pymupdf.Rect(MARGEM, y, MARGEM + 70, y + ALTURA_LOGO),
        alinhamento="left", caminho=CAMINHO_LOGO_GUI, xref=xref_logo,
    ) or xref_logo

    x = MARGEM + 80
    _escrever(pagina, x, y - 1, "ENVIADOS PARA IMPRESSÃO", 7, _CINZA_CLARO)
    _escrever(pagina, x, y + 8, cliente.upper(), 13, (0.08, 0.08, 0.08), negrito=True)
    _escrever(pagina, x, y + 26, cabecalho_extra, 7.5, _CINZA)

    # guarda o ÍNDICE da página, nunca o objeto Page: o objeto fica
    # inválido depois que outras páginas são criadas no mesmo documento
    caixas_pagina.append((len(pdf) - 1, pymupdf.Rect(LARGURA - MARGEM - 65, y, LARGURA - MARGEM, y + 12)))

    y += ALTURA_LOGO + 18
    pagina.draw_line(pymupdf.Point(MARGEM, y), pymupdf.Point(LARGURA - MARGEM, y), color=(0.2, 0.2, 0.2), width=1)
    return pagina, y + 10, xref_logo


def _desenhar_envio(pagina, y, envio, cor_fundo, cor_texto, cliente, ordinal):
    x_thumb = MARGEM
    x_texto = x_thumb + ALTURA_THUMB + 10
    largura_texto = LARGURA - MARGEM - x_texto

    rect_thumb = pymupdf.Rect(
        x_thumb, y + (ALTURA_ITEM - ALTURA_THUMB) / 2,
        x_thumb + ALTURA_THUMB, y + (ALTURA_ITEM - ALTURA_THUMB) / 2 + ALTURA_THUMB,
    )
    desenhou = False
    if envio.get("miniatura_b64"):
        try:
            pagina.insert_image(rect_thumb, stream=base64.b64decode(envio["miniatura_b64"]))
            desenhou = True
        except Exception:
            desenhou = False
    if not desenhou:
        pagina.draw_rect(rect_thumb, color=(0.85, 0.85, 0.85), fill=(0.94, 0.94, 0.94), width=0.5)

    dimensao = envio.get("dimensao")
    if dimensao and envio.get("area_total_m2") is not None:
        area = (
            f'{envio["area_total_m2"]:.2f} m² '
            f'({dimensao["largura_m"]:.2f} x {dimensao["altura_m"]:.2f} m)'
        ).replace(".", ",")
    else:
        area = "Medida não informada"

    # linha 1: selo de material, selos do envio, e a quantidade à direita
    linha_y = y + 5
    x = _selo(pagina, x_texto, linha_y, envio.get("categoria") or _SEM_MATERIAL, cor_fundo, cor_texto, tamanho=7)
    if envio.get("girou_previsto"):
        x = _selo(pagina, x, linha_y, "GIROU 90°", *_SELO_GIRO)
    if ordinal > 1:
        x = _selo(pagina, x, linha_y, f"{ordinal}º ENVIO", *_SELO_REENVIO)
    _escrever(pagina, 0, linha_y + 1, f"{envio['quantidade']} UN", 8, _CINZA,
              direita_em=x_texto + largura_texto)

    descricao = _descricao(envio["arquivo"], envio.get("categoria"), cliente)
    _escrever(pagina, x_texto, y + 20, _encurtar(descricao, 8.5, largura_texto), 8.5, _TINTA_SUAVE)
    _escrever(pagina, x_texto, y + 32, area, 9, _TINTA, negrito=True)

    # linha 4: a data/hora é o dado que prova o envio, então vem
    # carimbada num fundo cinza e em negrito, nunca como nota de rodapé
    # (pedido do usuário, 2026-09-05: "imprescindível a data e hora do
    # envio de cada material").
    quando = _data_curta(envio["quando"])
    largura_carimbo = pymupdf.get_text_length(quando, fontname=_FONTE_NEGRITO, fontsize=8) + 9
    pagina.draw_rect(
        pymupdf.Rect(x_texto, y + 45, x_texto + largura_carimbo, y + 56),
        color=None, fill=(0.94, 0.945, 0.953), width=0,
    )
    _escrever(pagina, x_texto + 4.5, y + 47, quando, 8, _TINTA, negrito=True)

    onde = f" · {envio['producao']}" if envio.get("producao") else ""
    _escrever(pagina, x_texto + largura_carimbo + 7, y + 47, f"{envio['maquina']}{onde}", 8, _TINTA_SUAVE)

    y += ALTURA_ITEM
    pagina.draw_line(pymupdf.Point(MARGEM, y), pymupdf.Point(LARGURA - MARGEM, y), color=(0.88, 0.89, 0.9), width=0.6)
    return y


def _resumo_por_material(envios, ordem_categorias):
    """
    Um resumo por material com m², contagem de envios, de unidades e o
    período — nunca um total combinado entre materiais diferentes
    (regra fixa desta casa).

    Soma o valor JÁ ARREDONDADO de cada linha, igual ao relatório
    diário: quem confere soma a coluna que está vendo, e o subtotal
    precisa fechar com ela.
    """
    resumo = {}
    for envio in envios:
        categoria = envio.get("categoria") or _SEM_MATERIAL
        atual = resumo.setdefault(
            categoria, {"m2": 0.0, "envios": 0, "unidades": 0, "sem_medida": 0, "de": None, "ate": None},
        )
        atual["envios"] += 1
        atual["unidades"] += envio.get("quantidade") or 0
        if envio.get("area_total_m2") is not None:
            atual["m2"] = round(atual["m2"] + envio["area_total_m2"], 2)
        else:
            # contado à parte de propósito: num documento de comprovação,
            # imprimir "0,00 m²" pra um material cuja medida ninguém leu
            # afirma que nada foi gasto, que é diferente de "não sei"
            atual["sem_medida"] += 1
        quando = envio["quando"]
        atual["de"] = quando if atual["de"] is None else min(atual["de"], quando)
        atual["ate"] = quando if atual["ate"] is None else max(atual["ate"], quando)

    conhecidas = [c for c in ordem_categorias if c in resumo]
    resto = sorted(c for c in resumo if c not in conhecidas)
    return [(c, resumo[c]) for c in [*conhecidas, *resto]]


def gerar_pdf(raiz_cliente, ordem_categorias=None, agora=None):
    """
    Redesenha o documento inteiro a partir do JSON. Sempre do zero —
    nunca acrescenta página em PDF existente: assim o documento é
    exatamente o que o histórico diz, e um PDF apagado por engano volta
    igualzinho no envio seguinte.

    Devolve o caminho do PDF, ou None se não houver nenhum envio ainda.
    """
    dados = carregar(raiz_cliente)
    envios = sorted(dados["envios"], key=lambda e: e["quando"])
    if not envios:
        return None

    ordem_categorias = list(ordem_categorias or [])
    cliente = dados["cliente"]
    agora = agora or datetime.datetime.now()
    primeiro = _data_curta(envios[0]["quando"])
    plural = "envio" if len(envios) == 1 else "envios"
    cabecalho = f"Atualizado {agora:%d/%m/%Y %H:%M}  ·  {len(envios)} {plural} desde {primeiro}"

    # quantas vezes cada arquivo já apareceu ATÉ esta linha — é o que dá
    # o selo "2º ENVIO" na linha certa, sem marcar a primeira
    ordinais = {}
    for envio in envios:
        ordinais[envio["arquivo"]] = ordinais.get(envio["arquivo"], 0) + 1
        envio["_ordinal"] = ordinais[envio["arquivo"]]

    por_categoria = {}
    for envio in envios:
        por_categoria.setdefault(envio.get("categoria") or _SEM_MATERIAL, []).append(envio)
    categorias = [c for c in ordem_categorias if c in por_categoria]
    categorias += sorted(c for c in por_categoria if c not in categorias)

    limite_y = ALTURA - MARGEM
    pdf = pymupdf.open()
    caixas_pagina = []
    pagina, y, xref_logo = _nova_pagina(pdf, cliente, cabecalho, caixas_pagina)

    for categoria in categorias:
        cor_fundo, cor_texto = _cores_do_selo(categoria, ordem_categorias)
        if y + ALTURA_GRUPO + ALTURA_ITEM > limite_y:
            pagina, y, xref_logo = _nova_pagina(pdf, cliente, cabecalho, caixas_pagina, xref_logo)

        _escrever(pagina, MARGEM, y, categoria, 10, _rgb(cor_texto), negrito=True)
        y += ALTURA_GRUPO

        for envio in por_categoria[categoria]:
            if y + ALTURA_ITEM > limite_y:
                pagina, y, xref_logo = _nova_pagina(pdf, cliente, cabecalho, caixas_pagina, xref_logo)
                _escrever(pagina, MARGEM, y, f"{categoria} (continuação)", 10, _rgb(cor_texto), negrito=True)
                y += ALTURA_GRUPO
            y = _desenhar_envio(pagina, y, envio, cor_fundo, cor_texto, cliente, envio["_ordinal"])

    resumo = _resumo_por_material(envios, categorias)
    altura_resumo = 24 + len(resumo) * 22 + 34
    if y + altura_resumo > limite_y:
        pagina, y, xref_logo = _nova_pagina(pdf, cliente, cabecalho, caixas_pagina, xref_logo)
    else:
        y += 10

    _escrever(pagina, MARGEM, y, "SUBTOTAL POR MATERIAL - ENVIADO", 8, _CINZA_CLARO, negrito=True)
    y += 20

    for categoria, info in resumo:
        _, cor_texto = _cores_do_selo(categoria, categorias)
        plural_envios = "envio" if info["envios"] == 1 else "envios"
        periodo = _data_curta(info["de"])
        if info["ate"] != info["de"]:
            periodo += f' a {_data_curta(info["ate"])}'
        detalhe = f"{info['envios']} {plural_envios} · {info['unidades']} un · {periodo}"
        if info["sem_medida"]:
            detalhe += f" · {info['sem_medida']} sem medida no nome"

        # sem NENHUMA medida lida, o m² não é zero — é desconhecido, e
        # este documento não pode afirmar que nada foi gasto
        if info["m2"] or not info["sem_medida"]:
            valor, cor_valor = f'{info["m2"]:.2f} m²'.replace(".", ","), _TINTA
        else:
            valor, cor_valor = "sem medida", _CINZA

        x = MARGEM + _escrever(pagina, MARGEM, y, categoria, 9, _rgb(cor_texto), negrito=True)
        _escrever(pagina, x + 8, y + 0.7, detalhe, 8, _CINZA)
        _escrever(pagina, 0, y, valor, 9, cor_valor, negrito=True, direita_em=LARGURA - MARGEM)
        y += 16
        pagina.draw_line(pymupdf.Point(MARGEM, y), pymupdf.Point(LARGURA - MARGEM, y), color=_LINHA_FINA, width=0.6)
        y += 6

    y += 6
    pagina.insert_textbox(
        pymupdf.Rect(MARGEM, y, LARGURA - MARGEM, y + 40),
        "Documento gerado automaticamente a cada envio. Cada linha é um envio para a máquina, não um "
        "item de pedido - reenvio do mesmo arquivo entra como linha nova e soma no subtotal, porque o "
        "material foi consumido de novo. A hora é a do envio para a fila.",
        fontsize=7, fontname=_FONTE, color=_CINZA_CLARO,
    )

    total = len(pdf)
    for indice, caixa in caixas_pagina:
        _escrever(pdf[indice], 0, caixa.y0, f"{indice + 1} / {total}", 7.5, _CINZA,
                  direita_em=LARGURA - MARGEM)

    destino = caminho_pdf(raiz_cliente)
    destino.parent.mkdir(parents=True, exist_ok=True)
    # garbage=4 + deflate=True é o padrão do resto do projeto (OS,
    # checklist unificado, relatório diário) e aqui vale ainda mais: o
    # documento é regravado do zero a cada envio e fica salvo o ano
    # todo. Sem isso, um documento de 3 páginas sai com 155 KB em vez
    # de 26 KB, quase tudo logo descomprimido (medido em 2026-09-05).
    pdf.save(str(destino), garbage=4, deflate=True)
    pdf.close()
    return destino


def regravar_pdf(raiz_cliente, ordem_categorias=None, agora=None):
    """
    Como gerar_pdf, mas devolve (caminho, erro) em vez de estourar —
    o caso real é o usuário estar com o documento aberto no leitor de
    PDF na hora do envio, e o Windows travar a regravação.

    Isso NUNCA pode derrubar o envio: nesse ponto os arquivos já foram
    copiados pra fila e já estão registrados no JSON. Só o desenho fica
    velho, e é só chamar de novo depois de fechar o documento.
    """
    try:
        return gerar_pdf(raiz_cliente, ordem_categorias, agora), None
    except Exception as e:
        return None, str(e)
