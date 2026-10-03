"""
Vigia do caderno de arte no Canva (2026-10-03).

Pedido do usuário: "o vigia está sempre passando; de qualquer cliente deve
ser um padrão conferir se o caderno tem coisa nova; se tiver link novo deve
baixar e gerar um aviso pra eu saber".

O que estes testes travam é o que pode custar material ou confiança: página
nova no meio do caderno NÃO pode anunciar o caderno inteiro como novidade;
medida mexida numa peça já recebida tem que virar aviso; o mesmo aviso não
se repete; e nada é baixado dentro do OneDrive nem arquivado sozinho.

Nenhum teste toca a internet nem pasta real.
"""
import datetime
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import pytest

import caminhos
import clientes
import vigia_caderno as vc

LINK = "https://www.canva.com/design/DAHWe8X_fZk/codigoDeCompartilhamento/view"


@pytest.fixture(autouse=True)
def nada_real(tmp_path, monkeypatch):
    onedrive = tmp_path / "UNYCOMUNICACAO"
    monkeypatch.setattr(caminhos, "ONEDRIVE_UNY", onedrive)
    monkeypatch.setattr(caminhos, "RECEBIMENTO_DE_ARTES", onedrive / "Recebimento de Artes")
    monkeypatch.setattr(caminhos, "PASTA_RECEBENDO", tmp_path / "recebendo")
    (onedrive / "Recebimento de Artes").mkdir(parents=True)

    def proibido(*a, **k):
        raise AssertionError("teste tentou sair pra rede de verdade")
    import requests
    monkeypatch.setattr(requests.Session, "request", proibido)


# ================================================================ dublês

def _ficha(nome, pagina, link="1LONAAaaaaaaaaaaaaaaa", secao="LONAS", **extra):
    return {"pagina": pagina, "nome": nome, "secao": secao, "medidas": "7,14 x 1,10m",
            "sangria": "15cm", "material": "LONA IMPRESSA", "quantidade": "1",
            "links": ["https://drive.google.com/file/d/%s/view?usp=drive_link" % link] if link else [],
            **extra}


def _caderno(fichas, versao=274):
    return {"titulo": "Caderno de artes - LOJINHA MR2 CULTURAL", "design_id": "DAHWe8X_fZk",
            "link": LINK, "paginas": 68, "versao": versao, "fichas": fichas}


def _lojinha():
    return _caderno([_ficha("LONA A", 8, "1LONAAaaaaaaaaaaaaaaa"),
                     _ficha("LONA B", 9, "1LONABaaaaaaaaaaaaaaa"),
                     _ficha("PLACA PS", 50, "1PLACA1aaaaaaaaaaaaaa", secao="ADESIVOS")])


def _cliente(caderno=None, nome="VIBRA"):
    """Um cliente que já recebeu um caderno do Canva — é isso que o faz vigiado."""
    cliente = clientes.criar(nome, checklist_ativo=False)
    if caderno is not None:
        pasta = cliente.pasta_sistema / "recebidos" / "2026-10-02 Canva"
        pasta.mkdir(parents=True)
        (pasta / "caderno.json").write_text(json.dumps(dict(caderno, lido_em="2026-10-02T19:41:49")),
                                            encoding="utf-8")
    return cliente


class _Avisos:
    """O notificador do Windows, de mentira."""
    def __init__(self, falhar=False):
        self.recebidos = []
        self.falhar = falhar

    def __call__(self, mensagem, titulo=""):
        if self.falhar:
            raise RuntimeError("PowerShell falhou ao notificar")
        self.recebidos.append((titulo, mensagem))


def _baixador(registro):
    """Dublê de baixar_novas: anota o que seria baixado, sem rede."""
    def baixar(caderno, achados, pasta, sessao=None):
        registro.append((pasta, [i["nome"] for i in achados if i["links"]]))
        pasta.mkdir(parents=True, exist_ok=True)
        caminhos_ = []
        for item in achados:
            if item["links"]:
                arquivo = pasta / ("%s.pdf" % item["nome"])
                arquivo.write_bytes(b"%PDF-1.4 arte")
                caminhos_.append(arquivo)
        return caminhos_, []
    return baixar


