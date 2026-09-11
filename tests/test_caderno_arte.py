import hashlib
import pathlib
import sys
import zipfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import pytest

import caderno_arte as ca

ALTURA_SLIDE = 5143500
LARGURA_SLIDE = 9144000

# Conteudo ficticio de cada carimbo. O modulo identifica carimbo pelo
# CONTEUDO da imagem, nunca pelo nome do arquivo — entao o teste tambem
# precisa de bytes de verdade dentro do .pptx.
CONTEUDO = {
    "APROVADO": b"<carimbo aprovado>",
    "EM APROVACAO": b"<carimbo em aprovacao>",
    "REPROVADO": b"<carimbo reprovado>",
    "EM CRIACAO": b"<carimbo em criacao>",
    "CRIACAO CONFERIDO": b"<carimbo criacao conferido>",
    "ARQUITETURA CONFERIDO": b"<carimbo arquitetura conferido>",
    "PRODUCAO CONFERIDO": b"<carimbo producao conferido>",
}


@pytest.fixture(autouse=True)
def _registrar_carimbos_de_teste(monkeypatch):
    tabela = dict(ca.CARIMBOS_POR_CONTEUDO)
    for rotulo, dados in CONTEUDO.items():
        tabela[hashlib.sha256(dados).hexdigest()] = rotulo
    monkeypatch.setattr(ca, "CARIMBOS_POR_CONTEUDO", tabela)


# Preenchida por _midias(): diz que rotulo cada arquivo de imagem carrega
# dentro do .pptx do teste.
_MIDIAS = {}


def _midias(**por_arquivo):
    """Define a numeracao de midia deste caderno de teste."""
    _MIDIAS.clear()
    _MIDIAS.update(por_arquivo)
    return _MIDIAS


def _pic(rid, y_percentual):
    """Um carimbo colado a y% da altura do slide."""
    y = int(ALTURA_SLIDE * y_percentual / 100)
    return (
        '<p:pic><p:blipFill><a:blip r:embed="%s"/></p:blipFill>'
        '<p:spPr><a:xfrm><a:off x="100" y="%d"/>'
        '<a:ext cx="10000" cy="10000"/></a:xfrm></p:spPr></p:pic>' % (rid, y)
    )


def _caderno(tmp_path, slides, nome="caderno.pptx"):
    """
    Monta um .pptx minimo: so o que o leitor realmente le. Cada slide e
    (lista de textos, lista de (rId, arquivo_de_imagem, y%), link).

    O terceiro elemento de cada carimbo e o NOME do arquivo de midia; o
    conteudo vem de CONTEUDO pelo rotulo, e o nome pode ser qualquer um —
    e justamente isso que os testes exercitam.
    """
    caminho = tmp_path / nome
    with zipfile.ZipFile(str(caminho), "w") as z:
        z.writestr(
            "ppt/presentation.xml",
            '<p:presentation><p:sldSz cy="%d" cx="%d"/></p:presentation>'
            % (ALTURA_SLIDE, LARGURA_SLIDE),
        )
        for numero, (textos, carimbos, link) in enumerate(slides, start=1):
            corpo = "".join("<a:t>%s</a:t>" % t for t in textos)
            corpo += "".join(_pic(rid, y) for rid, _, y in carimbos)
            z.writestr("ppt/slides/slide%d.xml" % numero, "<p:sld>%s</p:sld>" % corpo)

            rels = ['<?xml version="1.0"?><Relationships>']
            for rid, imagem, _ in carimbos:
                rels.append('<Relationship Id="%s" Target="../media/%s"/>' % (rid, imagem))
            if link:
                rels.append(
                    '<Relationship Id="rLink" Target="%s" TargetMode="External"/>' % link)
            rels.append("</Relationships>")
            z.writestr("ppt/slides/_rels/slide%d.xml.rels" % numero, "".join(rels))

        for arquivo, rotulo in _MIDIAS.items():
            z.writestr("ppt/media/" + arquivo, CONTEUDO[rotulo])
    return caminho


def _ficha(nome="LONA FRONTAL PORTICO", material="LONA IMPRESSA",
           medidas="12,80 X 4,50", sangria="13,10 X 4,80", qtd="01",
           etiqueta="AF - PORTICO EXT - LONA FRONTAL"):
    return [etiqueta, "QTDD", qtd, "OBS:", "NONONO", "MEDIDAS:", medidas,
            "MEDIDAS COM SANGRIA:", sangria, "NOME DO ARQUIVO", nome,
            "MATERIAL", material]


