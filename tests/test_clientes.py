"""
Cadastro de clientes: cada cliente é uma pasta em "Recebimento de Artes".

Nenhum teste toca o OneDrive de verdade: a fixture autouse aponta
Recebimento de Artes, EVENTOS e etiquetas_geradas pra tmp_path.
"""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import pytest

import caminhos
import clientes as cl


@pytest.fixture(autouse=True)
def onedrive_de_mentira(tmp_path, monkeypatch):
    onedrive = tmp_path / "UNYCOMUNICACAO"
    monkeypatch.setattr(caminhos, "ONEDRIVE_UNY", onedrive)
    monkeypatch.setattr(caminhos, "RECEBIMENTO_DE_ARTES", onedrive / "Recebimento de Artes")
    monkeypatch.setattr(caminhos, "EVENTOS", onedrive / "EVENTOS")
    monkeypatch.setattr(caminhos, "ETIQUETAS_GERADAS", tmp_path / "etiquetas_geradas")
    (onedrive / "Recebimento de Artes").mkdir(parents=True)
    return onedrive


def _evento(onedrive, nome):
    producao = onedrive / "EVENTOS" / nome / "PRODUCAO"
    producao.mkdir(parents=True)
    return producao


# ------------------------------------------------------------------ criar

def test_criar_faz_a_pasta_com_as_subpastas_do_recebimento(onedrive_de_mentira):
    producao = _evento(onedrive_de_mentira, "REPSOL")

    c = cl.criar("Repsol", pasta_producao=producao)

    assert c.pasta == caminhos.RECEBIMENTO_DE_ARTES / "Repsol"
    assert (c.pasta / "ARTES").is_dir() and (c.pasta / "_entrada").is_dir()
    assert (c.pasta / cl.NOME_CONFIG).is_file()
    assert c.checklist_ativo is True


def test_producao_e_gravada_relativa_ao_onedrive(onedrive_de_mentira):
    """O usuário do Windows muda de um PC pro outro; o pedaço no OneDrive não."""
    producao = _evento(onedrive_de_mentira, "REPSOL")

    c = cl.criar("Repsol", pasta_producao=producao)
    dados = json.loads((c.pasta / cl.NOME_CONFIG).read_text(encoding="utf-8"))

    assert dados["pasta_producao"] == str(pathlib.Path("EVENTOS/REPSOL/PRODUCAO"))
    assert cl.obter("Repsol").pasta_producao == producao


def test_sem_pasta_de_producao_o_checklist_nao_liga(onedrive_de_mentira):
    c = cl.criar("Asics", checklist_ativo=True)

    assert c.checklist_ativo is False
    assert cl.com_checklist() == []


@pytest.mark.parametrize("nome, trecho", [
    ("", "Digite"),
    ("   ", "Digite"),
    ("Cliente A/B", "Windows não aceita"),
    ("_interno", "não pode começar"),
])
def test_nome_invalido_diz_o_que_esta_errado(nome, trecho):
    with pytest.raises(cl.ErroCliente, match=trecho):
        cl.criar(nome)


def test_nome_repetido_nao_cria_de_novo_nem_com_maiuscula_diferente():
    cl.criar("Repsol")

    with pytest.raises(cl.ErroCliente, match="Já existe"):
        cl.criar("REPSOL")


def test_pasta_de_producao_que_nao_existe_e_recusada(tmp_path):
    with pytest.raises(cl.ErroCliente, match="não existe"):
        cl.criar("Repsol", pasta_producao=tmp_path / "nao" / "existe")


# ------------------------------------------------------------------ listar

def test_pasta_criada_a_mao_no_explorer_vira_cliente_sem_configuracao():
    (caminhos.RECEBIMENTO_DE_ARTES / "Nestle").mkdir()

    c = cl.obter("Nestle")

    assert c is not None
    assert c.configurado is False
    assert c.checklist_ativo is False


def test_pasta_com_sublinhado_ou_ponto_nao_e_cliente():
    (caminhos.RECEBIMENTO_DE_ARTES / "_modelo").mkdir()
    (caminhos.RECEBIMENTO_DE_ARTES / ".tmp").mkdir()
    (caminhos.RECEBIMENTO_DE_ARTES / "Repsol").mkdir()

    assert [c.nome for c in cl.listar()] == ["Repsol"]


def test_config_quebrada_nao_derruba_a_lista():
    pasta = caminhos.RECEBIMENTO_DE_ARTES / "Repsol"
    pasta.mkdir()
    (pasta / cl.NOME_CONFIG).write_text("{isto nao e json", encoding="utf-8")

    assert [c.nome for c in cl.listar()] == ["Repsol"]
    assert cl.obter("Repsol").configurado is False


def test_varios_clientes_em_paralelo_so_os_ligados_entram_no_checklist(onedrive_de_mentira):
    cl.criar("Mercado Livre", pasta_producao=_evento(onedrive_de_mentira, "MERCADO LIVRE 26"))
    cl.criar("Repsol", pasta_producao=_evento(onedrive_de_mentira, "REPSOL"), checklist_ativo=False)
    cl.criar("Asics", pasta_producao=_evento(onedrive_de_mentira, "ASICS"))

    assert [c.nome for c in cl.com_checklist()] == ["Asics", "Mercado Livre"]


# --------------------------------------------------------------- documento