def _passada(caderno, notificar, baixado=None, agora=None, forcar=True):
    return vc.conferir(agora=agora, notificar=notificar, ler=lambda link, sessao=None: caderno,
                       forcar=forcar, baixar=_baixador(baixado if baixado is not None else []))


# ===================================================== o que é "coisa nova"

def test_sem_mudanca_nao_avisa_nada():
    _cliente(_lojinha())
    avisos = _Avisos()
    assert _passada(_lojinha(), avisos) == {}
    assert avisos.recebidos == []


def test_peca_nova_no_caderno_baixa_e_avisa():
    _cliente(_lojinha())
    novo = _caderno(_lojinha()["fichas"] + [_ficha("LONA PISO", 69, "1PISOaaaaaaaaaaaaaaaaa")], versao=275)
    avisos, baixado = _Avisos(), []

    achados = _passada(novo, avisos, baixado)

    assert [i["tipo"] for i in achados["VIBRA"]] == ["ficha nova"]
    (pasta, nomes), = baixado
    assert nomes == ["LONA PISO"]
    (titulo, texto), = avisos.recebidos
    assert titulo == vc.TITULO_AVISO
    assert "VIBRA — p.69 LONA PISO: peça nova no caderno" in texto
    assert "Receber artes" in texto, "o aviso tem que dizer o que fazer com a arte baixada"


def test_arte_trocada_na_mesma_ficha_e_link_novo():
    """A agência reexportou a lona: mesmo nome, outro arquivo no Drive."""
    _cliente(_lojinha())
    novo = _caderno([_ficha("LONA A", 8, "1LONAAoutroaaaaaaaaaa"),
                     _ficha("LONA B", 9, "1LONABaaaaaaaaaaaaaaa"),
                     _ficha("PLACA PS", 50, "1PLACA1aaaaaaaaaaaaaa", secao="ADESIVOS")])
    avisos, baixado = _Avisos(), []

    achados = _passada(novo, avisos, baixado)

    assert [(i["tipo"], i["nome"]) for i in achados["VIBRA"]] == [("link novo", "LONA A")]
    assert baixado[0][1] == ["LONA A"]
    assert "a arte foi trocada no caderno" in avisos.recebidos[0][1]


def test_medida_mexida_vira_aviso_sem_baixar_nada():
    """O arquivo é o mesmo; produzir no tamanho velho é material perdido."""
    _cliente(_lojinha())
    novo = _caderno([_ficha("LONA A", 8, "1LONAAaaaaaaaaaaaaaaa", medidas="7,14 x 2,20m"),
                     _ficha("LONA B", 9, "1LONABaaaaaaaaaaaaaaa"),
                     _ficha("PLACA PS", 50, "1PLACA1aaaaaaaaaaaaaa", secao="ADESIVOS")])
    avisos, baixado = _Avisos(), []

    achados = _passada(novo, avisos, baixado)

    assert [i["tipo"] for i in achados["VIBRA"]] == ["ficha mexida"]
    assert baixado == [], "ficha mexida não tem arquivo novo pra pegar"
    assert "medidas: 7,14 x 1,10m -> 7,14 x 2,20m" in avisos.recebidos[0][1]
    assert "Nada foi baixado" in avisos.recebidos[0][1]


def test_pagina_nova_no_meio_nao_anuncia_o_caderno_inteiro():
    """
    Uma página inserida empurra a numeração de todas as seguintes. Contar por
    página faria o vigia gritar 'tudo novo' e ninguém olharia o aviso de novo.
    """
    _cliente(_lojinha())
    novo = _caderno([_ficha("LONA A", 9, "1LONAAaaaaaaaaaaaaaaa"),
                     _ficha("LONA B", 10, "1LONABaaaaaaaaaaaaaaa"),
                     _ficha("PLACA PS", 51, "1PLACA1aaaaaaaaaaaaaa", secao="ADESIVOS")])
    avisos = _Avisos()

    assert _passada(novo, avisos) == {}
    assert avisos.recebidos == []


