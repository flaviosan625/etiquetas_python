"""
A pasta de produção, PLANA desde 03/10/2026.

Pedido dele: "assim que for criada a pasta de produção, criar somente uma
pasta de PRONTOS; deixar os arquivos soltos e, na medida que for ficando
pronto, eu arrasto pra pasta. Antes estava por material, gerava muita
pasta — como no nome já consta o que vamos produzir, não precisamos dessa
separação por pasta; só em lista, etiqueta e relatórios precisa ser tudo
separado".

Então o que estes testes travam mudou de lado: antes provavam que o
arquivo ia PRA subpasta do material; agora provam que ele NÃO sai do
lugar — e que a classificação por material, que continua existindo, saiu
da pasta e ficou no nome (_pasta_de_trabalho_para), que é de onde a OS,
as etiquetas e os relatórios sempre agruparam.
"""
import copy

from config import CONFIG_PADRAO
from producao import (
    garantir_estrutura_producao, organizar_pasta_producao, varrer_e_organizar_todas,
    gerar_relatorio_pendencias, formatar_relatorio_pendencias, _pasta_de_trabalho_para,
    PASTA_LONA, PASTA_ADESIVO, PASTA_CORTE, PASTA_COMPOSTOS,
    NOME_PASTA_PRONTOS, NOME_SUBPASTA_PRONTOS,
)


def _rotulo(nome):
    config = copy.deepcopy(CONFIG_PADRAO)
    return _pasta_de_trabalho_para(nome, config["materiais"],
                                   config.get("sinonimos_categoria", {}),
                                   config.get("materiais_compostos", {}))


# ===================================== a pasta que o sistema cria

def test_producao_nova_ganha_so_a_pasta_de_prontos(tmp_path):
    garantir_estrutura_producao(tmp_path)

    assert (tmp_path / NOME_PASTA_PRONTOS).is_dir()
    assert [p.name for p in tmp_path.iterdir()] == [NOME_PASTA_PRONTOS], (
        "a pasta de produção é plana: uma pasta só, e o resto solto")


def test_garantir_estrutura_e_idempotente(tmp_path):
    garantir_estrutura_producao(tmp_path)
    (tmp_path / NOME_PASTA_PRONTOS / "ja_tinha.pdf").write_bytes(b"x")

    garantir_estrutura_producao(tmp_path)   # roda de novo, nao pode apagar nada

    assert (tmp_path / NOME_PASTA_PRONTOS / "ja_tinha.pdf").exists()


def test_arquivo_solto_fica_solto(tmp_path):
    """
    Quem decide que a peça saiu da máquina é ele, arrastando pra PRONTOS.
    Mover arte na pasta de produção por conta própria está congelado
    desde 2026-09-12 — e agora nem a distribuição por material existe.
    """
    config = copy.deepcopy(CONFIG_PADRAO)
    arte = tmp_path / "1UN LONA 2,00X1,00M_banner.pdf"
    arte.write_bytes(b"x")

    resultado = organizar_pasta_producao(tmp_path, config)

    assert arte.exists(), "o arquivo nao pode sair do lugar"
    assert resultado == {"movidos": [], "colisoes": []}
    assert sorted(p.name for p in tmp_path.iterdir()) == sorted([NOME_PASTA_PRONTOS, arte.name])


def test_nada_se_move_nem_quando_ha_pasta_antiga_de_material(tmp_path):
    """Cliente antigo tem LONAS/ADESIVOS/... ; a arte nova continua solta."""
    config = copy.deepcopy(CONFIG_PADRAO)
    (tmp_path / PASTA_LONA / NOME_SUBPASTA_PRONTOS).mkdir(parents=True)
    arte = tmp_path / "1UN LONA 2,00X1,00M_a.pdf"
    arte.write_bytes(b"x")

    organizar_pasta_producao(tmp_path, config)

    assert arte.exists()
    assert not (tmp_path / PASTA_LONA / arte.name).exists()


def test_organizar_funciona_sem_config(tmp_path):
    """Ela nao le mais o config pra nada — quem chamar sem ele nao pode quebrar."""
    assert organizar_pasta_producao(tmp_path) == {"movidos": [], "colisoes": []}
    assert (tmp_path / NOME_PASTA_PRONTOS).is_dir()


# ========================= a separação por material, que virou rótulo

def test_lona_pura_e_rotulada_como_lona():
    assert _rotulo("1UN LONA 2,00X1,00M_banner.pdf") == PASTA_LONA


