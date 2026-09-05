"""
Relatório diário de produção do RIP: o que passou por cada máquina num
dia, em PDF, a partir do registro permanente que o vigia da hot folder
grava (rasterlink_hotfolder.registrar_envio).

Por que existe (pedido do usuário, 2026-09-05): o arquivo enviado só
fica guardado 15 dias em "Enviados", mas a comprovação do que foi
produzido precisa durar. Na instalação — às vezes em outro estado —
aparece a conversa de "vocês não imprimiram tanto material"; este
documento é a resposta, com data, hora, máquina e metragem de cada
arquivo entregue à impressão.

O registro guarda só fato bruto (quando/máquina/arquivo/tamanho/girado)
porque quem escreve é a máquina do RIP, que não tem o projeto inteiro
instalado. É AQUI que o nome do arquivo vira quantidade, material,
medida e m², usando exatamente o mesmo parser do resto do sistema
(dimensoes.py + config.json) — se um dia a leitura de nome melhorar, o
relatório de qualquer dia passado melhora junto, porque é gerado na
hora a partir do registro.

Duas conferências que o documento faz sozinho:
  - ARQUIVO REPETIDO no mesmo dia: conta normalmente no subtotal
    (refação por dano na instalação, ou arte corrigida salva por cima
    do mesmo nome, consomem material de verdade — regra do usuário,
    2026-09-05), mas fica sinalizado pra conferência.
  - ARQUIVO QUE NÃO CABE na largura útil da máquina pra onde foi:
    sinal de que provavelmente foi pra fila errada.
"""
import datetime
import json
import pathlib

import pymupdf

from branding import CAMINHO_LOGO_GUI, inserir_logo
from config import carregar_config
from dimensoes import extrair_dimensoes, extrair_quantidade, identificar_categoria
from rasterlink_hotfolder import MAQUINAS, NOME_SUBPASTA_REGISTRO, PASTA_RELATORIOS, _config_maquina

LARGURA_PAGINA = 595.27  # A4
ALTURA_PAGINA = 841.89
MARGEM = 40

_COR_TEXTO = "#12161d"
_COR_SUAVE = "#5c6675"
_COR_FRACA = "#8a93a1"
_COR_ACENTO = "#0b6b8a"
_COR_AVISO = "#8a5300"
_FUNDO_AVISO = "#fdf2e0"
_FUNDO_REPETIDO = "#e4f0f5"

# Usa o logo JÁ reduzido que o projeto tem pra tela (230px), não o de
# alta resolução: o grande tem 347KB e é embutido em todo PDF, o que
# aqui aparece em ~92x26pt (≈180dpi com o reduzido, de sobra pra
# impressão). Guardar um ano de relatórios na pasta — condição do
# usuário, 2026-09-05 — depende de o documento ficar leve.


def caminho_registro(data, pasta_relatorios=None):
    """Arquivo de registro do mês a que 'data' pertence."""
    pasta = pathlib.Path(pasta_relatorios or PASTA_RELATORIOS) / NOME_SUBPASTA_REGISTRO
    return pasta / f"{data:%Y-%m}.jsonl"


def ler_registros_do_dia(data, pasta_relatorios=None):
    """
    Lê o registro do mês e devolve, em ordem de horário, só os envios do
    dia pedido. Linha corrompida (escrita cortada no meio por queda de
    energia, por exemplo) é pulada sem derrubar o relatório inteiro.
    """
    if isinstance(data, datetime.datetime):
        data = data.date()

    caminho = caminho_registro(data, pasta_relatorios)
    if not caminho.is_file():
        return []

    registros = []
    with open(caminho, "r", encoding="utf-8") as f:
        for linha in f:
            linha = linha.strip()
            if not linha:
                continue
            try:
                dados = json.loads(linha)
                quando = datetime.datetime.strptime(dados["quando"], "%Y-%m-%dT%H:%M:%S")
            except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                continue
            if quando.date() != data:
                continue
            dados["_quando"] = quando
            registros.append(dados)

    registros.sort(key=lambda d: d["_quando"])
    return registros


def _largura_util(nome_maquina, maquinas=None):
    maquinas = MAQUINAS if maquinas is None else maquinas
    if nome_maquina not in maquinas:
        return None
    return _config_maquina(maquinas[nome_maquina])[1]


