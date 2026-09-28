import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import pytest

import caminhos
import estoque
from estoque import confirmar_saida_os, pedido_ja_teve_saida, calcular_consumo, prever_saida_os, produtos_por_categoria


@pytest.fixture(autouse=True)
def _estoque_de_teste(monkeypatch, tmp_path):
    """
    salvar_estoque() grava em caminhos.ESTOQUE — sem isolar isso, QUALQUER
    teste que chame uma função que persiste (registrar_movimento,
    confirmar_saida_os, etc.) sobrescreve o estoque.json REAL de produção.
    Isso aconteceu de verdade ao escrever este arquivo de teste
    (2026-08-26): apagou os 51 produtos e os movimentos reais, restaurado
    via `git checkout -- estoque.json` logo em seguida. Por isso é autouse:
    nenhum teste daqui depende de lembrar de chamar.
    """
    monkeypatch.setattr(caminhos, "ESTOQUE", tmp_path / "estoque_teste.json")


def _isolar_arquivo_estoque(monkeypatch, tmp_path):
    """Mantido pros testes antigos; o isolamento de verdade é a fixture autouse acima."""
    monkeypatch.setattr(caminhos, "ESTOQUE", tmp_path / "estoque_teste.json")


def _estoque_minimo():
    return {
        "produtos": {
            "LONA_TESTE": {
                "descricao": "Lona Teste", "tipo": "rolo", "unidade": "rolo",
                "comprimento_rolo_m": 50, "categoria_vinculada": "LONA",
                "variante_vinculada": None, "minimo": 0, "maximo": 0,
                "codigo_planilha": None,
            },
        },
        "movimentos": [], "proximo_id": 1, "producao_mensal": [],
    }


def test_pedido_ja_teve_saida_falso_quando_nunca_confirmado(monkeypatch, tmp_path):
    _isolar_arquivo_estoque(monkeypatch, tmp_path)
    estoque_dados = _estoque_minimo()
    assert pedido_ja_teve_saida(estoque_dados, "CLIENTE (01/01/2026 10:00:00)") is False


def test_pedido_ja_teve_saida_verdadeiro_depois_de_confirmar(monkeypatch, tmp_path):
    """
    Regressão do bug conhecido (documentado desde 2026-08-25, corrigido
    agora): confirmar_saida_os não tinha como saber se o MESMO pedido já
    tinha sido descontado antes — escolher o mesmo arquivo de OS duas
    vezes dobrava o consumo em silêncio. pedido_ja_teve_saida é o que
    permite a tela avisar antes disso acontecer de novo.
    """
    _isolar_arquivo_estoque(monkeypatch, tmp_path)
    estoque_dados = _estoque_minimo()
    materiais_config = {"LONA": {"tipo": "rolo", "largura_cm": 320.0, "comprimento_cm": 5000.0}}
    itens = [{
        "categoria": "LONA", "variante": None, "quantidade": 1,
        "dimensao": {"area_m2": 120.0, "largura_m": 2.0, "altura_m": 60.0},
    }]
    nome_pedido = "CLIENTE TESTE (01/01/2026 10:00:00)"

    resumo = confirmar_saida_os(estoque_dados, itens, materiais_config, nome_pedido)
    assert resumo[0]["descontado"] == 1.2  # 60 m de um rolo de 50 m = 1,2 rolo

    assert pedido_ja_teve_saida(estoque_dados, nome_pedido) is True
    assert pedido_ja_teve_saida(estoque_dados, "OUTRO CLIENTE (02/01/2026 10:00:00)") is False


def _estoque_adesivo_ambiguo():
    def _adesivo(descricao):
        return {
            "descricao": descricao, "tipo": "rolo", "unidade": "rolo",
            "comprimento_rolo_m": 50, "categoria_vinculada": "ADESIVO",
            "variante_vinculada": None, "minimo": 0, "maximo": 0,
            "codigo_planilha": None,
        }
    return {
        "produtos": {
            "ADESIVO_BRANCO_FOSCO_127": _adesivo("Adesivo Branco Fosco"),
            "ADESIVO_CRISTAL_127": _adesivo("Adesivo Cristal"),
        },
        "movimentos": [], "proximo_id": 1, "producao_mensal": [],
    }


