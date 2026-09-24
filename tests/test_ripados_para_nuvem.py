"""
Testes do movedor do ripado da DOCAN pro OneDrive.

As constantes do modulo apontam pro Desktop e pro OneDrive DE VERDADE,
entao a fixture autouse desvia as duas. Ja aconteceu de teste apagar
estoque.json e sujar o registro de producao por causa disso; aqui o
estrago seria pior, porque este modulo MOVE arquivo de 14 GB.
"""
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import ripados_para_nuvem as rpn


@pytest.fixture(autouse=True)
def _isolar_pastas_reais(tmp_path, monkeypatch):
    monkeypatch.setattr(rpn, "PASTA_RIPADOS", tmp_path / "Ripados")
    monkeypatch.setattr(rpn, "PASTA_NUVEM", tmp_path / "nuvem" / "Para imprimir")
    # Sem isto cada teste que chama levar() dorme 20 segundos de verdade.
    monkeypatch.setattr(rpn.time, "sleep", lambda s: None)


def _ripado(pasta, nome, tamanho=1024):
    pasta.mkdir(parents=True, exist_ok=True)
    caminho = pasta / nome
    with open(caminho, "wb") as f:
        f.write(b"\0" * tamanho)
    return caminho


# ---------- o que tem pra levar ----------

def test_lista_so_os_ripados(tmp_path):
    pasta = tmp_path / "Ripados"
    _ripado(pasta, "arte.prt")
    _ripado(pasta, "anotacao.txt")
    _ripado(pasta, "arte.pdf")

    assert [c.name for c in rpn.listar()] == ["arte.prt"]


def test_lista_do_mais_antigo_pro_mais_novo(tmp_path):
    """
    Com quatro ou cinco na fila, quem ripou primeiro e quem esta
    esperando ha mais tempo do outro lado.
    """
    import os
    pasta = tmp_path / "Ripados"
    velho = _ripado(pasta, "velho.prt")
    novo = _ripado(pasta, "novo.prt")
    os.utime(velho, (1000, 1000))
    os.utime(novo, (2000, 2000))

    assert [c.name for c in rpn.listar()] == ["velho.prt", "novo.prt"]


def test_pasta_que_nao_existe_nao_quebra(tmp_path):
    assert rpn.listar() == []


# ---------- o teto de 20 GB ----------

def test_arquivo_dentro_do_limite_pode_ir(tmp_path):
    caminho = _ripado(tmp_path / "Ripados", "arte.prt", tamanho=5000)
    pode, motivo = rpn.conferir(caminho, limite_bytes=10000)
    assert pode is True and motivo is None


def test_arquivo_acima_do_limite_fica_e_avisa(tmp_path):
    """
    Nao apaga, nao esconde, nao tenta subir assim mesmo: fica onde esta e
    vira aviso. Quem decide o que fazer com um trabalho desse tamanho e
    uma pessoa.
    """
    caminho = _ripado(tmp_path / "Ripados", "gigante.prt", tamanho=20000)
    pode, motivo = rpn.conferir(caminho, limite_bytes=10000)

    assert pode is False
    assert "limite" in motivo
    assert caminho.exists(), "o arquivo grande nao pode sumir"


def test_o_limite_padrao_e_o_que_o_usuario_pediu():
    assert rpn.LIMITE_BYTES == 20 * 1024 ** 3


def test_arquivo_de_zero_byte_nao_vai(tmp_path):
    caminho = _ripado(tmp_path / "Ripados", "vazio.prt", tamanho=0)
    pode, motivo = rpn.conferir(caminho)
    assert pode is False and "0 byte" in motivo


# ---------- so vai o que parou de crescer ----------

