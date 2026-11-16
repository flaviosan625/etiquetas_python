"""
motor_pdf/descompressao.py — Decodificadores e filtros de descompressão de streams PDF.

Implementa:
  - FlateDecode (zlib/Deflate)
  - Desfazimento de Preditores PNG (10 a 15) e TIFF 2
  - ASCIIHexDecode
  - ASCII85Decode
  - RunLengthDecode

100% autônomo, sem dependências externas (apenas biblioteca padrão Python: zlib, struct).
Inspirado na arquitetura de src/io/pdf_vector.cpp do CNC CAM C++.
"""

from __future__ import annotations

import math
import zlib
from typing import Optional, Union


def ascii_hex_decode(data: bytes) -> bytes:
    """Decodifica stream ASCIIHexDecode."""
    out = bytearray()
    high = -1
    for b in data:
        if b == 0x3E:  # '>' fim do stream
            break
        # Caracteres hexadecimais
        if 0x30 <= b <= 0x39:
            v = b - 0x30
        elif 0x41 <= b <= 0x46:
            v = b - 0x41 + 10
        elif 0x61 <= b <= 0x66:
            v = b - 0x61 + 10
        else:
            continue  # ignora espaços

        if high < 0:
            high = v
        else:
            out.append((high << 4) | v)
            high = -1

    if high >= 0:
        out.append(high << 4)
    return bytes(out)


def ascii85_decode(data: bytes) -> bytes:
    """Decodifica stream ASCII85Decode."""
    out = bytearray()
    if data.startswith(b"<~"):
        data = data[2:]

    tuple_val = 0
    count = 0
    for b in data:
        if b == 0x7E:  # '~' fim
            break
        if b == 0x7A and count == 0:  # 'z' representa 4 zeros
            out.extend(b"\x00\x00\x00\x00")
            continue
        if b < 0x21 or b > 0x75:  # ignora fora de '!' até 'u'
            continue

        tuple_val = tuple_val * 85 + (b - 0x21)
        count += 1
        if count == 5:
            out.append((tuple_val >> 24) & 0xFF)
            out.append((tuple_val >> 16) & 0xFF)
            out.append((tuple_val >> 8) & 0xFF)
            out.append(tuple_val & 0xFF)
            tuple_val = 0
            count = 0

    if count > 1:
        for _ in range(count, 5):
            tuple_val = tuple_val * 85 + 84
        for k in range(3, 4 - count, -1):
            out.append((tuple_val >> (8 * k)) & 0xFF)

    return bytes(out)


def run_length_decode(data: bytes) -> bytes:
    """Decodifica stream RunLengthDecode."""
    out = bytearray()
    i = 0
    n = len(data)
    while i < n:
        length = data[i]
        i += 1
        if length == 128:
            break
        if length < 128:
            count = length + 1
            out.extend(data[i:i + count])
            i += count
        else:
            count = 257 - length
            if i < n:
                val = data[i]
                i += 1
                out.extend(bytes([val]) * count)
    return bytes(out)


def desfaz_preditor(
    data: bytes,
    predictor: int = 1,
    colors: int = 1,
    bits_per_component: int = 8,
    columns: int = 1,
) -> bytes:
    """
    Desfaz os preditores de compressão PNG (10-15) e TIFF (2).
    Usado em streams de imagens e tabelas de xref compactadas (/XRefStm).
    """
    if predictor <= 1:
        return data

    bpp = max(1, (colors * bits_per_component + 7) // 8)
    row_bytes = (colors * bits_per_component * columns + 7) // 8
    if row_bytes == 0:
        return data

    # Preditor TIFF 2: diferença horizontal
    if predictor == 2:
        if bits_per_component != 8:
            return data
        ba = bytearray(data)
        for row_start in range(0, len(ba), row_bytes):
            for i in range(bpp, min(row_bytes, len(ba) - row_start)):
                idx = row_start + i
                ba[idx] = (ba[idx] + ba[idx - bpp]) & 0xFF
        return bytes(ba)

    # Preditores PNG (10 a 15)
    stride = row_bytes + 1
    rows = (len(data) + stride - 1) // stride
    out = bytearray(rows * row_bytes)
    out_idx = 0
    prev_row = bytearray(row_bytes)

    for r in range(rows):
        base = r * stride
        if base >= len(data):
            break

        filter_byte = data[base]
        cur_row = bytearray(row_bytes)

        for i in range(min(row_bytes, len(data) - base - 1)):
            raw = data[base + 1 + i]
            left = cur_row[i - bpp] if i >= bpp else 0
            up = prev_row[i]
            up_left = prev_row[i - bpp] if i >= bpp else 0

            if filter_byte == 0:    # None
                v = raw
            elif filter_byte == 1:  # Sub
                v = raw + left
            elif filter_byte == 2:  # Up
                v = raw + up
            elif filter_byte == 3:  # Average
                v = raw + (left + up) // 2
            elif filter_byte == 4:  # Paeth
                p = left + up - up_left
                pa = abs(p - left)
                pb = abs(p - up)
                pc = abs(p - up_left)
                if pa <= pb and pa <= pc:
                    pr = left
                elif pb <= pc:
                    pr = up
                else:
                    pr = up_left
                v = raw + pr
            else:
                v = raw

            cur_row[i] = v & 0xFF

        out[out_idx:out_idx + row_bytes] = cur_row
        out_idx += row_bytes
        prev_row = cur_row

    return bytes(out[:out_idx])


def descompactar_stream(data: bytes, filtro: Union[str, list, None] = None, params: Optional[dict] = None) -> bytes:
    """
    Descompacta o stream de um objeto PDF conforme os filtros especificados.
    Suporta filtros únicos ou listas em pipeline (ex: [/ASCII85Decode /FlateDecode]).
    """
    if not filtro:
        return data

    filtros = [filtro] if isinstance(filtro, str) else list(filtro)

    for f in filtros:
        f_norm = f.strip("/").lower()
        if f_norm in ("flatedecode", "fl"):
            try:
                data = zlib.decompress(data)
            except zlib.error:
                # Tenta sem cabeçalho zlib (-15 para raw deflate)
                data = zlib.decompress(data, -15)

            if params and isinstance(params, dict):
                pred = int(params.get("/Predictor", params.get("Predictor", 1)))
                if pred > 1:
                    colors = int(params.get("/Colors", params.get("Colors", 1)))
                    bpc = int(params.get("/BitsPerComponent", params.get("BitsPerComponent", 8)))
                    cols = int(params.get("/Columns", params.get("Columns", 1)))
                    data = desfaz_preditor(data, predictor=pred, colors=colors, bits_per_component=bpc, columns=cols)

        elif f_norm in ("asciihexdecode", "ahx"):
            data = ascii_hex_decode(data)
        elif f_norm in ("ascii85decode", "a85"):
            data = ascii85_decode(data)
        elif f_norm in ("runlengthdecode", "rld"):
            data = run_length_decode(data)

    return data
