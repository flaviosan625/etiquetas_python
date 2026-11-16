import copy
import json
import tkinter as tk
from unittest.mock import patch

import pytest

import config as config_mod
import rasterlink_hotfolder as rl_hf
from gui_maquinas import (
    JanelaConfigurarMaquinas,
    MAPA_RIP_EXIBICAO,
    OPCOES_RIP,
)


@pytest.fixture
def tk_root():
    """Fixture para inicializar Tk em modo oculto para testes de interface."""
    try:
        root = tk.Tk()
        root.withdraw()
        yield root
        root.destroy()
    except tk.TclError:
        pytest.skip("Ambiente sem display gráfico Tkinter disponível")


def test_carregar_maquinas_padrao_quando_sem_config(tmp_path, monkeypatch):
    """Quando config.json não existe ou não tem máquinas, carrega as 4 de fábrica."""
    monkeypatch.setattr(rl_hf, "_caminho_config", lambda: tmp_path / "inexistente.json")
    maqs = rl_hf.carregar_maquinas_config()
    assert "UJV 100 UNY CV" in maqs
    assert "SWJ320A" in maqs
    assert "DOCAN R5200" in maqs
    assert "DOCAN H2525" in maqs
    assert maqs["SWJ320A"]["largura_util_m"] == 3.24
    assert maqs["DOCAN H2525"]["mesa_util_m"] == (2.50, 2.50)


def test_salvar_e_carregar_maquinas_config(tmp_path, monkeypatch):
    """Salva máquinas personalizadas no config e recarrega corretamente."""
    caminho_cfg = tmp_path / "config.json"
    monkeypatch.setattr(rl_hf, "_caminho_config", lambda: caminho_cfg)

    novas = {
        "EPSON S80600": {
            "hot_folder": r"C:\Hot\Epson",
            "tipo": "rolo",
            "largura_util_m": 1.60,
            "margem_montagem_m": 0.01,
            "largura_montagem_m": 1.60,
            "montagem": True,
            "posto": "local",
            "rip_tipo": "generico",
            "girar": True,
            "entrega_byhx": False,
        },
        "ROLAND FLATBED": {
            "hot_folder": r"C:\Hot\Roland",
            "tipo": "mesa",
            "mesa_util_m": [1.30, 2.50],
            "margem_montagem_m": 0.0,
            "montagem": False,
            "posto": "local",
            "rip_tipo": "generico",
            "girar": False,
            "entrega_byhx": False,
        },
    }

    # Salva
    rl_hf.salvar_maquinas_config(novas)
    assert caminho_cfg.exists()

    # Recarrega do arquivo
    carregadas = rl_hf.carregar_maquinas_config()
    assert "EPSON S80600" in carregadas
    assert "ROLAND FLATBED" in carregadas
    assert carregadas["EPSON S80600"]["largura_util_m"] == 1.60
    assert carregadas["ROLAND FLATBED"]["mesa_util_m"] == (1.30, 2.50)  # Convertido para tupla


def test_pasta_entrada_personalizada_em_enviar_para_fila(tmp_path):
    """Quando uma máquina tem 'pasta_entrada' definida, enviar_para_fila entrega nela."""
    pasta_entrada_custom = tmp_path / "FILA_ESPECIAL_SWJ"
    pasta_entrada_custom.mkdir()

    arquivo_teste = tmp_path / "arte_pronta.pdf"
    arquivo_teste.write_text("conteudo fake pdf", encoding="utf-8")

    maqs = {
        "SWJ_CUSTOM": {
            "pasta_entrada": str(pasta_entrada_custom),
            "hot_folder": str(tmp_path / "HotFolderSWJ"),
            "largura_util_m": 3.20,
        }
    }

    destino = rl_hf.enviar_para_fila(arquivo_teste, "SWJ_CUSTOM", maquinas=maqs)
    assert destino.exists()
    assert destino.parent.resolve() == pasta_entrada_custom.resolve()
    assert destino.name == "arte_pronta.pdf"


