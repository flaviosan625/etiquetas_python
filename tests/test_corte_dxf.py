"""
Testes da extração de linha de corte pro Aspire.

Os PDFs de teste são desenhados aqui mesmo com o PyMuPDF, com as cores
MEDIDAS nos arquivos de corte reais da casa — nada de cor inventada.
"""
import pathlib
import sys

import pymupdf
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from corte_dxf import converter, e_cor_de_corte, escrever_dxf, extrair_contornos

# Cores tiradas dos arquivos reais em 06/09/2026 (ver corte_dxf).
MAGENTA_LOGO = (0.922, 0.229, 0.506)      # 336° — contorno de recorte
MAGENTA_BNDES = (0.93, 0.193, 0.574)      # 329° — o mais distante da faixa
QUASE_PRETO = (0.137, 0.122, 0.125)       # 346° de matiz, mas saturação 0,11
VERMELHO_LETRA = (0.798, 0.125, 0.15)     # 357° — letra caixa
BRANCO = (1.0, 1.0, 1.0)


def _pdf(caminho, desenhos, largura=200, altura=100):
    """Cria um PDF com os desenhos pedidos: (retangulo, cor_do_traco)."""
    doc = pymupdf.open()
    pagina = doc.new_page(width=largura, height=altura)
    for rect, cor in desenhos:
        pagina.draw_rect(pymupdf.Rect(*rect), color=cor, width=1)
    doc.save(caminho)
    doc.close()
    return pathlib.Path(caminho)


# ---------- a regra da cor ----------

def test_reconhece_os_magentas_reais_dos_arquivos_de_corte():
    assert e_cor_de_corte(MAGENTA_LOGO)
    assert e_cor_de_corte(MAGENTA_BNDES)


def test_preto_com_matiz_de_magenta_nao_passa():
    """
    Armadilha real: (0.137, 0.122, 0.125) calcula 346° de matiz, dentro
    da faixa. Só a saturação (0,11) diz que é preto. Sem esse limite, o
    gabarito inteiro viraria linha de corte.
    """
    assert not e_cor_de_corte(QUASE_PRETO)


def test_vermelho_de_letra_caixa_nao_passa():
    """357° — um grau a mais na faixa e as letras entrariam como corte."""
    assert not e_cor_de_corte(VERMELHO_LETRA)


def test_sem_cor_nao_passa():
    assert not e_cor_de_corte(None)
    assert not e_cor_de_corte(())


# ---------- extração ----------

def test_so_o_magenta_vira_contorno(tmp_path):
    pdf = _pdf(tmp_path / "peca.pdf", [
        ((10, 10, 90, 90), MAGENTA_LOGO),
        ((20, 20, 80, 80), QUASE_PRETO),
        ((30, 30, 70, 70), VERMELHO_LETRA),
    ])
    polilinhas, relatorio = extrair_contornos(pdf)
    assert relatorio["de_corte"] == 1
    assert relatorio["descartados"] == 2
    assert len(polilinhas) == 1


def test_medida_sai_em_milimetros_e_com_y_pra_cima(tmp_path):
    """
    O PDF conta em pontos e de cima pra baixo; o DXF em mm e de baixo
    pra cima. Errar isso entrega a peça espelhada na fresa.
    """
    pdf = _pdf(tmp_path / "quadrado.pdf", [((0, 0, 72, 36), MAGENTA_LOGO)], altura=72)
    polilinhas, _ = extrair_contornos(pdf)
    xs = [x for x, _ in polilinhas[0]]
    ys = [y for _, y in polilinhas[0]]
    assert max(xs) - min(xs) == pytest.approx(25.4, abs=0.05)   # 72 pt = 1 pol
    assert max(ys) - min(ys) == pytest.approx(12.7, abs=0.05)   # 36 pt = meia pol
    # o retângulo estava colado no TOPO do PDF, então no DXF fica no alto
    assert max(ys) == pytest.approx(72 * 25.4 / 72, abs=0.05)


# ---------- gravação ----------

def test_dxf_sai_em_r12_na_camada_corte(tmp_path):
    destino = escrever_dxf([[(0, 0), (10, 0), (10, 10), (0, 0)]], tmp_path / "s.dxf")
    texto = destino.read_text(encoding="ascii")
    assert "POLYLINE" in texto and "VERTEX" in texto and "SEQEND" in texto
    assert "LWPOLYLINE" not in texto, "Aspire 8.5 é de 2016 — POLYLINE antigo entra em tudo"
    assert "CORTE" in texto
    assert texto.rstrip().endswith("EOF")
    assert "$INSUNITS" in texto


