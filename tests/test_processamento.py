import copy
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import pymupdf

from config import CONFIG_PADRAO
from processamento import _eh_reposicao, _nome_padronizado, _obter_pdf_reduzido, processar_etiquetas


def _pdf_de_uma_pagina(caminho):
    doc = pymupdf.open()
    doc.new_page(width=200, height=200)
    doc.save(str(caminho))
    doc.close()


def _pdf_com_desenho(caminho, largura_pt, altura_pt):
    """PDF de 1 página cujo conteúdo (não só a página) tem o tamanho exato pedido — pra testar medição pela arte."""
    doc = pymupdf.open()
    pagina = doc.new_page(width=largura_pt, height=altura_pt)
    pagina.draw_rect(pymupdf.Rect(0, 0, largura_pt, altura_pt), color=(0, 0, 0), fill=(0, 0, 0))
    doc.save(str(caminho))
    doc.close()


def _imagem_de_uma_pagina(caminho):
    """PNG/JPG real (não um PDF com extensão trocada) — o PyMuPDF abre imagem crua como documento de 1 página."""
    doc = pymupdf.open()
    pagina = doc.new_page(width=200, height=200)
    pagina.draw_rect(pymupdf.Rect(0, 0, 200, 200), fill=(0, 0, 0))
    pix = pagina.get_pixmap()
    pix.save(str(caminho))
    doc.close()


def test_eh_reposicao_reconhece_variacoes_de_acento():
    nomes = [
        "1UN LONA 2,00X1,00 - REPOSIÇÃO.PDF",
        "1UN LONA 2,00X1,00 - REPOSICAO.PDF",
        "1UN LONA 2,00X1,00 - REPOSIÇAO.PDF",
        "1UN LONA 2,00X1,00 - REFAÇÃO.PDF",
        "1UN LONA 2,00X1,00 - REFACAO.PDF",
        "1UN LONA 2,00X1,00 - REFAÇAO.PDF",
        "1UN LONA 2,00X1,00 - REF.PDF",
    ]
    for nome in nomes:
        assert _eh_reposicao(nome), f"deveria reconhecer: {nome}"


def test_eh_reposicao_arquivo_normal_nao_e_marcado():
    assert not _eh_reposicao("1UN LONA 2,00X1,00.PDF")


def test_eh_reposicao_ref_nao_casa_dentro_de_outra_palavra():
    assert not _eh_reposicao("1UN LONA REFORCO 2,00X1,00.PDF")


def test_segunda_rodada_mantem_itens_da_primeira_na_os(tmp_path):
    """
    Regressão direta do bug real de produção (2026-08-26): a OS de uma
    rodada de atualização precisa mostrar os itens da rodada ANTERIOR
    junto com os novos, não só os novos. Roda processar_etiquetas duas
    vezes de ponta a ponta (não só unidades isoladas) contra o mesmo
    pedido — cada rodada com uma pasta de entrada e categoria
    diferente — e confere que a OS final (texto renderizado do PDF)
    contém as DUAS categorias, com a área de cada uma correta.
    """
    config = copy.deepcopy(CONFIG_PADRAO)
    pasta_saida_base = tmp_path / "saida"

    entrada1 = tmp_path / "entrada1"
    entrada1.mkdir()
    _pdf_de_uma_pagina(entrada1 / "1UN LONA 2,00X1,00M_arte.pdf")

    resultado1 = processar_etiquetas(
        str(entrada1), "CLIENTE TESTE", "Gerente", "Produtor",
        config, pasta_saida_base=str(pasta_saida_base),
    )
    assert resultado1 is not None
    pasta_saida = resultado1["pasta_saida"]

    entrada2 = tmp_path / "entrada2"
    entrada2.mkdir()
    _pdf_de_uma_pagina(entrada2 / "1UN PVC BRANCO 1,00X1,00M_arte2.pdf")

    resultado2 = processar_etiquetas(
        str(entrada2), "CLIENTE TESTE", "Gerente", "Produtor",
        config, pasta_saida_base=str(pasta_saida_base), pasta_saida_existente=pasta_saida,
    )
    assert resultado2 is not None
    assert resultado2["arquivos_novos"] == 1

    doc = pymupdf.open(resultado2["os"])
    texto = "".join(p.get_text() for p in doc)
    doc.close()

    assert "LONA" in texto, "item da PRIMEIRA rodada sumiu da OS depois da segunda rodada"
    assert "PVC" in texto
    assert "2.00 m" in texto  # área da LONA (2,00 x 1,00m)
    assert "1.00 m" in texto  # área do PVC (1,00 x 1,00m)
    assert "2 itens no total" in texto


