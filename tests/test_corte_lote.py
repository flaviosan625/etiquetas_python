"""
Testes do lote de corte — juntar tudo que espera a fresa do mesmo
material numa chapa só.

Os PDFs são desenhados aqui, em tmp_path. Nenhum toca a produção: já
aconteceu de teste apagar estoque.json e sujar o registro por usar a
constante de módulo com o caminho real.
"""
import pathlib
import sys

import pymupdf
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import corte_lote
from corte_lote import (
    ILEGIVEL, SEM_CADASTRO, SEM_CORTE, cabe_na_chapa, dispor, juntar, ler_peca, resumo,
)

MAGENTA = (0.922, 0.229, 0.506)      # medido nos arquivos reais da casa
PRETO = (0.1, 0.1, 0.1)
MM_PARA_PT = 1 / 0.3527777777777778


def _pdf_de_corte(caminho, largura_mm, altura_mm, cor=MAGENTA, margem_mm=10):
    """Um PDF com UM retângulo do tamanho pedido, na cor pedida."""
    largura_pt = (largura_mm + 2 * margem_mm) * MM_PARA_PT
    altura_pt = (altura_mm + 2 * margem_mm) * MM_PARA_PT
    m = margem_mm * MM_PARA_PT

    doc = pymupdf.open()
    pagina = doc.new_page(width=largura_pt, height=altura_pt)
    pagina.draw_rect(
        pymupdf.Rect(m, m, m + largura_mm * MM_PARA_PT, m + altura_mm * MM_PARA_PT),
        color=cor, width=1,
    )
    doc.save(caminho)
    doc.close()
    return pathlib.Path(caminho)


def _caixas_das_pecas(polilinhas):
    """Cada polilinha aqui é uma peça inteira (os testes usam retângulos)."""
    return [corte_lote._caixa([p]) for p in polilinhas]


# ---------- ler um arquivo ----------

def test_le_material_espessura_e_quantidade_do_nome(tmp_path):
    pdf = _pdf_de_corte(tmp_path / "5UN PVC 10MM RECORTE_teste.pdf", 300, 200)
    peca, recusa = ler_peca(pdf)

    assert recusa is None
    assert (peca.material, peca.espessura) == ("PVC", 10)
    assert peca.quantidade == 5
    assert peca.largura == pytest.approx(300, abs=1)
    assert peca.altura == pytest.approx(200, abs=1)


def test_sem_linha_de_corte_e_sem_corte_nao_falta_de_cadastro(tmp_path):
    """
    A arte de impressão cai aqui, e isso é NORMAL — ela não tem corte
    nenhum. Misturar esse caso com "falta cadastrar" foi o que poluiu a
    primeira lista da pasta da UMBRO: a arte aparecia junto com o
    arquivo que de fato precisava de alguém.
    """
    pdf = _pdf_de_corte(tmp_path / "1UN PVC 10MM impresso.pdf", 300, 200, cor=PRETO)
    peca, (codigo, _) = ler_peca(pdf)

    assert peca is None
    assert codigo == SEM_CORTE


def test_com_corte_e_material_nao_cadastrado_pede_atencao(tmp_path):
    """
    O caso real da UMBRO (07/09/2026): o arquivo TEM 11 contornos de
    corte e mesmo assim não pode ir pra fresa, porque PS não está
    cadastrado. Recusar é certo — chutar a fresa estraga a chapa —, mas
    tem que gritar, não sumir no meio da lista.
    """
    pdf = _pdf_de_corte(tmp_path / "1UN PS BRANCO RECORTE CONTORNO_teste.pdf", 300, 200)
    peca, (codigo, motivo) = ler_peca(pdf)

    assert peca is None
    assert codigo == SEM_CADASTRO
    assert "contorno" in motivo, "o motivo tem que dizer que HÁ corte ali dentro"


def test_arquivo_quebrado_nao_derruba_a_leitura(tmp_path):
    quebrado = tmp_path / "1UN PVC 10MM quebrado.pdf"
    quebrado.write_bytes(b"isto nao e um PDF")

    peca, (codigo, _) = ler_peca(quebrado)
    assert peca is None and codigo == ILEGIVEL