def test_arquivo_ainda_crescendo_nao_e_levado(tmp_path, monkeypatch):
    """
    O .prt de 13,8 GB foi escrito por mais de dez minutos. Levar no meio
    disso manda meia arte pra maquina — e do outro lado ninguem tem como
    saber que veio pela metade.
    """
    caminho = _ripado(tmp_path / "Ripados", "crescendo.prt", tamanho=1000)

    # o RIP ainda escrevendo: o arquivo nunca fica do mesmo tamanho
    monkeypatch.setattr(rpn, "_arquivo_estavel", lambda c, espera_segundos=None: False)

    destino, motivo = rpn.levar(caminho)
    assert destino is None
    assert "sendo escrito" in motivo
    assert caminho.exists(), "continua na pasta pro proximo ciclo"


def test_arquivo_estavel_percebe_que_parou(tmp_path):
    caminho = _ripado(tmp_path / "Ripados", "pronto.prt", tamanho=1000)
    assert rpn._arquivo_estavel(caminho) is True


def test_arquivo_estavel_percebe_que_cresceu(tmp_path, monkeypatch):
    caminho = _ripado(tmp_path / "Ripados", "crescendo.prt", tamanho=1000)

    def crescer(_):
        with open(caminho, "ab") as f:
            f.write(b"\0" * 500)

    monkeypatch.setattr(rpn.time, "sleep", crescer)
    assert rpn._arquivo_estavel(caminho) is False


def test_arquivo_que_sumiu_no_meio_nao_e_dado_como_estavel(tmp_path, monkeypatch):
    caminho = _ripado(tmp_path / "Ripados", "some.prt", tamanho=1000)
    monkeypatch.setattr(rpn.time, "sleep", lambda s: caminho.unlink())
    assert rpn._arquivo_estavel(caminho) is False


# ---------- a entrega ----------

def test_levar_move_e_nao_copia(tmp_path):
    """
    Copiar 14 GB pra dentro de pasta sincronizada faria o OneDrive
    comecar a subir um arquivo pela metade. O rename e atomico: aparece
    inteiro ou nao aparece.
    """
    caminho = _ripado(tmp_path / "Ripados", "arte.prt", tamanho=2048)
    destino, motivo = rpn.levar(caminho)

    assert motivo is None
    assert destino.exists() and destino.stat().st_size == 2048
    assert not caminho.exists(), "duas copias de 14 GB no disco nao se sustentam"


def test_a_pasta_da_nuvem_e_criada_se_faltar(tmp_path):
    caminho = _ripado(tmp_path / "Ripados", "arte.prt")
    destino, motivo = rpn.levar(caminho)
    assert motivo is None and destino.parent.is_dir()


def test_nome_repetido_na_nuvem_nao_e_sobrescrito(tmp_path):
    """
    Sobrescrever poderia trocar um trabalho por outro no meio da subida —
    e do outro lado imprimiriam o errado sem desconfiar.
    """
    ja_la = tmp_path / "nuvem" / "Para imprimir" / "arte.prt"
    _ripado(ja_la.parent, "arte.prt", tamanho=9999)
    caminho = _ripado(tmp_path / "Ripados", "arte.prt", tamanho=2048)

    destino, motivo = rpn.levar(caminho)

    assert destino is None and "Já existe" in motivo
    assert ja_la.stat().st_size == 9999, "o que ja estava la nao foi tocado"
    assert caminho.exists()


def test_arquivo_grande_nao_e_movido(tmp_path):
    caminho = _ripado(tmp_path / "Ripados", "gigante.prt", tamanho=20000)
    destino, motivo = rpn.levar(caminho, limite_bytes=10000)

    assert destino is None and "limite" in motivo
    assert caminho.exists()
    assert not (tmp_path / "nuvem" / "Para imprimir" / "gigante.prt").exists()


# ---------- a fila inteira ----------

def test_leva_todos_os_que_podem(tmp_path):
    pasta = tmp_path / "Ripados"
    for nome in ("a.prt", "b.prt", "c.prt"):
        _ripado(pasta, nome, tamanho=1000)

    resultado = rpn.levar_todos()

    assert sorted(d.name for d in resultado["levados"]) == ["a.prt", "b.prt", "c.prt"]
    assert resultado["esperando"] == []