def test_rodadas_seguintes_acrescentam_no_mesmo_checklist(tmp_path):
    """
    Decisão do usuário (2026-09-02): o checklist virou um documento só
    por pedido, como a OS — cada rodada nova ACRESCENTA página nele em
    vez de gerar um arquivo "V2"/"V3" à parte (era assim antes,
    2026-08-26, quando cada rodada virava um checklist separado pra
    nunca reabrir uma folha já impressa/marcada à caneta). As páginas
    antigas nunca são renumeradas de novo — só o texto "Página X de Y"
    de quando foram criadas fica desatualizado, que é o preço aceito
    pra nunca desenhar em cima de uma página que já pode estar impressa
    (ver numerar_paginas_a_partir_de). Roda 3 rodadas reais e confere
    que sobra um arquivo só, com uma seção de TOC por rodada e o selo
    (NOVO/REPOSIÇÃO) certo em cada página.
    """
    config = copy.deepcopy(CONFIG_PADRAO)
    pasta_saida_base = tmp_path / "saida"

    entrada1 = tmp_path / "entrada1"
    entrada1.mkdir()
    _pdf_de_uma_pagina(entrada1 / "1UN LONA 2,00X1,00M_a.pdf")
    resultado1 = processar_etiquetas(
        str(entrada1), "CLIENTE TESTE", "Gerente", "Produtor",
        config, pasta_saida_base=str(pasta_saida_base),
    )
    pasta_saida = pathlib.Path(resultado1["pasta_saida"])

    entrada2 = tmp_path / "entrada2"
    entrada2.mkdir()
    _pdf_de_uma_pagina(entrada2 / "1UN LONA 3,00X1,00M_b.pdf")
    processar_etiquetas(
        str(entrada2), "CLIENTE TESTE", "Gerente", "Produtor",
        config, pasta_saida_base=str(pasta_saida_base), pasta_saida_existente=pasta_saida,
    )

    entrada3 = tmp_path / "entrada3"
    entrada3.mkdir()
    _pdf_de_uma_pagina(entrada3 / "1UN LONA 4,00X1,00M_c - REPOSICAO.pdf")
    processar_etiquetas(
        str(entrada3), "CLIENTE TESTE", "Gerente", "Produtor",
        config, pasta_saida_base=str(pasta_saida_base), pasta_saida_existente=pasta_saida,
    )

    nomes_checklist = sorted(p.name for p in pasta_saida.glob("Checklist *.pdf"))
    assert nomes_checklist == ["Checklist CLIENTE TESTE.pdf"], "tem que sobrar um arquivo só, nunca V2/V3"

    doc = pymupdf.open(str(pasta_saida / "Checklist CLIENTE TESTE.pdf"))
    assert len(doc) == 3, "1 etiqueta por rodada (banner+etiqueta na mesma página) = 3 páginas no total"
    toc = doc.get_toc()
    assert len(toc) == 3, "uma seção de TOC por rodada, mesmo repetindo a categoria LONA"
    textos = [p.get_text() for p in doc]
    doc.close()

    assert "NOVO" not in textos[0] and "REPOSIÇÃO" not in textos[0], "primeira rodada não leva selo"
    assert "NOVO" in textos[1], "segunda rodada (material novo) precisa do selo NOVO"
    assert "REPOSIÇÃO" in textos[2], "terceira rodada (nome com REPOSICAO) precisa do selo REPOSIÇÃO"


def test_cliente_digitado_com_espaco_diferente_nao_fragmenta_os_nem_checklist(tmp_path):
    """
    Regressão de bug real de produção (2026-08-28, SUPERBET): cliente
    digitado "SUPERBET" numa rodada e "SUPER BET" (com espaço) na
    seguinte, atualizando o MESMO pedido — antes desse fix, OS e
    checklist usavam o nome como foi digitado NAQUELA rodada, então a
    segunda rodada gerava "OS - SUPER BET.pdf" e "Checklist SUPER BET -
    ..." SEPARADOS dos arquivos "OS - SUPERBET.pdf"/"Checklist SUPERBET
    - ..." da primeira — a OS deixava de ser um documento só, cada
    arquivo só com metade do pedido. Precisa sempre usar o nome já
    fixado no nome da pasta, não o que foi digitado de novo.
    """
    config = copy.deepcopy(CONFIG_PADRAO)
    pasta_saida_base = tmp_path / "saida"

    entrada1 = tmp_path / "entrada1"
    entrada1.mkdir()
    _pdf_de_uma_pagina(entrada1 / "1UN LONA 2,00X1,00M_a.pdf")
    resultado1 = processar_etiquetas(
        str(entrada1), "SUPERBET", "Gerente", "Produtor",
        config, pasta_saida_base=str(pasta_saida_base),
    )
    pasta_saida = pathlib.Path(resultado1["pasta_saida"])
    assert (pasta_saida / "OS - SUPERBET.pdf").exists()

    entrada2 = tmp_path / "entrada2"
    entrada2.mkdir()
    _pdf_de_uma_pagina(entrada2 / "1UN LONA 3,00X1,00M_b.pdf")
    resultado2 = processar_etiquetas(
        str(entrada2), "SUPER BET", "Gerente", "Produtor",
        config, pasta_saida_base=str(pasta_saida_base), pasta_saida_existente=pasta_saida,
    )

    # continua sendo o MESMO arquivo de OS de sempre, atualizado — nunca
    # um "OS - SUPER BET.pdf" separado
    assert resultado2["os"] == str(pasta_saida / "OS - SUPERBET.pdf")
    assert not (pasta_saida / "OS - SUPER BET.pdf").exists()

    doc = pymupdf.open(resultado2["os"])
    texto = "".join(p.get_text() for p in doc)
    doc.close()
    assert "2 itens no total" in texto, "OS devia ter os itens das DUAS rodadas, não só a última"

    nomes_checklist = sorted(p.name for p in pasta_saida.glob("Checklist *.pdf"))
    assert nomes_checklist == ["Checklist SUPERBET.pdf"], "checklist também é um arquivo só por pedido, como a OS"

    doc_checklist = pymupdf.open(str(pasta_saida / "Checklist SUPERBET.pdf"))
    assert len(doc_checklist) == 2, "as etiquetas das DUAS rodadas, acrescentadas no mesmo arquivo"
    doc_checklist.close()


