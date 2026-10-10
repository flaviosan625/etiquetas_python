"""Seleção em lote e alertas de impressão, sem abrir janela ou acessar produção real."""
from types import MethodType, SimpleNamespace
from unittest.mock import Mock
from collections import OrderedDict
import queue

import pytest

import gui


class Variavel:
    def __init__(self, valor):
        self.valor = valor

    def get(self):
        return self.valor

    def set(self, valor):
        self.valor = valor


@pytest.fixture
def janela():
    destino = next(iter(gui.MAQUINAS_RIP))
    itens = [
        {"arquivo": "novo.pdf", "envios_anteriores": [], "maquina": destino,
         "dimensao": {"largura_m": 1, "altura_m": 2}, "categoria": "LONA", "area_total_m2": 2},
        {"arquivo": "antigo.pdf", "envios_anteriores": [{"quando": "2026-10-01T10:00:00"}],
         "maquina": destino, "dimensao": None, "categoria": "LONA", "area_total_m2": None},
        {"arquivo": "outro.pdf", "envios_anteriores": [], "maquina": destino,
         "dimensao": None, "categoria": "ADESIVO", "area_total_m2": None},
    ]
    tela = SimpleNamespace(
        itens=itens, marcados={i: Variavel(False) for i in range(3)}, historico_ilegivel=None,
        var_maquina_lote=Variavel(""), var_contagem=Variavel(""), var_subtotais=Variavel(""),
        btn_enviar=Mock(), btn_marcar_novos=Mock(), btn_aplicar_maquina=Mock(),
    )
    for nome in (
        "_marcar_nunca_enviados", "_limpar_selecao", "_definir_selecao", "_itens_marcados",
        "_atualizar_rodape", "_aplicar_maquina", "_aplicar_maquina_aos_marcados", "_trocar_maquina",
    ):
        setattr(tela, nome, MethodType(getattr(gui.JanelaEnviarImpressao, nome), tela))

    def refazer():
        tela.marcados = {i: Variavel(False) for i in range(3)}

    tela._preencher_lista = Mock(side_effect=refazer)
    return tela


def test_marcar_nunca_enviados_seleciona_apenas_ineditos(janela):
    janela._marcar_nunca_enviados()
    assert [v.get() for v in janela.marcados.values()] == [True, False, True]


def test_marcar_ineditos_preserva_reimpressao_escolhida_manualmente(janela):
    janela.marcados[1].set(True)
    janela._marcar_nunca_enviados()
    assert all(v.get() for v in janela.marcados.values())


def test_historico_ilegivel_nao_transforma_todos_em_ineditos(janela, monkeypatch):
    aviso = Mock()
    monkeypatch.setattr(gui.messagebox, "showwarning", aviso)
    janela.historico_ilegivel = "JSON incompleto"
    janela._marcar_nunca_enviados()
    assert not any(v.get() for v in janela.marcados.values())
    aviso.assert_called_once()
    janela._atualizar_rodape()
    janela.btn_marcar_novos.config.assert_called_with(state="disabled")


def test_aplicar_maquina_altera_so_marcados_e_preserva_selecao(janela):
    maquina = list(gui.MAQUINAS_RIP)[-1]
    origem = janela.itens[2]["maquina"]
    janela.marcados[0].set(True)
    janela.marcados[1].set(True)
    janela.var_maquina_lote.set(maquina)
    janela._aplicar_maquina_aos_marcados()
    assert [i["maquina"] for i in janela.itens] == [maquina, maquina, origem]
    assert [v.get() for v in janela.marcados.values()] == [True, True, False]
    assert janela.itens[0]["giro"] == gui.prever_giro(janela.itens[0]["dimensao"], maquina)
    assert janela.itens[0]["cabe"] == gui.cabe_na_maquina(janela.itens[0]["dimensao"], maquina)
    janela._preencher_lista.assert_called_once()


@pytest.mark.parametrize("maquina", ["", "máquina inexistente"])
def test_maquina_invalida_nao_altera_destino(janela, maquina):
    antes = [i["maquina"] for i in janela.itens]
    janela.marcados[0].set(True)
    janela.var_maquina_lote.set(maquina)
    janela._aplicar_maquina_aos_marcados()
    assert [i["maquina"] for i in janela.itens] == antes
    janela._preencher_lista.assert_not_called()


def test_sem_selecao_nao_aplica_maquina(janela):
    janela.var_maquina_lote.set(next(iter(gui.MAQUINAS_RIP)))
    janela._aplicar_maquina_aos_marcados()
    janela._preencher_lista.assert_not_called()


