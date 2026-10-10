"""Conferência da montagem em uma pasta temporária; nunca executa produção."""
import copy
import io
import pathlib
import threading
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import config
import gui_montagem as gm


class ExecutorImediato:
    def __init__(self, *args, **kwargs):
        self.encerrado = False

    def submit(self, funcao, *args, **kwargs):
        funcao(*args, **kwargs)

    def shutdown(self, **kwargs):
        self.encerrado = True


def _previa_de_mentira(pasta, maquina, arquivos=None, folga_m=0.05, passadas_docan=None):
    nomes = sorted(a.name for a in pathlib.Path(pasta).iterdir() if a.is_file())
    if arquivos is not None:
        nomes = [n for n in nomes if n in arquivos]
    pendentes = [n for n in nomes if pathlib.Path(n).suffix in (".eps", ".psd")]
    itens = []
    for nome in nomes:
        if nome in pendentes:
            continue
        paginas = 2 if "MULTI" in nome else 1
        quantidade = 2 if "MULTI" in nome else 1
        for pagina in range(paginas):
            for copia in range(1, quantidade + 1):
                itens.append({"arquivo": nome, "numero": len(itens) + 1,
                              "nome_m": (1.0, 0.5), "medida_m": (1.0, 0.5),
                              "pagina": pagina, "copia": copia,
                              "quantidade": quantidade, "diferenca_mm": 0,
                              "girada": False, "dpi": None, "qualidade": "vetor",
                              "estado": "ok", "avisos": [],
                              "posicao_m": [0.2 + (len(itens) % 3) * 1.05,
                                            0.12 + (len(itens) // 3) * 0.55, 1.0, 0.5]})
    folhas = ([{"categoria": "LONA", "tamanho": "5.00 x 1.15 m",
                "largura_m": 5.0, "folha_m": 1.15, "pecas": len(itens),
                "itens": itens}] if itens else [])
    return {"pasta": pathlib.Path(pasta), "maquina": maquina,
            "passadas_docan": passadas_docan,
            "cliente": "CLIENTE", "folhas": folhas, "a_converter": pendentes,
            "recusadas": [], "pior_diferenca_mm": 0,
            "folga_m": folga_m, "metragem_rolo": 1.15 if itens else 0,
            "aproveitamento_rolo": 0.5 if itens else None,
            "versoes": {n: {"tamanho": (pathlib.Path(pasta) / n).stat().st_size,
                            "mtime_ns": (pathlib.Path(pasta) / n).stat().st_mtime_ns}
                        for n in nomes}}


@pytest.fixture
def tela(tmp_path, monkeypatch):
    # Todos os caminhos persistentes e todos os efeitos do motor ficam isolados.
    monkeypatch.setattr(config, "CONFIG_PATH", tmp_path / "config.json")
    monkeypatch.setattr(gm.montagem, "PASTA_RAIZ", tmp_path)
    monkeypatch.setattr(gm, "carregar_config", lambda: {"montagem": {}})
    monkeypatch.setattr(gm, "salvar_config", Mock())
    monkeypatch.setattr(gm, "ThreadPoolExecutor", ExecutorImediato)
    monkeypatch.setattr(gm.previas_impressao, "carregar",
                        lambda *_: (None, "Prévia indisponível"))
    monkeypatch.setattr(gm.montagem, "prever_pasta", Mock(side_effect=_previa_de_mentira))
    monkeypatch.setattr(gm.montagem, "montar_pasta",
                        Mock(return_value={"folhas": [], "recusadas": []}))
    monkeypatch.setattr(gm.montagem, "converter_o_que_precisa", Mock(return_value=[]))
    monkeypatch.setattr(gm.messagebox, "showerror", Mock())
    monkeypatch.setattr(gm.messagebox, "showwarning", Mock())
    pasta = tmp_path / "DOCAN R5200"
    pasta.mkdir()
    for nome in ("1UN LONA 1.00X0.50M_CLIENTE_A.pdf",
                 "1UN LONA 1.00X0.50M_CLIENTE_B.pdf"):
        (pasta / nome).write_bytes(b"arte temporaria")
    try:
        raiz = gm.tk.Tk()
    except gm.tk.TclError as erro:
        pytest.skip(f"Tk indisponível: {erro}")
    raiz.withdraw()
    aba = gm._AbaMaquina(raiz, "DOCAN R5200")
    aba.pack(fill="both", expand=True)
    raiz.update_idletasks()
    _consumir(aba)
    yield aba
    aba.fechar()
    raiz.destroy()


def _consumir(tela):
    if tela._job_fila is not None:
        tela.after_cancel(tela._job_fila)
    tela._consumir()


@pytest.mark.parametrize("texto,esperado", [("5", 0.05), ("1", 0.01),
                                         ("2,5", 0.025), (" 3.5 ", 0.035)])
def test_controle_de_espaco_converte_cm_em_metros(texto, esperado):
    assert gm._folga_m_do_texto(texto) == pytest.approx(esperado)


@pytest.mark.parametrize("texto", ["", "abc", "0", "0,5", "nan", "inf", "-2"])
def test_controle_recusa_espaco_invalido(texto):
    with pytest.raises(ValueError):
        gm._folga_m_do_texto(texto)


def test_tela_inicia_com_todos_marcados_e_espaco_de_5_cm(tela):
    assert tela._selecionados == set(tela._arquivos)
    assert tela.var_folga.get() == "5"
    assert not tela._suja
    assert tela.btn_montar.cget("state") == "normal"
    for linha in tela.tabela.get_children():
        assert tela.tabela.set(linha, "marcar") == "☑"
        assert tela.tabela.item(linha, "text").endswith(".pdf")
    gm.salvar_config.assert_not_called()


def test_desmarcar_arquivo_exige_recalculo_e_preserva_os_demais(tela):
    retirado = next(iter(tela._arquivos))
    tela._alternar_arquivo(retirado)
    assert retirado not in tela._selecionados
    assert tela.btn_montar.cget("state") == "disabled"
    tela._montar_agora()
    gm.montagem.montar_pasta.assert_not_called()
    tela.calcular()
    _consumir(tela)
    chamada = gm.montagem.prever_pasta.call_args
    assert chamada.kwargs["arquivos"] == sorted(tela._selecionados)
    assert len(tela._previa["folhas"][0]["itens"]) == 1
    assert tela.tabela.set(tela._linhas[retirado], "quantidade") == "Não marcado"
    assert tela._arquivos[retirado].is_file()


def test_limpar_selecao_passada_vazia_nunca_significa_montar_todos(tela):
    tela._limpar_selecao()
    tela.calcular()
    _consumir(tela)
    assert gm.montagem.prever_pasta.call_args.kwargs["arquivos"] == []
    assert tela._previa["folhas"] == []
    assert tela.btn_montar.cget("state") == "disabled"


def test_espaco_modificado_exige_recalcular_e_chega_ao_motor(tela):
    tela.var_folga.set("2,5")
    assert tela._suja
    tela._montar_agora()
    gm.montagem.montar_pasta.assert_not_called()
    tela.calcular()
    _consumir(tela)
    assert gm.montagem.prever_pasta.call_args.kwargs["folga_m"] == pytest.approx(0.025)
    assert not tela._suja
    assert tela.btn_montar.cget("state") == "normal"


def test_montar_recebe_exatamente_a_selecao_espaco_e_versoes_conferidas(tela):
    versoes = copy.deepcopy(tela._previa["versoes"])
    tela._montar_agora()
    chamada = gm.montagem.montar_pasta.call_args
    assert chamada.kwargs == {"arquivos": sorted(tela._selecionados),
                             "folga_m": 0.05, "versoes_esperadas": versoes,
                             "passadas_docan": None}


def test_passadas_planejadas_exigem_recalculo_e_chegam_a_ficha(tela):
    tela.var_passadas_docan.set("4")
    tela._configuracao_mudou()
    tela._montar_agora()
    gm.montagem.montar_pasta.assert_not_called()
    tela.calcular()
    _consumir(tela)
    assert tela._previa["passadas_docan"] == 4
    tela._montar_agora()
    assert gm.montagem.montar_pasta.call_args.kwargs["passadas_docan"] == 4


def test_imagem_nome_e_checkbox_marcam_a_mesma_arte(tela, monkeypatch):
    nome = next(iter(tela._arquivos))
    linha = tela._linhas[nome]
    monkeypatch.setattr(tela.tabela, "identify_row", lambda _: linha)
    for coluna in ("#0", "#1"):
        monkeypatch.setattr(tela.tabela, "identify_column", lambda _, c=coluna: c)
        antes = nome in tela._selecionados
        assert tela._clicar_arquivo(SimpleNamespace(x=10, y=10)) == "break"
        assert (nome in tela._selecionados) is not antes


def test_mapa_usa_a_posicao_e_dimensoes_reais_da_peca(tela):
    tela._desenhar_mapa()
    retangulos = [i for i in tela.canvas.find_withtag("peca_0")
                  if tela.canvas.type(i) == "rectangle"]
    assert len(retangulos) == 1
    x, y, w, h = tela._previa["folhas"][0]["itens"][0]["posicao_m"]
    escala = tela._escala_mapa
    assert tela.canvas.coords(retangulos[0]) == pytest.approx(
        [20 + x * escala, 36 + y * escala,
         20 + (x + w) * escala, 36 + (y + h) * escala])


def test_mapa_destaca_o_arquivo_correto_sem_alterar_selecao(tela):
    item = tela._previa["folhas"][0]["itens"][1]
    antes = set(tela._selecionados)
    tela._destacar_arquivo(item)
    assert tela.tabela.selection() == (tela._linhas[item["arquivo"]],)
    assert tela._selecionados == antes
    assert item["arquivo"] in tela.var_mapa.get()


def test_pdf_multipagina_avisa_que_miniatura_so_mostra_primeira(tela):
    nome = "2UN LONA 1.00X0.50M_CLIENTE_MULTI.pdf"
    (tela.pasta / nome).write_bytes(b"pdf temporario multipagina")
    tela.calcular()
    _consumir(tela)
    linha = tela._linhas[nome]
    assert tela.tabela.set(linha, "quantidade") == "2 pág · 2 un"
    assert "Miniatura da primeira página" in tela.tabela.set(linha, "defeitos")
    tela.tabela.selection_set(linha)
    tela._detalhar_selecao()
    assert "confira as demais no arquivo" in tela.var_arquivo.get()


def test_conversao_pendente_impede_montar_arte_sem_previa(tela):
    nome = "1UN LONA 1.00X0.50M_CLIENTE_PENDENTE.eps"
    (tela.pasta / nome).write_bytes(b"eps temporario")
    tela.calcular()
    _consumir(tela)
    assert nome in tela._previa["a_converter"]
    assert tela.btn_montar.cget("state") == "disabled"
    tela._montar_agora()
    gm.montagem.montar_pasta.assert_not_called()
    assert "Converta e recalcule" in tela.var_recusadas.get()
    tela._converter()
    assert gm.montagem.converter_o_que_precisa.call_args.kwargs["arquivos"] == sorted(
        tela._selecionados)


def test_previa_antiga_de_outra_geracao_e_descartada(tela):
    anterior = tela._previa
    tela._fila.put(("calculo", tela._geracao - 1, {"folhas": []}, None, ((), 0.05)))
    _consumir(tela)
    assert tela._previa is anterior


def test_worker_nao_chama_tk_mesmo_quando_janela_ja_fechou(tela, monkeypatch):
    monkeypatch.setattr(tela, "after", Mock(side_effect=AssertionError("Tk no worker")))
    tela.fechar()
    argumentos = (tela._geracao, tela._config_calculada, sorted(tela._selecionados), 0.05)
    erros = []

    def trabalhar():
        try:
            tela._calcular_no_worker(*argumentos)
        except Exception as erro:
            erros.append(erro)

    worker = threading.Thread(target=trabalhar)
    worker.start()
    worker.join(timeout=3)
    assert not worker.is_alive()
    assert not erros
    assert not tela._fila.empty()


def test_fechar_cancela_workers_e_para_o_consumo(tela):
    tela.fechar()
    assert tela._trabalho.encerrado
    assert tela._trabalho_previas.encerrado
    tela._consumir()
    assert tela._fechando


def test_salvar_espaco_so_grava_a_maquina_ao_clicar(tela, monkeypatch):
    config_anterior = {"tema": "escuro", "montagem": {"SWJ320A": {"folga_m": 0.07}}}
    monkeypatch.setattr(gm, "carregar_config", lambda: copy.deepcopy(config_anterior))
    tela.var_folga.set("3")
    gm.salvar_config.assert_not_called()
    tela._salvar_folga()
    salvo = gm.salvar_config.call_args.args[0]
    assert salvo["montagem"]["DOCAN R5200"]["folga_m"] == pytest.approx(0.03)
    assert salvo["montagem"]["SWJ320A"]["folga_m"] == 0.07
    assert salvo["tema"] == "escuro"


def test_recusada_tem_motivo_visivel_e_tag_de_pendencia(tela):
    nome = next(iter(tela._arquivos))
    previa = copy.deepcopy(tela._previa)
    previa["recusadas"] = [{"arquivo": nome, "motivo": "Página 2 não cabe na largura"}]
    previa["folhas"][0]["itens"] = [i for i in previa["folhas"][0]["itens"]
                                     if i["arquivo"] != nome]
    previa["folhas"][0]["pecas"] = 1
    tela._mostrar(previa, None, tela._config_calculada)
    assert tela.tabela.item(tela._linhas[nome], "tags") == ("aviso",)
    assert "Página 2" in tela.tabela.set(tela._linhas[nome], "defeitos")
    assert nome in tela.var_recusadas.get()
    assert tela.btn_montar.cget("state") == "normal", "Os outros arquivos podem montar."


def test_espaco_preferido_e_lido_sem_salvar_ao_abrir(tela, monkeypatch):
    monkeypatch.setattr(gm, "carregar_config",
                        lambda: {"montagem": {"DOCAN R5200": {"folga_m": 0.03}}})
    outra = gm._AbaMaquina(tela.master, "DOCAN R5200")
    try:
        assert outra.var_folga.get() == "3"
        gm.salvar_config.assert_not_called()
    finally:
        outra.fechar()
        outra.destroy()


def test_falha_de_resolucao_nao_se_passa_por_vetor():
    assert gm._resolucao_em_palavras({"qualidade": "nao_verificada", "dpi": None}) == (
        "resolução não verificada")


def test_miniatura_chegada_apos_arte_mudar_e_descartada(tela):
    nome = next(iter(tela._arquivos))
    caminho = tela._arquivos[nome]
    chave = gm.previas_impressao.chave_do_arquivo(caminho)
    caminho.write_bytes(b"uma nova versao da arte, com outro tamanho")
    tela._aplicar_miniatura(nome, chave, b"foto antiga", "")
    assert tela._fotos.get(nome, (None,))[0] != chave


def test_miniatura_real_nunca_muda_o_nome_ou_a_marcacao(tela):
    imagem = pytest.importorskip("PIL.Image")
    nome = next(iter(tela._arquivos))
    chave = gm.previas_impressao.chave_do_arquivo(tela._arquivos[nome])
    memoria = io.BytesIO()
    imagem.new("RGB", (224, 160), color=(80, 120, 200)).save(memoria, format="JPEG")
    antes = set(tela._selecionados)
    tela._aplicar_miniatura(nome, chave, memoria.getvalue(), "")
    foto = tela._fotos[nome][1]
    assert foto is not None
    assert (foto.width(), foto.height()) == (112, 80)
    assert tela.tabela.item(tela._linhas[nome], "image")
    assert tela.tabela.item(tela._linhas[nome], "text") == nome
    assert tela._selecionados == antes
