import datetime
import queue
import threading
import time
import types

import gui_agentes


class _Variavel:
    def __init__(self):
        self.valores = []
        self.threads = []

    def set(self, valor):
        self.threads.append(threading.get_ident())
        self.valores.append(valor)


class _Frame:
    def __init__(self, threads):
        self.threads = threads

    def grid(self, **kwargs):
        self.threads.append(threading.get_ident())


def test_atualizacao_nao_espera_leitura_lenta_e_aplica_resultados_na_interface(monkeypatch):
    iniciou = threading.Event()
    liberar = threading.Event()

    def leitura_lenta(*args):
        iniciou.set()
        assert liberar.wait(2)
        return {
            "agora": args[2], "ler_acao": False, "estados": {}, "tarefas": {},
            "acoes": {}, "google": None,
        }

    monkeypatch.setattr(gui_agentes, "_capturar_snapshot", leitura_lenta)
    threads_interface = []

    class Painel:
        _atualizar = gui_agentes.JanelaAgentes._atualizar

        def __init__(self):
            self._fechando = False
            self._leitura_em_andamento = False
            self._ultima_leitura_acao = datetime.datetime.now()
            self._cartoes = {}
            self._disparos = {}
            self._resultados_leitura = queue.Queue()
            self._resultados_rodar_aqui = queue.Queue()
            self._resultados_disparar = queue.Queue()
            self._resultados_google = queue.Queue()
            self.var_rodape = _Variavel()
            self.aplicados = []
            self._aplicar_snapshot = self.aplicados.append

        def after(self, intervalo, callback):
            threads_interface.append(threading.get_ident())
            return "timer"

    painel = Painel()
    principal = threading.get_ident()
    inicio = time.perf_counter()
    painel._atualizar()
    duracao = time.perf_counter() - inicio

    try:
        assert iniciou.wait(1)
        assert duracao < 0.5
        assert painel._leitura_em_andamento
        assert threads_interface == [principal]
        liberar.set()
        painel._resultados_leitura.get(timeout=1)
        # A thread de leitura só publica na fila; a atualização dos widgets é
        # feita na próxima chamada de _atualizar, no thread principal.
        assert painel.aplicados == []
    finally:
        liberar.set()


def test_rodar_aqui_publica_resultado_sem_chamar_tk_pelo_thread_de_trabalho(monkeypatch):
    principal = threading.get_ident()
    threads_interface = []
    monkeypatch.setitem(
        __import__("sys").modules, "pythoncom",
        types.SimpleNamespace(CoInitialize=lambda: None, CoUninitialize=lambda: None),
    )
    monkeypatch.setattr(gui_agentes.agentes, "_servico_agendador", lambda **kwargs: object())
    monkeypatch.setattr(gui_agentes.agentes, "rodar_aqui", lambda ag, servico=None: {
        "codigo": 0, "saida": "ok", "durou_s": 0.01,
    })

    class Painel:
        _rodar_aqui = gui_agentes.JanelaAgentes._rodar_aqui

        def __init__(self):
            self._rodando_aqui = set()
            self._resultados_rodar_aqui = queue.Queue()
            self._cartoes = {"teste": {
                "frame_saida": _Frame(threads_interface),
                "var_titulo_saida": _Variavel(),
            }}

        def _habilitar(self, ag, ligado):
            threads_interface.append(threading.get_ident())

        def _escrever_saida(self, ag, texto):
            threads_interface.append(threading.get_ident())

        def after(self, *args):
            raise AssertionError("thread de trabalho não pode chamar Tk.after")

    painel = Painel()
    agente = types.SimpleNamespace(chave="teste", tarefa="tarefa", pode_disparar=True)
    painel._rodar_aqui(agente)

    ag, inicio, resultado = painel._resultados_rodar_aqui.get(timeout=2)
    assert ag is agente
    assert isinstance(inicio, datetime.datetime)
    assert resultado["codigo"] == 0
    assert threads_interface and set(threads_interface) == {principal}


def test_disparo_aguarda_se_a_leitura_do_agendador_nao_confirma_estado():
    agora = datetime.datetime.now()
    agente = types.SimpleNamespace(chave="teste")

    class Painel:
        _acompanhar_disparo = gui_agentes.JanelaAgentes._acompanhar_disparo

        def __init__(self):
            self._disparos = {"teste": agora}
            self._concluidos = {}
            self.habilitacoes = []

        def _habilitar(self, ag, ligado):
            self.habilitacoes.append(ligado)

    painel = Painel()
    nivel, texto = painel._acompanhar_disparo(
        agente, "ok", "estado anterior", agora, {"existe": None, "erro": "sem sinal"})

    assert nivel == "rodando"
    assert "esperando o Agendador" in texto
    assert "teste" in painel._disparos
    assert painel.habilitacoes == []


def test_disparo_recusado_reabilita_os_botoes():
    class Widget:
        def __init__(self):
            self.configuracoes = []

        def configure(self, **kwargs):
            self.configuracoes.append(kwargs)

    class Painel:
        _aplicar_resultado_disparo = gui_agentes.JanelaAgentes._aplicar_resultado_disparo

        def __init__(self):
            self._concluidos = {}
            self.habilitacoes = []
            self._cartoes = {"teste": {
                "simbolo": Widget(), "lbl_estado": Widget(), "var_estado": _Variavel(),
            }}

        def _habilitar(self, ag, ligado):
            self.habilitacoes.append(ligado)

    painel = Painel()
    agente = types.SimpleNamespace(chave="teste")
    painel._aplicar_resultado_disparo(agente, False, "Agendador indisponível")

    assert painel.habilitacoes == [True]
    assert "Agendador indisponível" in painel._cartoes["teste"]["var_estado"].valores[-1]
