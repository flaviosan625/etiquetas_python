import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from arquivamento import enviar_os, listar_pedidos


def _criar_pedido_fake(pasta_base, nome_pedido):
    pasta = pasta_base / nome_pedido
    pasta.mkdir(parents=True)
    (pasta / "OS - CLIENTE.pdf").write_text("pdf")
    (pasta / "OS - CLIENTE.json").write_text("{}")
    (pasta / "OS - CLIENTE - novos 26-08_100000.json").write_text("{}")
    (pasta / "Checklist CLIENTE - LONA.pdf").write_text("checklist")
    (pasta / "estado_pedido.json").write_text("{}")
    return pasta


def test_listar_pedidos_encontra_so_arquivos_de_os(tmp_path):
    origem = tmp_path / "etiquetas_geradas"
    _criar_pedido_fake(origem, "CLIENTE_20260826_100000")

    pedidos = listar_pedidos(origem, tmp_path / "destino")

    assert len(pedidos) == 1
    nomes = {a.name for a in pedidos[0]["arquivos"]}
    assert nomes == {"OS - CLIENTE.pdf", "OS - CLIENTE.json", "OS - CLIENTE - novos 26-08_100000.json"}
    assert pedidos[0]["ja_enviado"] is False


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
    assert len(resumo[0]["copiados"]) == 3
    assert len(list(pasta.iterdir())) == 5, "nada deveria ser apagado do original"
    assert not (destino / "CLIENTE_20260826_100000" / "Checklist CLIENTE - LONA.pdf").exists(), "checklist não deveria ser copiado"
    assert (destino / "CLIENTE_20260826_100000" / "OS - CLIENTE.pdf").exists()


def test_ja_enviado_fica_true_depois_do_envio(tmp_path):
    origem = tmp_path / "etiquetas_geradas"
    destino = tmp_path / "destino"
    _criar_pedido_fake(origem, "CLIENTE_20260826_100000")

    pedidos = listar_pedidos(origem, destino)
    enviar_os(pedidos, destino)

    pedidos_depois = listar_pedidos(origem, destino)
    assert pedidos_depois[0]["ja_enviado"] is True
