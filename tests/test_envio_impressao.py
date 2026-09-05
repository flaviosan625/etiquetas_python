import datetime

import pytest

import envio_impressao as env
import rasterlink_hotfolder as rl_hf
from config import carregar_config
from envio_impressao import (
    MAQUINA_ADESIVO, MAQUINA_LONA, cabe_na_maquina, conferir, enviar, listar, prever_giro,
    raiz_do_cliente, subtotais_por_material, sugerir_maquina,
)


@pytest.fixture(autouse=True)
def _isolar_pastas_reais(tmp_path, monkeypatch):
    """
    PASTA_FILA_ONEDRIVE e PASTA_RELATORIOS apontam pro OneDrive REAL.
    Sem isolar, um teste de envio copia arquivo de mentira pra fila de
    produção e o vigia manda pra impressora de verdade — e registrar_
    envio suja o histórico permanente (aconteceu em 2026-09-05, 45
    linhas falsas tiveram que ser limpas na mão).

    autouse de propósito: teste novo não pode ter a chance de esquecer.
    """
    monkeypatch.setattr(env, "PASTA_FILA_ONEDRIVE", tmp_path / "_fila_isolada")
    monkeypatch.setattr(rl_hf, "PASTA_FILA_ONEDRIVE", tmp_path / "_fila_isolada")
    monkeypatch.setattr(rl_hf, "PASTA_RELATORIOS", tmp_path / "_relatorios_isolados")


CONFIG = carregar_config()

MAQUINAS_TESTE = {
    MAQUINA_LONA: {"hot_folder": r"C:\nao_usado", "largura_util_m": 3.20},
    MAQUINA_ADESIVO: {"hot_folder": r"C:\nao_usado", "largura_util_m": 1.48},
}


def _producao(tmp_path, nome_cliente="FESTA ALEMA", nome_producao="PRODUCAO 03_09"):
    pasta = tmp_path / "EVENTOS" / nome_cliente / nome_producao
    for sub in ("LONAS", "ADESIVOS", "CORTES", "COMPOSTOS"):
        (pasta / sub / "Prontos").mkdir(parents=True)
    return pasta


def _arte(pasta, nome, conteudo=b"arte"):
    caminho = pasta / nome
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_bytes(conteudo)
    return caminho


# ---------------------------------------------------------------- máquina

@pytest.mark.parametrize("nome, esperado", [
    ("AF_Colunas Arena Principal_220x5500+sangria_lona_2 Unidades.tif", MAQUINA_LONA),
    ("8UN LONA IMPRESSA ACABAMENTO BANNER_Banner 50x250_.tif", MAQUINA_LONA),
    ("2UN VINIL IMPRESSO FOSCO 0.70X1.80M_totem_Adesivo.jpg", MAQUINA_ADESIVO),
    ("30UN VINIL IMPRESSO RECORTE CONTORNO_LOGO_16x7.1cm.pdf", MAQUINA_ADESIVO),
    ("1UN PVC 10MM RECORTE_Castelo_PVC Adesivado_Lado Esquerdo.pdf", MAQUINA_ADESIVO),
])
def test_maquina_vem_do_material_no_nome(nome, esperado):
    assert sugerir_maquina(nome, CONFIG) == esperado


def test_lona_vai_pra_swj_mesmo_sendo_pequena():
    """Regra do usuário (2026-09-05): lona sempre na SWJ, qualquer tamanho — sobra de bobina é normal."""
    assert sugerir_maquina("1UN LONA IMPRESSA_faixa_0,30x0,40M.pdf", CONFIG) == MAQUINA_LONA


def test_adesivo_largo_continua_na_ujv_porque_na_swj_nao_entra_adesivo():
    nome = "1UN VINIL IMPRESSO_painel_2,50x3,00M.pdf"
    assert sugerir_maquina(nome, CONFIG) == MAQUINA_ADESIVO


def test_adesivado_ganha_da_categoria_do_substrato():
    """'PVC ADESIVADO' tem categoria PVC, mas quem manda é a palavra adesivado."""
    assert sugerir_maquina("5UN PVC 10MM RECORTE_Aplique Adesivado_100 CM.pdf", CONFIG) == MAQUINA_ADESIVO


def test_sem_lona_nem_adesivo_vai_pra_ujv_ate_a_docan_entrar():
    assert sugerir_maquina("2UN PS IMPRESSO REFILE 1.50X0.33M_Brasao.pdf", CONFIG) == MAQUINA_ADESIVO


