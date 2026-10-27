"""
Testes do controle de material em produção (`material_producao.py`).

O módulo nasceu sem teste nenhum e grava registro PERMANENTE: cada peça
que entra em PRONTOS vira linha em `_controle_producao/movimentos.jsonl`,
e é dessa linha que sai o consumo e o custo por cliente. O que ele move é
arte de trabalho real, dentro da pasta de produção do cliente — a mesma
pasta que a regra do projeto proíbe tocar sem pedido explícito.

O config vem montado na mão, nunca de `config.carregar_config()`: o
`config.json` é do usuário e muda sem commit (preço mora lá). Teste que
parte do arquivo vivo prova uma coisa hoje e outra amanhã — foi assim que
a tabela de acrílicos de 10/10/2026 derrubou o teste do preço da OS.

A pasta de estado (`caminhos.PASTA_PROGRAMA / _controle_producao`) é
isolada pelo `conftest.py` da suíte. Aqui isolamos também a raiz dos
CLIENTES, porque `listar_vinculos` chama `clientes.listar()` e sem isso o
teste leria as pastas de cliente de verdade no OneDrive.
"""
import json
import os

import pytest

import caminhos
import material_producao as mp


CONFIG = {
    "materiais": {"LONA": {"tipo": "rolo", "largura_cm": 320, "variantes": []}},
    "sinonimos_categoria": {},
    "materiais_compostos": {},
    "typos_unidade": {},
}


@pytest.fixture(autouse=True)
def clientes_de_mentira(tmp_path, monkeypatch):
    """Sem isto, `listar_vinculos` leria os clientes reais do OneDrive."""
    raiz = tmp_path / "Recebimento de Artes"
    raiz.mkdir()
    monkeypatch.setattr(caminhos, "RECEBIMENTO_DE_ARTES", raiz)
    return raiz


def _producao(tmp_path, *arquivos):
    """Uma pasta de produção com as artes pedidas, caminho relativo e tudo."""
    raiz = tmp_path / "EVENTO" / "PRODUCAO RJ"
    raiz.mkdir(parents=True)
    for relativo in arquivos:
        alvo = raiz / relativo
        alvo.parent.mkdir(parents=True, exist_ok=True)
        alvo.write_bytes(b"arte de mentira")
    return raiz


# ------------------------------------------------- a pasta que se aceita

def test_endereco_que_nao_e_pasta_do_computador_e_recusado(tmp_path):
    """
    Link de nuvem não é pasta: o módulo move arquivo com `os.rename`, que
    só funciona em caminho de verdade. Recusar na entrada dá mensagem que
    se entende, em vez de erro de sistema no meio do lote.
    """
    for endereco in ("", "   ", "https://drive.google.com/x", "pasta/relativa"):
        with pytest.raises(mp.ErroProducao):
            mp.validar_pasta(endereco)


def test_a_propria_pasta_prontos_nao_pode_ser_a_raiz(tmp_path):
    """
    PRONTOS é o DESTINO. Vinculada como raiz, tudo dentro dela já contaria
    como produzido e não haveria pra onde mover — o controle inteiro
    viraria uma lista de peças prontas que nunca saíram de lugar.
    """
    prontos = tmp_path / "PRONTOS"
    prontos.mkdir()
    with pytest.raises(mp.ErroProducao):
        mp.validar_pasta(prontos)


def test_pasta_que_nao_existe_avisa_em_vez_de_quebrar(tmp_path):
    with pytest.raises(mp.ErroProducao):
        mp.validar_pasta(tmp_path / "nao existe")


# ------------------------------------------------------- vincular pastas

def test_vincular_a_mesma_pasta_duas_vezes_nao_duplica(tmp_path):
    """
    Pasta vinculada duas vezes apareceria duas vezes na tela e contaria o
    consumo em dobro no custo do cliente.
    """
    raiz = _producao(tmp_path)

    primeiro = mp.vincular(raiz, cliente="ASICS", trabalho="PRODUCAO RJ")
    segundo = mp.vincular(raiz, cliente="ASICS", trabalho="PRODUCAO RJ")

    assert primeiro["id"] == segundo["id"]
    assert len(mp.listar_vinculos()) == 1


def test_pasta_dentro_de_outra_ja_vinculada_e_recusada(tmp_path):
    """
    Com a mãe e a filha vinculadas, a mesma arte entra no inventário das
    duas — e o cliente recebe a conta do material duas vezes.
    """
    raiz = _producao(tmp_path, "UV/1UN LONA 1.00X2.00M_A.pdf")
    mp.vincular(raiz, cliente="ASICS", trabalho="PRODUCAO RJ")

    with pytest.raises(mp.ErroProducao):
        mp.vincular(raiz / "UV", cliente="ASICS", trabalho="UV")
    with pytest.raises(mp.ErroProducao):
        mp.vincular(raiz.parent, cliente="ASICS", trabalho="EVENTO")