def _itens_adesivo():
    materiais_config = {"ADESIVO": {"tipo": "rolo", "largura_cm": 127.0, "comprimento_cm": 5000.0}}
    itens = [{
        "categoria": "ADESIVO", "variante": None, "quantidade": 1,
        "dimensao": {"area_m2": 63.5, "largura_m": 1.27, "altura_m": 50.0},
    }]
    return itens, materiais_config


def test_produtos_por_categoria_lista_os_candidatos_ambiguos():
    estoque_dados = _estoque_adesivo_ambiguo()
    candidatos = produtos_por_categoria(estoque_dados, "ADESIVO")
    assert {codigo for codigo, _ in candidatos} == {"ADESIVO_BRANCO_FOSCO_127", "ADESIVO_CRISTAL_127"}


def test_sem_resolucao_manual_adesivo_continua_ambiguo(monkeypatch, tmp_path):
    _isolar_arquivo_estoque(monkeypatch, tmp_path)
    estoque_dados = _estoque_adesivo_ambiguo()
    itens, materiais_config = _itens_adesivo()

    previsao = prever_saida_os(estoque_dados, itens, materiais_config)

    assert previsao[0]["produto"] is None
    assert previsao[0]["ambiguo"] is True


def test_resolucao_manual_desconta_o_produto_escolhido(monkeypatch, tmp_path):
    _isolar_arquivo_estoque(monkeypatch, tmp_path)
    estoque_dados = _estoque_adesivo_ambiguo()
    itens, materiais_config = _itens_adesivo()
    resolucoes = {"ADESIVO": "ADESIVO_CRISTAL_127"}

    resumo = confirmar_saida_os(estoque_dados, itens, materiais_config, "CLIENTE (01/01/2026 10:00:00)", resolucoes_manuais=resolucoes)

    assert resumo[0]["produto"] == "Adesivo Cristal"
    assert resumo[0]["ambiguo"] is False
    assert estoque.saldo_produto(estoque_dados, "ADESIVO_CRISTAL_127") == -1
    assert estoque.saldo_produto(estoque_dados, "ADESIVO_BRANCO_FOSCO_127") == 0, "so o escolhido pode ser descontado"


def test_resolucao_manual_pra_outra_categoria_nao_afeta_esta(monkeypatch, tmp_path):
    _isolar_arquivo_estoque(monkeypatch, tmp_path)
    estoque_dados = _estoque_adesivo_ambiguo()
    itens, materiais_config = _itens_adesivo()
    resolucoes = {"OUTRA_CATEGORIA": "ADESIVO_CRISTAL_127"}

    previsao = prever_saida_os(estoque_dados, itens, materiais_config, resolucoes_manuais=resolucoes)

    assert previsao[0]["produto"] is None
    assert previsao[0]["ambiguo"] is True


def test_resolucao_manual_com_codigo_inexistente_nao_quebra(monkeypatch, tmp_path):
    _isolar_arquivo_estoque(monkeypatch, tmp_path)
    estoque_dados = _estoque_adesivo_ambiguo()
    itens, materiais_config = _itens_adesivo()
    resolucoes = {"ADESIVO": "CODIGO_QUE_NAO_EXISTE"}

    previsao = prever_saida_os(estoque_dados, itens, materiais_config, resolucoes_manuais=resolucoes)

    assert previsao[0]["produto"] is None
    assert previsao[0]["ambiguo"] is True


def test_calcular_consumo_multiplica_pela_quantidade_do_item():
    """
    Regressão de bug real (achado pelo usuário, 2026-08-29): 'dimensao'
    guarda a medida de UMA peça, mas um item "4UN PVC..." representa 4
    peças físicas — sem multiplicar pela quantidade, a baixa de estoque
    sempre debitava como se fosse 1 peça só, não importa o que o nome
    do arquivo dizia. Peça de 1,00 x 2,00m (cabe exata na largura do
    rolo de 1,00m, sem sobra) com quantidade 4 tem que consumir 8m de
    rolo (4 peças x 2m cada), não 2m.
    """
    materiais_config = {"LONA": {"tipo": "rolo", "largura_cm": 100.0, "comprimento_cm": 5000.0}}
    itens = [{
        "categoria": "LONA", "variante": None, "quantidade": 4,
        "dimensao": {"area_m2": 2.0, "largura_m": 1.0, "altura_m": 2.0},
    }]

    resultado = calcular_consumo(itens, materiais_config)
    assert len(resultado) == 1
    assert resultado[0]["metros"] == 8.0
    assert resultado[0]["area_m2"] == 8.0


# ----------------------------------------------- lote e rolo em fração (28/09/2026)

