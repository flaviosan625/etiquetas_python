"""
Vigia do checklist: uma passada regenera a OS de cada cliente ativo só
quando a pasta de produção dele mudou.

Regra da casa: teste nunca toca pasta real. A fixture autouse aponta o
OneDrive (Recebimento de Artes, EVENTOS) e etiquetas_geradas pra tmp_path.
"""
import pathlib
import shutil
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import pytest

import caminhos
import clientes
import vigia_checklist as vc


@pytest.fixture(autouse=True)
def onedrive_de_mentira(tmp_path, monkeypatch):
    import montagem
    import conversao_adobe

    onedrive = tmp_path / "UNYCOMUNICACAO"
    monkeypatch.setattr(montagem, "PASTA_RAIZ", onedrive / "MONTAGEM ARTES MAQUINAS")
    monkeypatch.setattr(conversao_adobe, "CONVERSORES_POR_EXTENSAO", {})
    # Estes testes são da OS: não consultam filas nem notificam máquinas reais.
    monkeypatch.setattr(vc, "_conferir_fila", lambda: {})
    monkeypatch.setattr(caminhos, "ONEDRIVE_UNY", onedrive)
    monkeypatch.setattr(caminhos, "RECEBIMENTO_DE_ARTES", onedrive / "Recebimento de Artes")
    monkeypatch.setattr(caminhos, "EVENTOS", onedrive / "EVENTOS")
    monkeypatch.setattr(caminhos, "ETIQUETAS_GERADAS", tmp_path / "etiquetas_geradas")
    (onedrive / "Recebimento de Artes").mkdir(parents=True)
    return onedrive


def _cliente(onedrive, nome, evento, ativo=True):
    producao = onedrive / "EVENTOS" / evento / "PRODUCAO"
    producao.mkdir(parents=True)
    return clientes.criar(nome, pasta_producao=producao, checklist_ativo=ativo)


def _por(pasta, rel):
    caminho = pasta / rel
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_bytes(b"%PDF-1.4 fake")


@pytest.fixture
def repsol(onedrive_de_mentira):
    c = _cliente(onedrive_de_mentira, "Repsol", "REPSOL")
    _por(c.pasta_producao, "UV/1UN LONA IMPRESSA 5.00X3.00M_L01.pdf")
    return clientes.obter("Repsol")


# ----------------------------------------------------------- um cliente

def test_primeira_passada_gera_a_os(repsol):
    assert vc.passada() == ["Repsol"]
    assert vc.destino_pdf(repsol).is_file()
    assert vc.destino_pdf(repsol).name == "OS - REPSOL.pdf"


def test_segunda_passada_sem_mudanca_nao_regenera(repsol):
    vc.passada()

    assert vc.passada() == []


def test_os_antiga_ganha_retirada_sem_movimento_na_producao(repsol):
    vc.passada()
    estado = vc._ler_estado(repsol)
    estado.pop("versao_documentos")
    vc._gravar_estado(repsol, estado)
    assert vc.passada() == ["Repsol"]
    assert "modelo da OS atualizado com retirada" in vc.arquivo_log(repsol).read_text(encoding="utf-8")
    assert vc.passada() == []


def test_mudar_quantidade_na_producao_atualiza_os_e_retirada(repsol):
    import pymupdf
    vc.passada()
    original = repsol.pasta_producao / "UV/1UN LONA IMPRESSA 5.00X3.00M_L01.pdf"
    original.rename(original.with_name("5UN LONA IMPRESSA 5.00X3.00M_L01.pdf"))
    assert vc.passada() == ["Repsol"]
    with pymupdf.open(vc.destino_pdf(repsol)) as doc:
        os = "".join(p.get_text() for p in doc)
    with pymupdf.open(vc.destino_retirada(repsol)) as doc:
        retirada = "".join(p.get_text() for p in doc)
    assert "COMPROVANTE DE RETIRADA" not in os
    assert "5 UN" in os and "5 UN" in retirada
    assert "1 UN" not in os + retirada
    assert "Total da OS: 5 unidades" in retirada


def test_retirada_apagada_e_recriada_junto_da_os_sem_movimento(repsol):
    vc.passada()
    vc.destino_retirada(repsol).unlink()
    assert vc.passada() == ["Repsol"]
    assert vc.destino_retirada(repsol).is_file()
    assert vc.passada() == []


def test_movimento_na_pasta_regenera(repsol):
    vc.passada()
    _por(repsol.pasta_producao, "UV/1UN LONA IMPRESSA 6.00X3.00M_L02.pdf")

    assert vc.passada() == ["Repsol"]
    assert vc.passada() == []