# ---------------------------------------------------------------- ficha

def test_le_a_ficha_inteira_do_slide(tmp_path):
    caminho = _caderno(tmp_path, [(_ficha(), [], "https://drive.google.com/open?id=ABC123")])

    peca = ca.pecas(caminho)[0]

    assert peca["nome"] == "LONA FRONTAL PORTICO"
    assert peca["material"] == "LONA IMPRESSA"
    assert peca["medidas"] == "12,80 X 4,50"
    assert peca["medidas_sangria"] == "13,10 X 4,80"
    assert peca["quantidade"] == "01"
    assert peca["links"] == ["https://drive.google.com/open?id=ABC123"]


def test_slide_sem_nome_de_arquivo_nao_e_peca(tmp_path):
    """Capa, indice e pagina de status nao sao peca — e nao sao erro."""
    caminho = _caderno(tmp_path, [
        (["Cenografia GL", "EXECUTIVO"], [], None),
        (_ficha(), [], None),
    ])

    assert len(ca.ler(caminho)) == 2
    assert len(ca.pecas(caminho)) == 1


# -------------------------------------------------------------- carimbo

def test_carimbo_do_rodape_e_paleta_e_nao_conta_como_status(tmp_path):
    """
    Os 7 carimbos existem em TODO slide; a fileira do rodape mora fora da
    area (y ~110%) e e so a paleta de onde o designer arrasta. Confundir
    as duas faria toda peca do caderno parecer aprovada.
    """
    _midias(**{"image1.png": "ARQUITETURA CONFERIDO",
               "image4.png": "APROVADO", "image3.png": "REPROVADO"})
    caminho = _caderno(tmp_path, [(
        _ficha(),
        [("rId1", "image1.png", 6.7),      # colado no slide
         ("rId4", "image4.png", 110.5),    # APROVADO, mas na paleta
         ("rId3", "image3.png", 110.5)],   # REPROVADO, mas na paleta
        None)])

    peca = ca.pecas(caminho)[0]

    assert peca["carimbos"] == ["ARQUITETURA CONFERIDO"]
    assert peca["situacao"] == "EM CRIACAO", "carimbo da paleta nao pode virar status"


def test_aprovado_colado_no_slide_vale(tmp_path):
    _midias(**{"image1.png": "ARQUITETURA CONFERIDO", "image11.png": "CRIACAO CONFERIDO",
               "image4.png": "APROVADO", "image3.png": "REPROVADO"})
    caminho = _caderno(tmp_path, [(
        _ficha(),
        [("rId1", "image1.png", 6.7), ("rId11", "image11.png", 25.8),
         ("rId4", "image4.png", 43.5),
         ("rId3", "image3.png", 110.5)],
        None)])

    assert ca.pecas(caminho)[0]["situacao"] == "APROVADO"


def test_reprovado_vence_aprovado_no_mesmo_slide(tmp_path):
    """Sobrou carimbo antigo: o pior caso manda, nunca o melhor."""
    _midias(**{"image4.png": "APROVADO", "image3.png": "REPROVADO"})
    caminho = _caderno(tmp_path, [(
        _ficha(),
        [("rId4", "image4.png", 43.5), ("rId3", "image3.png", 20.0)],
        None)])

    assert ca.pecas(caminho)[0]["situacao"] == "REPROVADO"


def test_carimbo_e_reconhecido_pelo_conteudo_e_nao_pelo_nome_do_arquivo(tmp_path):
    """
    A numeracao de 'ppt/media' e por apresentacao. Num caderno o APROVADO
    e 'image4.png'; no caderno seguinte esse mesmo nome e o REPROVADO.
    Identificar por nome inverteu o sinal de um caderno inteiro de 154
    pecas (2026-09-11) — reprovando o que estava aprovado.

    Aqui a numeracao e deliberadamente TROCADA em relacao aos outros
    testes: quem manda tem que ser o conteudo.
    """
    _midias(**{"image9.png": "APROVADO", "image1.png": "REPROVADO"})
    caminho = _caderno(tmp_path, [(
        _ficha(),
        [("rId9", "image9.png", 30.0),      # APROVADO colado no slide
         ("rId1", "image1.png", 110.5)],    # REPROVADO na paleta
        None)])

    assert ca.pecas(caminho)[0]["situacao"] == "APROVADO"