def test_troca_individual_continua_preservando_os_marcados(janela):
    maquina = list(gui.MAQUINAS_RIP)[-1]
    janela.combos_maquina = {1: Variavel(maquina)}
    janela.marcados[2].set(True)
    janela._trocar_maquina(1)
    assert janela.itens[1]["maquina"] == maquina
    assert [v.get() for v in janela.marcados.values()] == [False, False, True]


def test_limpar_selecao_desabilita_envio_sem_mudar_maquinas(janela):
    antes = [i["maquina"] for i in janela.itens]
    janela._marcar_nunca_enviados()
    janela._limpar_selecao()
    assert not any(v.get() for v in janela.marcados.values())
    assert [i["maquina"] for i in janela.itens] == antes
    janela.btn_enviar.config.assert_called_with(text="Enviar", state="disabled")


def test_lote_calcula_totais_uma_vez_sem_travar_a_cada_item(janela):
    atualizar = Mock()
    janela._atualizar_rodape = atualizar
    janela._marcar_nunca_enviados()
    atualizar.assert_called_once()


def test_estado_do_rip_pinta_tema_e_mostra_erro_sem_excecao(monkeypatch):
    monkeypatch.setattr(gui, "estado_do_rip", lambda: {
        "nivel": "ok", "texto": "RIP ativo", "erros": {"SWJ320A": "Pasta ausente"},
    })
    tela = SimpleNamespace(
        var_rip=Variavel(""), ponto_rip=Mock(), rotulo_rip=Mock(),
        _reagendar_estado_do_rip=Mock(),
    )
    avisos = []
    gui.JanelaEnviarImpressao._mostrar_estado_do_rip(tela, avisos)
    assert tela.var_rip.get() == "RIP ativo"
    tela.ponto_rip.configure.assert_called_with(text="●", fg=gui.cores.positivo)
    assert len(avisos) == 1 and "Pasta ausente" in avisos[0]
    tela._reagendar_estado_do_rip.assert_called_once()


def test_atualizacao_periodica_renova_estado_e_alertas():
    tela = SimpleNamespace(winfo_exists=lambda: True, _avisar_fila_parada=Mock())
    gui.JanelaEnviarImpressao._repintar_estado_do_rip(tela)
    tela._avisar_fila_parada.assert_called_once()


@pytest.mark.parametrize("confirmado", [False, True])
def test_envio_em_lote_continua_dependendo_da_conferencia(monkeypatch, confirmado):
    item = {"arquivo": "novo.pdf"}
    bloqueado = {"arquivo": "conflito.pdf"}
    resultado = {"limpos": [item], "atencao": [], "bloqueados": [(bloqueado, "Já está na fila")]}
    conferir = Mock(return_value=resultado)
    monkeypatch.setattr(gui, "conferir_envio", conferir)
    monkeypatch.setattr(gui, "JanelaConferenciaEnvio", lambda *_: SimpleNamespace(confirmado=confirmado))
    tela = SimpleNamespace(_itens_marcados=lambda: [item, bloqueado], _executar_envio=Mock())
    gui.JanelaEnviarImpressao._conferir_e_enviar(tela)
    conferir.assert_called_once_with([item, bloqueado])
    if confirmado:
        tela._executar_envio.assert_called_once_with([item], resultado["bloqueados"])
    else:
        tela._executar_envio.assert_not_called()


def test_previa_atrasada_de_outra_pasta_nao_aparece_na_linha_atual(tmp_path):
    antiga, atual = tmp_path / "cliente_a.pdf", tmp_path / "cliente_b.pdf"
    antiga.write_bytes(b"a")
    atual.write_bytes(b"b")
    chave_a = gui.previas_impressao.chave_do_arquivo(antiga)
    chave_b = gui.previas_impressao.chave_do_arquivo(atual)
    fila = queue.Queue()
    fila.put((chave_a, b"imagem antiga", ""))
    tela = SimpleNamespace(
        _fechando=False, _fila_previas=fila, _cache_previas=OrderedDict(),
        _previas_pendentes={chave_a}, _rotulos_previas={chave_b: [(Mock(), atual, atual.name)]},
        _mostrar_previa=Mock(), after=Mock(return_value="agendamento"), _consumir_previas=Mock(),
    )
    gui.JanelaEnviarImpressao._consumir_previas(tela)
    tela._mostrar_previa.assert_not_called()


def test_previa_chegada_apos_arquivo_mudar_e_descartada(tmp_path):
    arte = tmp_path / "arte.pdf"
    arte.write_bytes(b"a")
    chave = gui.previas_impressao.chave_do_arquivo(arte)
    arte.write_bytes(b"arte alterada")
    fila = queue.Queue()
    fila.put((chave, b"imagem antiga", ""))
    rotulo = Mock()
    tela = SimpleNamespace(
        _fechando=False, _fila_previas=fila, _cache_previas=OrderedDict(),
        _previas_pendentes={chave}, _rotulos_previas={chave: [(rotulo, arte, arte.name)]},
        _mostrar_previa=Mock(), after=Mock(), _consumir_previas=Mock(),
    )
    gui.JanelaEnviarImpressao._consumir_previas(tela)
    tela._mostrar_previa.assert_called_once_with(rotulo, arte.name, None, "Arquivo alterado — atualize a lista")


