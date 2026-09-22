"""
Tira do PDF as marcas de corte que o arte-finalista deixa nos cantos —
sem encostar na arte.

Por que (pedido do usuário, 2026-09-11): "essa marca de corte adicionada
pelo arte finalista nos cantos, isso deve acontecer em todas, não é um
problema mas é preciso remover sem mexer na qualidade da arte em
hipótese alguma, somente remover marcas de corte".

O QUE ESSAS MARCAS SÃO
Não são desenho do arquivo: são coisa que o Illustrator PINTA na hora de
exportar o PDF, quando as opções de "Marcas e Sangrias" estão ligadas.
Junto com elas vem a tarja de informação (nome do arquivo, página, data).
A página exportada fica maior que a arte pra caber tudo isso.

POR QUE O CAMINHO É O ILLUSTRATOR (e por que ele é seguro aqui)
Arquivo salvo pelo arte-finalista traz '/PieceInfo /Illustrator' — o dado
editável do próprio Illustrator viaja dentro do PDF. Reabrindo, ele lê
esse dado, que é a ARTE, sem marca nenhuma; as marcas nunca existiram
como objeto. Salvando de novo com as marcas desligadas, o que sai é a
mesma arte sem a moldura. Não é apagar objeto: é reexportar sem pedir a
moldura.

A SANGRIA NÃO SE MEXE
"Somente remover marcas de corte" — então a sangria do original é medida
e devolvida igual. Sem isso, desligar as marcas encolheria a página até a
linha de corte e comeria a sangria junto.

A CONFERÊNCIA ANTES DE SUBSTITUIR
O original é sobrescrito (escolha dele: "pode ser até com o mesmo nome
sem criar cópias"), então o arquivo novo é conferido ANTES: medida de
corte igual, tarja de informação sumida, e a ARTE RENDERIZADA PIXEL A
PIXEL igual à do original. Falhou qualquer uma, o original fica como
estava. Sobrescrever arquivo de cliente sem conferir seria apostar.

CUIDADO COM /UserUnit
Arte grande passa dos 5,08 m que o PDF aceita por página, e o Illustrator
resolve isso com '/UserUnit' — os números das caixas ficam em décimos.
Este arquivo de 8,57 m tem UserUnit 10. Toda medida em metro aqui
multiplica por ele; esquecer isso dá erro de 10x calado.
"""
import os
import pathlib

try:
    import pythoncom
    import win32com.client
    COM_DISPONIVEL = True
except ImportError:
    COM_DISPONIVEL = False

_AI_NAO_EXIBIR_ALERTAS = 2   # aiDontDisplayAlerts
_AI_NAO_SALVAR = 2           # aiDoNotSaveChanges

# Quanto a medida de corte pode variar depois da volta pelo Illustrator.
# 0,5 pt em 24 mil é ruído de arredondamento, não mudança de tamanho.
_TOLERANCIA_PT = 0.5

# Como a arte é comparada antes de substituir o original. Pela DIFERENÇA
# MÉDIA, não pelo pior pixel — ver arte_esta_igual. Reprocessar o mesmo
# desenho dá média perto de 0 (peças pequenas ~0,6); lona grande e cheia
# de detalhe fino chega a ~3 só de ruído de rasterização (medido em lonas
# de 20-29 m, 2026-09-11). O limite fica bem acima disso e ainda longe de
# uma arte TROCADA, que daria dezenas.
_DIFERENCA_MEDIA_MAXIMA = 6.0
# Guarda secundária: no máximo esta fração da área pode diferir muito, pra
# pegar alteração localizada que a média diluiria.
_FRACAO_ALTERADA_MAXIMA = 0.05

# Largura do render de conferência. Suficiente pra pegar mudança de arte
# e barato o bastante pra rodar em arquivo de 9 metros.
_LARGURA_CONFERENCIA = 1600

_MARCAS = {
    "TrimMarks": False,
    "RegistrationMarks": False,
    "ColorBars": False,
    "PageInformation": False,
}


def _pymupdf():
    import pymupdf
    return pymupdf


def _caixa(doc, pagina, nome):
    tipo, valor = doc.xref_get_key(pagina.xref, nome)
    if tipo != "array":
        return None
    try:
        nums = [float(n) for n in valor.strip("[]").split()]
    except ValueError:
        return None
    return nums if len(nums) == 4 else None


def _unidade(doc, pagina):
    tipo, valor = doc.xref_get_key(pagina.xref, "UserUnit")
    try:
        return float(valor) if tipo in ("float", "int") else 1.0
    except (TypeError, ValueError):
        return 1.0


