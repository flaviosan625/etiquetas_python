"""Taxas da simulação, custo por cor e privacidade dos outros documentos."""
import copy
from types import SimpleNamespace
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import pymupdf
import pytest

import custos_tinta as ct
from config import CONFIG_PADRAO
from processamento import processar_etiquetas
from relatorios import gerar_os
from retirada_material import caminho_pdf


def _item(maquina=ct.R5200, categoria="DECORFLEX", quantidade=1, **extras):
    return dict(arquivo="PAINEL IMPRESSO.pdf", categoria=categoria, maquina=maquina,
                quantidade=quantidade, dimensao=dict(largura_m=5, altura_m=0.5, area_m2=2.5), **extras)


def _texto(caminho):
    with pymupdf.open(caminho) as doc:
        return "".join(p.get_text() for p in doc)


def _config():
    cfg = copy.deepcopy(CONFIG_PADRAO)
    cfg["materiais"]["DECORFLEX"] = dict(tipo="rolo", largura_cm=500, comprimento_cm=5000, preco_m2=10)
    cfg["ordem_unificado"].append("DECORFLEX")
    return cfg


def _config_com_precos_de_teste():
    cfg = ct.configuracao_padrao()
    for perfil in cfg["maquinas"].values():
        for dados in perfil["cores"].values():
            dados["preco_frasco"] = 100.0
    return cfg


def test_simulacao_usa_taxas_por_area_e_preco_cadastrado():
    conta = ct.calcular([_item()], _config_com_precos_de_teste())
    linha = conta["por_maquina"][ct.R5200]
    assert linha["area_m2"] == 2.5
    assert linha["volume_ml"] == pytest.approx(12.55)
    assert linha["valor"] == conta["total"] == 1.26
    assert conta["completo"]
    for cor, volume in ct.VOLUMES_REFERENCIA.items():
        assert linha["cores"][cor]["volume_ml"] == pytest.approx(volume)
        assert linha["cores"][cor]["preco_ml"] == 0.1
    assert [c["consumo_ml_m2"] for c in linha["cores"].values()] == [0.984, 0.552, 1.312, 2.172]


def test_quantidade_multiplica_area_consumo_e_gasto_sem_sobra_de_rolo():
    conta = ct.calcular([_item(quantidade=3)], _config_com_precos_de_teste())
    assert conta["por_maquina"][ct.R5200]["area_m2"] == 7.5
    assert conta["por_maquina"][ct.R5200]["volume_ml"] == pytest.approx(37.65)
    assert conta["total"] == 3.77


def test_h2525_usa_referencia_provisoria_autorizada():
    conta = ct.calcular([_item(ct.H2525, "PS")], _config_com_precos_de_teste())
    linha = conta["por_maquina"][ct.H2525]
    assert linha["valor"] == 1.26
    assert linha["referencia_provisoria"] is True
    assert linha["referencia_consumo"] == ct.R5200


def test_preco_e_por_cor_e_por_maquina():
    cfg = _config_com_precos_de_teste()
    cfg["maquinas"][ct.H2525]["cores"]["CIANO"]["preco_frasco"] = 50
    assert ct.calcular([_item(ct.R5200)], cfg)["total"] == 1.26
    assert ct.calcular([_item(ct.H2525)], cfg)["total"] == 1.13


def test_outras_impressoras_chapas_sem_impressao_e_adesivadas_nao_sao_cobradas_como_docan():
    cfg = _config_com_precos_de_teste()
    casos = [_item("SWJ320A", "LONA"), _item("UJV 100 UNY CV", "PS"),
             dict(_item(None, "PS"), arquivo="CORTE DIRETO.pdf"),
             dict(_item(None, "PVC"), arquivo="PAINEL.pdf"),
             _item(None, "PS", categoria_extra="ADESIVO")]
    assert ct.calcular(casos, cfg)["por_maquina"] == {}
    assert ct.maquina_da_peca(_item(None), cfg) == (ct.R5200, True)
    assert ct.maquina_da_peca(_item(None, "PS"), cfg) == (ct.H2525, True)


def test_sem_taxa_ou_medida_nao_inventa_consumo():
    cfg = _config_com_precos_de_teste()
    cfg["maquinas"][ct.H2525]["cores"]["BLACK"]["consumo_ml_m2"] = None
    conta = ct.calcular([_item(ct.H2525)], cfg)
    assert not conta["completo"] and conta["faltantes"]
    item = _item()
    item["dimensao"] = None
    conta = ct.calcular([item], cfg)
    assert not conta["completo"] and conta["por_maquina"] == {}


def test_estoque_cadastra_oito_frascos_com_custo_sem_movimentacao():
    cadastro = dict(produtos={"OUTRO":dict(custo=7)}, movimentos=[dict(id=1, quantidade=2)], proximo_id=2)
    antes = copy.deepcopy(cadastro["movimentos"])
    ct.sincronizar_catalogo(cadastro, _config_com_precos_de_teste())
    assert len(cadastro["produtos"]) == 9
    assert cadastro["produtos"]["OUTRO"]["custo"] == 7
    for maquina in (ct.R5200, ct.H2525):
        for cor in ct.CORES:
            produto = cadastro["produtos"][ct.codigo_produto(maquina, cor)]
            assert produto["custo"] == 100 and produto["capacidade_ml"] == 1000
    assert cadastro["movimentos"] == antes and cadastro["proximo_id"] == 2


