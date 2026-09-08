import datetime
import json
import os
import pathlib

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

    Junto vão o log, a trava e o estado de avisos: todos moram AO LADO
    do módulo, então sem isso um teste suja a pasta do projeto — e o
    log de verdade, que é o que a gente lê quando a fila para, ganha
    linha de mentira no meio.
    """
    monkeypatch.setattr(rl_hf, "PASTA_RELATORIOS", tmp_path / "_relatorios_isolados")
    monkeypatch.setattr(rl_hf, "CAMINHO_LOG", tmp_path / "hotfolder.log")
    monkeypatch.setattr(rl_hf, "CAMINHO_TRAVA", tmp_path / "hotfolder.lock")
    monkeypatch.setattr(rl_hf, "CAMINHO_ESTADO_AVISOS", tmp_path / "hotfolder_avisos.json")
    # O crash tambem: sem esta linha, toda rodada de teste que passa por
    # _rodar_protegido despeja traceback no arquivo de verdade do
    # repositorio. Foram 49 entradas acumuladas assim, todas do mesmo
    # teste, e uma investigacao inteira atras de um defeito de producao
    # que nunca existiu (2026-09-07).
    monkeypatch.setattr(rl_hf, "CAMINHO_CRASH", tmp_path / "hotfolder_crash.log")


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

    assert resultado == {"UJV100": {"enviados": [], "ignorados": [], "falharam": []}}


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


def test_um_arquivo_com_problema_nao_prende_a_fila_atras_dele(tmp_path, monkeypatch):
    """
    Aconteceu de verdade (2026-09-05): 6 arquivos passaram, o setimo
    falhou na copia, e os 5 seguintes ficaram parados PARA SEMPRE —
    todo ciclo novo recomecava pelo mesmo arquivo ruim e morria no mesmo
    ponto. Um arquivo com problema so pode prender a si mesmo.
    """
    import shutil as shutil_real
    import rasterlink_hotfolder as modulo
    modulo._ultimo_erro_por_arquivo.clear()

    fila = tmp_path / "fila"
    hot = tmp_path / "hot"
    hot.mkdir()
    (fila / "UJV100").mkdir(parents=True)
    for nome in ("a_boa.pdf", "b_ruim.pdf", "c_boa.pdf"):
        (fila / "UJV100" / nome).write_bytes(b"conteudo")

    copia_real = modulo.shutil.copy2

    def falha_na_ruim(origem, destino, *args, **kwargs):
        if "ruim" in str(origem):
            raise OSError("nao consegui baixar o arquivo do OneDrive")
        return copia_real(origem, destino, *args, **kwargs)

    monkeypatch.setattr(modulo.shutil, "copy2", falha_na_ruim)

    linhas = []
    resultado = vigiar_fila_uma_vez(
        pasta_fila=str(fila), maquinas={"UJV100": str(hot)},
        logger=lambda n, m: linhas.append((n, m)),
    )

    assert sorted(resultado["UJV100"]["enviados"]) == ["a_boa.pdf", "c_boa.pdf"]
    assert resultado["UJV100"]["falharam"] == ["b_ruim.pdf"]
    assert (hot / "a_boa.pdf").exists() and (hot / "c_boa.pdf").exists()
    # o que falhou continua na fila, pra tentar de novo
    assert (fila / "UJV100" / "b_ruim.pdf").exists()
    assert any(nivel == "err" and "b_ruim.pdf" in msg for nivel, msg in linhas)


def test_erro_de_arquivo_nao_repete_no_log_a_cada_ciclo(tmp_path, monkeypatch):
    import rasterlink_hotfolder as modulo
    modulo._ultimo_erro_por_arquivo.clear()

    fila = tmp_path / "fila"
    hot = tmp_path / "hot"
    hot.mkdir()
    (fila / "UJV100").mkdir(parents=True)
    (fila / "UJV100" / "ruim.pdf").write_bytes(b"conteudo")

    def sempre_falha(origem, destino, *args, **kwargs):
        raise OSError("OneDrive indisponivel")

    monkeypatch.setattr(modulo.shutil, "copy2", sempre_falha)

    linhas = []
    for _ in range(3):
        vigiar_fila_uma_vez(pasta_fila=str(fila), maquinas={"UJV100": str(hot)},
                            logger=lambda n, m: linhas.append((n, m)))

    assert sum(1 for nivel, _ in linhas if nivel == "err") == 1


def test_arquivo_que_volta_a_funcionar_avisa_e_e_enviado(tmp_path, monkeypatch):
    """Falha de download do OneDrive passa sozinha — o vigia nunca desiste do arquivo."""
    import rasterlink_hotfolder as modulo
    modulo._ultimo_erro_por_arquivo.clear()

    fila = tmp_path / "fila"
    hot = tmp_path / "hot"
    hot.mkdir()
    (fila / "UJV100").mkdir(parents=True)
    (fila / "UJV100" / "arte.pdf").write_bytes(b"conteudo")

    copia_real = modulo.shutil.copy2
    tentativas = {"n": 0}

    def falha_so_na_primeira(origem, destino, *args, **kwargs):
        tentativas["n"] += 1
        if tentativas["n"] == 1:
            raise OSError("OneDrive ainda baixando")
        return copia_real(origem, destino, *args, **kwargs)

    monkeypatch.setattr(modulo.shutil, "copy2", falha_so_na_primeira)

    linhas = []
    vigiar_fila_uma_vez(pasta_fila=str(fila), maquinas={"UJV100": str(hot)},
                        logger=lambda n, m: linhas.append((n, m)))
    resultado = vigiar_fila_uma_vez(pasta_fila=str(fila), maquinas={"UJV100": str(hot)},
                                    logger=lambda n, m: linhas.append((n, m)))

    assert resultado["UJV100"]["enviados"] == ["arte.pdf"]
    assert (hot / "arte.pdf").exists()
    assert any(nivel == "ok" and "passou depois de falhar" in msg for nivel, msg in linhas)


# --- modo "uma passada e sai" (tarefa do Agendador na maquina do RIP) ---


def test_principal_uma_vez_faz_uma_passada_e_sai(tmp_path, monkeypatch):
    """
    O modo do Agendador NAO pode entrar em loop: a tarefa dispara de
    minuto em minuto e cada disparo tem que morrer sozinho.
    """
    import rasterlink_hotfolder as modulo

    chamadas = []

    # O dublê tem que devolver o MESMO tipo do verdadeiro (um dict por
    # máquina). Enquanto devolveu o None do list.append, principal_uma_
    # vez estourava em resultado.update(None) — e o teste continuava
    # passando, porque _rodar_protegido engole o erro e a contagem
    # acontece antes dele. Um teste que escondia a quebra que devia
    # denunciar (2026-09-07).
    def anotar(**kw):
        chamadas.append(kw)
        return {"UJV100": {"enviados": [], "ignorados": [], "falharam": []}}

    monkeypatch.setattr(modulo, "vigiar_fila_uma_vez", anotar)
    monkeypatch.setattr(modulo, "vigiar_fila", lambda **kw: pytest.fail("nao pode chamar o loop eterno"))
    monkeypatch.setattr(modulo, "CAMINHO_TRAVA", tmp_path / "trava.lock")
    monkeypatch.setattr(modulo, "CAMINHO_ESTADO_AVISOS", tmp_path / "avisos.json")

    modulo.principal_uma_vez()

    assert len(chamadas) == 1
    assert not modulo.CAMINHO_CRASH.exists(), "uma passada normal nao pode gerar arquivo de crash"


def test_aviso_de_erro_nao_repete_entre_passadas_separadas(tmp_path, monkeypatch):
    """
    A deduplicacao do log vivia so na memoria do processo. Com uma
    passada por minuto o processo morre a cada minuto: sem guardar o
    estado em disco, uma hot folder faltando por um fim de semana
    escreveria a mesma linha de erro umas 4.300 vezes.
    """
    import rasterlink_hotfolder as modulo
    monkeypatch.setattr(modulo, "CAMINHO_ESTADO_AVISOS", tmp_path / "avisos.json")

    fila = tmp_path / "fila"
    maquinas = {"QUEBRADA": str(tmp_path / "nao_existe")}

    linhas = []

    def uma_passada():
        # cada passada e um processo novo: memoria zerada, disco nao
        modulo._ultimo_erro_por_maquina.clear()
        modulo.carregar_estado_avisos()
        vigiar_fila_uma_vez(pasta_fila=str(fila), maquinas=maquinas,
                            logger=lambda n, m: linhas.append((n, m)))
        modulo.salvar_estado_avisos()

    for _ in range(3):
        uma_passada()

    assert sum(1 for nivel, _ in linhas if nivel == "err") == 1


def test_maquina_que_volta_a_funcionar_ainda_avisa_entre_passadas(tmp_path, monkeypatch):
    """Guardar o estado nao pode calar o aviso bom — o 'voltou a funcionar' tem que sobreviver igual."""
    import rasterlink_hotfolder as modulo
    monkeypatch.setattr(modulo, "CAMINHO_ESTADO_AVISOS", tmp_path / "avisos.json")

    fila = tmp_path / "fila"
    hot = tmp_path / "hot"
    linhas = []

    def uma_passada():
        modulo._ultimo_erro_por_maquina.clear()
        modulo.carregar_estado_avisos()
        vigiar_fila_uma_vez(pasta_fila=str(fila), maquinas={"UJV100": str(hot)},
                            logger=lambda n, m: linhas.append((n, m)))
        modulo.salvar_estado_avisos()

    uma_passada()
    hot.mkdir()
    uma_passada()

    assert any(nivel == "ok" and "voltou a funcionar" in msg for nivel, msg in linhas)


def test_estado_de_avisos_ilegivel_nao_derruba_a_passada(tmp_path, monkeypatch):
    """Arquivo de estado corrompido, no pior caso, repete uma linha de log — nunca para a fila."""
    import rasterlink_hotfolder as modulo
    caminho = tmp_path / "avisos.json"
    caminho.write_text("{ isso nao e json", encoding="utf-8")
    monkeypatch.setattr(modulo, "CAMINHO_ESTADO_AVISOS", caminho)

    modulo._ultimo_erro_por_maquina.clear()
    modulo.carregar_estado_avisos()  # nao pode estourar

    resultado = vigiar_fila_uma_vez(pasta_fila=str(tmp_path / "fila"),
                                    maquinas={"UJV100": str(tmp_path / "hot")},
                                    logger=lambda n, m: None)
    assert "erro" in resultado["UJV100"]


def test_segunda_passada_simultanea_desiste_em_vez_de_duplicar(tmp_path, monkeypatch):
    """
    Duas passadas ao mesmo tempo pegariam o MESMO arquivo e copiariam
    duas vezes pra hot folder — e ai o RasterLink cria job duplicado,
    que vira material impresso duas vezes.
    """
    import rasterlink_hotfolder as modulo
    monkeypatch.setattr(modulo, "CAMINHO_TRAVA", tmp_path / "trava.lock")

    pode, trava = modulo._travar_instancia_unica()
    assert pode
    try:
        assert modulo._rodar_protegido(lambda: pytest.fail("nao podia ter rodado")) is False
    finally:
        trava.close()


def test_erro_na_passada_vira_arquivo_de_crash_em_vez_de_sumir(tmp_path, monkeypatch):
    """Sem console (pythonw), um erro sem essa rede desaparece sem deixar rastro nenhum."""
    import rasterlink_hotfolder as modulo
    monkeypatch.setattr(modulo, "CAMINHO_TRAVA", tmp_path / "trava.lock")
    monkeypatch.setattr(modulo, "CAMINHO_ESTADO_AVISOS", tmp_path / "avisos.json")

    def estoura(**kw):
        raise RuntimeError("quebrou bem no comeco")

    monkeypatch.setattr(modulo, "vigiar_fila_uma_vez", estoura)
    modulo.principal_uma_vez()  # nao pode propagar: a tarefa do Agendador nao tem quem olhe

    # CAMINHO_CRASH ja vem desviado pra tmp_path pela fixture autouse
    crash = modulo.CAMINHO_CRASH.read_text(encoding="utf-8")
    assert "quebrou bem no comeco" in crash


def test_recusa_rodar_o_loop_de_dentro_do_onedrive(tmp_path, monkeypatch):
    r"""
    Aconteceu de verdade (2026-09-05, 18:59): dois cliques no .py dentro
    da pasta de deploy do OneDrive, na maquina do RIP. A trava mora AO
    LADO do script — de dentro do OneDrive ela cai numa pasta
    sincronizada, e aí o loop e a tarefa agendada (que roda de
    C:\RasterLink) travam em arquivos DIFERENTES, se acham sozinhos, e
    o RIP recebe o mesmo arquivo duas vezes.
    """
    import rasterlink_hotfolder as modulo

    falso = tmp_path / "OneDrive" / "UNYCOMUNICACAO" / "rasterlink_hotfolder.py"
    falso.parent.mkdir(parents=True)
    falso.write_text("", encoding="utf-8")
    monkeypatch.setattr(modulo, "__file__", str(falso))
    monkeypatch.setattr(modulo, "vigiar_fila", lambda **kw: pytest.fail("nao podia ter rodado"))

    with pytest.raises(SystemExit):
        modulo.principal()


def test_de_uma_pasta_local_o_loop_roda_normal(tmp_path, monkeypatch):
    import rasterlink_hotfolder as modulo

    local = tmp_path / "RasterLink" / "rasterlink_hotfolder.py"
    local.parent.mkdir(parents=True)
    local.write_text("", encoding="utf-8")
    monkeypatch.setattr(modulo, "__file__", str(local))

    rodou = []
    monkeypatch.setattr(modulo, "vigiar_fila", lambda **kw: rodou.append(True))
    modulo.principal()

    assert rodou == [True]


def test_resumo_da_passada_diz_o_que_aconteceu_em_cada_maquina():
    """
    Rodando na mao, uma passada com a fila vazia nao escrevia NADA e a
    pessoa ficava olhando pro prompt sem saber se tinha funcionado
    (aconteceu, 2026-09-05 19:37).
    """
    import datetime as dt
    from rasterlink_hotfolder import resumo_da_passada

    linhas = resumo_da_passada({
        "SWJ320A": {"enviados": ["a.pdf", "b.pdf"], "ignorados": [], "falharam": []},
        "UJV100": {"enviados": [], "ignorados": ["nota.zip"], "falharam": ["ruim.pdf"]},
        "QUEBRADA": {"enviados": [], "ignorados": [], "erro": "Hot folder nao encontrada"},
    }, agora=dt.datetime(2026, 9, 5, 19, 37, 0))

    texto = "\n".join(linhas)
    assert "19:37:00" in texto
    assert "SWJ320A: 2 enviado(s)" in texto
    assert "UJV100: 0 enviado(s), 1 falharam, 1 ignorados" in texto
    assert "QUEBRADA: PROBLEMA" in texto


def test_resumo_com_fila_vazia_ainda_diz_que_rodou():
    from rasterlink_hotfolder import resumo_da_passada

    linhas = resumo_da_passada({"SWJ320A": {"enviados": [], "ignorados": [], "falharam": []}})
    assert any("Passada concluída" in l for l in linhas)
    assert any("0 enviado(s)" in l for l in linhas)


def test_resumo_nunca_vai_pro_log(tmp_path, monkeypatch):
    """
    A tarefa roda 1.440 vezes por dia. Uma linha "passada ok" por minuto
    no log soterraria justamente o que a gente le quando a fila para.
    """
    import rasterlink_hotfolder as modulo

    monkeypatch.setattr(modulo, "vigiar_fila_uma_vez", lambda **kw: {"UJV100": {"enviados": [], "ignorados": [], "falharam": []}})
    monkeypatch.setattr(modulo, "_tem_saida", lambda: True)
    modulo.principal_uma_vez()

    assert not modulo.CAMINHO_LOG.exists(), "passada limpa nao pode escrever no log"


def test_sem_console_nao_tenta_escrever_na_tela(monkeypatch):
    """Com pythonw.exe sys.stdout e None — print() sozinho quebraria."""
    import rasterlink_hotfolder as modulo

    monkeypatch.setattr(modulo.sys, "stdout", None)
    assert modulo._tem_saida() is False
    modulo._falar("nao pode estourar")


# --- arquivo grande: o RIP nao pode ver arquivo pela metade ---


def test_arquivo_e_montado_fora_da_hot_folder_e_entra_por_rename(tmp_path, monkeypatch):
    """
    O RasterLink vigia a hot folder ATIVAMENTE. Escrevendo direto la
    dentro, ele enxerga o nome no primeiro byte e pode ripar um arquivo
    pela metade — com 45 MB passa batido, com 1,83 GB nao.

    O teste espia o que existe dentro da hot folder DURANTE a copia.
    """
    import rasterlink_hotfolder as modulo

    fila = tmp_path / "fila"
    hot = tmp_path / "MijCtrl" / "Hot" / "UJV100"
    hot.mkdir(parents=True)
    (fila / "UJV100").mkdir(parents=True)
    (fila / "UJV100" / "grande.pdf").write_bytes(b"x" * 5000)

    visto_durante = []
    copia_real = modulo.shutil.copy2

    def espiar(origem, destino, *args, **kwargs):
        visto_durante.append(sorted(p.name for p in hot.iterdir()))
        return copia_real(origem, destino, *args, **kwargs)

    monkeypatch.setattr(modulo.shutil, "copy2", espiar)
    monkeypatch.setattr(modulo.time, "sleep", lambda s: None)

    vigiar_fila_uma_vez(pasta_fila=str(fila), maquinas={"UJV100": str(hot)})

    assert visto_durante == [[]], "a hot folder tem que estar VAZIA enquanto o arquivo e montado"
    assert (hot / "grande.pdf").read_bytes() == b"x" * 5000, "e o arquivo inteiro aparece no fim"


def test_montagem_nao_sobra_quando_a_copia_falha(tmp_path, monkeypatch):
    """Passada morta no meio (limite de tempo da tarefa) nao pode deixar lixo pra tras."""
    import rasterlink_hotfolder as modulo

    fila = tmp_path / "fila"
    hot = tmp_path / "MijCtrl" / "Hot" / "UJV100"
    hot.mkdir(parents=True)
    (fila / "UJV100").mkdir(parents=True)
    (fila / "UJV100" / "grande.pdf").write_bytes(b"x" * 100)

    def morre_no_meio(origem, destino, *args, **kwargs):
        pathlib.Path(destino).write_bytes(b"pela metade")
        raise OSError("passada encerrada no meio da copia")

    monkeypatch.setattr(modulo.shutil, "copy2", morre_no_meio)
    monkeypatch.setattr(modulo.time, "sleep", lambda s: None)

    resultado = vigiar_fila_uma_vez(pasta_fila=str(fila), maquinas={"UJV100": str(hot)},
                                    logger=lambda n, m: None)

    assert resultado["UJV100"]["falharam"] == ["grande.pdf"]
    assert list(hot.iterdir()) == [], "nada pela metade dentro da hot folder"
    assert [p.name for p in hot.parent.iterdir() if p.is_file()] == [], "nem resto de montagem na pasta-mae"


def test_faxina_apaga_montagem_abandonada_antiga_e_poupa_a_recente(tmp_path):
    import datetime as dt
    from rasterlink_hotfolder import _limpar_montagens_abandonadas, _PREFIXO_MONTAGEM, _SUFIXO_MONTAGEM

    hot = tmp_path / "Hot" / "UJV100"
    hot.mkdir(parents=True)
    mae = hot.parent

    antiga = mae / f"{_PREFIXO_MONTAGEM}UJV100~velha.pdf{_SUFIXO_MONTAGEM}"
    recente = mae / f"{_PREFIXO_MONTAGEM}UJV100~agora.pdf{_SUFIXO_MONTAGEM}"
    alheio = mae / "arquivo_de_outra_pessoa.pdf"
    for p in (antiga, recente, alheio):
        p.write_bytes(b"x")
    velho = (dt.datetime.now() - dt.timedelta(hours=48)).timestamp()
    os.utime(antiga, (velho, velho))
    os.utime(alheio, (velho, velho))

    apagados = _limpar_montagens_abandonadas(hot, horas=6, logger=lambda n, m: None)

    assert apagados == [antiga.name]
    assert recente.exists(), "montagem recente pode ser de uma copia acontecendo AGORA"
    assert alheio.exists(), "so mexe no que tem a nossa marca"


# --- sinal de vida gravado pela maquina do RIP ---


def test_passada_deixa_sinal_de_vida_na_raiz_da_fila(tmp_path):
    from rasterlink_hotfolder import ler_sinal_de_vida

    fila = tmp_path / "fila"
    hot = tmp_path / "hot"
    hot.mkdir()
    (fila / "UJV100").mkdir(parents=True)

    vigiar_fila_uma_vez(pasta_fila=str(fila), maquinas={"UJV100": str(hot)}, logger=lambda n, m: None)

    sinal = ler_sinal_de_vida(str(fila))
    assert sinal is not None
    assert sinal["idade_minutos"] < 1
    assert sinal["maquinas"] == {"UJV100": None}


def test_sinal_guarda_a_maquina_que_o_vigia_nao_conseguiu_atender(tmp_path):
    from rasterlink_hotfolder import ler_sinal_de_vida

    fila = tmp_path / "fila"
    vigiar_fila_uma_vez(pasta_fila=str(fila), maquinas={"UJV100": str(tmp_path / "nao_existe")},
                        logger=lambda n, m: None)

    sinal = ler_sinal_de_vida(str(fila))
    assert "Hot folder" in sinal["maquinas"]["UJV100"]


def test_sinal_nao_e_reescrito_a_cada_passada(tmp_path):
    """
    Seriam 1.440 gravacoes por dia numa pasta sincronizada, na maquina
    cujo OneDrive e justamente o ponto fraco.
    """
    import rasterlink_hotfolder as modulo

    fila = tmp_path / "fila"
    hot = tmp_path / "hot"
    hot.mkdir()
    maquinas = {"UJV100": str(hot)}

    vigiar_fila_uma_vez(pasta_fila=str(fila), maquinas=maquinas, logger=lambda n, m: None)
    caminho = modulo.caminho_do_sinal(str(fila))
    primeiro = caminho.read_text(encoding="utf-8")

    vigiar_fila_uma_vez(pasta_fila=str(fila), maquinas=maquinas, logger=lambda n, m: None)
    assert caminho.read_text(encoding="utf-8") == primeiro, "passada logo em seguida nao regrava"


def test_maquina_que_quebrou_fura_a_espera_e_grava_na_hora(tmp_path):
    """Hot folder sumindo e noticia — nao pode esperar 5 minutos pra aparecer na tela."""
    import rasterlink_hotfolder as modulo

    fila = tmp_path / "fila"
    hot = tmp_path / "hot"
    hot.mkdir()

    vigiar_fila_uma_vez(pasta_fila=str(fila), maquinas={"UJV100": str(hot)}, logger=lambda n, m: None)
    hot.rmdir()
    vigiar_fila_uma_vez(pasta_fila=str(fila), maquinas={"UJV100": str(hot)}, logger=lambda n, m: None)

    sinal = modulo.ler_sinal_de_vida(str(fila))
    assert "Hot folder" in sinal["maquinas"]["UJV100"]


def test_sinal_nao_atrapalha_a_varredura_da_fila(tmp_path):
    """O arquivo de sinal mora na RAIZ da fila — nao pode virar 'pasta desconhecida' nem arquivo pra enviar."""
    fila = tmp_path / "fila"
    hot = tmp_path / "hot"
    hot.mkdir()
    (fila / "UJV100").mkdir(parents=True)

    linhas = []
    vigiar_fila_uma_vez(pasta_fila=str(fila), maquinas={"UJV100": str(hot)},
                        logger=lambda n, m: linhas.append((n, m)))
    resultado = vigiar_fila_uma_vez(pasta_fila=str(fila), maquinas={"UJV100": str(hot)},
                                    logger=lambda n, m: linhas.append((n, m)))

    assert resultado["UJV100"]["enviados"] == []
    assert not any("_sinal_de_vida" in msg for _, msg in linhas)


def test_falha_ao_gravar_o_sinal_nao_derruba_a_passada(tmp_path, monkeypatch):
    import rasterlink_hotfolder as modulo

    fila = tmp_path / "fila"
    hot = tmp_path / "hot"
    hot.mkdir()
    (fila / "UJV100").mkdir(parents=True)
    (fila / "UJV100" / "arte.pdf").write_bytes(b"conteudo")
    monkeypatch.setattr(modulo.time, "sleep", lambda s: None)

    def sem_gravar(*a, **kw):
        raise OSError("disco cheio")

    monkeypatch.setattr(modulo.os, "replace", sem_gravar)

    resultado = vigiar_fila_uma_vez(pasta_fila=str(fila), maquinas={"UJV100": str(hot)},
                                    logger=lambda n, m: None)
    assert resultado["UJV100"]["falharam"] == ["arte.pdf"] or resultado["UJV100"]["enviados"] == ["arte.pdf"]
    assert modulo.ler_sinal_de_vida(str(fila)) is None


# ---------- postos: cada vigia cuida so das maquinas dele ----------
#
# As hot folders nao estao todas no mesmo PC (2026-09-07): as duas
# Mimaki sao atendidas pelo RasterLink7 na maquina do RIP, e a DOCAN
# pelo SAi Production Manager na maquina principal. Sem separar por
# posto, o vigia do RIP procuraria a pasta da DOCAN do lado errado e
# reclamaria dela de minuto em minuto — e o arquivo mandado pra DOCAN
# ficaria encalhado esperando um vigia que nunca vem.

def _duas_maquinas(hot_rip, hot_sai):
    return {
        "UJV100": {"hot_folder": str(hot_rip), "posto": rl_hf.POSTO_RIP},
        "DOCAN": {"hot_folder": str(hot_sai), "posto": rl_hf.POSTO_SAI},
    }


def test_vigia_de_um_posto_nao_atende_maquina_do_outro(tmp_path):
    fila = tmp_path / "fila"
    hot_rip = tmp_path / "hot_rip"
    hot_rip.mkdir()
    (fila / "UJV100").mkdir(parents=True)
    (fila / "DOCAN").mkdir(parents=True)

    # a hot folder do posto 'sai' nem existe deste lado, de proposito
    maquinas = _duas_maquinas(hot_rip, tmp_path / "hot_sai_que_so_existe_no_outro_pc")

    resultado = vigiar_fila_uma_vez(pasta_fila=str(fila), maquinas=maquinas,
                                    logger=lambda n, m: None, posto=rl_hf.POSTO_RIP)

    assert list(resultado) == ["UJV100"]
    assert "erro" not in resultado["UJV100"]


def test_pasta_de_maquina_do_outro_posto_nao_vira_reclamacao(tmp_path):
    """
    A pasta da DOCAN dentro da fila e legitima e tem dono — so que o
    dono e o outro vigia. Acusa-la de nome errado seria acusar de errado
    o que esta certo, todo minuto, no log que a gente le quando a fila
    para de verdade.
    """
    fila = tmp_path / "fila"
    hot_rip = tmp_path / "hot_rip"
    hot_rip.mkdir()
    (fila / "UJV100").mkdir(parents=True)
    (fila / "DOCAN").mkdir(parents=True)

    avisos = []
    vigiar_fila_uma_vez(
        pasta_fila=str(fila), maquinas=_duas_maquinas(hot_rip, tmp_path / "nao_existe"),
        logger=lambda nivel, msg: avisos.append((nivel, msg)), posto=rl_hf.POSTO_RIP,
    )

    assert not [m for n, m in avisos if "DOCAN" in m], f"reclamou da DOCAN a toa: {avisos}"


def test_pasta_que_nao_e_de_maquina_nenhuma_continua_sendo_avisada(tmp_path):
    """A separacao por posto nao pode calar o aviso que ja existia."""
    fila = tmp_path / "fila"
    hot_rip = tmp_path / "hot_rip"
    hot_rip.mkdir()
    (fila / "UJV100").mkdir(parents=True)
    (fila / "UJV 100 UNY CVV").mkdir(parents=True)   # nome digitado errado

    avisos = []
    vigiar_fila_uma_vez(
        pasta_fila=str(fila), maquinas=_duas_maquinas(hot_rip, tmp_path / "nao_existe"),
        logger=lambda nivel, msg: avisos.append((nivel, msg)), posto=rl_hf.POSTO_RIP,
    )

    assert [m for n, m in avisos if "UJV 100 UNY CVV" in m]


def test_hot_folder_sumida_do_proprio_posto_continua_sendo_erro_alto(tmp_path):
    """
    Pular em silencio so vale pra maquina de OUTRO posto. A do posto
    daqui que sumiu (RasterLink reinstalado, Favorito renomeado) tem que
    gritar — foi pra isso que o aviso por maquina foi feito.
    """
    fila = tmp_path / "fila"
    maquinas = _duas_maquinas(tmp_path / "hot_rip_que_sumiu", tmp_path / "hot_sai")

    resultado = vigiar_fila_uma_vez(pasta_fila=str(fila), maquinas=maquinas,
                                    logger=lambda n, m: None, posto=rl_hf.POSTO_RIP)

    assert "Hot folder" in resultado["UJV100"]["erro"]


def test_maquina_sem_posto_declarado_e_do_posto_do_rip(tmp_path):
    """
    Entrada antiga (so o caminho da hot folder em texto) tem que
    continuar valendo sem alteracao nenhuma: e o formato que a maquina
    do RIP ja tem instalado.
    """
    hot = tmp_path / "hot"
    hot.mkdir()
    so_o_caminho = {"UJV100": str(hot)}

    assert rl_hf.maquinas_do_posto(rl_hf.POSTO_RIP, so_o_caminho) == so_o_caminho
    assert rl_hf.maquinas_do_posto(rl_hf.POSTO_SAI, so_o_caminho) == {}


def test_posto_sem_nenhuma_maquina_reclama_em_vez_de_rodar_calado(tmp_path):
    hot = tmp_path / "hot"
    hot.mkdir()
    with pytest.raises(RuntimeError, match="posto"):
        vigiar_fila_uma_vez(pasta_fila=str(tmp_path / "fila"), maquinas={"UJV100": str(hot)},
                            logger=lambda n, m: None, posto=rl_hf.POSTO_SAI)


def test_cada_posto_deixa_o_sinal_de_vida_dele(tmp_path):
    """
    Um sinal so, gravado pelos dois, se apagaria a cada ciclo: cada
    vigia escreve apenas as maquinas dele, entao o estado nunca bateria
    com o anterior e a espera de 5 minutos deixaria de valer — viraria
    uma gravacao por minuto de cada lado, numa pasta sincronizada.
    """
    fila = tmp_path / "fila"
    hot_rip = tmp_path / "hot_rip"
    hot_sai = tmp_path / "hot_sai"
    hot_rip.mkdir()
    hot_sai.mkdir()
    maquinas = _duas_maquinas(hot_rip, hot_sai)

    vigiar_fila_uma_vez(pasta_fila=str(fila), maquinas=maquinas,
                        logger=lambda n, m: None, posto=rl_hf.POSTO_RIP)
    vigiar_fila_uma_vez(pasta_fila=str(fila), maquinas=maquinas,
                        logger=lambda n, m: None, posto=rl_hf.POSTO_SAI)

    do_rip = rl_hf.ler_sinal_de_vida(str(fila), posto=rl_hf.POSTO_RIP)
    do_sai = rl_hf.ler_sinal_de_vida(str(fila), posto=rl_hf.POSTO_SAI)

    assert do_rip["maquinas"] == {"UJV100": None}, "o vigia da DOCAN apagou o sinal do RIP"
    assert do_sai["maquinas"] == {"DOCAN": None}


def test_sinal_do_rip_continua_no_arquivo_de_sempre(tmp_path):
    """
    E o nome que a tarefa ja agendada grava e que as telas ja leem —
    trocar o nome cegaria a tela de envio sem ninguem perceber.
    """
    caminho = rl_hf.caminho_do_sinal(tmp_path, posto=rl_hf.POSTO_RIP)
    assert caminho.name == rl_hf.NOME_ARQUIVO_SINAL
    assert rl_hf.caminho_do_sinal(tmp_path).name == rl_hf.NOME_ARQUIVO_SINAL
    assert rl_hf.caminho_do_sinal(tmp_path, posto=rl_hf.POSTO_SAI).name != rl_hf.NOME_ARQUIVO_SINAL


def test_sem_argumento_o_posto_e_o_do_rip():
    """
    A tarefa do Agendador na maquina do RIP nao passa argumento nenhum e
    tem que continuar identica depois de receber esta versao.
    """
    assert rl_hf.posto_pedido(["rasterlink_hotfolder.py", "--uma-vez"]) == rl_hf.POSTO_RIP


def test_posto_e_lido_das_duas_formas_de_escrever():
    assert rl_hf.posto_pedido(["x.py", "--posto", "sai"]) == rl_hf.POSTO_SAI
    assert rl_hf.posto_pedido(["x.py", "--posto=sai"]) == rl_hf.POSTO_SAI
    assert rl_hf.posto_pedido(["x.py", "--posto=SAI"]) == rl_hf.POSTO_SAI


def test_docan_esta_cadastrada_com_a_largura_util_e_nao_a_da_midia():
    """
    A midia e de 5,20 m; quem imprime sao 5,00 (BYHX, Media/Width =
    5000.00 mm). Cadastrar 5,20 aqui faria o giro automatico deixar
    passar uma arte que a maquina corta na borda.
    """
    hot, largura = rl_hf._config_maquina(rl_hf.MAQUINAS["DOCAN"])
    assert largura == 5.00
    assert "SAi" in hot, "a hot folder da DOCAN e o Setup do SAi, nao uma pasta inventada"
    assert rl_hf._posto_da_maquina(rl_hf.MAQUINAS["DOCAN"]) == rl_hf.POSTO_SAI
    for mimaki in ("UJV 100 UNY CV", "SWJ320A"):
        assert rl_hf._posto_da_maquina(rl_hf.MAQUINAS[mimaki]) == rl_hf.POSTO_RIP


# ---------- o bilhete do rolo ----------
#
# A DOCAN roda dois rolos (3,20 e 5,00) e qual esta montado muda a
# largura util DAQUELE trabalho. Quem indica e o usuario na tela; o
# numero viaja num bilhete ao lado da arte, porque a fila so carrega
# arquivos e o nome da arte nao pode ser sujo com isso — ele vira linha
# no documento do cliente e no relatorio diario.

def test_o_rolo_escolhido_viaja_num_bilhete_ao_lado_da_arte(tmp_path):
    origem = tmp_path / "arte.pdf"
    origem.write_bytes(b"conteudo")
    maquinas = {"DOCAN": {"hot_folder": str(tmp_path / "hot"), "rolos_m": (3.20, 5.00)}}

    destino = enviar_para_fila(origem, "DOCAN", pasta_fila=tmp_path / "fila",
                               maquinas=maquinas, rolo_m=3.20)

    assert rl_hf.ler_bilhete(destino) == {"rolo_m": 3.20}


def test_arte_sem_rolo_nao_ganha_bilhete(tmp_path):
    """As Mimaki tem uma largura so — bilhete ali seria arquivo a toa na fila."""
    origem = tmp_path / "arte.pdf"
    origem.write_bytes(b"conteudo")

    destino = enviar_para_fila(origem, "UJV100", pasta_fila=tmp_path / "fila",
                               maquinas={"UJV100": str(tmp_path / "hot")})

    assert not rl_hf.caminho_do_bilhete(destino).exists()
    assert rl_hf.ler_bilhete(destino) == {}


def test_bilhete_e_escrito_antes_da_arte(tmp_path, monkeypatch):
    """
    O vigia so age quando ve a ARTE. Se a arte chegasse primeiro, um
    ciclo poderia pega-la antes do bilhete e girar pela largura errada —
    mandando pra impressao uma peca mais larga que o material.
    """
    origem = tmp_path / "arte.pdf"
    origem.write_bytes(b"conteudo")
    maquinas = {"DOCAN": {"hot_folder": str(tmp_path / "hot"), "rolos_m": (3.20, 5.00)}}

    def copia_que_falha(*a, **kw):
        raise OSError("rede caiu no meio")

    monkeypatch.setattr(rl_hf.shutil, "copy2", copia_que_falha)

    with pytest.raises(OSError):
        enviar_para_fila(origem, "DOCAN", pasta_fila=tmp_path / "fila",
                         maquinas=maquinas, rolo_m=3.20)

    # a arte nem chegou, mas o bilhete ja estava la: essa e a ordem certa
    fila_docan = tmp_path / "fila" / "DOCAN"
    assert not (fila_docan / "arte.pdf").exists()
    assert rl_hf.caminho_do_bilhete(fila_docan / "arte.pdf").exists()


def test_vigia_gira_pela_largura_do_rolo_e_nao_pela_da_maquina(tmp_path, monkeypatch):
    """
    Numa DOCAN cadastrada com 5,00 mas rodando o rolo de 3,20, uma arte
    de 3,90x0,95 TEM que girar. Girando pelos 5,00 do cadastro ela
    passaria reta e sairia cortada na borda do material.
    """
    monkeypatch.setattr(rl_hf.time, "sleep", lambda s: None)
    fila = tmp_path / "fila"
    (fila / "DOCAN").mkdir(parents=True)
    hot = tmp_path / "hot"
    hot.mkdir()
    arte = fila / "DOCAN" / "arte.pdf"
    _pdf_de(arte, largura_cm=390, altura_cm=95)
    rl_hf._escrever_bilhete(arte, {"rolo_m": 3.20})

    maquinas = {"DOCAN": {"hot_folder": str(hot), "largura_util_m": 5.00,
                          "rolos_m": (3.20, 5.00)}}
    vigiar_fila_uma_vez(pasta_fila=str(fila), maquinas=maquinas, logger=lambda n, m: None)

    assert _tamanho_cm(hot / "arte.pdf") == (95, 390), "devia girar pelo rolo de 3,20"


def test_sem_bilhete_o_vigia_usa_a_largura_da_maquina(tmp_path, monkeypatch):
    """A mesma arte, sem bilhete, cabe nos 5,00 da DOCAN e passa reta."""
    monkeypatch.setattr(rl_hf.time, "sleep", lambda s: None)
    fila = tmp_path / "fila"
    (fila / "DOCAN").mkdir(parents=True)
    hot = tmp_path / "hot"
    hot.mkdir()
    _pdf_de(fila / "DOCAN" / "arte.pdf", largura_cm=390, altura_cm=95)

    maquinas = {"DOCAN": {"hot_folder": str(hot), "largura_util_m": 5.00,
                          "rolos_m": (3.20, 5.00)}}
    vigiar_fila_uma_vez(pasta_fila=str(fila), maquinas=maquinas, logger=lambda n, m: None)

    assert _tamanho_cm(hot / "arte.pdf") == (390, 95)


def test_bilhete_sai_da_fila_junto_com_a_arte(tmp_path, monkeypatch):
    """
    Bilhete que fica pra tras faz a PROXIMA arte de mesmo nome herdar o
    rolo desta — e sozinho ele nunca mais seria lido por ninguem.
    """
    monkeypatch.setattr(rl_hf.time, "sleep", lambda s: None)
    fila = tmp_path / "fila"
    (fila / "DOCAN").mkdir(parents=True)
    hot = tmp_path / "hot"
    hot.mkdir()
    arte = fila / "DOCAN" / "arte.pdf"
    _pdf_de(arte, largura_cm=100, altura_cm=100)
    rl_hf._escrever_bilhete(arte, {"rolo_m": 3.20})

    maquinas = {"DOCAN": {"hot_folder": str(hot), "largura_util_m": 5.00}}
    vigiar_fila_uma_vez(pasta_fila=str(fila), maquinas=maquinas, logger=lambda n, m: None)

    sobrou = [f.name for f in (fila / "DOCAN").iterdir() if f.is_file()]
    assert sobrou == [], f"sobrou lixo na fila: {sobrou}"


def test_bilhete_nao_conta_como_arquivo_ignorado(tmp_path, monkeypatch):
    """
    Contar o bilhete como 'ignorado' faria o resumo da passada dizer o
    dobro do que aconteceu — e quem le o resumo procura numero estranho.
    """
    monkeypatch.setattr(rl_hf.time, "sleep", lambda s: None)
    fila = tmp_path / "fila"
    (fila / "DOCAN").mkdir(parents=True)
    hot = tmp_path / "hot"
    hot.mkdir()
    arte = fila / "DOCAN" / "arte.pdf"
    _pdf_de(arte, largura_cm=100, altura_cm=100)
    rl_hf._escrever_bilhete(arte, {"rolo_m": 3.20})

    maquinas = {"DOCAN": {"hot_folder": str(hot), "largura_util_m": 5.00}}
    r = vigiar_fila_uma_vez(pasta_fila=str(fila), maquinas=maquinas, logger=lambda n, m: None)

    assert r["DOCAN"]["enviados"] == ["arte.pdf"]
    assert r["DOCAN"]["ignorados"] == []


def test_bilhete_ilegivel_nao_segura_a_arte(tmp_path, monkeypatch):
    """
    Detalhe nosso nunca pode virar arquivo represado: sem conseguir ler
    o bilhete, vale a largura da maquina e a arte segue.
    """
    monkeypatch.setattr(rl_hf.time, "sleep", lambda s: None)
    fila = tmp_path / "fila"
    (fila / "DOCAN").mkdir(parents=True)
    hot = tmp_path / "hot"
    hot.mkdir()
    arte = fila / "DOCAN" / "arte.pdf"
    _pdf_de(arte, largura_cm=100, altura_cm=100)
    rl_hf.caminho_do_bilhete(arte).write_text("isto nao e json", encoding="utf-8")

    maquinas = {"DOCAN": {"hot_folder": str(hot), "largura_util_m": 5.00}}
    r = vigiar_fila_uma_vez(pasta_fila=str(fila), maquinas=maquinas, logger=lambda n, m: None)

    assert r["DOCAN"]["enviados"] == ["arte.pdf"]
    assert (hot / "arte.pdf").exists()


def test_rolos_so_existem_em_quem_tem_rolo(tmp_path):
    assert rl_hf.rolos_da_maquina("DOCAN") == (3.20, 5.00)
    assert rl_hf.rolos_da_maquina("SWJ320A") == ()
    assert rl_hf.rolos_da_maquina("UJV 100 UNY CV") == ()
