import datetime
import json

import pytest

import rasterlink_hotfolder as rl_hf
from rasterlink_hotfolder import enviar_para_fila, logger_arquivo, vigiar_fila, vigiar_fila_uma_vez

MAQUINAS_TESTE = {"UJV100": None}  # caminho da hot folder preenchido por teste, via tmp_path


@pytest.fixture(autouse=True)
def _isolar_pasta_relatorios(tmp_path, monkeypatch):
    """
    PASTA_RELATORIOS aponta pro OneDrive REAL. Qualquer teste que
    dispare um envio chama registrar_envio, que sem isso grava linha de
    mentira no registro de produção — aconteceu de verdade
    (2026-09-05): 45 linhas falsas com 'arte.pdf'/'foto.jpg' foram
    parar no arquivo real e tiveram que ser limpas na mão. É o mesmo
    tropeço que já tinha acontecido com estoque.ESTOQUE_PATH.

    autouse de propósito: teste novo não pode ter a chance de esquecer.
    """
    monkeypatch.setattr(rl_hf, "PASTA_RELATORIOS", tmp_path / "_relatorios_isolados")


def _maquinas(hot_folder, largura_util_m=None):
    if largura_util_m is None:
        return {"UJV100": str(hot_folder)}
    return {"UJV100": {"hot_folder": str(hot_folder), "largura_util_m": largura_util_m}}


def _pdf_de(caminho, largura_cm, altura_cm):
    """PDF de 1 pagina com tamanho fisico exato, pra testar o giro automatico."""
    import pymupdf

    pt_por_cm = 72 / 2.54
    doc = pymupdf.open()
    doc.new_page(width=largura_cm * pt_por_cm, height=altura_cm * pt_por_cm)
    doc.save(str(caminho))
    doc.close()


def _tamanho_cm(caminho):
    import pymupdf

    pt_por_cm = 72 / 2.54
    doc = pymupdf.open(str(caminho))
    rect = doc.load_page(0).rect
    doc.close()
    return round(rect.width / pt_por_cm), round(rect.height / pt_por_cm)


def test_enviar_para_fila_copia_pra_subpasta_da_maquina_sem_mexer_no_original(tmp_path):
    fila = tmp_path / "fila"
    origem = tmp_path / "arte.pdf"
    origem.write_bytes(b"conteudo")

    destino = enviar_para_fila(str(origem), "UJV100", pasta_fila=str(fila), maquinas=_maquinas(tmp_path / "hf"))

    assert destino == fila / "UJV100" / "arte.pdf"
    assert destino.read_bytes() == b"conteudo"
    assert origem.exists(), "original nunca pode sumir — so copia, nunca move"


def test_enviar_para_fila_cria_pasta_se_nao_existir(tmp_path):
    fila = tmp_path / "fila_nova"
    origem = tmp_path / "arte.pdf"
    origem.write_bytes(b"x")

    enviar_para_fila(str(origem), "UJV100", pasta_fila=str(fila), maquinas=_maquinas(tmp_path / "hf"))

    assert (fila / "UJV100").is_dir()


def test_enviar_para_fila_maquina_nao_reconhecida_da_erro_claro(tmp_path):
    origem = tmp_path / "arte.pdf"
    origem.write_bytes(b"x")
    with pytest.raises(ValueError, match="não reconhecida"):
        enviar_para_fila(str(origem), "IMPRESSORA_QUE_NAO_EXISTE", pasta_fila=str(tmp_path / "fila"), maquinas=_maquinas(tmp_path / "hf"))


def test_enviar_para_fila_arquivo_origem_inexistente_da_erro_claro(tmp_path):
    with pytest.raises(FileNotFoundError):
        enviar_para_fila(
            str(tmp_path / "nao_existe.pdf"), "UJV100",
            pasta_fila=str(tmp_path / "fila"), maquinas=_maquinas(tmp_path / "hf"),
        )


def test_vigiar_fila_uma_vez_sem_maquinas_configuradas_da_erro_claro(tmp_path):
    with pytest.raises(RuntimeError, match="[Nn]enhuma máquina"):
        vigiar_fila_uma_vez(pasta_fila=str(tmp_path / "fila"), maquinas={})


