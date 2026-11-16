"""
tests/test_tiling.py — Testes unitários do Módulo de Acabamento — Painelamento Automático de Grandes Formatos (Tiling).

Valida:
  1. Cálculo geométrico exato: arte de 10.00 m com sobreposição de 25 mm recompõe 10.00 m.
  2. Fatiamento em orientações vertical e horizontal.
  3. Geração de arquivos PDF autônomos para cada faixa via motor_pdf (ISO 32000-1).
  4. Preservação cega de bytes de streams e encapsulamento em /Subtype /Form XObject.
  5. Cruzetas finas de solda no eixo ('0 0 0 RG 0.5 w') e identificação técnica no rodapé.
  6. Ausência estrita de dependências externas (pymupdf / fitz).
"""

from __future__ import annotations

import ast
import os
from pathlib import Path
import pytest
import zlib

from motor_pdf import PdfWriter, abrir_pdf
from motor_pdf.leitor import PT_POR_M, PT_POR_MM
from motor_pdf.sintaxe import PdfName, PdfRef, PdfStream, PdfString
from tiling import FaixaInfo, PlanoPainelamento, calcular_painelamento, gerar_faixas_pdf


def _criar_pdf_arte_grande_formato(
    caminho: Path,
    largura_m: float,
    altura_m: float,
    payload_imagem: bytes = b"PAYLOAD_VETORIAL_GRANDE_FORMATO_12345",
) -> Path:
    """Cria um PDF de grande formato de teste com dimensões métricas e objeto embutido."""
    largura_pt = largura_m * PT_POR_M
    altura_pt = altura_m * PT_POR_M

    writer = PdfWriter(versao="1.6")

    # Objeto de imagem /XObject simulando arte de alta resolução
    img_id = writer.alocar_id()
    img_stream = PdfStream(
        {
            PdfName("/Type"): PdfName("/XObject"),
            PdfName("/Subtype"): PdfName("/Image"),
            PdfName("/Width"): 100,
            PdfName("/Height"): 100,
            PdfName("/ColorSpace"): PdfName("/DeviceRGB"),
            PdfName("/BitsPerComponent"): 8,
            PdfName("/Length"): len(payload_imagem),
        },
        payload_imagem,
    )
    writer.objetos[img_id] = img_stream

    # Comandos vetoriais de desenho
    cmds = f"""
    q
    0.1 0.3 0.8 rg
    0 0 {largura_pt:.2f} {altura_pt:.2f} re f
    q
    {largura_pt:.2f} 0 0 {altura_pt:.2f} 0 0 cm
    /Im1 Do
    Q
    Q
    """.encode("ascii")

    recursos = {
        PdfName("/XObject"): {
            PdfName("/Im1"): PdfRef(img_id, 0),
        }
    }

    writer.adicionar_pagina(largura_pt, altura_pt, recursos, cmds)
    writer.salvar(caminho)
    return caminho


