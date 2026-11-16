"""
Suíte de testes abrangente para o subsistema de hardware e drivers de RIP (ISSUE-11).
"""
import datetime
import json
import os
import pathlib
import shutil
import time
import pytest

import hardware
from hardware import (
    DriverByhx,
    DriverGenericoHotfolder,
    DriverRasterLink,
    DriverRip,
    DriverSaiProductionManager,
    EntregaResultado,
    GerenciadorHardware,
    MaquinaInfo,
    StatusFila,
    StatusTrabalho,
    obter_gerenciador_hardware,
)


# ============================================================================
# 1. TESTES DE MODELO (MaquinaInfo, EntregaResultado, StatusFila, StatusTrabalho)
# ============================================================================

def test_maquina_info_criacao_e_propriedades():
    # Máquina de Rolo
    m_rolo = MaquinaInfo(
        nome="Mimaki SWJ320",
        tipo="rolo",
        largura_util_m=3.24,
        largura_montagem_m=3.20,
        rip_tipo="rasterlink",
    )
    assert m_rolo.is_rolo is True
    assert m_rolo.is_mesa is False
    assert m_rolo.limite_largura == 3.24
    assert m_rolo.area_mesa_m2 is None
    assert "Rolo 3,24 m" in m_rolo.descricao_dimensoes

    # Máquina de Mesa Plana
    m_mesa = MaquinaInfo(
        nome="Docan H2525",
        tipo="mesa",
        mesa_util_m=(2.50, 2.50),
        rip_tipo="sai",
        setup_sai="Docan_H2525",
    )
    assert m_mesa.is_mesa is True
    assert m_mesa.is_rolo is False
    assert m_mesa.limite_largura == 2.50
    assert m_mesa.area_mesa_m2 == 6.25
    assert "Mesa 2,50 × 2,50 m" in m_mesa.descricao_dimensoes


def test_maquina_info_cabe():
    m_rolo = MaquinaInfo(nome="Rolo 3.2m", tipo="rolo", largura_util_m=3.20)
    # Cabe na largura normal
    assert m_rolo.cabe(3.0, 10.0) is True
    # Cabe girado
    assert m_rolo.cabe(10.0, 3.0) is True
    # Não cabe de nenhum lado
    assert m_rolo.cabe(3.5, 3.5) is False
    # Medida inválida
    assert m_rolo.cabe(0, 5.0) is False

    m_mesa = MaquinaInfo(nome="Mesa 2x3m", tipo="mesa", mesa_util_m=(2.0, 3.0))
    # Cabe normal
    assert m_mesa.cabe(1.8, 2.8) is True
    # Cabe girado
    assert m_mesa.cabe(2.8, 1.8) is True
    # Não cabe
    assert m_mesa.cabe(2.2, 3.2) is False


def test_maquina_info_serializacao_e_desserializacao():
    dados_originais = {
        "tipo": "mesa",
        "mesa_util_m": [2.5, 2.5],
        "hot_folder": r"C:\RIP\HotFolder",
        "pasta_entrada": r"C:\Fila\Entrada",
        "rip_tipo": "byhx",
        "posto": "sai",
        "montagem": True,
        "largura_montagem_m": 2.5,
        "margem_montagem_m": 0.02,
        "girar": False,
        "entrega_byhx": True,
        "ativo": True,
        "metadados": {"chave": "valor123"},
    }
    m = MaquinaInfo.from_dict("Docan H2525", dados_originais)
    assert m.nome == "Docan H2525"
    assert m.tipo == "mesa"
    assert m.mesa_util_m == (2.5, 2.5)
    assert m.rip_tipo == "byhx"
    assert m.girar is False
    assert m.entrega_byhx is True
    assert m.metadados == {"chave": "valor123"}

    d_exportado = m.to_dict()
    assert d_exportado["tipo"] == "mesa"
    assert d_exportado["mesa_util_m"] == [2.5, 2.5]
    assert d_exportado["rip_tipo"] == "byhx"
    assert d_exportado["metadados"] == {"chave": "valor123"}

    # Caso legado (apenas string com caminho da hot folder)
    m_legada = MaquinaInfo.from_dict("Legada", r"C:\MijCtrl\Hot\Legada")
    assert m_legada.nome == "Legada"
    assert m_legada.hot_folder == r"C:\MijCtrl\Hot\Legada"
    assert m_legada.rip_tipo == "rasterlink"  # inferido pelo MijCtrl