def medidas_da_pagina(doc, indice=0):
    """
    As medidas de UMA página de um documento já aberto. Existe separado
    porque PDF pode trazer peças diferentes em cada página: o TOTEM do
    Mandarin Sessions (2026-09-21) tinha 0,80x1,90 m na página 1 e um
    quadrado de 0,50x0,50 m na página 2 — medir só a primeira escondia a
    segunda peça.
    """
    pagina = doc[indice]
    unidade = _unidade(doc, pagina)
    fora = {"unidade": unidade, "paginas": doc.page_count, "pagina": indice}
    for nome in ("MediaBox", "CropBox", "TrimBox", "BleedBox"):
        caixa = _caixa(doc, pagina, nome)
        fora[nome] = caixa
        if caixa:
            fora[nome + "_pt"] = ((caixa[2] - caixa[0]) * unidade,
                                  (caixa[3] - caixa[1]) * unidade)
    fora["tem_texto"] = bool(pagina.get_text().strip())
    fora["rect"] = (pagina.rect.width, pagina.rect.height)
    return fora


def medidas(caminho, indice=0):
    """
    O que interessa saber de um PDF antes e depois: caixas, unidade e se
    tem tarja de informação. Devolve dicionário, ou None se não abrir.
    Por padrão a primeira página; 'indice' escolhe outra.
    """
    pymupdf = _pymupdf()
    try:
        doc = pymupdf.open(str(caminho))
    except Exception:
        return None
    try:
        return medidas_da_pagina(doc, indice)
    finally:
        doc.close()


def tem_marca_de_corte(dados):
    """
    True quando a página ainda traz a moldura de marcas de corte.

    A marca acrescenta espaço ALÉM da sangria — então a página (MediaBox)
    fica maior que a borda de sangria (BleedBox). Depois de removida,
    MediaBox = BleedBox, e o que sobra maior que o TrimBox é a sangria,
    que DEVE ficar. Comparar MediaBox com TrimBox (e não com BleedBox)
    confundiria a sangria com marca e removeria de novo o que já está
    limpo (visto em 2026-09-11). Sem BleedBox declarado, cai pra tarja de
    informação como sinal, ou pra diferença grande da página pro corte.
    """
    if not dados:
        return False
    media = dados.get("MediaBox_pt")
    if not media:
        return False
    sangria = dados.get("BleedBox_pt")
    if sangria:
        return (media[0] - sangria[0] > _TOLERANCIA_PT
                or media[1] - sangria[1] > _TOLERANCIA_PT)
    if dados.get("tem_texto"):
        return True
    corte = dados.get("TrimBox_pt")
    return bool(corte and (media[0] - corte[0] > _TOLERANCIA_PT
                           or media[1] - corte[1] > _TOLERANCIA_PT))


def sangria_em_pontos(dados):
    """
    Distância entre a linha de corte e a borda da sangria, em pontos
    reais (já multiplicada pelo UserUnit) — é o que o Illustrator espera
    em BleedOffset. Zero quando o arquivo não tem sangria declarada.
    """
    corte, sangria = dados.get("TrimBox"), dados.get("BleedBox")
    if not corte or not sangria:
        return 0.0
    folgas = [corte[0] - sangria[0], corte[1] - sangria[1],
              sangria[2] - corte[2], sangria[3] - corte[3]]
    folga = max(folgas)
    return round(max(0.0, folga) * dados.get("unidade", 1.0), 3)


def _recorte_do_corte(pagina, dados):
    """
    O retângulo da ARTE (área de corte) dentro do render da página.

    Calculado por proporção sobre a página, e não em pontos: os dois
    arquivos têm páginas de tamanho diferente — é justamente o que muda —
    e a proporção é o que permite comparar a mesma região dos dois.
    """
    pymupdf = _pymupdf()
    media, corte = dados.get("MediaBox"), dados.get("TrimBox")
    if not media or not corte:
        return pagina.rect
    largura = media[2] - media[0]
    altura = media[3] - media[1]
    if largura <= 0 or altura <= 0:
        return pagina.rect
    r = pagina.rect
    # PDF conta do rodapé pra cima; o render conta do topo pra baixo.
    return pymupdf.Rect(
        r.x0 + r.width * (corte[0] - media[0]) / largura,
        r.y0 + r.height * (media[3] - corte[3]) / altura,
        r.x0 + r.width * (corte[2] - media[0]) / largura,
        r.y0 + r.height * (media[3] - corte[1]) / altura,
    )


def _render_da_arte(caminho, dados, largura_px=_LARGURA_CONFERENCIA):
    """Imagem PIL (RGB) só da área de corte — a arte, sem a moldura."""
    from PIL import Image

    pymupdf = _pymupdf()
    doc = pymupdf.open(str(caminho))
    try:
        pagina = doc[0]
        recorte = _recorte_do_corte(pagina, dados)
        if recorte.width <= 0:
            return None
        escala = largura_px / recorte.width
        px = pagina.get_pixmap(matrix=pymupdf.Matrix(escala, escala), clip=recorte)
        modo = "RGB" if px.n < 4 else "RGBA"
        return Image.frombytes(modo, (px.width, px.height), px.samples).convert("RGB")
    finally:
        doc.close()


