import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import estoque
from estoque import confirmar_saida_os, pedido_ja_teve_saida, calcular_consumo, prever_saida_os, produtos_por_categoria


def _isolar_arquivo_estoque(monkeypatch, tmp_path):
    """
    salvar_estoque() sempre grava em estoque.ESTOQUE_PATH (caminho fixo
    do módulo, não um parâmetro) — sem isolar isso, QUALQUER teste que
    chame uma função que persiste (registrar_movimento, confirmar_saida_
    os, etc.) sobrescreve o estoque.json REAL de produção. Isso
    aconteceu de verdade ao escrever este arquivo de teste (2026-08-26):
    apagou os 51 produtos e os movimentos reais, restaurado via
    `git checkout -- estoque.json` logo em seguida. Todo teste aqui
    precisa chamar isso antes de qualquer função que possa persistir.
    """
    monkeypatch.setattr(estoque, "ESTOQUE_PATH", tmp_path / "estoque_teste.json")


def _estoque_minimo():
    return {
        "produtos": {
            "LONA_TESTE": {
                "descricao": "Lona Teste", "tipo": "rolo", "unidade": "rolo",
                "comprimento_rolo_m": 50, "categoria_vinculada": "LONA",
                "variante_vinculada": None, "minimo": 0, "maximo": 0,
                "codigo_planilha": None, "acumulado_m": 0.0,
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
    assert resumo[0]["descontado"] == 1  # 60m acumulados / 50m por rolo = 1 rolo fechado

    assert pedido_ja_teve_saida(estoque_dados, nome_pedido) is True
    assert pedido_ja_teve_saida(estoque_dados, "OUTRO CLIENTE (02/01/2026 10:00:00)") is False


def _estoque_adesivo_ambiguo():
    def _adesivo(descricao):
        return {
            "descricao": descricao, "tipo": "rolo", "unidade": "rolo",
            "comprimento_rolo_m": 50, "categoria_vinculada": "ADESIVO",
            "variante_vinculada": None, "minimo": 0, "maximo": 0,
            "codigo_planilha": None, "acumulado_m": 0.0,
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
