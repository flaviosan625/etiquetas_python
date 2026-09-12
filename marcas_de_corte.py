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


def medidas(caminho):
    """
    O que interessa saber de um PDF antes e depois: caixas, unidade e se
    tem tarja de informação. Devolve dicionário, ou None se não abrir.
    """
    pymupdf = _pymupdf()
    try:
        doc = pymupdf.open(str(caminho))
    except Exception:
        return None
    try:
        pagina = doc[0]
        unidade = _unidade(doc, pagina)
        fora = {"unidade": unidade, "paginas": doc.page_count}
        for nome in ("MediaBox", "CropBox", "TrimBox", "BleedBox"):
            caixa = _caixa(doc, pagina, nome)
            fora[nome] = caixa
            if caixa:
                fora[nome + "_pt"] = ((caixa[2] - caixa[0]) * unidade,
                                      (caixa[3] - caixa[1]) * unidade)
        fora["tem_texto"] = bool(pagina.get_text().strip())
        fora["rect"] = (pagina.rect.width, pagina.rect.height)
        return fora
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
_LIMITE_ILLUSTRATOR_S = 150


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
    try:
        saida = subprocess.run(
            [sys.executable, "-c", codigo, str(caminho_pdf)],
            cwd=str(pathlib.Path(__file__).parent),
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


if __name__ == "__main__":
    # Chamado como subprocesso por remover_marcas_com_limite.
    import sys
    if len(sys.argv) > 1:
        ok, msg = remover_marcas_de_corte(sys.argv[1])
        print("OK" if ok else "NAO", msg)