def test_log_processamento_fica_dentro_da_subpasta_log(tmp_path):
    """Decisão do usuário (2026-08-26): log_processamento_*.csv não fica solto na pasta do pedido, deixa cheio."""
    config = copy.deepcopy(CONFIG_PADRAO)
    pasta_saida_base = tmp_path / "saida"
    entrada = tmp_path / "entrada"
    entrada.mkdir()
    _pdf_de_uma_pagina(entrada / "1UN LONA 2,00X1,00M_a.pdf")

    resultado = processar_etiquetas(
        str(entrada), "CLIENTE TESTE", "Gerente", "Produtor",
        config, pasta_saida_base=str(pasta_saida_base),
    )

    pasta_saida = pathlib.Path(resultado["pasta_saida"])
    assert not list(pasta_saida.glob("log_processamento_*.csv")), "log não deveria ficar solto na pasta"
    assert list(pasta_saida.glob("_log/log_processamento_*.csv")), "log deveria estar dentro de _log"


def test_subtotal_da_os_multiplica_area_pela_quantidade(tmp_path):
    """
    Regressão de bug real (achado pelo usuário, 2026-08-29): 'dimensao'
    é a medida de UMA peça — um arquivo "4UN LONA 1,00X2,00M..." (4
    peças de 2m² cada) tinha que somar 8,00 m² no subtotal da OS, mas
    o total antes ficava sempre em 2,00 m² (como se fosse 1 peça só),
    porque a quantidade nunca entrava na conta de área/desperdício.
    """
    config = copy.deepcopy(CONFIG_PADRAO)
    pasta_saida_base = tmp_path / "saida"
    entrada = tmp_path / "entrada"
    entrada.mkdir()
    _pdf_de_uma_pagina(entrada / "4UN LONA 1,00X2,00M_a.pdf")

    resultado = processar_etiquetas(
        str(entrada), "CLIENTE TESTE", "Gerente", "Produtor",
        config, pasta_saida_base=str(pasta_saida_base),
    )

    doc = pymupdf.open(resultado["os"])
    texto = "".join(p.get_text() for p in doc)
    doc.close()

    assert "8.00 m²" in texto, "subtotal da OS devia refletir as 4 peças (4 x 2,00m² = 8,00m²)"


def test_nome_padronizado_nao_repete_material_nem_empilha_marca_da_arte():
    """
    Regressão de bug real (achado pelo usuário, 2026-08-29): reprocessar
    um arquivo que já tinha passado pela padronização (ex: pasta de
    entrada rodada de novo) empilhava um prefixo novo em cima do
    anterior — "1 UN LONA 8.70x1.30M UCB_CWB LONA (medida pela arte)
    LONA IMPRESSA (3).pdf", com o material repetido e a marca de uma
    rodada anterior sobrando. O material não pode repetir no nome, e
    reprocessar um arquivo já padronizado tem que dar um resultado
    limpo, sem empilhar.
    """
    nome_ja_padronizado = "1 UN LONA 8.70x1.30M (medida pela arte) LONA IMPRESSA (3).pdf"
    dimensao = {
        "largura_m": 8.7, "altura_m": 1.3, "area_m2": 11.31, "unidade_usada": "M",
        "medida_bruta": "8.70X1.30M", "unidade_corrigida": False, "unidade_bruta": "M", "origem": "nome",
    }
    resultado = _nome_padronizado(nome_ja_padronizado, 1, "LONA", dimensao, {}, "UCB_CWB")

    assert resultado == "1 UN LONA 8.70x1.30M UCB_CWB IMPRESSA (3).pdf"
    assert resultado.upper().count("LONA") == 1
    assert "(medida pela arte)" not in resultado


def test_material_composto_ps_e_acrilico_adesivado_somam_no_adesivo(tmp_path):
    """
    Regra do usuário (2026-08-29): "PS ADESIVADO"/"ACRÍLICO ADESIVADO"
    são UMA peça física que consome DOIS materiais — o mesmo tamanho
    conta pro subtotal de PS/ACRÍLICO E de ADESIVO na OS, mas só gera
    UMA etiqueta/entrada no checklist cada (nunca duplica a peça
    impressa). ADESIVO acumula as duas peças (PS + ACRÍLICO), mesmo
    sem ter etiqueta própria nenhuma.
    """
    config = copy.deepcopy(CONFIG_PADRAO)
    pasta_saida_base = tmp_path / "saida"
    entrada = tmp_path / "entrada"
    entrada.mkdir()
    _pdf_de_uma_pagina(entrada / "1UN PS ADESIVADO 1,00X2,00M_a.pdf")
    _pdf_de_uma_pagina(entrada / "1UN ACRILICO ADESIVADO 1,00X1,00M_b.pdf")

    resultado = processar_etiquetas(
        str(entrada), "CLIENTE TESTE", "Gerente", "Produtor",
        config, pasta_saida_base=str(pasta_saida_base),
    )

    doc = pymupdf.open(resultado["os"])
    texto = "".join(p.get_text() for p in doc)
    doc.close()

    assert "PS · 1 item" in texto
    assert "ACRILICO · 1 item" in texto
    # ADESIVO acumula as duas peças (2,00 + 1,00 = 3,00 m²), sem
    # nenhuma etiqueta própria
    assert "ADESIVO · 2 items" in texto
    assert "3.00 m²" in texto

    # cada peça continua com UMA etiqueta só (PS e ACRÍLICO separados,
    # nada com ADESIVO no checklist)
    pasta_saida = pathlib.Path(resultado["pasta_saida"])
    doc_checklist = pymupdf.open(str(pasta_saida / "Checklist CLIENTE TESTE.pdf"))
    toc = doc_checklist.get_toc()
    doc_checklist.close()
    assert {t[1] for t in toc} == {"PS (1 etiquetas)", "ACRILICO (1 etiquetas)"}

    # regressão: ADESIVO nunca tem item de verdade (só consumo) — não
    # pode aparecer como cabeçalho de seção vazio no corpo da OS, só na
    # linha de subtotal do fim (achado nessa varredura, 2026-08-29)
    corpo_os, _, _ = texto.partition("Subtotal por material")
    assert "ADESIVO" not in corpo_os, "ADESIVO não pode virar cabeçalho de seção vazio no corpo da OS"


