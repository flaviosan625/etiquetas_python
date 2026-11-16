"""
Testes abrangentes do sistema de licenciamento criptográfico autônomo (ISSUE-14).
Cobre:
- Estabilidade e formato de Machine ID (Hardware ID).
- Emissão e validação com curva Ed25519.
- Rejeição de cópia de licença para outro hardware.
- Rejeição de licença expirada.
- Rejeição de adulteração de payload ou corrupção de assinatura.
- Detecção e proteção contra manipulação temporal de relógio (anti-clock tampering).
- Ciclo de vida completo do modo Trial de 14 dias (ativo, dias decrescentes e expirado).
- Licença perpétua e tipos de licença.
- Emissão e chave via CLI.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from ferramentas.emissor_licenca import emitir_licenca, gerar_par_chaves, main as cli_main
from licenciamento.hardware_id import (
    obter_hardware_id,
    obter_mac_address,
    obter_machine_guid,
    obter_volume_serial,
    validar_formato_hardware_id,
)
from licenciamento.validador import DadosLicenca, StatusLicenca, ValidadorLicenca


def test_hardware_id_formato_e_estabilidade():
    """Valida se o Hardware ID é estável, determinístico e segue CV-XXXX-XXXX-XXXX."""
    hw1 = obter_hardware_id()
    hw2 = obter_hardware_id()

    assert hw1 == hw2, "Hardware ID deve ser estável e determinístico em múltiplas chamadas"
    assert validar_formato_hardware_id(hw1), f"Formato inválido: {hw1}"
    assert hw1.startswith("CV-")
    partes = hw1.split("-")
    assert len(partes) == 4
    for p in partes[1:]:
        assert len(p) == 4
        int(p, 16)  # Deve ser hexadecimal válido

    # Componentes individuais
    assert isinstance(obter_machine_guid(), str)
    assert isinstance(obter_volume_serial(), str)
    assert isinstance(obter_mac_address(), str)

    # Teste com semente customizada (para simulação de hardware em testes)
    hw_sim1 = obter_hardware_id(custom_seed="MAQUINA_A")
    hw_sim2 = obter_hardware_id(custom_seed="MAQUINA_A")
    hw_sim3 = obter_hardware_id(custom_seed="MAQUINA_B")

    assert hw_sim1 == hw_sim2
    assert hw_sim1 != hw_sim3
    assert validar_formato_hardware_id(hw_sim1)


def test_emissao_e_validacao_sucesso(tmp_path: Path):
    """Testa o ciclo de emissão e validação bem-sucedida de licença comercial."""
    priv_b64, pub_b64 = gerar_par_chaves()
    hw_id = "CV-1234-5678-ABCD"

    licenca_str = emitir_licenca(
        cliente="Gráfica e Comunicação Visual Express",
        machine_id=hw_id,
        dias_validade=30,
        modulos=["corte", "impressao", "montagem"],
        max_impressoras=3,
        tipo="MENSAL",
        chave_privada=priv_b64,
    )

    lic_path = tmp_path / "licenca.lic"
    lic_path.write_text(licenca_str, encoding="utf-8")

    validador = ValidadorLicenca(
        chave_publica=pub_b64,
        caminho_estado=tmp_path / ".lic_state",
        caminho_licenca=lic_path,
        hardware_id_override=hw_id,
    )

    status = validador.validar_arquivo()

    assert status.valida is True
    assert status.estado == "LICENCIADO"
    assert status.dias_restantes >= 29
    assert status.dados is not None
    assert status.dados.cliente == "Gráfica e Comunicação Visual Express"
    assert status.dados.machine_id == hw_id
    assert status.dados.modulos == ["corte", "impressao", "montagem"]
    assert status.dados.max_impressoras == 3
    assert status.dados.tipo == "MENSAL"


def test_rejeicao_hardware_diferente(tmp_path: Path):
    """Garante que licença copiada para outra máquina seja sumariamente rejeitada."""
    priv_b64, pub_b64 = gerar_par_chaves()
    hw_original = "CV-1111-2222-3333"
    hw_invasor = "CV-9999-8888-7777"

    licenca_str = emitir_licenca(
        cliente="Cliente Pirata",
        machine_id=hw_original,
        dias_validade=365,
        tipo="ANUAL",
        chave_privada=priv_b64,
    )

    lic_path = tmp_path / "licenca.lic"
    lic_path.write_text(licenca_str, encoding="utf-8")

    # Executa na máquina invasora
    validador = ValidadorLicenca(
        chave_publica=pub_b64,
        caminho_estado=tmp_path / ".lic_state",
        caminho_licenca=lic_path,
        hardware_id_override=hw_invasor,
    )

    status = validador.validar_arquivo()
    assert status.valida is False
    assert status.estado == "INVALIDO_HARDWARE"
    assert "não autorizada para este computador" in status.mensagem


def test_licenca_universal_wildcard(tmp_path: Path):
    """Testa licença com machine_id '*' que deve ser válida em qualquer máquina."""
    priv_b64, pub_b64 = gerar_par_chaves()

    licenca_str = emitir_licenca(
        cliente="Licença Desenvolvedor",
        machine_id="*",
        dias_validade=100,
        tipo="ANUAL",
        chave_privada=priv_b64,
    )

    lic_path = tmp_path / "licenca.lic"
    lic_path.write_text(licenca_str, encoding="utf-8")

    validador = ValidadorLicenca(
        chave_publica=pub_b64,
        caminho_estado=tmp_path / ".lic_state",
        caminho_licenca=lic_path,
        hardware_id_override="CV-QUAL-QUER-MAQU",
    )

    status = validador.validar_arquivo()
    assert status.valida is True
    assert status.estado == "LICENCIADO"


def test_rejeicao_licenca_expirada(tmp_path: Path):
    """Testa rejeição imediata quando a data de validade é ultrapassada."""
    priv_b64, pub_b64 = gerar_par_chaves()
    hw_id = "CV-AAAA-BBBB-CCCC"

    agora = datetime.now()
    passado = agora - timedelta(days=60)

    # Emitida no passado com validade de 30 dias (já expirou há 30 dias)
    licenca_str = emitir_licenca(
        cliente="Cliente Vencido",
        machine_id=hw_id,
        dias_validade=30,
        tipo="MENSAL",
        chave_privada=priv_b64,
        emissao_override=passado,
    )

    lic_path = tmp_path / "licenca.lic"
    lic_path.write_text(licenca_str, encoding="utf-8")

    validador = ValidadorLicenca(
        chave_publica=pub_b64,
        caminho_estado=tmp_path / ".lic_state",
        caminho_licenca=lic_path,
        hardware_id_override=hw_id,
    )

    status = validador.validar_arquivo(agora_override=agora)
    assert status.valida is False
    assert status.estado == "EXPIRADO"
    assert status.dias_restantes == 0
    assert "expirada" in status.mensagem.lower()


def test_rejeicao_payload_adulterado(tmp_path: Path):
    """Testa que adulterar qualquer campo no JSON quebra a assinatura Ed25519."""
    priv_b64, pub_b64 = gerar_par_chaves()
    hw_id = "CV-AAAA-BBBB-CCCC"

    licenca_str = emitir_licenca(
        cliente="Cliente Honesto",
        machine_id=hw_id,
        dias_validade=30,
        modulos=["impressao"],
        max_impressoras=1,
        tipo="MENSAL",
        chave_privada=priv_b64,
    )

    doc = json.loads(licenca_str)

    # Tentativa de fraude 1: Usuário tenta alterar a data para 2099 no payload_raw
    p_raw_dict = json.loads(doc["payload_raw"])
    p_raw_dict["valido_ate"] = "2099-12-31"
    doc_adulterado1 = dict(doc)
    doc_adulterado1["payload_raw"] = json.dumps(p_raw_dict, sort_keys=True, separators=(",", ":"))

    lic_path1 = tmp_path / "licenca_fraude1.lic"
    lic_path1.write_text(json.dumps(doc_adulterado1), encoding="utf-8")

    validador = ValidadorLicenca(
        chave_publica=pub_b64,
        caminho_estado=tmp_path / ".lic_state",
        caminho_licenca=lic_path1,
        hardware_id_override=hw_id,
    )

    status1 = validador.validar_arquivo()
    assert status1.valida is False
    assert status1.estado == "ASSINATURA_INVALIDA"

    # Tentativa de fraude 2: Usuário adultera a assinatura
    doc_adulterado2 = dict(doc)
    doc_adulterado2["signature"] = "A" * len(doc["signature"])

    lic_path2 = tmp_path / "licenca_fraude2.lic"
    lic_path2.write_text(json.dumps(doc_adulterado2), encoding="utf-8")

    validador.caminho_licenca = lic_path2
    status2 = validador.validar_arquivo()
    assert status2.valida is False
    assert status2.estado == "ASSINATURA_INVALIDA"


def test_anti_clock_tampering(tmp_path: Path):
    """Valida a detecção de recuo proposital do relógio do sistema."""
    priv_b64, pub_b64 = gerar_par_chaves()
    hw_id = "CV-RELOGIO-TEST"

    licenca_str = emitir_licenca(
        cliente="Cliente Relógio",
        machine_id=hw_id,
        dias_validade=30,
        tipo="MENSAL",
        chave_privada=priv_b64,
    )

    lic_path = tmp_path / "licenca.lic"
    lic_path.write_text(licenca_str, encoding="utf-8")

    validador = ValidadorLicenca(
        chave_publica=pub_b64,
        caminho_estado=tmp_path / ".lic_state",
        caminho_licenca=lic_path,
        hardware_id_override=hw_id,
    )

    t0 = datetime(2026, 11, 16, 12, 0, 0)
    # Validação inicial em t0
    st0 = validador.validar_arquivo(agora_override=t0)
    assert st0.valida is True
    assert st0.estado == "LICENCIADO"

    # Avanço normal no tempo (+2 horas)
    t1 = t0 + timedelta(hours=2)
    st1 = validador.validar_arquivo(agora_override=t1)
    assert st1.valida is True

    # Tolerância de até 10 minutos para trás (ex: ajuste NTP de 5 minutos)
    t_ntp = t1 - timedelta(minutes=5)
    st_ntp = validador.validar_arquivo(agora_override=t_ntp)
    assert st_ntp.valida is True

    # Fraude: Usuário volta o relógio em 2 horas (-120 min > 10 min tolerância)
    t_fraude = t1 - timedelta(hours=2)
    st_fraude = validador.validar_arquivo(agora_override=t_fraude)
    assert st_fraude.valida is False
    assert st_fraude.estado == "RELOGIO_ADULTERADO"
    assert "retrocedido" in st_fraude.mensagem.lower()


def test_ciclo_de_vida_trial_14_dias(tmp_path: Path):
    """Testa o ciclo autônomo do Modo Trial de 14 dias sem arquivo de licença."""
    priv_b64, pub_b64 = gerar_par_chaves()
    hw_id = "CV-TRIAL-MAQU-INA1"

    validador = ValidadorLicenca(
        chave_publica=pub_b64,
        caminho_estado=tmp_path / ".lic_state",
        caminho_licenca=tmp_path / "arquivo_inexistente.lic",
        hardware_id_override=hw_id,
    )

    # Dia 0: Primeiro acesso
    t0 = datetime(2026, 11, 16, 10, 0, 0)
    st0 = validador.validar_arquivo(agora_override=t0)
    assert st0.valida is True
    assert st0.estado == "TRIAL_ATIVO"
    assert st0.dias_restantes == 14
    assert st0.dados is not None
    assert st0.dados.tipo == "TRIAL"
    assert st0.dados.modulos == ["*"]

    # Dia 5: Restam 9 dias
    t5 = t0 + timedelta(days=5)
    st5 = validador.validar_arquivo(agora_override=t5)
    assert st5.valida is True
    assert st5.estado == "TRIAL_ATIVO"
    assert st5.dias_restantes == 9

    # Dia 13: Último dia restante
    t13 = t0 + timedelta(days=13)
    st13 = validador.validar_arquivo(agora_override=t13)
    assert st13.valida is True
    assert st13.estado == "TRIAL_ATIVO"
    assert st13.dias_restantes == 1

    # Dia 15: Expirado (> 14 dias)
    t15 = t0 + timedelta(days=15)
    st15 = validador.validar_arquivo(agora_override=t15)
    assert st15.valida is False
    assert st15.estado == "TRIAL_EXPIRADO"
    assert st15.dias_restantes == 0
    assert "expirado" in st15.mensagem.lower()

    # Recuo de relógio durante o trial
    t_tamper = t0 + timedelta(days=2)  # Tentou voltar de 15 para 2
    st_tamper = validador.validar_arquivo(agora_override=t_tamper)
    assert st_tamper.valida is False
    assert st_tamper.estado == "RELOGIO_ADULTERADO"


def test_licenca_perpetua(tmp_path: Path):
    """Testa licença vitalícia/perpétua que nunca expira."""
    priv_b64, pub_b64 = gerar_par_chaves()
    hw_id = "CV-PERP-ETUA-0001"

    licenca_str = emitir_licenca(
        cliente="Cliente Vitalício",
        machine_id=hw_id,
        tipo="PERPETUA",
        chave_privada=priv_b64,
    )

    lic_path = tmp_path / "perpetua.lic"
    lic_path.write_text(licenca_str, encoding="utf-8")

    validador = ValidadorLicenca(
        chave_publica=pub_b64,
        caminho_estado=tmp_path / ".lic_state",
        caminho_licenca=lic_path,
        hardware_id_override=hw_id,
    )

    status = validador.validar_arquivo()
    assert status.valida is True
    assert status.estado == "LICENCIADO"
    assert status.dias_restantes == 99999
    assert status.dados.tipo == "PERPETUA"


def test_cli_emissor(tmp_path: Path, monkeypatch, capsys):
    """Testa a interface de linha de comando (CLI) do emissor de licenças."""
    # 1. Testar hardware-id
    monkeypatch.setattr("sys.argv", ["emissor_licenca.py", "hardware-id"])
    codigo = cli_main()
    assert codigo == 0
    saida = capsys.readouterr().out
    assert "Hardware ID: CV-" in saida

    # 2. Testar gerar-chaves
    priv_file = tmp_path / "chave.priv"
    pub_file = tmp_path / "chave.pub"
    monkeypatch.setattr(
        "sys.argv",
        [
            "emissor_licenca.py",
            "gerar-chaves",
            "--saida-priv",
            str(priv_file),
            "--saida-pub",
            str(pub_file),
        ],
    )
    codigo = cli_main()
    assert codigo == 0
    assert priv_file.exists()
    assert pub_file.exists()
    priv_key = priv_file.read_text(encoding="utf-8").strip()
    pub_key = pub_file.read_text(encoding="utf-8").strip()

    # 3. Testar emitir licença via CLI
    lic_out = tmp_path / "saida_cli.lic"
    monkeypatch.setattr(
        "sys.argv",
        [
            "emissor_licenca.py",
            "emitir",
            "--cliente",
            "Empresa Teste CLI",
            "--machine-id",
            "CV-9999-AAAA-BBBB",
            "--dias",
            "60",
            "--modulos",
            "corte,impressao",
            "--max-impressoras",
            "2",
            "--tipo",
            "MENSAL",
            "--chave-privada",
            str(priv_file),
            "--saida",
            str(lic_out),
        ],
    )
    codigo = cli_main()
    assert codigo == 0
    assert lic_out.exists()

    validador = ValidadorLicenca(
        chave_publica=pub_key,
        caminho_estado=tmp_path / ".lic_state_cli",
        caminho_licenca=lic_out,
        hardware_id_override="CV-9999-AAAA-BBBB",
    )
    status = validador.validar_arquivo()
    assert status.valida is True
    assert status.dados.cliente == "Empresa Teste CLI"
    assert status.dados.modulos == ["corte", "impressao"]
