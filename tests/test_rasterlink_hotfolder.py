import pytest

import rasterlink_hotfolder as rl_hf
from rasterlink_hotfolder import enviar_para_fila, logger_arquivo, vigiar_fila, vigiar_fila_uma_vez

MAQUINAS_TESTE = {"UJV100": None}  # caminho da hot folder preenchido por teste, via tmp_path


def _maquinas(hot_folder):
    return {"UJV100": str(hot_folder)}


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


def test_vigiar_fila_uma_vez_hot_folder_inexistente_da_erro_claro(tmp_path):
    with pytest.raises(FileNotFoundError):
        vigiar_fila_uma_vez(
            pasta_fila=str(tmp_path / "fila"),
            maquinas=_maquinas(tmp_path / "nao_existe"),
        )


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