def test_material_composto_nao_confunde_impresso_com_adesivado(tmp_path):
    """"IMPRESSO" é outro processo (impressão direta, sem adesivo colado
    em cima) — nunca deve contar ADESIVO junto."""
    config = copy.deepcopy(CONFIG_PADRAO)
    pasta_saida_base = tmp_path / "saida"
    entrada = tmp_path / "entrada"
    entrada.mkdir()
    _pdf_de_uma_pagina(entrada / "1UN PS 10MM IMPRESSO 1,00X1,00M_b.pdf")

    resultado = processar_etiquetas(
        str(entrada), "CLIENTE TESTE", "Gerente", "Produtor",
        config, pasta_saida_base=str(pasta_saida_base),
    )

    doc = pymupdf.open(resultado["os"])
    texto = "".join(p.get_text() for p in doc)
    doc.close()

    assert "PS · 1 item" in texto
    assert "ADESIVO" not in texto


def test_material_composto_sem_categoria_base_vira_categoria_propria(tmp_path):
    """
    Bug real de produção (2026-08-29, pedido Unilever): arquivo nomeado
    só "1UN ADESIVADO 0,80X1,29M_..." (sem MDF/PS/ACRÍLICO junto — é o
    próprio adesivo impresso pra colar, sem chapa base nesse arquivo)
    não batia em NENHUMA categoria (identificar_categoria não reconhece
    "ADESIVADO" como sinônimo de "ADESIVO") e sumia inteiro da OS/
    checklist, sem aviso nenhum além do log. Correção: quando não há
    categoria base, a própria categoria extra do composto vira a
    categoria principal, em vez de descartar o arquivo.
    """
    config = copy.deepcopy(CONFIG_PADRAO)
    pasta_saida_base = tmp_path / "saida"
    entrada = tmp_path / "entrada"
    entrada.mkdir()
    _pdf_de_uma_pagina(entrada / "1UN ADESIVADO 0,80X1,29M_cliente_resto.pdf")

    resultado = processar_etiquetas(
        str(entrada), "CLIENTE TESTE", "Gerente", "Produtor",
        config, pasta_saida_base=str(pasta_saida_base),
    )

    assert resultado["arquivos_novos"] == 1

    doc = pymupdf.open(resultado["os"])
    texto = "".join(p.get_text() for p in doc)
    doc.close()

    assert "1 item no total" in texto
    assert "ADESIVO · 1 item" in texto
    assert "1.03 m²" in texto


def test_le_png_e_jpg_alem_de_pdf(tmp_path):
    """
    Pedido do usuário (2026-08-29): entrada não pode ler só PDF — PNG/
    JPG já funcionam de verdade com o PyMuPDF (testado direto antes de
    aplicar), sem precisar de nenhuma conversão.
    """
    config = copy.deepcopy(CONFIG_PADRAO)
    pasta_saida_base = tmp_path / "saida"
    entrada = tmp_path / "entrada"
    entrada.mkdir()
    _imagem_de_uma_pagina(entrada / "1UN LONA 1,00X1,00M_a.png")
    _imagem_de_uma_pagina(entrada / "1UN PVC 1,00X1,00M_b.jpg")

    resultado = processar_etiquetas(
        str(entrada), "CLIENTE TESTE", "Gerente", "Produtor",
        config, pasta_saida_base=str(pasta_saida_base),
    )

    assert resultado is not None
    assert resultado["arquivos_novos"] == 2

    doc = pymupdf.open(resultado["os"])
    texto = "".join(p.get_text() for p in doc)
    doc.close()
    assert "2 itens no total" in texto


def test_formato_reconhecido_sem_suporte_avisa_e_nao_trava(tmp_path):
    """
    CDR aparece na prática mas não tem conversão nenhuma disponível
    (decisão do usuário, 2026-08-29: "não precisa mexer") — precisa
    avisar que o arquivo foi visto, não ficar invisível como antes, mas
    sem travar o resto da rodada. EPS/PSD têm conversão automática via
    Illustrator/Photoshop — ver test_conversao_adobe.py e o teste de
    integração logo abaixo (com conversor simulado, não abre os
    programas de verdade no teste).
    """
    config = copy.deepcopy(CONFIG_PADRAO)
    pasta_saida_base = tmp_path / "saida"
    entrada = tmp_path / "entrada"
    entrada.mkdir()
    (entrada / "1UN LONA 2,00X1,00M_arte.cdr").write_bytes(b"lixo binario qualquer, nao interessa o conteudo")
    _pdf_de_uma_pagina(entrada / "1UN PVC 1,00X1,00M_valido.pdf")

    avisos = []

    def on_log(nivel, msg):
        if nivel == "warn":
            avisos.append(msg)

    resultado = processar_etiquetas(
        str(entrada), "CLIENTE TESTE", "Gerente", "Produtor",
        config, pasta_saida_base=str(pasta_saida_base), on_log=on_log,
    )

    assert resultado is not None
    assert resultado["arquivos_novos"] == 1, "só o PDF válido deveria ter sido processado"
    assert any("CDR" in a and "não" in a for a in avisos), "deveria avisar sobre o CDR não suportado"