# ---------- juntar a pasta ----------

def test_junta_arquivos_do_mesmo_material_num_lote_so(tmp_path):
    _pdf_de_corte(tmp_path / "1UN PVC 10MM RECORTE_a.pdf", 300, 200)
    _pdf_de_corte(tmp_path / "2UN PVC 10MM RECORTE_b.pdf", 400, 250)
    _pdf_de_corte(tmp_path / "1UN MDF 9MM RECORTE_c.pdf", 300, 200)

    lotes, recusados = juntar(tmp_path)

    assert set(lotes) == {("PVC", 10), ("MDF", 9)}
    assert len(lotes[("PVC", 10)]) == 2, "os dois PVC 10 vão pra mesma chapa"
    assert recusados == []


def test_nao_junta_o_que_ja_foi_enviado(tmp_path):
    _pdf_de_corte(tmp_path / "1UN PVC 10MM RECORTE_novo.pdf", 300, 200)
    enviados = tmp_path / "Enviados"
    enviados.mkdir()
    _pdf_de_corte(enviados / "1UN PVC 10MM RECORTE_velho.pdf", 300, 200)

    lotes, _ = juntar(tmp_path)
    assert len(lotes[("PVC", 10)]) == 1


def test_juntar_nunca_escreve_nada(tmp_path):
    pdf = _pdf_de_corte(tmp_path / "1UN PVC 10MM RECORTE_a.pdf", 300, 200)
    antes = {p: p.stat().st_mtime_ns for p in tmp_path.rglob("*")}

    juntar(tmp_path)

    depois = {p: p.stat().st_mtime_ns for p in tmp_path.rglob("*")}
    assert antes == depois, "olhar a pasta tem que ser sempre seguro"
    assert pdf.exists()


# ---------- a chapa ----------

def test_peca_que_so_cabe_girada_e_girada(tmp_path):
    """
    Foi assim que o arquivo de teste mordeu: 1244,9 mm de largura numa
    chapa de 1220 — deitado passa 25 mm, de pé sobra.
    """
    pdf = _pdf_de_corte(tmp_path / "1UN PVC 10MM RECORTE_deitada.pdf", 1300, 500)
    peca, _ = ler_peca(pdf)

    cabe, girar = cabe_na_chapa(peca)
    assert cabe and girar

    polilinhas, _, chapas, fora = dispor([peca])
    assert fora == []
    (x0, y0, x1, y1), = _caixas_das_pecas(polilinhas)
    assert (x1 - x0) == pytest.approx(500, abs=1), "entrou girada: a largura virou 500"
    assert (y1 - y0) == pytest.approx(1300, abs=1)


def test_peca_maior_que_a_chapa_fica_de_fora_e_e_avisada(tmp_path):
    pdf = _pdf_de_corte(tmp_path / "1UN PVC 10MM RECORTE_castelo.pdf", 1300, 2500)
    peca, _ = ler_peca(pdf)

    assert cabe_na_chapa(peca)[0] is False
    polilinhas, _, _, fora = dispor([peca])
    assert polilinhas == []
    assert fora == [peca], "não pode sumir em silêncio — vira aviso"


def test_area_da_peca_que_nao_coube_nao_conta_nas_chapas(tmp_path):
    """
    O primeiro teste real (07/09/2026) deu 87% de aproveitamento contando
    dois castelos de 3,5 m que nem entraram na chapa. Número bonito e
    mentiroso — do tipo que faz comprar chapa a menos.
    """
    dentro, _ = ler_peca(_pdf_de_corte(tmp_path / "1UN PVC 10MM RECORTE_ok.pdf", 500, 500))
    fora, _ = ler_peca(_pdf_de_corte(tmp_path / "1UN PVC 10MM RECORTE_grande.pdf", 1300, 2500))

    dados = resumo("PVC", 10, [dentro, fora])

    assert dados["unidades"] == 1, "só conta o que vai pra chapa"
    assert dados["unidades_fora"] == 1
    assert dados["area_m2"] == pytest.approx(0.25, abs=0.01)
    assert dados["area_fora_m2"] > 3, "a área que ficou de fora continua visível"