def test_calculo_geometrico_recomposicao_10m():
    """
    Testa o cálculo geométrico: uma arte de 10.00 m fatiada com sobreposição de 25 mm
    deve recompor os 10.00 m exatos ao subtrair os overlaps de solda.
    """
    largura_total = 10.00  # 10 metros
    altura_total = 3.00   # 3 metros
    largura_maxima = 3.20  # máquina de 3.20 m
    sobreposicao_mm = 25.0  # 25 mm = 0.025 m
    sobreposicao_m = 0.025

    plano = calcular_painelamento(
        largura_m=largura_total,
        altura_m=altura_total,
        largura_maxima_faixa_m=largura_maxima,
        sobreposicao_solda_mm=sobreposicao_mm,
        orientacao="vertical",
    )

    # 1. Validação estrutural do plano
    assert isinstance(plano, PlanoPainelamento)
    assert plano.largura_total_m == pytest.approx(10.00)
    assert plano.altura_total_m == pytest.approx(3.00)
    assert plano.orientacao == "vertical"
    assert plano.sobreposicao_solda_mm == pytest.approx(25.0)

    # 10.00 / (3.20 - 0.025) = 10.00 / 3.175 = 3.1496 -> ceil = 4 faixas
    assert plano.numero_faixas == 4
    assert len(plano.faixas) == 4

    # 2. Validação individual de cada faixa
    for idx, faixa in enumerate(plano.faixas, start=1):
        assert faixa.indice == idx
        assert faixa.largura_com_sobreposicao_m <= largura_maxima, (
            f"Faixa {idx} ({faixa.largura_com_sobreposicao_m:.4f} m) excedeu a largura da máquina ({largura_maxima} m)"
        )
        assert faixa.altura_m == pytest.approx(3.00)
        # Cada faixa útil individual = largura com sobreposição - suas sobreposições
        largura_recomposta_faixa = faixa.largura_com_sobreposicao_m - (
            faixa.sobreposicao_esquerda_m + faixa.sobreposicao_direita_m
        )
        assert largura_recomposta_faixa == pytest.approx(faixa.largura_util_m)

    # Faixa 1: início da arte, overlap apenas à direita
    f1 = plano.faixas[0]
    assert f1.x0_m == pytest.approx(0.0)
    assert f1.sobreposicao_esquerda_m == pytest.approx(0.0)
    assert f1.sobreposicao_direita_m == pytest.approx(sobreposicao_m)
    assert f1.largura_util_m == pytest.approx(2.50)
    assert f1.largura_com_sobreposicao_m == pytest.approx(2.525)

    # Faixas 2 e 3: intermediárias, overlap à direita para a próxima faixa
    for f in (plano.faixas[1], plano.faixas[2]):
        assert f.sobreposicao_esquerda_m == pytest.approx(0.0)
        assert f.sobreposicao_direita_m == pytest.approx(sobreposicao_m)
        assert f.largura_util_m == pytest.approx(2.50)
        assert f.largura_com_sobreposicao_m == pytest.approx(2.525)

    # Faixa 4: última faixa, fecha a montagem sem sobreposição à direita
    f4 = plano.faixas[3]
    assert f4.sobreposicao_esquerda_m == pytest.approx(0.0)
    assert f4.sobreposicao_direita_m == pytest.approx(0.0)
    assert f4.largura_util_m == pytest.approx(2.50)
    assert f4.largura_com_sobreposicao_m == pytest.approx(2.50)

    # 3. RECOMPOSIÇÃO GEOMÉTRICA EXATA:
    # A soma das larguras com sobreposição menos a soma de todos os overlaps de solda
    # DEVE resultar em EXATAMENTE 10.00 m!
    total_larguras_com_sobreposicao = sum(f.largura_com_sobreposicao_m for f in plano.faixas)
    total_overlaps_solda = sum(
        f.sobreposicao_esquerda_m + f.sobreposicao_direita_m for f in plano.faixas
    )
    largura_recomposta = total_larguras_com_sobreposicao - total_overlaps_solda

    assert total_overlaps_solda == pytest.approx(3 * sobreposicao_m)  # 3 emendas x 25 mm = 75 mm
    assert largura_recomposta == pytest.approx(10.00, abs=1e-6)

    # Soma das larguras úteis nominais também deve somar 10.00 m
    assert sum(f.largura_util_m for f in plano.faixas) == pytest.approx(10.00, abs=1e-6)


def test_fatiamento_horizontal_e_recomposicao():
    """Testa o fatiamento na orientação horizontal (cortes horizontais ao longo da altura)."""
    largura_total = 2.40
    altura_total = 10.00  # Arte alta de 10 metros
    largura_maxima = 3.20  # máquina de 3.20 m
    sobreposicao_mm = 25.0
    sobreposicao_m = 0.025

    plano = calcular_painelamento(
        largura_m=largura_total,
        altura_m=altura_total,
        largura_maxima_faixa_m=largura_maxima,
        sobreposicao_solda_mm=sobreposicao_mm,
        orientacao="horizontal",
    )

    assert plano.numero_faixas == 4
    assert len(plano.faixas) == 4
    assert plano.orientacao == "horizontal"

    for idx, faixa in enumerate(plano.faixas, start=1):
        assert faixa.indice == idx
        # Na horizontal, a altura física com sobreposição deve caber na máquina
        assert faixa.altura_m <= largura_maxima
        assert faixa.largura_util_m == pytest.approx(largura_total)
        assert faixa.largura_com_sobreposicao_m == pytest.approx(largura_total)

    # Recomposição da altura de 10.00 m descontando os overlaps superiores
    total_altura_com_sobreposicao = sum(f.altura_m for f in plano.faixas)
    total_overlaps = sum(
        f.sobreposicao_inferior_m + f.sobreposicao_superior_m for f in plano.faixas
    )
    altura_recomposta = total_altura_com_sobreposicao - total_overlaps

    assert total_overlaps == pytest.approx(3 * sobreposicao_m)
    assert altura_recomposta == pytest.approx(10.00, abs=1e-6)
    assert sum(f.altura_util_m for f in plano.faixas) == pytest.approx(10.00, abs=1e-6)