# ============================================================================
# 2. TESTES DE ENTREGA ATÔMICA SEGURA (DriverRip.entregar_arquivo)
# ============================================================================

def test_entrega_atomica_segura_sucesso(tmp_path):
    origem = tmp_path / "arte_producao.pdf"
    conteudo = b"%PDF-1.4 Dados binarios de teste de alta resolucao" * 1000
    origem.write_bytes(conteudo)

    hot_folder = tmp_path / "HotFolderRIP"
    hot_folder.mkdir()

    maquina = MaquinaInfo(nome="TesteMaq", hot_folder=str(hot_folder), rip_tipo="generico")
    driver = DriverGenericoHotfolder(maquina)

    resultado = driver.entregar_arquivo(origem)

    assert resultado.sucesso is True
    assert resultado.arquivo_destino == hot_folder / "arte_producao.pdf"
    assert resultado.arquivo_destino.is_file()
    assert resultado.arquivo_destino.read_bytes() == conteudo
    assert resultado.bytes_transferidos == len(conteudo)
    assert resultado.tempo_segundos >= 0.0

    # Garante que nenhum arquivo temporário residual (~montando~ ou .tmp) ficou na pasta
    arquivos_restantes = [f.name for f in hot_folder.iterdir()]
    assert arquivos_restantes == ["arte_producao.pdf"]


def test_entrega_atomica_cria_pasta_inexistente(tmp_path):
    origem = tmp_path / "trabalho.pdf"
    origem.write_bytes(b"conteudo")

    hot_folder = tmp_path / "subpasta" / "aninhada" / "hotfolder"
    maquina = MaquinaInfo(nome="TesteMaq", hot_folder=str(hot_folder))
    driver = DriverGenericoHotfolder(maquina)

    resultado = driver.entregar_arquivo(origem)
    assert resultado.sucesso is True
    assert hot_folder.is_dir()
    assert (hot_folder / "trabalho.pdf").exists()


def test_entrega_atomica_origem_inexistente(tmp_path):
    origem_fantasma = tmp_path / "nao_existe.pdf"
    hot_folder = tmp_path / "hotfolder"
    hot_folder.mkdir()

    maquina = MaquinaInfo(nome="TesteMaq", hot_folder=str(hot_folder))
    driver = DriverGenericoHotfolder(maquina)

    resultado = driver.entregar_arquivo(origem_fantasma)
    assert resultado.sucesso is False
    assert "não encontrado" in resultado.mensagem


def test_entrega_atomica_com_nome_personalizado(tmp_path):
    origem = tmp_path / "temp_12345.pdf"
    origem.write_bytes(b"conteudo")
    hot_folder = tmp_path / "hotfolder"
    hot_folder.mkdir()

    maquina = MaquinaInfo(nome="TesteMaq", hot_folder=str(hot_folder))
    driver = DriverGenericoHotfolder(maquina)

    resultado = driver.entregar_arquivo(
        origem, metadados={"nome_destino": "OS_9999_Lona_5x2m.pdf"}
    )
    assert resultado.sucesso is True
    assert resultado.arquivo_destino.name == "OS_9999_Lona_5x2m.pdf"
    assert resultado.arquivo_destino.exists()


# ============================================================================
# 3. TESTES DOS DRIVERS ESPECÍFICOS (Generico, RasterLink, SAi, BYHX)
# ============================================================================

def test_driver_generico_validacao_e_status(tmp_path):
    hf = tmp_path / "hot_generico"
    hf.mkdir()

    # Cria arquivos simulando fila pendente e concluída
    (hf / "arte1.pdf").write_bytes(b"123")
    (hf / "arte2.tif").write_bytes(b"4567")
    (hf / "~montando~temp.tmp").write_bytes(b"999")  # deve ser ignorado no status

    pasta_done = hf / "Done"
    pasta_done.mkdir()
    (pasta_done / "arte_antiga.pdf").write_bytes(b"abc")

    maquina = MaquinaInfo(nome="Caldera_Roll", hot_folder=str(hf), rip_tipo="generico")
    driver = DriverGenericoHotfolder(maquina)

    assert driver.validar_conexao() is True

    status = driver.obter_status()
    assert status.online is True
    assert status.pasta_acessivel is True
    assert status.total_pendentes == 2
    assert {t.nome_arquivo for t in status.trabalhos} == {"arte1.pdf", "arte2.tif"}

    concluidos = driver.detectar_conclusao()
    assert len(concluidos) == 1
    assert concluidos[0].nome_arquivo == "arte_antiga.pdf"
    assert concluidos[0].estado == "concluido"