def test_um_travado_nao_prende_os_outros_atras(tmp_path):
    """
    Ja aconteceu na fila do RIP (2026-09-05): o setimo falhou e os cinco
    seguintes ficaram parados pra sempre, porque todo ciclo recomecava
    pelo mesmo arquivo ruim.
    """
    import os
    pasta = tmp_path / "Ripados"
    grande = _ripado(pasta, "grande.prt", tamanho=20000)
    pequeno = _ripado(pasta, "pequeno.prt", tamanho=1000)
    os.utime(grande, (1000, 1000))      # o problematico vem primeiro
    os.utime(pequeno, (2000, 2000))

    resultado = rpn.levar_todos(limite_bytes=10000)

    assert [d.name for d in resultado["levados"]] == ["pequeno.prt"]
    assert [c.name for c, _ in resultado["esperando"]] == ["grande.prt"]
    assert grande.exists()


def test_passada_sem_nada_nao_inventa_resultado(tmp_path):
    resultado = rpn.levar_todos()
    assert resultado == {"levados": [], "esperando": []}
    assert "nada pra levar" in "\n".join(rpn.resumo(resultado))


def test_resumo_diz_o_que_ficou_pra_tras(tmp_path):
    _ripado(tmp_path / "Ripados", "gigante.prt", tamanho=20000)
    texto = "\n".join(rpn.resumo(rpn.levar_todos(limite_bytes=10000)))
    assert "gigante.prt" in texto and "limite" in texto


# ---------- entrega entre discos diferentes ----------
#
# Desde 23/09/2026 o ripado mora no D: e o OneDrive no C:, entao
# os.replace falha e a entrega passa pela montagem. Os testes forcam
# esse caminho pelo erro do replace, em vez de exigir dois discos de
# verdade na maquina que roda a suite.

def _sem_replace_entre_discos(monkeypatch):
    """Faz os.replace recusar a travessia, como o Windows faz de verdade."""
    replace_real = rpn.os.replace

    def replace(origem, destino):
        if pathlib.Path(origem).name.startswith("~montando~"):
            return replace_real(origem, destino)  # rename local: esse funciona
        raise OSError(17, "The system cannot move the file to a different disk drive")

    monkeypatch.setattr(rpn.os, "replace", replace)


def test_entrega_acontece_mesmo_em_discos_diferentes(tmp_path, monkeypatch):
    _sem_replace_entre_discos(monkeypatch)
    origem = _ripado(tmp_path / "Ripados", "arte.prt")

    destino, motivo = rpn.levar(origem)

    assert motivo is None
    assert destino.exists(), "o ripado tem que chegar mesmo atravessando disco"
    assert not origem.exists(), "a origem sai do D: pra nao encher o disco"


def test_o_nome_final_so_aparece_depois_de_completo(tmp_path, monkeypatch):
    """
    O OneDrive nao pode ver um .prt de 14 GB ainda sendo escrito: a copia
    vai pra um nome provisorio e so entra por rename local.
    """
    _sem_replace_entre_discos(monkeypatch)
    origem = _ripado(tmp_path / "Ripados", "arte.prt")

    copiados = []
    copy2_real = rpn.shutil.copy2

    def copy2(de, para):
        copiados.append(pathlib.Path(para).name)
        return copy2_real(de, para)

    monkeypatch.setattr(rpn.shutil, "copy2", copy2)
    rpn.levar(origem)

    assert copiados == ["~montando~arte.prt.parcial"], \
        "a copia nunca pode ir direto pro nome final"


def test_montagem_nao_fica_pra_tras(tmp_path, monkeypatch):
    _sem_replace_entre_discos(monkeypatch)
    origem = _ripado(tmp_path / "Ripados", "arte.prt")
    destino, _ = rpn.levar(origem)

    restos = [f.name for f in destino.parent.iterdir() if "montando" in f.name]
    assert restos == []


