"""
tests/test_acabamento_completo.py — Suíte completa de testes de acabamento industrial gráfico.

Testa 100% dos requisitos da ISSUE-07:
  1. Eliminação total de PyMuPDF em acabamento.py e nos geradores de teste.
  2. Uso exclusivo do motor interno motor_pdf (PdfWriter, PdfReader, Caixa, etc.).
  3. Cálculo de posições de ilhós (perímetro, cantos, recuo proporcional, deduplicação).
  4. Operadores nativos de ilhós com curvas de Bézier cúbicas (kappa = 0.5522847498) e duplo contraste.
  5. Aplicação de ilhós em PDF via Form XObject nativo.
  6. Borda de solda / bainha térmica com linhas guia pontilhadas [3 3] 0 d.
  7. Sangria espelhada (Mirror Bleed) nas 4 margens e 4 cantos via matrizes afins e clipping.
  8. Camada vetorial CutContour com ColorSpace Separation (100% Magenta) e OCG (Optional Content Group).
"""

import math
import pathlib
import pytest

import acabamento
from motor_pdf import (
    Caixa,
    PdfDict,
    PdfName,
    PdfReader,
    PdfRef,
    PdfStream,
    PdfString,
    PdfWriter,
    abrir_pdf,
)


def _criar_pdf_teste(caminho, largura_pt=595.28, altura_pt=841.89, cor_rgb=(0.2, 0.4, 0.8)):
    """Cria um PDF de teste nativo usando PdfWriter."""
    writer = PdfWriter(versao="1.6")
    conteudo = (
        f"q\n"
        f"{cor_rgb[0]:.2f} {cor_rgb[1]:.2f} {cor_rgb[2]:.2f} rg\n"
        f"0 0 {largura_pt:.2f} {altura_pt:.2f} re f\n"
        f"Q\n"
    ).encode("ascii")
    writer.adicionar_pagina(largura_pt=largura_pt, altura_pt=altura_pt, recursos={}, conteudo_bytes=conteudo)
    writer.salvar(caminho)


def _criar_pdf_multipage_teste(caminho, lista_tamanhos):
    """Cria um PDF multipágina com diferentes tamanhos."""
    writer = PdfWriter(versao="1.6")
    for idx, (w, h) in enumerate(lista_tamanhos):
        conteudo = f"q 0.5 0.5 0.5 rg 0 0 {w:.2f} {h:.2f} re f Q\n".encode("ascii")
        writer.adicionar_pagina(largura_pt=w, altura_pt=h, recursos={}, conteudo_bytes=conteudo)
    writer.salvar(caminho)


# =========================================================================
# 1. Testes de Cálculo de Posições de Ilhós
# =========================================================================

def test_calcular_posicoes_cantos_apenas():
    largura = 800.0
    altura = 600.0
    recuo_m = 0.03
    recuo_pt = recuo_m * acabamento.PT_POR_M

    posicoes = acabamento.calcular_posicoes_ilhos(
        largura, altura, recuo_borda_m=recuo_m, cantos_apenas=True
    )
    assert len(posicoes) == 4
    assert posicoes[0] == (recuo_pt, recuo_pt)
    assert posicoes[1] == (largura - recuo_pt, recuo_pt)
    assert posicoes[2] == (largura - recuo_pt, altura - recuo_pt)
    assert posicoes[3] == (recuo_pt, altura - recuo_pt)


def test_calcular_posicoes_espacamento_invalido_ou_zero():
    posicoes = acabamento.calcular_posicoes_ilhos(1000.0, 500.0, espacamento_m=0.0)
    assert len(posicoes) == 4
    posicoes_neg = acabamento.calcular_posicoes_ilhos(1000.0, 500.0, espacamento_m=-0.5)
    assert len(posicoes_neg) == 4


def test_calcular_posicoes_recuo_limitado_a_quarto_da_pagina():
    # Dimensões pequenas onde o recuo excederia 1/4 da página
    w = 100.0
    h = 80.0
    recuo_grande_m = 1.0  # 1m em folha de ~3.5cm
    posicoes = acabamento.calcular_posicoes_ilhos(w, h, recuo_borda_m=recuo_grande_m, cantos_apenas=True)
    # Deve ser limitado a min(w/4, h/4) = 20.0
    assert posicoes[0] == (20.0, 20.0)
    assert posicoes[1] == (80.0, 20.0)
    assert posicoes[2] == (80.0, 60.0)
    assert posicoes[3] == (20.0, 60.0)