def test_medida_impossivel_para_chapa_recorre_a_arte(tmp_path):
    """
    Bug real de produção (2026-08-29, MDF "073X1.73M" virando 73 METROS
    por causa do zero à esquerda engolido pelo float() — reapareceu
    mais de uma vez porque só o dado salvo era corrigido, nunca a causa
    raiz). Pedido do usuário: "no caso de dúvida sempre recorra ao
    tamanho da imagem". 73m não cabe em NENHUMA chapa de MDF (máx
    1.85x2.70m no CONFIG_PADRAO) em nenhuma orientação — isso não é um
    chute de escala (a regra 1:10 testada e descartada), é geometria
    pura: a peça não cabe na chapa. Nesse caso o nome deixa de ser
    confiável e o sistema mede pela arte, como já faz quando o nome não
    tem medida nenhuma.
    """
    config = copy.deepcopy(CONFIG_PADRAO)
    pasta_saida_base = tmp_path / "saida"
    entrada = tmp_path / "entrada"
    entrada.mkdir()

    largura_pt = round(0.74 / 0.0254 * 72)
    altura_pt = round(1.73 / 0.0254 * 72)
    _pdf_com_desenho(entrada / "1UN MDF 73,00X1,73M_cliente_recorte.pdf", largura_pt, altura_pt)

    avisos = []

    def on_log(nivel, msg):
        if nivel == "warn":
            avisos.append(msg)

    resultado = processar_etiquetas(
        str(entrada), "CLIENTE TESTE", "Gerente", "Produtor",
        config, pasta_saida_base=str(pasta_saida_base), on_log=on_log,
    )

    assert resultado["arquivos_novos"] == 1
    assert any("não cabe na chapa" in a for a in avisos), "deveria avisar que a medida do nome é impossível"

    doc = pymupdf.open(resultado["os"])
    texto = "".join(p.get_text() for p in doc)
    doc.close()

    assert "126.29" not in texto and "73.00" not in texto, "não pode confiar cegamente na medida impossível do nome"
    assert "1.28 m²" in texto, "devia ter medido pela arte (0.74 x 1.73 ≈ 1.28 m²)"


def test_medida_impossivel_para_rolo_recorre_a_arte(tmp_path):
    """
    Bug real de produção (2026-08-30, pedido Unilever GJA): "1.46X094M"
    virou 1.46 x 94,00 METROS por causa do MESMO bug do zero à esquerda
    (item de totem, devia ser 0,94m) — 94m passa muito do comprimento
    de rolo cadastrado (5000cm/50m no CONFIG_PADRAO), sinal claro de
    erro de digitação. Mesmo princípio do teste de chapa acima, mas pra
    rolo: largura maior que o rolo é cenário legítimo (emenda), não
    entra nessa trava — só comprimento implausível entra.
    """
    config = copy.deepcopy(CONFIG_PADRAO)
    pasta_saida_base = tmp_path / "saida"
    entrada = tmp_path / "entrada"
    entrada.mkdir()

    largura_pt = round(1.46 / 0.0254 * 72)
    altura_pt = round(0.94 / 0.0254 * 72)
    _pdf_com_desenho(entrada / "1UN ADESIVO 1,46X094M_cliente_totem.pdf", largura_pt, altura_pt)

    avisos = []

    def on_log(nivel, msg):
        if nivel == "warn":
            avisos.append(msg)

    resultado = processar_etiquetas(
        str(entrada), "CLIENTE TESTE", "Gerente", "Produtor",
        config, pasta_saida_base=str(pasta_saida_base), on_log=on_log,
    )

    assert resultado["arquivos_novos"] == 1
    assert any("passa do comprimento de rolo" in a for a in avisos), "deveria avisar que a medida do nome é impossível"

    doc = pymupdf.open(resultado["os"])
    texto = "".join(p.get_text() for p in doc)
    doc.close()

    assert "94.00" not in texto, "não pode confiar cegamente na medida impossível do nome"
    assert "1.37 m²" in texto, "devia ter medido pela arte (1.46 x 0.94 ≈ 1.37 m²)"


def test_medida_de_rolo_mais_larga_que_o_rolo_nao_recorre_a_arte(tmp_path):
    """
    Regressão: peça mais larga que o rolo (precisaria de emenda) é
    cenário real e legítimo, não erro de digitação — só o comprimento
    implausível deve derrubar a confiança no nome, nunca a largura.
    """
    config = copy.deepcopy(CONFIG_PADRAO)
    pasta_saida_base = tmp_path / "saida"
    entrada = tmp_path / "entrada"
    entrada.mkdir()
    _pdf_de_uma_pagina(entrada / "1UN ADESIVO 1,50X2,00M_cliente.pdf")

    resultado = processar_etiquetas(
        str(entrada), "CLIENTE TESTE", "Gerente", "Produtor",
        config, pasta_saida_base=str(pasta_saida_base),
    )

    doc = pymupdf.open(resultado["os"])
    texto = "".join(p.get_text() for p in doc)
    doc.close()

    assert "3.00 m²" in texto, "1.50 x 2.00, mesmo mais largo que o rolo de 1.27m, devia confiar no nome"


