"""
Testes dos parametros de usinagem.

Os numeros de passes aqui NAO foram calculados por mim: sao os que o
Flavio disse de cabeca em 06/09/2026 ("MDF 15 vai dar 3 passes", "MDF 9
vai dar 2"). Se a conta do modulo divergir deles, a conta e que esta
errada.
"""
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from corte_parametros import (
    buscar, combinacoes_cadastradas, profundidade_de_corte, quantidade_de_passes,
)


def test_corta_sempre_um_milimetro_alem_da_chapa():
    """
    Regra do usuario: "todos deve passar 1mm alem da espessura da chapa".
    Parar exatamente na espessura deixa a peca presa por um filme.
    """
    assert profundidade_de_corte(10) == 11.0
    assert profundidade_de_corte(20) == 21.0
    assert profundidade_de_corte(6) == 7.0


@pytest.mark.parametrize("material, espessura, passes", [
    ("PVC", 10, 1),   # profundidade 11, passada 11 -> sai de uma vez
    ("PVC", 20, 2),   # profundidade 21, passada 11
    ("MDF", 6, 1),    # profundidade 7, passada 7
    ("MDF", 9, 2),    # dito pelo usuario: "vai dar 2 passes"
    ("MDF", 15, 3),   # dito pelo usuario: "vai dar 3 passes"
])
def test_passes_batem_com_o_que_o_usuario_disse(material, espessura, passes):
    assert buscar(material, espessura)["passes"] == passes


def test_a_passada_muda_com_a_espessura_nao_so_com_o_material():
    """
    MDF de 6 usa passada 7 (corta de uma vez); MDF de 9 e 15 usam 6.
    Guardar a passada so por material perderia essa diferenca.
    """
    assert buscar("MDF", 6)["passada_mm"] == 7.0
    assert buscar("MDF", 9)["passada_mm"] == 6.0
    assert buscar("MDF", 15)["passada_mm"] == 6.0


def test_aponta_pra_ferramenta_do_banco_do_aspire():
    """
    'grupo' e 'ferramenta' tem que bater letra por letra com o banco, que
    e como GetTool(grupo, nome) acha. Lidos do arquivo real do banco.
    """
    pvc = buscar("PVC", 10)
    assert pvc["grupo"] == "Fresa 4 mm"
    assert pvc["ferramenta"] == "Topo Raso (4 mm)"

    mdf = buscar("MDF", 15)
    assert mdf["grupo"] == "Fresa 6 mm"
    assert mdf["ferramenta"] == "Topo Raso (6 mm)"


def test_material_nao_cadastrado_devolve_nada_em_vez_de_chutar():
    """
    Chutar parametro de corte quebra fresa e estraga chapa. Quem chama
    tem que tratar a ausencia.
    """
    assert buscar("PS", 3) is None, "PS existe no estoque e ainda nao tem parametro"
    assert buscar("PVC", 3) is None, "cancelado pelo usuario em 06/09/2026"
    assert buscar("ACRILICO", 12) is None, "12mm nao existe no estoque"
    assert buscar("MDF", 15.0) is not None, "aceita float, arredonda pra espessura inteira"


def test_aceita_material_em_minusculo_e_com_espaco():
    assert buscar("  pvc  ", 10) == buscar("PVC", 10)


def test_passada_zero_nao_passa_calado():
    with pytest.raises(ValueError):
        quantidade_de_passes(10, 0)


def test_lista_o_que_esta_cadastrado():
    """A tela precisa saber o que falta, nao so o que tem."""
    combos = combinacoes_cadastradas()
    assert ("MDF", 6) in combos
    assert ("PVC", 20) in combos
    assert ("ACRILICO", 10) in combos
    assert len(combos) == 14


def test_letra_corta_dentro_por_dentro_e_fora_por_fora():
    """
    Regra do usuario, literal: "dentro por dentro e fora por fora".
    O buraco do 'O' usinado por fora sai maior que o desenho; o contorno
    da letra usinado por dentro sai menor.
    """
    from corte_parametros import LADO_DENTRO, LADO_FORA

    ordem = buscar("MDF", 15)["ordem"]
    assert [e["lado"] for e in ordem] == [LADO_DENTRO, LADO_FORA]


def test_o_interno_vem_primeiro_e_isso_nao_e_detalhe():
    """
    Assim que o contorno externo fecha, a peca solta da chapa e comeca a
    se mexer. Furo feito depois disso sai torto, quando nao arranca a
    peca. A ordem e regra de producao, nao preferencia.
    """
    ordem = buscar("PVC", 10)["ordem"]
    assert ordem[0]["camada"] == "CORTE INTERNO"
    assert ordem[1]["camada"] == "CORTE EXTERNO"