def test_documento_sai_no_nome_do_cliente_em_maiusculas():
    c = cl.criar("Repsol")

    assert c.documento == "REPSOL"
    assert c.pasta_documentos == caminhos.ETIQUETAS_GERADAS / "REPSOL"


def test_nome_de_documento_proprio_mantem_o_que_ja_existe(onedrive_de_mentira):
    """A pasta 'Mercado Livre' continua gerando 'OS - MERCADO LIVRE 26.pdf'."""
    c = cl.criar("Mercado Livre", pasta_producao=_evento(onedrive_de_mentira, "MERCADO LIVRE 26"),
                 nome_documento="MERCADO LIVRE 26")

    assert cl.obter("Mercado Livre").documento == "MERCADO LIVRE 26"
    assert c.pasta_documentos == caminhos.ETIQUETAS_GERADAS / "MERCADO LIVRE 26"


# ---------------------------------------------------------------- sugestão

def test_sugere_a_producao_do_evento_com_o_mesmo_nome(onedrive_de_mentira):
    producao = _evento(onedrive_de_mentira, "REPSOL")

    assert cl.sugerir_pasta_producao("Repsol") == producao


def test_sugere_quando_o_evento_tem_o_nome_mais_comprido(onedrive_de_mentira):
    producao = _evento(onedrive_de_mentira, "MERCADO LIVRE 26")

    assert cl.sugerir_pasta_producao("Mercado Livre") == producao


def test_nao_chuta_quando_ha_mais_de_um_parecido(onedrive_de_mentira):
    _evento(onedrive_de_mentira, "OAKLEY")
    _evento(onedrive_de_mentira, "OAKLEY stand")

    assert cl.sugerir_pasta_producao("Oak") is None


def test_as_subpastas_sao_as_mesmas_que_o_recebimento_usa():
    import arte_recebida
    assert set(cl.PASTAS_DO_CLIENTE) == {arte_recebida.NOME_ARTES, arte_recebida.NOME_ENTRADA}


def test_so_prontos_e_gravado_e_lido_do_cliente_json(onedrive_de_mentira):
    producao = _evento(onedrive_de_mentira, "MERCADO LIVRE 26")
    c = cl.criar("Mercado Livre", pasta_producao=producao)
    assert c.so_prontos is False, "desligado por padrão: cliente sem Prontos ficaria com a OS vazia"

    c.so_prontos = True
    cl.salvar(c)

    assert cl.obter("Mercado Livre").so_prontos is True
    assert json.loads((c.pasta / cl.NOME_CONFIG).read_text(encoding="utf-8"))["so_prontos"] is True


# ------------------------------------------- nome digitado na tela de receber

def test_nome_vazio(onedrive_de_mentira):
    assert cl.situacao_do_nome("   ") == ("vazio", None)


def test_nome_que_ja_existe_mesmo_com_outra_grafia(onedrive_de_mentira):
    """'MERCADO LIVRE' digitado não pode criar um segundo cliente ao lado de 'Mercado Livre'."""
    cl.criar("Mercado Livre")
    for digitado in ("Mercado Livre", "MERCADO LIVRE", "mercadolivre", "  Mercado  Livre "):
        situacao, cliente = cl.situacao_do_nome(digitado)
        assert situacao == "existe" and cliente.nome == "Mercado Livre", digitado


def test_nome_sem_acento_acha_o_cliente_com_acento(onedrive_de_mentira):
    cl.criar("Túnel Eventos")
    assert cl.situacao_do_nome("TUNEL EVENTOS")[0] == "existe"


def test_nome_parecido_pede_confirmacao(onedrive_de_mentira):
    cl.criar("Mercado Livre")
    situacao, cliente = cl.situacao_do_nome("Mercado")
    assert situacao == "parecido" and cliente.nome == "Mercado Livre"


def test_nome_curto_demais_nao_vira_parecido_de_tudo(onedrive_de_mentira):
    """'ML' está dentro de muita coisa; parecido só com 4+ letras."""
    cl.criar("Mercado Livre")
    assert cl.situacao_do_nome("ML")[0] == "novo"


def test_nome_novo(onedrive_de_mentira):
    cl.criar("Mercado Livre")
    assert cl.situacao_do_nome("Mandarin Sessions") == ("novo", None)


def test_nome_invalido_explica(onedrive_de_mentira):
    situacao, mensagem = cl.situacao_do_nome("Cliente A/B")
    assert situacao == "invalido" and "Cliente A_B" in mensagem


def test_obter_ou_criar_usa_o_que_existe(onedrive_de_mentira):
    original = cl.criar("Mercado Livre")
    cliente, criado = cl.obter_ou_criar("MERCADO LIVRE")
    assert not criado and cliente.pasta == original.pasta


def test_obter_ou_criar_nasce_a_pasta_do_nome_digitado(onedrive_de_mentira):
    """Pedido de 21/09: a pasta do cliente nasce do nome informado na tela."""
    cliente, criado = cl.obter_ou_criar("Mandarin Sessions")
    assert criado
    assert cliente.pasta == caminhos.RECEBIMENTO_DE_ARTES / "Mandarin Sessions"
    assert (cliente.pasta / "ARTES").is_dir()


def test_obter_ou_criar_recusa_vazio_e_invalido(onedrive_de_mentira):
    for ruim in ("", "a/b", "_sistema"):
        with pytest.raises(cl.ErroCliente):
            cl.obter_ou_criar(ruim)