def arte_esta_igual(antes, depois, media_maxima=_DIFERENCA_MEDIA_MAXIMA,
                    fracao_maxima=_FRACAO_ALTERADA_MAXIMA):
    """
    True quando a área de corte dos dois arquivos desenha a mesma coisa.

    Compara pela DIFERENÇA MÉDIA por canal, não pelo pior pixel: a
    remoção de marca reprocessa o MESMO desenho pelo Illustrator, e o
    recorte pode sair com meio pixel de desencontro nas bordas — isso
    infla o pior pixel sem a arte ter mudado (medido: pior 20, média
    0,66, 2026-09-11). A média separa limpo os dois casos: reprocessar
    dá média perto de zero; arte trocada daria média nas dezenas.

    A fração de pixels muito diferentes é a guarda secundária: pega uma
    alteração localizada (um texto trocado num canto) que a média
    diluiria. Devolve (igual, explicação).
    """
    if antes is None or depois is None:
        return False, "não consegui renderizar a arte pra comparar"
    if depois.size != antes.size:
        depois = depois.resize(antes.size)   # alinha o desencontro de borda

    from PIL import ImageChops
    dif = ImageChops.difference(antes, depois)
    pixels = antes.size[0] * antes.size[1]
    if not pixels:
        return False, "área de corte vazia"

    soma = sum(v * i for i, v in enumerate(dif.convert("L").histogram()))
    media = soma / pixels
    limiar = 40
    alterados = sum(n for i, n in enumerate(dif.convert("L").histogram()) if i > limiar)
    fracao = alterados / pixels

    if media > media_maxima:
        return False, "a arte mudou (diferença média de %.1f em 255)" % media
    if fracao > fracao_maxima:
        return False, ("a arte mudou em %.1f%% da área (acima de %d/255)"
                       % (fracao * 100, limiar))
    return True, ("arte idêntica (diferença média %.2f em 255, %.2f%% da área alterada)"
                  % (media, fracao * 100))


def remover_marcas_de_corte(caminho_pdf, logger=None):
    """
    Abre no Illustrator, salva sem as marcas e substitui o original.

    Nunca fecha o Illustrator (o usuário costuma estar com arquivos
    abertos nele — ver conversao_adobe): só fecha o documento que esta
    função abriu, sem salvar por cima dele.

    Devolve (trocou, mensagem). Em qualquer falha o original fica
    exatamente como estava.
    """
    def avisar(nivel, texto):
        if logger:
            logger(nivel, texto)

    if not COM_DISPONIVEL:
        return False, "pywin32 não está instalado — não dá pra automatizar o Illustrator."

    caminho_pdf = pathlib.Path(caminho_pdf)
    if not caminho_pdf.is_file():
        return False, "arquivo não encontrado: %s" % caminho_pdf

    antes = medidas(caminho_pdf)
    if not antes or not antes.get("TrimBox"):
        return False, ("'%s' não tem área de corte (TrimBox) declarada — sem ela não dá pra "
                       "saber o que é arte e o que é marca. Não mexi." % caminho_pdf.name)

    if not tem_marca_de_corte(antes):
        return False, "'%s' já está sem marcas de corte." % caminho_pdf.name

    sangria = sangria_em_pontos(antes)
    temporario = caminho_pdf.with_name("~sem_marcas~%s" % caminho_pdf.name)

    pythoncom.CoInitialize()
    app = win32com.client.Dispatch("Illustrator.Application")
    app.UserInteractionLevel = _AI_NAO_EXIBIR_ALERTAS
    doc = app.Open(str(caminho_pdf))
    try:
        opcoes = win32com.client.Dispatch("Illustrator.PDFSaveOptions")
        # Cada opção é tentada uma a uma: versão de Illustrator que não
        # conhecer alguma não pode derrubar a operação inteira. O que
        # vale mesmo é a conferência do resultado, logo abaixo — opção
        # que não pegou aparece lá como marca que sobrou.
        for propriedade, valor in _MARCAS.items():
            try:
                setattr(opcoes, propriedade, valor)
            except Exception:
                avisar("warn", "Este Illustrator não aceitou desligar '%s'." % propriedade)
        try:
            opcoes.PreserveEditability = True
        except Exception:
            pass
        try:
            opcoes.BleedOffset = sangria
        except Exception:
            # Nem toda versão aceita escrever isso, e não é problema: a
            # sangria mora no documento do Illustrator, não na opção de
            # exportação. Quem garante é a conferência lá embaixo, que
            # exige a página nova bater com a caixa de sangria do
            # original. Avisar aqui seria assustar à toa.
            pass
        doc.SaveAs(str(temporario), opcoes)
    except Exception as e:
        try:
            temporario.unlink()
        except OSError:
            pass
        return False, "o Illustrator não conseguiu salvar '%s': %s" % (caminho_pdf.name, e)
    finally:
        try:
            doc.Close(_AI_NAO_SALVAR)
        except Exception:
            pass

    if not temporario.is_file():
        return False, "o Illustrator não gerou o arquivo novo. O original ficou intacto."

    trocou, mensagem = _conferir_e_trocar(caminho_pdf, temporario, antes)
    return trocou, mensagem