def _estoque_lona_e_ps():
    dados = _estoque_minimo()
    dados["produtos"]["PS_2MM_BRANCO"] = {
        "descricao": "PS 2mm Branco", "tipo": "chapa", "unidade": "chapa", "categoria_vinculada": "PS",
        "variante_vinculada": {"espessura": "2MM", "cor": "BRANCO"}, "minimo": 0, "maximo": 0,
        "codigo_planilha": None, "custo": 75.0,
    }
    return dados


_MATERIAIS = {
    "LONA": {"tipo": "rolo", "largura_cm": 320.0, "comprimento_cm": 5000.0},
    "PS": {"tipo": "chapa", "largura_cm": 200.0, "comprimento_cm": 100.0,
           "variantes": [{"espessura": "2MM", "cor": "BRANCO", "preco_m2": 40.0}]},
}


def _peca(categoria, largura, altura, quantidade=1, variante=None):
    return {"categoria": categoria, "variante": variante, "quantidade": quantidade,
            "dimensao": {"largura_m": largura, "altura_m": altura, "area_m2": largura * altura}}


def test_consumo_e_do_lote_encaixado():
    """Três lonas de 1,00 × 2,00 num rolo de 3,20 saem lado a lado: 2 m, não 6 m."""
    resultado = calcular_consumo([_peca("LONA", 1.0, 2.0, 3)], _MATERIAIS)
    assert resultado[0]["metros"] == 2.0
    assert resultado[0]["desperdicio_m2"] == pytest.approx(0.4)


def test_pedido_pequeno_de_rolo_deixa_rastro_e_se_desfaz():
    """
    Regressão (28/09/2026): 12 m de lona não fechavam um rolo, iam pra um
    contador solto e o histórico não via nada — nem o aviso de baixa repetida.
    """
    dados = _estoque_lona_e_ps()
    estoque.registrar_movimento(dados, "LONA_TESTE", "entrada", 3)
    nome = "CLIENTE (28/09/2026 10:00:00)"

    resumo = confirmar_saida_os(dados, [_peca("LONA", 3.0, 12.4)], _MATERIAIS, nome)

    assert resumo[0]["descontado"] == pytest.approx(0.248)
    assert estoque.saldo_produto(dados, "LONA_TESTE") == pytest.approx(2.752)
    assert pedido_ja_teve_saida(dados, nome) is True
    saida = dados["movimentos"][-1]
    assert "12.40 m" in saida["observacao"] and "estimativa" in saida["observacao"]
    estoque.desfazer_movimento(dados, saida["id"])
    assert estoque.saldo_produto(dados, "LONA_TESTE") == 3


def test_chapa_sai_em_chapas_inteiras_do_lote():
    dados = _estoque_lona_e_ps()
    ps = {"espessura": "2MM", "cor": "BRANCO"}
    resumo = confirmar_saida_os(dados, [_peca("PS", 1.80, 0.50, 4, ps)], _MATERIAIS, "C (28/09/2026 10:00:00)")
    assert resumo[0]["descontado"] == 2
    assert estoque.saldo_produto(dados, "PS_2MM_BRANCO") == -2


def test_variante_com_preco_ainda_acha_o_produto():
    """A variante da peça é cópia do config e pode trazer preço e rótulo: vale espessura e cor."""
    dados = _estoque_lona_e_ps()
    ps = {"espessura": "2MM", "cor": "BRANCO", "preco_m2": 40.0, "rotulo": "PS BRILHO"}
    previsao = prever_saida_os(dados, [_peca("PS", 1.0, 1.0, 1, ps)], _MATERIAIS)
    assert previsao[0]["codigo"] == "PS_2MM_BRANCO"


def test_contador_antigo_de_rolo_aberto_vira_ajuste_na_carga():
    dados = _estoque_minimo()
    dados["produtos"]["LONA_TESTE"]["acumulado_m"] = 12.5
    estoque.salvar_estoque(dados)

    carregado = estoque.carregar_estoque()

    assert "acumulado_m" not in carregado["produtos"]["LONA_TESTE"]
    assert estoque.saldo_produto(carregado, "LONA_TESTE") == pytest.approx(-0.25)
    assert "12.50 m" in carregado["movimentos"][-1]["observacao"]
    assert "acumulado_m" not in estoque.carregar_estoque()["produtos"]["LONA_TESTE"]


