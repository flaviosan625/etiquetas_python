"""Montagem sem teto de comprimento, seleção conferida e identificação segura."""
import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import montagem

pymupdf = pytest.importorskip("pymupdf")


@pytest.fixture
def entrada(tmp_path):
    pasta = tmp_path / "DOCAN R5200"
    pasta.mkdir()
    return pasta


def _arte(pasta, nome, medidas):
    arquivo = pasta / nome
    with pymupdf.open() as doc:
        for largura, altura in medidas:
            pagina = doc.new_page(width=largura * montagem.PT_M,
                                  height=altura * montagem.PT_M)
            pagina.draw_rect(pagina.rect, color=None, fill=(0.1, 0.3, 0.5))
        doc.save(str(arquivo))
    return arquivo


def test_lote_comprido_sai_inteiro_com_todas_as_copias(entrada):
    nome = "12UN LONA IMPRESSA 2.40X2.00M_VIBRA_LOTE.pdf"
    _arte(entrada, nome, [(2.4, 2.0)])
    previa = montagem.prever_pasta(entrada, raiz_clientes=entrada.parent / "clientes")
    assert len(previa["folhas"]) == 1
    assert previa["folhas"][0]["folha_m"] > 10
    assert len(previa["folhas"][0]["itens"]) == 12
    resultado = montagem.montar_pasta(entrada, raiz_clientes=entrada.parent / "clientes")
    assert len(resultado["folhas"]) == 1
    with pymupdf.open(str(resultado["folhas"][0]["arquivo"])) as doc:
        assert doc.page_count == 1
        assert doc[0].rect.height / montagem.PT_M > 10


@pytest.mark.parametrize("folga", [0.01, 0.02, 0.05, 0.08])
def test_folga_passada_preserva_geometria_nome_e_faixa_do_rotulo(entrada, folga):
    nome = "2UN LONA IMPRESSA 6.00X0.20M_VIBRA_FAIXA.pdf"
    _arte(entrada, nome, [(6.0, 0.2)])
    previa = montagem.prever_pasta(entrada, folga_m=folga,
                                  raiz_clientes=entrada.parent / "clientes")
    plano = montagem.planejar_pasta(entrada, folga_m=folga,
                                   raiz_clientes=entrada.parent / "clientes")
    assert previa["folga_m"] == folga
    for posta in plano["folhas"][0]["postas"]:
        assert posta[5] is True
        assert posta[6] >= 0.3
        assert posta[7] - posta[4] >= folga - 1e-9
        assert sorted(posta[3:5]) == pytest.approx([0.2, 6.0], abs=0.0001)
    resultado = montagem.montar_pasta(
        entrada, folga_m=folga, arquivos=[nome], versoes_esperadas=previa["versoes"],
        raiz_clientes=entrada.parent / "clientes")
    arquivo = resultado["folhas"][0]["arquivo"]
    ficha = json.loads(arquivo.with_suffix(".json").read_text(encoding="utf-8"))
    assert ficha["folga_m"] == folga
    with pymupdf.open(str(arquivo)) as doc:
        texto = doc[0].get_text()
        assert nome[:-4] in texto
        assert "(1/2)" in texto and "(2/2)" in texto
        assert "~" not in texto
        for item in previa["folhas"][0]["itens"]:
            # Texto adjacente pode ocupar o mesmo bloco, linha e span.
            # Busque a caixa de cada identificação completa separadamente.
            correspondentes = doc[0].search_for(item["rotulo"])
            assert len(correspondentes) == 1, "cada cópia precisa do seu rótulo inteiro"
            rotulo = correspondentes[0]
            caixa = tuple(rotulo)
            x, y, _w, _h = item["posicao_m"]
            assert caixa[0] == pytest.approx(x * montagem.PT_M, abs=1)
            assert caixa[1] >= (y - folga / 2) * montagem.PT_M - 1
            assert caixa[3] <= y * montagem.PT_M
            assert caixa[2] - caixa[0] <= montagem.ROTULO_LARGURA_M * montagem.PT_M + 1
            fontes = [span["size"] for bloco in doc[0].get_text("dict", clip=rotulo)["blocks"]
                      for linha in bloco.get("lines", []) for span in linha["spans"]]
            assert fontes
            assert min(fontes) / montagem.PT_M * 1000 >= montagem.ROTULO_LETRA_MINIMA_MM - 0.01


def test_diminuir_folga_reduz_comprimento_sem_diminuir_a_arte(entrada):
    _arte(entrada, "4UN LONA IMPRESSA 1.00X0.50M_VIBRA.pdf", [(1.0, 0.5)])
    larga = montagem.prever_pasta(entrada, folga_m=0.05)
    justa = montagem.prever_pasta(entrada, folga_m=0.01)
    assert justa["metragem_rolo"] < larga["metragem_rolo"]
    assert [i["medida_m"] for i in justa["folhas"][0]["itens"]] == \
           [i["medida_m"] for i in larga["folhas"][0]["itens"]]


@pytest.mark.parametrize("invalida", [0, -0.01, 0.009, float("nan"), float("inf"), "ruim"])
def test_folga_invalida_falha_antes_de_escrever(entrada, invalida):
    with pytest.raises(ValueError):
        montagem.montar_pasta(entrada, folga_m=invalida)
    assert list(entrada.iterdir()) == []
    assert not montagem.pasta_de_saida("DOCAN R5200", entrada.parent).exists()


def test_preferencia_de_folga_por_maquina_e_override_do_lote():
    config = {"montagem": {"DOCAN R5200": {"folga_m": 0.02}}}
    assert montagem.folga_da_montagem("DOCAN R5200", config=config) == 0.02
    assert montagem.folga_da_montagem("DOCAN R5200", config=config, folga_m=0.04) == 0.04