def _conferir_e_trocar(original, novo, antes):
    """Só substitui se a arte estiver igual e as marcas tiverem saído."""
    depois = medidas(novo)
    if not depois:
        novo.unlink(missing_ok=True)
        return False, "o arquivo que saiu do Illustrator não abriu. O original ficou intacto."

    corte_antes, corte_depois = antes.get("TrimBox_pt"), depois.get("TrimBox_pt")
    if corte_antes and corte_depois:
        erro = max(abs(a - b) for a, b in zip(corte_antes, corte_depois))
        if erro > _TOLERANCIA_PT:
            novo.unlink(missing_ok=True)
            return False, ("a área de corte mudou de tamanho (%.1f pt de diferença). "
                           "NÃO troquei — o original continua lá." % erro)

    igual, explicacao = arte_esta_igual(
        _render_da_arte(original, antes), _render_da_arte(novo, depois))
    if not igual:
        novo.unlink(missing_ok=True)
        return False, "%s. NÃO troquei — o original continua lá." % explicacao

    # A sangria tem que ter sobrevivido inteira: a página nova precisa
    # ser exatamente a caixa de sangria do original. É esta conferência
    # que substitui o palpite do BleedOffset.
    sangria_antes = antes.get("BleedBox_pt")
    media_nova = depois.get("MediaBox_pt")
    if sangria_antes and media_nova:
        erro = max(abs(a - b) for a, b in zip(sangria_antes, media_nova))
        if erro > _TOLERANCIA_PT:
            novo.unlink(missing_ok=True)
            return False, ("a sangria mudou: a página nova tem %.2f x %.2f m e a sangria do "
                           "original era %.2f x %.2f m. NÃO troquei — o original continua lá."
                           % (media_nova[0] * 0.0254 / 72, media_nova[1] * 0.0254 / 72,
                              sangria_antes[0] * 0.0254 / 72, sangria_antes[1] * 0.0254 / 72))

    # A prova de que a marca e a tarja saíram é a página ter ENCOLHIDO até
    # a sangria — a tarja mora fora dela, então some junto. NÃO se checa
    # "sobrou texto": arte de verdade tem texto próprio (logo, slogan), e
    # confundir isso com a tarja recusava a troca de artes perfeitas — 3
    # lonas do Mercado Livre travaram por isso (2026-09-11), com a página
    # encolhida e a arte idêntica.
    media_depois = depois.get("MediaBox_pt")
    media_antes = antes.get("MediaBox_pt")
    if media_depois and media_antes and media_depois[0] >= media_antes[0] - _TOLERANCIA_PT:
        novo.unlink(missing_ok=True)
        return False, ("a página não encolheu — as marcas parecem continuar lá. "
                       "NÃO troquei — o original continua lá.")

    os.replace(str(novo), str(original))
    mp = 0.0254 / 72
    return True, ("marcas removidas de '%s': página de %.2f x %.2f m virou %.2f x %.2f m, "
                  "arte de %.2f x %.2f m intacta (%s)." % (
                      original.name,
                      media_antes[0] * mp, media_antes[1] * mp,
                      media_depois[0] * mp, media_depois[1] * mp,
                      corte_depois[0] * mp, corte_depois[1] * mp, explicacao))


# Tempo que o Illustrator tem pra devolver o arquivo antes de a gente
# desistir. Ele já travou de vez no meio do 'salvar' (2026-09-11) e
# pendurou o processo inteiro. Num lote de 93 artes, uma trava não pode
# parar as outras — passado este limite, aborta esta arte e segue.
# Era 150 s até 2026-09-21: a parede externa do EIXO PRINCIPAL (3,7 MB)
# estourou os 150 s no lote de 20/09 e passou em 2 s na segunda tentativa.
# Travar de vez continua pego; arte grande num Illustrator lento, não.
_LIMITE_ILLUSTRATOR_S = 300


def remover_marcas_com_limite(caminho_pdf, timeout_s=_LIMITE_ILLUSTRATOR_S, logger=None):
    """
    Igual a remover_marcas_de_corte, mas num processo à parte com
    tempo-limite: se o Illustrator travar, o processo é morto e a função
    volta com um aviso, em vez de pendurar pra sempre. O original nunca
    fica corrompido — a troca lá dentro só acontece depois da conferência.
    """
    import subprocess
    import sys

    caminho_pdf = pathlib.Path(caminho_pdf)
    codigo = (
        "import sys, marcas_de_corte as m;"
        "ok, msg = m.remover_marcas_de_corte(sys.argv[1]);"
        "print('OK' if ok else 'NAO', msg)"
    )
    # O filho fala UTF-8 na força: sem isto o print dele vai pro cano em
    # cp1252 (padrão do Windows) e QUALQUER caractere fora do Latin-1 na
    # mensagem de erro do Illustrator derruba o filho com 'charmap codec
    # can't encode' — a falha real some e vira um traceback ilegível que
    # ainda derruba o pai ao logar (visto no Mercado Livre, 2026-09-12).
    ambiente = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    try:
        saida = subprocess.run(
            [sys.executable, "-c", codigo, str(caminho_pdf)],
            cwd=str(pathlib.Path(__file__).parent), env=ambiente,
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=timeout_s)
    except subprocess.TimeoutExpired:
        if logger:
            logger("warn", "O Illustrator não respondeu em %ds; abandonei a remoção "
                           "de marca desta arte. Ela segue com a marca." % timeout_s)
        return False, "o Illustrator travou (mais de %ds)" % timeout_s

    linha = (saida.stdout or "").strip().splitlines()
    resposta = linha[-1] if linha else ""
    ok = resposta.startswith("OK")
    mensagem = resposta[3:].strip() if resposta[:3] in ("OK ", "NAO") else (
        saida.stderr.strip()[-200:] or "sem resposta do Illustrator")
    if logger and not ok:
        logger("warn", "Não removi a marca: %s" % mensagem)
    return ok, mensagem