def test_vigiar_fila_uma_vez_hot_folder_inexistente_avisa_sem_derrubar_o_ciclo(tmp_path):
    """
    Antes isso levantava FileNotFoundError e derrubava o ciclo inteiro.
    Mudou em 2026-09-05: com mais de uma máquina configurada, a que
    quebra não pode parar as outras (ver
    test_maquina_com_hot_folder_faltando_nao_derruba_as_outras). O erro
    continua aparecendo, agora no log e nomeando a máquina.
    """
    import rasterlink_hotfolder as modulo
    modulo._ultimo_erro_por_maquina.clear()

    linhas = []
    resultado = vigiar_fila_uma_vez(
        pasta_fila=str(tmp_path / "fila"),
        maquinas=_maquinas(tmp_path / "nao_existe"),
        logger=lambda nivel, msg: linhas.append((nivel, msg)),
    )

    assert "Hot folder" in resultado["UJV100"]["erro"]
    assert any(nivel == "err" and "UJV100" in msg for nivel, msg in linhas)


def test_vigiar_fila_uma_vez_pasta_da_maquina_inexistente_retorna_vazio_sem_erro(tmp_path):
    hot_folder = tmp_path / "hotfolder"
    hot_folder.mkdir()

    resultado = vigiar_fila_uma_vez(
        pasta_fila=str(tmp_path / "fila_que_nao_existe"), maquinas=_maquinas(hot_folder),
    )

    assert resultado == {"UJV100": {"enviados": [], "ignorados": []}}


def test_vigiar_fila_uma_vez_envia_arquivo_estavel_e_move_pra_enviados_da_maquina(tmp_path, monkeypatch):
    monkeypatch.setattr(rl_hf.time, "sleep", lambda s: None)
    fila = tmp_path / "fila"
    (fila / "UJV100").mkdir(parents=True)
    hot_folder = tmp_path / "hotfolder"
    hot_folder.mkdir()
    arquivo = fila / "UJV100" / "1 UN LONA 1.00x1.00M teste.pdf"
    arquivo.write_bytes(b"conteudo estavel")

    resultado = vigiar_fila_uma_vez(pasta_fila=str(fila), maquinas=_maquinas(hot_folder))

    assert resultado["UJV100"]["enviados"] == ["1 UN LONA 1.00x1.00M teste.pdf"]
    assert (hot_folder / "1 UN LONA 1.00x1.00M teste.pdf").read_bytes() == b"conteudo estavel"
    assert not arquivo.exists(), "sai da fila depois de enviado"
    assert (fila / "UJV100" / "Enviados" / "1 UN LONA 1.00x1.00M teste.pdf").exists()


def test_vigiar_fila_uma_vez_ignora_arquivo_ainda_crescendo(tmp_path, monkeypatch):
    fila = tmp_path / "fila"
    (fila / "UJV100").mkdir(parents=True)
    hot_folder = tmp_path / "hotfolder"
    hot_folder.mkdir()
    arquivo = fila / "UJV100" / "ainda_baixando.pdf"
    arquivo.write_bytes(b"parcial")

    def sleep_que_simula_crescimento(segundos):
        arquivo.write_bytes(arquivo.read_bytes() + b"mais dados chegando")

    monkeypatch.setattr(rl_hf.time, "sleep", sleep_que_simula_crescimento)

    resultado = vigiar_fila_uma_vez(pasta_fila=str(fila), maquinas=_maquinas(hot_folder))

    assert resultado["UJV100"]["enviados"] == []
    assert not (hot_folder / "ainda_baixando.pdf").exists()
    assert arquivo.exists(), "continua na fila pro proximo ciclo tentar de novo"


def test_vigiar_fila_uma_vez_ignora_extensao_nao_suportada(tmp_path, monkeypatch):
    monkeypatch.setattr(rl_hf.time, "sleep", lambda s: None)
    fila = tmp_path / "fila"
    (fila / "UJV100").mkdir(parents=True)
    hot_folder = tmp_path / "hotfolder"
    hot_folder.mkdir()
    (fila / "UJV100" / "referencia.zip").write_bytes(b"x")

    resultado = vigiar_fila_uma_vez(pasta_fila=str(fila), maquinas=_maquinas(hot_folder))

    assert resultado["UJV100"]["ignorados"] == ["referencia.zip"]
    assert resultado["UJV100"]["enviados"] == []
    assert (fila / "UJV100" / "referencia.zip").exists(), "nunca mexe no que nao reconhece"