def test_driver_generico_pasta_invalida(tmp_path):
    hf = tmp_path / "nao_existe"
    maquina = MaquinaInfo(nome="Onyx", hot_folder=str(hf), rip_tipo="generico")
    driver = DriverGenericoHotfolder(maquina)

    assert driver.validar_conexao() is False
    status = driver.obter_status()
    assert status.online is False
    assert status.pasta_acessivel is False


def test_driver_rasterlink_sanitizacao_e_extensoes(tmp_path):
    hf = tmp_path / "MijCtrl" / "Hot" / "UJV100"
    hf.mkdir(parents=True)

    maquina = MaquinaInfo(nome="UJV100", hot_folder=str(hf), rip_tipo="rasterlink")
    driver = DriverRasterLink(maquina)

    assert driver.validar_conexao() is True

    # Teste de sanitização de caracteres inválidos
    nome_sujo = "Arte #01 <Especial> % 50% & Lona.Final.pdf"
    nome_limpo = driver.sanitizar_nome_arquivo(nome_sujo)
    assert "<" not in nome_limpo
    assert ">" not in nome_limpo
    assert "%" not in nome_limpo
    assert "#" not in nome_limpo
    assert "&" not in nome_limpo
    assert nome_limpo.endswith(".pdf")

    # Extensão aceita
    origem_pdf = tmp_path / "teste.pdf"
    origem_pdf.write_bytes(b"%PDF...")
    res_pdf = driver.entregar_arquivo(origem_pdf)
    assert res_pdf.sucesso is True

    # Extensão recusada pelo RasterLink
    origem_doc = tmp_path / "instrucoes.docx"
    origem_doc.write_bytes(b"PK...")
    res_doc = driver.entregar_arquivo(origem_doc)
    assert res_doc.sucesso is False
    assert "não suportada pelo Mimaki RasterLink" in res_doc.mensagem


def test_driver_rasterlink_status_e_conclusao(tmp_path):
    pe = tmp_path / "FilaEntrada"
    pe.mkdir()
    pasta_env = pe / "Enviados"
    pasta_env.mkdir()
    (pasta_env / "trabalho_entregue.pdf").write_bytes(b"pronto")

    hf = tmp_path / "MijCtrl_Hot"
    hf.mkdir()
    (hf / "aguardando.pdf").write_bytes(b"no spool")

    maquina = MaquinaInfo(
        nome="SWJ320",
        hot_folder=str(hf),
        pasta_entrada=str(pe),
        rip_tipo="rasterlink",
    )
    driver = DriverRasterLink(maquina)

    status = driver.obter_status()
    assert status.online is True
    assert status.total_pendentes == 1
    assert status.trabalhos[0].nome_arquivo == "aguardando.pdf"

    concluidos = driver.detectar_conclusao()
    assert len(concluidos) == 1
    assert concluidos[0].nome_arquivo == "trabalho_entregue.pdf"


def test_driver_sai_setups_e_status(tmp_path):
    hf = tmp_path / "SAi_Jobs" / "Docan"
    hf.mkdir(parents=True)
    (hf / "lona_5x2m.pdf").write_bytes(b"pdf dados")

    maquina = MaquinaInfo(
        nome="DOCAN R5200",
        hot_folder=str(hf),
        rip_tipo="sai",
        setup_sai="Docan",
    )
    driver = DriverSaiProductionManager(maquina)

    assert driver.validar_conexao() is True
    status = driver.obter_status()
    assert status.online is True
    assert status.total_pendentes == 1
    assert status.metadados["setup_sai"] == "Docan"


