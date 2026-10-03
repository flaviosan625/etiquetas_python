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


# ============ uma pasta por cliente, com os lotes dentro (03/10/2026)
#
# Pedido dele: "esta gerando duas pastas de clientes na hora que estou
# gerando as etiquetas, uma vem com uma OS — deixar apenas uma pasta". A
# pasta do cliente passou a ser a unica: a OS da producao fica na raiz
# dela (quem escreve e o vigia) e cada rodada de etiquetas e uma subpasta
# com o carimbo de data. O formato antigo (CLIENTE_<carimbo> na raiz)
# continua sendo LIDO, porque tem pedido em andamento no disco assim.

def test_lote_novo_mora_dentro_da_pasta_do_cliente(tmp_path):
    from utils import cliente_do_pedido, pastas_de_lote
    (tmp_path / "VIBRA" / "20261003_192549").mkdir(parents=True)

    lotes = pastas_de_lote(tmp_path)

    assert [p.name for p in lotes] == ["20261003_192549"]
    assert cliente_do_pedido(lotes[0]) == "VIBRA"


def test_formato_antigo_continua_sendo_lido(tmp_path):
    from utils import cliente_do_pedido, pastas_de_lote
    (tmp_path / "VIBRA_20261003_192549").mkdir()

    lotes = pastas_de_lote(tmp_path)

    assert len(lotes) == 1 and cliente_do_pedido(lotes[0]) == "VIBRA"


def test_a_pasta_do_cliente_nunca_e_confundida_com_lote(tmp_path):
    """Na raiz dela mora a OS da PRODUCAO, que o vigia regenera — nao e pedido."""
    from utils import pasta_e_de_lote, pastas_de_lote
    pasta = tmp_path / "VIBRA"
    pasta.mkdir()
    (pasta / "OS - VIBRA.pdf").write_bytes(b"%PDF")

    assert pastas_de_lote(tmp_path) == []
    assert pasta_e_de_lote(pasta) is False


def test_os_dois_formatos_convivem_e_vem_do_mais_novo_pro_mais_velho(tmp_path):
    from utils import pastas_de_lote
    (tmp_path / "VIBRA_20260101_080000").mkdir()
    (tmp_path / "VIBRA" / "20261003_192549").mkdir(parents=True)
    (tmp_path / "OUTRO" / "20260615_120000").mkdir(parents=True)

    nomes = [str(p.relative_to(tmp_path)).replace("\\", "/") for p in pastas_de_lote(tmp_path)]

    assert nomes == ["VIBRA/20261003_192549", "OUTRO/20260615_120000", "VIBRA_20260101_080000"]


def test_pedido_anterior_do_cliente_acha_os_dois_formatos(tmp_path):
    from estado_pedido import localizar_pastas_cliente
    (tmp_path / "VIBRA_20260101_080000").mkdir()
    (tmp_path / "VIBRA" / "20261003_192549").mkdir(parents=True)
    (tmp_path / "OUTRO" / "20260615_120000").mkdir(parents=True)

    achados = localizar_pastas_cliente("VIBRA", pasta_saida_base=tmp_path)

    assert [p.name for p in achados] == ["20261003_192549", "VIBRA_20260101_080000"]


def test_data_legivel_sai_igual_nos_dois_formatos():
    from utils import data_hora_da_pasta
    assert data_hora_da_pasta("VIBRA_20261003_192549") == "03-10-2026 19-25-49"
    assert data_hora_da_pasta("20261003_192549") == "03-10-2026 19-25-49"
