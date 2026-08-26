import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from arquivamento import enviar_os, listar_pedidos


def _criar_pedido_fake(pasta_base, nome_pedido, nome_cliente="CLIENTE"):
    pasta = pasta_base / nome_pedido
    pasta.mkdir(parents=True)
    (pasta / f"OS - {nome_cliente}.pdf").write_text("pdf")
    (pasta / f"OS - {nome_cliente}.json").write_text("{}")
    (pasta / f"OS - {nome_cliente} - novos 26-08_100000.json").write_text("{}")
    (pasta / f"Checklist {nome_cliente} - LONA.pdf").write_text("checklist")
    (pasta / "estado_pedido.json").write_text("{}")
    return pasta


def test_listar_pedidos_encontra_so_o_pdf_da_os(tmp_path):
    """
    Só o PDF da OS vai pra pasta de fora — os JSON que acompanham (usados
    só internamente pelo controle de estoque) não são enviados (decisão
    do usuário, 2026-08-26): quem abre a pasta de fora quer ver a OS, não
    um arquivo de máquina/log.
    """
    origem = tmp_path / "etiquetas_geradas"
    _criar_pedido_fake(origem, "CLIENTE_20260826_100000")

    pedidos = listar_pedidos(origem, tmp_path / "destino")

    assert len(pedidos) == 1
    nomes = {a.name for a in pedidos[0]["arquivos"]}
    assert nomes == {"OS - CLIENTE.pdf"}
    assert pedidos[0]["ja_enviado"] is False
    assert pedidos[0]["cliente"] == "CLIENTE"
    assert pedidos[0]["subpasta"] == "26-08-2026 10-00-00"


def test_pasta_sem_os_nao_aparece_na_lista(tmp_path):
    origem = tmp_path / "etiquetas_geradas"
    pasta = origem / "SEM_OS_20260826_100000"
    pasta.mkdir(parents=True)
    (pasta / "Checklist CLIENTE - LONA.pdf").write_text("checklist")

    assert listar_pedidos(origem, tmp_path / "destino") == []


def test_enviar_os_copia_sem_apagar_original(tmp_path):
    origem = tmp_path / "etiquetas_geradas"
    destino = tmp_path / "destino"
    pasta = _criar_pedido_fake(origem, "CLIENTE_20260826_100000")

    pedidos = listar_pedidos(origem, destino)
    resumo = enviar_os(pedidos, destino)

    assert resumo[0]["erros"] == []
    assert len(resumo[0]["copiados"]) == 1
    assert len(list(pasta.iterdir())) == 5, "nada deveria ser apagado do original"

    pasta_no_destino = destino / "CLIENTE" / "26-08-2026 10-00-00"
    assert not (pasta_no_destino / "Checklist CLIENTE - LONA.pdf").exists(), "checklist não deveria ser copiado"
    assert not (pasta_no_destino / "OS - CLIENTE.json").exists(), "JSON não deveria ser copiado, só o PDF"
    assert (pasta_no_destino / "OS - CLIENTE.pdf").exists()


def test_ja_enviado_fica_true_depois_do_envio(tmp_path):
    origem = tmp_path / "etiquetas_geradas"
    destino = tmp_path / "destino"
    _criar_pedido_fake(origem, "CLIENTE_20260826_100000")

    pedidos = listar_pedidos(origem, destino)
    enviar_os(pedidos, destino)

    pedidos_depois = listar_pedidos(origem, destino)
    assert pedidos_depois[0]["ja_enviado"] is True


def test_dois_pedidos_do_mesmo_dia_nao_colidem_na_subpasta(tmp_path):
    """Dois pedidos do mesmo cliente no mesmo dia, minutos/segundos diferentes — precisa gerar subpastas diferentes."""
    origem = tmp_path / "etiquetas_geradas"
    destino = tmp_path / "destino"
    _criar_pedido_fake(origem, "CLIENTE_20260826_100000", nome_cliente="CLIENTE")
    _criar_pedido_fake(origem, "CLIENTE_20260826_153045", nome_cliente="CLIENTE")

    pedidos = listar_pedidos(origem, destino)
    subpastas = {p["subpasta"] for p in pedidos}
    assert subpastas == {"26-08-2026 10-00-00", "26-08-2026 15-30-45"}

    resumo = enviar_os(pedidos, destino)
    assert all(r["erros"] == [] for r in resumo)

    pasta_cliente = destino / "CLIENTE"
    assert (pasta_cliente / "26-08-2026 10-00-00" / "OS - CLIENTE.pdf").exists()
    assert (pasta_cliente / "26-08-2026 15-30-45" / "OS - CLIENTE.pdf").exists()