def test_eps_e_convertido_e_entra_na_rodada(tmp_path, monkeypatch):
    """
    Integração da conversão automática (ver conversao_adobe.py) —
    conversor SIMULADO (só copia um PDF pronto), não abre o Illustrator
    de verdade nesse teste (lento, depende do programa instalado; a
    conversão real em si já foi verificada manualmente antes de
    aplicar). Confere que o PDF convertido entra no processamento dessa
    mesma rodada e o .eps original vai pra subpasta, sem ser apagado.
    """
    import processamento as mod_processamento

    def conversor_fake(caminho_origem, caminho_pdf_destino):
        _pdf_de_uma_pagina(caminho_pdf_destino)

    def converter_fake(pasta_entrada, nome_arquivo, pasta_originais, logger_emitir, conversores=None):
        from conversao_adobe import converter_se_necessario
        return converter_se_necessario(
            pasta_entrada, nome_arquivo, pasta_originais, logger_emitir,
            conversores={".eps": conversor_fake},
        )

    monkeypatch.setattr(mod_processamento, "converter_se_necessario", converter_fake)
    monkeypatch.setattr(mod_processamento, "CONVERSORES_POR_EXTENSAO", {".eps": conversor_fake})

    config = copy.deepcopy(CONFIG_PADRAO)
    pasta_saida_base = tmp_path / "saida"
    entrada = tmp_path / "entrada"
    entrada.mkdir()
    (entrada / "1UN LONA 2,00X1,00M_arte.eps").write_bytes(b"conteudo fake, o conversor nem olha isso")

    resultado = processar_etiquetas(
        str(entrada), "CLIENTE TESTE", "Gerente", "Produtor",
        config, pasta_saida_base=str(pasta_saida_base),
    )

    assert resultado is not None
    assert resultado["arquivos_novos"] == 1
    # o PDF convertido passa pelo resto do fluxo normal igual qualquer
    # outro arquivo — inclusive a padronização do nome (ver
    # processamento._nome_padronizado)
    assert list(entrada.glob("* LONA *.pdf")), "PDF convertido deveria ter sido processado e renomeado"
    assert (entrada / "_originais_convertidos" / "1UN LONA 2,00X1,00M_arte.eps").exists(), \
        "original deveria ter sido movido pra subpasta, nunca apagado"
    assert not (entrada / "1UN LONA 2,00X1,00M_arte.eps").exists()


def test_tif_e_convertido_e_quantidade_por_extenso_e_reconhecida(tmp_path, monkeypatch):
    """
    Integração da conversão de TIF (mesmo espírito do teste de EPS
    acima, conversor SIMULADO — TIF de verdade é grande demais/lento
    pra testar aqui) + a leitura de "N Unidades" por extenso no nome
    (ver dimensoes.py), com um nome de arquivo real (FESTA ALEMA,
    2026-08-31): "AF_Banner 50x250_Lona_8 Unidades.tif".
    """
    import processamento as mod_processamento

    def conversor_fake(caminho_origem, caminho_pdf_destino):
        _pdf_com_desenho(caminho_pdf_destino, round(0.5 / 0.0254 * 72), round(2.5 / 0.0254 * 72))

    def converter_fake(pasta_entrada, nome_arquivo, pasta_originais, logger_emitir, conversores=None):
        from conversao_adobe import converter_se_necessario
        return converter_se_necessario(
            pasta_entrada, nome_arquivo, pasta_originais, logger_emitir,
            conversores={".tif": conversor_fake},
        )

    monkeypatch.setattr(mod_processamento, "converter_se_necessario", converter_fake)
    monkeypatch.setattr(mod_processamento, "CONVERSORES_POR_EXTENSAO", {".tif": conversor_fake})

    config = copy.deepcopy(CONFIG_PADRAO)
    pasta_saida_base = tmp_path / "saida"
    entrada = tmp_path / "entrada"
    entrada.mkdir()
    (entrada / "AF_Banner 50x250_Lona_8 Unidades.tif").write_bytes(b"conteudo fake, o conversor nem olha isso")

    resultado = processar_etiquetas(
        str(entrada), "CLIENTE TESTE", "Gerente", "Produtor",
        config, pasta_saida_base=str(pasta_saida_base),
    )

    assert resultado is not None
    assert resultado["arquivos_novos"] == 1
    assert (entrada / "_originais_convertidos" / "AF_Banner 50x250_Lona_8 Unidades.tif").exists()

    doc = pymupdf.open(resultado["os"])
    texto = "".join(p.get_text() for p in doc)
    doc.close()
    assert "10.00 m²" in texto, \
        "quantidade 8 (por extenso, 'Unidades') devia ter multiplicado a área: 8 x 1.25m² (0.5x2.5m) = 10.00m²"