# ---------------------------------------------------------------- giro

def test_giro_por_economia_de_bobina():
    dimensao = {"largura_m": 0.50, "altura_m": 2.50, "area_m2": 1.25}
    giro = prever_giro(dimensao, MAQUINA_LONA, MAQUINAS_TESTE)
    assert giro["motivo"] == "economia"
    assert giro["economia_m"] == pytest.approx(2.00)


def test_giro_porque_nao_cabe_em_pe():
    dimensao = {"largura_m": 6.00, "altura_m": 3.00, "area_m2": 18.0}
    giro = prever_giro(dimensao, MAQUINA_LONA, MAQUINAS_TESTE)
    assert giro["motivo"] == "nao_cabe"


def test_nao_gira_quando_ja_esta_do_jeito_mais_economico():
    dimensao = {"largura_m": 3.00, "altura_m": 1.00, "area_m2": 3.0}
    assert prever_giro(dimensao, MAQUINA_LONA, MAQUINAS_TESTE) is None


def test_nao_gira_quando_deitado_nao_caberia():
    """0,70x1,80 na UJV: em pé cabe, deitado (1,80) não — girar seria pior que inútil."""
    dimensao = {"largura_m": 0.70, "altura_m": 1.80, "area_m2": 1.26}
    assert prever_giro(dimensao, MAQUINA_ADESIVO, MAQUINAS_TESTE) is None


def test_arte_na_largura_exata_da_bobina_nao_e_recusada_por_arredondamento():
    """3,20m vira 3.2000000038m depois da conversão de pontos — a folga de 1mm existe por isso."""
    dimensao = {"largura_m": 1.00, "altura_m": 3.2000000038, "area_m2": 3.2}
    assert prever_giro(dimensao, MAQUINA_LONA, MAQUINAS_TESTE)["motivo"] == "economia"


def test_sem_medida_no_nome_nao_ha_previsao_de_giro():
    assert prever_giro(None, MAQUINA_LONA, MAQUINAS_TESTE) is None


def test_nao_cabe_nem_girado_e_sinalizado_mas_nao_impede():
    dimensao = {"largura_m": 2.50, "altura_m": 3.00, "area_m2": 7.5}
    assert cabe_na_maquina(dimensao, MAQUINA_ADESIVO, MAQUINAS_TESTE) is False
    assert cabe_na_maquina(dimensao, MAQUINA_LONA, MAQUINAS_TESTE) is True


# ---------------------------------------------------------------- listagem

def test_listar_pega_arquivos_das_pastas_de_trabalho(tmp_path):
    pasta = _producao(tmp_path)
    _arte(pasta / "LONAS", "1UN LONA IMPRESSA_faixa_1,00x2,00M.pdf")
    _arte(pasta / "ADESIVOS", "2UN VINIL IMPRESSO_totem_0,70x1,80M.pdf")

    itens = listar(pasta, CONFIG, maquinas=MAQUINAS_TESTE)

    assert sorted(i["arquivo"] for i in itens) == [
        "1UN LONA IMPRESSA_faixa_1,00x2,00M.pdf",
        "2UN VINIL IMPRESSO_totem_0,70x1,80M.pdf",
    ]


def test_listar_nunca_entra_em_prontos(tmp_path):
    """Prontos é a confirmação manual do usuário — o sistema não lê nem escreve lá."""
    pasta = _producao(tmp_path)
    _arte(pasta / "LONAS" / "Prontos", "1UN LONA IMPRESSA_acabada_1,00x2,00M.pdf")

    assert listar(pasta, CONFIG, maquinas=MAQUINAS_TESTE) == []


def test_listar_nunca_entra_em_cortes(tmp_path):
    pasta = _producao(tmp_path)
    _arte(pasta / "CORTES", "4UN ACRILICO 4MM CRISTAL RECORTE_placa_1,62x0,42M.pdf")

    assert listar(pasta, CONFIG, maquinas=MAQUINAS_TESTE) == []


def test_listar_desce_em_subpasta_solta_criada_na_mao(tmp_path):
    """A FESTA ALEMÃ real tem 'enchanted_land' e 'PS impres_dupla face recorte' soltas na produção."""
    pasta = _producao(tmp_path)
    _arte(pasta / "LONAS" / "refazer 04_09", "1UN LONA IMPRESSA_refeita_1,00x2,00M.pdf")

    itens = listar(pasta, CONFIG, maquinas=MAQUINAS_TESTE)

    assert [i["arquivo"] for i in itens] == ["1UN LONA IMPRESSA_refeita_1,00x2,00M.pdf"]


