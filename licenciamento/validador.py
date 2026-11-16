"""
Módulo validador de licenças criptográficas baseado na curva assimétrica Ed25519.
Inclui amarração ao Machine ID, proteção contra retrocesso de relógio (anti-clock tampering)
e gerenciador autônomo de modo Trial de 14 dias.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

from licenciamento.hardware_id import obter_hardware_id

# Chave pública mestra oficial padrão (Raw 32 bytes em Base64)
CHAVE_MESTRA_PUBLICA_PADRAO = "7KONMjQpcxIR6zIyn6Kon/mZnk06Na/XtpuImlg3788="

# Tolerância máxima permitida para relógio atrasado (em segundos)
TOLERANCIA_RELOGIO_SEGUNDOS = 600.0  # 10 minutos
DURACAO_TRIAL_DIAS = 14


@dataclass
class DadosLicenca:
    cliente: str
    machine_id: str
    valido_ate: str
    modulos: List[str] = field(default_factory=list)
    max_impressoras: int = 1
    tipo: str = "ANUAL"  # MENSAL, ANUAL, PERPETUA, TRIAL
    emissao: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cliente": self.cliente,
            "machine_id": self.machine_id,
            "valido_ate": self.valido_ate,
            "modulos": sorted(self.modulos),
            "max_impressoras": self.max_impressoras,
            "tipo": self.tipo,
            "emissao": self.emissao,
            "extra": self.extra,
        }


@dataclass
class StatusLicenca:
    valida: bool
    estado: str  # LICENCIADO, TRIAL_ATIVO, TRIAL_EXPIRADO, EXPIRADO, INVALIDO_HARDWARE, ASSINATURA_INVALIDA, RELOGIO_ADULTERADO
    dias_restantes: int
    mensagem: str
    dados: Optional[DadosLicenca] = None


class ValidadorLicenca:
    """
    Validador criptográfico de licenças do sistema.
    """

    def __init__(
        self,
        chave_publica: Optional[Union[str, ed25519.Ed25519PublicKey]] = None,
        caminho_estado: Optional[Union[str, Path]] = None,
        caminho_licenca: Optional[Union[str, Path]] = None,
        hardware_id_override: Optional[str] = None,
    ):
        self.hardware_id_override = hardware_id_override
        self.caminho_estado = (
            Path(caminho_estado) if caminho_estado else Path(".lic_state")
        )
        self.caminho_licenca = (
            Path(caminho_licenca) if caminho_licenca else Path("licenca.lic")
        )
        self.chave_publica = self._carregar_chave_publica(chave_publica)

    def obter_hardware_id_atual(self) -> str:
        if self.hardware_id_override:
            return self.hardware_id_override
        return obter_hardware_id()

    def _carregar_chave_publica(
        self, chave: Optional[Union[str, ed25519.Ed25519PublicKey]]
    ) -> ed25519.Ed25519PublicKey:
        if isinstance(chave, ed25519.Ed25519PublicKey):
            return chave

        chave_str = (chave or CHAVE_MESTRA_PUBLICA_PADRAO).strip()

        # Tenta decodificar Base64 (32 bytes raw)
        try:
            dados = base64.b64decode(chave_str)
            if len(dados) == 32:
                return ed25519.Ed25519PublicKey.from_public_bytes(dados)
        except Exception:
            pass

        # Tenta decodificar Hexadecimal (64 caracteres)
        try:
            dados = bytes.fromhex(chave_str)
            if len(dados) == 32:
                return ed25519.Ed25519PublicKey.from_public_bytes(dados)
        except Exception:
            pass

        # Tenta decodificar PEM SubjectPublicKeyInfo
        try:
            return serialization.load_pem_public_key(chave_str.encode("utf-8"))  # type: ignore
        except Exception as e:
            raise ValueError(f"Chave pública Ed25519 inválida ou formato não reconhecido: {e}")

    def _gerar_hmac_estado(self, payload_dict: Dict[str, Any]) -> str:
        """Gera HMAC de integridade para o arquivo de estado local."""
        chave_segredo = self.obter_hardware_id_atual().encode("utf-8")
        corpo = json.dumps(payload_dict, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hmac.new(chave_segredo, corpo, hashlib.sha256).hexdigest()

    def _carregar_estado(self) -> Dict[str, Any]:
        """Carrega e valida o arquivo de estado local."""
        if not self.caminho_estado.exists():
            return {}

        try:
            with open(self.caminho_estado, "r", encoding="utf-8") as f:
                dados = json.load(f)

            hmac_armazenado = dados.get("hmac", "")
            dados_sem_hmac = {k: v for k, v in dados.items() if k != "hmac"}
            hmac_calculado = self._gerar_hmac_estado(dados_sem_hmac)

            if not hmac.compare_digest(hmac_armazenado, hmac_calculado):
                # Estado violado
                return {"_corrompido": True}

            return dados_sem_hmac
        except Exception:
            return {"_corrompido": True}

    def _salvar_estado(self, estado: Dict[str, Any]) -> None:
        """Salva o estado local com selo criptográfico HMAC."""
        dados_sem_hmac = {k: v for k, v in estado.items() if k != "hmac" and k != "_corrompido"}
        hmac_sig = self._gerar_hmac_estado(dados_sem_hmac)
        dados_para_salvar = dict(dados_sem_hmac)
        dados_para_salvar["hmac"] = hmac_sig

        self.caminho_estado.parent.mkdir(parents=True, exist_ok=True)
        with open(self.caminho_estado, "w", encoding="utf-8") as f:
            json.dump(dados_para_salvar, f, indent=2)

    def _verificar_relogio_e_atualizar(self, agora_ts: float) -> bool:
        """
        Verifica proteção anti-adulteração de relógio (anti-clock tampering).
        Retorna True se relógio é válido, False se foi adulterado para o passado.
        """
        estado = self._carregar_estado()

        if estado.get("_corrompido"):
            # Se o arquivo foi corrompido ou adulterado manualmente
            return False

        ultimo_ts = estado.get("ultimo_timestamp")
        if ultimo_ts is not None:
            # Se o relógio do sistema está mais de 10 minutos atrás do último timestamp registrado
            if agora_ts < (ultimo_ts - TOLERANCIA_RELOGIO_SEGUNDOS):
                return False

        # Atualiza o timestamp (se o novo for maior, avançamos)
        novo_ts = max(ultimo_ts or agora_ts, agora_ts)
        estado["ultimo_timestamp"] = novo_ts
        self._salvar_estado(estado)
        return True

    def _processar_trial(self, agora_dt: datetime) -> StatusLicenca:
        """Gerencia o ciclo de vida do Modo Trial autônomo de 14 dias."""
        agora_ts = agora_dt.timestamp()
        hw_id = self.obter_hardware_id_atual()
        estado = self._carregar_estado()

        if estado.get("_corrompido"):
            return StatusLicenca(
                valida=False,
                estado="RELOGIO_ADULTERADO",
                dias_restantes=0,
                mensagem="Arquivo de integridade do sistema violado ou adulterado.",
            )

        trial_inicio = estado.get("trial_inicio")
        trial_fim = estado.get("trial_fim")

        if trial_inicio is None or trial_fim is None:
            # Primeiro uso: inicializa trial de 14 dias
            trial_inicio = agora_ts
            trial_fim = agora_ts + (DURACAO_TRIAL_DIAS * 86400.0)
            estado["trial_inicio"] = trial_inicio
            estado["trial_fim"] = trial_fim
            estado["ultimo_timestamp"] = agora_ts
            self._salvar_estado(estado)

        segundos_restantes = trial_fim - agora_ts
        data_fim_str = datetime.fromtimestamp(trial_fim, tz=timezone.utc).strftime("%Y-%m-%d")

        dados_trial = DadosLicenca(
            cliente="Modo Avaliação (Trial)",
            machine_id=hw_id,
            valido_ate=data_fim_str,
            modulos=["*"],
            max_impressoras=1,
            tipo="TRIAL",
            emissao=datetime.fromtimestamp(trial_inicio, tz=timezone.utc).strftime("%Y-%m-%d"),
        )

        if segundos_restantes <= 0:
            return StatusLicenca(
                valida=False,
                estado="TRIAL_EXPIRADO",
                dias_restantes=0,
                mensagem=f"Período de avaliação de {DURACAO_TRIAL_DIAS} dias expirado em {data_fim_str}.",
                dados=dados_trial,
            )

        dias_restantes = math.ceil(segundos_restantes / 86400.0)
        return StatusLicenca(
            valida=True,
            estado="TRIAL_ATIVO",
            dias_restantes=dias_restantes,
            mensagem=f"Modo Trial ativo. Restam {dias_restantes} dia(s) de avaliação.",
            dados=dados_trial,
        )

    def validar_conteudo(
        self,
        payload_json: str,
        assinatura_b64: str,
        agora_override: Optional[datetime] = None,
    ) -> StatusLicenca:
        """
        Valida criptograficamente o conteúdo do payload e sua assinatura Ed25519.
        """
        agora_dt = agora_override or datetime.now()
        agora_ts = agora_dt.timestamp()

        # 1. Proteção anti-retrocesso de relógio
        if not self._verificar_relogio_e_atualizar(agora_ts):
            return StatusLicenca(
                valida=False,
                estado="RELOGIO_ADULTERADO",
                dias_restantes=0,
                mensagem="Adulteração de relógio detectada. O relógio do sistema foi retrocedido.",
            )

        # 2. Verificação criptográfica Ed25519
        try:
            sig_bytes = base64.b64decode(assinatura_b64)
            self.chave_publica.verify(sig_bytes, payload_json.encode("utf-8"))
        except (InvalidSignature, Exception):
            return StatusLicenca(
                valida=False,
                estado="ASSINATURA_INVALIDA",
                dias_restantes=0,
                mensagem="Assinatura digital inválida ou licença corrompida.",
            )

        # 3. Decodificação do payload
        try:
            p_dict = json.loads(payload_json)
            dados = DadosLicenca(
                cliente=str(p_dict.get("cliente", "")),
                machine_id=str(p_dict.get("machine_id", "")),
                valido_ate=str(p_dict.get("valido_ate", "")),
                modulos=list(p_dict.get("modulos", [])),
                max_impressoras=int(p_dict.get("max_impressoras", 1)),
                tipo=str(p_dict.get("tipo", "ANUAL")),
                emissao=str(p_dict.get("emissao", "")),
                extra=dict(p_dict.get("extra", {})),
            )
        except Exception as e:
            return StatusLicenca(
                valida=False,
                estado="ASSINATURA_INVALIDA",
                dias_restantes=0,
                mensagem=f"Estrutura interna da licença corrompida: {e}",
            )

        # 4. Amarração ao Hardware ID
        hw_atual = self.obter_hardware_id_atual()
        if dados.machine_id != "*" and dados.machine_id.upper() != hw_atual.upper():
            return StatusLicenca(
                valida=False,
                estado="INVALIDO_HARDWARE",
                dias_restantes=0,
                mensagem=(
                    f"Licença não autorizada para este computador. "
                    f"Esperado: {dados.machine_id}, Atual: {hw_atual}"
                ),
                dados=dados,
            )

        # 5. Validação da vigência temporal
        if dados.tipo.upper() == "PERPETUA" or dados.valido_ate.upper() in ("PERPETUA", "9999-12-31"):
            return StatusLicenca(
                valida=True,
                estado="LICENCIADO",
                dias_restantes=99999,
                mensagem="Licença perpétua ativa e válida.",
                dados=dados,
            )

        try:
            # Suporta YYYY-MM-DD ou ISO completo
            valido_ate_limpo = dados.valido_ate.strip()
            if "T" in valido_ate_limpo:
                dt_valido = datetime.fromisoformat(valido_ate_limpo)
            else:
                dt_valido = datetime.strptime(valido_ate_limpo, "%Y-%m-%d").replace(
                    hour=23, minute=59, second=59
                )
        except Exception:
            return StatusLicenca(
                valida=False,
                estado="ASSINATURA_INVALIDA",
                dias_restantes=0,
                mensagem=f"Data de validade inválida na licença: '{dados.valido_ate}'",
                dados=dados,
            )

        delta_segundos = (dt_valido - agora_dt).total_seconds()
        if delta_segundos < 0:
            return StatusLicenca(
                valida=False,
                estado="EXPIRADO",
                dias_restantes=0,
                mensagem=f"Licença expirada em {dados.valido_ate}.",
                dados=dados,
            )

        dias_restantes = max(0, math.ceil(delta_segundos / 86400.0))
        return StatusLicenca(
            valida=True,
            estado="LICENCIADO",
            dias_restantes=dias_restantes,
            mensagem=f"Licença válida ({dados.tipo}). Restam {dias_restantes} dia(s).",
            dados=dados,
        )

    def validar_arquivo(
        self,
        caminho_licenca: Optional[Union[str, Path]] = None,
        agora_override: Optional[datetime] = None,
    ) -> StatusLicenca:
        """
        Valida o arquivo de licença especificado ou padrão.
        Se nenhum arquivo existir, aciona o Modo Trial de 14 dias.
        """
        agora_dt = agora_override or datetime.now()
        arquivo = Path(caminho_licenca) if caminho_licenca else self.caminho_licenca

        if not arquivo.exists():
            # Sem arquivo de licença: ativa ou consulta modo Trial
            # Verifica proteção de relógio no trial também
            if not self._verificar_relogio_e_atualizar(agora_dt.timestamp()):
                return StatusLicenca(
                    valida=False,
                    estado="RELOGIO_ADULTERADO",
                    dias_restantes=0,
                    mensagem="Adulteração de relógio detectada ao acessar período de teste.",
                )
            return self._processar_trial(agora_dt)

        try:
            with open(arquivo, "r", encoding="utf-8") as f:
                conteudo = json.load(f)

            sig = conteudo.get("signature", "")
            if "payload_raw" in conteudo:
                payload_str = conteudo["payload_raw"]
            elif isinstance(conteudo.get("payload"), dict):
                payload_str = json.dumps(conteudo["payload"], sort_keys=True, separators=(",", ":"))
            elif isinstance(conteudo.get("payload"), str):
                payload_str = conteudo["payload"]
            else:
                return StatusLicenca(
                    valida=False,
                    estado="ASSINATURA_INVALIDA",
                    dias_restantes=0,
                    mensagem="Formato do arquivo de licença não reconhecido.",
                )

            return self.validar_conteudo(payload_str, sig, agora_override=agora_dt)

        except json.JSONDecodeError:
            return StatusLicenca(
                valida=False,
                estado="ASSINATURA_INVALIDA",
                dias_restantes=0,
                mensagem="Arquivo de licença corrompido ou formato inválido.",
            )
        except Exception as e:
            return StatusLicenca(
                valida=False,
                estado="ASSINATURA_INVALIDA",
                dias_restantes=0,
                mensagem=f"Erro ao ler arquivo de licença: {e}",
            )