def test_vigiar_fila_uma_vez_nao_sobrescreve_arquivo_ja_enviado_antes(tmp_path, monkeypatch):
    monkeypatch.setattr(rl_hf.time, "sleep", lambda s: None)
    fila = tmp_path / "fila"
    (fila / "UJV100").mkdir(parents=True)
    hot_folder = tmp_path / "hotfolder"
    hot_folder.mkdir()
    (fila / "UJV100" / "Enviados").mkdir()
    (fila / "UJV100" / "Enviados" / "arte.pdf").write_bytes(b"envio de ontem")
    (fila / "UJV100" / "arte.pdf").write_bytes(b"envio de hoje")

    vigiar_fila_uma_vez(pasta_fila=str(fila), maquinas=_maquinas(hot_folder))

    assert (fila / "UJV100" / "Enviados" / "arte.pdf").read_bytes() == b"envio de ontem"
    arquivos_enviados = list((fila / "UJV100" / "Enviados").glob("arte_*.pdf"))
    assert len(arquivos_enviados) == 1
    assert arquivos_enviados[0].read_bytes() == b"envio de hoje"


def test_vigiar_fila_uma_vez_processa_cada_maquina_na_sua_propria_hot_folder(tmp_path, monkeypatch):
    monkeypatch.setattr(rl_hf.time, "sleep", lambda s: None)
    fila = tmp_path / "fila"
    hot_a = tmp_path / "hotfolder_a"
    hot_b = tmp_path / "hotfolder_b"
    hot_a.mkdir()
    hot_b.mkdir()
    (fila / "MAQUINA_A").mkdir(parents=True)
    (fila / "MAQUINA_B").mkdir(parents=True)
    (fila / "MAQUINA_A" / "arte_a.pdf").write_bytes(b"a")
    (fila / "MAQUINA_B" / "arte_b.pdf").write_bytes(b"b")

    resultado = vigiar_fila_uma_vez(
        pasta_fila=str(fila),
        maquinas={"MAQUINA_A": str(hot_a), "MAQUINA_B": str(hot_b)},
    )

    assert resultado["MAQUINA_A"]["enviados"] == ["arte_a.pdf"]
    assert resultado["MAQUINA_B"]["enviados"] == ["arte_b.pdf"]
    assert (hot_a / "arte_a.pdf").exists()
    assert (hot_b / "arte_b.pdf").exists()
    assert not (hot_a / "arte_b.pdf").exists(), "arquivo de uma maquina nunca vai pra hot folder da outra"
    assert not (hot_b / "arte_a.pdf").exists()


def test_vigiar_fila_uma_vez_avisa_sobre_pasta_que_nao_bate_com_nenhuma_maquina(tmp_path, monkeypatch):
    monkeypatch.setattr(rl_hf.time, "sleep", lambda s: None)
    fila = tmp_path / "fila"
    hot_folder = tmp_path / "hotfolder"
    hot_folder.mkdir()
    (fila / "UJV100").mkdir(parents=True)
    (fila / "NOME_ERRADO_DIGITADO").mkdir(parents=True)

    avisos = []
    vigiar_fila_uma_vez(
        pasta_fila=str(fila), maquinas=_maquinas(hot_folder),
        logger=lambda nivel, msg: avisos.append((nivel, msg)),
    )

    assert any(nivel == "warn" and "NOME_ERRADO_DIGITADO" in msg for nivel, msg in avisos)


def _fila_com_pdf(tmp_path, monkeypatch, largura_cm, altura_cm, nome="arte.pdf"):
    monkeypatch.setattr(rl_hf.time, "sleep", lambda s: None)
    fila = tmp_path / "fila"
    (fila / "UJV100").mkdir(parents=True)
    hot_folder = tmp_path / "hotfolder"
    hot_folder.mkdir()
    _pdf_de(fila / "UJV100" / nome, largura_cm, altura_cm)
    return fila, hot_folder


def test_pdf_mais_largo_que_a_maquina_vai_girado_pra_hot_folder(tmp_path, monkeypatch):
    # 200cm de largura numa maquina de 148cm uteis, mas so 100cm de
    # altura — girado passa a ter 100cm de largura e cabe.
    fila, hot_folder = _fila_com_pdf(tmp_path, monkeypatch, largura_cm=200, altura_cm=100)

    avisos = []
    vigiar_fila_uma_vez(
        pasta_fila=str(fila), maquinas=_maquinas(hot_folder, largura_util_m=1.48),
        logger=lambda nivel, msg: avisos.append((nivel, msg)),
    )

    assert _tamanho_cm(hot_folder / "arte.pdf") == (100, 200), "devia chegar girado no RIP"
    assert any("gir" in msg.lower() for _, msg in avisos), "o giro precisa ficar registrado no log"