def test_painelamento_faixa_unica_sem_fatiamento():
    """Arte que cabe diretamente na largura útil da máquina não deve ser dividida."""
    plano = calcular_painelamento(
        largura_m=2.00,
        altura_m=1.00,
        largura_maxima_faixa_m=3.20,
        sobreposicao_solda_mm=25.0,
    )

    assert plano.numero_faixas == 1
    assert len(plano.faixas) == 1
    f = plano.faixas[0]
    assert f.largura_util_m == pytest.approx(2.00)
    assert f.largura_com_sobreposicao_m == pytest.approx(2.00)
    assert f.altura_m == pytest.approx(1.00)
    assert f.sobreposicao_esquerda_m == 0.0
    assert f.sobreposicao_direita_m == 0.0


def test_painelamento_validacoes_entradas():
    """Valida rejeição de parâmetros inválidos com mensagens claras."""
    with pytest.raises(ValueError, match="dimensões"):
        calcular_painelamento(0.0, 3.0, 3.20)

    with pytest.raises(ValueError, match="dimensões"):
        calcular_painelamento(10.0, -1.0, 3.20)

    with pytest.raises(ValueError, match="largura máxima"):
        calcular_painelamento(10.0, 3.0, 0.0)

    with pytest.raises(ValueError, match="negativa"):
        calcular_painelamento(10.0, 3.0, 3.20, sobreposicao_solda_mm=-5.0)

    with pytest.raises(ValueError, match="Orientação inválida"):
        calcular_painelamento(10.0, 3.0, 3.20, orientacao="diagonal")

    with pytest.raises(ValueError, match="maior ou igual"):
        calcular_painelamento(10.0, 3.0, 1.00, sobreposicao_solda_mm=1000.0)


def test_painelamento_com_bainha_extra():
    """Testa aplicação de margem extra de reforço/bainha perimetral."""
    bainha_mm = 50.0  # 50 mm = 0.05 m
    bainha_m = 0.05

    plano = calcular_painelamento(
        largura_m=6.00,
        altura_m=2.00,
        largura_maxima_faixa_m=3.20,
        sobreposicao_solda_mm=25.0,
        bainha_extra_mm=bainha_mm,
    )

    assert plano.bainha_extra_mm == 50.0
    for f in plano.faixas:
        # A altura de todas as faixas recebe bainha no topo e na base (2x)
        assert f.altura_m == pytest.approx(2.00 + 2 * bainha_m)


def test_gerar_faixas_pdf_completo(tmp_path):
    """
    Testa geração completa de arquivos PDF para as faixas:
      - Arquivos independentes nomeados corretamente.
      - Importação da arte original como /Subtype /Form XObject.
      - Dimensões do MediaBox correspondentes ao plano.
      - Cruzetas de alinhamento com '0 0 0 RG 0.5 w'.
      - Identificação técnica no rodapé com overlap e sentido de montagem.
    """
    arquivo_origem = tmp_path / "banner_10m.pdf"
    pasta_saida = tmp_path / "faixas_saida"
    _criar_pdf_arte_grande_formato(arquivo_origem, largura_m=10.00, altura_m=3.00)

    arquivos = gerar_faixas_pdf(
        caminho_arquivo=arquivo_origem,
        pasta_saida=pasta_saida,
        largura_maxima_faixa_m=3.20,
        sobreposicao_solda_mm=25.0,
        orientacao="vertical",
        prefixo_nome="PAINEL_OUTDOOR",
    )

    # 1. Confere quantidade e padrão de nomes
    assert len(arquivos) == 4
    nomes_esperados = [
        "PAINEL_OUTDOOR_FAIXA_01_DE_04.pdf",
        "PAINEL_OUTDOOR_FAIXA_02_DE_04.pdf",
        "PAINEL_OUTDOOR_FAIXA_03_DE_04.pdf",
        "PAINEL_OUTDOOR_FAIXA_04_DE_04.pdf",
    ]
    for arq, nome_esp in zip(arquivos, nomes_esperados):
        assert arq.is_file()
        assert arq.name == nome_esp

    # 2. Inspeciona cada PDF gerado utilizando o motor_pdf nativo
    for idx, arq in enumerate(arquivos, start=1):
        with abrir_pdf(arq) as leitor:
            assert len(leitor.paginas) == 1
            pag = leitor.paginas[0]

            # Dimensões exatas da página
            largura_esperada_m = 2.525 if idx < 4 else 2.500
            assert pag.largura_m == pytest.approx(largura_esperada_m, abs=1e-3)
            assert pag.altura_m == pytest.approx(3.00, abs=1e-3)

            # Inspeciona recursos: deve conter o Form XObject (/Fm1)
            recursos = leitor._resolver_objeto(pag.raw_dict.get("/Resources", {}))
            assert "/XObject" in recursos
            xobjects = leitor._resolver_objeto(recursos["/XObject"])
            assert "/Fm1" in xobjects

            # Inspeciona o Form XObject
            form_obj = leitor._resolver_objeto(xobjects["/Fm1"])
            assert isinstance(form_obj, PdfStream)
            assert form_obj.header.get(PdfName("/Subtype")) == PdfName("/Form")
            assert form_obj.header.get(PdfName("/Type")) == PdfName("/XObject")

            # Inspeciona os comandos da página
            conteudo_bytes = pag.obter_conteudo_bruto()

            # Presença da chamada do Form
            assert b"/Fm1 Do" in conteudo_bytes

            # Cruzetas de solda com traçado 0 0 0 RG 0.5 w nas faixas com overlap
            if idx < 4:
                assert b"0 0 0 RG 0.5 w" in conteudo_bytes

            # Identificação técnica no rodapé
            assert b"FAIXA" in conteudo_bytes
            assert b"DE 04" in conteudo_bytes
            assert b"OVERLAP 25MM" in conteudo_bytes
            assert b"[>>> SENTIDO DE MONTAGEM]" in conteudo_bytes