def test_ficha_que_ganhou_link_e_novidade():
    """As PLACAS QR CODE do VIBRA ficaram sem link no recebimento."""
    _cliente(_caderno([_ficha("PLACA QR", 65, None, secao="ADESIVOS")]))
    novo = _caderno([_ficha("PLACA QR", 65, "1QRaaaaaaaaaaaaaaaaaa", secao="ADESIVOS")])
    avisos, baixado = _Avisos(), []

    achados = _passada(novo, avisos, baixado)

    assert [i["tipo"] for i in achados["VIBRA"]] == ["link novo"]
    assert baixado[0][1] == ["PLACA QR"]


def test_homonimas_nao_se_confundem():
    """O caderno da LOJINHA tem 15 fichas chamadas 'PLACA PS'."""
    tres = [_ficha("PLACA PS", 50 + i, "1PLACA%daaaaaaaaaaaaa" % i, secao="ADESIVOS") for i in range(3)]
    _cliente(_caderno(tres))
    mexida = [dict(tres[0]), dict(tres[1], medidas="0,50 x 0,50m"), dict(tres[2])]
    avisos = _Avisos()

    achados = _passada(_caderno(mexida), avisos)

    assert len(achados["VIBRA"]) == 1
    assert achados["VIBRA"][0]["pagina"] == 51


def test_mesmo_arquivo_em_outra_ficha_nao_e_arte_nova():
    """Os três QUADROS apontam o mesmo PDF: ficha nova sim, download não."""
    _cliente(_lojinha())
    novo = _caderno(_lojinha()["fichas"] + [_ficha("LONA A CÓPIA", 70, "1LONAAaaaaaaaaaaaaaaa")])
    avisos, baixado = _Avisos(), []

    achados = _passada(novo, avisos, baixado)

    assert [i["tipo"] for i in achados["VIBRA"]] == ["ficha nova"]
    assert achados["VIBRA"][0]["links"] == [], "o arquivo já estava no caderno"
    assert baixado == []


def test_baixa_pela_mesma_origem_da_tela_e_so_as_fichas_novas():
    """
    Quem busca o arquivo é a OrigemCaderno — a mesma da tela —, mas com o
    caderno reduzido às fichas novas: resolver os 60 links a cada novidade
    seria uma leitura inteira do Drive por peça acrescentada.
    """
    import origem_artes as oa
    caderno = _caderno(_lojinha()["fichas"] + [_ficha("LONA PISO", 69, "1PISOaaaaaaaaaaaaaaaaa")])
    achados = vc.novidades(vc.resumo(_lojinha()), vc.resumo(caderno))
    recebido = {}

    class Falsa:
        ignorados = []

        def __init__(self, cad):
            recebido["caderno"] = cad

        def listar(self):
            return [oa.Arquivo(id="p69|1PISOaaaaaaaaaaaaaaaaa", nome="PISO.pdf",
                               ref={"drive_id": "1PISOaaaaaaaaaaaaaaaaa"})]

        def baixar(self, arquivo, pasta):
            destino = pathlib.Path(pasta) / arquivo.nome
            destino.parent.mkdir(parents=True, exist_ok=True)
            destino.write_bytes(b"%PDF-1.4")
            return destino

    baixados, ignorados = vc.baixar_novas(caderno, achados, caminhos.PASTA_RECEBENDO / "lote",
                                          abrir_origem=Falsa)

    assert [f["nome"] for f in recebido["caderno"]["fichas"]] == ["LONA PISO"]
    assert recebido["caderno"]["link"] == LINK, "a origem precisa do link do caderno"
    assert [p.name for p in baixados] == ["PISO.pdf"] and ignorados == []


