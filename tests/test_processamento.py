import copy
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import pymupdf

from config import CONFIG_PADRAO
from processamento import _eh_reposicao, _nome_padronizado, processar_etiquetas


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


def test_rodadas_seguintes_geram_checklist_separado_e_versionado(tmp_path):
    """
    Decisão do usuário (2026-08-26): cada rodada (arquivo novo ou
    reposição) vira um checklist SEPARADO — nunca mais cola página num
    checklist que já foi impresso/marcado à caneta antes. Primeira
    rodada sem sufixo, segunda "V2", terceira "V3" — cada uma só com o
    que foi processado NAQUELA rodada. Desde 2026-08-28 só existe UM
    checklist por rodada (não mais um arquivo separado por categoria) —
    "Checklist CLIENTE.pdf", "V2.pdf", "V3.pdf". Roda 3 rodadas reais e
    confere o nome de cada arquivo em disco e quantas etiquetas cada um
    tem, e que nenhum arquivo por categoria foi gerado.
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
    assert nomes_checklist == [
        "Checklist CLIENTE TESTE V2.pdf",
        "Checklist CLIENTE TESTE V3.pdf",
        "Checklist CLIENTE TESTE.pdf",
    ]

    def _paginas(nome):
        doc = pymupdf.open(str(pasta_saida / nome))
        n = len(doc)
        doc.close()
        return n

    # cada rodada tem 1 arquivo só (banner + 1 etiqueta = 1 página cada)
    assert _paginas("Checklist CLIENTE TESTE.pdf") == 1
    assert _paginas("Checklist CLIENTE TESTE V2.pdf") == 1
    assert _paginas("Checklist CLIENTE TESTE V3.pdf") == 1


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
    assert nomes_checklist == ["Checklist SUPERBET V2.pdf", "Checklist SUPERBET.pdf"]


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
