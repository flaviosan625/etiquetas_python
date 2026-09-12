"""
Quem entra no lote de download (receber_artes.pecas_liberadas).

A regra mudou em 2026-09-12: aprovada + com link JÁ entra, mesmo sem um
nome pronto. O caderno real do Mercado Livre trouxe peças aprovadas com a
medida pela metade ("0,80", "182,10") — e áreas "aguardando 3D". Elas
precisam baixar; o nome é completado depois, medindo a arte. Só o que NÃO
está aprovado, ou não tem link, é que fica de fora.
"""
import hashlib
import pathlib
import sys
import zipfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import pytest

import caderno_arte as ca
import receber_artes

ALTURA_SLIDE = 5143500
LARGURA_SLIDE = 9144000

CONTEUDO = {
    "APROVADO": b"<carimbo aprovado>",
    "EM APROVACAO": b"<carimbo em aprovacao>",
    "REPROVADO": b"<carimbo reprovado>",
}


@pytest.fixture(autouse=True)
def _registrar_carimbos_de_teste(monkeypatch):
    tabela = dict(ca.CARIMBOS_POR_CONTEUDO)
    for rotulo, dados in CONTEUDO.items():
        tabela[hashlib.sha256(dados).hexdigest()] = rotulo
    monkeypatch.setattr(ca, "CARIMBOS_POR_CONTEUDO", tabela)


def _pic(rid, y_percentual):
    y = int(ALTURA_SLIDE * y_percentual / 100)
    return (
        '<p:pic><p:blipFill><a:blip r:embed="%s"/></p:blipFill>'
        '<p:spPr><a:xfrm><a:off x="100" y="%d"/>'
        '<a:ext cx="10000" cy="10000"/></a:xfrm></p:spPr></p:pic>' % (rid, y)
    )


def _ficha(nome="LONA FRONTAL PORTICO", material="LONA IMPRESSA",
           medidas="12,80 X 4,50", sangria="13,10 X 4,80", qtd="01",
           etiqueta="AF - PORTICO EXT - LONA FRONTAL"):
    return [etiqueta, "QTDD", qtd, "OBS:", "NONONO", "MEDIDAS:", medidas,
            "MEDIDAS COM SANGRIA:", sangria, "NOME DO ARQUIVO", nome,
            "MATERIAL", material]


def _caderno(tmp_path, slides, midias, nome="caderno.pptx"):
    """Monta um .pptx mínimo. slides: (textos, carimbos[(rId,img,y%)], link)."""
    caminho = tmp_path / nome
    with zipfile.ZipFile(str(caminho), "w") as z:
        z.writestr("ppt/presentation.xml",
                   '<p:presentation><p:sldSz cy="%d" cx="%d"/></p:presentation>'
                   % (ALTURA_SLIDE, LARGURA_SLIDE))
        for numero, (textos, carimbos, link) in enumerate(slides, start=1):
            corpo = "".join("<a:t>%s</a:t>" % t for t in textos)
            corpo += "".join(_pic(rid, y) for rid, _, y in carimbos)
            z.writestr("ppt/slides/slide%d.xml" % numero, "<p:sld>%s</p:sld>" % corpo)
            rels = ['<?xml version="1.0"?><Relationships>']
            for rid, imagem, _ in carimbos:
                rels.append('<Relationship Id="%s" Target="../media/%s"/>' % (rid, imagem))
            if link:
                rels.append('<Relationship Id="rLink" Target="%s" TargetMode="External"/>' % link)
            rels.append("</Relationships>")
            z.writestr("ppt/slides/_rels/slide%d.xml.rels" % numero, "".join(rels))
        for arquivo, rotulo in midias.items():
            z.writestr("ppt/media/" + arquivo, CONTEUDO[rotulo])
    return caminho


LINK = "https://drive.google.com/open?id=ABC123"
APROV = [("rId4", "image4.png", 43.5)]   # APROVADO colado no slide
MIDIAS = {"image4.png": "APROVADO", "image3.png": "REPROVADO", "image2.png": "EM APROVACAO"}


def test_aprovada_com_link_e_nome_completo_entra(tmp_path):
    caminho = _caderno(tmp_path, [(_ficha(), APROV, LINK)], MIDIAS)

    liberadas = receber_artes.pecas_liberadas(caminho)

    assert [f["nome"] for f in liberadas] == ["LONA FRONTAL PORTICO"]


def test_aprovada_com_link_mas_medida_pela_metade_TAMBEM_entra(tmp_path):
    """
    O ponto da mudança: o caderno deu só '182,10', então não há nome pronto,
    mas a peça está aprovada e tem link. Ela ENTRA — o nome vem depois, da
    arte. Antes ela era descartada em silêncio.
    """
    caminho = _caderno(tmp_path, [(_ficha(medidas="182,10", sangria="-"), APROV, LINK)], MIDIAS)

    liberadas = receber_artes.pecas_liberadas(caminho)

    assert len(liberadas) == 1
    assert liberadas[0]["nome_arquivo"] is None  # sem nome ainda, mas liberada


def test_aprovada_sem_link_fica_de_fora(tmp_path):
    caminho = _caderno(tmp_path, [(_ficha(), APROV, None)], MIDIAS)

    assert receber_artes.pecas_liberadas(caminho) == []


def test_em_aprovacao_fica_de_fora_mesmo_com_link(tmp_path):
    """Cliente ainda não liberou (o print do status): não baixa."""
    caminho = _caderno(tmp_path, [(
        _ficha(), [("rId2", "image2.png", 43.5)], LINK)], MIDIAS)

    assert receber_artes.pecas_liberadas(caminho) == []