def test_copias_da_mesma_peca_nao_se_encostam(tmp_path):
    """
    A regra que o Flávio deu: 15 mm entre as linhas, "para não colidir
    uma linha da outra".
    """
    pdf = _pdf_de_corte(tmp_path / "6UN PVC 10MM RECORTE_aplique.pdf", 300, 300)
    peca, _ = ler_peca(pdf)

    polilinhas, _, _, _ = dispor([peca])
    caixas = _caixas_das_pecas(polilinhas)
    assert len(caixas) == 6

    for i, (ax0, ay0, ax1, ay1) in enumerate(caixas):
        for bx0, by0, bx1, by1 in caixas[i + 1:]:
            separadas = (bx0 - ax1 >= corte_lote.FOLGA_ENTRE_PECAS_MM - 0.01
                         or ax0 - bx1 >= corte_lote.FOLGA_ENTRE_PECAS_MM - 0.01
                         or by0 - ay1 >= corte_lote.FOLGA_ENTRE_PECAS_MM - 0.01
                         or ay0 - by1 >= corte_lote.FOLGA_ENTRE_PECAS_MM - 0.01)
            assert separadas, "duas cópias encostaram — uma linha cortaria a outra"


def test_nada_passa_da_borda_da_chapa(tmp_path):
    pdf = _pdf_de_corte(tmp_path / "8UN PVC 10MM RECORTE_p.pdf", 400, 400)
    peca, _ = ler_peca(pdf)

    polilinhas, _, chapas, _ = dispor([peca])
    largura_total = chapas * corte_lote.CHAPA_PADRAO_MM[0] + chapas * corte_lote.FOLGA_DA_BORDA_MM
    for x0, y0, x1, y1 in _caixas_das_pecas(polilinhas):
        assert y0 >= corte_lote.FOLGA_DA_BORDA_MM - 0.01
        assert y1 <= corte_lote.CHAPA_PADRAO_MM[1] - corte_lote.FOLGA_DA_BORDA_MM + 0.01
        assert x1 <= largura_total


def test_as_camadas_de_corte_sobrevivem_ao_lote(tmp_path):
    """
    É a camada que garante dentro-antes-de-fora no gadget. Se ela se
    perder ao juntar, o gadget cai no modo de um percurso só e a ordem
    deixa de ser garantida.
    """
    import corte_dxf

    pdf = _pdf_de_corte(tmp_path / "3UN PVC 10MM RECORTE_x.pdf", 300, 300)
    peca, _ = ler_peca(pdf)

    polilinhas, camadas, _, _ = dispor([peca])
    assert len(camadas) == len(polilinhas)
    assert set(camadas) <= {corte_dxf.CAMADA_INTERNO, corte_dxf.CAMADA_EXTERNO}


# ---------- o arquivo do lote ----------

def test_escreve_um_dxf_so_com_o_lote_inteiro(tmp_path):
    _pdf_de_corte(tmp_path / "2UN PVC 10MM RECORTE_a.pdf", 300, 200)
    _pdf_de_corte(tmp_path / "3UN PVC 10MM RECORTE_b.pdf", 400, 250)
    lotes, _ = juntar(tmp_path)

    destino = tmp_path / "lote.dxf"
    dados = corte_lote.escrever_lote("PVC", 10, lotes[("PVC", 10)], destino)

    assert destino.exists()
    assert dados["unidades"] == 5
    assert dados["atalho"] == "Corte Automatico PVC 10"
    texto = destino.read_text(encoding="utf-8")
    assert "CORTE EXTERNO" in texto


def test_escrever_lote_nao_toca_nos_pdfs(tmp_path):
    pdf = _pdf_de_corte(tmp_path / "2UN PVC 10MM RECORTE_a.pdf", 300, 200)
    antes = pdf.read_bytes()
    lotes, _ = juntar(tmp_path)

    corte_lote.escrever_lote("PVC", 10, lotes[("PVC", 10)], tmp_path / "lote.dxf")

    assert pdf.read_bytes() == antes, "o original nunca sai do lugar"