def test_mover_para_prontos_conta_como_movimento(repsol):
    vc.passada()
    origem = repsol.pasta_producao / "UV/1UN LONA IMPRESSA 5.00X3.00M_L01.pdf"
    destino = repsol.pasta_producao / "UV/PRONTOS/1UN LONA IMPRESSA 5.00X3.00M_L01.pdf"
    destino.parent.mkdir(parents=True, exist_ok=True)
    origem.rename(destino)

    assert vc.passada() == ["Repsol"]


# ------------------------------------ etiquetas_geradas pode ser apagada

def test_apagar_etiquetas_geradas_inteira_nao_apaga_a_memoria(repsol):
    """
    Regra do usuário (2026-09-13): "estruturar pra que eu possa apagar sempre
    que precisar qualquer cliente em etiquetas_geradas". A OS volta; a memória
    nunca esteve lá.
    """
    vc.passada()
    shutil.rmtree(caminhos.ETIQUETAS_GERADAS)

    assert vc.arquivo_estado(repsol).is_file()                # memória na pasta do cliente
    assert vc.passada() == ["Repsol"]                         # a OS volta sozinha
    assert vc.destino_pdf(repsol).is_file()
    assert vc.passada() == []                                 # e não fica regenerando à toa


def test_estado_e_log_moram_na_pasta_do_cliente_e_nao_na_saida(repsol):
    vc.passada()

    assert vc.arquivo_estado(repsol).parent == repsol.pasta / clientes.PASTA_SISTEMA
    assert vc.arquivo_log(repsol).parent == repsol.pasta / clientes.PASTA_SISTEMA
    assert not list(repsol.pasta_documentos.glob("*.json"))
    assert not list(repsol.pasta_documentos.glob("*.log"))


# ---------------------------------------------------- vários clientes

def test_clientes_em_paralelo_so_regenera_quem_mudou(onedrive_de_mentira):
    a = _cliente(onedrive_de_mentira, "Asics", "ASICS")
    m = _cliente(onedrive_de_mentira, "Mercado Livre", "MERCADO LIVRE 26")
    _por(a.pasta_producao, "1UN LONA IMPRESSA 2.00X1.00M_A.pdf")
    _por(m.pasta_producao, "1UN LONA IMPRESSA 2.00X1.00M_M.pdf")

    assert vc.passada() == ["Asics", "Mercado Livre"]         # cada um na sua pasta
    assert vc.destino_pdf(a).parent != vc.destino_pdf(m).parent

    _por(m.pasta_producao, "1UN LONA IMPRESSA 3.00X1.00M_M2.pdf")
    assert vc.passada() == ["Mercado Livre"]                  # só quem mudou


def test_cliente_com_checklist_desligado_nao_gera(onedrive_de_mentira):
    c = _cliente(onedrive_de_mentira, "Interlagos", "INTERLAGOS", ativo=False)
    _por(c.pasta_producao, "1UN LONA IMPRESSA 2.00X1.00M_I.pdf")

    assert vc.passada() == []
    assert not vc.destino_pdf(c).exists()


def test_erro_num_cliente_nao_impede_os_outros(onedrive_de_mentira, monkeypatch):
    a = _cliente(onedrive_de_mentira, "Asics", "ASICS")
    r = _cliente(onedrive_de_mentira, "Repsol", "REPSOL")
    _por(a.pasta_producao, "1UN LONA IMPRESSA 2.00X1.00M_A.pdf")
    _por(r.pasta_producao, "1UN LONA IMPRESSA 2.00X1.00M_R.pdf")

    import checklist_producao
    original = checklist_producao.gerar

    def gerar_que_quebra_na_asics(pasta_saida, pasta_producao, nome_cliente, **k):
        if nome_cliente == "ASICS":
            raise RuntimeError("PDF corrompido")
        return original(pasta_saida, pasta_producao, nome_cliente=nome_cliente, **k)

    monkeypatch.setattr(checklist_producao, "gerar", gerar_que_quebra_na_asics)

    assert vc.passada() == ["Repsol"]
    assert "PDF corrompido" in vc.arquivo_log(clientes.obter("Asics")).read_text(encoding="utf-8")


# --------------------------------------------------------------- trava