def test_listar_ignora_arquivo_que_nao_e_arte(tmp_path):
    pasta = _producao(tmp_path)
    _arte(pasta / "LONAS", "readme.txt")
    _arte(pasta / "LONAS", "enchanted_land.zip")

    assert listar(pasta, CONFIG, maquinas=MAQUINAS_TESTE) == []


def test_listar_calcula_area_total_pela_quantidade(tmp_path):
    pasta = _producao(tmp_path)
    _arte(pasta / "LONAS", "8UN LONA IMPRESSA ACABAMENTO BANNER_Banner 50x250_.pdf")

    item = listar(pasta, CONFIG, maquinas=MAQUINAS_TESTE)[0]

    assert item["quantidade"] == 8
    assert item["area_total_m2"] == pytest.approx(10.00)
    assert item["giro"]["motivo"] == "economia"


def test_listar_marca_o_que_ja_foi_enviado_mas_nao_esconde(tmp_path):
    """Reimpressão é caso real: a tela avisa e deixa o usuário decidir, nunca some com a linha."""
    pasta = _producao(tmp_path)
    _arte(pasta / "LONAS", "1UN LONA IMPRESSA_faixa_1,00x2,00M.pdf")
    anteriores = [{
        "arquivo": "1UN LONA IMPRESSA_faixa_1,00x2,00M.pdf",
        "quando": "2026-09-04T09:12:00", "maquina": MAQUINA_LONA,
    }]

    itens = listar(pasta, CONFIG, envios_anteriores=anteriores, maquinas=MAQUINAS_TESTE)

    assert len(itens) == 1
    assert len(itens[0]["envios_anteriores"]) == 1


def test_subtotal_nunca_soma_materiais_diferentes(tmp_path):
    pasta = _producao(tmp_path)
    _arte(pasta / "LONAS", "1UN LONA IMPRESSA_faixa_1,00x2,00M.pdf")
    _arte(pasta / "ADESIVOS", "2UN VINIL IMPRESSO_totem_0,70x1,80M.pdf")

    totais = subtotais_por_material(listar(pasta, CONFIG, maquinas=MAQUINAS_TESTE))

    assert totais == {"LONA": 2.00, "ADESIVO": 2.52}


def test_subtotal_soma_o_valor_ja_arredondado_de_cada_linha():
    """Quem confere o documento soma a coluna que está vendo — o subtotal tem que fechar com ela."""
    itens = [
        {"categoria": "LONA", "area_total_m2": 26.80},
        {"categoria": "LONA", "area_total_m2": 26.80},
    ]
    assert subtotais_por_material(itens) == {"LONA": 53.60}


# ---------------------------------------------------------------- raiz do cliente

def test_raiz_do_cliente_a_partir_da_pasta_de_producao(tmp_path):
    pasta = _producao(tmp_path)
    assert raiz_do_cliente(pasta).name == "FESTA ALEMA"


def test_raiz_do_cliente_a_partir_de_uma_subpasta_de_trabalho(tmp_path):
    pasta = _producao(tmp_path)
    assert raiz_do_cliente(pasta / "LONAS").name == "FESTA ALEMA"


def test_raiz_do_cliente_fora_do_padrao_usa_a_propria_pasta(tmp_path):
    solta = tmp_path / "uma pasta qualquer"
    solta.mkdir()
    assert raiz_do_cliente(solta) == solta.resolve()


# ---------------------------------------------------------------- conferência

def _itens_de(pasta, maquinas=MAQUINAS_TESTE, anteriores=None):
    return listar(pasta, CONFIG, envios_anteriores=anteriores, maquinas=maquinas)


def test_conferencia_aprova_arquivo_limpo(tmp_path):
    pasta = _producao(tmp_path)
    _arte(pasta / "LONAS", "1UN LONA IMPRESSA_faixa_1,00x2,00M.pdf")

    resultado = conferir(_itens_de(pasta), pasta_fila=tmp_path / "fila", maquinas=MAQUINAS_TESTE)

    assert len(resultado["limpos"]) == 1
    assert resultado["bloqueados"] == []
    assert resultado["atencao"] == []


