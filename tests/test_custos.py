"""
Custo de material na cópia da gerência.

Decisões do usuário (2026-09-14): só numa cópia da gerência; custo = peças +
sobra; preço por espessura/cor quando houver. E a garantia que mais importa:
a cópia com valores NUNCA aparece onde a produção procura OS.

Nenhum teste toca pasta real nem o config.json de verdade.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import pymupdf
import pytest

import custos
from dimensoes import calcular_desperdicio_item


def _materiais(preco_lona=18.0, preco_adesivo=25.0):
    lona = {"tipo": "rolo", "largura_cm": 320.0, "comprimento_cm": 5000.0}
    adesivo = {"tipo": "rolo", "largura_cm": 127.0, "comprimento_cm": 5000.0}
    if preco_lona:
        lona["preco_m2"] = preco_lona
    if preco_adesivo:
        adesivo["preco_m2"] = preco_adesivo
    return {
        "LONA": lona,
        "ADESIVO": adesivo,
        "PS": {"tipo": "chapa", "largura_cm": 200.0, "comprimento_cm": 100.0, "preco_m2": 40.0,
               "variantes": [{"espessura": "1MM", "cor": "BRANCO", "preco_m2": 30.0},
                             {"espessura": "3MM", "cor": "BRANCO", "preco_m2": 55.0},
                             {"espessura": "2MM", "cor": "PRETO"}]},
        "MDF": {"tipo": "chapa", "largura_cm": 185.0, "comprimento_cm": 270.0,
                "variantes": [{"espessura": "6MM"}]},
    }


def _item(categoria, largura, altura, quantidade=1, variante=None, extra=None):
    return {"categoria": categoria, "quantidade": quantidade, "variante": variante,
            "categoria_extra": extra, "arquivo": "x.pdf",
            "dimensao": {"largura_m": largura, "altura_m": altura, "area_m2": largura * altura}}


# ------------------------------------------------------------------ preço

def test_preco_do_material_sem_variante():
    assert custos.preco_m2(_materiais(), "LONA") == 18.0


def test_preco_da_espessura_vence_o_do_material():
    """PS 1mm e 3mm custam diferente (decisão do usuário)."""
    m = _materiais()
    assert custos.preco_m2(m, "PS", {"espessura": "3MM", "cor": "BRANCO"}) == 55.0
    assert custos.preco_m2(m, "PS", {"espessura": "1MM", "cor": "BRANCO"}) == 30.0


def test_espessura_sem_preco_usa_o_preco_do_material():
    assert custos.preco_m2(_materiais(), "PS", {"espessura": "2MM", "cor": "PRETO"}) == 40.0


def test_variante_de_rodada_antiga_sem_o_campo_de_preco_ainda_acha_o_preco():
    """O estado_pedido.json guarda uma cópia da variante gravada antes do preço existir."""
    copia_velha = {"espessura": "3MM", "cor": "BRANCO"}          # sem preco_m2 dentro
    assert custos.preco_m2(_materiais(), "PS", copia_velha) == 55.0


def test_sem_nada_cadastrado_nao_tem_preco():
    m = _materiais(preco_lona=None, preco_adesivo=None)
    del m["PS"]
    assert custos.preco_m2(m, "LONA") is None
    assert custos.tem_algum_preco(m) is False
    assert custos.assinatura_precos(m) == ""


# ------------------------------------------------------------------ conta

def test_custo_e_pecas_mais_sobra_vezes_o_preco():
    """Decisão do usuário: o material que sai do rolo de verdade, não só a peça."""
    item = _item("LONA", 3.0, 1.0, quantidade=2)
    sobra = calcular_desperdicio_item(item["dimensao"], 3.20)["desperdicio_m2"] * 2

    r = custos.calcular([item], _materiais())
    lona = r["por_material"]["LONA"]

    assert lona["area_pecas_m2"] == round(3.0 * 1.0 * 2, 2)
    assert lona["area_sobra_m2"] == round(sobra, 2)
    assert lona["valor"] == round((6.0 + sobra) * 18.0, 2)


def test_reais_somam_entre_materiais():
    r = custos.calcular([_item("LONA", 2.0, 1.0), _item("ADESIVO", 1.0, 1.0)], _materiais())

    assert r["total"] == round(r["por_material"]["LONA"]["valor"] + r["por_material"]["ADESIVO"]["valor"], 2)
    assert r["completo"] is True


def test_material_composto_consome_o_extra_ao_preco_dele():
    """PS ADESIVADO: uma peça, dois materiais."""
    r = custos.calcular([_item("PS", 1.0, 0.5, variante={"espessura": "3MM", "cor": "BRANCO"},
                               extra="ADESIVO")], _materiais())

    assert set(r["por_material"]) == {"PS", "ADESIVO"}
    assert r["por_material"]["ADESIVO"]["valor"] > 0


def test_material_sem_preco_nao_vira_zero_calado():
    """Número deduzido nunca se passa por declarado: o total diz que é parcial e o que falta."""
    r = custos.calcular([_item("LONA", 2.0, 1.0), _item("MDF", 1.0, 1.0, variante={"espessura": "6MM"})],
                        _materiais())

    assert r["completo"] is False
    assert r["faltando_preco"] == ["MDF 6MM"]
    assert r["por_material"]["MDF"]["completo"] is False
    assert r["total"] == r["por_material"]["LONA"]["valor"]


@pytest.mark.parametrize("valor, texto", [
    (49157.64, "R$ 49.157,64"),
    (0.5, "R$ 0,50"),
    (1234567.8, "R$ 1.234.567,80"),
    (999, "R$ 999,00"),
])
def test_reais_no_formato_brasileiro(valor, texto):
    assert custos.formatar_reais(valor) == texto


def test_mudar_um_preco_muda_a_assinatura():
    m = _materiais()
    antes = custos.assinatura_precos(m)
    m["PS"]["variantes"][1]["preco_m2"] = 60.0

    assert custos.assinatura_precos(m) != antes


# ------------------------------------------------- só gerência, de verdade

def test_a_copia_nao_se_chama_os():
    assert not custos.nome_arquivo("MERCADO LIVRE 26").startswith("OS - ")


def test_a_tela_de_impressao_da_producao_nao_enxerga_a_copia(tmp_path):
    """
    gui._pedidos_para_impressao lista "OS - *.pdf" pra reimpressão. Com nome
    de OS, a cópia com os valores iria parar na mão de quem imprime pra
    produção.
    """
    import gui
    pedido = tmp_path / "MERCADO LIVRE 26_20260914_100000"
    pedido.mkdir()
    (pedido / "OS - MERCADO LIVRE 26.pdf").write_bytes(b"%PDF")
    (pedido / custos.nome_arquivo("MERCADO LIVRE 26")).write_bytes(b"%PDF")

    pedidos = gui._pedidos_para_impressao(tmp_path)

    assert [p.name for p in pedidos[0]["os"]] == ["OS - MERCADO LIVRE 26.pdf"]


def test_o_arquivamento_nao_enxerga_a_copia(tmp_path):
    import arquivamento
    (tmp_path / "OS - REPSOL.pdf").write_bytes(b"%PDF")
    (tmp_path / custos.nome_arquivo("REPSOL")).write_bytes(b"%PDF")

    assert [p.name for p in arquivamento._arquivos_os(tmp_path)] == ["OS - REPSOL.pdf"]


def _texto(caminho):
    doc = pymupdf.open(str(caminho))
    try:
        return "".join(doc[i].get_text() for i in range(doc.page_count))
    finally:
        doc.close()


def _gerar_copia(pasta, materiais, itens):
    dados = {"LONA": {"contem_arquivos": True, "area_total_m2": sum(i["dimensao"]["area_m2"] for i in itens)}}
    return custos.gerar_copia(str(pasta), "TESTE", "Gerente", "Produtor", itens, dados, ["LONA"],
                              "14/09/2026 10:00:00", materiais)


def test_copia_da_gerencia_tem_valores_e_diz_que_e_da_gerencia(tmp_path):
    caminho = _gerar_copia(tmp_path, _materiais(), [_item("LONA", 3.0, 1.0)])

    texto = _texto(caminho)
    assert pathlib.Path(caminho).name == "CUSTOS - TESTE.pdf"
    assert "SÓ GERÊNCIA" in texto
    assert "R$" in texto
    assert "sobra est." in texto
    assert "Custo de material" in texto


def test_a_os_da_producao_continua_sem_valor_nenhum(tmp_path):
    from relatorios import gerar_os
    itens = [_item("LONA", 3.0, 1.0)]
    dados = {"LONA": {"contem_arquivos": True, "area_total_m2": 3.0}}

    caminho = gerar_os(str(tmp_path), "TESTE", "G", "P", itens, dados, ["LONA"],
                       "14/09/2026 10:00:00", _materiais())

    texto = _texto(caminho)
    assert "R$" not in texto
    assert "GERÊNCIA" not in texto


def test_sem_preco_nao_gera_copia_e_apaga_a_velha(tmp_path):
    """Valor de preço que não existe mais é pior que nenhum valor."""
    velha = tmp_path / custos.nome_arquivo("TESTE")
    velha.write_bytes(b"%PDF antiga")
    sem_preco = {"LONA": {"tipo": "rolo", "largura_cm": 320.0, "comprimento_cm": 5000.0}}

    assert _gerar_copia(tmp_path, sem_preco, [_item("LONA", 3.0, 1.0)]) is None
    assert not velha.exists()


def test_o_checklist_do_evento_sai_com_a_copia_de_custos(tmp_path):
    import checklist_producao
    prod = tmp_path / "PRODUCAO"
    (prod / "UV").mkdir(parents=True)
    (prod / "UV" / "2UN LONA IMPRESSA 3.00X1.00M_L01.pdf").write_bytes(b"%PDF-1.4 fake")
    config = {"materiais": _materiais(), "ordem_unificado": ["LONA"], "sinonimos_categoria": {},
              "typos_unidade": {}, "ultimo_gerente": "G", "ultimo_produtor": "P"}

    checklist_producao.gerar(tmp_path / "saida", prod, nome_cliente="TESTE", config=config, com_miniatura=False)

    assert (tmp_path / "saida" / "OS - TESTE.pdf").is_file()
    assert (tmp_path / "saida" / "CUSTOS - TESTE.pdf").is_file()
