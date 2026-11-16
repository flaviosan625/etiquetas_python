"""
Ferramenta para geração de pares de chaves Ed25519 e emissão de licenças assinadas.
Suporta execução via biblioteca Python ou interface de linha de comando (CLI).
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

# Garante que a raiz do projeto esteja no sys.path ao rodar o script diretamente
_RAIZ_PROJETO = Path(__file__).resolve().parent.parent
if str(_RAIZ_PROJETO) not in sys.path:
    sys.path.insert(0, str(_RAIZ_PROJETO))

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

from licenciamento.hardware_id import obter_hardware_id, validar_formato_hardware_id


def gerar_par_chaves() -> Tuple[str, str]:
    """
    Gera um novo par de chaves assimétricas Ed25519.

    Returns:
        Tupla (chave_privada_b64, chave_publica_b64) com 32 bytes brutos codificados em Base64.
    """
    priv = ed25519.Ed25519PrivateKey.generate()
    pub = priv.public_key()

    priv_bytes = priv.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    pub_bytes = pub.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )

    priv_b64 = base64.b64encode(priv_bytes).decode("utf-8")
    pub_b64 = base64.b64encode(pub_bytes).decode("utf-8")
    return priv_b64, pub_b64


def carregar_chave_privada(
    chave: Union[str, ed25519.Ed25519PrivateKey]
) -> ed25519.Ed25519PrivateKey:
    """Carrega uma chave privada Ed25519 de objeto, string Base64, Hex ou caminho de arquivo."""
    if isinstance(chave, ed25519.Ed25519PrivateKey):
        return chave

    chave_str = str(chave).strip()

    # Se for um caminho de arquivo existente, lê o conteúdo
    possivel_arquivo = Path(chave_str)
    if possivel_arquivo.is_file():
        chave_str = possivel_arquivo.read_text(encoding="utf-8").strip()

    # Tenta Base64 (32 bytes raw)
    try:
        dados = base64.b64decode(chave_str)
        if len(dados) == 32:
            return ed25519.Ed25519PrivateKey.from_private_bytes(dados)
    except Exception:
        pass

    # Tenta Hex (64 caracteres)
    try:
        dados = bytes.fromhex(chave_str)
        if len(dados) == 32:
            return ed25519.Ed25519PrivateKey.from_private_bytes(dados)
    except Exception:
        pass

    # Tenta PEM
    try:
        return serialization.load_pem_private_key(  # type: ignore
            chave_str.encode("utf-8"), password=None
        )
    except Exception as e:
        raise ValueError(f"Chave privada Ed25519 inválida ou formato não reconhecido: {e}")


def emitir_licenca(
    cliente: str,
    machine_id: str,
    dias_validade: int = 365,
    modulos: Optional[List[str]] = None,
    max_impressoras: int = 1,
    tipo: str = "ANUAL",
    chave_privada: Union[str, ed25519.Ed25519PrivateKey] = "",
    extra: Optional[Dict[str, Any]] = None,
    emissao_override: Optional[datetime] = None,
) -> str:
    """
    Gera e assina digitalmente uma licença em formato JSON.

    Args:
        cliente: Nome ou Razão Social do cliente.
        machine_id: Hardware ID da máquina de destino (ou '*' para qualquer).
        dias_validade: Quantidade de dias de validade (ignorado se PERPETUA).
        modulos: Lista de módulos liberados (ex: ['corte', 'impressao', 'montagem']).
        max_impressoras: Limite máximo de impressoras simultâneas.
        tipo: Tipo da licença ('MENSAL', 'ANUAL', 'PERPETUA', 'TRIAL').
        chave_privada: Chave privada Ed25519 para assinar o pacote.
        extra: Metadados adicionais arbitrários.
        emissao_override: Data de emissão customizada (para testes).

    Returns:
        String JSON contendo payload estruturado e assinatura Base64.
    """
    priv_key = carregar_chave_privada(chave_privada)
    tipo_up = tipo.strip().upper()

    agora = emissao_override or datetime.now()
    if tipo_up == "PERPETUA":
        valido_ate = "9999-12-31"
    else:
        dt_exp = agora + timedelta(days=dias_validade)
        valido_ate = dt_exp.strftime("%Y-%m-%d")

    lista_modulos = sorted(modulos or ["*"])

    payload_dict = {
        "cliente": cliente.strip(),
        "emissao": agora.strftime("%Y-%m-%dT%H:%M:%S"),
        "extra": extra or {},
        "machine_id": machine_id.strip(),
        "max_impressoras": int(max_impressoras),
        "modulos": lista_modulos,
        "tipo": tipo_up,
        "valido_ate": valido_ate,
    }

    # Serialização canônica determinística para assinatura
    payload_raw = json.dumps(payload_dict, sort_keys=True, separators=(",", ":"))
    sig_bytes = priv_key.sign(payload_raw.encode("utf-8"))
    sig_b64 = base64.b64encode(sig_bytes).decode("utf-8")

    documento = {
        "payload": payload_dict,
        "payload_raw": payload_raw,
        "signature": sig_b64,
    }

    return json.dumps(documento, indent=2, ensure_ascii=False)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Emissor de Licenças Criptográficas Ed25519 (Comunicação Visual)"
    )
    subparsers = parser.add_subparsers(dest="comando", help="Comandos disponíveis")

    # Subcomando gerar-chaves
    p_chaves = subparsers.add_parser("gerar-chaves", help="Gera um novo par de chaves Ed25519")
    p_chaves.add_argument("--saida-priv", help="Arquivo para salvar a chave privada")
    p_chaves.add_argument("--saida-pub", help="Arquivo para salvar a chave pública")

    # Subcomando hardware-id
    subparsers.add_parser("hardware-id", help="Exibe o Machine ID do computador atual")

    # Subcomando emitir
    p_emitir = subparsers.add_parser("emitir", help="Emite uma nova licença assinada")
    p_emitir.add_argument("--cliente", required=True, help="Nome do cliente/empresa")
    p_emitir.add_argument("--machine-id", required=True, help="Machine ID da máquina (ou '*' para universal)")
    p_emitir.add_argument("--dias", type=int, default=365, help="Dias de validade (padrão: 365)")
    p_emitir.add_argument("--modulos", default="*", help="Módulos liberados separados por vírgula (ex: corte,impressao)")
    p_emitir.add_argument("--max-impressoras", type=int, default=2, help="Limite de impressoras (padrão: 2)")
    p_emitir.add_argument("--tipo", default="ANUAL", choices=["MENSAL", "ANUAL", "PERPETUA", "TRIAL"], help="Tipo de licença")
    p_emitir.add_argument("--chave-privada", required=True, help="Chave privada em Base64 ou caminho de arquivo")
    p_emitir.add_argument("--saida", help="Arquivo .lic de destino (se omitido, imprime no terminal)")

    args = parser.parse_args()

    if args.comando == "gerar-chaves":
        priv_b64, pub_b64 = gerar_par_chaves()
        if args.saida_priv:
            Path(args.saida_priv).write_text(priv_b64, encoding="utf-8")
            print(f"Chave privada salva em: {args.saida_priv}")
        else:
            print(f"CHAVE_PRIVADA: {priv_b64}")

        if args.saida_pub:
            Path(args.saida_pub).write_text(pub_b64, encoding="utf-8")
            print(f"Chave pública salva em: {args.saida_pub}")
        else:
            print(f"CHAVE_PUBLICA: {pub_b64}")
        return 0

    if args.comando == "hardware-id":
        hw = obter_hardware_id()
        print(f"Hardware ID: {hw}")
        return 0

    if args.comando == "emitir":
        modulos = [m.strip() for m in args.modulos.split(",") if m.strip()]
        licenca_json = emitir_licenca(
            cliente=args.cliente,
            machine_id=args.machine_id,
            dias_validade=args.dias,
            modulos=modulos,
            max_impressoras=args.max_impressoras,
            tipo=args.tipo,
            chave_privada=args.chave_privada,
        )
        if args.saida:
            Path(args.saida).write_text(licenca_json, encoding="utf-8")
            print(f"Licença emitida com sucesso e salva em: {args.saida}")
        else:
            print(licenca_json)
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
