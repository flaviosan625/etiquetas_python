"""
motor_pdf/sintaxe.py — Parser de tipos primitivos, objetos e estruturas sintáticas de PDF.

Conforme especificação ISO 32000-1:
  - Booleanos (true, false) e nulos (null)
  - Numéricos (inteiros e ponto flutuante)
  - Nomes (/MediaBox, /Type, etc.)
  - Strings literais "(...)" e hexadecimais "<...>"
  - Dicionários "<< ... >>"
  - Arrays "[ ... ]"
  - Referências indiretas "12 0 R"
  - Objetos indiretos "12 0 obj ... endobj"
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple, Union


class PdfName(str):
    """Representa um nome PDF (/Nome). Sempre normalizado com a barra inicial."""
    def __new__(cls, val):
        s = str(val)
        if not s.startswith("/"):
            s = "/" + s
        return super().__new__(cls, s)

    def __repr__(self):
        return f"PdfName('{self}')"


class PdfRef:
    """Representa uma referência indireta (ex: 12 0 R)."""
    __slots__ = ("num", "gen")

    def __init__(self, num: int, gen: int = 0):
        self.num = int(num)
        self.gen = int(gen)

    def __repr__(self):
        return f"PdfRef({self.num}, {self.gen})"

    def __eq__(self, other):
        return isinstance(other, PdfRef) and self.num == other.num and self.gen == other.gen

    def __hash__(self):
        return hash((self.num, self.gen))


class PdfString(bytes):
    """Representa uma cadeia de caracteres (literal ou hexadecimal)."""
    def texto(self, encoding: str = "latin1") -> str:
        # Se começar com BOM UTF-16BE (0xFE 0xFF)
        if self.startswith(b"\xfe\xff"):
            return self[2:].decode("utf-16-be", errors="replace")
        return self.decode(encoding, errors="replace")


PdfDict = dict
PdfArray = list


class PdfStream:
    """Representa um objeto stream (dicionário de metadados + bytes brutos)."""
    def __init__(self, header: dict, raw_bytes: bytes):
        self.header = header
        self.raw_bytes = raw_bytes

    def __repr__(self):
        return f"PdfStream(len={len(self.raw_bytes)}, header={self.header})"


# Delimitadores de sintaxe PDF
DELIMITADORES = set(b"()<>[]{}/%")
ESPACOS = set(b" \t\r\n\x0c\x00")


class PdfTokenizer:
    """Tokenizer léxico de bytes para streams e arquivos PDF."""

    def __init__(self, data: bytes, offset: int = 0):
        self.data = data
        self.pos = offset
        self.length = len(data)

    def pular_espacos_e_comentarios(self):
        """Avança o cursor ignorando espaços em branco e comentários iniciados por '%'."""
        while self.pos < self.length:
            b = self.data[self.pos]
            if b in ESPACOS:
                self.pos += 1
            elif b == 0x25:  # '%' comentário até fim da linha
                self.pos += 1
                while self.pos < self.length and self.data[self.pos] not in (0x0A, 0x0D):
                    self.pos += 1
            else:
                break

    def espiar_byte(self) -> Optional[int]:
        self.pular_espacos_e_comentarios()
        if self.pos < self.length:
            return self.data[self.pos]
        return None

    def ler_token(self) -> Optional[Union[str, bytes]]:
        """Lê o próximo token léxico bruto."""
        self.pular_espacos_e_comentarios()
        if self.pos >= self.length:
            return None

        b = self.data[self.pos]

        # 1. Delimitadores duplos: << ou >>
        if b == 0x3C and self.pos + 1 < self.length and self.data[self.pos + 1] == 0x3C:
            self.pos += 2
            return "<<"
        if b == 0x3E and self.pos + 1 < self.length and self.data[self.pos + 1] == 0x3E:
            self.pos += 2
            return ">>"

        # 2. Delimitadores simples: [ ou ]
        if b in (0x5B, 0x5D):  # '[' ou ']'
            self.pos += 1
            return chr(b)

        # 3. String Hexadecimal: < ... >
        if b == 0x3C:  # '<'
            self.pos += 1
            start = self.pos
            while self.pos < self.length and self.data[self.pos] != 0x3E:
                self.pos += 1
            hex_data = self.data[start:self.pos]
            if self.pos < self.length:
                self.pos += 1  # consome '>'
            # Converte hex para bytes
            limpo = re.sub(rb"\s+", b"", hex_data)
            if len(limpo) % 2 != 0:
                limpo += b"0"
            try:
                return PdfString(bytes.fromhex(limpo.decode("ascii", errors="ignore")))
            except Exception:
                return PdfString(b"")

        # 4. String Literal: ( ... )
        if b == 0x28:  # '('
            self.pos += 1
            profundidade = 1
            escapado = False
            resultado = bytearray()
            while self.pos < self.length and profundidade > 0:
                char_byte = self.data[self.pos]
                self.pos += 1

                if escapado:
                    escapado = False
                    if char_byte == 0x6E:    # \n
                        resultado.append(0x0A)
                    elif char_byte == 0x72:  # \r
                        resultado.append(0x0D)
                    elif char_byte == 0x74:  # \t
                        resultado.append(0x09)
                    elif char_byte == 0x62:  # \b
                        resultado.append(0x08)
                    elif char_byte == 0x66:  # \f
                        resultado.append(0x0C)
                    elif char_byte in (0x28, 0x29, 0x5C):  # \( \) \\
                        resultado.append(char_byte)
                    elif 0x30 <= char_byte <= 0x37:  # octal \ddd
                        octal = [char_byte]
                        for _ in range(2):
                            if self.pos < self.length and 0x30 <= self.data[self.pos] <= 0x37:
                                octal.append(self.data[self.pos])
                                self.pos += 1
                            else:
                                break
                        resultado.append(int(bytes(octal), 8) & 0xFF)
                    else:
                        resultado.append(char_byte)
                elif char_byte == 0x5C:  # '\'
                    escapado = True
                elif char_byte == 0x28:  # '('
                    profundidade += 1
                    resultado.append(char_byte)
                elif char_byte == 0x29:  # ')'
                    profundidade -= 1
                    if profundidade > 0:
                        resultado.append(char_byte)
                else:
                    resultado.append(char_byte)
            return PdfString(bytes(resultado))

        # 5. Nome: /Nome
        if b == 0x2F:  # '/'
            self.pos += 1
            start = self.pos
            while self.pos < self.length and self.data[self.pos] not in ESPACOS and self.data[self.pos] not in DELIMITADORES:
                self.pos += 1
            raw_nome = self.data[start:self.pos].decode("latin1", errors="ignore")
            # Decodifica escapes numéricos de nomes (#20 -> espaço)
            nome_dec = re.sub(r"#([0-9A-Fa-f]{2})", lambda m: chr(int(m.group(1), 16)), raw_nome)
            return PdfName(nome_dec)

        # 6. Palavra ou Número regular
        start = self.pos
        while self.pos < self.length and self.data[self.pos] not in ESPACOS and self.data[self.pos] not in DELIMITADORES:
            self.pos += 1
        return self.data[start:self.pos].decode("latin1", errors="ignore")


def parse_objeto(tokenizer: PdfTokenizer) -> Any:
    """Lê recursivamente o próximo objeto PDF a partir do cursor do tokenizer."""
    tok = tokenizer.ler_token()
    if tok is None:
        return None

    # Dicionário << ... >>
    if tok == "<<":
        d = {}
        while True:
            chave_tok = tokenizer.ler_token()
            if chave_tok == ">>" or chave_tok is None:
                break
            if not isinstance(chave_tok, PdfName):
                # Chave inválida ou recuperação
                continue
            valor = parse_objeto(tokenizer)
            d[chave_tok] = valor
        return d

    # Array [ ... ]
    if tok == "[":
        arr = []
        while True:
            ponto = tokenizer.pos
            prox_byte = tokenizer.espiar_byte()
            if prox_byte == 0x5D:  # ']'
                tokenizer.ler_token()  # consome ']'
                break
            elem = parse_objeto(tokenizer)
            if elem is None and tokenizer.pos == ponto:
                break
            arr.append(elem)
        return arr

    if isinstance(tok, (PdfName, PdfString)):
        return tok

    if isinstance(tok, str):
        if tok == "true":
            return True
        if tok == "false":
            return False
        if tok == "null":
            return None

        # Tenta interpretar como inteiro ou float
        try:
            if "." in tok:
                return float(tok)
            # Pode ser o primeiro número de uma referência: <num> <gen> R
            val_int = int(tok)
            ponto_retorno = tokenizer.pos
            segundo = tokenizer.ler_token()
            if isinstance(segundo, str) and segundo.isdigit():
                terceiro = tokenizer.ler_token()
                if terceiro == "R":
                    return PdfRef(val_int, int(segundo))
            # Não era referência; recua o tokenizer
            tokenizer.pos = ponto_retorno
            return val_int
        except ValueError:
            return tok

    return tok