def test_cadastro_estragado_preserva_o_arquivo(tmp_path):
    """
    Cadastro ilegível não pode ser reescrito do zero: o que está lá é o
    vínculo das pastas de trabalho em andamento. Avisa e preserva.
    """
    mp.pasta_estado().mkdir(parents=True, exist_ok=True)
    arquivo = mp.pasta_estado() / "pastas.json"
    arquivo.write_text("{isto não é json", encoding="utf-8")

    with pytest.raises(mp.ErroProducao):
        mp.listar_vinculos()
    assert arquivo.read_text(encoding="utf-8") == "{isto não é json"


# ---------------------------------------------------------- o inventário

def test_inventario_ignora_documento_e_arquivo_de_sistema(tmp_path):
    """
    A OS, a cópia de CUSTOS e o checklist moram na mesma pasta das artes.
    Contados como peça, viram material que ninguém imprimiu no consumo do
    cliente.
    """
    raiz = _producao(
        tmp_path,
        "1UN LONA 1.00X2.00M_ARTE.pdf",
        "OS - ASICS.pdf",
        "CUSTOS - ASICS.pdf",
        "CHECKLIST ASICS.pdf",
        "_rascunho.pdf",
        "anotacao.txt",
    )
    vinculo = mp.vincular(raiz, cliente="ASICS", trabalho="PRODUCAO RJ")

    itens = mp.inventariar(vinculo, CONFIG)

    assert [i["arquivo"] for i in itens] == ["1UN LONA 1.00X2.00M_ARTE.pdf"]


def test_arquivo_em_prontos_conta_como_produzido(tmp_path):
    """PRONTOS é a fonte do status — é o que ele arrasta quando termina."""
    raiz = _producao(
        tmp_path,
        "1UN LONA 1.00X2.00M_ESPERANDO.pdf",
        "PRONTOS/1UN LONA 1.00X2.00M_FEITA.pdf",
    )
    vinculo = mp.vincular(raiz, cliente="ASICS", trabalho="PRODUCAO RJ")

    por_nome = {i["arquivo"]: i for i in mp.inventariar(vinculo, CONFIG)}

    assert por_nome["1UN LONA 1.00X2.00M_FEITA.pdf"]["pronto"] is True
    assert por_nome["1UN LONA 1.00X2.00M_ESPERANDO.pdf"]["pronto"] is False


def test_o_que_o_nome_nao_diz_sai_como_aviso(tmp_path):
    """
    Medida e material saem do NOME do arquivo, e o que falta tem que
    aparecer na tela: peça sem medida não entra no m² do cliente, e
    descobrir isso depois de produzir é tarde.
    """
    raiz = _producao(tmp_path, "arte sem especificacao nenhuma.pdf")
    vinculo = mp.vincular(raiz, cliente="ASICS", trabalho="PRODUCAO RJ")

    item, = mp.inventariar(vinculo, CONFIG)

    assert "Material não identificado" in item["avisos"]
    assert "Medida não identificada no nome" in item["avisos"]
    assert "Quantidade presumida: 1 unidade" in item["avisos"]


# ------------------------------------------- mover pra PRONTOS, com prova

def _um_item(tmp_path, *arquivos):
    raiz = _producao(tmp_path, *arquivos)
    vinculo = mp.vincular(raiz, cliente="ASICS", trabalho="PRODUCAO RJ")
    itens = [i for i in mp.inventariar(vinculo, CONFIG) if not i["pronto"]]
    return raiz, itens


def _historico():
    arquivo = mp.pasta_estado() / "movimentos.jsonl"
    if not arquivo.is_file():
        return []
    return [json.loads(l) for l in arquivo.read_text(encoding="utf-8").splitlines() if l.strip()]


def test_mover_registra_antes_de_mover_e_confirma_depois(tmp_path):
    """
    A linha 'solicitado' é escrita (e sincronizada) ANTES do movimento, e
    a 'concluido' depois. É o que impede peça de entrar em PRONTOS sem
    rastro: o registro é a comprovação de consumo do cliente, e arquivo
    movido sem linha é material que sai do estoque e não aparece em
    documento nenhum.
    """
    raiz, itens = _um_item(tmp_path, "1UN LONA 1.00X2.00M_ARTE.pdf")

    resultado = mp.mover_lote(itens)

    assert resultado["erros"] == []
    assert (raiz / "PRONTOS" / "1UN LONA 1.00X2.00M_ARTE.pdf").is_file()
    assert not (raiz / "1UN LONA 1.00X2.00M_ARTE.pdf").exists()
    assert [e["evento"] for e in _historico()] == ["solicitado", "concluido"]


