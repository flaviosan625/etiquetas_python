import pathlib

from rasterlink import classificar, rastrear


def test_classificar_exato_parecido_e_nenhum():
    lista = ["2UN LONA IMPRESSA 1.00X2.00M_banner"]
    assert classificar("2UN LONA IMPRESSA 1.00X2.00M_banner.pdf", lista)[0] == "exato"
    assert classificar("2UN LONA IMPRESSA 1.00X2.00M_banner2.pdf", lista)[0] == "parecido"
    assert classificar("9UN PVC 5.00X5.00M_outracoisa.pdf", lista)[0] == "nenhum"


def test_normalizar_nao_corta_no_ponto_decimal_da_medida():
    """
    Regressão: pathlib.Path(nome).stem trata o ÚLTIMO ponto de
    qualquer string como extensão — corta errado num nome do RIP como
    "1.00X2.00M_banner" (colado sem ".pdf" de verdade).
    """
    lista = ["2UN LONA IMPRESSA 1.00X2.00M_banner"]
    classe, correspondencia = classificar("2UN LONA IMPRESSA 1.00X2.00M_banner.pdf", lista)
    assert classe == "exato"
    assert correspondencia == "2UN LONA IMPRESSA 1.00X2.00M_banner"


def test_termo_ignorado_reconcilia_nome_que_ganhou_um_trecho_a_mais():
    """
    Caso real (FESTA ALEMÃ, 2026-09-01): o nome do cliente foi inserido
    no arquivo DEPOIS que o RIP já tinha importado o job — sem ignorar
    esse trecho, todo item vira "parecido" em vez de "exato".
    """
    lista = ["2UN LONA IMPRESSA 1.00X2.00M_banner"]
    sem_ignorar = classificar("2UN LONA IMPRESSA 1.00X2.00M_FESTA ALEMA_banner.pdf", lista)
    assert sem_ignorar[0] == "parecido"

    com_ignorar = classificar(
        "2UN LONA IMPRESSA 1.00X2.00M_FESTA ALEMA_banner.pdf", lista, termo_ignorado="FESTA ALEMA",
    )
    assert com_ignorar[0] == "exato"


def test_rastrear_move_exato_avisa_parecido_e_nao_mexe_no_resto(tmp_path):
    pasta = tmp_path
    (pasta / "Prontos").mkdir()
    (pasta / "2UN LONA IMPRESSA 1.00X2.00M_banner.pdf").write_bytes(b"x")        # bate exato -> Prontos
    (pasta / "3UN LONA IMPRESSA 1.50X2.50M_outro.pdf").write_bytes(b"x")         # sem match -> continua solto
    (pasta / "1UN LONA IMPRESSA 2.00X2.00M_parecido.pdf").write_bytes(b"x")      # parecido -> duvidoso
    (pasta / "Prontos" / "5UN LONA IMPRESSA 3.00X1.00M_ja_pronto.pdf").write_bytes(b"x")   # não está na lista -> volta solto
    (pasta / "Prontos" / "9UN LONA IMPRESSA 4.00X1.00M_confirmado.pdf").write_bytes(b"x")  # bate exato, já em Prontos -> fica

    lista = [
        "2UN LONA IMPRESSA 1.00X2.00M_banner",
        "1UN LONA IMPRESSA 2.00X2.00M_parecidoo",
        "9UN LONA IMPRESSA 4.00X1.00M_confirmado",
    ]
    resultado = rastrear(str(pasta), lista, raiz_busca_outros_clientes=tmp_path / "nao_existe_outros")

    assert resultado["movidos_pra_prontos"] == ["2UN LONA IMPRESSA 1.00X2.00M_banner.pdf"]
    assert resultado["movidos_pra_solto"] == ["5UN LONA IMPRESSA 3.00X1.00M_ja_pronto.pdf"]
    assert len(resultado["duvidosos"]) == 1
    assert resultado["duvidosos"][0][1] == "1UN LONA IMPRESSA 2.00X2.00M_parecido.pdf"
    assert resultado["erros"] == []

    soltos_finais = sorted(f.name for f in pasta.iterdir() if f.is_file())
    prontos_finais = sorted(f.name for f in (pasta / "Prontos").iterdir() if f.is_file())
    assert soltos_finais == [
        "1UN LONA IMPRESSA 2.00X2.00M_parecido.pdf",
        "3UN LONA IMPRESSA 1.50X2.50M_outro.pdf",
        "5UN LONA IMPRESSA 3.00X1.00M_ja_pronto.pdf",
    ]
    assert prontos_finais == [
        "2UN LONA IMPRESSA 1.00X2.00M_banner.pdf",
        "9UN LONA IMPRESSA 4.00X1.00M_confirmado.pdf",
    ]


def test_rastrear_nunca_apaga_so_move(tmp_path):
    pasta = tmp_path
    (pasta / "Prontos").mkdir()
    (pasta / "1UN LONA IMPRESSA 1.00X1.00M_a.pdf").write_bytes(b"conteudo")

    rastrear(
        str(pasta), ["1UN LONA IMPRESSA 1.00X1.00M_a"],
        raiz_busca_outros_clientes=tmp_path / "nao_existe_outros",
    )

    arquivos = list(pathlib.Path(pasta).rglob("*.pdf"))
    assert len(arquivos) == 1
    assert arquivos[0].read_bytes() == b"conteudo"