def test_driver_byhx_log_e_xml(tmp_path):
    pasta_byhx = tmp_path / "PrinterManager"
    pasta_byhx.mkdir()

    # Simula PrintedArea.Log real
    log_content = (
        "[2026-10-01 10:15:30.100][TID 1234] D:\\RIPADOS\\PAINEL_TESTE.prt; "
        "10/1/2026-10:00 AM; 0:15:30; 100; 5.25 m2\n"
    )
    (pasta_byhx / "PrintedArea.Log").write_text(log_content, encoding="utf-8")

    # Simula Joblist_His.xml com dois elementos raiz (formato do BYHX)
    xml_content = (
        '\ufeff<Hash CRCVers="V1.0">1234ABCD</Hash>\n'
        "<JobList>\n"
        "  <UIJob>\n"
        "    <JobStatus>Printed</JobStatus>\n"
        "    <string>FACHADA_ACRILICO.prt</string>\n"
        "    <int>1</int>\n"
        "    <dateTime>2026-10-01T11:20:00</dateTime>\n"
        "    <string>D:\\RIPADOS\\FACHADA_ACRILICO.prt</string>\n"
        "    <float>98.4251969</float>\n"
        "    <float>78.7401575</float>\n"
        "  </UIJob>\n"
        "</JobList>\n"
    )
    (pasta_byhx / "Joblist_His.xml").write_text(xml_content, encoding="utf-8")

    maquina = MaquinaInfo(
        nome="DOCAN H2525",
        hot_folder=str(pasta_byhx),
        rip_tipo="byhx",
    )
    driver = DriverByhx(maquina, pasta_programa=pasta_byhx)

    assert driver.validar_conexao() is True

    # Teste de validação de extensão .prt/.prn
    origem_invalida = tmp_path / "arte.pdf"
    origem_invalida.write_bytes(b"pdf")
    res_invalida = driver.entregar_arquivo(origem_invalida)
    assert res_invalida.sucesso is False
    assert ".prt ou .prn" in res_invalida.mensagem

    origem_prt = tmp_path / "novo_job.prt"
    origem_prt.write_bytes(b"dados binarios de impressao")
    res_prt = driver.entregar_arquivo(origem_prt)
    assert res_prt.sucesso is True

    # Detectar conclusão a partir do log e do xml
    concluidos = driver.detectar_conclusao()
    assert len(concluidos) == 2
    nomes = {c.nome_arquivo for c in concluidos}
    assert "PAINEL_TESTE.prt" in nomes
    assert "FACHADA_ACRILICO.prt" in nomes

    # Confere dados da passada no log
    item_log = next(c for c in concluidos if c.nome_arquivo == "PAINEL_TESTE.prt")
    assert item_log.metadados["segundos_impressao"] == 15 * 60 + 30
    assert item_log.metadados["area_m2"] == 5.25


# ============================================================================
# 4. TESTES DO GERENCIADOR DE HARDWARE (GerenciadorHardware & Fábrica)
# ============================================================================

def test_gerenciador_fabrica_de_drivers():
    gerenciador = GerenciadorHardware(carregar_automatico=False)

    m1 = MaquinaInfo(nome="M1", rip_tipo="generico")
    m2 = MaquinaInfo(nome="M2", rip_tipo="rasterlink")
    m3 = MaquinaInfo(nome="M3", rip_tipo="sai")
    m4 = MaquinaInfo(nome="M4", rip_tipo="byhx")

    assert isinstance(gerenciador.obter_driver(m1), DriverGenericoHotfolder)
    assert isinstance(gerenciador.obter_driver(m2), DriverRasterLink)
    assert isinstance(gerenciador.obter_driver(m3), DriverSaiProductionManager)
    assert isinstance(gerenciador.obter_driver(m4), DriverByhx)