# ========================================================= disciplina do aviso

def test_o_mesmo_aviso_nao_se_repete():
    _cliente(_lojinha())
    novo = _caderno(_lojinha()["fichas"] + [_ficha("LONA PISO", 69, "1PISOaaaaaaaaaaaaaaaaa")])
    avisos = _Avisos()

    assert _passada(novo, avisos)
    assert _passada(novo, avisos) == {}, "a novidade de antes não pode voltar a tocar"
    assert len(avisos.recebidos) == 1


def test_aviso_que_falhou_tenta_de_novo_sem_baixar_de_novo():
    """Sem notificação ninguém ficou sabendo — mas o arquivo já está aqui."""
    _cliente(_lojinha())
    novo = _caderno(_lojinha()["fichas"] + [_ficha("LONA PISO", 69, "1PISOaaaaaaaaaaaaaaaaa")])
    baixado = []

    assert _passada(novo, _Avisos(falhar=True), baixado) == {}
    avisos = _Avisos()
    achados = _passada(novo, avisos, baixado)

    assert [i["nome"] for i in achados["VIBRA"]] == ["LONA PISO"]
    assert len(baixado) == 1, "baixou duas vezes a mesma arte"
    assert len(avisos.recebidos) == 1


def test_nao_le_o_canva_a_cada_minuto():
    _cliente(_lojinha())
    leituras = []

    def ler(link, sessao=None):
        leituras.append(link)
        return _lojinha()

    agora = datetime.datetime(2026, 10, 3, 8, 0)
    for minuto in (0, 1, 2, 14):
        vc.conferir(agora=agora + datetime.timedelta(minutes=minuto), notificar=_Avisos(), ler=ler)
    assert len(leituras) == 1, "a leitura puxa 1,4 MB — não pode ser de minuto em minuto"
    vc.conferir(agora=agora + datetime.timedelta(minutes=16), notificar=_Avisos(), ler=ler)
    assert len(leituras) == 2


def test_aviso_longo_nao_vira_muralha():
    _cliente(_caderno([_ficha("LONA A", 8)]))
    muitas = [_ficha("PEÇA %d" % i, 20 + i, "1PECA%03daaaaaaaaaaaa" % i) for i in range(20)]
    avisos = _Avisos()

    _passada(_caderno([_ficha("LONA A", 8)] + muitas), avisos)

    texto = avisos.recebidos[0][1]
    assert texto.count("\n") <= vc.LINHAS_NO_AVISO + 1
    assert "e mais 12 mudança(s)" in texto


# ============================================== quem é vigiado, e onde cai

def test_cliente_sem_caderno_do_canva_nao_e_vigiado():
    _cliente(None, nome="SEM CADERNO")
    leituras = []
    vc.conferir(notificar=_Avisos(), ler=lambda link, sessao=None: leituras.append(link))
    assert leituras == []


def test_caderno_de_outra_origem_nao_e_vigiado():
    """Caderno do Google Slides não se lê pelo Canva."""
    cliente = _cliente(None, nome="MERCADO LIVRE")
    pasta = cliente.pasta_sistema / "recebidos" / "2026-09-20 Slides"
    pasta.mkdir(parents=True)
    (pasta / "caderno.json").write_text(json.dumps(
        {"link": "https://docs.google.com/presentation/d/XYZ/edit", "fichas": [{"pagina": 1}]}),
        encoding="utf-8")
    assert vc.caderno_do_cliente(clientes.obter("MERCADO LIVRE")) is None


def test_a_arte_nova_espera_fora_do_onedrive():
    cliente = _cliente(_lojinha())
    pasta = vc.pasta_das_novidades(cliente, datetime.datetime(2026, 10, 3, 8, 30))
    assert caminhos.PASTA_RECEBENDO in pasta.parents
    assert caminhos.RECEBIMENTO_DE_ARTES not in pasta.parents
    assert pasta.name == "2026-10-03 083000" and cliente.nome in pasta.parts