def test_editar_produto_nao_apaga_o_custo():
    """A tela de cadastro não tem campo de custo: editar a descrição levava o custo junto."""
    dados = _estoque_lona_e_ps()
    estoque.atualizar_produto(dados, "PS_2MM_BRANCO", "chapa", "PS 2mm Branco Brilho", categoria_vinculada="PS",
                              variante={"espessura": "2MM", "cor": "BRANCO"})
    assert dados["produtos"]["PS_2MM_BRANCO"]["custo"] == 75.0


def test_salvar_nao_deixa_arquivo_pela_metade():
    estoque.salvar_estoque(_estoque_minimo())
    assert caminhos.ESTOQUE.exists()
    assert not caminhos.ESTOQUE.with_name(caminhos.ESTOQUE.name + ".tmp").exists()


def test_saldo_de_rolo_como_se_conta_na_prateleira():
    lona = _estoque_minimo()["produtos"]["LONA_TESTE"]
    assert estoque.descrever_saldo(lona, 2.752) == "2 fechado(s) + aberto com 37,6 m (137,6 m)"
    assert estoque.descrever_saldo(lona, 3) == "3 rolo (150 m)"
    assert estoque.formatar_quantidade(lona, -0.248) == "-0,248 rolo (-12,4 m)"
    chapa = _estoque_lona_e_ps()["produtos"]["PS_2MM_BRANCO"]
    assert estoque.descrever_saldo(chapa, 7) == "7 chapa"


def test_rolo_aberto_se_lanca_em_metros():
    lona = _estoque_minimo()["produtos"]["LONA_TESTE"]
    assert estoque.interpretar_quantidade(lona, "37,6m") == pytest.approx(0.752)
    assert estoque.interpretar_quantidade(lona, "2") == 2
    chapa = _estoque_lona_e_ps()["produtos"]["PS_2MM_BRANCO"]
    with pytest.raises(ValueError):
        estoque.interpretar_quantidade(chapa, "3m")
    with pytest.raises(ValueError):
        estoque.interpretar_quantidade(lona, "0")


def test_conferir_cadastro_acha_o_que_nao_conversa():
    dados = _estoque_lona_e_ps()
    materiais = {
        "LONA": {"tipo": "rolo", "largura_cm": 320.0, "comprimento_cm": 5000.0},
        "PS": {"tipo": "chapa", "largura_cm": 200.0, "comprimento_cm": 100.0,
               "variantes": [{"espessura": "2MM", "cor": "BRANCO", "preco_m2": 40.0},
                             {"espessura": "3MM", "cor": "PRETO"}]},
        "ADESIVO": {"tipo": "rolo", "largura_cm": 127.0, "comprimento_cm": 5000.0},
    }
    dados["produtos"]["PS_1MM_PRETO"] = dict(dados["produtos"]["PS_2MM_BRANCO"], descricao="PS 1mm Preto",
                                             variante_vinculada={"espessura": "1MM", "cor": "PRETO"})

    r = estoque.conferir_cadastro(dados, materiais)

    assert r["sem_produto"] == ["PS 3MM · PRETO", "ADESIVO"]
    assert r["sem_material"] == ["PS 1mm Preto"]


def test_chapa_sem_espessura_no_nome_deixa_escolher_o_produto():
    """"PS 1,00X0,50M" sem o "2MM": era "sem produto vinculado"; agora quem dá baixa escolhe."""
    dados = _estoque_lona_e_ps()
    itens = [_peca("PS", 1.0, 0.5, 2)]

    previsao = prever_saida_os(dados, itens, _MATERIAIS)
    assert previsao[0]["produto"] is None and previsao[0]["ambiguo"] is True

    resumo = confirmar_saida_os(dados, itens, _MATERIAIS, "C (28/09/2026 11:00:00)",
                                resolucoes_manuais={"PS": "PS_2MM_BRANCO"})
    assert resumo[0]["codigo"] == "PS_2MM_BRANCO"
    assert estoque.saldo_produto(dados, "PS_2MM_BRANCO") == -1


def test_espessura_sem_produto_continua_sem_produto():
    """Espessura que o nome disse e o estoque não tem é cadastro faltando — não vira escolha."""
    dados = _estoque_lona_e_ps()
    previsao = prever_saida_os(dados, [_peca("PS", 1.0, 0.5, 1, {"espessura": "3MM", "cor": "PRETO"})], _MATERIAIS)
    assert previsao[0]["produto"] is None and previsao[0]["ambiguo"] is False