def test_adesivo_puro_e_rotulado_como_adesivo():
    assert _rotulo("1UN ADESIVO 1,00X1,00M_vinil.pdf") == PASTA_ADESIVO


def test_mdf_corte_direto_sem_impressao_e_corte():
    assert _rotulo("1UN MDF 1,00X1,00M_placa.pdf") == PASTA_CORTE


def test_material_composto_adesivado_e_composto_nunca_corte():
    assert _rotulo("1UN PS ADESIVADO 1,00X1,00M_a.pdf") == PASTA_COMPOSTOS


def test_pvc_impresso_sem_ser_adesivado_tambem_e_composto():
    """
    Regra do usuário (2026-09-03): PVC/PS/MDF/ACRÍLICO com "IMPRESSO" no
    nome envolve os dois processos (imprimir + cortar), mesmo sem o
    gatilho ADESIVADO — nunca pode contar como corte puro, que é o que
    some da tela de envio. Caso real (FESTA ALEMÃ).
    """
    nome = "1UN PVC 10MM IMPRESSO RECORTE 2.25X0.45M_logo_PVC Expandido_225x45_1 Unidade.pdf"
    assert _rotulo(nome) == PASTA_COMPOSTOS


def test_ps_impresso_recorte_e_composto():
    assert _rotulo("1UN PS IMPRESSO RECORTE_apliques_PS_cerca de 45x45_8 Unidades.pdf") == PASTA_COMPOSTOS


def test_arquivo_sem_categoria_reconhecida_e_composto():
    """Pedido do usuário (2026-09-03): "o que não reconhecer joga em Compostos"."""
    assert _rotulo("orcamento_cliente.pdf") == PASTA_COMPOSTOS


# ================================================ varredura e pendências

def test_varrer_acha_a_producao_de_cada_cliente_e_so_cria_prontos(tmp_path):
    config = copy.deepcopy(CONFIG_PADRAO)
    eventos = tmp_path / "EVENTOS"
    for nome, arte in (("CLIENTE A", "1UN LONA 2,00X1,00M_a.pdf"), ("CLIENTE B", "1UN MDF 1,00X1,00M_b.pdf")):
        (eventos / nome / "PRODUCAO").mkdir(parents=True)
        (eventos / nome / "PRODUCAO" / arte).write_bytes(b"x")

    resultado = varrer_e_organizar_todas(eventos, config)

    assert set(resultado.keys()) == {"CLIENTE A", "CLIENTE B"}
    for nome, arte in (("CLIENTE A", "1UN LONA 2,00X1,00M_a.pdf"), ("CLIENTE B", "1UN MDF 1,00X1,00M_b.pdf")):
        pasta = eventos / nome / "PRODUCAO"
        assert (pasta / arte).exists(), "a arte ficou onde estava"
        assert (pasta / NOME_PASTA_PRONTOS).is_dir()


def test_varrer_raiz_eventos_inexistente_nao_estoura_erro(tmp_path):
    config = copy.deepcopy(CONFIG_PADRAO)
    assert varrer_e_organizar_todas(tmp_path / "nao_existe", config) == {}


def test_pendencia_e_o_que_esta_solto_fora_do_prontos(tmp_path):
    eventos = tmp_path / "EVENTOS"

    pasta_a = eventos / "CLIENTE A" / "PRODUCAO"
    garantir_estrutura_producao(pasta_a)
    (pasta_a / "a1.pdf").write_bytes(b"x")
    (pasta_a / "a2.pdf").write_bytes(b"x")

    # Cliente B: tudo ja em PRONTOS -> nao aparece
    pasta_b = eventos / "CLIENTE B" / "PRODUCAO"
    garantir_estrutura_producao(pasta_b)
    (pasta_b / NOME_PASTA_PRONTOS / "b1.pdf").write_bytes(b"x")

    pendencias = gerar_relatorio_pendencias(eventos)

    assert set(pendencias.keys()) == {"CLIENTE A"}
    assert pendencias["CLIENTE A"] == {"a fazer": 2}


def test_pendencia_ainda_conta_a_pasta_de_material_do_cliente_antigo(tmp_path):
    eventos = tmp_path / "EVENTOS"
    pasta = eventos / "CLIENTE VELHO" / "PRODUCAO"
    (pasta / PASTA_LONA).mkdir(parents=True)
    (pasta / PASTA_LONA / "a1.pdf").write_bytes(b"x")
    (pasta / "solta.pdf").write_bytes(b"x")

    pendencias = gerar_relatorio_pendencias(eventos)

    assert pendencias["CLIENTE VELHO"] == {"a fazer": 1, PASTA_LONA: 1}


