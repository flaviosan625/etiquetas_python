"""Referência fornecida pelo usuário, projeções e limites do planejamento."""
import pytest
import tempo_impressao as tempo


def test_reproduz_trabalho_de_referencia_sem_arredondar_taxa():
    estimativa = tempo.estimar(tempo.MAQUINA_DOCAN, 4.85 * 27.251)
    assert estimativa["segundos"] == pytest.approx(9400)
    assert tempo.duracao(estimativa["segundos"]) == "2h36min40s"
    assert tempo.duracao(estimativa["segundos"] * .3) == "47min00s"
    assert tempo.duracao(estimativa["segundos"] * .7) == "1h49min40s"
    assert estimativa["m2_por_hora"] == pytest.approx(50.62, abs=.005)
    assert estimativa["minutos_por_m2"] != 1.19
    assert estimativa["passadas_referencia"]


@pytest.mark.parametrize("passadas,total", [(2,2350),(4,4700),(5,5875),(6,7050),
                                           (8,9400),(10,11750),(12,14100),
                                           (16,18800),(24,28200),(32,37600)])
def test_projecao_por_passadas_reproduz_tabela(passadas, total):
    estimativa = tempo.estimar(tempo.MAQUINA_DOCAN, tempo.AREA_REFERENCIA_M2, passadas)
    assert estimativa["segundos"] == pytest.approx(total)
    assert not estimativa["passadas_referencia"]
    assert estimativa["projecao_passadas"] == (passadas != 8)


@pytest.mark.parametrize("area", [None, "abc", float("nan"), float("inf"), -1])
def test_area_desconhecida_ou_invalida_nao_inventa_tempo(area):
    assert tempo.estimar(tempo.MAQUINA_DOCAN, area) is None


@pytest.mark.parametrize("passadas", [0, 3, 8.5, "abc", True, float("nan"), float("inf")])
def test_passadas_invalidas_sao_recusadas(passadas):
    with pytest.raises(ValueError):
        tempo.estimar(tempo.MAQUINA_DOCAN, 10, passadas)


def test_calibracao_nao_se_aplica_a_outra_impressora():
    assert tempo.estimar("SWJ320A", 100) is None
    assert tempo.estimar("DOCAN H2525", 100) is None


def test_cem_metros_quadrados_usa_taxa_precisa():
    assert tempo.duracao(tempo.estimar(tempo.MAQUINA_DOCAN, 100)["segundos"]) == "1h58min32s"


def test_registro_antigo_indica_referencia_sem_confundir_reimpressoes_com_perfil():
    registro = {"maquina": tempo.MAQUINA_DOCAN, "area_total_m2": 10, "passadas": ["trabalho1", "trabalho2"]}
    estimativa = tempo.do_registro(registro)
    assert estimativa["passadas"] == 8
    assert "referência" in tempo.texto(estimativa)


def test_conta_gravada_permanece_reproduzivel():
    gravada = tempo.estimar(tempo.MAQUINA_DOCAN, 100, 4)
    assert tempo.do_registro({"maquina": tempo.MAQUINA_DOCAN, "estimativa_impressao": gravada}) == gravada
