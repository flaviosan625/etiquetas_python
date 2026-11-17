"""
Testes do novo fluxo unificado de montagem e despacho automático para o RIP:
1. Artes soltas a serem montadas.
2. Saída única na pasta ARTES MONTADAS com identificação da máquina no nome.
3. Vigia automático que identifica a máquina pelo nome da folha e despacha direto para o RIP.
"""
import pathlib
import pytest

import caminhos
import dimensoes
import montagem
import rasterlink_hotfolder as rlhf


def test_nome_da_folha_com_maquina():
    nome = montagem.nome_da_folha(
        cliente="UNY_CLIENTE",
        categoria="LONA",
        largura_m=5.00,
        comprimento_m=12.50,
        quantas=8,
        maquina="DOCAN R5200"
    )
    assert nome.startswith("[DOCAN R5200]_1UN LONA 5.00X12.50M")
    assert "MONTAGEM_8pecas" in nome

    # Dimensões e quantidade são reconhecidas perfeitamente mesmo com a tag da máquina
    dim = dimensoes.extrair_dimensoes(nome)
    assert dim is not None
    assert dim["largura_m"] == 5.00
    assert dim["altura_m"] == 12.50

    qtd, achou = dimensoes.extrair_quantidade(nome)
    assert qtd == 1
    assert achou is True


def test_identificar_maquina_pelo_nome():
    maquinas = {
        "DOCAN R5200": {"hot_folder": r"C:\RIP\Docan"},
        "SWJ320A": {"hot_folder": r"C:\RIP\SWJ"},
        "UJV 100 UNY CV": {"hot_folder": r"C:\RIP\UJV"},
    }

    # Com tag entre colchetes
    arq1 = "[DOCAN R5200]_1UN LONA 5.00X12.50M_CLIENTE_MONTAGEM_8pecas.pdf"
    assert rlhf.identificar_maquina_pelo_nome(arq1, maquinas) == "DOCAN R5200"

    arq2 = "[SWJ320A]_1UN LONA 3.20X8.00M_EVENTO_MONTAGEM_4pecas.pdf"
    assert rlhf.identificar_maquina_pelo_nome(arq2, maquinas) == "SWJ320A"

    arq3 = "[UJV 100]_1UN ADESIVO 1.20X3.00M_MONTAGEM_2pecas.pdf"
    assert rlhf.identificar_maquina_pelo_nome(arq3, maquinas) == "UJV 100 UNY CV"

    # Sem colchetes, no meio do nome
    arq4 = "1UN LONA 5.00X10.00M_DOCAN R5200_FOLHA_01.pdf"
    assert rlhf.identificar_maquina_pelo_nome(arq4, maquinas) == "DOCAN R5200"


def test_processar_artes_montadas_leva_direto_ao_rip(tmp_path):
    pasta_montadas = tmp_path / "ARTES MONTADAS"
    pasta_montadas.mkdir()

    hot_docan = tmp_path / "RIP_DOCAN"
    hot_docan.mkdir()

    hot_swj = tmp_path / "RIP_SWJ"
    hot_swj.mkdir()

    maquinas = {
        "DOCAN R5200": {"hot_folder": str(hot_docan)},
        "SWJ320A": {"hot_folder": str(hot_swj)},
    }

    # Cria folha simulada montada para a DOCAN
    folha_docan = pasta_montadas / "[DOCAN R5200]_1UN LONA 5.00X10.00M_FESTA_MONTAGEM_5pecas.pdf"
    folha_docan.write_bytes(b"%PDF-1.4 teste docan")

    # Cria folha simulada montada para a SWJ
    folha_swj = pasta_montadas / "[SWJ320A]_1UN LONA 3.20X6.00M_STAND_MONTAGEM_3pecas.pdf"
    folha_swj.write_bytes(b"%PDF-1.4 teste swj")

    logs = []
    resultado = rlhf.processar_artes_montadas_uma_vez(
        pasta_montadas=pasta_montadas,
        maquinas=maquinas,
        logger=lambda nivel, msg: logs.append((nivel, msg)),
        pasta_relatorios=tmp_path / "relatorios"
    )

    # Ambos devem ser enviados com sucesso
    assert len(resultado["enviados"]) == 2
    assert folha_docan.name in resultado["enviados"]
    assert folha_swj.name in resultado["enviados"]

    # Conferir se caíram nas Hot Folders corretas
    assert (hot_docan / folha_docan.name).is_file()
    assert (hot_swj / folha_swj.name).is_file()

    # Conferir se saíram da pasta principal e foram para 'Enviados'
    assert not folha_docan.exists()
    assert not folha_swj.exists()
    pasta_enviados = pasta_montadas / "Enviados"
    assert (pasta_enviados / folha_docan.name).is_file()
    assert (pasta_enviados / folha_swj.name).is_file()
