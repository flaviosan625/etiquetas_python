import json
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import config as config_mod


def test_carregar_config_cria_arquivo_padrao_se_nao_existir(tmp_path, monkeypatch):
    caminho = tmp_path / "config.json"
    monkeypatch.setattr(config_mod, "CONFIG_PATH", caminho)

    cfg = config_mod.carregar_config()

    assert caminho.exists()
    assert "LONA" in cfg["materiais"]


def test_carregar_config_completa_chaves_faltantes_sem_apagar_o_resto(tmp_path, monkeypatch):
    caminho = tmp_path / "config.json"
    caminho.write_text(
        json.dumps({"materiais": {"LONA": {"tipo": "rolo", "largura_cm": 999, "comprimento_cm": 1}}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(config_mod, "CONFIG_PATH", caminho)

    cfg = config_mod.carregar_config()

    # a chave que faltava foi preenchida com o padrão
    assert "typos_unidade" in cfg
    assert "ultimo_gerente" in cfg
    # mas o valor customizado que já existia não foi perdido
    assert cfg["materiais"]["LONA"]["largura_cm"] == 999


def test_config_corrompido_recria_padrao_em_vez_de_travar(tmp_path, monkeypatch):
    caminho = tmp_path / "config.json"
    caminho.write_text("{isso não é um json valido", encoding="utf-8")
    monkeypatch.setattr(config_mod, "CONFIG_PATH", caminho)

    cfg = config_mod.carregar_config()

    assert "materiais" in cfg
    assert (tmp_path / "config.json.bak").exists()


def test_atualizar_ultimo_uso_salva_no_arquivo(tmp_path, monkeypatch):
    caminho = tmp_path / "config.json"
    monkeypatch.setattr(config_mod, "CONFIG_PATH", caminho)
    cfg = config_mod.carregar_config()

    config_mod.atualizar_ultimo_uso(cfg, "João Silva", "Maria Souza")

    conteudo = json.loads(caminho.read_text(encoding="utf-8"))
    assert conteudo["ultimo_gerente"] == "João Silva"
    assert conteudo["ultimo_produtor"] == "Maria Souza"