# ======================================================================
# IMAGEM (TIFF, JPG, PNG, PSD): não declara onde a arte acaba
# ======================================================================
#
# No PDF a arte se DECLARA (TrimBox, BleedBox). Numa imagem, a marca de
# corte é só pixel preto no canto — pra tirar, é preciso ACHAR a linha de
# corte. Provado em 2026-09-21 com gabarito (um PDF que declara o TrimBox,
# rasterizado e lido só por pixel): erro de 0,3 mm numa peça de 5,20 m.
#
# O que faz funcionar é cruzar margens opostas: a marca de corte de
# verdade aparece em cima E embaixo na mesma posição; a tarja de
# informação do Illustrator (nome do arquivo, data), que mora só em cima,
# não tem par e cai fora sozinha — no teste eram 19 falsos positivos.
#
# E aqui a detecção vale mais que o corte: numa imagem com marca, o
# tamanho pelo DPI é o da imagem INTEIRA, com moldura. A medida da arte —
# a que vai no nome — é a distância entre as marcas.
#
# Regra do usuário (2026-09-21): o sistema PROPÕE, ele APROVA. Nada é
# cortado sem o OK, e o corte mantém a sangria, como no PDF.

# Acima disto o Pillow não abre a imagem inteira com folga (TIFF de GB já
# travou o PyMuPDF por minutos, 2026-08-31): o Photoshop reduz antes.
LIMITE_DETECCAO_PIXELS = 90_000_000
# Resolução em que a detecção trabalha. Numa peça de 5,7 m dá ~1 mm por
# pixel — foi nessa que o erro medido foi 0,3 mm.
LARGURA_DETECCAO = 6000
_LIMIAR_TINTA = 245
# Margens opostas discordando mais que isto: a detecção não é confiável.
_DESACORDO_MAXIMO_MM = 3.0
_LIMITE_PHOTOSHOP_S = 600
# Comparar pixel a pixel carrega a imagem inteira em RGB (3 bytes/pixel):
# até aqui cabe com folga; acima, confere tamanho e resolução.
_LIMITE_COMPARACAO_PIXELS = 40_000_000
_EXTENSOES_IMAGEM = (".tif", ".tiff", ".jpg", ".jpeg", ".png", ".psd")


def _valores(imagem):
    """Os pixels numa lista — getdata() foi descontinuado no Pillow novo."""
    ler = getattr(imagem, "get_flattened_data", None) or imagem.getdata
    return list(ler())


def _maior_bloco(perfil, limiar):
    """Maior faixa contígua acima do limiar — o bloco da arte com sangria."""
    melhor, inicio = (0, -1), None
    for i, v in enumerate(perfil):
        if v > limiar and inicio is None:
            inicio = i
        elif v <= limiar and inicio is not None:
            if i - 1 - inicio > melhor[1] - melhor[0]:
                melhor = (inicio, i - 1)
            inicio = None
    if inicio is not None and len(perfil) - 1 - inicio > melhor[1] - melhor[0]:
        melhor = (inicio, len(perfil) - 1)
    return melhor


def _grupos(indices, folga=4):
    """Índices vizinhos juntos: cada grupo é uma linha de marca."""
    if not indices:
        return []
    saida, atual = [], [indices[0]]
    for i in indices[1:]:
        if i - atual[-1] <= folga:
            atual.append(i)
        else:
            saida.append(atual)
            atual = [i]
    saida.append(atual)
    return [(g[0] + g[-1]) / 2 for g in saida]


def _cruzar(a, b, tolerancia):
    """Só o que aparece nas duas margens opostas, na mesma posição."""
    pares = []
    for va in a:
        perto = [vb for vb in b if abs(va - vb) <= tolerancia]
        if perto:
            vb = min(perto, key=lambda v: abs(va - v))
            pares.append(((va + vb) / 2, abs(va - vb)))
    return pares


