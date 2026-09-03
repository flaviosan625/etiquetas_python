import copy
import pathlib

from config import CONFIG_PADRAO
from producao import (
    garantir_estrutura_producao, organizar_pasta_producao, varrer_e_organizar_todas,
    gerar_relatorio_pendencias, formatar_relatorio_pendencias,
    PASTA_LONA, PASTA_ADESIVO, PASTA_CORTE, PASTA_COMPOSTOS, NOME_SUBPASTA_PRONTOS,
)


def test_garantir_estrutura_cria_as_4_pastas_com_prontos(tmp_path):
    garantir_estrutura_producao(tmp_path)

    for nome in (PASTA_LONA, PASTA_ADESIVO, PASTA_CORTE, PASTA_COMPOSTOS):
        assert (tmp_path / nome).is_dir()
        assert (tmp_path / nome / NOME_SUBPASTA_PRONTOS).is_dir()


def test_garantir_estrutura_e_idempotente(tmp_path):
    garantir_estrutura_producao(tmp_path)
    (tmp_path / PASTA_LONA / "ja_tinha.pdf").write_bytes(b"x")

    garantir_estrutura_producao(tmp_path)  # roda de novo, nao pode apagar nada

    assert (tmp_path / PASTA_LONA / "ja_tinha.pdf").exists()


def test_lona_pura_vai_pra_lona(tmp_path):
    config = copy.deepcopy(CONFIG_PADRAO)
    (tmp_path / "1UN LONA 2,00X1,00M_banner.pdf").write_bytes(b"x")

    resultado = organizar_pasta_producao(tmp_path, config)

    assert (tmp_path / PASTA_LONA / "1UN LONA 2,00X1,00M_banner.pdf").exists()
    assert resultado["movidos"] == [("1UN LONA 2,00X1,00M_banner.pdf", PASTA_LONA)]


def test_adesivo_puro_vai_pra_adesivo(tmp_path):
    config = copy.deepcopy(CONFIG_PADRAO)
    (tmp_path / "1UN ADESIVO 1,00X1,00M_vinil.pdf").write_bytes(b"x")

    resultado = organizar_pasta_producao(tmp_path, config)

    assert (tmp_path / PASTA_ADESIVO / "1UN ADESIVO 1,00X1,00M_vinil.pdf").exists()
    assert resultado["movidos"] == [("1UN ADESIVO 1,00X1,00M_vinil.pdf", PASTA_ADESIVO)]


def test_mdf_corte_direto_sem_impressao_vai_pra_corte(tmp_path):
    config = copy.deepcopy(CONFIG_PADRAO)
    (tmp_path / "1UN MDF 1,00X1,00M_placa.pdf").write_bytes(b"x")

    resultado = organizar_pasta_producao(tmp_path, config)

    assert (tmp_path / PASTA_CORTE / "1UN MDF 1,00X1,00M_placa.pdf").exists()
    assert resultado["movidos"] == [("1UN MDF 1,00X1,00M_placa.pdf", PASTA_CORTE)]


def test_material_composto_adesivado_vai_pra_compostos_nao_pra_corte(tmp_path):
    config = copy.deepcopy(CONFIG_PADRAO)
    (tmp_path / "1UN PS ADESIVADO 1,00X1,00M_a.pdf").write_bytes(b"x")

    resultado = organizar_pasta_producao(tmp_path, config)

    assert (tmp_path / PASTA_COMPOSTOS / "1UN PS ADESIVADO 1,00X1,00M_a.pdf").exists()
    assert not (tmp_path / PASTA_CORTE / "1UN PS ADESIVADO 1,00X1,00M_a.pdf").exists()


def test_pvc_impresso_sem_ser_adesivado_tambem_vai_pra_compostos(tmp_path):
    """
    Regra do usuário (2026-09-03): PVC/PS/MDF/ACRÍLICO com "IMPRESSO"
    no nome envolve os dois processos (imprimir + cortar), mesmo sem
    ser tecnicamente um "material composto" via gatilho ADESIVADO —
    nunca pode ir pra CORTE, que é só pra corte puro, sem impressão.
    Caso real (FESTA ALEMÃ): "PVC 10MM IMPRESSO RECORTE ... PVC
    Expandido ...pdf" não tinha ADESIVADO, mas tinha IMPRESSO.
    """
    config = copy.deepcopy(CONFIG_PADRAO)
    nome = "1UN PVC 10MM IMPRESSO RECORTE 2.25X0.45M_logo_PVC Expandido_225x45_1 Unidade.pdf"
    (tmp_path / nome).write_bytes(b"x")

    resultado = organizar_pasta_producao(tmp_path, config)

    assert (tmp_path / PASTA_COMPOSTOS / nome).exists()
    assert not (tmp_path / PASTA_CORTE / nome).exists()


