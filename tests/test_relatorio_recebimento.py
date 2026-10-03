"""
Testes do relatório de recebimento — a parte que monta os blocos, que é
pura (não fala com a API do Slides nem escreve arquivo).
"""
import datetime

import pymupdf

import relatorio_recebimento as rr


def _ficha(slide, nome, situacao="APROVADO", **extra):
    return {"slide": slide, "nome": nome, "situacao": situacao, "links": ["http://x"],
            "nome_arquivo": nome + ".pdf", "material": "LONA", "medidas": "2,00 x 1,00 m", **extra}


def _blocos(fichas, baixados, previas=None):
    return rr.montar_blocos(fichas, baixados, "PRES", {}, "caderno",
                            datetime.datetime(2026, 9, 23, 8, 0), previas)


def test_linha_da_arte_baixada_mostra_a_previa():
    fichas = [_ficha(3, "PAINEL")]
    chave = "caderno|slide|3"
    baixados = {chave: {"arquivo": "1UN LONA 2.00X1.00M_PAINEL.pdf",
                        "quando": "2026-09-23T07:00:00"}}

    blocos = _blocos(fichas, baixados, {chave: ("previa_0.jpg", (60, 30))})

    linha = [b for b in blocos if "PAINEL" in b][0]
    assert "<img src='previa_0.jpg'" in linha
    assert "width='60' height='30'" in linha


def test_sem_previa_sai_o_quadrado_cinza():
    """Arte que não abre (EPS) não pode impedir o documento de sair."""
    fichas = [_ficha(3, "PAINEL")]
    chave = "caderno|slide|3"

    blocos = _blocos(fichas, {chave: {"arquivo": "x.pdf", "quando": "2026-09-23T07:00:00"}})

    linha = [b for b in blocos if "PAINEL" in b][0]
    # o <img> do selo "JA PEGAMOS" continua la: o que nao pode e a previa
    assert "previa_" not in linha
    assert "background:#f0f1f3" in linha


def test_previas_das_artes_acha_o_arquivo_em_qualquer_subpasta(tmp_path):
    """A arte mora em ARTES/<área>/, e a área é opcional."""
    destino = tmp_path / "ARTES" / "EIXO PRINCIPAL"
    destino.mkdir(parents=True)
    doc = pymupdf.open()
    doc.new_page(width=200, height=100)
    doc.save(str(destino / "arte.pdf"))
    doc.close()

    arquivo = pymupdf.Archive()
    previas = rr._previas_das_artes(tmp_path, {"c|1|X": {"arquivo": "arte.pdf"}}, arquivo)

    nome, (largura, altura) = previas["c|1|X"]
    assert nome.endswith(".jpg")
    assert (largura, altura) == (60, 30), "a proporção da arte tem que ser mantida"


def test_arte_que_nao_esta_na_pasta_nao_quebra(tmp_path):
    previas = rr._previas_das_artes(tmp_path, {"c|1|X": {"arquivo": "sumiu.pdf"}}, pymupdf.Archive())

    assert previas == {}


# ================================ caderno do Canva (2026-10-02) — o mesmo modelo

def _caderno_canva():
    def ficha(pagina, nome, link, secao="LONAS", **extra):
        return {"pagina": pagina, "nome": nome, "secao": secao, "medidas": "7,14 x 1,10m",
                "material": "LONA IMPRESSA", "quantidade": "1", "links": [link] if link else [], **extra}
    return {"titulo": "Caderno de artes - LOJINHA MR2 CULTURAL", "design_id": "DAHWe8X_fZk",
            "link": "https://www.canva.com/design/DAHWe8X_fZk/codigo123/edit",
            "fichas": [ficha(8, "LONA A", "https://drive.google.com/file/d/1LONAAaaaaaaaaaaa/view"),
                       ficha(41, "LONA PISO", "https://drive.google.com/file/d/1PISOaaaaaaaaaaaa/view"),
                       ficha(50, "PLACA PS", None, secao="ADESIVOS", link_do_modelo=True)]}


def _blocos_canva(baixados, previas=None):
    caderno = _caderno_canva()
    return rr.montar_blocos(caderno["fichas"], baixados, None, None, None,
                            datetime.datetime(2026, 10, 2, 20, 0), previas, fonte=rr._FonteCanva(caderno))


def test_canva_linha_tem_o_caderno_na_pagina_e_o_arquivo_de_onde_veio():
    """Pedido de 02/10: 'link indicando de onde pegou a determinada arte'."""
    chave = "canva|DAHWe8X_fZk|p08|1LONAAaaaaaaaaaaa"
    baixados = {chave: {"arquivo": "1UN LONA 7,44X1,40M_LONA A.pdf", "quando": "2026-10-02T19:41:49",
                        "link_origem": "https://drive.google.com/file/d/1LONAAaaaaaaaaaaa/view"}}

    blocos = _blocos_canva(baixados, {chave: ("previa_0.jpg", (60, 11))})

    linha = [b for b in blocos if "LONA A" in b][0]
    assert "<img src='previa_0.jpg'" in linha
    assert "https://www.canva.com/design/DAHWe8X_fZk/codigo123/view\"" in linha   # sem #página: 02/10
    assert "https://drive.google.com/file/d/1LONAAaaaaaaaaaaa/view" in linha and "arquivo de origem" in linha
    assert "p.08" in linha and "JÁ PEGAMOS" in linha
    assert any("1 de 3 peças do caderno já recebidas" in b for b in blocos)