def test_a_espera_do_vigia_tambem_e_faxinada():
    """O lote do vigia tem o mesmo prazo do lote da tela."""
    import origem_artes as oa
    cliente = _cliente(_lojinha())
    velha = vc.pasta_das_novidades(cliente, datetime.datetime(2026, 9, 1, 8, 0))
    nova = vc.pasta_das_novidades(cliente, datetime.datetime(2026, 10, 3, 8, 0))
    for p in (velha, nova):
        p.mkdir(parents=True)
        (p / "arte.pdf").write_bytes(b"%PDF")

    oa.limpar_lotes_velhos(agora=datetime.datetime(2026, 10, 3, 9, 0))

    assert not velha.exists() and nova.exists()


def test_nada_entra_em_artes_sozinho():
    """Quem decide nome, medida e material é ele, na tela de dois passos."""
    cliente = _cliente(_lojinha())
    novo = _caderno(_lojinha()["fichas"] + [_ficha("LONA PISO", 69, "1PISOaaaaaaaaaaaaaaaaa")])

    _passada(novo, _Avisos())

    assert list((cliente.pasta / "ARTES").rglob("*.pdf")) == []
    assert not (cliente.pasta / "_baixados.json").exists()


def test_o_caderno_do_recebimento_nao_e_reescrito():
    """O caderno guardado é a prova do que estava escrito no dia — não se mexe."""
    cliente = _cliente(_lojinha())
    guardado = cliente.pasta_sistema / "recebidos" / "2026-10-02 Canva" / "caderno.json"
    antes = guardado.read_text(encoding="utf-8")

    _passada(_caderno(_lojinha()["fichas"] + [_ficha("LONA PISO", 69, "1PISOaaaaaaaaaaaaaaaaa")]), _Avisos())

    assert guardado.read_text(encoding="utf-8") == antes


def test_canva_fora_do_ar_nao_derruba_a_passada():
    _cliente(_lojinha())

    def cair(link, sessao=None):
        raise OSError("o Canva não respondeu")

    assert vc.conferir(notificar=_Avisos(), ler=cair, forcar=True) == {}
    assert "não consegui ler o caderno" in vc.arquivo_log(clientes.obter("VIBRA")).read_text(encoding="utf-8")


def test_um_cliente_quebrado_nao_impede_o_outro():
    _cliente(_lojinha(), nome="VIBRA")
    _cliente(_lojinha(), nome="OUTRO")
    novo = _caderno(_lojinha()["fichas"] + [_ficha("LONA PISO", 69, "1PISOaaaaaaaaaaaaaaaaa")])

    def ler(link, sessao=None):
        if not getattr(ler, "caiu", False):
            ler.caiu = True
            raise OSError("caiu no primeiro cliente")
        return novo

    avisos = _Avisos()
    achados = vc.conferir(notificar=avisos, ler=ler, forcar=True,
                          baixar=_baixador([]))
    assert list(achados) == ["VIBRA"], "o segundo cliente da lista tinha que ser conferido"


def test_o_checklist_leva_o_vigia_de_carona(monkeypatch):
    """O caderno pega carona na única tarefa que já passa de minuto em minuto."""
    import vigia_checklist
    chamadas = []
    monkeypatch.setattr(vc, "conferir", lambda **k: chamadas.append(k) or {})
    vigia_checklist._conferir_cadernos()
    assert chamadas, "a passada do checklist tem que conferir os cadernos"


def test_carona_que_quebra_nao_derruba_o_checklist(monkeypatch):
    import vigia_checklist

    def explodir(**k):
        raise RuntimeError("boom")
    monkeypatch.setattr(vc, "conferir", explodir)
    assert vigia_checklist._conferir_cadernos() == {}