def interpretar(registros, config=None, maquinas=None):
    """
    Transforma os registros brutos em linhas de relatório: lê do nome do
    arquivo a quantidade, o material, a medida e o m², e marca as duas
    conferências (repetido no dia / não cabe na máquina).

    Devolve {nome_maquina: [linha, ...]} preservando a ordem de horário.
    """
    config = config or carregar_config()
    materiais = config["materiais"]
    typos = config.get("typos_unidade", {})
    sinonimos = config.get("sinonimos_categoria")

    vistos = {}
    por_maquina = {}
    for registro in registros:
        nome = registro["arquivo"]
        quantidade = extrair_quantidade(nome)[0]
        dimensao = extrair_dimensoes(nome, typos)
        categoria = identificar_categoria(nome.upper(), materiais, sinonimos)[0]

        vistos[nome] = vistos.get(nome, 0) + 1
        repeticao = vistos[nome]

        area_m2 = dimensao["area_m2"] * quantidade if dimensao else None
        largura_util = _largura_util(registro["maquina"], maquinas)
        nao_cabe = False
        if dimensao and largura_util:
            menor_lado = min(dimensao["largura_m"], dimensao["altura_m"])
            nao_cabe = menor_lado > largura_util + 0.001

        por_maquina.setdefault(registro["maquina"], []).append({
            "quando": registro["_quando"],
            "arquivo": nome,
            "quantidade": quantidade,
            "categoria": categoria,
            "dimensao": dimensao,
            "area_m2": area_m2,
            "bytes": registro.get("bytes"),
            "girado": registro.get("girado", False),
            "repeticao": repeticao,
            "nao_cabe": nao_cabe,
            "largura_util": largura_util,
        })
    return por_maquina


def subtotais_por_material(linhas):
    """
    m² somado por material. NUNCA devolve um total juntando materiais
    diferentes — cada material tem custo e máquina próprios, somar tudo
    num número só não significa nada (regra do projeto).

    Soma o valor JÁ ARREDONDADO de cada linha, não o valor cheio: este
    documento serve de comprovação, e quem confere soma a coluna que
    está vendo. Somando o valor cheio, três linhas de 26,80 fechariam
    em 66,79 no rodapé — parece erro de conta e destrói a confiança no
    documento inteiro.
    """
    totais = {}
    for linha in linhas:
        if linha["area_m2"] is None or not linha["categoria"]:
            continue
        totais[linha["categoria"]] = totais.get(linha["categoria"], 0.0) + round(linha["area_m2"], 2)
    return totais


def _num(valor, casas=2):
    return f"{valor:,.{casas}f}".replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def _tamanho_legivel(bytes_):
    if not bytes_:
        return "—"
    if bytes_ >= 1024 ** 3:
        return f"{bytes_ / 1024 ** 3:.1f} GB".replace(".", ",")
    return f"{bytes_ / 1024 ** 2:.0f} MB"


class _Folha:
    """
    Monta o PDF acumulando os blocos de HTML de uma página inteira e
    gravando TUDO numa chamada só de insert_htmlbox quando a página
    fecha.

    O acúmulo não é capricho: cada insert_htmlbox embute um subconjunto
    de fonte próprio, e como cada caixa usa glifos diferentes, o
    save(garbage=4) não tem subconjuntos idênticos pra juntar. Uma caixa
    por linha dava ~400KB num dia de 30 envios (≈100MB/ano); uma caixa
    por página derruba isso pra alguns KB, que é o que viabiliza guardar
    o ano inteiro na pasta (condição do usuário, 2026-09-05).

    Guarda o ÍNDICE da página, nunca o objeto Page — um Page fica
    obsoleto assim que outra página é criada no mesmo documento (ver
    [[reference-pymupdf-gotchas]]).
    """

    LIMITE_Y = ALTURA_PAGINA - MARGEM - 20

    def __init__(self, data):
        self.doc = pymupdf.open()
        self.data = data
        self.indice = -1
        self.y = 0
        self.buffer = []
        self._nova_pagina()

    @property
    def pagina(self):
        return self.doc[self.indice]

    def _nova_pagina(self):
        self._descarregar()
        self.doc.new_page(width=LARGURA_PAGINA, height=ALTURA_PAGINA)
        self.indice = len(self.doc) - 1
        self.y = MARGEM
        self._cabecalho()

    def _descarregar(self):
        """Grava numa tacada só tudo que foi acumulado pra página atual."""
        if not self.buffer or self.indice < 0:
            self.buffer = []
            return
        html = f'<div style="font-family:sans-serif">{"".join(self.buffer)}</div>'
        self.pagina.insert_htmlbox(
            pymupdf.Rect(MARGEM, self.inicio_corpo, LARGURA_PAGINA - MARGEM, self.LIMITE_Y), html,
        )
        self.buffer = []

    def bloco(self, altura, html):
        """Acumula um bloco, virando a página se ele não couber mais."""
        if self.y + altura > self.LIMITE_Y:
            self._nova_pagina()
        self.buffer.append(html)
        self.y += altura

    def _cabecalho(self):
        pagina = self.pagina
        try:
            caminho = CAMINHO_LOGO_GUI if CAMINHO_LOGO_GUI.is_file() else None
            inserir_logo(pagina, pymupdf.Rect(MARGEM, MARGEM, MARGEM + 92, MARGEM + 26), caminho=caminho)
        except Exception:
            pass
        pagina.insert_htmlbox(
            pymupdf.Rect(LARGURA_PAGINA / 2, MARGEM - 4, LARGURA_PAGINA - MARGEM, MARGEM + 34),
            f'<div style="text-align:right;font-family:sans-serif">'
            f'<div style="font-size:13pt;font-weight:700;color:{_COR_TEXTO}">Relatório Diário de Produção</div>'
            f'<div style="font-size:9pt;color:{_COR_SUAVE};margin-top:2px">{self.data:%d/%m/%Y}</div>'
            f'</div>',
        )
        self.y = MARGEM + 42
        pagina.draw_line(
            pymupdf.Point(MARGEM, MARGEM + 38), pymupdf.Point(LARGURA_PAGINA - MARGEM, MARGEM + 38),
            color=_hex_para_rgb(_COR_TEXTO), width=1.2,
        )
        self.inicio_corpo = self.y

    def salvar(self, caminho):
        self._descarregar()
        self.doc.save(str(caminho), garbage=4, deflate=True)
        self.doc.close()


