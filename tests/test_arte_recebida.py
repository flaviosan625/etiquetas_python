"""
Onde a arte processada vai parar.

Até 2026-09-20 toda arte caía solta em ARTES/. As áreas já organizadas na
mão (04 - Túnel entrada, 09 - Área Premium, 11 - Sala Conexões) mostraram
que o lugar certo é uma pasta por área do caderno, e o pedido do usuário
nessa data foi explícito: "separar pasta por área". O parâmetro 'subpasta'
faz isso SEM mudar o caminho de quem não passa nada — é a extensão por
parâmetro opcional que o CLAUDE.md pede, não um caminho novo.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import pymupdf
import pytest

import arte_recebida


def _pdf(caminho, largura_pt=200, altura_pt=100):
    """Um PDF de uma página, sem marca de corte, só pra ter o que mover."""
    doc = pymupdf.open()
    doc.new_page(width=largura_pt, height=altura_pt)
    doc.save(str(caminho), garbage=4, deflate=True)
    doc.close()
    return caminho


@pytest.fixture
def ficha():
    return {
        "slide": 158,
        "nome": "PAINEL FRONTAL FUNDO",
        "nome_arquivo": "1UN LONA 9,50X4,50M_PAINEL FRONTAL FUNDO",
        "medidas": None,
    }


def test_sem_subpasta_continua_caindo_solta_em_artes(tmp_path, ficha):
    pasta = tmp_path / "cliente"
    entrada = pasta / arte_recebida.NOME_ENTRADA
    entrada.mkdir(parents=True)
    arte = _pdf(entrada / "baixada.pdf")

    ok, msg, _ = arte_recebida.processar_pdf(
        arte, tmp_path / "caderno.pptx", pasta, remover_marcas=False, ficha=ficha)

    assert ok, msg
    destino = pasta / "ARTES" / (ficha["nome_arquivo"] + ".pdf")
    assert destino.is_file()
    assert not arte.exists()


def test_com_subpasta_a_arte_cai_na_pasta_da_area(tmp_path, ficha):
    pasta = tmp_path / "cliente"
    entrada = pasta / arte_recebida.NOME_ENTRADA
    entrada.mkdir(parents=True)
    arte = _pdf(entrada / "baixada.pdf")

    ok, msg, _ = arte_recebida.processar_pdf(
        arte, tmp_path / "caderno.pptx", pasta, remover_marcas=False,
        ficha=ficha, subpasta="LANDMARK")

    assert ok, msg
    assert (pasta / "ARTES" / "LANDMARK" / (ficha["nome_arquivo"] + ".pdf")).is_file()
    # e não ficou nada solto na raiz de ARTES
    assert list((pasta / "ARTES").glob("*.pdf")) == []


def test_a_area_fica_registrada_em_baixados(tmp_path, ficha):
    """
    Sem isso o registro diria só o nome do arquivo, e ninguém saberia em
    qual pasta ele foi parar — justamente o que a separação por área
    existe pra responder.
    """
    pasta = tmp_path / "cliente"
    entrada = pasta / arte_recebida.NOME_ENTRADA
    entrada.mkdir(parents=True)
    arte = _pdf(entrada / "baixada.pdf")

    arte_recebida.processar_pdf(
        arte, tmp_path / "caderno.pptx", pasta, remover_marcas=False,
        ficha=ficha, subpasta="EIXO PRINCIPAL")

    registro = arte_recebida.ler_baixados(pasta)["caderno|slide|158"]
    assert registro["area"] == "EIXO PRINCIPAL"
    assert registro["arquivo"] == ficha["nome_arquivo"] + ".pdf"


def test_sem_subpasta_o_registro_nao_ganha_campo_novo(tmp_path, ficha):
    """Quem não usa área não vê o registro mudar de forma."""
    pasta = tmp_path / "cliente"
    entrada = pasta / arte_recebida.NOME_ENTRADA
    entrada.mkdir(parents=True)
    arte = _pdf(entrada / "baixada.pdf")

    arte_recebida.processar_pdf(
        arte, tmp_path / "caderno.pptx", pasta, remover_marcas=False, ficha=ficha)

    assert "area" not in arte_recebida.ler_baixados(pasta)["caderno|slide|158"]


def test_barra_no_nome_da_area_nao_escapa_da_pasta(tmp_path, ficha):
    """Nome de área vem do caderno, digitado por gente — sanitiza igual ao arquivo."""
    pasta = tmp_path / "cliente"
    entrada = pasta / arte_recebida.NOME_ENTRADA
    entrada.mkdir(parents=True)
    arte = _pdf(entrada / "baixada.pdf")

    arte_recebida.processar_pdf(
        arte, tmp_path / "caderno.pptx", pasta, remover_marcas=False,
        ficha=ficha, subpasta="EIXO/PRINCIPAL")

    assert (pasta / "ARTES" / "EIXO_PRINCIPAL").is_dir()
