import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import estoque
from estoque import confirmar_saida_os, pedido_ja_teve_saida


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
