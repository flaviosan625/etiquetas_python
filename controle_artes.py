"""
NOSSA planilha de controle: cruza o caderno de arte do cliente com a
planilha de status do cliente, numa lista só.

Por que existe (pedido do usuário, 2026-09-11): "uma planilha nossa que
vamos usar para fazer o cruzamento com caderno com a planilha do cliente
para não deixar nada para trás".

Nenhum dos dois documentos do cliente mostra o que falta. O caderno tem
as peças desenhadas; a planilha tem as peças cobradas. **O que se perde é
justamente a peça que está num e não está no outro** — e isso só aparece
quando os dois viram uma lista só. No primeiro cruzamento real foram 16
peças só no caderno e 63 só na planilha: nenhuma casou, porque eram
documentos de áreas diferentes do mesmo evento. Sem esta planilha isso
seguiria invisível.

COMO O PAR É FEITO
Medida igual E nome parecido. Medida sozinha NÃO serve: 5,00 x 3,00 é
comum, e casou "PAINEL DE FUNDO" com "VISTA PAREDE DO DEPÓSITO", de
outra área (visto em 2026-09-11). Nome sozinho também não: a mesma peça
é "TESTEIRA ARENA" no caderno e "TESTEIRA - LONA" na planilha. Sem par,
a linha fica marcada — nunca inventada.

A COLUNA "OBSERVAÇÃO NOSSA" É DO USUÁRIO
A planilha se refaz a cada verificação, mas o que ele escreveu tem que
sobreviver. As observações são reancoradas por DUAS chaves (decisão
dele, 2026-09-11: "pode ser os dois"): caderno+slide e caderno+nome da
peça. Slide sobrevive a peça renomeada; nome sobrevive a slide movido.
O que não achar âncora nenhuma vai pro fim marcado como ÓRFÃ — apagar
observação em silêncio seria perder trabalho de gente.
"""
import datetime
import pathlib
import re
import unicodedata

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

import caderno_arte

ABA = "CONTROLE"
ABA_CLIENTE = "Status AFs"
LINHA_CABECALHO = 5

MARCA_SO_CADERNO = "SÓ NO CADERNO"
MARCA_SO_PLANILHA = "SEM SLIDE NO CADERNO"
MARCA_DIVERGENTE = "DIVERGENTE"
MARCA_CONFERE = "confere"
MARCA_ORFA = "OBSERVAÇÃO ÓRFÃ"

_TINTA = "12161D"
_CAB = "1F3A4A"
_FUNDO_FALTA = "FDF2E0"
_FUNDO_DIVERG = "FBECEB"
_FUNDO_OK = "EAF4EC"

COLUNAS = [
    ("ORIGEM", 11), ("ÁREA / CADERNO", 26), ("PEÇA", 32), ("MATERIAL", 20),
    ("QTD", 5), ("MEDIDA", 14), ("SANGRIA", 14),
    ("STATUS CADERNO", 15), ("STATUS PLANILHA", 16), ("CONFERE?", 21),
    ("ARQUIVO NO NOSSO PADRÃO", 46), ("BAIXADO EM", 15),
    ("LINK DA ARTE", 44), ("OBSERVAÇÃO NOSSA", 30),
]
_CAMPOS = ["origem", "area", "peca", "material", "quantidade", "medida", "sangria",
           "status_caderno", "status_planilha", "confere", "arquivo", "baixado",
           "link", "observacao"]


def _normalizar(texto):
    t = unicodedata.normalize("NFKD", str(texto or ""))
    t = "".join(c for c in t if not unicodedata.combining(c)).upper()
    return re.sub(r"\s+", " ", re.sub(r"[^A-Z0-9 ]+", " ", t)).strip()


def _medida_par(texto):
    m = re.match(r"^\s*([\d.,]+)\s*[Xx]\s*([\d.,]+)", str(texto or ""))
    if not m:
        return None
    return (round(float(m.group(1).replace(",", ".")), 2),
            round(float(m.group(2).replace(",", ".")), 2))