def test_pdf_alto_e_estreito_gira_pra_gastar_menos_bobina(tmp_path, monkeypatch):
    # 1,00x3,00m numa bobina de 3,20m: cabe dos dois jeitos, mas em pe
    # gasta 3m de material e deitado gasta so 1m.
    fila, hot_folder = _fila_com_pdf(tmp_path, monkeypatch, largura_cm=100, altura_cm=300)

    avisos = []
    vigiar_fila_uma_vez(
        pasta_fila=str(fila), maquinas=_maquinas(hot_folder, largura_util_m=3.20),
        logger=lambda nivel, msg: avisos.append((nivel, msg)),
    )

    assert _tamanho_cm(hot_folder / "arte.pdf") == (300, 100), "devia deitar pra economizar bobina"
    assert any("economiza 2.00m" in msg for _, msg in avisos), "a economia precisa aparecer no log"


def test_pdf_ja_deitado_do_jeito_mais_economico_nao_gira(tmp_path, monkeypatch):
    # 3,00x1,00m na bobina de 3,20m ja esta na melhor posicao: gasta 1m.
    fila, hot_folder = _fila_com_pdf(tmp_path, monkeypatch, largura_cm=300, altura_cm=100)

    vigiar_fila_uma_vez(pasta_fila=str(fila), maquinas=_maquinas(hot_folder, largura_util_m=3.20))

    assert _tamanho_cm(hot_folder / "arte.pdf") == (300, 100), "girar so trocaria os lados sem ganho"


def test_pdf_exatamente_na_largura_da_bobina_passa_sem_giro_nem_aviso(tmp_path, monkeypatch):
    # 3,20x10,00m numa bobina de 3,20m — encaixe exato. Sem folga na
    # comparacao, a conversao de pontos pra metros faria isso virar
    # 3.2000000038 e ser recusado por arredondamento.
    fila, hot_folder = _fila_com_pdf(tmp_path, monkeypatch, largura_cm=320, altura_cm=1000)

    avisos = []
    vigiar_fila_uma_vez(
        pasta_fila=str(fila), maquinas=_maquinas(hot_folder, largura_util_m=3.20),
        logger=lambda nivel, msg: avisos.append((nivel, msg)),
    )

    assert _tamanho_cm(hot_folder / "arte.pdf") == (320, 1000)
    assert not any(nivel == "warn" for nivel, _ in avisos), "encaixe exato nao e problema"


def test_pdf_que_ja_cabe_na_maquina_nunca_e_girado(tmp_path, monkeypatch):
    fila, hot_folder = _fila_com_pdf(tmp_path, monkeypatch, largura_cm=100, altura_cm=200)

    vigiar_fila_uma_vez(pasta_fila=str(fila), maquinas=_maquinas(hot_folder, largura_util_m=1.48))

    assert _tamanho_cm(hot_folder / "arte.pdf") == (100, 200), "cabia do jeito que estava"


def test_pdf_que_nao_cabe_nem_girado_vai_assim_mesmo_com_aviso(tmp_path, monkeypatch):
    fila, hot_folder = _fila_com_pdf(tmp_path, monkeypatch, largura_cm=200, altura_cm=300)

    avisos = []
    resultado = vigiar_fila_uma_vez(
        pasta_fila=str(fila), maquinas=_maquinas(hot_folder, largura_util_m=1.48),
        logger=lambda nivel, msg: avisos.append((nivel, msg)),
    )

    assert resultado["UJV100"]["enviados"] == ["arte.pdf"], "escolha do usuario: manda mesmo assim"
    assert _tamanho_cm(hot_folder / "arte.pdf") == (200, 300), "girar nao resolveria, entao vai como veio"
    assert any(nivel == "warn" and "nem girado" in msg for nivel, msg in avisos)


def test_original_na_fila_nunca_e_girado_mesmo_quando_a_copia_gira(tmp_path, monkeypatch):
    fila, hot_folder = _fila_com_pdf(tmp_path, monkeypatch, largura_cm=200, altura_cm=100)

    vigiar_fila_uma_vez(pasta_fila=str(fila), maquinas=_maquinas(hot_folder, largura_util_m=1.48))

    arquivado = fila / "UJV100" / "Enviados" / "arte.pdf"
    assert _tamanho_cm(arquivado) == (200, 100), "o arquivo guardado tem que ser sempre o original intacto"