def test_duas_passadas_juntas_so_uma_trabalha(repsol):
    """
    Desde o painel de agentes, um disparo forçado pode cair em cima da
    passada agendada. Com a trava ocupada, a segunda sai sem regenerar.
    """
    from rasterlink_hotfolder import _travar_instancia_unica

    vc.arquivo_trava().parent.mkdir(parents=True, exist_ok=True)
    pode, trava = _travar_instancia_unica(vc.arquivo_trava())     # "a outra passada"
    assert pode
    try:
        assert vc.passada() is None
        assert not vc.destino_pdf(repsol).exists()
    finally:
        trava.close()

    assert vc.passada() == ["Repsol"]


# ------------------------------------------------------ preço é movimento

def test_mudar_preco_atualiza_a_copia_de_custos_sem_mexer_na_pasta(repsol, monkeypatch):
    """
    Sem isto, a cópia de custos do evento ficaria com o valor velho até
    alguém mexer na produção — número errado com cara de certo.
    """
    import config as modulo_config
    import checklist_producao
    import custos

    base = modulo_config.carregar_config()
    materiais = {k: dict(v) for k, v in base["materiais"].items()}
    materiais["LONA"].pop("preco_m2", None)
    cfg = dict(base, materiais=materiais)
    monkeypatch.setattr(modulo_config, "carregar_config", lambda: cfg)
    monkeypatch.setattr(checklist_producao, "carregar_config", lambda: cfg)

    assert vc.passada() == ["Repsol"]                         # primeira vez, sem preço
    assert not (repsol.pasta_documentos / custos.nome_arquivo(repsol.documento)).exists()
    assert vc.passada() == []

    materiais["LONA"]["preco_m2"] = 18.0                      # cadastrou o preço
    assert vc.passada() == ["Repsol"]
    assert (repsol.pasta_documentos / custos.nome_arquivo(repsol.documento)).is_file()
    assert "preço mudou" in vc.arquivo_log(repsol).read_text(encoding="utf-8")
    assert vc.passada() == []                                 # e estabiliza


# ------------------------------------------------------------ só Prontos

@pytest.mark.parametrize("campo,valor,total", [("preco_frasco", 150, "R$ 1,53"),
                                              ("consumo_ml_m2", 3, "R$ 1,46")])
def test_mudar_preco_ou_consumo_de_tinta_atualiza_os_sem_mexer_na_pasta(repsol, monkeypatch, campo, valor, total):
    import copy
    import pymupdf
    import config as modulo_config
    import checklist_producao
    import custos_tinta

    cfg = copy.deepcopy(modulo_config.CONFIG_PADRAO)
    for dados in cfg["centro_custos_tintas"]["maquinas"][custos_tinta.R5200]["cores"].values():
        dados["preco_frasco"] = 100
    monkeypatch.setattr(modulo_config, "carregar_config", lambda: cfg)
    monkeypatch.setattr(checklist_producao, "carregar_config", lambda: cfg)
    _por(repsol.pasta_producao, "UV/DOCAN R5200/1UN LONA IMPRESSA 5.00X0.50M_TINTA.pdf")

    def texto_os():
        with pymupdf.open(vc.destino_pdf(repsol)) as doc:
            return "".join(p.get_text() for p in doc)

    assert vc.passada() == ["Repsol"]
    assert "R$ 1,26" in texto_os()
    assert vc.passada() == []
    cfg["centro_custos_tintas"]["maquinas"][custos_tinta.R5200]["cores"]["BLACK"][campo] = valor
    assert vc.passada() == ["Repsol"]
    assert total in texto_os()
    assert "preço/consumo de tinta mudou" in vc.arquivo_log(repsol).read_text(encoding="utf-8")
    with pymupdf.open(vc.destino_retirada(repsol)) as doc:
        assert "R$" not in "".join(p.get_text() for p in doc)
    assert vc.passada() == []


def test_ligar_so_prontos_regera_a_os_sem_mexer_na_pasta(repsol):
    """Marcou na janela, a OS muda na passada seguinte — não quando alguém mexer na pasta."""
    vc.passada()
    assert vc.passada() == []

    repsol.so_prontos = True
    clientes.salvar(repsol)

    assert vc.passada() == ["Repsol"]
    assert vc.passada() == []


def test_os_so_com_prontos_leva_so_as_pecas_prontas(repsol, monkeypatch):
    _por(repsol.pasta_producao, "UV/PRONTOS/1UN LONA IMPRESSA 6.00X3.00M_L02.pdf")
    repsol.so_prontos = True
    clientes.salvar(repsol)
    recebidos = []
    monkeypatch.setattr(vc.checklist_producao, "gerar",
                        lambda *a, **k: recebidos.append(k.get("so_prontos")))

    vc.passada()

    assert recebidos == [True]
