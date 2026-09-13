"""
Painel dos agentes: a regra de "vivo / atrasado / parado" e o disparo.

Nenhum teste fala com o Agendador de verdade nem roda passada nenhuma:
o Agendador é um dublê, o subprocesso é um dublê, e as pastas do monitor
apontam pra tmp_path.
"""
import datetime
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import pytest

import agentes as ag

AGORA = datetime.datetime(2026, 9, 13, 12, 0, 0)
MINUTO = ag.agente("checklist")
DIARIO = ag.agente("relatorio")


def _tarefa(**campos):
    base = {"existe": True, "habilitada": True, "estado": 3,
            "ultima": AGORA - datetime.timedelta(seconds=40), "resultado": 0,
            "proxima": AGORA + datetime.timedelta(seconds=20)}
    base.update(campos)
    return base


# ------------------------------------------------------- vivo ou parado

def test_rodou_agora_e_sem_erro_e_ok():
    r = ag.classificar_tarefa(MINUTO, _tarefa(), AGORA)

    assert r["nivel"] == "ok"
    assert "40 s" in r["texto"]                      # o que mediu
    assert "Normal" in r["texto"]                    # e o que significa


def test_alguns_minutos_sem_rodar_e_atencao_nao_parado():
    r = ag.classificar_tarefa(MINUTO, _tarefa(ultima=AGORA - datetime.timedelta(minutes=6)), AGORA)

    assert r["nivel"] == "atencao"
    assert "12 min" in r["texto"]                    # diz onde vira defeito


def test_passou_de_12_minutos_e_parado():
    r = ag.classificar_tarefa(MINUTO, _tarefa(ultima=AGORA - datetime.timedelta(minutes=30)), AGORA)

    assert r["nivel"] == "parado"
    assert "Force um disparo" in r["texto"]


def test_rodou_mas_terminou_com_erro_e_parado_mesmo_recente():
    """Rodar não é funcionar: o venv quebrado rodava toda hora e falhava."""
    r = ag.classificar_tarefa(MINUTO, _tarefa(resultado=1), AGORA)

    assert r["nivel"] == "parado"
    assert "terminou com erro" in r["texto"]
    assert "Rodar aqui" in r["texto"]


def test_codigo_negativo_do_com_e_normalizado():
    """O COM devolve HRESULT com sinal; a tabela é sem sinal."""
    assert ag.traduzir_resultado(-2147024891) == "acesso negado"      # 0x80070005
    assert ag.traduzir_resultado(0) == "deu certo"


def test_tarefa_desligada_e_parado():
    r = ag.classificar_tarefa(MINUTO, _tarefa(habilitada=False), AGORA)

    assert r["nivel"] == "parado"
    assert "DESLIGADA" in r["texto"]


def test_tarefa_que_nao_existe_e_parado():
    r = ag.classificar_tarefa(MINUTO, {"existe": False}, AGORA)

    assert r["nivel"] == "parado"
    assert "NÃO EXISTE" in r["texto"]


def test_nao_conseguir_ler_o_agendador_nao_vira_parado():
    """'Não sei' não é 'parado' — mesma regra do sinal do RIP."""
    r = ag.classificar_tarefa(MINUTO, {"existe": None, "erro": "COM indisponível"}, AGORA)

    assert r["nivel"] == "sem_sinal"


def test_rodando_agora():
    r = ag.classificar_tarefa(MINUTO, _tarefa(estado=4), AGORA)

    assert r["nivel"] == "rodando"


def test_diario_rodou_hoje_de_manha_e_ok():
    r = ag.classificar_tarefa(DIARIO, _tarefa(ultima=AGORA.replace(hour=6), resultado=0,
                                              proxima=AGORA.replace(hour=6) + datetime.timedelta(days=1)), AGORA)

    assert r["nivel"] == "ok"
    assert "hoje às 06:00" in r["texto"]


def test_diario_sem_rodar_ha_dois_dias_e_parado():
    r = ag.classificar_tarefa(DIARIO, _tarefa(ultima=AGORA - datetime.timedelta(days=2)), AGORA)

    assert r["nivel"] == "parado"


def test_hora_do_agendador_vem_marcada_utc_mas_e_local():
    """Sondado: o Agendador devolve 12:14 local marcado como +00:00."""
    marcada = datetime.datetime(2026, 9, 13, 12, 14, 22, tzinfo=datetime.timezone.utc)

    assert ag._data_local(marcada) == datetime.datetime(2026, 9, 13, 12, 14, 22)
    assert ag._data_local(datetime.datetime(1899, 12, 30)) is None     # nunca rodou


# --------------------------------------------------------------- monitor

def test_monitor_congelado(tmp_path, monkeypatch):
    monkeypatch.setattr(ag, "PASTA_INICIALIZACAO", tmp_path / "Startup")
    monkeypatch.setattr(ag, "PASTA_CONGELADO", tmp_path / "_congelado")
    (tmp_path / "_congelado").mkdir()
    (tmp_path / "_congelado" / ag.ATALHO_MONITOR).write_bytes(b"lnk")

    assert ag.estado_monitor()["nivel"] == "congelado"


def test_monitor_que_voltou_pra_inicializacao_acende_alerta(tmp_path, monkeypatch):
    monkeypatch.setattr(ag, "PASTA_INICIALIZACAO", tmp_path / "Startup")
    monkeypatch.setattr(ag, "PASTA_CONGELADO", tmp_path / "_congelado")
    (tmp_path / "Startup").mkdir()
    (tmp_path / "Startup" / ag.ATALHO_MONITOR).write_bytes(b"lnk")

    r = ag.estado_monitor()
    assert r["nivel"] == "atencao"
    assert "VOLTOU" in r["texto"]