def test_preco_nao_configurado_nao_vira_custo_ou_valor_inventado():
    cfg = ct.configuracao_padrao()
    conta = ct.calcular([_item()], cfg)
    assert not conta["completo"]
    assert any("preço" in falta for falta in conta["faltantes"])
    cadastro = {"produtos": {}}
    ct.sincronizar_catalogo(cadastro, cfg)
    assert all("custo" not in produto for produto in cadastro["produtos"].values())


def test_mudar_preco_ou_taxa_muda_assinatura():
    cfg = _config_com_precos_de_teste()
    antes = ct.assinatura(cfg)
    cfg["maquinas"][ct.R5200]["cores"]["BLACK"]["consumo_ml_m2"] = 3
    assert ct.assinatura(cfg) != antes


def test_mesmo_comando_valores_so_na_os_e_estimativa_da_h2525_identificada(tmp_path):
    cfg = _config()
    cfg["centro_custos_tintas"] = _config_com_precos_de_teste()
    entrada = tmp_path / "entrada"
    entrada.mkdir()
    nomes = ["1UN DECORFLEX IMPRESSO 5.00X0.50M_PAINEL.pdf", "1UN PS 1MM IMPRESSO 1.00X0.50M_PLACA.pdf"]
    for nome in nomes:
        with pymupdf.open() as doc:
            doc.new_page(width=200, height=200)
            doc.save(str(entrada / nome))
    resultado = processar_etiquetas(str(entrada), "TESTE", "G", "P", cfg, pasta_saida_base=str(tmp_path / "saida"))
    assert resultado and resultado["os"] and resultado["retirada"] and resultado["unificado"]
    os = _texto(resultado["os"])
    assert "Custo estimado de tinta" in os
    assert "DOCAN R5200" in os and "DOCAN H2525" in os
    assert "R$ 1,26" in os
    assert "Referência provisória da R5200" in os
    for caminho in [resultado["retirada"], resultado["unificado"]]:
        texto = _texto(caminho)
        assert "R$" not in texto and "Custo estimado de tinta" not in texto
    assert "Custo estimado de tinta" not in _texto(resultado["custos"])


def test_custos_tinta_paginam_em_os_grande_sem_encolher_ou_cortar_texto(tmp_path):
    cfg = _config()
    itens = [dict(_item(), arquivo=f"PECA{i}.pdf") for i in range(50)]
    dados = {"DECORFLEX": dict(contem_arquivos=True, area_total_m2=125)}
    caminho = gerar_os(str(tmp_path), "TESTE", "G", "P", itens, dados, ["DECORFLEX"], "09/10/2026 10:00",
                       cfg["materiais"], tintas_docan=_config_com_precos_de_teste())
    texto = _texto(caminho)
    assert "Total estimado de tinta" in texto and "R$ 62,75" in texto
    assert "R$" not in _texto(caminho_pdf(tmp_path, "TESTE"))


@pytest.mark.parametrize("valor", ["NaN", "Infinity", "-1", "abc"])
def test_cadastro_rejeita_precos_invalidos_sem_tocar_arquivos(valor):
    from gui_custos_tinta import JanelaCustosTinta
    class Campo:
        def __init__(self, valor):
            self.valor = valor
        def get(self):
            return self.valor
    objeto = SimpleNamespace(configuracao=ct.configuracao_padrao(),
                             campos={(ct.R5200, "CIANO"): {"preco_frasco": Campo(valor)}})
    with pytest.raises(ValueError):
        JanelaCustosTinta._ler_campos(objeto)


def test_preco_em_branco_pode_ser_salvo_sem_inventar_custo():
    from gui_custos_tinta import JanelaCustosTinta

    configuracao = ct.configuracao_padrao()
    campos = {}
    for maquina in (ct.R5200, ct.H2525):
        for cor in ct.CORES:
            dados = configuracao["maquinas"][maquina]["cores"][cor]
            campos[maquina, cor] = {
                "capacidade_ml": SimpleNamespace(get=lambda: "1000"),
                "preco_frasco": SimpleNamespace(get=lambda: ""),
                "consumo_ml_m2": SimpleNamespace(
                    get=lambda valor=str(dados["consumo_ml_m2"]): valor),
            }
    objeto = SimpleNamespace(
        configuracao=configuracao,
        campos=campos,
        provisoria=SimpleNamespace(get=lambda: True),
        materiais={},
    )

    salvo = JanelaCustosTinta._ler_campos(objeto)

    assert all(
        salvo["maquinas"][maquina]["cores"][cor]["preco_frasco"] is None
        for maquina in (ct.R5200, ct.H2525)
        for cor in ct.CORES
    )