def test_conversao_que_falha_bloqueia_a_rodada_inteira(tmp_path, monkeypatch):
    """
    Bug real de produção (2026-09-01, pedido FESTA ALEMÃ): a conversão
    de um TIF falhou ("CoInitialize não foi chamado" — ver
    conversao_adobe._garantir_com_iniciado) e a OS/Checklist saíram
    "completos" com 1 item a menos, sem nenhum aviso — porque um
    arquivo que precisa de conversão (EPS/PSD/TIF) NUNCA chega a entrar
    em 'arquivos_arte' quando a conversão falha, então a regra de
    reconciliação de quantidade (ver test_arquivo_sem_categoria_
    bloqueia_os_e_checklist_da_rodada_inteira) não enxergava essa falta.
    Essa é a MESMA regra, mas cobrindo o caminho da conversão.
    """
    import processamento as mod_processamento

    def conversor_que_falha(caminho_origem, caminho_pdf_destino):
        raise RuntimeError("CoInitialize não foi chamado")

    def converter_fake(pasta_entrada, nome_arquivo, pasta_originais, logger_emitir, conversores=None):
        from conversao_adobe import converter_se_necessario
        return converter_se_necessario(
            pasta_entrada, nome_arquivo, pasta_originais, logger_emitir,
            conversores={".tif": conversor_que_falha},
        )

    monkeypatch.setattr(mod_processamento, "converter_se_necessario", converter_fake)
    monkeypatch.setattr(mod_processamento, "CONVERSORES_POR_EXTENSAO", {".tif": conversor_que_falha})

    config = copy.deepcopy(CONFIG_PADRAO)
    pasta_saida_base = tmp_path / "saida"
    entrada = tmp_path / "entrada"
    entrada.mkdir()
    _pdf_de_uma_pagina(entrada / "1UN LONA 2,00X1,00M_valido.pdf")
    (entrada / "8UN LONA 0,50X2,50M_banner.tif").write_bytes(b"conteudo fake, o conversor nem olha isso")

    resultado = processar_etiquetas(
        str(entrada), "CLIENTE TESTE", "Gerente", "Produtor",
        config, pasta_saida_base=str(pasta_saida_base),
    )

    assert resultado is None, "não pode gerar nada — o TIF que falhou na conversão nunca virou etiqueta"
    assert (entrada / "8UN LONA 0,50X2,50M_banner.tif").exists(), "original do TIF não pode sumir numa falha"

    pastas_geradas = list(pasta_saida_base.iterdir()) if pasta_saida_base.exists() else []
    assert len(pastas_geradas) == 1
    pasta_pedido = pastas_geradas[0]
    assert not list(pasta_pedido.glob("OS - *.pdf"))
    assert not list(pasta_pedido.glob("Checklist *.pdf"))


def test_arquivo_sem_categoria_bloqueia_os_e_checklist_da_rodada_inteira(tmp_path):
    """
    Regra de segurança pedida pelo usuário (2026-08-31), depois do caso
    real "temos 32 itens na pasta de entrada, a OS e o Checklist não
    bate" (2026-08-30): se algum arquivo da pasta de entrada não vira
    etiqueta (aqui, por não ter categoria nenhuma no nome), a
    quantidade não bate — e NENHUM documento é gerado pra essa rodada,
    nem pros arquivos que estavam OK. Preferível travar tudo e mostrar
    o erro a mandar pra fábrica uma OS/Checklist faltando peça sem
    ninguém perceber.
    """
    config = copy.deepcopy(CONFIG_PADRAO)
    pasta_saida_base = tmp_path / "saida"
    entrada = tmp_path / "entrada"
    entrada.mkdir()
    _pdf_de_uma_pagina(entrada / "1UN LONA 2,00X1,00M_valido.pdf")
    _pdf_de_uma_pagina(entrada / "arquivo_sem_material_nenhum_no_nome.pdf")

    erros = []

    def on_log(nivel, msg):
        if nivel == "err":
            erros.append(msg)

    resultado = processar_etiquetas(
        str(entrada), "CLIENTE TESTE", "Gerente", "Produtor",
        config, pasta_saida_base=str(pasta_saida_base), on_log=on_log,
    )

    assert resultado is None, "não pode gerar nada — a quantidade não bateu com a pasta de entrada"
    assert any("NÃO foram gerados" in e and "quantidade não bate" in e for e in erros)

    pastas_geradas = list(pasta_saida_base.iterdir()) if pasta_saida_base.exists() else []
    assert len(pastas_geradas) == 1, "a pasta do pedido é criada, mas sem OS nem Checklist dentro"
    pasta_pedido = pastas_geradas[0]
    assert not list(pasta_pedido.glob("OS - *.pdf"))
    assert not list(pasta_pedido.glob("Checklist *.pdf"))
    assert not (pasta_pedido / "estado_pedido.json").exists(), \
        "não pode salvar estado — senão o arquivo válido nunca mais seria reprocessado numa rodada futura"


def test_todos_os_arquivos_processados_gera_normalmente(tmp_path):
    """Contraprova da regra acima: quando todos os arquivos da pasta de entrada viram etiqueta, gera normal."""
    config = copy.deepcopy(CONFIG_PADRAO)
    pasta_saida_base = tmp_path / "saida"
    entrada = tmp_path / "entrada"
    entrada.mkdir()
    _pdf_de_uma_pagina(entrada / "1UN LONA 2,00X1,00M_valido.pdf")
    _pdf_de_uma_pagina(entrada / "1UN PVC 1,00X1,00M_valido.pdf")

    resultado = processar_etiquetas(
        str(entrada), "CLIENTE TESTE", "Gerente", "Produtor",
        config, pasta_saida_base=str(pasta_saida_base),
    )

    assert resultado is not None
    assert resultado["arquivos_novos"] == 2
    assert resultado["os"] is not None
    assert resultado["unificado"] is not None


def test_obter_pdf_reduzido_cria_copia_e_nunca_toca_no_original(tmp_path):
    entrada = tmp_path
    caminho_original = entrada / "grande.pdf"
    _pdf_de_uma_pagina(caminho_original)
    conteudo_original = caminho_original.read_bytes()

    chamadas = []

    def reduzir_fake(caminho_origem, caminho_destino):
        chamadas.append((caminho_origem, caminho_destino))
        pathlib.Path(caminho_destino).write_bytes(b"pdf fake reduzido")

    class _LoggerFake:
        def emitir(self, *a, **k):
            pass

    resultado = _obter_pdf_reduzido(str(entrada), "grande.pdf", _LoggerFake(), reduzir=reduzir_fake)

    assert resultado is not None
    assert pathlib.Path(resultado).name == "grande.pdf"
    assert pathlib.Path(resultado).parent.name == "_reduzidos_para_processar"
    assert pathlib.Path(resultado).read_bytes() == b"pdf fake reduzido"
    assert caminho_original.read_bytes() == conteudo_original, "original não pode ser tocado"
    assert len(chamadas) == 1