def _hex_para_rgb(cor):
    cor = cor.lstrip("#")
    return tuple(int(cor[i:i + 2], 16) / 255 for i in (0, 2, 4))


def gerar_pdf(data, pasta_relatorios=None, config=None, maquinas=None, caminho_saida=None):
    """
    Gera o PDF do dia e devolve o caminho — ou None se nada passou pelas
    máquinas nesse dia (não faz sentido emitir comprovação em branco).

    Os PDFs ficam agrupados por ano (Relatório de Impressão Diária/2026/
    2026-09-05.pdf): nome em AAAA-MM-DD pra ordenar sozinho no Explorer,
    e um ano inteiro cabe folgado numa pasta só (pedido do usuário,
    2026-09-05 — cada PDF tem algumas dezenas de KB).
    """
    if isinstance(data, datetime.datetime):
        data = data.date()

    registros = ler_registros_do_dia(data, pasta_relatorios)
    if not registros:
        return None

    por_maquina = interpretar(registros, config, maquinas)
    folha = _Folha(data)

    total_arquivos = sum(len(linhas) for linhas in por_maquina.values())
    geral = {}
    for linhas in por_maquina.values():
        for material, m2 in subtotais_por_material(linhas).items():
            geral[material] = geral.get(material, 0.0) + m2
    resumo_materiais = " · ".join(f"{mat} {_num(m2)} m²" for mat, m2 in sorted(geral.items())) or "sem medida lida"

    folha.bloco(
        26,
        f'<div style="font-size:9pt;color:{_COR_SUAVE};padding-bottom:8px">'
        f'<b style="color:{_COR_TEXTO}">{total_arquivos}</b> arquivo(s) &nbsp;·&nbsp; '
        f'<b style="color:{_COR_TEXTO}">{len(por_maquina)}</b> máquina(s) &nbsp;·&nbsp; {resumo_materiais}'
        f'</div>',
    )

    for nome_maquina in sorted(por_maquina):
        linhas = por_maquina[nome_maquina]
        largura_util = linhas[0]["largura_util"]
        spec = f"largura útil {_num(largura_util)} m" if largura_util else "largura útil não configurada"

        folha.bloco(
            26,
            f'<div style="font-size:10pt;font-weight:700;color:{_COR_TEXTO};'
            f'border-bottom:1px solid #b9c0cb;padding:6px 0 3px">{_escapar(nome_maquina.upper())}'
            f'<span style="font-weight:400;font-size:8pt;color:{_COR_SUAVE}"> — {spec}</span></div>',
        )

        for linha in linhas:
            avisos = []
            if linha["repeticao"] > 1:
                avisos.append((
                    _COR_ACENTO,
                    f"{linha['repeticao']}ª entrada deste mesmo nome no dia — conta no subtotal "
                    f"(refação e arte corrigida consomem material igual). Confira o motivo.",
                ))
            if linha["nao_cabe"]:
                avisos.append((
                    _COR_AVISO,
                    f"Não cabe nesta máquina: menor lado maior que {_num(linha['largura_util'])} m "
                    f"de largura útil. Conferir se o destino certo não era outra máquina.",
                ))
            if linha["girado"]:
                avisos.append((_COR_SUAVE, "Girado 90° automaticamente para aproveitar melhor a bobina."))

            dim = linha["dimensao"]
            medida = f'{_num(dim["largura_m"])} × {_num(dim["altura_m"])} m' if dim else "medida não lida"
            area = f'{_num(linha["area_m2"])} m²' if linha["area_m2"] is not None else "—"

            if linha["nao_cabe"]:
                fundo = f"background:{_FUNDO_AVISO};"
            elif linha["repeticao"] > 1:
                fundo = f"background:{_FUNDO_REPETIDO};"
            else:
                fundo = ""

            corpo = (
                f'<div style="{fundo}border-bottom:0.5px solid #dce0e7;padding:4px 3px;font-size:8pt;color:{_COR_TEXTO}">'
                f'<span style="color:{_COR_SUAVE}">{linha["quando"]:%H:%M}</span> &nbsp; '
                f'<b>{linha["quantidade"]}un</b> &nbsp; '
                f'<span style="color:{_COR_SUAVE}">{_escapar(linha["categoria"] or "material não identificado")}</span> &nbsp; '
                f'{medida} &nbsp; <b>{area}</b> &nbsp; '
                f'<span style="color:{_COR_FRACA}">{_tamanho_legivel(linha["bytes"])}</span>'
                f'<div style="font-size:7pt;color:{_COR_SUAVE};padding-top:1px">{_escapar(linha["arquivo"])}</div>'
            )
            for cor, texto in avisos:
                corpo += f'<div style="font-size:7pt;color:{cor};padding-top:1px">{texto}</div>'
            corpo += "</div>"

            folha.bloco(30 + 11 * len(avisos), corpo)

        subtotais = subtotais_por_material(linhas)
        if subtotais:
            repetidos = sum(1 for l in linhas if l["repeticao"] > 1)
            obs = f' <span style="color:{_COR_ACENTO}">(inclui {repetidos} repetição)</span>' if repetidos else ""
            texto = " &nbsp;·&nbsp; ".join(f"{_escapar(mat)} <b>{_num(m2)} m²</b>" for mat, m2 in sorted(subtotais.items()))
            folha.bloco(
                24,
                f'<div style="font-size:8.5pt;text-align:right;color:{_COR_TEXTO};padding:5px 3px 12px">'
                f'Subtotal: {texto}{obs}</div>',
            )

    folha.bloco(
        50,
        f'<div style="font-size:7pt;color:{_COR_SUAVE};line-height:1.45;'
        f'border-top:0.5px solid #dce0e7;padding-top:6px;margin-top:6px">'
        f'Este documento registra os arquivos <b>entregues à fila de impressão</b> de cada máquina na data acima, '
        f'com hora de entrada registrada automaticamente pelo sistema. Um mesmo arquivo enviado mais de uma vez '
        f'<b>conta em cada envio</b> — refação e arte corrigida consomem material igual. Quantidades e medidas são '
        f'lidas do nome do arquivo.<br>'
        f'Gerado em {datetime.datetime.now():%d/%m/%Y %H:%M} · arquivo original guardado por 15 dias.'
        f'</div>',
    )

    if caminho_saida is None:
        pasta = pathlib.Path(pasta_relatorios or PASTA_RELATORIOS) / f"{data:%Y}"
        pasta.mkdir(parents=True, exist_ok=True)
        caminho_saida = pasta / f"{data:%Y-%m-%d}.pdf"
    else:
        caminho_saida = pathlib.Path(caminho_saida)
        caminho_saida.parent.mkdir(parents=True, exist_ok=True)

    folha.salvar(caminho_saida)
    return caminho_saida


def _escapar(texto):
    return texto.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def dias_com_registro(ano_mes, pasta_relatorios=None):
    """Lista as datas que têm envio registrado no mês (pra oferecer na tela)."""
    caminho = caminho_registro(ano_mes, pasta_relatorios)
    if not caminho.is_file():
        return []
    dias = set()
    with open(caminho, "r", encoding="utf-8") as f:
        for linha in f:
            try:
                quando = json.loads(linha)["quando"]
                dias.add(datetime.datetime.strptime(quando, "%Y-%m-%dT%H:%M:%S").date())
            except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                continue
    return sorted(dias)