def test_redesenhar_mesmo_arquivo_reutiliza_leitura_em_andamento(tmp_path):
    arte = tmp_path / "arte.pdf"
    arte.write_bytes(b"a")
    item = {"caminho": arte, "arquivo": arte.name}
    chave = gui.previas_impressao.chave_do_arquivo(arte)
    tela = SimpleNamespace(
        _rotulos_previas={}, _cache_previas=OrderedDict(), _previas_pendentes={chave},
        _trabalho_previas=Mock(), _carregar_previa=Mock(),
    )
    gui.JanelaEnviarImpressao._solicitar_previa(tela, item, Mock())
    tela._trabalho_previas.submit.assert_not_called()


def test_atualizacao_da_previa_preserva_nome_sem_mudar_selecao():
    foto = object()
    rotulo = Mock()
    tela = SimpleNamespace(_foto_previa=Mock(return_value=foto), _foto_vazia=object())
    gui.JanelaEnviarImpressao._mostrar_previa(tela, rotulo, "arte.pdf", b"jpeg", "")
    rotulo.configure.assert_called_once_with(image=foto, text="arte.pdf")
    assert rotulo._foto_previa is foto


@pytest.fixture
def tela_de_envio(tmp_path, monkeypatch):
    """Widgets reais em janelas ocultas; nenhuma pasta de produção é acessada."""
    import tkinter as tk
    from config import CONFIG_PADRAO

    monkeypatch.setattr(gui.JanelaEnviarImpressao, "_escolher_pasta", lambda _: None)
    raiz = tk.Tk()
    raiz.withdraw()
    tela = gui.JanelaEnviarImpressao(raiz, CONFIG_PADRAO)
    tela.withdraw()
    try:
        yield tela
    finally:
        tela.destroy()
        raiz.destroy()


def test_imagem_e_nome_selecionam_a_mesma_arte_na_tela(tela_de_envio, tmp_path):
    import tkinter as tk

    arte = tmp_path / "1UN DECORFLEX IMPRESSO 1X2M_painel.pdf"
    arte.write_bytes(b"arquivo sem previa")
    item = {"caminho": arte, "arquivo": arte.name, "envios_anteriores": [],
            "maquina": "DOCAN R5200", "dimensao": None, "quantidade": 1,
            "categoria": "DECORFLEX", "area_total_m2": None, "pasta_trabalho": "COMPOSTOS",
            "cabe": True, "giro": None}
    tela = tela_de_envio
    tela.itens = [item]
    tela._preencher_lista()
    [selecao] = [w for w in tela.frame_lista.winfo_children() if isinstance(w, tk.Checkbutton)]
    assert arte.name in selecao.cget("text")
    assert selecao.cget("image")
    assert not tela.marcados[0].get()
    selecao.invoke()
    assert tela._itens_marcados() == [item]
    assert item["maquina"] == "DOCAN R5200"


def test_pdf_carrega_imagem_real_sem_perder_nome_ou_marcacao(tela_de_envio, tmp_path):
    import tkinter as tk
    import pymupdf

    arte = tmp_path / "1UN DECORFLEX 1X2M_painel.pdf"
    with pymupdf.open() as doc:
        pagina = doc.new_page(width=300, height=200)
        pagina.draw_rect(pagina.rect, color=(1, 0, 0), fill=(1, 0, 0))
        doc.save(str(arte))
    item = {"caminho": arte, "arquivo": arte.name, "envios_anteriores": [],
            "maquina": "DOCAN R5200", "dimensao": None, "quantidade": 1,
            "categoria": "DECORFLEX", "area_total_m2": None, "pasta_trabalho": "COMPOSTOS",
            "cabe": True, "giro": None}
    tela = tela_de_envio
    tela.itens = [item]
    tela._preencher_lista()
    [selecao] = [w for w in tela.frame_lista.winfo_children() if isinstance(w, tk.Checkbutton)]
    selecao.invoke()
    # O worker produz JPEG; a thread principal cria e aplica a PhotoImage.
    resultado = tela._fila_previas.get(timeout=3)
    tela._fila_previas.put(resultado)
    tela._consumir_previas()
    assert selecao._foto_previa is not None
    assert (selecao._foto_previa.width(), selecao._foto_previa.height()) == (112, 80)
    assert selecao.cget("text") == arte.name
    assert tela._itens_marcados() == [item]