def test_conferencia_trava_arquivo_de_zero_byte(tmp_path):
    pasta = _producao(tmp_path)
    _arte(pasta / "LONAS", "1UN LONA IMPRESSA_faixa_1,00x2,00M.pdf", conteudo=b"")

    resultado = conferir(_itens_de(pasta), pasta_fila=tmp_path / "fila", maquinas=MAQUINAS_TESTE)

    assert len(resultado["bloqueados"]) == 1
    assert "0 byte" in resultado["bloqueados"][0][1]


def test_conferencia_trava_nome_que_ja_esta_na_fila_da_maquina(tmp_path):
    """O vigia pode estar lendo esse arquivo agora — sobrescrever manda peça pela metade."""
    pasta = _producao(tmp_path)
    nome = "1UN LONA IMPRESSA_faixa_1,00x2,00M.pdf"
    _arte(pasta / "LONAS", nome)
    fila = tmp_path / "fila"
    (fila / MAQUINA_LONA).mkdir(parents=True)
    (fila / MAQUINA_LONA / nome).write_bytes(b"ja esperando o RIP")

    resultado = conferir(_itens_de(pasta), pasta_fila=fila, maquinas=MAQUINAS_TESTE)

    assert len(resultado["bloqueados"]) == 1
    assert "na fila" in resultado["bloqueados"][0][1]


def test_conferencia_trava_dois_marcados_com_o_mesmo_nome(tmp_path):
    """Vindo de pastas de trabalho diferentes, mas indo pra mesma fila: um comeria o outro."""
    pasta = _producao(tmp_path)
    nome = "1UN LONA IMPRESSA_faixa_1,00x2,00M.pdf"
    _arte(pasta / "LONAS", nome)
    _arte(pasta / "COMPOSTOS", nome)

    resultado = conferir(_itens_de(pasta), pasta_fila=tmp_path / "fila", maquinas=MAQUINAS_TESTE)

    assert len(resultado["bloqueados"]) == 2
    assert all("mesmo nome" in motivo for _, motivo in resultado["bloqueados"])


def test_mesmo_nome_em_maquinas_diferentes_nao_e_conflito(tmp_path):
    """Caem em pastas diferentes da fila — não se atropelam."""
    pasta = _producao(tmp_path)
    _arte(pasta / "LONAS", "1UN LONA IMPRESSA_x_1,00x2,00M.pdf")
    _arte(pasta / "ADESIVOS", "1UN VINIL IMPRESSO_x_1,00x2,00M.pdf")

    resultado = conferir(_itens_de(pasta), pasta_fila=tmp_path / "fila", maquinas=MAQUINAS_TESTE)

    assert resultado["bloqueados"] == []
    assert len(resultado["limpos"]) == 2


def test_conferencia_avisa_reimpressao_sem_bloquear(tmp_path):
    pasta = _producao(tmp_path)
    nome = "1UN LONA IMPRESSA_faixa_1,00x2,00M.pdf"
    _arte(pasta / "LONAS", nome)
    anteriores = [{"arquivo": nome, "quando": "2026-09-04T09:12:00", "maquina": MAQUINA_LONA}]

    resultado = conferir(
        _itens_de(pasta, anteriores=anteriores), pasta_fila=tmp_path / "fila", maquinas=MAQUINAS_TESTE,
    )

    assert resultado["bloqueados"] == []
    assert len(resultado["atencao"]) == 1
    assert "04/09 09:12" in resultado["atencao"][0][1][0]


def test_conferencia_avisa_que_nao_cabe_nem_girado_sem_bloquear(tmp_path):
    """Escolha do usuário: prefere decidir dentro do RasterLink a ter arquivo represado sem ver."""
    pasta = _producao(tmp_path)
    _arte(pasta / "ADESIVOS", "1UN VINIL IMPRESSO_painel_2,50x3,00M.pdf")

    resultado = conferir(_itens_de(pasta), pasta_fila=tmp_path / "fila", maquinas=MAQUINAS_TESTE)

    assert resultado["bloqueados"] == []
    assert "não cabe nem girado" in resultado["atencao"][0][1][0]