def test_ps_impresso_recorte_vai_pra_compostos(tmp_path):
    config = copy.deepcopy(CONFIG_PADRAO)
    nome = "1UN PS IMPRESSO RECORTE_apliques_PS_cerca de 45x45_8 Unidades.pdf"
    (tmp_path / nome).write_bytes(b"x")

    resultado = organizar_pasta_producao(tmp_path, config)

    assert (tmp_path / PASTA_COMPOSTOS / nome).exists()


def test_arquivo_sem_categoria_reconhecida_vai_pra_compostos(tmp_path):
    """
    Pedido do usuário (2026-09-03): "o que não reconhecer joga em
    Compostos" — nunca mais fica solto sem classificar.
    """
    config = copy.deepcopy(CONFIG_PADRAO)
    (tmp_path / "orcamento_cliente.pdf").write_bytes(b"x")

    resultado = organizar_pasta_producao(tmp_path, config)

    assert (tmp_path / PASTA_COMPOSTOS / "orcamento_cliente.pdf").exists()
    assert not (tmp_path / "orcamento_cliente.pdf").exists()
    assert resultado["movidos"] == [("orcamento_cliente.pdf", PASTA_COMPOSTOS)]


def test_nunca_mexe_em_arquivo_que_ja_esta_dentro_de_subpasta(tmp_path):
    config = copy.deepcopy(CONFIG_PADRAO)
    garantir_estrutura_producao(tmp_path)
    ja_organizado = tmp_path / PASTA_LONA / "1UN LONA 2,00X1,00M_ja_ai.pdf"
    ja_organizado.write_bytes(b"conteudo original")

    organizar_pasta_producao(tmp_path, config)

    assert ja_organizado.read_bytes() == b"conteudo original"


def test_colisao_de_nome_no_destino_nao_sobrescreve(tmp_path):
    config = copy.deepcopy(CONFIG_PADRAO)
    garantir_estrutura_producao(tmp_path)
    (tmp_path / PASTA_LONA / "1UN LONA 2,00X1,00M_a.pdf").write_bytes(b"ja existia")
    solto = tmp_path / "1UN LONA 2,00X1,00M_a.pdf"
    solto.write_bytes(b"arquivo novo")

    resultado = organizar_pasta_producao(tmp_path, config)

    assert resultado["colisoes"] == ["1UN LONA 2,00X1,00M_a.pdf"]
    assert solto.exists(), "colisao nao move — fica solto pra conferir na mao"
    assert (tmp_path / PASTA_LONA / "1UN LONA 2,00X1,00M_a.pdf").read_bytes() == b"ja existia"


def test_varrer_e_organizar_todas_acha_producao_de_cada_cliente(tmp_path):
    config = copy.deepcopy(CONFIG_PADRAO)
    eventos = tmp_path / "EVENTOS"
    (eventos / "CLIENTE A" / "PRODUCAO").mkdir(parents=True)
    (eventos / "CLIENTE A" / "PRODUCAO" / "1UN LONA 2,00X1,00M_a.pdf").write_bytes(b"x")
    (eventos / "CLIENTE B" / "PRODUCAO").mkdir(parents=True)
    (eventos / "CLIENTE B" / "PRODUCAO" / "1UN MDF 1,00X1,00M_b.pdf").write_bytes(b"x")

    resultado = varrer_e_organizar_todas(eventos, config)

    assert set(resultado.keys()) == {"CLIENTE A", "CLIENTE B"}
    assert (eventos / "CLIENTE A" / "PRODUCAO" / PASTA_LONA / "1UN LONA 2,00X1,00M_a.pdf").exists()
    assert (eventos / "CLIENTE B" / "PRODUCAO" / PASTA_CORTE / "1UN MDF 1,00X1,00M_b.pdf").exists()


