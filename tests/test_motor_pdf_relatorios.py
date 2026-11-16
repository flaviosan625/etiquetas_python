"""
tests/test_motor_pdf_relatorios.py — Testes unitários do gerador nativo de relatórios A4 em PDF (ISO 32000-1).
"""

import io
import pathlib
import pytest
from PIL import Image

from motor_pdf import RelatorioA4Builder, abrir_pdf


def test_relatorio_a4_pagina_unica_e_elementos(tmp_path):
    saida = tmp_path / "relatorio_teste.pdf"
    builder = RelatorioA4Builder()
    builder.nova_pagina()

    # Desenho de cabeçalho
    builder.desenhar_retangulo(36.0, 36.0, 523.28, 60.0, cor_fundo=(0.95, 0.95, 0.95), cor_traco=(0.8, 0.8, 0.8))
    builder.desenhar_texto(46.0, 55.0, "ORDEM DE SERVICO TESTE", tamanho=14.0, negrito=True, cor=(0.1, 0.2, 0.4))
    builder.desenhar_texto(46.0, 75.0, "Cliente: UNY COMUNICACAO VISUAL", tamanho=9.0, cor=(0.3, 0.3, 0.3))

    # Linha divisória
    builder.desenhar_linha(36.0, 110.0, 559.28, 110.0, cor=(0.7, 0.75, 0.8), espessura=0.8)

    # Inserção de imagem de teste
    img = Image.new("RGB", (100, 50), color=(200, 50, 50))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    dados_img = buf.getvalue()

    builder.desenhar_imagem(46.0, 120.0, 80.0, 40.0, dados_img)

    builder.salvar(saida)
    assert saida.is_file()

    # Validação com PdfReader nativo
    with abrir_pdf(saida) as doc:
        assert len(doc.paginas) == 1
        p = doc.paginas[0]
        assert p.mediabox.width == pytest.approx(595.28, abs=0.1)
        assert p.mediabox.height == pytest.approx(841.89, abs=0.1)


def test_relatorio_a4_paginacao_automatica_multiplas_paginas(tmp_path):
    saida = tmp_path / "relatorio_multipagina.pdf"
    builder = RelatorioA4Builder()

    # Página 1
    builder.nova_pagina()
    builder.desenhar_texto(36.0, 50.0, "CONTEUDO DA PAGINA 1", tamanho=12.0)

    # Página 2
    builder.nova_pagina()
    builder.desenhar_texto(36.0, 50.0, "CONTEUDO DA PAGINA 2", tamanho=12.0)

    # Página 3
    builder.nova_pagina()
    builder.desenhar_texto(36.0, 50.0, "CONTEUDO DA PAGINA 3", tamanho=12.0)

    builder.salvar(saida)

    with abrir_pdf(saida) as doc:
        assert len(doc.paginas) == 3
        for idx, pag in enumerate(doc.paginas):
            stream_conteudo = pag.obter_conteudo_bruto()
            esperado = f"Pagina {idx + 1} de 3".encode("ascii")
            assert esperado in stream_conteudo, f"Rodapé com paginação não encontrado na página {idx+1}!"


def test_relatorio_a4_truncamento_e_alinhamentos(tmp_path):
    saida = tmp_path / "relatorio_alinhamentos.pdf"
    builder = RelatorioA4Builder()
    builder.nova_pagina()

    # Alinhamento à direita
    builder.desenhar_texto(559.28, 50.0, "TOTAL: R$ 1.500,00", tamanho=10.0, negrito=True, alinhamento="right")

    # Alinhamento centralizado
    builder.desenhar_texto(297.64, 50.0, "RELATORIO CENTRALIZADO", tamanho=10.0, alinhamento="center")

    # Truncamento de texto excessivamente longo
    texto_longo = "NOME DE ARQUIVO MUITO EXTENSO QUE CERTAMENTE ULTRAPASSA A LARGURA DA COLUNA DA TABELA DO RELATORIO " * 5
    builder.desenhar_texto(36.0, 100.0, texto_longo, tamanho=8.0, largura_max=150.0)

    builder.salvar(saida)
    assert saida.is_file()

    with abrir_pdf(saida) as doc:
        stream = doc.paginas[0].obter_conteudo_bruto()
        assert b"TOTAL: R$ 1.500,00" in stream
        assert b"..." in stream  # Reticências do truncamento