def test_acrilico_usa_passada_menor_porque_trinca():
    """
    Acrilico e o material mais delicado da casa: passada de 3 mm, menos
    da metade das outras. Calor derrete a borda e corte forcado trinca a
    chapa.
    """
    for espessura in (1, 2, 3, 4, 5, 6, 7, 8, 10):
        p = buscar("ACRILICO", espessura)
        assert p is not None, f"acrilico de {espessura}mm nao cadastrado"
        assert p["passada_mm"] == 3.0
        assert p["ferramenta"] == "Topo Raso (6 mm)"


def test_acrilico_de_6_desce_ate_7():
    """Dito pelo usuario: "de acrilico e 6mm a profundidade C: precisa ser de 7 mm"."""
    p = buscar("ACRILICO", 6)
    assert p["profundidade_mm"] == 7.0
    assert p["passes"] == 3          # 7 / 3 arredondado pra cima


def test_o_corte_e_convencional_nao_subida():
    """
    Dito pelo usuario duas vezes: "o corte pode ser padrao convencional" e
    "corte precisa ser convencional". E confirmado na tela do Aspire:
    CutDirection = 0 acende "Convencional".

    A primeira versao deste cadastro dizia "subida". So nao virou peca
    torta porque o gadget ja usava o valor certo — mas cadastro que
    contradiz a maquina e pior que cadastro nenhum.
    """
    from corte_parametros import DIRECAO_CONVENCIONAL

    for material, espessura in (("PVC", 10), ("MDF", 15), ("ACRILICO", 6)):
        assert buscar(material, espessura)["direcao"] == DIRECAO_CONVENCIONAL


def test_todo_material_tem_fresa_avanco_e_rotacao():
    """
    "Deixar com mesmo parametro, so mudar a fresa" — entao avanco, ataque
    e rotacao sao iguais em tudo, e o que muda e o diametro.
    """
    from corte_parametros import AVANCO_MM_MIN, ATAQUE_MM_MIN, ROTACAO_RPM

    for material, espessura in combinacoes_cadastradas():
        p = buscar(material, espessura)
        assert p["avanco_mm_min"] == AVANCO_MM_MIN
        assert p["ataque_mm_min"] == ATAQUE_MM_MIN
        assert p["rotacao_rpm"] == ROTACAO_RPM
        assert p["diametro_mm"] in (4.0, 6.0)


def test_pvc_usa_fresa_de_4_o_resto_usa_a_de_6():
    """"Normalmente vai ser usada a de 6mm" — a de 4 e so do PVC."""
    assert buscar("PVC", 10)["diametro_mm"] == 4.0
    assert buscar("PVC", 20)["diametro_mm"] == 4.0
    for material, espessura in combinacoes_cadastradas():
        if material != "PVC":
            assert buscar(material, espessura)["diametro_mm"] == 6.0


def test_tudo_declarado_em_milimetro():
    """
    O Tool do Aspire nasce em POLEGADA. Em 06/09/2026 o diametro 4 virou
    4 polegadas: raio de 50,8mm marcado sobre o vetor, e a passada de 11
    teria virado 279mm de profundidade numa chapa de 10.

    Por isso a unidade viaja junto do valor: quem consome tem como
    conferir antes de escrever na ferramenta.
    """
    from corte_parametros import UNIDADE
    assert UNIDADE == "mm"
    assert buscar("PVC", 10)["unidade"] == "mm"


def test_a_tabela_exportada_pro_lua_bate_com_o_cadastro(tmp_path):
    """
    O gadget le essa tabela. Se ela divergir do cadastro, a maquina corta
    com numero que ninguem revisou.
    """
    from corte_parametros import exportar_para_lua

    destino = exportar_para_lua(tmp_path / "p.lua")
    texto = destino.read_text(encoding="utf-8")

    assert 'unidade = "mm"' in texto, "sem isso o gadget nao tem como conferir a unidade"
    assert "nao edite" in texto, "arquivo gerado tem que avisar que e gerado"
    for material, espessura in combinacoes_cadastradas():
        p = buscar(material, espessura)
        assert f'["{material} {espessura}"]' in texto
        assert f'passada = {p["passada_mm"]}' in texto
        assert f'profundidade = {p["profundidade_mm"]}' in texto


