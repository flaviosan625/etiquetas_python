"""
tests/test_motor_pdf_montador.py — Testes unitários do escritor PDF e do motor de imposição por Form XObject.
"""

import hashlib
import io
import pathlib
import time
import zlib
import pytest

from motor_pdf import (
    MontadorBobina,
    PecaMontagem,
    PdfReader,
    PdfWriter,
    abrir_pdf,
)
from motor_pdf.leitor import PT_POR_M, PT_POR_MM
from motor_pdf.sintaxe import PdfName, PdfRef, PdfStream, PdfString


def criar_pdf_teste_com_imagem(caminho: pathlib.Path, largura_pt: float, altura_pt: float, payload_imagem: bytes) -> bytes:
    """Gera um PDF fonte contendo uma imagem arbitrária com payload conhecido."""
    writer = PdfWriter()

    # Stream de imagem DCT/raw
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

    # Desenho da imagem cobrindo a página
    cmds = f"""
    q
    {largura_pt:.2f} 0 0 {altura_pt:.2f} 0 0 cm
    /Im1 Do
    Q
    """.encode("ascii")

    recursos = {
        PdfName("/XObject"): {
            PdfName("/Im1"): PdfRef(img_id, 0),
        }
    }

    writer.adicionar_pagina(largura_pt, altura_pt, recursos, cmds)
    return writer.salvar(caminho)


def test_pdf_writer_basico(tmp_path):
    saida = tmp_path / "basico.pdf"
    writer = PdfWriter(versao="1.6")

    # Página simples de 100x100 pt
    recursos = {}
    conteudo = b"q 0 0 100 100 re f Q\n"
    writer.adicionar_pagina(100.0, 100.0, recursos, conteudo)
    writer.salvar(saida)

    assert saida.is_file()
    dados = saida.read_bytes()
    assert dados.startswith(b"%PDF-1.6")
    assert b"%%EOF" in dados

    # Valida abrindo de volta com o nosso PdfReader nativo
    with abrir_pdf(saida) as leitor:
        assert len(leitor.paginas) == 1
        p = leitor.paginas[0]
        assert p.mediabox.width == pytest.approx(100.0)
        assert p.mediabox.height == pytest.approx(100.0)


def test_montador_bobina_duas_pecas_e_rotacao(tmp_path):
    arquivo_arte = tmp_path / "arte_50x100.pdf"
    payload_img = b"PAYLOAD_RAW_IMAGEM_GRAFICA_1234567890" * 50
    criar_pdf_teste_com_imagem(arquivo_arte, 50.0 * PT_POR_MM, 100.0 * PT_POR_MM, payload_img)

    saida_montagem = tmp_path / "montagem_bobina.pdf"
    montador = MontadorBobina(
        largura_m=1.60,
        altura_m=2.00,
        titulo="LOTE 001 - CLIENTE TESTE - SWJ320",
    )

    # Peça 1: reta (0 graus)
    montador.adicionar_peca(
        PecaMontagem(
            arquivo=arquivo_arte,
            x_m=0.10,
            y_m=0.20,
            largura_m=0.50,
            altura_m=1.00,
            girada=False,
            rotulo="1UN LONA 50x100cm CLIENTE_PECA1",
        )
    )

    # Peça 2: girada 90 graus
    montador.adicionar_peca(
        PecaMontagem(
            arquivo=arquivo_arte,
            x_m=0.70,
            y_m=0.20,
            largura_m=1.00,
            altura_m=0.50,
            girada=True,
            rotulo="1UN LONA 100x50cm CLIENTE_PECA2",
        )
    )

    montador.salvar(saida_montagem)
    assert saida_montagem.is_file()

    # Valida estrutura da folha montada
    with abrir_pdf(saida_montagem) as doc_montado:
        assert len(doc_montado.paginas) == 1
        p = doc_montado.paginas[0]
        assert p.mediabox.largura_m == pytest.approx(1.60, abs=1e-3)
        assert p.mediabox.altura_m == pytest.approx(2.00, abs=1e-3)

        # Deve conter recursos de Form XObjects (/Fm1)
        rec = doc_montado._resolver_objeto(p.raw_dict.get("/Resources", {}))
        xobjs = doc_montado._resolver_objeto(rec.get("/XObject", {}))
        assert len(xobjs) >= 1  # Form XObject das peças