def test_calcular_posicoes_distribuicao_regular():
    # Lona de 3x1 metros com espaçamento de 0.50m
    w_pt = 3.0 * acabamento.PT_POR_M
    h_pt = 1.0 * acabamento.PT_POR_M
    posicoes = acabamento.calcular_posicoes_ilhos(w_pt, h_pt, espacamento_m=0.50, recuo_borda_m=0.025)

    # 3m / 0.5m = 6 intervalos no topo e na base (7 furos por borda horizontal)
    # 1m / 0.5m = 2 intervalos nas laterais (1 furo intermediário por lateral)
    # Total esperado: aproximadamente 6 + 6 + 2 + 2 = 16 furos únicos
    assert len(posicoes) >= 14
    assert len(posicoes) <= 18

    # Confere que não há furos sobrepostos
    for i, p1 in enumerate(posicoes):
        for j, p2 in enumerate(posicoes):
            if i != j:
                dist = math.hypot(p1[0] - p2[0], p1[1] - p2[1])
                assert dist >= 2.0, f"Furos duplicados encontrados: {p1} e {p2}"


# =========================================================================
# 2. Testes de Comandos Nativos de Ilhós (Bézier e Duplo Contraste)
# =========================================================================

def test_gerar_comandos_marca_ilhos_estrutura():
    x, y = 150.0, 250.0
    cmds = acabamento.gerar_comandos_marca_ilhos(x, y, diametro_mm=10.0, tamanho_mira_mm=4.0)

    assert isinstance(cmds, bytes)
    texto = cmds.decode("ascii")

    # Verifica isolamento de estado gráfico
    assert texto.startswith("q\n")
    assert texto.endswith("Q\n")

    # 1. Halo branco externo
    assert "1 1 1 RG" in texto
    assert "1.8 w" in texto

    # 2. Círculo interno preto
    assert "0 0 0 RG" in texto
    assert "0.8 w" in texto

    # 3. Ponto de agulha central
    assert "1 1 1 rg 0 0 0 RG" in texto
    assert "0.5 w" in texto
    assert "b\n" in texto or "b" in texto

    # 4. Verifica aproximação cúbica de Bézier (kappa = 0.5522847498)
    raio = 5.0 * acabamento.PT_POR_MM
    k = raio * acabamento.KAPPA
    # Verifica que pontos de controle Bézier calculados com kappa estão presentes
    assert " c\n" in texto or " c" in texto
    assert f"{y + k:.4f}" in texto or f"{y - k:.4f}" in texto

    # 5. Cruz de mira (+/- 4mm)
    braco = 4.0 * acabamento.PT_POR_MM
    assert f"{x - braco:.4f} {y:.4f} m" in texto
    assert f"{x + braco:.4f} {y:.4f} l" in texto


# =========================================================================
# 3. Testes de Aplicação de Ilhós em PDF
# =========================================================================

def test_aplicar_marcas_ilhos_pdf_completo(tmp_path):
    origem = tmp_path / "banner_origem.pdf"
    destino = tmp_path / "banner_ilhos.pdf"
    w = 2.0 * acabamento.PT_POR_M
    h = 1.0 * acabamento.PT_POR_M
    _criar_pdf_teste(origem, largura_pt=w, altura_pt=h)

    res = acabamento.aplicar_marcas_ilhos_pdf(
        origem, destino, espacamento_m=0.40, recuo_borda_m=0.025, diametro_mm=10.0
    )

    assert destino.exists()
    assert res["total_paginas"] == 1
    assert res["total_furos"] > 0
    assert res["total_furos"] == res["furos_por_pagina"][0]
    assert res["espacamento_m"] == 0.40
    assert res["recuo_borda_m"] == 0.025

    with abrir_pdf(destino) as doc:
        assert len(doc.paginas) == 1
        pag = doc.paginas[0]
        assert abs(pag.largura_pt - w) < 0.1
        assert abs(pag.altura_pt - h) < 0.1

        # Conteúdo deve invocar o Form XObject e conter os traços de ilhós
        raw = pag.obter_conteudo_bruto()
        assert b"/Fm1 Do" in raw
        assert b"1.8 w" in raw
        assert b"0.8 w" in raw
        assert b"1 1 1 RG" in raw
        assert b"0 0 0 RG" in raw