def detectar_corte_em_imagem(cinza):
    """
    Onde está a linha de corte numa imagem (Pillow, modo 'L'), só olhando
    pixel. Devolve dict com 'corte' (x0, y0, x1, y1), 'bloco' (a arte com
    sangria), 'desacordo_px' e 'notas'; ou None + notas quando não acha
    exatamente um par de marcas por eixo.
    """
    from PIL import Image
    tinta = cinza.point(lambda v: 255 if v < _LIMIAR_TINTA else 0, mode="L")
    largura, altura = tinta.size
    notas = []

    # média de tinta por coluna e por linha, numa passada só (reamostra por área)
    colunas = _valores(tinta.resize((largura, 1), Image.Resampling.BOX))
    linhas = _valores(tinta.resize((1, altura), Image.Resampling.BOX))
    bx0, bx1 = _maior_bloco(colunas, 255 * 0.30)
    by0, by1 = _maior_bloco(linhas, 255 * 0.30)
    if bx1 <= bx0 or by1 <= by0:
        return None, ["não achei o bloco da arte"]

    faixa = max(5, int(0.012 * largura))

    def com_tinta(caixa, eixo):
        recorte = tinta.crop(caixa)
        if recorte.width <= 0 or recorte.height <= 0:
            return []
        px, py = recorte.getprojection()
        return [i for i, v in enumerate(py if eixo == "y" else px) if v]

    ys_esq = _grupos(com_tinta((max(0, bx0 - faixa), 0, max(1, bx0 - 2), altura), "y"))
    ys_dir = _grupos(com_tinta((min(largura - 1, bx1 + 2), 0, min(largura, bx1 + faixa), altura), "y"))
    xs_cima = _grupos(com_tinta((0, max(0, by0 - faixa), largura, max(1, by0 - 2)), "x"))
    xs_baixo = _grupos(com_tinta((0, min(altura - 1, by1 + 2), largura, min(altura, by1 + faixa)), "x"))

    tolerancia = max(3, int(0.002 * largura))
    pares_y = _cruzar(ys_esq, ys_dir, tolerancia)
    pares_x = _cruzar(xs_cima, xs_baixo, tolerancia)
    notas.append("marcas que batem nas margens opostas: %d na vertical, %d na horizontal"
                 % (len(pares_y), len(pares_x)))
    if len(pares_y) != 2 or len(pares_x) != 2:
        return None, notas + ["esperava 2 marcas em cada eixo — sem isso não dá pra confiar"]

    return {
        "corte": (pares_x[0][0], pares_y[0][0], pares_x[1][0], pares_y[1][0]),
        "bloco": (bx0, by0, bx1 + 1, by1 + 1),
        "desacordo_px": max(d for _, d in pares_y + pares_x),
        "notas": notas,
    }, notas


def _reduzir_pelo_photoshop(origem, destino_png, largura):
    """Imagem grande demais pro Pillow: o Photoshop abre e salva uma cópia reduzida."""
    import subprocess
    import sys
    codigo = ("import sys, marcas_de_corte as m;"
              "m._reduzir_no_photoshop(sys.argv[1], sys.argv[2], int(sys.argv[3]));"
              "print('OK')")
    ambiente = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    saida = subprocess.run([sys.executable, "-c", codigo, str(origem), str(destino_png), str(largura)],
                           cwd=str(pathlib.Path(__file__).parent), env=ambiente, capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=_LIMITE_PHOTOSHOP_S)
    if "OK" not in (saida.stdout or ""):
        raise RuntimeError((saida.stderr or "o Photoshop não reduziu a imagem").strip()[-300:])
    return destino_png


def _reduzir_no_photoshop(origem, destino_png, largura):
    pythoncom.CoInitialize()
    app = win32com.client.Dispatch("Photoshop.Application")
    app.DisplayDialogs = 3                      # psDisplayNoDialogs
    unidades = app.Preferences.RulerUnits
    app.Preferences.RulerUnits = 1              # psPixels
    try:
        doc = app.Open(str(origem))
        try:
            altura = float(doc.Height) * largura / float(doc.Width)
            doc.ResizeImage(largura, altura)
            doc.SaveAs(str(destino_png), win32com.client.Dispatch("Photoshop.PNGSaveOptions"), True)
        finally:
            doc.Close(2)                        # psDoNotSaveChanges: o original não muda
    finally:
        app.Preferences.RulerUnits = unidades