def test_obter_pdf_reduzido_reaproveita_copia_ja_existente(tmp_path):
    entrada = tmp_path
    _pdf_de_uma_pagina(entrada / "grande.pdf")

    chamadas = []

    def reduzir_fake(caminho_origem, caminho_destino):
        chamadas.append(1)
        pathlib.Path(caminho_destino).write_bytes(b"pdf fake reduzido")

    class _LoggerFake:
        def emitir(self, *a, **k):
            pass

    logger = _LoggerFake()
    _obter_pdf_reduzido(str(entrada), "grande.pdf", logger, reduzir=reduzir_fake)
    _obter_pdf_reduzido(str(entrada), "grande.pdf", logger, reduzir=reduzir_fake)

    assert len(chamadas) == 1, "não pode reduzir de novo se a cópia já existe"


def test_obter_pdf_reduzido_troca_extensao_pra_pdf_quando_original_e_imagem(tmp_path, monkeypatch):
    """
    Pedido do usuário (2026-09-01): "preciso adicionar a extensão png,
    preciso que leia esse formato também via Photoshop" — mesmo caminho
    de resgate por falta de memória já usado pro PDF, agora pra PNG/JPG
    também. A redução sempre produz PDF (mesmo de um PNG de origem),
    então o nome da cópia troca de extensão.
    """
    import processamento as mod_processamento
    import conversao_adobe

    monkeypatch.setattr(conversao_adobe, "COM_DISPONIVEL", True)

    entrada = tmp_path
    (entrada / "foto.png").write_bytes(b"conteudo fake de imagem, nao importa aqui")

    chamadas = []

    def reduzir_imagem_fake(caminho_origem, caminho_destino):
        chamadas.append((caminho_origem, caminho_destino))
        pathlib.Path(caminho_destino).write_bytes(b"pdf fake reduzido a partir de imagem")

    monkeypatch.setattr(conversao_adobe, "reduzir_imagem_grande", reduzir_imagem_fake)

    class _LoggerFake:
        def emitir(self, *a, **k):
            pass

    resultado = mod_processamento._obter_pdf_reduzido(str(entrada), "foto.png", _LoggerFake())

    assert resultado is not None
    assert pathlib.Path(resultado).suffix == ".pdf", "a cópia reduzida é sempre PDF, mesmo vindo de PNG"
    assert pathlib.Path(resultado).stem == "foto"
    assert len(chamadas) == 1, "devia ter usado reduzir_imagem_grande, não reduzir_pdf_grande"


def test_arte_grande_demais_reduz_resolucao_automaticamente_sem_mexer_no_original(tmp_path, monkeypatch):
    """
    Bug real de produção (2026-09-01, pedido FESTA ALEMÃ): PDFs
    nascidos de TIF gigante falhavam com "malloc failed" ao montar a
    etiqueta, mesmo com pouca memória de sobra na máquina. Pedido do
    usuário: "pode reduzir o que precisar... a única coisa é não mexer
    nos arquivos originais, pode criar uma regra". Simula a falha de
    memória na pré-checagem (ver processar_etiquetas) e confere que o
    sistema troca pra uma cópia reduzida automaticamente, processa
    normal a partir dela, e nunca toca no arquivo original.
    """
    import processamento as mod_processamento

    reducoes = []

    def obter_pdf_reduzido_fake(pasta_entrada, arquivo, logger, reduzir=None):
        pasta_reduzidos = pathlib.Path(pasta_entrada).resolve() / "_reduzidos_para_processar"
        pasta_reduzidos.mkdir(parents=True, exist_ok=True)
        caminho_reduzido = pasta_reduzidos / arquivo
        reducoes.append(str(caminho_reduzido))
        _pdf_de_uma_pagina(caminho_reduzido)
        return str(caminho_reduzido)

    monkeypatch.setattr(mod_processamento, "_obter_pdf_reduzido", obter_pdf_reduzido_fake)

    pixmap_original = pymupdf.Page.get_pixmap
    chamadas = {"n": 0}

    def get_pixmap_fake(self, *args, **kwargs):
        chamadas["n"] += 1
        if chamadas["n"] == 1:
            raise RuntimeError("code=2: malloc (999999999 bytes) failed")
        return pixmap_original(self, *args, **kwargs)

    monkeypatch.setattr(pymupdf.Page, "get_pixmap", get_pixmap_fake)

    config = copy.deepcopy(CONFIG_PADRAO)
    pasta_saida_base = tmp_path / "saida"
    entrada = tmp_path / "entrada"
    entrada.mkdir()
    caminho_original = entrada / "1UN LONA 2,00X1,00M_grande.pdf"
    _pdf_de_uma_pagina(caminho_original)
    conteudo_original = caminho_original.read_bytes()

    resultado = processar_etiquetas(
        str(entrada), "CLIENTE TESTE", "Gerente", "Produtor",
        config, pasta_saida_base=str(pasta_saida_base),
    )

    assert resultado is not None, "devia ter processado normal depois de trocar pra cópia reduzida"
    assert resultado["arquivos_novos"] == 1
    assert reducoes, "devia ter tentado reduzir a resolução"

    # o arquivo é renomeado pro padrão ANTES da checagem de memória (já
    # é assim independente dessa regra nova) — o que importa aqui é que
    # o conteúdo original nunca foi reescrito, só o nome do arquivo.
    arquivos_finais = list(entrada.glob("*.pdf"))
    assert len(arquivos_finais) == 1
    assert arquivos_finais[0].read_bytes() == conteudo_original, "conteúdo original não pode ser alterado"