def test_dois_pedidos_do_mesmo_cliente_ficam_agrupados_sem_se_sobrescrever(tmp_path):
    """
    Cenário real: material chega aos poucos, o mesmo cliente gera mais
    de uma pasta de pedido ao longo do tempo. As duas devem terminar
    dentro da MESMA pasta de cliente no destino, cada uma na própria
    subpasta — nunca uma sobrescrevendo a outra.
    """
    origem = tmp_path / "etiquetas_geradas"
    destino = tmp_path / "destino"
    _criar_pedido_fake(origem, "SUPERBET_20260824_093132", nome_cliente="SUPERBET")
    _criar_pedido_fake(origem, "SUPERBET_20260825_151149", nome_cliente="SUPERBET")

    pedidos = listar_pedidos(origem, destino)
    assert {p["cliente"] for p in pedidos} == {"SUPERBET"}

    resumo = enviar_os(pedidos, destino)
    assert all(r["erros"] == [] for r in resumo)

    pasta_cliente = destino / "SUPERBET"
    assert (pasta_cliente / "24-08-2026 09-31-32" / "OS - SUPERBET.pdf").exists()
    assert (pasta_cliente / "25-08-2026 15-11-49" / "OS - SUPERBET.pdf").exists()


def test_dois_pedidos_novos_no_mesmo_lote_com_espaco_diferente_nao_fragmentam(tmp_path):
    """
    Caso mais sutil que o de cima: os DOIS pedidos são novos (nenhum
    dos dois já foi enviado antes), digitados com espaço diferente, e
    aparecem JUNTOS na mesma chamada de listar_pedidos/enviar_os — não
    dá pra um achar o outro no disco, porque nenhum foi criado ainda.
    Ainda assim precisam cair na mesma pasta de cliente.
    """
    origem = tmp_path / "etiquetas_geradas"
    destino = tmp_path / "destino"
    _criar_pedido_fake(origem, "NOVO CLIENTE_20260826_090000", nome_cliente="NOVO CLIENTE")
    _criar_pedido_fake(origem, "NOVOCLIENTE_20260826_100000", nome_cliente="NOVOCLIENTE")

    pedidos = listar_pedidos(origem, destino)
    nomes_cliente = {p["cliente"] for p in pedidos}
    assert len(nomes_cliente) == 1, f"deveria resolver pro mesmo cliente, ficou {nomes_cliente}"

    enviar_os(pedidos, destino)
    assert len(list(destino.iterdir())) == 1, "não deveria ter criado duas pastas de cliente"


def test_nome_de_cliente_com_espaco_diferente_reaproveita_a_mesma_pasta(tmp_path):
    """
    Cenário real que já aconteceu: cliente digitado 'SUPERBET' (sem
    espaço) num pedido e 'SUPER BET' (com espaço) noutro. Os dois
    precisam terminar dentro da MESMA pasta de cliente no destino, não
    em duas pastas fragmentadas.
    """
    origem = tmp_path / "etiquetas_geradas"
    destino = tmp_path / "destino"
    _criar_pedido_fake(origem, "SUPERBET_20260824_093132", nome_cliente="SUPERBET")

    pedidos_1 = listar_pedidos(origem, destino)
    enviar_os(pedidos_1, destino)

    # segundo pedido, mesmo cliente, espaço digitado diferente
    _criar_pedido_fake(origem, "SUPER BET_20260825_151149", nome_cliente="SUPER BET")
    pedidos_2 = listar_pedidos(origem, destino)
    pedido_novo = next(p for p in pedidos_2 if p["nome"] == "SUPER BET_20260825_151149")

    assert pedido_novo["cliente"] == "SUPERBET", "deveria reaproveitar a grafia já usada na primeira pasta"
    assert len(list(destino.iterdir())) == 1, "não deveria ter criado uma segunda pasta de cliente"
