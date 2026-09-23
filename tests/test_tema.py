"""
Testes do tema (claro/escuro).

Nenhum deles pode encostar no config.json de verdade: tema.alternar
grava, e config.salvar_config escreve na raiz do projeto. A fixture
autouse aponta o caminho pro tmp_path — mesma precaução do resto da
suíte (já houve teste distraído apagando arquivo real).
"""
import pytest

import config as config_modulo
import tema


@pytest.fixture(autouse=True)
def config_de_mentira(tmp_path, monkeypatch):
    monkeypatch.setattr(config_modulo, "CONFIG_PATH", tmp_path / "config.json")
    yield
    tema.cores.trocar(tema.PADRAO)


def test_as_duas_paletas_tem_exatamente_as_mesmas_chaves():
    # uma cor que existe só numa paleta é uma tela que quebra na outra
    assert set(tema.CLARO) == set(tema.ESCURO)


def test_toda_cor_e_um_hex_valido():
    for paleta in tema.PALETAS.values():
        for chave, valor in paleta.items():
            if chave == "nome":
                continue
            assert valor.startswith("#") and len(valor) == 7, (chave, valor)
            int(valor[1:], 16)


def test_padrao_e_escuro():
    assert tema.cores.nome == "escuro"
    assert tema.cores.escuro is True


def test_trocar_muda_todos_os_atributos_de_uma_vez():
    tema.cores.trocar("claro")
    assert tema.cores.fundo == tema.CLARO["fundo"]
    assert tema.cores.escuro is False
    tema.cores.trocar("escuro")
    assert tema.cores.fundo == tema.ESCURO["fundo"]


def test_nome_desconhecido_cai_no_padrao():
    tema.cores.trocar("roxo")
    assert tema.cores.nome == tema.PADRAO


def test_carregar_le_o_que_esta_no_config():
    assert tema.carregar({"tema": "claro"}) == "claro"
    assert tema.cores.escuro is False
    # config antigo, sem a chave
    assert tema.carregar({}) == tema.PADRAO


def test_alternar_troca_e_grava():
    dados = {"tema": "escuro"}
    nome, devolvido = tema.alternar(dados)
    assert nome == "claro"
    assert devolvido["tema"] == "claro"
    assert tema.cores.escuro is False
    # e gravou de verdade: quem abrir de novo pega claro
    assert config_modulo.carregar_config()["tema"] == "claro"

    nome, _ = tema.alternar(devolvido)
    assert nome == "escuro"
    assert config_modulo.carregar_config()["tema"] == "escuro"


def test_placa_logo_sem_o_arquivo_devolve_none(monkeypatch, tmp_path):
    # clone sem a pasta assets: a tela abre sem logo em vez de quebrar
    import branding
    monkeypatch.setattr(branding, "CAMINHO_LOGO_GUI", tmp_path / "nao_existe.png")
    assert tema.placa_logo(None) is None