def test_maquina_sem_largura_configurada_nao_analisa_nem_gira(tmp_path, monkeypatch):
    fila, hot_folder = _fila_com_pdf(tmp_path, monkeypatch, largura_cm=200, altura_cm=100)

    vigiar_fila_uma_vez(pasta_fila=str(fila), maquinas=_maquinas(hot_folder))

    assert _tamanho_cm(hot_folder / "arte.pdf") == (200, 100)


def test_arquivo_que_nao_e_pdf_passa_intacto_sem_analise_de_largura(tmp_path, monkeypatch):
    monkeypatch.setattr(rl_hf.time, "sleep", lambda s: None)
    fila = tmp_path / "fila"
    (fila / "UJV100").mkdir(parents=True)
    hot_folder = tmp_path / "hotfolder"
    hot_folder.mkdir()
    (fila / "UJV100" / "foto.jpg").write_bytes(b"nao e um pdf de verdade")

    resultado = vigiar_fila_uma_vez(
        pasta_fila=str(fila), maquinas=_maquinas(hot_folder, largura_util_m=1.48),
    )

    assert resultado["UJV100"]["enviados"] == ["foto.jpg"]
    assert (hot_folder / "foto.jpg").read_bytes() == b"nao e um pdf de verdade"


def test_pdf_ilegivel_vai_assim_mesmo_com_aviso(tmp_path, monkeypatch):
    monkeypatch.setattr(rl_hf.time, "sleep", lambda s: None)
    fila = tmp_path / "fila"
    (fila / "UJV100").mkdir(parents=True)
    hot_folder = tmp_path / "hotfolder"
    hot_folder.mkdir()
    (fila / "UJV100" / "quebrado.pdf").write_bytes(b"%PDF-1.4 lixo que nao abre")

    avisos = []
    resultado = vigiar_fila_uma_vez(
        pasta_fila=str(fila), maquinas=_maquinas(hot_folder, largura_util_m=1.48),
        logger=lambda nivel, msg: avisos.append((nivel, msg)),
    )

    assert resultado["UJV100"]["enviados"] == ["quebrado.pdf"], "nunca segura arquivo por falha nossa de leitura"
    assert any(nivel == "warn" for nivel, _ in avisos)


def test_giro_continua_funcionando_sem_pymupdf_instalado(tmp_path, monkeypatch):
    # A maquina do RIP tem um Python novo em folha — se o pymupdf nao
    # estiver la, o vigia nao pode parar de enviar: so avisa e copia.
    fila, hot_folder = _fila_com_pdf(tmp_path, monkeypatch, largura_cm=200, altura_cm=100)
    monkeypatch.setattr(rl_hf, "_importar_pymupdf", lambda: None)

    avisos = []
    resultado = vigiar_fila_uma_vez(
        pasta_fila=str(fila), maquinas=_maquinas(hot_folder, largura_util_m=1.48),
        logger=lambda nivel, msg: avisos.append((nivel, msg)),
    )

    assert resultado["UJV100"]["enviados"] == ["arte.pdf"]
    assert _tamanho_cm(hot_folder / "arte.pdf") == (200, 100), "sem pymupdf, copia sem mexer"
    assert any(nivel == "warn" and "pymupdf" in msg.lower() for nivel, msg in avisos)


def test_vigiar_fila_nunca_trava_com_erro_no_ciclo(monkeypatch):
    chamadas = []

    def uma_vez_fake(*args, **kwargs):
        chamadas.append(1)
        raise RuntimeError("falha simulada")

    def sleep_que_para_apos_duas_voltas(segundos):
        if len(chamadas) >= 2:
            raise StopIteration

    monkeypatch.setattr(rl_hf, "vigiar_fila_uma_vez", uma_vez_fake)
    monkeypatch.setattr(rl_hf.time, "sleep", sleep_que_para_apos_duas_voltas)

    erros = []
    with pytest.raises(StopIteration):
        vigiar_fila(logger=lambda nivel, msg: erros.append((nivel, msg)))

    assert len(chamadas) == 2, "erro num ciclo nao pode impedir o proximo"
    assert any(nivel == "err" for nivel, _ in erros)


def _envelhecer(caminho, dias):
    import os
    quando = (datetime.datetime.now() - datetime.timedelta(days=dias)).timestamp()
    os.utime(caminho, (quando, quando))