def test_selecao_vazia_nao_converte_monta_nem_move(entrada):
    nome = "1UN LONA IMPRESSA 1.00X0.50M_VIBRA.pdf"
    arte = _arte(entrada, nome, [(1.0, 0.5)])
    assert montagem.prever_pasta(entrada, arquivos=[])["folhas"] == []
    assert montagem.converter_o_que_precisa(entrada, arquivos=[]) == []
    assert montagem.montar_pasta(entrada, arquivos=[])["folhas"] == []
    assert arte.exists()
    assert not montagem.pasta_de_saida("DOCAN R5200", entrada.parent).exists()


def test_selecao_restringe_montagem_e_arquivamento(entrada):
    a = _arte(entrada, "1UN LONA IMPRESSA 1.00X0.50M_A.pdf", [(1, 0.5)])
    b = _arte(entrada, "1UN LONA IMPRESSA 1.00X0.50M_B.pdf", [(1, 0.5)])
    previa = montagem.prever_pasta(entrada, arquivos=[a])
    assert set(previa["versoes"]) == {a.name}
    resultado = montagem.montar_pasta(entrada, arquivos=[a.name],
                                      versoes_esperadas=previa["versoes"])
    assert resultado["folhas"][0]["pecas"] == 1
    assert not a.exists() and b.exists()


def test_versao_alterada_exige_nova_previa_sem_mover(entrada):
    nome = "1UN LONA IMPRESSA 1.00X0.50M_A.pdf"
    arte = _arte(entrada, nome, [(1, 0.5)])
    previa = montagem.prever_pasta(entrada, arquivos=[nome])
    arte.write_bytes(arte.read_bytes() + b"\n% versao alterada\n")
    with pytest.raises(ValueError, match="Recalcule"):
        montagem.montar_pasta(entrada, arquivos=[nome], versoes_esperadas=previa["versoes"])
    assert arte.exists()
    assert not montagem.pasta_de_saida("DOCAN R5200", entrada.parent).exists()


def test_arte_recusada_no_encaixe_nao_e_arquivada_com_as_boas(entrada):
    boa = _arte(entrada, "1UN LONA IMPRESSA 1.00X1.00M_BOA.pdf", [(1, 1)])
    ruim = _arte(entrada, "1UN LONA IMPRESSA 6.00X6.00M_GRANDE.pdf", [(6, 6)])
    resultado = montagem.montar_pasta(entrada)
    assert resultado["folhas"][0]["pecas"] == 1
    assert not boa.exists() and ruim.exists()
    assert [r["arquivo"] for r in resultado["recusadas"]] == [ruim.name]


def test_paginas_sao_medidas_separadamente_e_resolucao_nao_repete_por_copia(entrada, monkeypatch):
    nome = "3UN LONA IMPRESSA 1.00X0.50M_PAGINAS.pdf"
    _arte(entrada, nome, [(1, 0.5), (2, 1)])
    chamadas = []
    def medir(arquivo, pagina, fator):
        chamadas.append((pagina, fator))
        return {"dpi": None, "estado": "sem_raster", "motivo": ""}
    monkeypatch.setattr(montagem, "_resolucao_detalhada", medir)
    pecas, recusadas = montagem.pecas_da_pasta(entrada)
    assert not recusadas and len(pecas) == 6
    assert len(chamadas) == 2
    assert [pagina for pagina, _fator in chamadas] == [0, 1]
    assert [fator for _pagina, fator in chamadas] == pytest.approx([1, 0.5])
    assert {p["pagina"] for p in pecas} == {0, 1}
    assert all(p["largura_m"] == pytest.approx(1) for p in pecas)


def test_pagina_com_proporcao_errada_recusa_arquivo_completo(entrada):
    nome = "2UN LONA IMPRESSA 1.00X0.50M_PAGINAS.pdf"
    _arte(entrada, nome, [(1, 0.5), (1, 1)])
    pecas, recusadas = montagem.pecas_da_pasta(entrada)
    assert pecas == []
    assert len(recusadas) == 1 and "página 2" in recusadas[0]["motivo"]


def test_quantidade_zero_nao_vira_uma_copia(entrada):
    _arte(entrada, "0UN LONA IMPRESSA 1.00X0.50M_A.pdf", [(1, 0.5)])
    pecas, recusadas = montagem.pecas_da_pasta(entrada)
    assert not pecas and "quantidade" in recusadas[0]["motivo"]


def test_resolucao_nao_verificada_aparece_com_aviso(entrada, monkeypatch):
    _arte(entrada, "1UN LONA IMPRESSA 1.00X0.50M_A.pdf", [(1, 0.5)])
    monkeypatch.setattr(montagem, "_resolucao_detalhada", lambda *args:
                        {"dpi": None, "estado": "nao_verificada", "motivo": "Falha na verificação."})
    previa = montagem.prever_pasta(entrada)
    item = previa["folhas"][0]["itens"][0]
    assert item["qualidade"] == "nao_verificada"
    assert item["estado"] == "nao_verificada" and item["avisos"]


def test_aproveitamento_do_pdf_e_do_rolo_sao_diferentes(entrada):
    _arte(entrada, "1UN LONA IMPRESSA 1.00X0.50M_A.pdf", [(1, 0.5)])
    previa = montagem.prever_pasta(entrada)
    folha = previa["folhas"][0]
    assert folha["largura_m"] < 5
    assert folha["aproveitamento"] > folha["aproveitamento_rolo"]
    assert previa["aproveitamento_rolo"] == pytest.approx(
        folha["area_pecas_m2"] / (5 * folha["folha_m"]))
    assert previa["consumo_rolo_estimado"] is True
