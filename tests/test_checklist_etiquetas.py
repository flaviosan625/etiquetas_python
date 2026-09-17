"""
Checklist de etiquetas da produção: só o que é NOVO vira etiqueta.

O documento em si é o de sempre (processamento.processar_etiquetas) — aqui
se testa o que é deste módulo: cruzar com a lista antiga pra não reimprimir
etiqueta que já saiu.

Nenhum teste toca pasta real: produção, saída e estado vão todos pra
tmp_path.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import pymupdf
import pytest

import checklist_etiquetas as ce


def _pdf(caminho, largura_pt=144, altura_pt=72):
    """Um PDF pequeno mas DE VERDADE — o gerador rasteriza a arte."""
    caminho.parent.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open()
    pagina = doc.new_page(width=largura_pt, height=altura_pt)
    pagina.draw_rect(pymupdf.Rect(4, 4, largura_pt - 4, altura_pt - 4),
                     color=(0, 0, 0), fill=(0.95, 0.85, 0.1), width=1)
    doc.save(str(caminho), garbage=4, deflate=True)
    doc.close()
    return caminho


@pytest.fixture
def producao(tmp_path):
    prod = tmp_path / "PRODUCAO"
    _pdf(prod / "A_PREMIUM/UV/1UN LONA IMPRESSA 2.00X1.00M_PECA_A.pdf")
    _pdf(prod / "A_PREMIUM/UV/1UN LONA IMPRESSA 2.00X1.00M_PECA_B.pdf")
    return prod


@pytest.fixture
def estado(tmp_path):
    return tmp_path / "estado" / ce.NOME_ESTADO


# ------------------------------------------------- cruzar com a lista antiga

def test_na_primeira_vez_tudo_e_novo(producao, estado):
    novas = ce.artes_novas(producao, estado)

    assert sorted(a.name for a in novas) == [
        "1UN LONA IMPRESSA 2.00X1.00M_PECA_A.pdf",
        "1UN LONA IMPRESSA 2.00X1.00M_PECA_B.pdf",
    ]


def test_o_que_ja_foi_impresso_nao_volta(producao, estado):
    ce._gravar_estado(estado, {"1UN LONA IMPRESSA 2.00X1.00M_PECA_A.pdf"}, {})

    novas = ce.artes_novas(producao, estado)

    assert [a.name for a in novas] == ["1UN LONA IMPRESSA 2.00X1.00M_PECA_B.pdf"]


def test_ir_para_prontos_nao_torna_a_peca_nova_de_novo(producao, estado):
    """
    A chave é o NOME, não o caminho: a arte muda de pasta quando é
    produzida, e isso não pode fazer a etiqueta ser impressa de novo.
    """
    nome = "1UN LONA IMPRESSA 2.00X1.00M_PECA_A.pdf"
    ce._gravar_estado(estado, {nome}, {})
    origem = producao / "A_PREMIUM/UV" / nome
    destino = producao / "A_PREMIUM/UV/PRONTOS" / nome
    destino.parent.mkdir(parents=True, exist_ok=True)
    origem.rename(destino)

    assert nome not in [a.name for a in ce.artes_novas(producao, estado)]


# ------------------------------------------------------------ gerar o lote

def test_gera_o_checklist_e_marca_como_impresso(producao, estado, tmp_path):
    saida = tmp_path / "etiquetas_geradas"

    r = ce.gerar_lote(producao, "TESTE ML", caminho_estado=estado,
                      pasta_saida_base=saida, on_log=lambda n, m: None)

    assert r["gerou"] is True
    assert r["quantidade"] == 2
    checklist = pathlib.Path(r["checklist"])
    assert checklist.is_file()
    assert checklist.name == "Checklist TESTE ML.pdf"    # o nome de sempre
    # e a etiqueta é meia A4, 2 por folha: 2 peças cabem numa folha só
    doc = pymupdf.open(str(checklist))
    try:
        assert doc.page_count >= 1
        assert round(doc[0].rect.height) == 842          # A4 em pontos
    finally:
        doc.close()


def test_segunda_rodada_sem_novidade_nao_gera_nada(producao, estado, tmp_path):
    saida = tmp_path / "etiquetas_geradas"
    ce.gerar_lote(producao, "TESTE ML", caminho_estado=estado,
                  pasta_saida_base=saida, on_log=lambda n, m: None)
    pastas_antes = sorted(p.name for p in saida.iterdir())

    r = ce.gerar_lote(producao, "TESTE ML", caminho_estado=estado,
                      pasta_saida_base=saida, on_log=lambda n, m: None)

    assert r["gerou"] is False
    assert "nenhuma arte nova" in r["motivo"]
    # nada de pasta de pedido vazia sujando etiquetas_geradas
    assert sorted(p.name for p in saida.iterdir()) == pastas_antes


def test_so_a_arte_nova_entra_no_lote_seguinte(producao, estado, tmp_path):
    saida = tmp_path / "etiquetas_geradas"
    ce.gerar_lote(producao, "TESTE ML", caminho_estado=estado,
                  pasta_saida_base=saida, on_log=lambda n, m: None)

    _pdf(producao / "A_PREMIUM/UV/1UN LONA IMPRESSA 3.00X1.00M_PECA_C.pdf")
    r = ce.gerar_lote(producao, "TESTE ML", caminho_estado=estado,
                      pasta_saida_base=saida, on_log=lambda n, m: None)

    assert r["gerou"] is True
    assert r["arquivos"] == ["1UN LONA IMPRESSA 3.00X1.00M_PECA_C.pdf"]


def test_a_producao_nao_e_tocada(producao, estado, tmp_path):
    """
    O gerador renomeia e cria subpasta na entrada que recebe — por isso ele
    recebe uma pasta temporária, nunca a produção. Se um dia alguém apontar
    direto pra produção, este teste cai.
    """
    antes = sorted(p.relative_to(producao).as_posix() for p in producao.rglob("*"))

    ce.gerar_lote(producao, "TESTE ML", caminho_estado=estado,
                  pasta_saida_base=tmp_path / "etiquetas_geradas",
                  on_log=lambda n, m: None)

    assert sorted(p.relative_to(producao).as_posix() for p in producao.rglob("*")) == antes


# ------------------------------------------- cliente do cadastro e limpeza

@pytest.fixture
def cliente_ml(tmp_path, monkeypatch, producao):
    import caminhos
    import clientes

    onedrive = tmp_path / "UNYCOMUNICACAO"
    monkeypatch.setattr(caminhos, "ONEDRIVE_UNY", onedrive)
    monkeypatch.setattr(caminhos, "RECEBIMENTO_DE_ARTES", onedrive / "Recebimento de Artes")
    monkeypatch.setattr(caminhos, "EVENTOS", onedrive / "EVENTOS")
    monkeypatch.setattr(caminhos, "ETIQUETAS_GERADAS", tmp_path / "etiquetas_geradas")
    (onedrive / "Recebimento de Artes").mkdir(parents=True)
    return clientes.criar("Mercado Livre", pasta_producao=producao, nome_documento="TESTE ML")


def test_a_lista_de_impressos_mora_na_pasta_do_cliente(cliente_ml):
    import caminhos
    import clientes

    r = ce.gerar_lote_do_cliente(cliente_ml, on_log=lambda n, m: None)

    assert r["gerou"] is True
    assert ce.arquivo_estado(cliente_ml).is_file()
    assert ce.arquivo_estado(cliente_ml).parent == cliente_ml.pasta / clientes.PASTA_SISTEMA
    # o checklist sai em etiquetas_geradas — e SÓ ele: nenhuma memória lá
    assert pathlib.Path(r["checklist"]).is_relative_to(caminhos.ETIQUETAS_GERADAS)
    assert not list(caminhos.ETIQUETAS_GERADAS.rglob(ce.NOME_ESTADO))


def test_apagar_etiquetas_geradas_nao_faz_reimprimir(cliente_ml):
    """
    Aconteceu em 2026-09-13: a limpeza de etiquetas_geradas levou a lista das
    50 etiquetas já impressas, e o próximo lote teria reimpresso todas. Regra
    do usuário: "preciso manter somente o que está em andamento" — apagar
    qualquer cliente de lá tem que ser seguro.
    """
    import shutil
    import caminhos

    ce.gerar_lote_do_cliente(cliente_ml, on_log=lambda n, m: None)
    shutil.rmtree(caminhos.ETIQUETAS_GERADAS)                 # a limpeza

    r = ce.gerar_lote_do_cliente(cliente_ml, on_log=lambda n, m: None)

    assert r["gerou"] is False
    assert "nenhuma arte nova" in r["motivo"]


def test_lote_sem_caminho_de_estado_explicito_e_recusado(producao):
    """Sem padrão escondido em etiquetas_geradas pra memória cair calada."""
    with pytest.raises(TypeError):
        ce.gerar_lote(producao, "TESTE ML")


def test_cliente_sem_producao_nao_gera_nem_quebra(tmp_path, monkeypatch):
    import caminhos
    import clientes

    onedrive = tmp_path / "UNYCOMUNICACAO"
    monkeypatch.setattr(caminhos, "RECEBIMENTO_DE_ARTES", onedrive / "Recebimento de Artes")
    monkeypatch.setattr(caminhos, "ETIQUETAS_GERADAS", tmp_path / "etiquetas_geradas")
    (onedrive / "Recebimento de Artes").mkdir(parents=True)
    c = clientes.criar("Asics")

    assert ce.gerar_lote_do_cliente(c)["gerou"] is False
    assert ce.artes_novas_do_cliente(c) == []


# ------------------------------------------------------------ só Prontos

def test_so_prontos_nao_da_etiqueta_pra_peca_que_nao_saiu_da_maquina(producao, estado):
    """Etiqueta é pra peça pronta — a mesma regra da OS (2026-09-16)."""
    pronta = producao / "A_PREMIUM/UV/PRONTOS/1UN LONA IMPRESSA 2.00X1.00M_PECA_C.pdf"
    _pdf(pronta)

    novas = ce.artes_novas(producao, estado, so_prontos=True)

    assert [a.name for a in novas] == [pronta.name]


def test_so_prontos_ignora_pronto_em_espera(producao, estado):
    _pdf(producao / "TUNEL/NAO RODAR AINDA/PRONTOS/1UN LONA IMPRESSA 2.00X1.00M_PECA_D.pdf")

    assert ce.artes_novas(producao, estado, so_prontos=True) == []


def test_cliente_com_so_prontos_leva_a_regra_pro_lote(cliente_ml):
    cliente_ml.so_prontos = True

    assert ce.artes_novas_do_cliente(cliente_ml) == [], "as duas peças da produção estão fora de Prontos"