def test_conferencia_trava_arquivo_que_sumiu_entre_a_lista_e_o_envio(tmp_path):
    pasta = _producao(tmp_path)
    caminho = _arte(pasta / "LONAS", "1UN LONA IMPRESSA_faixa_1,00x2,00M.pdf")
    itens = _itens_de(pasta)
    caminho.unlink()

    resultado = conferir(itens, pasta_fila=tmp_path / "fila", maquinas=MAQUINAS_TESTE)

    assert len(resultado["bloqueados"]) == 1
    assert "não está mais" in resultado["bloqueados"][0][1]


# ---------------------------------------------------------------- envio

def test_enviar_copia_pra_fila_sem_mexer_no_original(tmp_path):
    """A regra mais importante do usuário: o arquivo original não pode sumir."""
    pasta = _producao(tmp_path)
    nome = "1UN LONA IMPRESSA_faixa_1,00x2,00M.pdf"
    origem = _arte(pasta / "LONAS", nome, conteudo=b"a arte inteira")
    fila = tmp_path / "fila"

    resultado = enviar(_itens_de(pasta), pasta, pasta_fila=fila, maquinas=MAQUINAS_TESTE)

    assert origem.exists()
    assert origem.read_bytes() == b"a arte inteira"
    assert (fila / MAQUINA_LONA / nome).read_bytes() == b"a arte inteira"
    assert len(resultado["enviados"]) == 1
    assert resultado["falhas"] == []


def test_envio_registra_o_que_so_existe_no_momento_do_envio(tmp_path):
    pasta = _producao(tmp_path)
    _arte(pasta / "LONAS", "8UN LONA IMPRESSA ACABAMENTO BANNER_Banner 50x250_.pdf")
    agora = datetime.datetime(2026, 9, 5, 14, 22, 3)

    registro = enviar(
        _itens_de(pasta), pasta, pasta_fila=tmp_path / "fila", maquinas=MAQUINAS_TESTE, agora=agora,
    )["enviados"][0]

    assert registro["quando"] == "2026-09-05T14:22:03"
    assert registro["maquina"] == MAQUINA_LONA
    assert registro["producao"] == "PRODUCAO 03_09"
    assert registro["categoria"] == "LONA"
    assert registro["quantidade"] == 8
    assert registro["area_total_m2"] == pytest.approx(10.00)
    assert registro["girou_previsto"] is True


def test_copia_incompleta_e_desfeita_e_nao_vira_registro(tmp_path, monkeypatch):
    """
    Nunca pode existir linha no documento de um arquivo que não chegou
    inteiro na fila — e a cópia meia-boca não pode ficar lá esperando o
    RIP puxar.
    """
    pasta = _producao(tmp_path)
    nome = "1UN LONA IMPRESSA_faixa_1,00x2,00M.pdf"
    _arte(pasta / "LONAS", nome, conteudo=b"conteudo completo")
    fila = tmp_path / "fila"

    def copia_truncada(caminho, maquina, pasta_fila=None, maquinas=None):
        destino = pathlib_destino = (fila / maquina / nome)
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(b"pela")
        return pathlib_destino

    monkeypatch.setattr(env, "enviar_para_fila", copia_truncada)

    resultado = enviar(_itens_de(pasta), pasta, pasta_fila=fila, maquinas=MAQUINAS_TESTE)

    assert resultado["enviados"] == []
    assert len(resultado["falhas"]) == 1
    assert "incompleta" in resultado["falhas"][0][1]
    assert not (fila / MAQUINA_LONA / nome).exists()


def test_falha_num_arquivo_nao_derruba_o_resto_do_lote(tmp_path, monkeypatch):
    pasta = _producao(tmp_path)
    _arte(pasta / "LONAS", "1UN LONA IMPRESSA_boa_1,00x2,00M.pdf")
    _arte(pasta / "LONAS", "1UN LONA IMPRESSA_ruim_1,00x2,00M.pdf")

    original = env.enviar_para_fila

    def falha_na_ruim(caminho, maquina, pasta_fila=None, maquinas=None):
        if "ruim" in str(caminho):
            raise OSError("disco cheio")
        return original(caminho, maquina, pasta_fila=pasta_fila, maquinas=maquinas)

    monkeypatch.setattr(env, "enviar_para_fila", falha_na_ruim)

    resultado = enviar(_itens_de(pasta), pasta, pasta_fila=tmp_path / "fila", maquinas=MAQUINAS_TESTE)

    assert len(resultado["enviados"]) == 1
    assert len(resultado["falhas"]) == 1
    assert "disco cheio" in resultado["falhas"][0][1]