def test_gerenciador_crud_e_padroes(tmp_path):
    config_path = tmp_path / "config_teste.json"
    gerenciador = GerenciadorHardware(caminho_config=config_path, carregar_automatico=False)

    # Restaura padrões de fábrica
    padroes = gerenciador.restaurar_padroes(persistir=True)
    assert len(padroes) >= 4
    assert "SWJ320A" in padroes
    assert "UJV 100 UNY CV" in padroes
    assert "DOCAN R5200" in padroes
    assert "DOCAN H2525" in padroes
    assert config_path.is_file()

    # Cadastra nova máquina
    nova = MaquinaInfo(
        nome="Nova Plotter UV",
        tipo="rolo",
        largura_util_m=1.80,
        hot_folder=str(tmp_path / "nova_hf"),
        rip_tipo="generico",
    )
    gerenciador.cadastrar_maquina(nova, persistir=True)
    assert gerenciador.obter_maquina("Nova Plotter UV") is not None

    # Atualiza / renomeia máquina
    nova_editada = MaquinaInfo(
        nome="Nova Plotter UV v2",
        tipo="rolo",
        largura_util_m=1.90,
        hot_folder=str(tmp_path / "nova_hf"),
        rip_tipo="generico",
    )
    gerenciador.atualizar_maquina("Nova Plotter UV", nova_editada, persistir=True)
    assert gerenciador.obter_maquina("Nova Plotter UV") is None
    assert gerenciador.obter_maquina("Nova Plotter UV v2") is not None
    assert gerenciador.obter_maquina("Nova Plotter UV v2").largura_util_m == 1.90

    # Remove máquina
    removido = gerenciador.remover_maquina("Nova Plotter UV v2", persistir=True)
    assert removido is True
    assert gerenciador.obter_maquina("Nova Plotter UV v2") is None


def test_gerenciador_persistencia_relacional_sqlite(tmp_path):
    config_path = tmp_path / "config.json"
    banco_path = tmp_path / "dados_teste.db"

    gerenciador = GerenciadorHardware(
        caminho_config=config_path,
        caminho_banco=banco_path,
        carregar_automatico=False,
    )

    m = MaquinaInfo(
        nome="Docan H2525 Teste",
        tipo="mesa",
        mesa_util_m=(2.50, 2.50),
        hot_folder=str(tmp_path / "docan_hf"),
        rip_tipo="sai",
        posto="sai",
        setup_sai="Docan_H2525",
        montagem=True,
        margem_montagem_m=0.02,
        girar=False,
        entrega_byhx=True,
    )
    gerenciador.cadastrar_maquina(m, persistir=True)

    # Verifica persistência no banco relacional
    import banco
    repo = banco.obter_repositorio_maquinas(banco_path)
    salva = repo.obter_maquina("Docan H2525 Teste")

    assert salva is not None
    assert salva["nome"] == "Docan H2525 Teste"
    assert salva["tipo"] == "mesa"
    assert salva["mesa_largura_m"] == 2.50
    assert salva["mesa_altura_m"] == 2.50
    assert salva["setup_sai"] == "Docan_H2525"
    assert salva["girar"] == 0
    assert salva["entrega_byhx"] == 1


def test_gerenciador_operacoes_alto_nivel(tmp_path):
    hf = tmp_path / "hot_operacoes"
    hf.mkdir()

    config_path = tmp_path / "config.json"
    gerenciador = GerenciadorHardware(caminho_config=config_path, carregar_automatico=False)

    m = MaquinaInfo(nome="ImpressoraAuto", hot_folder=str(hf), rip_tipo="generico")
    gerenciador.cadastrar_maquina(m, persistir=False)

    # Validar conexão
    assert gerenciador.validar_conexao("ImpressoraAuto") is True

    # Entregar arquivo
    origem = tmp_path / "job_automatico.pdf"
    origem.write_bytes(b"%PDF...")
    res = gerenciador.entregar("ImpressoraAuto", origem)
    assert res.sucesso is True
    assert (hf / "job_automatico.pdf").exists()

    # Obter status
    status = gerenciador.obter_status_fila("ImpressoraAuto")
    assert status.online is True
    assert status.total_pendentes == 1

    status_todas = gerenciador.obter_status_todas()
    assert "ImpressoraAuto" in status_todas


def test_facade_hardware_raiz():
    # Testa se a fachada hardware.py exporta todos os componentes requeridos
    assert hasattr(hardware, "GerenciadorHardware")
    assert hasattr(hardware, "DriverRip")
    assert hasattr(hardware, "MaquinaInfo")
    assert hasattr(hardware, "EntregaResultado")
    assert hasattr(hardware, "StatusFila")
    assert hasattr(hardware, "StatusTrabalho")
    assert hasattr(hardware, "obter_gerenciador_hardware")
    assert hasattr(hardware, "DriverGenericoHotfolder")
    assert hasattr(hardware, "DriverRasterLink")
    assert hasattr(hardware, "DriverSaiProductionManager")
    assert hasattr(hardware, "DriverByhx")

    instancia = hardware.obter_gerenciador_hardware()
    assert isinstance(instancia, hardware.GerenciadorHardware)