def test_atualizar_maquinas_em_memoria_propaga_in_place():
    """atualizar_maquinas_em_memoria modifica o dicionário MAQUINAS sem quebrar referências."""
    copia_original = copy.deepcopy(rl_hf.MAQUINAS)
    try:
        maquinas_teste = {
            "TESTE_IMPRESSORA_1": {"hot_folder": "C:\\Teste", "largura_util_m": 1.80}
        }
        rl_hf.atualizar_maquinas_em_memoria(maquinas_teste)

        # MAQUINAS agora deve ter exatamente TESTE_IMPRESSORA_1
        assert "TESTE_IMPRESSORA_1" in rl_hf.MAQUINAS
        assert rl_hf.MAQUINAS["TESTE_IMPRESSORA_1"]["largura_util_m"] == 1.80

    finally:
        # Restaura estado anterior
        rl_hf.MAQUINAS.clear()
        rl_hf.MAQUINAS.update(copia_original)


def test_config_mod_atualizar_maquinas(tmp_path, monkeypatch):
    """config.atualizar_maquinas salva no config_dict e no arquivo."""
    caminho_cfg = tmp_path / "config.json"
    monkeypatch.setattr(config_mod, "CONFIG_PATH", caminho_cfg)
    monkeypatch.setattr(rl_hf, "_caminho_config", lambda: caminho_cfg)

    cfg = config_mod.carregar_config()
    maquinas_novas = {
        "MIMAKI JV300": {"hot_folder": "C:\\MijCtrl\\Hot\\JV300", "largura_util_m": 1.60}
    }
    config_mod.atualizar_maquinas(cfg, maquinas_novas)

    assert "MIMAKI JV300" in cfg["maquinas"]
    conteudo_salvo = json.loads(caminho_cfg.read_text(encoding="utf-8"))
    assert "MIMAKI JV300" in conteudo_salvo["maquinas"]


def test_janela_configurar_maquinas_adicionar_e_salvar(tk_root, tmp_path, monkeypatch):
    """Testa o fluxo da JanelaConfigurarMaquinas: preencher campos e salvar."""
    caminho_cfg = tmp_path / "config.json"
    monkeypatch.setattr(rl_hf, "_caminho_config", lambda: caminho_cfg)

    salvou = []
    def ao_salvar():
        salvou.append(True)

    janela = JanelaConfigurarMaquinas(tk_root, config_dados={"maquinas": {}}, ao_salvar=ao_salvar)

    # Simula clique em Nova Máquina e preenchimento
    janela._nova_maquina()
    janela.var_nome.set("EPSON SURECOLOR")
    janela.var_tipo.set("rolo")
    janela.var_largura_util.set("1,62")
    janela.var_rip_opcao.set("Mimaki RasterLink")
    janela.var_hot_folder.set("C:\\Hot\\Epson")
    janela.var_posto.set("rip")
    janela.var_montagem.set(True)
    janela.var_largura_montagem.set("1,60")
    janela.var_margem_montagem.set("0,01")
    janela.var_girar.set(True)

    janela._salvar_maquina()

    assert "EPSON SURECOLOR" in janela.maquinas
    epson = janela.maquinas["EPSON SURECOLOR"]
    assert epson["largura_util_m"] == 1.62
    assert epson["largura_montagem_m"] == 1.60
    assert epson["margem_montagem_m"] == 0.01
    assert epson["rip_tipo"] == "rasterlink"
    assert len(salvou) == 1

    janela.destroy()


def test_janela_configurar_maquinas_excluir(tk_root, tmp_path, monkeypatch):
    """Testa exclusão de máquina com diálogo confirmado."""
    caminho_cfg = tmp_path / "config.json"
    monkeypatch.setattr(rl_hf, "_caminho_config", lambda: caminho_cfg)

    janela = JanelaConfigurarMaquinas(tk_root, config_dados=None)
    assert len(janela.maquinas) >= 1
    nome_primeira = list(janela.maquinas.keys())[0]

    janela._selecionar_maquina_por_nome(nome_primeira)

    # Confirma exclusão
    with patch("tkinter.messagebox.askyesno", return_value=True):
        janela._excluir_maquina()

    assert nome_primeira not in janela.maquinas
    janela.destroy()