def test_montador_preservacao_cega_de_bytes(tmp_path):
    """Garante que a imagem original entra na folha montada com os exatos mesmos bytes (SHA1)."""
    payload_original = b"CONTEUDO_BINARIO_IMAGEM_RGB_ALTA_DEFINICAO_DE_TESTE_ISO32000" * 100
    sha_esperado = hashlib.sha1(payload_original).hexdigest()

    arquivo_origem = tmp_path / "origem_com_imagem.pdf"
    criar_pdf_teste_com_imagem(arquivo_origem, 200.0, 300.0, payload_original)

    saida_montada = tmp_path / "montada_bytes.pdf"
    montador = MontadorBobina(largura_m=1.00, altura_m=1.00)
    montador.adicionar_peca(
        PecaMontagem(
            arquivo=arquivo_origem,
            x_m=0.10,
            y_m=0.10,
            largura_m=0.40,
            altura_m=0.60,
        )
    )
    montador.salvar(saida_montada)

    # Inspeciona o arquivo montado: o payload original deve estar intacto
    dados_montados = saida_montada.read_bytes()
    assert payload_original in dados_montados, "O payload bruto da imagem deve ser preservado byte a byte!"


def test_montador_deduplicacao_de_formas(tmp_path):
    """Peças iguais repetidas na folha devem compartilhar o mesmo /Form XObject (sem duplicar bytes)."""
    arquivo_arte = tmp_path / "etiqueta_repetida.pdf"
    payload = b"IMG_REPETIDA_" * 200
    criar_pdf_teste_com_imagem(arquivo_arte, 100.0, 100.0, payload)

    montador = MontadorBobina(largura_m=1.20, altura_m=1.00)

    # Adiciona a MESMA peça 10 vezes na folha
    for i in range(10):
        montador.adicionar_peca(
            PecaMontagem(
                arquivo=arquivo_arte,
                x_m=0.05 * i,
                y_m=0.05 * i,
                largura_m=0.10,
                altura_m=0.10,
                rotulo=f"ETIQUETA COPIA {i+1}",
            )
        )

    saida = tmp_path / "folha_10x.pdf"
    montador.salvar(saida)

    with abrir_pdf(saida) as doc:
        p = doc.paginas[0]
        rec = doc._resolver_objeto(p.raw_dict.get("/Resources", {}))
        xobjs = doc._resolver_objeto(rec.get("/XObject", {}))
        # Deve haver apenas 1 Form XObject registrado (/Fm1), compartilhado pelas 10 chamadas
        assert len(xobjs) == 1, "Peças repetidas devem ser deduplicadas em um único /Form!"


def test_montador_performance_30_pecas_em_5_metros(tmp_path):
    """Critério de aceite 3: folha de 5 metros com 30 peças deve ser gerada em < 1 segundo."""
    arquivo_arte = tmp_path / "peca_benchmark.pdf"
    criar_pdf_teste_com_imagem(arquivo_arte, 200.0, 300.0, b"BENCHMARK_BYTES_RAW" * 50)

    montador = MontadorBobina(largura_m=3.20, altura_m=5.00, titulo="PRODUCAO EM MASSA 30 PECAS")
    for i in range(30):
        montador.adicionar_peca(
            PecaMontagem(
                arquivo=arquivo_arte,
                x_m=(i % 3) * 1.0,
                y_m=(i // 3) * 0.45,
                largura_m=0.90,
                altura_m=0.40,
                girada=(i % 2 == 1),
                rotulo=f"PECA {i+1:02d} LOTE AUTOMATICO",
            )
        )

    saida_bench = tmp_path / "folha_benchmark.pdf"

    t0 = time.perf_counter()
    montador.salvar(saida_bench)
    t1 = time.perf_counter()
    tempo_ms = (t1 - t0) * 1000

    assert saida_bench.is_file()
    assert tempo_ms < 1000.0, f"Tempo de geração ({tempo_ms:.1f} ms) excedeu o teto de 1000 ms!"
