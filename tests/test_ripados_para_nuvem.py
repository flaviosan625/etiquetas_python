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