def test_copia_que_falha_nao_deixa_lixo_nem_perde_a_origem(tmp_path, monkeypatch):
    """Um .prt de 14 GB pela metade nao pode ficar ocupando a pasta sincronizada."""
    _sem_replace_entre_discos(monkeypatch)
    origem = _ripado(tmp_path / "Ripados", "arte.prt")
    monkeypatch.setattr(rpn.shutil, "copy2",
                        lambda de, para: (_ for _ in ()).throw(OSError("disco cheio")))

    destino, motivo = rpn.levar(origem)

    assert destino is None
    assert "disco cheio" in motivo
    assert origem.exists(), "falhar a entrega nao pode perder o trabalho ripado"
    assert not list(rpn.PASTA_NUVEM.glob("*montando*"))


# ---------- as duas extensoes ----------

def test_prn_conta_tanto_quanto_prt(tmp_path):
    """
    O SAi cospe as duas: o teste de 07/09 saiu .prt e o de 23/09, na
    mesma maquina, saiu .prn - 9,4 GB que o codigo ignorava por procurar
    so uma extensao.
    """
    pasta = tmp_path / "Ripados"
    _ripado(pasta, "arte.prt")
    _ripado(pasta, "outra.prn")
    _ripado(pasta, "anotacao.txt")

    assert sorted(f.name for f in rpn.listar(pasta)) == ["arte.prt", "outra.prn"]


def test_prn_maiusculo_tambem_conta(tmp_path):
    pasta = tmp_path / "Ripados"
    _ripado(pasta, "ARTE.PRN")
    assert [f.name for f in rpn.listar(pasta)] == ["ARTE.PRN"]


# ---------- uma pasta por maquina ----------

def test_cada_maquina_tem_sua_pasta_de_saida(tmp_path):
    """
    Duas DOCAN cuspindo na mesma pasta misturaria os ripados, e do outro
    lado ninguem saberia qual trabalho e de qual impressora.
    """
    r5200 = rpn.pasta_da_maquina("DOCAN R5200", tmp_path)
    h2525 = rpn.pasta_da_maquina("DOCAN H2525", tmp_path)
    assert r5200 != h2525
    assert r5200.parent == tmp_path


def test_a_pasta_da_nuvem_espelha_a_da_saida(tmp_path):
    assert rpn.pasta_na_nuvem("DOCAN H2525", tmp_path).name == \
           rpn.pasta_da_maquina("DOCAN H2525", tmp_path).name


def test_so_as_maquinas_do_sai_ripam_aqui():
    """As Mimaki ripam no OUTRO PC: o caminho delas nao passa por aqui."""
    nomes = rpn.maquinas_do_sai()
    assert "DOCAN R5200" in nomes and "DOCAN H2525" in nomes
    assert not [n for n in nomes if "UJV" in n or "SWJ" in n]


def test_garantir_pastas_cria_a_de_cada_maquina(tmp_path):
    """
    A porta do setup NAO cria pasta: destino faltando faz o trabalho
    morrer depois de ripado, com "Nao foi possivel abrir a porta".
    """
    criadas = rpn.garantir_pastas(tmp_path)
    assert set(criadas) == set(rpn.maquinas_do_sai())
    assert all(p.is_dir() for p in criadas.values())


def test_o_ripado_de_cada_maquina_vai_pra_pasta_dela(tmp_path):
    rpn.garantir_pastas(tmp_path / "saida")
    _ripado(rpn.pasta_da_maquina("DOCAN H2525", tmp_path / "saida"), "chapa.prn")

    resultado = rpn.levar_de_todas_as_maquinas(
        raiz_ripados=tmp_path / "saida", raiz_nuvem=tmp_path / "nuvem",
        esperar_estavel=False)

    assert [d.name for d in resultado["DOCAN H2525"]["levados"]] == ["chapa.prn"]
    assert resultado["DOCAN R5200"]["levados"] == []
    assert (tmp_path / "nuvem" / "DOCAN H2525" / "chapa.prn").exists()
    assert not (tmp_path / "nuvem" / "DOCAN R5200").exists()
