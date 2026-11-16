"""
Módulo de identificação determinística e imutável de hardware da máquina (Machine ID).
Suporta coleta profunda no Windows (MachineGuid, Volume Serial C:, MAC primário)
e fallback determinístico para outros ambientes.
"""

from __future__ import annotations

import ctypes
import hashlib
import re
import sys
import uuid
from typing import Optional

PADRAO_HARDWARE_ID = re.compile(r"^CV-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}$")


def obter_machine_guid() -> str:
    """
    Obtém o MachineGuid do registro do Windows (HKLM\\SOFTWARE\\Microsoft\\Cryptography).
    Fallback determinístico para MAC/UUID caso não esteja disponível.
    """
    if sys.platform == "win32":
        try:
            import winreg

            flags = winreg.KEY_READ | getattr(winreg, "KEY_WOW64_64KEY", 0)
            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Microsoft\Cryptography",
                0,
                flags,
            ) as chave:
                valor, _ = winreg.QueryValueEx(chave, "MachineGuid")
                if valor and isinstance(valor, str):
                    return valor.strip().upper()
        except Exception:
            pass

    return f"FALLBACK-GUID-{uuid.getnode():012X}"


def obter_volume_serial(drive: str = "C:\\") -> str:
    """
    Obtém o número de série do volume da unidade do sistema (padrão C:\\).
    """
    if sys.platform == "win32":
        try:
            numero_serie = ctypes.c_ulong()
            sucesso = ctypes.windll.kernel32.GetVolumeInformationW(
                ctypes.c_wchar_p(drive),
                None,
                0,
                ctypes.byref(numero_serie),
                None,
                None,
                None,
                0,
            )
            if sucesso:
                return f"{numero_serie.value:08X}"
        except Exception:
            pass

    return "VOL-00000000"


def obter_mac_address() -> str:
    """
    Obtém o identificador MAC primário da máquina formatado em hexadecimal.
    """
    try:
        mac_num = uuid.getnode()
        return f"{mac_num:012X}"
    except Exception:
        return "MAC-000000000000"


def obter_hardware_id(custom_seed: Optional[str] = None) -> str:
    """
    Calcula o identificador único de hardware formatado no padrão:
    CV-XXXX-XXXX-XXXX (ex: CV-9A4F-28B1-0C7D).

    Args:
        custom_seed: Se fornecido, utiliza esta semente ao invés dos componentes reais
                     da máquina (útil para testes unitários ou simulação de hardware).

    Returns:
        String no formato CV-XXXX-XXXX-XXXX.
    """
    if custom_seed is not None:
        dados_brutos = f"SEED:{custom_seed}".encode("utf-8")
    else:
        guid = obter_machine_guid()
        vol = obter_volume_serial("C:\\")
        mac = obter_mac_address()
        dados_brutos = f"{guid}::{vol}::{mac}".encode("utf-8")

    digest = hashlib.blake2b(dados_brutos, digest_size=16).hexdigest().upper()
    hardware_id = f"CV-{digest[0:4]}-{digest[4:8]}-{digest[8:12]}"
    return hardware_id


def validar_formato_hardware_id(hw_id: str) -> bool:
    """
    Valida se a string segue o formato esperado CV-XXXX-XXXX-XXXX.
    """
    if not isinstance(hw_id, str):
        return False
    return bool(PADRAO_HARDWARE_ID.match(hw_id.strip()))