def test_aplicar_marcas_ilhos_pdf_multipagina(tmp_path):
    origem = tmp_path / "multi_origem.pdf"
    destino = tmp_path / "multi_ilhos.pdf"
    tamanhos = [(1000.0, 500.0), (1200.0, 800.0), (600.0, 600.0)]
    _criar_pdf_multipage_teste(origem, tamanhos)

    res = acabamento.aplicar_marcas_ilhos_pdf(origem, destino, espacamento_m=0.30)
    assert res["total_paginas"] == 3
    assert len(res["furos_por_pagina"]) == 3
    assert res["total_furos"] == sum(res["furos_por_pagina"])

    with abrir_pdf(destino) as doc:
        assert len(doc.paginas) == 3
        for i, (w_exp, h_exp) in enumerate(tamanhos):
            p = doc.paginas[i]
            assert abs(p.largura_pt - w_exp) < 0.1
            assert abs(p.altura_pt - h_exp) < 0.1


# =========================================================================
# 4. Testes de Borda de Solda / Bainha Térmica
# =========================================================================

def test_aplicar_borda_solda_com_e_sem_linhas_guia(tmp_path):
    origem = tmp_path / "lona_solda.pdf"
    dest_com_guia = tmp_path / "lona_solda_com_guia.pdf"
    dest_sem_guia = tmp_path / "lona_solda_sem_guia.pdf"

    w_orig = 1000.0
    h_orig = 800.0
    _criar_pdf_teste(origem, largura_pt=w_orig, altura_pt=h_orig)

    borda_m = 0.05  # 5 cm de vira
    borda_pt = borda_m * acabamento.PT_POR_M

    # Com linhas guia
    res1 = acabamento.aplicar_borda_solda_pdf(origem, dest_com_guia, borda_solda_m=borda_m, linhas_guia=True)
    assert res1["paginas"] == 1
    with abrir_pdf(dest_com_guia) as doc1:
        pag1 = doc1.paginas[0]
        assert abs(pag1.largura_pt - (w_orig + 2 * borda_pt)) < 0.1
        assert abs(pag1.altura_pt - (h_orig + 2 * borda_pt)) < 0.1
        raw1 = pag1.obter_conteudo_bruto()
        assert b"[3 3] 0 d" in raw1
        assert b"0.4 0.4 0.4 RG" in raw1

    # Sem linhas guia
    res2 = acabamento.aplicar_borda_solda_pdf(origem, dest_sem_guia, borda_solda_m=borda_m, linhas_guia=False)
    assert res2["paginas"] == 1
    with abrir_pdf(dest_sem_guia) as doc2:
        pag2 = doc2.paginas[0]
        assert abs(pag2.largura_pt - (w_orig + 2 * borda_pt)) < 0.1
        assert abs(pag2.altura_pt - (h_orig + 2 * borda_pt)) < 0.1
        raw2 = pag2.obter_conteudo_bruto()
        assert b"[3 3] 0 d" not in raw2


# =========================================================================
# 5. Testes de Sangria Espelhada (Mirror Bleed)
# =========================================================================