def test_registrar_envio_grava_uma_linha_json_no_arquivo_do_mes(tmp_path):
    arquivo = tmp_path / "arte.pdf"
    arquivo.write_bytes(b"12345")
    quando = datetime.datetime(2026, 9, 5, 14, 30, 0)

    assert rl_hf.registrar_envio("SWJ320A", arquivo, girado=True, pasta_relatorios=tmp_path / "rel", quando=quando) is True

    registro = tmp_path / "rel" / "_registro" / "2026-09.jsonl"
    dados = json.loads(registro.read_text(encoding="utf-8").strip())
    assert dados == {
        "quando": "2026-09-05T14:30:00", "maquina": "SWJ320A",
        "arquivo": "arte.pdf", "bytes": 5, "girado": True,
    }


def test_registrar_envio_acumula_sem_apagar_o_que_ja_tinha(tmp_path):
    arquivo = tmp_path / "arte.pdf"
    arquivo.write_bytes(b"x")
    quando = datetime.datetime(2026, 9, 5, 8, 0, 0)

    rl_hf.registrar_envio("SWJ320A", arquivo, False, pasta_relatorios=tmp_path / "rel", quando=quando)
    rl_hf.registrar_envio("UJV 100 UNY CV", arquivo, False, pasta_relatorios=tmp_path / "rel", quando=quando)

    linhas = (tmp_path / "rel" / "_registro" / "2026-09.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert [json.loads(l)["maquina"] for l in linhas] == ["SWJ320A", "UJV 100 UNY CV"]


def test_registrar_envio_separa_por_mes(tmp_path):
    arquivo = tmp_path / "arte.pdf"
    arquivo.write_bytes(b"x")
    rel = tmp_path / "rel"

    rl_hf.registrar_envio("SWJ320A", arquivo, False, pasta_relatorios=rel, quando=datetime.datetime(2026, 8, 31, 23, 59))
    rl_hf.registrar_envio("SWJ320A", arquivo, False, pasta_relatorios=rel, quando=datetime.datetime(2026, 9, 1, 0, 1))

    assert (rel / "_registro" / "2026-08.jsonl").exists()
    assert (rel / "_registro" / "2026-09.jsonl").exists()


def test_registrar_envio_nunca_estoura_quando_nao_consegue_gravar(tmp_path):
    arquivo = tmp_path / "arte.pdf"
    arquivo.write_bytes(b"x")
    # caminho invalido no Windows (caractere proibido) — nao pode levantar
    assert rl_hf.registrar_envio("SWJ320A", arquivo, False, pasta_relatorios=tmp_path / "in<>valido") is False


def test_registrar_envio_avisa_no_log_quando_nao_consegue_gravar(tmp_path):
    """
    Falhar em silencio aqui seria a pior falha possivel: o arquivo vai
    pra impressao, mas some do historico — e so se descobre no dia em
    que a comprovacao fizer falta.
    """
    arquivo = tmp_path / "arte.pdf"
    arquivo.write_bytes(b"x")
    avisos = []

    rl_hf.registrar_envio(
        "SWJ320A", arquivo, False, pasta_relatorios=tmp_path / "in<>valido",
        logger=lambda nivel, msg: avisos.append((nivel, msg)),
    )

    assert any(nivel == "warn" and "arte.pdf" in msg for nivel, msg in avisos)
    assert any("relatório do dia" in msg for _, msg in avisos), "o aviso precisa dizer a consequencia"


def test_falha_de_registro_nao_impede_o_envio_pra_impressora(tmp_path, monkeypatch):
    monkeypatch.setattr(rl_hf.time, "sleep", lambda s: None)
    fila = tmp_path / "fila"
    (fila / "UJV100").mkdir(parents=True)
    hot_folder = tmp_path / "hotfolder"
    hot_folder.mkdir()
    (fila / "UJV100" / "arte.pdf").write_bytes(b"conteudo")

    resultado = vigiar_fila_uma_vez(
        pasta_fila=str(fila), maquinas=_maquinas(hot_folder),
        logger=lambda n, m: None, pasta_relatorios=tmp_path / "in<>valido",
    )

    assert resultado["UJV100"]["enviados"] == ["arte.pdf"]
    assert (hot_folder / "arte.pdf").exists(), "a arte tem que chegar na impressora mesmo assim"


def test_limpar_enviados_apaga_o_que_passou_do_prazo(tmp_path):
    enviados = tmp_path / "SWJ320A" / "Enviados"
    enviados.mkdir(parents=True)
    velho = enviados / "de_20_dias.pdf"
    novo = enviados / "de_ontem.pdf"
    velho.write_bytes(b"x")
    novo.write_bytes(b"x")
    _envelhecer(velho, 20)
    _envelhecer(novo, 1)

    apagados = rl_hf.limpar_enviados_antigos(enviados, dias=15, logger=lambda n, m: None)

    assert apagados == ["de_20_dias.pdf"]
    assert not velho.exists()
    assert novo.exists(), "o que esta dentro do prazo nao pode sumir"


def test_limpar_enviados_nao_apaga_bem_no_limite(tmp_path):
    enviados = tmp_path / "SWJ320A" / "Enviados"
    enviados.mkdir(parents=True)
    no_limite = enviados / "de_14_dias.pdf"
    no_limite.write_bytes(b"x")
    _envelhecer(no_limite, 14)

    assert rl_hf.limpar_enviados_antigos(enviados, dias=15, logger=lambda n, m: None) == []
    assert no_limite.exists()


def test_limpar_enviados_ignora_pasta_inexistente(tmp_path):
    assert rl_hf.limpar_enviados_antigos(tmp_path / "nao_existe", dias=15) == []


def test_vigiar_fila_registra_cada_envio_e_limpa_o_antigo(tmp_path, monkeypatch):
    monkeypatch.setattr(rl_hf.time, "sleep", lambda s: None)
    fila = tmp_path / "fila"
    (fila / "UJV100").mkdir(parents=True)
    hot_folder = tmp_path / "hotfolder"
    hot_folder.mkdir()
    (fila / "UJV100" / "arte_nova.pdf").write_bytes(b"conteudo")

    # arquivo antigo ja arquivado, que deve ser varrido no mesmo ciclo
    enviados = fila / "UJV100" / "Enviados"
    enviados.mkdir()
    antigo = enviados / "arte_de_marco.pdf"
    antigo.write_bytes(b"x")
    _envelhecer(antigo, 40)

    rel = tmp_path / "rel"
    vigiar_fila_uma_vez(
        pasta_fila=str(fila), maquinas=_maquinas(hot_folder),
        logger=lambda n, m: None, pasta_relatorios=rel, dias_retencao=15,
    )

    registros = list((rel / "_registro").glob("*.jsonl"))
    assert len(registros) == 1
    dados = json.loads(registros[0].read_text(encoding="utf-8").strip())
    assert dados["arquivo"] == "arte_nova.pdf"
    assert dados["maquina"] == "UJV100"

    assert not antigo.exists(), "o de 40 dias devia ter sido apagado"
    assert (enviados / "arte_nova.pdf").exists(), "o recem-enviado fica"


def test_registro_anota_quando_o_arquivo_foi_girado(tmp_path, monkeypatch):
    fila, hot_folder = _fila_com_pdf(tmp_path, monkeypatch, largura_cm=100, altura_cm=300)
    rel = tmp_path / "rel"

    vigiar_fila_uma_vez(
        pasta_fila=str(fila), maquinas=_maquinas(hot_folder, largura_util_m=3.20),
        logger=lambda n, m: None, pasta_relatorios=rel,
    )

    registro = next((rel / "_registro").glob("*.jsonl"))
    assert json.loads(registro.read_text(encoding="utf-8").strip())["girado"] is True


def test_trava_impede_dois_vigias_ao_mesmo_tempo(tmp_path):
    trava = tmp_path / "vigia.lock"

    pode_primeiro, handle = rl_hf._travar_instancia_unica(caminho_trava=trava)
    try:
        assert pode_primeiro
        pode_segundo, _ = rl_hf._travar_instancia_unica(caminho_trava=trava)
        assert not pode_segundo, "dois vigias juntos mandam arquivo duplicado pro RIP"
    finally:
        if handle:
            handle.close()


def test_trava_liberada_deixa_o_proximo_vigia_subir(tmp_path):
    trava = tmp_path / "vigia.lock"
    _, handle = rl_hf._travar_instancia_unica(caminho_trava=trava)
    handle.close()  # simula o vigia anterior morrendo

    pode, handle2 = rl_hf._travar_instancia_unica(caminho_trava=trava)
    try:
        assert pode, "com o vigia anterior morto, o proximo tem que conseguir subir"
    finally:
        if handle2:
            handle2.close()


def test_trava_impossivel_de_criar_nao_impede_o_vigia(tmp_path):
    pode, _ = rl_hf._travar_instancia_unica(caminho_trava=tmp_path / "pasta_que_nao_existe" / "vigia.lock")

    assert pode, "falha nossa de trava nunca pode deixar a fila parada"


def test_logger_arquivo_grava_no_arquivo_mesmo_sem_console(tmp_path, monkeypatch):
    caminho_log = tmp_path / "log.txt"

    def print_fake(*args, **kwargs):
        raise AttributeError("'NoneType' object has no attribute 'write'")

    monkeypatch.setattr(rl_hf, "print", print_fake, raising=False)

    logger_arquivo("ok", "mensagem de teste", caminho_log=caminho_log)

    conteudo = caminho_log.read_text(encoding="utf-8")
    assert "[ok] mensagem de teste" in conteudo


def test_logger_arquivo_acumula_varias_chamadas(tmp_path):
    caminho_log = tmp_path / "log.txt"

    logger_arquivo("info", "primeira", caminho_log=caminho_log)
    logger_arquivo("err", "segunda", caminho_log=caminho_log)

    linhas = caminho_log.read_text(encoding="utf-8").splitlines()
    assert len(linhas) == 2
    assert "[info] primeira" in linhas[0]
    assert "[err] segunda" in linhas[1]


def test_logger_arquivo_nunca_estoura_erro_se_nao_conseguir_escrever_arquivo(tmp_path):
    caminho_log_invalido = tmp_path / "pasta_que_nao_existe" / "log.txt"

    logger_arquivo("ok", "mensagem", caminho_log=caminho_log_invalido)  # nao deve levantar exececao


def test_maquina_com_hot_folder_faltando_nao_derruba_as_outras(tmp_path, capsys):
    """
    Achado ao vivo (2026-09-05): a hot folder da UJV sumindo derrubava o
    ciclo inteiro, e como a UJV é a PRIMEIRA do dicionário, a SWJ nunca
    chegava a ser processada — as duas máquinas paravam por causa de uma.
    """
    fila = tmp_path / "fila"
    hot_boa = tmp_path / "hot_boa"
    hot_boa.mkdir()
    maquinas = {
        "QUEBRADA": str(tmp_path / "nao_existe"),
        "BOA": str(hot_boa),
    }
    (fila / "BOA").mkdir(parents=True)
    (fila / "BOA" / "arte.pdf").write_bytes(b"conteudo")

    linhas = []
    resultado = vigiar_fila_uma_vez(
        pasta_fila=str(fila), maquinas=maquinas, logger=lambda n, m: linhas.append((n, m)),
    )

    assert resultado["BOA"]["enviados"] == ["arte.pdf"]
    assert (hot_boa / "arte.pdf").exists()
    assert "erro" in resultado["QUEBRADA"]
    assert any(nivel == "err" and "QUEBRADA" in msg for nivel, msg in linhas)


def test_erro_de_maquina_nao_repete_no_log_a_cada_ciclo(tmp_path):
    """Uma hot folder faltando por um fim de semana encheria o log com milhares de linhas iguais."""
    import rasterlink_hotfolder as modulo
    modulo._ultimo_erro_por_maquina.clear()

    fila = tmp_path / "fila"
    maquinas = {"QUEBRADA": str(tmp_path / "nao_existe")}

    linhas = []
    for _ in range(3):
        vigiar_fila_uma_vez(pasta_fila=str(fila), maquinas=maquinas,
                            logger=lambda n, m: linhas.append((n, m)))

    assert sum(1 for nivel, _ in linhas if nivel == "err") == 1


def test_maquina_que_volta_a_funcionar_avisa(tmp_path):
    import rasterlink_hotfolder as modulo
    modulo._ultimo_erro_por_maquina.clear()

    fila = tmp_path / "fila"
    hot = tmp_path / "hot"
    maquinas = {"UJV100": str(hot)}

    linhas = []
    vigiar_fila_uma_vez(pasta_fila=str(fila), maquinas=maquinas, logger=lambda n, m: linhas.append((n, m)))
    hot.mkdir()
    vigiar_fila_uma_vez(pasta_fila=str(fila), maquinas=maquinas, logger=lambda n, m: linhas.append((n, m)))

    assert any(nivel == "err" for nivel, _ in linhas)
    assert any(nivel == "ok" and "voltou a funcionar" in msg for nivel, msg in linhas)
