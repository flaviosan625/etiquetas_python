"""Cadastro e consumo da tabela fornecida; nenhum teste usa dados reais."""
import copy
from decimal import Decimal, ROUND_HALF_UP
import pathlib
import sys
from types import SimpleNamespace

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import pytest
import catalogo_acrilicos as catalogo
import consumo_custo
import custos
import dimensoes
import estoque


def _item(variante, pronto=True):
    return dict(arquivo='1UN ACRILICO CORTE DIRETO.pdf', categoria='ACRILICO',
                variante=variante, quantidade=1, categoria_extra=None, pronto=pronto,
                vinculo='pedido', dimensao=dict(largura_m=1.8, altura_m=0.9, area_m2=1.62))


@pytest.mark.parametrize('espessura,preco', [
    ('2MM', 212.83), ('3MM', 290.30), ('4MM', 387.05), ('5MM', 483.80),
    ('6MM', 580.56), ('8MM', 774.08), ('10MM', 921.53),
])
def test_precos_cristal_e_acrescimos(espessura, preco):
    variantes = {(v['espessura'], v['cor']): v for v in catalogo.variantes()}
    assert variantes[espessura, 'CRISTAL']['preco_m2'] * 2 == preco
    for cor, fator in [('LEITOSO', '1.08')] + [(c, '1.15') for c in catalogo.CORES]:
        esperado = float((Decimal(str(preco)) * Decimal(fator)).quantize(Decimal('.01'), rounding=ROUND_HALF_UP))
        assert variantes[espessura, cor]['preco_m2'] * 2 == esperado


@pytest.mark.parametrize('cor,espessura,preco', [
    ('ESPELHADO PRATA', '1.5MM', 192.63), ('ESPELHADO PRATA', '1.8MM', 225.79),
    ('ESPELHADO PRATA', '2MM', 249.77), ('ESPELHADO PRATA', '3MM', 327.99),
    ('ESPELHADO DOURADO', '1.5MM', 221.53), ('ESPELHADO DOURADO', '2MM', 272.18),
    ('ESPELHADO DOURADO', '3MM', 356.18), ('FUNDO INFINITO', '2MM', 315.00),
    ('FUNDO INFINITO', '2.5MM', 342.00),
] + [('ESPELHADO ' + c, '2MM', 293.95) for c in catalogo.CORES_ESPELHADAS])
def test_precos_especiais_sem_acrescimo(cor, espessura, preco):
    variante = next(v for v in catalogo.variantes() if (v['cor'], v['espessura']) == (cor, espessura))
    assert variante['preco_m2'] * 2 == preco


@pytest.mark.parametrize('variante', catalogo.variantes(), ids=lambda v: v['espessura'] + '-' + v['cor'])
def test_todas_variantes_vinculam_estoque_e_custo_da_chapa_consumida(variante):
    materiais = {'ACRILICO': catalogo.configuracao()}
    dados = dict(produtos=copy.deepcopy(estoque.CATALOGO_PADRAO), movimentos=[])
    item = _item(variante)
    os_custo = custos.calcular([item], materiais)
    centro = consumo_custo.calcular([item], dict(materiais=materiais))
    baixa = estoque.prever_saida_os(dados, [item], materiais)
    preco_chapa = variante['preco_m2'] * 2
    assert os_custo['total'] == pytest.approx(preco_chapa)
    assert centro['subtotal_material'] == pytest.approx(preco_chapa)
    assert centro['linhas'][0]['consumo'] == 2
    assert centro['linhas'][0]['sobra'] == pytest.approx(.38)
    assert centro['completo']
    assert len(baixa) == 1
    assert not baixa[0]['ambiguo']
    assert baixa[0]['descontado'] == 1
    assert dados['produtos'][baixa[0]['codigo']]['custo'] == pytest.approx(preco_chapa)
    assert dados['movimentos'] == []


def test_pendente_nao_e_cobrado_e_outro_material_nao_e_cobrado():
    cfg = dict(materiais={'ACRILICO': catalogo.configuracao(),
                         'PS': dict(tipo='chapa', largura_cm=200, comprimento_cm=100, preco_m2=30)})
    resultado = consumo_custo.calcular([_item(catalogo.variantes()[0], pronto=False)], cfg)
    assert resultado['subtotal_material'] == 0
    assert resultado['produzidos'] == 0
    assert resultado['linhas'][0]['consumo'] == 0
    assert resultado['linhas'][1]['usado'] is False