def test_canva_sem_link_gravado_o_arquivo_sai_da_chave_do_registro():
    """O VIBRA foi arquivado antes do link entrar no registro: o id do Drive está na chave."""
    chave = "canva|DAHWe8X_fZk|p08|1LONAAaaaaaaaaaaa"
    blocos = _blocos_canva({chave: {"arquivo": "x.pdf", "quando": "2026-10-02T19:41:49"}})
    linha = [b for b in blocos if "LONA A" in b][0]
    assert "https://drive.google.com/file/d/1LONAAaaaaaaaaaaa/view" in linha


def test_canva_ficha_com_varias_pecas_tem_uma_linha_por_arquivo():
    """O piso de 7,00 x 6,00 em três lonas: três arquivos, cada um com a sua prévia."""
    baixados = {"canva|DAHWe8X_fZk|p41|1PISOaaaaaaaaaaaa|pagina %d" % i: {"arquivo": "PISO %d.pdf" % i,
                                                                           "quando": "2026-10-02T19:41:49"}
                for i in (1, 2, 3)}
    blocos = _blocos_canva(baixados)
    assert sum(1 for b in blocos if "LONA PISO" in b and "<table" in b) == 3


def test_canva_o_que_falta_diz_por_que():
    blocos = _blocos_canva({})
    falta = [b for b in blocos if "PLACA PS" in b][0]
    assert "link escrito do modelo" in falta
    assert any("AINDA FALTAM" in b for b in blocos)


def test_slides_ganhou_o_link_da_pasta_da_arte():
    """O do Mercado Livre também diz de onde a arte foi pega: a pasta do Drive da ficha."""
    fichas = [_ficha(3, "PAINEL")]
    blocos = _blocos(fichas, {"caderno|slide|3": {"arquivo": "x.pdf", "quando": "2026-09-23T07:00:00"}})
    linha = [b for b in blocos if "PAINEL" in b][0]
    assert "pasta da arte" in linha and "http://x" in linha


def test_caderno_guardado_e_o_mais_recente(tmp_path):
    import json
    for quando, titulo in (("2026-10-01T10:00:00", "velho"), ("2026-10-02T19:41:50", "novo")):
        pasta = tmp_path / "_sistema" / "recebidos" / titulo
        pasta.mkdir(parents=True)
        (pasta / "caderno.json").write_text(json.dumps({"titulo": titulo, "lido_em": quando,
                                                        "fichas": [{"pagina": 1}]}), encoding="utf-8")
    assert rr.caderno_guardado(tmp_path)["titulo"] == "novo"
    assert rr.caderno_guardado(tmp_path / "outro") is None


def test_gerar_do_canva_escreve_o_pdf_com_os_links(tmp_path):
    caderno = _caderno_canva()
    artes = tmp_path / "ARTES"
    artes.mkdir()
    doc = pymupdf.open()
    doc.new_page(width=300, height=60)
    doc.save(str(artes / "1UN LONA 7,44X1,40M_LONA A.pdf"))
    doc.close()
    import json
    (tmp_path / "_baixados.json").write_text(json.dumps({"canva|DAHWe8X_fZk|p08|1LONAAaaaaaaaaaaa": {
        "arquivo": "1UN LONA 7,44X1,40M_LONA A.pdf", "quando": "2026-10-02T19:41:49"}}), encoding="utf-8")

    destino = rr.gerar_do_canva(tmp_path / "RECEBIMENTO - VIBRA.pdf", caderno, tmp_path, nome_cliente="VIBRA")

    pdf = pymupdf.open(destino)
    texto = "".join(p.get_text() for p in pdf)
    links = [l.get("uri") for p in pdf for l in p.get_links()]
    assert "VIBRA · LOJINHA MR2 CULTURAL" in texto and "1 de 3 peças" in texto
    assert "https://www.canva.com/design/DAHWe8X_fZk/codigo123/view" in links
    assert not any(l and "#" in l for l in links), "link com # pode chegar como %23 e dar 404 no Canva"
    assert "https://drive.google.com/file/d/1LONAAaaaaaaaaaaa/view" in links


# ============== a página do caderno anexada (02/10: "continua travada")
#
# O visualizador do Canva não termina de abrir o caderno de 68 páginas. A
# imagem da página de cada ficha vai anexada no fim do relatório, e 'abrir no
# caderno' pula pra ela dentro do PDF — sem rede, sem Canva.

def _imagem_de_pagina(texto="ORTOGONAL"):
    doc = pymupdf.open()
    pg = doc.new_page(width=596, height=335)
    pg.insert_text((40, 60), texto, fontsize=20)
    dados = pg.get_pixmap().tobytes("png")
    doc.close()
    return dados