def test_movimento_que_falha_deixa_a_prova_e_nao_perde_o_arquivo(tmp_path, monkeypatch):
    """
    Esta é a prova da ORDEM. Com o movimento falhando, a arte tem que
    continuar onde estava e o histórico tem que ter o 'solicitado' sem o
    'concluido' — é assim que se descobre, depois, uma peça que ficou no
    meio do caminho. Gravar depois de mover deixaria o movimento sem
    rastro justamente no caso em que o rastro importa.
    """
    raiz, itens = _um_item(tmp_path, "1UN LONA 1.00X2.00M_ARTE.pdf")
    monkeypatch.setattr(os, "rename", lambda *a, **k: (_ for _ in ()).throw(OSError("disco cheio")))

    resultado = mp.mover_lote(itens)

    assert resultado["movidos"] == []
    assert [e["arquivo"] for e in resultado["erros"]] == ["1UN LONA 1.00X2.00M_ARTE.pdf"]
    assert (raiz / "1UN LONA 1.00X2.00M_ARTE.pdf").is_file()
    assert [e["evento"] for e in _historico()] == ["solicitado"]


def test_nunca_sobrescreve_o_que_ja_esta_em_prontos(tmp_path):
    """
    Dois arquivos de mesmo nome são peças diferentes (refação, versão
    nova). Sobrescrever apagaria a arte que já estava aprovada, e o
    original não existe mais em lugar nenhum depois do movimento.
    """
    raiz, itens = _um_item(
        tmp_path,
        "1UN LONA 1.00X2.00M_ARTE.pdf",
        "PRONTOS/1UN LONA 1.00X2.00M_ARTE.pdf",
    )
    (raiz / "PRONTOS" / "1UN LONA 1.00X2.00M_ARTE.pdf").write_bytes(b"a que ja estava")

    resultado = mp.mover_lote(itens)

    assert resultado["movidos"] == []
    assert resultado["erros"]
    assert (raiz / "PRONTOS" / "1UN LONA 1.00X2.00M_ARTE.pdf").read_bytes() == b"a que ja estava"
    assert (raiz / "1UN LONA 1.00X2.00M_ARTE.pdf").is_file()


def test_arquivo_que_mudou_desde_a_selecao_nao_e_movido(tmp_path):
    """
    Entre listar e clicar, alguém pode reexportar a arte. Mover a nova
    como se fosse a conferida marcaria como produzida uma peça que ninguém
    olhou — a assinatura (tamanho + data) é o que segura isso.
    """
    raiz, itens = _um_item(tmp_path, "1UN LONA 1.00X2.00M_ARTE.pdf")
    (raiz / "1UN LONA 1.00X2.00M_ARTE.pdf").write_bytes(b"arte reexportada, outro tamanho")

    resultado = mp.mover_lote(itens)

    assert resultado["movidos"] == []
    assert resultado["erros"]
    assert (raiz / "1UN LONA 1.00X2.00M_ARTE.pdf").is_file()


def test_lote_de_mais_de_um_cliente_e_recusado(tmp_path):
    """
    O lote vira linha de consumo por CLIENTE. Misturado, o material de um
    entraria na conta do outro.
    """
    raiz, itens = _um_item(tmp_path, "1UN LONA 1.00X2.00M_ARTE.pdf",
                           "1UN LONA 1.00X3.00M_OUTRA.pdf")
    itens[1] = dict(itens[1], cliente="OUTRO CLIENTE")

    with pytest.raises(mp.ErroProducao):
        mp.mover_lote(itens)

    assert not (raiz / "PRONTOS").exists()


def test_falha_em_um_arquivo_nao_impede_os_outros(tmp_path):
    """
    Lote de 20 peças com uma travada tem que mover 19 e dizer qual sobrou.
    Parar tudo na primeira faria ele repetir o trabalho na mão.
    """
    raiz, itens = _um_item(tmp_path, "1UN LONA 1.00X2.00M_BOA.pdf",
                           "1UN LONA 1.00X3.00M_TRAVADA.pdf")
    travada = next(i for i in itens if i["arquivo"] == "1UN LONA 1.00X3.00M_TRAVADA.pdf")
    itens[itens.index(travada)] = dict(travada, assinatura=(1, 1))

    resultado = mp.mover_lote(itens)

    assert [i["arquivo"] for i in resultado["movidos"]] == ["1UN LONA 1.00X2.00M_BOA.pdf"]
    assert [e["arquivo"] for e in resultado["erros"]] == ["1UN LONA 1.00X3.00M_TRAVADA.pdf"]
    assert (raiz / "PRONTOS" / "1UN LONA 1.00X2.00M_BOA.pdf").is_file()
    assert (raiz / "1UN LONA 1.00X3.00M_TRAVADA.pdf").is_file()


def test_lote_vazio_nao_abre_trava_nem_escreve_historico(tmp_path):
    """Clicar sem selecionar nada não pode criar linha de histórico."""
    assert mp.mover_lote([]) == dict(movidos=[], erros=[])
    assert _historico() == []