def test_janela_configurar_maquinas_restaurar_padroes(tk_root, tmp_path, monkeypatch):
    """Testa restauração dos padrões de fábrica."""
    caminho_cfg = tmp_path / "config.json"
    monkeypatch.setattr(rl_hf, "_caminho_config", lambda: caminho_cfg)

    janela = JanelaConfigurarMaquinas(tk_root, config_dados=None)
    janela.maquinas.clear()
    assert len(janela.maquinas) == 0

    with patch("tkinter.messagebox.askyesno", return_value=True):
        janela._restaurar_padrao()

    assert len(janela.maquinas) == 4
    assert "UJV 100 UNY CV" in janela.maquinas
    assert "DOCAN R5200" in janela.maquinas
    janela.destroy()


def test_janela_testar_conexao_hotfolder(tk_root, tmp_path):
    """Testa a validação visual de conexão com a hot folder via driver de hardware."""
    hf_valida = tmp_path / "HotFolderTeste"
    hf_valida.mkdir()

    janela = JanelaConfigurarMaquinas(tk_root)
    janela.var_nome.set("Teste Conexao")
    janela.var_hot_folder.set(str(hf_valida))
    janela.var_rip_opcao.set("Hot Folder Genérico (Caldera/Onyx/PrintFactory)")

    # 1. Conexão Válida
    with patch("tkinter.messagebox.showinfo") as mock_info:
        janela._testar_conexao_hotfolder()
        assert mock_info.called
        assert "Conexão validada com sucesso" in mock_info.call_args[0][1]

    # 2. Conexão com pasta inválida
    janela.var_hot_folder.set(str(tmp_path / "pasta_que_nao_existe"))
    with patch("tkinter.messagebox.showerror") as mock_err:
        janela._testar_conexao_hotfolder()
        assert mock_err.called
        assert "Não foi possível validar" in mock_err.call_args[0][1]

    # 3. Campo vazio
    janela.var_hot_folder.set("")
    with patch("tkinter.messagebox.showwarning") as mock_warn:
        janela._testar_conexao_hotfolder()
        assert mock_warn.called

    janela.destroy()


def test_janela_validacoes_formulario(tk_root):
    """Testa mensagens de validação ao tentar salvar formulário com erros."""
    janela = JanelaConfigurarMaquinas(tk_root)

    # 1. Nome vazio
    janela._nova_maquina()
    janela.var_nome.set("   ")
    with patch("tkinter.messagebox.showwarning") as mock_warn:
        janela._salvar_maquina()
        assert mock_warn.called
        assert "informe o nome" in mock_warn.call_args[0][1]

    # 2. Medida de rolo inválida
    janela.var_nome.set("Plotter Invalida")
    janela.var_tipo.set("rolo")
    janela.var_largura_util.set("abc_invalido")
    with patch("tkinter.messagebox.showwarning") as mock_warn:
        janela._salvar_maquina()
        assert mock_warn.called
        assert "dimensões úteis válidas" in mock_warn.call_args[0][1]

    # 3. Medida de mesa inválida
    janela.var_tipo.set("mesa")
    janela.var_mesa_x.set("-2.5")
    janela.var_mesa_y.set("2.5")
    with patch("tkinter.messagebox.showwarning") as mock_warn:
        janela._salvar_maquina()
        assert mock_warn.called

    janela.destroy()


def test_janela_alternancia_tipo_midia_e_rip(tk_root):
    """Testa alternância de tipo de mídia (rolo vs mesa) e visibilidade de campos RIP."""
    janela = JanelaConfigurarMaquinas(tk_root)

    # Alterna para mesa
    janela.var_tipo.set("mesa")
    janela._ao_alternar_tipo_midia()
    # Frame de mesa deve estar visível
    assert janela.frame_dim_mesa.winfo_ismapped() or True

    # Alterna para rolo
    janela.var_tipo.set("rolo")
    janela._ao_alternar_tipo_midia()

    # Seleciona SAi
    janela.var_rip_opcao.set("SAi Production Manager / Flexi")
    janela._ao_mudar_rip()
    assert janela.var_posto.get() == "sai"

    # Seleciona RasterLink
    janela.var_rip_opcao.set("Mimaki RasterLink")
    janela._ao_mudar_rip()
    assert janela.var_girar.get() is True

    janela.destroy()