def _relatorio_com_paginas(tmp_path, paginas, nome="RECEBIMENTO - VIBRA.pdf", **extra):
    import json
    caderno = _caderno_canva()
    (tmp_path / "_baixados.json").write_text(json.dumps({"canva|DAHWe8X_fZk|p08|1LONAAaaaaaaaaaaa": {
        "arquivo": "LONA A.pdf", "quando": "2026-10-02T19:41:49"}}), encoding="utf-8")
    destino = rr.gerar_do_canva(tmp_path / nome, caderno, tmp_path,
                                nome_cliente="VIBRA", paginas=paginas, **extra)
    return pymupdf.open(destino)


def test_abrir_no_caderno_pula_pra_pagina_anexada_no_proprio_pdf(tmp_path):
    pdf = _relatorio_com_paginas(tmp_path, {8: _imagem_de_pagina(), 41: _imagem_de_pagina("PISO")},
                                 paginas_em="2026-10-02T22:10:00")

    anexos = [i for i in range(pdf.page_count) if pdf[i].rect.height < 500]
    assert len(anexos) == 2, "uma folha por página do caderno que alguma linha aponta"
    pulos = [l for i in range(pdf.page_count) for l in pdf[i].get_links()
             if l["kind"] == pymupdf.LINK_GOTO and l.get("page") in anexos]
    assert pulos, "'abrir no caderno' tem que pular pra folha da página, não sair pra rede"
    texto = pdf[anexos[0]].get_text()
    assert "PÁGINA 08" in texto and "LONAS" in texto and "LONA A" in texto
    assert "voltar à lista" in texto and "abrir no Canva" in texto
    assert "02/10 22:10" in texto, "de quando é a imagem tem que estar escrito"
    assert pdf[anexos[0]].get_images(), "a imagem da página tem que estar na folha"


def test_pagina_sem_imagem_continua_abrindo_o_canva(tmp_path):
    """Página mexida depois do recebimento fica sem imagem — a linha dela abre o Canva."""
    pdf = _relatorio_com_paginas(tmp_path, {8: _imagem_de_pagina()})

    uris = [l.get("uri") for i in range(pdf.page_count) for l in pdf[i].get_links()]
    assert "https://www.canva.com/design/DAHWe8X_fZk/codigo123/view" in uris
    assert not any(u and u.startswith("caderno:") for u in uris), "o link de dentro nunca sai no PDF"


def test_sem_imagem_nenhuma_o_relatorio_nao_ganha_folha(tmp_path):
    sem = _relatorio_com_paginas(tmp_path, None, nome="sem.pdf")
    com = _relatorio_com_paginas(tmp_path, {8: _imagem_de_pagina()}, nome="com.pdf")
    assert com.page_count == sem.page_count + 1
    # a fonte do PDF junta 'fi' numa letra só: comparar sem a palavra 'fim'
    texto = " ".join(" ".join(p.get_text().split()) for p in com)
    assert "Ver as páginas do caderno" in texto and "abrir no Canva" in texto


def test_completar_paginas_so_pega_o_que_nao_mudou(tmp_path):
    """
    O VIBRA foi arquivado antes de a imagem existir. Refazer o relatório lê o
    Canva de novo — e só guarda a página que ainda diz o que dizia no dia.
    """
    import json
    pasta = tmp_path / "_sistema" / "recebidos" / "2026-10-02 Canva"
    pasta.mkdir(parents=True)
    caderno = dict(_caderno_canva(), lido_em="2026-10-02T19:41:49")
    (pasta / "caderno.json").write_text(json.dumps(caderno), encoding="utf-8")
    guardado = rr.caderno_guardado(tmp_path)

    novo = _caderno_canva()
    novo["fichas"][1] = dict(novo["fichas"][1], medidas="7,00 x 6,00m")      # a p.41 mudou
    novo["enderecos_das_paginas"] = {8: "http://x/8", 41: "http://x/41", 50: "http://x/50"}
    pedidas = {}

    def baixar(enderecos, numeros=None, **k):
        pedidas.update({"numeros": set(numeros)})
        return {n: _imagem_de_pagina() for n in numeros}

    guardadas = rr.completar_paginas(guardado, ler=lambda link: novo, baixar=baixar)

    assert pedidas["numeros"] == {8, 50}, "a página mexida não pode ilustrar o recebimento antigo"
    assert sorted(guardadas) == [8, 50]
    assert json.loads((pasta / "caderno.json").read_text(encoding="utf-8"))["paginas_em_imagem"]["8"]


def test_completar_paginas_com_o_canva_fora_do_ar_nao_estraga_nada(tmp_path):
    import json
    pasta = tmp_path / "_sistema" / "recebidos" / "2026-10-02 Canva"
    pasta.mkdir(parents=True)
    (pasta / "caderno.json").write_text(json.dumps(_caderno_canva()), encoding="utf-8")

    def cair(link):
        raise OSError("o Canva não respondeu")

    assert rr.completar_paginas(rr.caderno_guardado(tmp_path), ler=cair) == {}