def ler_planilha_do_cliente(caminho):
    """
    A aba 'Status AFs' da planilha do cliente.

    A primeira coluna é vazia e a ÁREA vem em célula mesclada — só a
    primeira linha de cada bloco traz o nome, então ela é arrastada pra
    baixo. Sem isso, 58 das 63 peças ficariam sem área.
    """
    wb = openpyxl.load_workbook(str(caminho), data_only=True)
    if ABA_CLIENTE not in wb.sheetnames:
        wb.close()
        return []
    ws = wb[ABA_CLIENTE]
    itens, area_corrente = [], ""
    for linha in ws.iter_rows(min_row=3, values_only=True):
        area, nome = linha[1], linha[2]
        if area:
            area_corrente = str(area).strip()
        if not nome or not linha[8]:
            continue
        itens.append({
            "area": area_corrente,
            "nome": str(nome).strip(),
            "quantidade": linha[3],
            "largura": linha[4], "altura": linha[5],
            "material": str(linha[6]).strip() if linha[6] else "",
            "status": str(linha[8]).strip().upper(),
        })
    wb.close()
    return itens


# Palavras que não provam parentesco nenhum entre dois nomes: ligação,
# número solto, e nome de material (que aparece em quase toda peça).
_VAZIAS = {"DE", "DO", "DA", "DOS", "DAS", "E", "COM", "EM", "A", "O", "NO", "NA",
           "LONA", "ADESIVO", "VINIL", "PS", "PVC", "XPS", "MDF", "ACRILICO",
           "IMPRESSA", "IMPRESSO", "FOSCA", "FOSCO", "RECORTE", "UN"}


def _distintivas(nome):
    return {p for p in _normalizar(nome).split()
            if p not in _VAZIAS and not p.isdigit() and len(p) > 1}


def _parear(ficha, por_medida):
    """
    O item da planilha que é esta peça — ou None.

    Exige medida igual E parentesco de nome. O parentesco é por palavra
    DISTINTIVA em comum, não por palavra qualquer: a mesma peça é
    "TESTEIRA ARENA" no caderno e "TESTEIRA - LONA" na planilha — uma
    palavra só em comum, e é ela que identifica. Já o falso positivo que
    precisa ser barrado ("PAINEL DE FUNDO" contra "VISTA PAREDE DO
    DEPÓSITO", ambos 5,00 x 3,00, áreas diferentes) não tem nenhuma.
    Material e palavra de ligação não contam: aparecem em quase tudo.

    Sem par, a linha fica marcada — nunca inventada.
    """
    medida = _medida_par(ficha.get("medidas"))
    if not medida:
        return None
    alvo = _normalizar(ficha.get("nome"))
    distintivas = _distintivas(ficha.get("nome"))
    for item in por_medida.get(medida, []):
        outro = _normalizar(item["nome"])
        if alvo and outro and (alvo in outro or outro in alvo):
            return item
        if distintivas & _distintivas(item["nome"]):
            return item
    return None


def chaves_da_peca(caderno, ficha):
    """As DUAS âncoras de uma peça do caderno — ver docstring do módulo."""
    return ("%s|slide|%s" % (caderno, ficha.get("slide")),
            "%s|nome|%s" % (caderno, _normalizar(ficha.get("nome"))))


def chave_do_item(item):
    return "planilha|%s|%s" % (_normalizar(item["area"]), _normalizar(item["nome"]))


def ler_observacoes(caminho):
    """
    As observações escritas à mão na planilha anterior, indexadas por
    TODAS as âncoras da linha onde estavam.

    As âncoras moram numa coluna oculta ao lado das visíveis — é o que
    permite reencontrar a observação mesmo que o cliente renomeie a peça
    ou mova o slide. Arquivo inexistente, corrompido ou de outro formato
    devolve vazio: perder a observação é ruim, mas derrubar a geração
    inteira por causa dela é pior.
    """
    caminho = pathlib.Path(caminho)
    if not caminho.is_file():
        return []
    try:
        wb = openpyxl.load_workbook(str(caminho), data_only=True)
    except Exception:
        return []
    try:
        if ABA not in wb.sheetnames:
            return []
        ws = wb[ABA]
        coluna_obs = _CAMPOS.index("observacao")
        coluna_ancora = len(COLUNAS)          # 0-based: a primeira depois das visíveis
        guardadas = []
        for linha in ws.iter_rows(min_row=LINHA_CABECALHO + 1, values_only=True):
            if len(linha) <= coluna_ancora:
                continue
            observacao = linha[coluna_obs]
            ancoras = linha[coluna_ancora]
            if not observacao or not str(observacao).strip() or not ancoras:
                continue
            guardadas.append({
                "ancoras": [a.strip() for a in str(ancoras).split("||") if a.strip()],
                "texto": str(observacao).strip(),
            })
        return guardadas
    finally:
        wb.close()


