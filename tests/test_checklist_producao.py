"""
Checklist de Produção: lê a pasta PRODUCAO e monta a OS no padrão da casa.

O documento em si é desenhado por relatorios.gerar_os (miniatura, quadrinho
de marcar, subtotal por material) — aqui se testa o que é deste módulo: o
status que vem da pasta, o material/quantidade que vêm do nome, e o
subtotal por material (nunca somado entre materiais).

Nenhum teste toca pasta real: tudo em tmp_path.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import checklist_producao as cp


def _criar(pasta, *relativos):
    for rel in relativos:
        caminho = pasta / rel
        caminho.parent.mkdir(parents=True, exist_ok=True)
        caminho.write_bytes(b"%PDF-1.4 fake")   # so o nome importa
    return pasta


def _producao(tmp_path):
    return _criar(
        tmp_path / "PRODUCAO",
        "A_PREMIUM/SOLVENTE/PRONTOS/1UN LONA IMPRESSA 5.20X3.20M_L04.pdf",
        "A_PREMIUM/UV/4UN LONA IMPRESSA 3.20X0.60M_L12.pdf",
        "CAEX PATRO/ADESIVOS/Prontos/1UN VINIL IMPRESSO 6.10X1.10M_TESTEIRA.pdf",
        "TUNEL ENTRADA/NAO RODAR AINDA/2UN LONA IMPRESSA 1.90X4.55M_LAT.pdf",
    )


def _por_arquivo(tmp_path):
    itens = cp.inventariar(_producao(tmp_path), com_miniatura=False)
    return {i["arquivo"].split("_")[-1].replace(".pdf", ""): i for i in itens}


def test_status_vem_da_pasta(tmp_path):
    itens = _por_arquivo(tmp_path)

    assert itens["L04"]["status"] == cp.STATUS_PRONTO
    assert itens["L12"]["status"] == cp.STATUS_FAZER        # em UV, sem Prontos
    assert itens["TESTEIRA"]["status"] == cp.STATUS_PRONTO
    assert itens["LAT"]["status"] == cp.STATUS_ESPERA       # NAO RODAR AINDA


def test_cada_item_leva_o_selo_do_seu_status(tmp_path):
    """É pelo selo que a OS mostra o status; sem ele o documento fica mudo."""
    itens = _por_arquivo(tmp_path)

    assert itens["L04"]["selo"]["texto"] == "PRONTO"
    assert itens["L12"]["selo"]["texto"] == "A FAZER"
    assert itens["LAT"]["selo"]["texto"] == "ESPERA"


def test_area_e_maquina_saem_da_arvore(tmp_path):
    itens = _por_arquivo(tmp_path)

    assert itens["L04"]["area"] == "A_PREMIUM"
    assert itens["L04"]["maquina"] == "SOLVENTE"
    assert itens["L12"]["maquina"] == "UV"
    assert itens["TESTEIRA"]["area"] == "CAEX PATRO"
    assert itens["LAT"]["maquina"] == ""                    # direto na área


def test_material_quantidade_e_area_do_nome(tmp_path):
    itens = _por_arquivo(tmp_path)

    assert itens["L04"]["categoria"] == "LONA"
    assert itens["TESTEIRA"]["categoria"] == "ADESIVO"      # VINIL IMPRESSO -> ADESIVO
    # a OS mostra a área POR UNIDADE na linha, e a quantidade ao lado
    assert itens["L12"]["quantidade"] == 4
    assert round(itens["L12"]["dimensao"]["area_m2"], 2) == round(3.20 * 0.60, 2)
    # o m² total (com quantidade) é o que entra no subtotal
    assert round(itens["L12"]["m2_total"], 2) == round(3.20 * 0.60 * 4, 2)


def test_quantidade_nunca_vira_1_calado(tmp_path):
    """
    extrair_quantidade devolve (qtd, achou) — tratar a tupla como número
    fazia TODA peça virar 1un e o m² sair subcontado (2026-09-12).
    """
    itens = _por_arquivo(tmp_path)

    assert itens["LAT"]["quantidade"] == 2
    assert sum(i["quantidade"] for i in itens.values()) == 1 + 4 + 1 + 2


def test_subtotal_por_material_usa_o_total_e_nunca_junta(tmp_path):
    itens = cp.inventariar(_producao(tmp_path), com_miniatura=False)
    ordem = cp.ordem_das_categorias(itens, {"ordem_unificado": ["LONA", "ADESIVO"]})
    dados = cp.dados_por_categoria(itens, ordem)

    assert ordem == ["LONA", "ADESIVO"]
    # ADESIVO isolado, nunca somado com LONA
    assert round(dados["ADESIVO"]["area_total_m2"], 2) == round(6.10 * 1.10, 2)
    # LONA: 5.20x3.20 + 4x(3.20x0.60) + 2x(1.90x4.55)
    esperado = 5.20 * 3.20 + 4 * (3.20 * 0.60) + 2 * (1.90 * 4.55)
    assert round(dados["LONA"]["area_total_m2"], 2) == round(esperado, 2)


def test_resumo_conta_pecas_e_unidades(tmp_path):
    r = cp.resumo(cp.inventariar(_producao(tmp_path), com_miniatura=False))

    assert r["total"] == 4          # linhas de arte
    assert r["unidades"] == 8       # peças físicas
    assert (r["prontos"], r["a_fazer"], r["em_espera"]) == (2, 1, 1)


def test_miniatura_de_pdf_quebrado_nao_derruba(tmp_path):
    """Miniatura é conforto visual — nunca motivo pra o documento não sair."""
    ruim = tmp_path / "ruim.pdf"
    ruim.write_bytes(b"isto nao e pdf")

    assert cp.miniatura(ruim) is None


def test_gera_a_os_no_nome_da_casa(tmp_path):
    prod = _producao(tmp_path)
    saida = tmp_path / "saida"

    caminho = cp.gerar(saida, prod, nome_cliente="TESTE ML", com_miniatura=False)

    assert caminho.name == "OS - TESTE ML.pdf"
    assert caminho.is_file()
    import pymupdf
    doc = pymupdf.open(str(caminho))
    try:
        assert doc.page_count >= 1
        texto = "".join(doc[p].get_text() for p in range(doc.page_count))
    finally:
        doc.close()
    # o padrão da casa tem que estar lá
    assert "ORDEM DE SERVIÇO" in texto
    assert "Subtotal por material" in texto
    assert "A FAZER" in texto and "PRONTO" in texto


def test_data_sai_formatada_e_nao_datetime_cru(tmp_path):
    """
    A OS recebe a data como STRING pronta. Passar o datetime cru imprimia
    '2026-09-12 20:44:42.538633' no cabeçalho (2026-09-12).
    """
    import datetime
    prod = _producao(tmp_path)
    quando = datetime.datetime(2026, 9, 12, 20, 44, 42)

    caminho = cp.gerar(tmp_path / "saida", prod, nome_cliente="TESTE ML",
                       quando=quando, com_miniatura=False)

    import pymupdf
    doc = pymupdf.open(str(caminho))
    try:
        texto = doc[0].get_text()
    finally:
        doc.close()
    assert "12/09/2026 20:44:42" in texto
    assert "2026-09-12" not in texto