def test_importacao_preserva_historico_saldos_e_e_idempotente():
    movimento = dict(id=1, produto='ACRILICO_2MM_CRISTAL', quantidade=20, tipo='entrada')
    produto = copy.deepcopy(estoque.CATALOGO_PADRAO['ACRILICO_2MM_CRISTAL'])
    produto.update(custo=None, minimo=6, maximo=60, codigo_planilha='original')
    dados = dict(produtos={'ACRILICO_2MM_CRISTAL': produto}, movimentos=[movimento], proximo_id=2)
    cfg = dict(materiais={'LONA': {'largura_cm': 320}, 'ACRILICO': dict(variantes=[
        dict(espessura='2MM', cor='CRISTAL', rotulo='Cristal personalizado'),
        dict(espessura='7MM', cor='CRISTAL'),
    ])})
    catalogo.cadastrar(cfg, dados)
    primeiro = copy.deepcopy((cfg, dados))
    catalogo.cadastrar(cfg, dados)
    assert (cfg, dados) == primeiro
    assert dados['movimentos'] == [movimento]
    assert dados['proximo_id'] == 2
    assert estoque.saldo_produto(dados, 'ACRILICO_2MM_CRISTAL') == 20
    assert estoque.saldo_produto(dados, 'ACRILICO_2MM_AZUL') == 0
    assert produto['minimo'] == 6 and produto['maximo'] == 60
    assert produto['codigo_planilha'] == 'original'
    assert cfg['materiais']['LONA'] == {'largura_cm': 320}
    assert cfg['materiais']['ACRILICO']['variantes'][0]['rotulo'] == 'Cristal personalizado'
    assert 'preco_m2' not in cfg['materiais']['ACRILICO']['variantes'][1]


@pytest.mark.parametrize('nome,espessura,cor', [
    ('ACRÍLICO CRISTAL 2,0 mm', '2MM', 'CRISTAL'),
    ('ACRILICO TRANSLÚCIDO 3MM', '3MM', 'LEITOSO'),
    ('ACRILICO BRANCO 4 MM', '4MM', 'LEITOSO'),
    ('ACRILICO ESPELHADO PRATA 1,5 mm', '1.5MM', 'ESPELHADO PRATA'),
    ('ACRILICO ESPELHADO 1.80MM PRATA', '1.8MM', 'ESPELHADO PRATA'),
    ('ACRILICO_FUNDO-INFINITO_2,5MM', '2.5MM', 'FUNDO INFINITO'),
    ('ACRILICO_AZUL_2MM', '2MM', 'AZUL'),
    ('ACRILICO ESPELHADO 2MM AZUL', '2MM', 'ESPELHADO AZUL'),
    ('ACRILICO 2 MM LILÁS ESPELHADO', '2MM', 'ESPELHADO LILAS'),
    ('ACRILICO 2MM ROSÉ', '2MM', 'ROSE'),
    ('ACRILICO.CRISTAL.2MM.pdf', '2MM', 'CRISTAL'),
])
def test_identifica_espessura_cor_e_acabamento(nome, espessura, cor):
    v = dimensoes.identificar_variante(nome, catalogo.variantes())
    assert (v['espessura'], v['cor']) == (espessura, cor)


@pytest.mark.parametrize('nome', ['ACRILICO ESPELHADO AZUL 3MM', 'ACRILICO CRISTAL 1.5MM',
                                'ACRILICO CRISTAL 1,5 MM', 'ACRILICO FUNDO INFINITO AZUL 5MM'])
def test_nao_troca_material_ou_espessura_na_falta_de_preco(nome):
    assert dimensoes.identificar_variante(nome, catalogo.variantes()) is None


def test_nome_do_trabalho_nao_muda_variante_de_outro_material():
    variantes = [dict(espessura='9MM')]
    assert dimensoes.identificar_variante('MDF 9MM estrutura ESPELHO', variantes) == variantes[0]


def test_editar_preco_preserva_fracao_do_centavo_e_aliases():
    import gui
    v = next(v for v in catalogo.variantes() if v['cor'] == 'LEITOSO' and v['espessura'] == '3MM')
    def campo(texto):
        return SimpleNamespace(get=lambda: texto)
    recebido = []
    janela = SimpleNamespace(linhas_variantes=[dict(dados=v, espessura=campo(v['espessura']),
        cor=campo(v['cor']), rotulo=campo(''), preco_m2=campo(gui._preco_na_tela(v['preco_m2'])))],
        ao_salvar=recebido.extend, destroy=lambda: None)
    gui.JanelaVariantes._salvar(janela)
    assert recebido[0] == v
    assert gui._preco_digitado(gui._preco_na_tela(106.415)) == (106.415, True)
    assert gui._preco_na_tela(18.5) == '18,50'