def test_slide_sem_carimbo_nenhum_fica_marcado(tmp_path):
    caminho = _caderno(tmp_path, [(_ficha(), [], None)])

    assert ca.pecas(caminho)[0]["situacao"] == "SEM CARIMBO"


# ----------------------------------------------------------------- nome

def test_nome_sai_no_padrao_da_casa(tmp_path):
    caminho = _caderno(tmp_path, [(_ficha(), [], None)])

    peca = ca.fichas_com_nome(caminho)[0]

    assert peca["nome_arquivo"] == "1UN LONA 12,80X4,50M_FRONTAL PORTICO_sangria 13,10X4,80M"


def test_medida_real_vem_antes_da_sangria_e_e_ela_que_o_sistema_le(tmp_path):
    """
    O projeto inteiro le a PRIMEIRA medida do nome. Se a sangria viesse
    primeiro, toda peca entraria no sistema maior do que e.
    """
    from config import carregar_config
    from dimensoes import extrair_dimensoes

    caminho = _caderno(tmp_path, [(_ficha(), [], None)])
    nome = ca.fichas_com_nome(caminho)[0]["nome_arquivo"]

    dim = extrair_dimensoes(nome, carregar_config().get("typos_unidade", {}))

    assert round(dim["largura_m"], 2) == 12.80
    assert round(dim["altura_m"], 2) == 4.50


def test_material_do_cliente_manda_sobre_o_nome_da_peca(tmp_path):
    """
    Regra do usuario (2026-09-11): "respeite sempre o que for material
    que o cliente pede". No caderno real existe peca CHAMADA "ADESIVO"
    feita de LONA IMPRESSA — o nome nao pode dizer as duas coisas.
    """
    caminho = _caderno(tmp_path, [(
        _ficha(nome="ADESIVO", material="LONA IMPRESSA", medidas="0,80 X 1,80",
               sangria="0,85 X 1,85", qtd="04",
               etiqueta="AF - PORTICO EXT PAINEL POSTERIOR LATERAL"),
        [], None)])

    peca = ca.fichas_com_nome(caminho)[0]

    assert peca["nome_arquivo"].startswith("4UN LONA ")
    assert "ADESIVO" not in peca["nome_arquivo"], "a palavra que contradiz o material sai"
    assert "PORTICO EXT PAINEL POSTERIOR LATERAL" in peca["nome_arquivo"], \
        "descricao vazia usa a etiqueta do link, que e mais descritiva"


def test_xps_e_sempre_pvc_mesmo_com_adesivo_no_material(tmp_path):
    """
    "tudo que for XPS pode considerar PVC" (usuario, 2026-09-11). Sem
    isto o desempate por nome mais longo daria ADESIVO (7) em vez de
    PVC (3), e a peca iria pra maquina errada.
    """
    caminho = _caderno(tmp_path, [(
        _ficha(nome="LOGO MERCADO LIVRE", material="LOGO XPS RECORTE COM ADESIVO IMPRESSO",
               medidas="3,44 X 0,37", sangria="-"),
        [], None)])

    assert ca.fichas_com_nome(caminho)[0]["nome_arquivo"].startswith("1UN PVC ")


def test_medida_incompleta_nao_vira_nome_nem_palpite(tmp_path):
    """
    Tres pecas do caderno real vieram com um numero so ('182,10'). Dado
    quebrado na origem se sinaliza; nao se adivinha a outra medida.
    """
    caminho = _caderno(tmp_path, [(_ficha(medidas="182,10", sangria="-"), [], None)])

    peca = ca.fichas_com_nome(caminho)[0]

    assert peca["nome_arquivo"] is None
    assert "182,10" in peca["motivo_nome"]


def test_arquivo_que_nao_e_caderno_e_recusado(tmp_path):
    qualquer = tmp_path / "nao_e_pptx.pptx"
    qualquer.write_bytes(b"isto nao e um zip")

    assert ca.caminho_valido(qualquer) is False
    assert ca.caminho_valido(tmp_path / "nem_existe.pptx") is False
