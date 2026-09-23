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