def test_varrer_raiz_eventos_inexistente_nao_estoura_erro(tmp_path):
    config = copy.deepcopy(CONFIG_PADRAO)
    resultado = varrer_e_organizar_todas(tmp_path / "nao_existe", config)
    assert resultado == {}


def test_relatorio_pendencias_so_lista_quem_tem_arquivo_fora_do_prontos(tmp_path):
    eventos = tmp_path / "EVENTOS"

    # Cliente A: 2 pendentes em LONA, 1 em CORTE, nada em COMPOSTOS/ADESIVO
    pasta_a = eventos / "CLIENTE A" / "PRODUCAO"
    garantir_estrutura_producao(pasta_a)
    (pasta_a / PASTA_LONA / "a1.pdf").write_bytes(b"x")
    (pasta_a / PASTA_LONA / "a2.pdf").write_bytes(b"x")
    (pasta_a / PASTA_CORTE / "a3.pdf").write_bytes(b"x")

    # Cliente B: tudo ja em Prontos -> nao deve aparecer no relatorio
    pasta_b = eventos / "CLIENTE B" / "PRODUCAO"
    garantir_estrutura_producao(pasta_b)
    (pasta_b / PASTA_LONA / NOME_SUBPASTA_PRONTOS / "b1.pdf").write_bytes(b"x")

    pendencias = gerar_relatorio_pendencias(eventos)

    assert set(pendencias.keys()) == {"CLIENTE A"}
    assert pendencias["CLIENTE A"] == {PASTA_LONA: 2, PASTA_CORTE: 1}


def test_reconhece_mais_de_uma_pasta_producao_do_mesmo_cliente_dividida_por_data(tmp_path):
    """
    Caso real (FESTA ALEMÃ, 2026-09-03): quando a produção é dividida
    por data, o cliente tem "PRODUCAO", "PRODUCAO 01_09", "PRODUCAO
    02_09" coexistindo — um match exato pelo nome "PRODUCAO" ignorava
    silenciosamente as duas datadas.
    """
    config = copy.deepcopy(CONFIG_PADRAO)
    eventos = tmp_path / "EVENTOS"
    cliente = eventos / "FESTA ALEMA"
    (cliente / "PRODUCAO").mkdir(parents=True)
    (cliente / "PRODUCAO" / "1UN LONA 2,00X1,00M_a.pdf").write_bytes(b"x")
    (cliente / "PRODUCAO 01_09").mkdir(parents=True)
    (cliente / "PRODUCAO 01_09" / "1UN MDF 1,00X1,00M_b.pdf").write_bytes(b"x")
    (cliente / "PRODUCAO 02_09").mkdir(parents=True)
    (cliente / "PRODUCAO 02_09" / "1UN LONA 3,00X1,00M_c.pdf").write_bytes(b"x")

    resultado = varrer_e_organizar_todas(eventos, config)

    assert set(resultado.keys()) == {
        "FESTA ALEMA", "FESTA ALEMA — PRODUCAO 01_09", "FESTA ALEMA — PRODUCAO 02_09",
    }
    assert (cliente / "PRODUCAO" / PASTA_LONA / "1UN LONA 2,00X1,00M_a.pdf").exists()
    assert (cliente / "PRODUCAO 01_09" / PASTA_CORTE / "1UN MDF 1,00X1,00M_b.pdf").exists()
    assert (cliente / "PRODUCAO 02_09" / PASTA_LONA / "1UN LONA 3,00X1,00M_c.pdf").exists()

    pendencias = gerar_relatorio_pendencias(eventos)
    assert set(pendencias.keys()) == {
        "FESTA ALEMA", "FESTA ALEMA — PRODUCAO 01_09", "FESTA ALEMA — PRODUCAO 02_09",
    }


def test_relatorio_pendencias_raiz_inexistente_nao_estoura_erro(tmp_path):
    assert gerar_relatorio_pendencias(tmp_path / "nao_existe") == {}


def test_formatar_relatorio_pendencias_vazio():
    assert "Nenhuma pend" in formatar_relatorio_pendencias({})


def test_formatar_relatorio_pendencias_com_conteudo():
    texto = formatar_relatorio_pendencias({"CLIENTE A": {"LONA": 2, "CORTE": 1}})
    assert "CLIENTE A" in texto
    assert "LONA: 2 pendentes" in texto
    assert "CORTE: 1 pendente" in texto