def test_gerar_faixas_pdf_preservacao_cega_bytes(tmp_path):
    """
    Garante o princípio de 'preservação cega de bytes':
    o payload binário da imagem/arte original deve constar byte a byte
    nos arquivos PDF fatiados sem recompressão nem perda de resolução.
    """
    payload_original = b"BYTES_BRUTOS_PRESERVADOS_ALTA_DEFINICAO_GRAFICA_" * 50
    arquivo_origem = tmp_path / "arte_com_payload.pdf"
    pasta_saida = tmp_path / "saida_bytes"
    _criar_pdf_arte_grande_formato(
        arquivo_origem, largura_m=4.00, altura_m=2.00, payload_imagem=payload_original
    )

    arquivos = gerar_faixas_pdf(
        caminho_arquivo=arquivo_origem,
        pasta_saida=pasta_saida,
        largura_maxima_faixa_m=2.50,
        sobreposicao_solda_mm=25.0,
    )

    assert len(arquivos) == 2
    for arq in arquivos:
        dados_pdf = arq.read_bytes()
        # O payload bruto da imagem deve existir intacto no PDF gerado
        assert payload_original in dados_pdf, (
            "Falha na preservação cega de bytes: o payload original não foi encontrado intacto no PDF da faixa!"
        )


def test_gerar_faixas_pdf_horizontal(tmp_path):
    """Testa geração física dos arquivos PDF no modo de painelamento horizontal."""
    arquivo_origem = tmp_path / "arte_horizontal_8m.pdf"
    pasta_saida = tmp_path / "saida_horizontal"
    _criar_pdf_arte_grande_formato(arquivo_origem, largura_m=2.00, altura_m=8.00)

    arquivos = gerar_faixas_pdf(
        caminho_arquivo=arquivo_origem,
        pasta_saida=pasta_saida,
        largura_maxima_faixa_m=3.00,
        sobreposicao_solda_mm=25.0,
        orientacao="horizontal",
        prefixo_nome="FRONT_VERTICAL",
    )

    assert len(arquivos) == 3
    for arq in arquivos:
        with abrir_pdf(arq) as leitor:
            assert len(leitor.paginas) == 1
            pag = leitor.paginas[0]
            assert pag.largura_m == pytest.approx(2.00, abs=1e-3)
            # Altura com sobreposição cabe na máquina
            assert pag.altura_m <= 3.00


def test_tiling_sem_dependencia_pymupdf():
    """Garante que o módulo tiling.py NÃO importa fitz nem pymupdf (100% motor_pdf nativo)."""
    caminho_tiling = Path(__file__).resolve().parent.parent / "tiling.py"
    assert caminho_tiling.is_file()

    codigo = caminho_tiling.read_text(encoding="utf-8")
    arvore = ast.parse(codigo)

    modulos_importados = set()
    for nodo in ast.walk(arvore):
        if isinstance(nodo, ast.Import):
            for alias in nodo.names:
                modulos_importados.add(alias.name.split(".")[0])
        elif isinstance(nodo, ast.ImportFrom):
            if nodo.module:
                modulos_importados.add(nodo.module.split(".")[0])

    assert "pymupdf" not in modulos_importados, "tiling.py não deve importar pymupdf!"
    assert "fitz" not in modulos_importados, "tiling.py não deve importar fitz!"
    assert "motor_pdf" in modulos_importados, "tiling.py deve usar motor_pdf nativo!"