def test_reconhece_mais_de_uma_pasta_producao_do_mesmo_cliente_dividida_por_data(tmp_path):
    """
    Caso real (FESTA ALEMÃ, 2026-09-03): quando a produção é dividida por
    data, o cliente tem "PRODUCAO", "PRODUCAO 01_09", "PRODUCAO 02_09"
    coexistindo — um match exato pelo nome ignorava as duas datadas.
    """
    config = copy.deepcopy(CONFIG_PADRAO)
    eventos = tmp_path / "EVENTOS"
    cliente = eventos / "FESTA ALEMA"
    for sub, arte in (("PRODUCAO", "1UN LONA 2,00X1,00M_a.pdf"),
                      ("PRODUCAO 01_09", "1UN MDF 1,00X1,00M_b.pdf"),
                      ("PRODUCAO 02_09", "1UN LONA 3,00X1,00M_c.pdf")):
        (cliente / sub).mkdir(parents=True)
        (cliente / sub / arte).write_bytes(b"x")

    resultado = varrer_e_organizar_todas(eventos, config)

    esperado = {"FESTA ALEMA", "FESTA ALEMA — PRODUCAO 01_09", "FESTA ALEMA — PRODUCAO 02_09"}
    assert set(resultado.keys()) == esperado
    assert (cliente / "PRODUCAO" / "1UN LONA 2,00X1,00M_a.pdf").exists()
    assert (cliente / "PRODUCAO 01_09" / NOME_PASTA_PRONTOS).is_dir()
    assert set(gerar_relatorio_pendencias(eventos).keys()) == esperado


def test_relatorio_pendencias_raiz_inexistente_nao_estoura_erro(tmp_path):
    assert gerar_relatorio_pendencias(tmp_path / "nao_existe") == {}


def test_formatar_relatorio_pendencias_vazio():
    assert "Nenhuma pend" in formatar_relatorio_pendencias({})


def test_formatar_relatorio_pendencias_com_conteudo():
    texto = formatar_relatorio_pendencias({"CLIENTE A": {"a fazer": 2, "LONA": 1}})
    assert "CLIENTE A" in texto
    assert "a fazer: 2 pendentes" in texto
    assert "LONA: 1 pendente" in texto


# ============================ quem cria a pasta, na pratica

def test_apontar_a_producao_no_cadastro_ja_cria_o_prontos(tmp_path, monkeypatch):
    """
    "Assim que for criada a pasta de produção, criar somente uma pasta de
    PRONTOS" — entao salvar o cliente com a producao apontada ja basta.
    """
    import caminhos
    import clientes
    monkeypatch.setattr(caminhos, "RECEBIMENTO_DE_ARTES", tmp_path / "Recebimento de Artes")
    producao = tmp_path / "EVENTOS" / "CLIENTE Z" / "PRODUCAO"
    producao.mkdir(parents=True)

    clientes.criar("CLIENTE Z", pasta_producao=producao, raiz=caminhos.RECEBIMENTO_DE_ARTES)

    assert [p.name for p in producao.iterdir()] == [NOME_PASTA_PRONTOS]


def test_a_passada_do_checklist_cria_o_prontos_de_pasta_feita_na_mao(tmp_path, monkeypatch):
    """Pasta criada no Explorer nao passa pelo cadastro — o vigia cobre isso."""
    import caminhos
    import clientes
    import vigia_checklist
    monkeypatch.setattr(caminhos, "RECEBIMENTO_DE_ARTES", tmp_path / "Recebimento de Artes")
    monkeypatch.setattr(caminhos, "ETIQUETAS_GERADAS", tmp_path / "saida")
    producao = tmp_path / "EVENTOS" / "CLIENTE W" / "PRODUCAO"
    producao.mkdir(parents=True)
    cliente = clientes.criar("CLIENTE W", pasta_producao=producao, raiz=caminhos.RECEBIMENTO_DE_ARTES)
    (producao / NOME_PASTA_PRONTOS).rmdir()      # como se a pasta tivesse nascido na mao

    monkeypatch.setattr(vigia_checklist.checklist_producao, "gerar", lambda *a, **k: None)
    vigia_checklist.passada_do_cliente(cliente, forcar=True)

    assert (producao / NOME_PASTA_PRONTOS).is_dir()