def test_gera_um_atalho_de_menu_por_material(tmp_path):
    """
    Pedido do usuario: escolher pelo menu do Aspire em vez de editar uma
    linha do script. Um arquivo por material, e o nome do arquivo vira o
    nome no menu com '_' virando espaco.
    """
    from corte_parametros import gerar_gadgets

    gerados, faltando = gerar_gadgets(tmp_path, instalar=True)
    assert len(gerados) == 8, "as oito combinacoes que a casa corta"
    assert faltando == [], "nao falta mais nenhuma do foco"

    nomes = {d.name for _, d, _ in gerados}
    assert "Corte_Automatico_PVC_10.lua" in nomes
    assert "Corte_Automatico_MDF_9.lua" in nomes
    assert "Corte_Automatico_ACRILICO_6.lua" in nomes

    for chave, destino, _ in gerados:
        texto = destino.read_text(encoding="ascii")
        assert f'MATERIAL_DO_GADGET = "{chave}"' in texto
        assert "corte_nucleo.lua" in texto, "o atalho tem que chamar o nucleo"
        assert "nao edite" in texto, "arquivo gerado avisa que e gerado"


def test_atalho_nao_carrega_logica_nenhuma(tmp_path):
    """
    Se o atalho tivesse logica, seriam 14 copias pra manter em dia e uma
    correcao esqueceria treze. Ele diz o material e chama o nucleo.
    """
    from corte_parametros import gerar_gadgets

    gerados, _ = gerar_gadgets(tmp_path)
    _, _, conteudo = gerados[0]
    codigo = [l for l in conteudo.splitlines() if l.strip() and not l.startswith("--")]
    assert len(codigo) == 2, f"esperava 2 linhas de codigo, achei {codigo}"


def test_menu_e_menor_que_o_cadastro_de_proposito():
    """
    O Flavio apontou as combinacoes que a casa realmente corta. Menu com
    material que ninguem usa atrapalha — mas o cadastro segue completo,
    porque o acrilico de 1, 2, 3, 5, 7 e 10 segue a mesma regra e guardar
    nao custa nada.
    """
    from corte_parametros import MENU_FOCO

    assert len(MENU_FOCO) < len(combinacoes_cadastradas())
    for material, espessura in MENU_FOCO:
        assert buscar(material, espessura) is not None
    assert buscar("ACRILICO", 5) is not None, "fora do menu, mas o cadastro sabe"


def test_todo_material_desce_exatamente_1mm_alem_da_chapa():
    """
    Sem excecao. Houve uma por algumas horas (PVC 3mm com 0,5), cancelada
    antes de ir pra maquina — ver o comentario de FOLGA_PASSANTE_MM.
    """
    for material, espessura in combinacoes_cadastradas():
        assert buscar(material, espessura)["profundidade_mm"] == espessura + 1.0


def test_le_material_e_espessura_do_nome_do_arquivo():
    """
    Tira a escolha do material da cabeca de quem opera. Clicar no atalho
    errado corta com a passada errada, e isso NAO da erro: da peca
    estragada.
    """
    from corte_parametros import material_e_espessura

    assert material_e_espessura("1UN PVC 10MM BRANCO + SANCA 1,21x0,22M.pdf") == ("PVC", 10)
    assert material_e_espessura("2UN MDF 15MM RECORTE CONTORNO 99X90CM.pdf") == ("MDF", 15)
    assert material_e_espessura("4UN ACRILICO 4MM CRISTAL RECORTE.pdf") == ("ACRILICO", 4)


def test_espessura_sai_do_cadastro_nao_de_qualquer_numero_com_mm():
    """
    Armadilha real: "PVC 20MM ... 1500MM de largura" tem dois numeros
    seguidos de MM. So vale o que existe como espessura daquele material —
    senao a peca sairia com 1500mm de profundidade programada.
    """
    from corte_parametros import material_e_espessura

    assert material_e_espessura("1UN PVC 20MM RECORTE 1500MM de largura.pdf") == ("PVC", 20)


def test_nome_sem_espessura_devolve_nada():
    """
    "ACRILICO CRISTAL" sem milimetro nao diz a espessura. Chutar aqui e
    escolher a passada errada.
    """
    from corte_parametros import atalho_do_menu, material_e_espessura

    assert material_e_espessura("2UN LOGO EM ACRILICO CRISTAL 0.95X0.17M.pdf") is None
    assert atalho_do_menu("2UN LOGO EM ACRILICO CRISTAL 0.95X0.17M.pdf") is None


def test_atalho_so_existe_pro_que_esta_no_menu():
    """Acrilico de 5mm esta cadastrado mas fora do menu: nao ha o que clicar."""
    from corte_parametros import atalho_do_menu

    assert atalho_do_menu("1UN ACRILICO 6MM RECORTE.pdf") == "Corte Automatico ACRILICO 6"
    assert atalho_do_menu("1UN ACRILICO 5MM RECORTE.pdf") is None