def test_rastrear_pasta_inexistente_da_erro_claro(tmp_path):
    import pytest
    with pytest.raises(FileNotFoundError):
        rastrear(str(tmp_path / "nao_existe"), ["qualquer coisa"])


def test_item_sem_match_local_e_achado_solto_em_outro_cliente_e_inserido_no_prontos_de_la(tmp_path):
    """
    Regra extra (2026-09-02): a Job List do RIP serve a fábrica
    inteira — um item que não bate com nada na pasta apontada
    provavelmente é de OUTRO cliente, arquivado em outra pasta.
    """
    pasta_cliente_a = tmp_path / "Cliente A"
    pasta_cliente_a.mkdir()
    (pasta_cliente_a / "Prontos").mkdir()

    pasta_cliente_b = tmp_path / "Cliente B"
    pasta_cliente_b.mkdir()
    (pasta_cliente_b / "5UN LONA IMPRESSA 3.00X1.00M_de_outro_cliente.pdf").write_bytes(b"x")

    resultado = rastrear(
        str(pasta_cliente_a), ["5UN LONA IMPRESSA 3.00X1.00M_de_outro_cliente"],
        raiz_busca_outros_clientes=tmp_path,
    )

    assert resultado["achados_em_outra_pasta"] == [
        (
            "5UN LONA IMPRESSA 3.00X1.00M_de_outro_cliente",
            str(pasta_cliente_b / "5UN LONA IMPRESSA 3.00X1.00M_de_outro_cliente.pdf"),
            str(pasta_cliente_b / "Prontos" / "5UN LONA IMPRESSA 3.00X1.00M_de_outro_cliente.pdf"),
        )
    ]
    assert not (pasta_cliente_b / "5UN LONA IMPRESSA 3.00X1.00M_de_outro_cliente.pdf").exists()
    assert (pasta_cliente_b / "Prontos" / "5UN LONA IMPRESSA 3.00X1.00M_de_outro_cliente.pdf").exists()
    # a pasta A (a apontada) nunca ganha o arquivo do cliente B
    assert not list((pasta_cliente_a / "Prontos").glob("*.pdf"))


def test_item_ja_no_prontos_de_outro_cliente_e_apenas_ignorado(tmp_path):
    """"Se já estiver lá, só ignorar" — pedido explícito do usuário."""
    pasta_cliente_a = tmp_path / "Cliente A"
    pasta_cliente_a.mkdir()
    (pasta_cliente_a / "Prontos").mkdir()

    pasta_cliente_b = tmp_path / "Cliente B"
    (pasta_cliente_b / "Prontos").mkdir(parents=True)
    caminho_ja_pronto = pasta_cliente_b / "Prontos" / "9UN LONA IMPRESSA 4.00X1.00M_ja_pronto_em_b.pdf"
    caminho_ja_pronto.write_bytes(b"conteudo")

    resultado = rastrear(
        str(pasta_cliente_a), ["9UN LONA IMPRESSA 4.00X1.00M_ja_pronto_em_b"],
        raiz_busca_outros_clientes=tmp_path,
    )

    assert resultado["achados_em_outra_pasta"] == []
    assert resultado["nao_encontrados"] == []
    assert resultado["erros"] == []
    assert caminho_ja_pronto.exists(), "nunca deveria mexer num arquivo que já está no Prontos certo"


def test_item_sem_match_em_lugar_nenhum_e_reportado_separadamente(tmp_path):
    pasta_cliente_a = tmp_path / "Cliente A"
    pasta_cliente_a.mkdir()
    (pasta_cliente_a / "Prontos").mkdir()

    resultado = rastrear(
        str(pasta_cliente_a), ["1UN LONA IMPRESSA 9.99X9.99M_nao_existe_em_lugar_nenhum"],
        raiz_busca_outros_clientes=tmp_path,
    )

    assert resultado["nao_encontrados"] == ["1UN LONA IMPRESSA 9.99X9.99M_nao_existe_em_lugar_nenhum"]
    assert resultado["achados_em_outra_pasta"] == []
    assert resultado["erros"] == []


def test_ambiguidade_entre_duas_pastas_diferentes_vira_erro_nao_move_sozinho(tmp_path):
    pasta_cliente_a = tmp_path / "Cliente A"
    pasta_cliente_a.mkdir()
    (pasta_cliente_a / "Prontos").mkdir()

    pasta_cliente_b = tmp_path / "Cliente B"
    pasta_cliente_b.mkdir()
    (pasta_cliente_b / "1UN LONA IMPRESSA 1.00X1.00M_ambiguo.pdf").write_bytes(b"x")

    pasta_cliente_c = tmp_path / "Cliente C"
    pasta_cliente_c.mkdir()
    (pasta_cliente_c / "1UN LONA IMPRESSA 1.00X1.00M_ambiguo.pdf").write_bytes(b"x")

    resultado = rastrear(
        str(pasta_cliente_a), ["1UN LONA IMPRESSA 1.00X1.00M_ambiguo"],
        raiz_busca_outros_clientes=tmp_path,
    )

    assert resultado["achados_em_outra_pasta"] == []
    assert len(resultado["erros"]) == 1
    assert "MAIS DE UM arquivo" in resultado["erros"][0]
    # nenhum dos dois foi movido
    assert (pasta_cliente_b / "1UN LONA IMPRESSA 1.00X1.00M_ambiguo.pdf").exists()
    assert (pasta_cliente_c / "1UN LONA IMPRESSA 1.00X1.00M_ambiguo.pdf").exists()