def montar_linhas(fichas, itens, caderno, observacoes=None, baixados=None):
    """
    A união das duas fontes, com o par feito onde der.

    'observacoes' é a lista de registros devolvida por ler_observacoes:
    cada um traz TODAS as âncoras da linha onde estava. O registro é
    consumido inteiro quando qualquer uma das âncoras encontra a peça —
    senão a âncora do nome antigo, sobrando depois de um rename, viraria
    uma órfã fantasma.
    """
    observacoes = list(observacoes or [])
    baixados = baixados or {}
    por_ancora = {}
    for registro in observacoes:
        for ancora in registro["ancoras"]:
            por_ancora.setdefault(ancora, registro)
    usados = set()

    def _resgatar(*ancoras):
        for ancora in ancoras:
            registro = por_ancora.get(ancora)
            if registro is not None:
                usados.add(id(registro))
                return registro["texto"]
        return ""

    por_medida = {}
    for item in itens:
        try:
            chave = (round(float(item["largura"]), 2), round(float(item["altura"]), 2))
        except (TypeError, ValueError):
            continue
        por_medida.setdefault(chave, []).append(item)

    linhas, pareados = [], set()
    for ficha in fichas:
        par = _parear(ficha, por_medida)
        if par is not None:
            pareados.add(chave_do_item(par))

        chave_slide, chave_nome = chaves_da_peca(caderno, ficha)
        observacao = _resgatar(chave_slide, chave_nome)
        registro_baixa = baixados.get("%s|slide|%s" % (caderno, ficha.get("slide"))) or {}
        baixado_em = ""
        if registro_baixa.get("quando"):
            import datetime as _dt
            try:
                q = _dt.datetime.strptime(registro_baixa["quando"], "%Y-%m-%dT%H:%M:%S")
                baixado_em = q.strftime("%d/%m/%Y %H:%M")
            except ValueError:
                baixado_em = registro_baixa["quando"]

        if par is None:
            confere = MARCA_SO_CADERNO
        elif _normalizar(par["status"]) == _normalizar(ficha["situacao"]):
            confere = MARCA_CONFERE
        else:
            confere = MARCA_DIVERGENTE

        linhas.append({
            "origem": "caderno",
            "area": "%s (slide %s)" % (caderno, ficha.get("slide")),
            "peca": ficha.get("nome") or "",
            "material": ficha.get("material") or "",
            "quantidade": ficha.get("quantidade") or "",
            "medida": ficha.get("medidas") or "",
            "sangria": ficha.get("medidas_sangria") or "",
            "status_caderno": ficha.get("situacao") or "",
            "status_planilha": par["status"] if par else "",
            "confere": confere,
            "arquivo": registro_baixa.get("arquivo") or ficha.get("nome_arquivo") or (
                "— %s" % ficha["motivo_nome"] if ficha.get("motivo_nome") else ""),
            "baixado": baixado_em,
            "link": ficha["links"][0] if ficha.get("links") else "",
            "observacao": observacao,
            "_ancoras": [chave_slide, chave_nome],
        })

    for item in itens:
        chave = chave_do_item(item)
        if chave in pareados:
            continue
        observacao = _resgatar(chave)
        medida = ""
        if item["largura"] and item["altura"]:
            medida = "%s X %s" % (item["largura"], item["altura"])
        linhas.append({
            "origem": "planilha", "area": item["area"], "peca": item["nome"],
            "material": item["material"], "quantidade": item["quantidade"],
            "medida": medida, "sangria": "",
            "status_caderno": "", "status_planilha": item["status"],
            "confere": MARCA_SO_PLANILHA,
            "arquivo": "", "baixado": "", "link": "",
            "observacao": observacao, "_ancoras": [chave],
        })

    # Observação que perdeu as duas âncoras não se apaga: vai pro fim,
    # marcada, pra alguém decidir. É trabalho de gente.
    for registro in observacoes:
        if id(registro) in usados:
            continue
        linhas.append({
            "origem": "órfã", "area": "", "peca": "(a peça desta observação sumiu)",
            "material": "", "quantidade": "", "medida": "", "sangria": "",
            "status_caderno": "", "status_planilha": "", "confere": MARCA_ORFA,
            "arquivo": "", "baixado": "", "link": "",
            "observacao": registro["texto"], "_ancoras": list(registro["ancoras"]),
        })
    return linhas