def test_contorno_que_volta_ao_inicio_e_marcado_como_fechado(tmp_path):
    destino = escrever_dxf([[(0, 0), (10, 0), (10, 10), (0, 0)]], tmp_path / "f.dxf")
    linhas = destino.read_text(encoding="ascii").splitlines()
    # o 70 logo depois do 66/1 é a bandeira de fechado
    i = linhas.index("66")
    assert linhas[i + 3] == "1", "contorno fechado tem que sair fechado, senão a fresa não fecha a peça"
    assert destino.read_text(encoding="ascii").count("VERTEX") == 3, "o ponto repetido não se grava"


# ---------- o fluxo inteiro ----------

def test_gera_dxf_com_mesmo_nome_e_nao_toca_no_pdf(tmp_path):
    pdf = _pdf(tmp_path / "logo balcao.pdf", [((10, 10, 90, 90), MAGENTA_LOGO)])
    antes = pdf.read_bytes()

    relatorio = converter(pdf)

    assert relatorio["dxf"] == str(tmp_path / "logo balcao.dxf")
    assert pathlib.Path(relatorio["dxf"]).exists()
    assert pdf.exists(), "o PDF nunca pode sumir"
    assert pdf.read_bytes() == antes, "o PDF nunca pode ser reescrito"


def test_recusa_quando_nao_ha_magenta_em_vez_de_gerar_dxf_vazio(tmp_path):
    """
    Letra caixa não tem contorno magenta. Gerar um DXF vazio pareceria
    sucesso, iria pra fresa e o erro só apareceria com a chapa na
    máquina — por isso recusa, e diz o porquê.
    """
    pdf = _pdf(tmp_path / "letra caixa.pdf", [((10, 10, 90, 90), VERMELHO_LETRA)])

    relatorio = converter(pdf)

    assert relatorio["dxf"] is None
    assert not (tmp_path / "letra caixa.dxf").exists()
    assert "letra caixa" in relatorio["motivo"]


def test_pdf_sem_vetor_nenhum_avisa_que_e_imagem(tmp_path):
    doc = pymupdf.open()
    doc.new_page(width=100, height=100)
    doc.save(tmp_path / "vazio.pdf")
    doc.close()

    relatorio = converter(tmp_path / "vazio.pdf")

    assert relatorio["dxf"] is None
    assert "imagem" in relatorio["motivo"]


def test_conta_imagem_descartada_no_relatorio(tmp_path):
    """
    'Se tiver imagem pode descartar' — mas o relatório precisa dizer que
    havia uma, senão ninguém percebe que algo ficou de fora.
    """
    doc = pymupdf.open()
    pagina = doc.new_page(width=200, height=100)
    pagina.draw_rect(pymupdf.Rect(10, 10, 90, 90), color=MAGENTA_LOGO, width=1)
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 8, 8))
    pix.clear_with(200)
    pagina.insert_image(pymupdf.Rect(100, 10, 180, 90), pixmap=pix)
    doc.save(tmp_path / "com imagem.pdf")
    doc.close()

    relatorio = converter(tmp_path / "com imagem.pdf")

    assert relatorio["imagens"] == 1
    assert relatorio["dxf"] is not None, "a imagem sai, mas o contorno magenta continua valendo"


def test_mascara_de_recorte_complexa_vira_pista_em_vez_de_recusa_seca(tmp_path):
    """
    Ideia do Flavio (06/09/2026): a linha de corte pode estar servindo de
    mascara de recorte no Illustrator. No PDF, mascara NAO PINTA nada e
    por isso nao guarda cor — a geometria fica, o magenta some, e a busca
    por cor nunca acha.

    Nos arquivos daquele dia a hipotese nao se confirmou (as mascaras
    eram borda de pagina e recorte de imagem, 1 segmento cada), mas
    quando acontecer o programa tem que APONTAR pra isso, e nao dizer
    apenas "nao achei magenta".
    """
    doc = pymupdf.open()
    pagina = doc.new_page(width=200, height=200)
    pagina.draw_rect(pymupdf.Rect(1, 1, 2, 2))  # só pra existir fluxo de conteúdo pra trocar
    # Máscara de recorte de verdade: caminho com 8 segmentos seguido de
    # "W n" (recorta, não pinta) — é assim que o Illustrator grava uma
    # máscara. Depois um retângulo preto pintado por dentro dela.
    # Precisa ser escrito no fluxo bruto: draw_polyline pinta, não recorta.
    conteudo = (b"30 30 m 60 25 l 90 40 l 120 25 l 150 40 l "
                b"150 90 l 120 110 l 60 110 l 30 90 l h W n\n"
                b"0 0 0 rg 40 40 100 60 re f\n")
    doc.update_stream(pagina.get_contents()[0], conteudo)
    doc.save(tmp_path / "mascarado.pdf")
    doc.close()

    relatorio = converter(tmp_path / "mascarado.pdf")

    assert relatorio["dxf"] is None, "sem magenta continua recusando"
    assert relatorio["mascaras"], "a máscara complexa tem que ser notada"
    assert "máscara de recorte" in relatorio["motivo"]
    assert "Illustrator" in relatorio["motivo"], "o recado tem que dizer o que fazer"