def propor_corte_imagem(caminho, reduzir=None, pasta_temporaria=None):
    """
    A proposta de corte de uma imagem com marca, pra ele aprovar.

    Devolve dict: 'ok' (achou e confia), 'motivo', 'largura_px',
    'altura_px', 'dpi', 'corte_px' (a linha de corte, na resolução do
    arquivo), 'sangria_px' (quanto de sangria fica em cada lado, em
    pixel do arquivo), 'desacordo_mm', 'previa' (imagem reduzida pra
    mostrar) e 'escala_previa' (px da prévia por px do arquivo).
    """
    from PIL import Image
    caminho = pathlib.Path(caminho)
    fora = {"ok": False, "motivo": "", "corte_px": None, "sangria_px": 0, "previa": None}
    try:
        with Image.open(str(caminho)) as img:
            largura, altura = img.size
            dpi = img.info.get("dpi")
            fora.update(largura_px=largura, altura_px=altura,
                        dpi=float(dpi[0]) if dpi and dpi[0] else None)
            previa_cor = None
            if largura * altura <= LIMITE_DETECCAO_PIXELS:
                if img.format == "JPEG" and largura > LARGURA_DETECCAO:
                    img.draft("RGB", (LARGURA_DETECCAO, int(altura * LARGURA_DETECCAO / largura)))
                img.load()
                trabalho = img.convert("L")
                # a prévia que ele olha é EM COR — a cinza é só pra achar a marca
                fator = max(1, -(-max(img.size) // 1400))
                try:
                    previa_cor = img.reduce(fator).convert("RGB")
                except ValueError:
                    # reduce() não aceita todo modo (TIFF CMYK de impressão)
                    previa_cor = img.convert("RGB").reduce(fator)
            else:
                trabalho = None
    except Exception as e:
        fora["motivo"] = "a imagem não abriu: %s" % e
        return fora

    if trabalho is None:
        # grande demais pro Pillow: o Photoshop reduz uma cópia
        import tempfile
        reduzir = reduzir or _reduzir_pelo_photoshop
        pasta = pathlib.Path(pasta_temporaria or tempfile.gettempdir())
        png = pasta / ("~deteccao~%s.png" % caminho.stem)
        try:
            reduzir(caminho, png, LARGURA_DETECCAO)
            with Image.open(str(png)) as reduzida:
                trabalho = reduzida.convert("L")
                previa_cor = reduzida.convert("RGB")
        except Exception as e:
            fora["motivo"] = "o Photoshop não conseguiu reduzir a imagem pra procurar a marca: %s" % e
            return fora
        finally:
            png.unlink(missing_ok=True)

    if trabalho.width > LARGURA_DETECCAO:
        trabalho = trabalho.resize(
            (LARGURA_DETECCAO, max(1, round(trabalho.height * LARGURA_DETECCAO / trabalho.width))),
            Image.Resampling.BOX)
    # medida NO FIM: o JPEG já pode ter aberto reduzido (modo rascunho) e o
    # Photoshop entrega a cópia reduzida — a escala é sempre detecção ÷ arquivo
    escala = trabalho.width / largura

    previa = previa_cor if previa_cor is not None else trabalho.convert("RGB")
    previa.thumbnail((1400, 1400))
    fora["previa"] = previa
    fora["escala_previa"] = previa.width / largura

    achado, notas = detectar_corte_em_imagem(trabalho)
    if not achado:
        fora["motivo"] = "; ".join(notas)
        return fora

    x0, y0, x1, y1 = (v / escala for v in achado["corte"])
    b0, c0, b1, c1 = (v / escala for v in achado["bloco"])
    # sangria que fica: o menor lado em que a arte chega até a borda — lado
    # com fundo branco encolhe o bloco e não pode ditar a sangria
    lados = [x0 - b0, y0 - c0, b1 - x1, c1 - y1]
    positivos = [v for v in lados if v > 1]
    sangria = min(positivos) if positivos else 0.0
    mm_por_px = (25.4 / fora["dpi"]) if fora["dpi"] else None
    desacordo_mm = achado["desacordo_px"] / escala * mm_por_px if mm_por_px else None

    fora.update(corte_px=(round(x0), round(y0), round(x1), round(y1)),
                sangria_px=round(sangria), desacordo_mm=desacordo_mm, notas=notas)
    if desacordo_mm is not None and desacordo_mm > _DESACORDO_MAXIMO_MM:
        fora["motivo"] = ("as marcas de lados opostos discordam em %.1f mm — confira antes de aprovar"
                          % desacordo_mm)
        return fora
    fora["ok"] = True
    fora["motivo"] = "marcas encontradas nos quatro lados, batendo entre si"
    return fora


def retangulo_do_corte(proposta, sangria_px=None):
    """
    O retângulo que FICA: a linha de corte mais a sangria de cada lado,
    sem passar da imagem. É o que vai pro Photoshop.
    """
    x0, y0, x1, y1 = proposta["corte_px"]
    s = proposta["sangria_px"] if sangria_px is None else sangria_px
    return (max(0, int(x0 - s)), max(0, int(y0 - s)),
            min(proposta["largura_px"], int(round(x1 + s))), min(proposta["altura_px"], int(round(y1 + s))))


def medidas_da_proposta(proposta, sangria_px=None):
    """(arte_m, sangria_m) da proposta: a arte é entre as marcas; a sangria, o que fica."""
    dpi = proposta.get("dpi")
    if not dpi or not proposta.get("corte_px"):
        return None, None
    m_por_px = 0.0254 / dpi
    x0, y0, x1, y1 = proposta["corte_px"]
    r = retangulo_do_corte(proposta, sangria_px)
    return ((x1 - x0) * m_por_px, (y1 - y0) * m_por_px), ((r[2] - r[0]) * m_por_px, (r[3] - r[1]) * m_por_px)


def _cortar_no_photoshop(origem, destino, x0, y0, x1, y1):
    """Corta no Photoshop e salva uma CÓPIA no mesmo formato. Roda no processo filho."""
    pythoncom.CoInitialize()
    app = win32com.client.Dispatch("Photoshop.Application")
    app.DisplayDialogs = 3
    unidades = app.Preferences.RulerUnits
    app.Preferences.RulerUnits = 1              # psPixels
    try:
        doc = app.Open(str(origem))
        try:
            doc.Crop([x0, y0, x1, y1])
            ext = pathlib.Path(destino).suffix.lower()
            if ext in (".tif", ".tiff"):
                opcoes = win32com.client.Dispatch("Photoshop.TiffSaveOptions")
                opcoes.ImageCompression = 2     # LZW: sem perda
            elif ext in (".jpg", ".jpeg"):
                opcoes = win32com.client.Dispatch("Photoshop.JPEGSaveOptions")
                opcoes.Quality = 12             # máxima: salvar JPG recomprime
            elif ext == ".png":
                opcoes = win32com.client.Dispatch("Photoshop.PNGSaveOptions")
            else:
                opcoes = win32com.client.Dispatch("Photoshop.PhotoshopSaveOptions")
            doc.SaveAs(str(destino), opcoes, True)
        finally:
            doc.Close(2)
    finally:
        app.Preferences.RulerUnits = unidades


def _cortar_pelo_photoshop(origem, destino, retangulo, timeout_s=_LIMITE_PHOTOSHOP_S):
    """O Photoshop num processo à parte, com tempo-limite — como o Illustrator."""
    import subprocess
    import sys
    codigo = ("import sys, marcas_de_corte as m;"
              "m._cortar_no_photoshop(sys.argv[1], sys.argv[2], *map(int, sys.argv[3:7]));"
              "print('OK')")
    ambiente = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    try:
        saida = subprocess.run([sys.executable, "-c", codigo, str(origem), str(destino), *map(str, retangulo)],
                               cwd=str(pathlib.Path(__file__).parent), env=ambiente, capture_output=True,
                               text=True, encoding="utf-8", errors="replace", timeout=timeout_s)
    except subprocess.TimeoutExpired:
        raise RuntimeError("o Photoshop não respondeu em %ds" % timeout_s)
    if "OK" not in (saida.stdout or ""):
        raise RuntimeError((saida.stderr or "o Photoshop não cortou").strip()[-300:])


def cortar_imagem(caminho, retangulo, logger=None, cortador=None):
    """
    Corta a imagem em 'caminho' pro 'retangulo' (x0, y0, x1, y1, em pixel
    do arquivo) — no lugar, mas só depois de conferir. Quem chama passa a
    CÓPIA de trabalho: o original recebido nunca é tocado.

    Confere antes de trocar: o tamanho em pixel tem que ser o do corte, a
    resolução (DPI) tem que continuar a mesma, e — quando a imagem cabe no
    Pillow — o miolo cortado tem que desenhar igual ao mesmo pedaço do
    original. 'cortador' existe pro teste não precisar do Photoshop.
    Devolve (ok, mensagem).
    """
    from PIL import Image
    caminho = pathlib.Path(caminho)
    cortador = cortador or _cortar_pelo_photoshop
    novo = caminho.with_name("~cortada~" + caminho.name)
    x0, y0, x1, y1 = map(int, retangulo)
    try:
        cortador(caminho, novo, (x0, y0, x1, y1))
    except Exception as e:
        novo.unlink(missing_ok=True)
        return False, str(e)
    if not novo.is_file():
        return False, "o arquivo cortado não apareceu"
    try:
        with Image.open(str(caminho)) as antes, Image.open(str(novo)) as depois:
            tamanho_ok = abs(depois.width - (x1 - x0)) <= 1 and abs(depois.height - (y1 - y0)) <= 1
            dpi_a, dpi_d = antes.info.get("dpi"), depois.info.get("dpi")
            dpi_ok = not dpi_a or (dpi_d and abs(float(dpi_a[0]) - float(dpi_d[0])) < 0.5)
            igual, explicacao = True, "imagem grande demais pra comparar pixel a pixel; conferido o tamanho"
            if tamanho_ok and antes.width * antes.height <= _LIMITE_COMPARACAO_PIXELS:
                pedaco = antes.convert("RGB").crop((x0, y0, x1, y1))
                pedaco.thumbnail((_LARGURA_CONFERENCIA, _LARGURA_CONFERENCIA))
                cortada = depois.convert("RGB")
                cortada.thumbnail((_LARGURA_CONFERENCIA, _LARGURA_CONFERENCIA))
                igual, explicacao = arte_esta_igual(pedaco, cortada)
    except Exception as e:
        novo.unlink(missing_ok=True)
        return False, "não consegui conferir o corte: %s" % e
    if not tamanho_ok:
        novo.unlink(missing_ok=True)
        return False, "o corte saiu com outro tamanho. NÃO troquei — o original continua lá."
    if not dpi_ok:
        novo.unlink(missing_ok=True)
        return False, "a resolução mudou no corte (%s -> %s dpi). NÃO troquei." % (dpi_a, dpi_d)
    if not igual:
        novo.unlink(missing_ok=True)
        return False, "%s. NÃO troquei — o original continua lá." % explicacao
    os.replace(str(novo), str(caminho))
    if logger:
        logger("ok", "marca de corte cortada de '%s': %s" % (caminho.name, explicacao))
    return True, explicacao


if __name__ == "__main__":
    # Chamado como subprocesso por remover_marcas_com_limite.
    import sys
    if len(sys.argv) > 1:
        ok, msg = remover_marcas_de_corte(sys.argv[1])
        print("OK" if ok else "NAO", msg)