def _fundo(linha):
    if linha["confere"] in (MARCA_DIVERGENTE, MARCA_ORFA):
        return _FUNDO_DIVERG
    if linha["confere"] in (MARCA_SO_CADERNO, MARCA_SO_PLANILHA):
        return _FUNDO_FALTA
    if linha["status_caderno"] == "APROVADO":
        return _FUNDO_OK
    return None


def escrever(destino, linhas, titulo, agora=None):
    """Grava a planilha. A âncora de cada linha vai num comentário na
    primeira célula, que é como a observação se reencontra na próxima."""
    agora = agora or datetime.datetime.now()
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = ABA

    fino = Side(style="thin", color="DCE0E7")
    borda = Border(left=fino, right=fino, top=fino, bottom=fino)

    ws["A1"] = titulo
    ws["A1"].font = Font(size=14, bold=True, color=_TINTA)
    ws["A2"] = "Cruzamento do caderno com a planilha do cliente · gerado em %s" % (
        agora.strftime("%d/%m/%Y %H:%M"))
    ws["A2"].font = Font(size=9, color="5C6675")
    ws["A3"] = ("%d peças · %d só no caderno · %d só na planilha · %d divergentes · "
                "%d aprovadas" % (
                    len(linhas),
                    sum(1 for l in linhas if l["confere"] == MARCA_SO_CADERNO),
                    sum(1 for l in linhas if l["confere"] == MARCA_SO_PLANILHA),
                    sum(1 for l in linhas if l["confere"] == MARCA_DIVERGENTE),
                    sum(1 for l in linhas if l["status_caderno"] == "APROVADO")))
    ws["A3"].font = Font(size=10, bold=True, color="8A5300")

    for i, (rotulo, largura) in enumerate(COLUNAS, start=1):
        c = ws.cell(row=LINHA_CABECALHO, column=i, value=rotulo)
        c.font = Font(bold=True, color="FFFFFF", size=9)
        c.fill = PatternFill("solid", fgColor=_CAB)
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        c.border = borda
        ws.column_dimensions[get_column_letter(i)].width = largura
    ws.row_dimensions[LINHA_CABECALHO].height = 28

    for r, linha in enumerate(linhas, start=LINHA_CABECALHO + 1):
        cor = _fundo(linha)
        for i, campo in enumerate(_CAMPOS, start=1):
            c = ws.cell(row=r, column=i, value=linha[campo])
            c.font = Font(size=9, color=_TINTA)
            c.alignment = Alignment(vertical="center",
                                    wrap_text=campo in ("peca", "arquivo", "observacao"))
            c.border = borda
            if cor:
                c.fill = PatternFill("solid", fgColor=cor)
        if linha["link"]:
            c = ws.cell(row=r, column=_CAMPOS.index("link") + 1)
            c.hyperlink = linha["link"]
            c.font = Font(size=9, color="0B6B8A", underline="single")
        # As âncoras da linha, pra observação se reencontrar na próxima
        # geração. Coluna oculta: é maquinário, não informação de tela.
        ws.cell(row=r, column=len(COLUNAS) + 1,
                value="||".join(linha.get("_ancoras") or []))

    ws.column_dimensions[get_column_letter(len(COLUNAS) + 1)].hidden = True

    ws.freeze_panes = ws.cell(row=LINHA_CABECALHO + 1, column=1)
    ws.auto_filter.ref = "A%d:%s%d" % (
        LINHA_CABECALHO, get_column_letter(len(COLUNAS)), LINHA_CABECALHO + len(linhas))

    destino = pathlib.Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(destino))
    return destino


def gerar(destino, caminho_caderno, caminho_planilha=None, titulo=None, config=None):
    """
    Refaz a planilha de controle a partir do caderno (e da planilha do
    cliente, quando houver), preservando as observações da anterior.
    """
    destino = pathlib.Path(destino)
    caderno = pathlib.Path(caminho_caderno).stem
    fichas = caderno_arte.fichas_com_nome(caminho_caderno, config)
    itens = ler_planilha_do_cliente(caminho_planilha) if caminho_planilha else []

    import arte_recebida
    baixados = arte_recebida.ler_baixados(destino.parent)
    linhas = montar_linhas(fichas, itens, caderno, ler_observacoes(destino), baixados)
    return escrever(destino, linhas, titulo or "CONTROLE DE ARTES — %s" % caderno)