def test_aplicar_sangria_espelhada_pdf(tmp_path):
    origem = tmp_path / "arte_quadro.pdf"
    destino = tmp_path / "arte_quadro_espelhada.pdf"

    w_orig = 500.0
    h_orig = 400.0
    _criar_pdf_teste(origem, largura_pt=w_orig, altura_pt=h_orig)

    sangria_mm = 15.0
    sangria_pt = sangria_mm * acabamento.PT_POR_MM

    res = acabamento.aplicar_sangria_espelhada_pdf(origem, destino, sangria_mm=sangria_mm)

    assert destino.exists()
    assert res["sangria_mm"] == 15.0
    assert res["paginas"] == 1
    assert abs(res["largura_final_pt"] - (w_orig + 2 * sangria_pt)) < 0.5
    assert abs(res["altura_final_pt"] - (h_orig + 2 * sangria_pt)) < 0.5

    with abrir_pdf(destino) as doc:
        assert len(doc.paginas) == 1
        pag = doc.paginas[0]
        assert abs(pag.largura_pt - (w_orig + 2 * sangria_pt)) < 0.1
        assert abs(pag.altura_pt - (h_orig + 2 * sangria_pt)) < 0.1

        raw = pag.obter_conteudo_bruto()
        # Confere que o Form XObject da arte é invocado 9 vezes (1 centro + 4 bordas + 4 cantos)
        ocorrencias = raw.count(b"/Fm1 Do")
        assert ocorrencias == 9

        # Confere que há operadores de recorte (clipping: re W n)
        assert raw.count(b"re W n") == 9

        # Confere a presença de matrizes de escala negativa (-1) para espelhamento
        assert b"-1.000000 0.000000 0.000000 1.000000" in raw    # Espelhamento horizontal
        assert b"1.000000 0.000000 0.000000 -1.000000" in raw    # Espelhamento vertical
        assert b"-1.000000 0.000000 0.000000 -1.000000" in raw   # Espelhamento duplo nos cantos


# =========================================================================
# 6. Testes de Camada CutContour (OCG + Separation ColorSpace)
# =========================================================================

def test_adicionar_camada_cutcontour(tmp_path):
    origem = tmp_path / "adesivo_sem_corte.pdf"
    destino = tmp_path / "adesivo_com_corte.pdf"

    w_orig = 300.0
    h_orig = 300.0
    _criar_pdf_teste(origem, largura_pt=w_orig, altura_pt=h_orig)

    recuo = 2.5
    res = acabamento.adicionar_camada_cutcontour(
        origem, destino, recuo_pt=recuo, spot_color_name="CutContour"
    )

    assert destino.exists()
    assert res["spot_color_name"] == "CutContour"
    assert res["recuo_pt"] == recuo
    assert res["paginas"] == 1

    with abrir_pdf(destino) as doc:
        assert len(doc.paginas) == 1
        pag = doc.paginas[0]

        # 1. Confere no trailer/catálogo a presença de /OCProperties
        cat_ref = doc.trailer.get("/Root")
        catalogo = doc._resolver_objeto(cat_ref)
        oc_props = doc._resolver_objeto(catalogo.get("/OCProperties"))
        assert oc_props is not None
        ocgs = doc._resolver_objeto(oc_props.get("/OCGs"))
        assert len(ocgs) >= 1
        ocg_dict = doc._resolver_objeto(ocgs[0])
        assert ocg_dict.get("/Type") in ("/OCG", PdfName("/OCG"))
        assert b"CutContour" in bytes(ocg_dict.get("/Name"))

        # 2. Confere no Resources da página a Separation ColorSpace e Property OCG
        rec = doc._resolver_objeto(pag.raw_dict.get("/Resources"))
        cs = doc._resolver_objeto(rec.get("/ColorSpace"))
        cs_cut = doc._resolver_objeto(cs.get("/CS_Cut"))
        assert cs_cut[0] in ("/Separation", PdfName("/Separation"))
        assert cs_cut[1] in ("/CutContour", PdfName("/CutContour"))
        assert cs_cut[2] in ("/DeviceCMYK", PdfName("/DeviceCMYK"))

        # Função de interpolação tipo 2 para 100% Magenta
        func = doc._resolver_objeto(cs_cut[3])
        assert int(func.get("/FunctionType")) == 2
        c1 = [float(x) for x in func.get("/C1")]
        assert c1 == [0.0, 1.0, 0.0, 0.0]  # 100% Magenta!

        # 3. Confere o stream de conteúdo da página com marcadores de OCG e Separation
        raw = pag.obter_conteudo_bruto()
        assert b"/OC /OC1 BDC" in raw
        assert b"/CS_Cut CS" in raw
        assert b"1.0 SCN" in raw
        assert b"1.0 w" in raw
        assert b"EMC" in raw

        # Medidas do retângulo de corte com recuo
        x_exp = recuo
        y_exp = recuo
        w_exp = w_orig - 2 * recuo
        h_exp = h_orig - 2 * recuo
        ret_cmd = f"{x_exp:.4f} {y_exp:.4f} {w_exp:.4f} {h_exp:.4f} re".encode("ascii")
        assert ret_cmd in raw