# ---------------------------------------------------------------- disparo

class _TarefaFalsa:
    def __init__(self, habilitada=True, estado=3):
        self.Enabled = habilitada
        self.State = estado
        self.disparos = 0

    def Run(self, _):
        self.disparos += 1


class _AgendadorFalso:
    def __init__(self, tarefa):
        self._tarefa = tarefa

    def GetFolder(self, _):
        return self

    def GetTask(self, _):
        if self._tarefa is None:
            raise Exception("não existe")
        return self._tarefa


def test_disparar_pede_ao_agendador():
    tarefa = _TarefaFalsa()

    ok, msg = ag.disparar(MINUTO, servico=_AgendadorFalso(tarefa), agora=AGORA)

    assert ok is True
    assert tarefa.disparos == 1
    assert "12:00:00" in msg


def test_nao_dispara_o_que_ja_esta_rodando():
    tarefa = _TarefaFalsa(estado=4)

    ok, _ = ag.disparar(MINUTO, servico=_AgendadorFalso(tarefa))

    assert ok is False
    assert tarefa.disparos == 0


def test_nao_dispara_tarefa_desligada():
    tarefa = _TarefaFalsa(habilitada=False)

    ok, msg = ag.disparar(MINUTO, servico=_AgendadorFalso(tarefa))

    assert ok is False and "Rodar aqui" in msg
    assert tarefa.disparos == 0


@pytest.mark.parametrize("chave", ["rip", "monitor"])
def test_rip_e_monitor_congelado_nunca_se_disparam(chave):
    """O RIP é outro PC; o monitor está congelado por ordem do usuário."""
    tarefa = _TarefaFalsa()

    ok, _ = ag.disparar(ag.agente(chave), servico=_AgendadorFalso(tarefa))
    rodou = ag.rodar_aqui(ag.agente(chave), servico=_AgendadorFalso(tarefa),
                          executar=lambda *a, **k: pytest.fail("não podia rodar"))

    assert ok is False
    assert "recusado" in rodou
    assert tarefa.disparos == 0


# ------------------------------------------------------------- rodar aqui

def test_rodar_aqui_roda_a_mesma_passada_da_tarefa(monkeypatch):
    chamadas = []

    def executar(comando, **kwargs):
        chamadas.append((comando, kwargs))
        return subprocess.CompletedProcess(comando, 0, stdout="regenerou\n", stderr="")

    monkeypatch.setattr(ag, "ler_tarefa", lambda nome, servico=None: _tarefa())
    r = ag.rodar_aqui(MINUTO, executar=executar)

    comando, kwargs = chamadas[0]
    assert comando[1:] == ["-m", "vigia_checklist", "--uma-vez"]      # igual à tarefa
    assert kwargs["cwd"] == str(ag.RAIZ)
    assert r["codigo"] == 0 and r["saida"] == "regenerou"


def test_rodar_aqui_recusa_se_a_tarefa_esta_rodando(monkeypatch):
    monkeypatch.setattr(ag, "ler_tarefa", lambda nome, servico=None: _tarefa(estado=4))

    r = ag.rodar_aqui(MINUTO, executar=lambda *a, **k: pytest.fail("não podia rodar"))

    assert "recusado" in r


def test_rodar_aqui_que_trava_nao_prende_a_tela(monkeypatch):
    def executar(comando, **kwargs):
        raise subprocess.TimeoutExpired(comando, kwargs["timeout"])

    monkeypatch.setattr(ag, "ler_tarefa", lambda nome, servico=None: _tarefa())
    r = ag.rodar_aqui(MINUTO, timeout_s=5, executar=executar)

    assert r["codigo"] is None
    assert "5 s" in r["saida"]


def test_todo_agente_disparavel_tem_tarefa_e_comando():
    """Agente que aparece com botão de disparo e não sabe o que rodar é bug."""
    for a in ag.AGENTES:
        if a.pode_disparar:
            assert a.tarefa and a.argumentos, a.chave


def test_acha_a_tarefa_pelo_nome_antigo_ate_reinstalar(monkeypatch):
    """
    A tarefa nasceu 'Checklist Producao - Mercado Livre'. O nome novo é
    genérico, mas até alguém rodar o instalador de novo ela continua com o
    nome antigo no Agendador — e o painel não pode dizer que ela não existe.
    """
    lidas = []

    def ler(nome, servico=None):
        lidas.append(nome)
        return {"existe": False} if nome == "Checklist de Producao" else _tarefa()

    monkeypatch.setattr(ag, "ler_tarefa", ler)
    tarefa = ag.ler_tarefa_do_agente(MINUTO)

    assert tarefa["existe"] is True
    assert tarefa["nome"] == "Checklist Producao - Mercado Livre"
    assert lidas == ["Checklist de Producao", "Checklist Producao - Mercado Livre"]


def test_nao_saber_ler_o_agendador_nao_vira_procurar_nome_antigo(monkeypatch):
    lidas = []
    monkeypatch.setattr(ag, "ler_tarefa",
                        lambda nome, servico=None: lidas.append(nome) or {"existe": None, "erro": "x"})

    assert ag.ler_tarefa_do_agente(MINUTO)["existe"] is None
    assert lidas == ["Checklist de Producao"]


def test_nenhum_agente_fala_de_cliente_especifico():
    """Amanhã é outro cliente, e vários em paralelo (2026-09-13)."""
    for a in ag.AGENTES:
        texto = " ".join((a.chave, a.nome, a.faz, a.onde, a.tarefa or "")).lower()
        assert "mercado livre" not in texto, a.chave
