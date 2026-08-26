import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from estado_pedido import carregar_estado


def _cria_log_legado(pasta, nomes_ok):
    caminho = pasta / "log_processamento_CLIENTE_20260101_000000.csv"
    linhas = ["arquivo,status,detalhe"]
    for nome in nomes_ok:
        linhas.append(f'"{nome}",OK,"processado"')
    caminho.write_text("\n".join(linhas), encoding="utf-8-sig")


def test_carregar_estado_sem_config_mantem_categoria_none(tmp_path):
    # comportamento antigo preservado quando ninguém passa config (ex:
    # alguma chamada futura que não tenha o config à mão)
    _cria_log_legado(tmp_path, ["1UN LONA 1,00X1,00.PDF"])
    itens = carregar_estado(str(tmp_path))
    assert len(itens) == 1
    assert itens[0]["categoria"] is None
    assert itens[0]["dimensao"] is None


def test_carregar_estado_com_config_reconstroi_categoria_e_dimensao(tmp_path):
    """
    Regressão do bug real (2026-08-26): pasta de antes do estado_pedido.
    json existir tinha os itens antigos reconstruídos SEM categoria —
    isso fazia esses itens não aparecerem na OS (nenhuma categoria bate
    com None), e se a rodada não trouxesse nenhum item novo válido, a
    OS inteira saía sem nenhum item visível ("em branco"). Agora, com o
    config disponível, a categoria/medida são recuperadas do próprio
    nome do arquivo, do mesmo jeito que o processamento normal faz.
    """
    _cria_log_legado(tmp_path, ["2UN LONA 4,00X4,00M.PDF"])
    config = {
        "materiais": {"LONA": {"tipo": "rolo", "largura_cm": 320.0, "comprimento_cm": 5000.0}},
        "sinonimos_categoria": {},
        "typos_unidade": {},
    }
    itens = carregar_estado(str(tmp_path), config)
    assert len(itens) == 1
    item = itens[0]
    assert item["categoria"] == "LONA"
    assert item["quantidade"] == 2
    assert item["dimensao"]["area_m2"] == 16.0


def test_carregar_estado_com_config_mas_categoria_nao_reconhecida(tmp_path):
    # arquivo real que causou o bug em produção: "TECIDO" não é uma
    # categoria cadastrada — reconstrução não pode inventar uma
    _cria_log_legado(tmp_path, ["8UN TECIDO IMPRESSO 1,50X1.20M.PDF"])
    config = {
        "materiais": {"LONA": {"tipo": "rolo", "largura_cm": 320.0, "comprimento_cm": 5000.0}},
        "sinonimos_categoria": {},
        "typos_unidade": {},
    }
    itens = carregar_estado(str(tmp_path), config)
    assert len(itens) == 1
    assert itens[0]["categoria"] is None
