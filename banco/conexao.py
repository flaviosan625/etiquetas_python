"""
Gerenciador de conexão SQLite com persistência concorrente (Modo WAL).

Garante integridade referencial, isolamento transacional, concorrência
segura entre leitores e escritores e fechamento determinístico de recursos.
"""
from __future__ import annotations

import contextlib
import os
import pathlib
import sqlite3
from typing import Any, Generator, Optional, Union

CaminhoBanco = Union[str, pathlib.Path]


def obter_caminho_banco(config: Optional[Union[dict, Any]] = None) -> pathlib.Path:
    """
    Determina o caminho do arquivo do banco SQLite.
    Prioridade:
      1. Variável de ambiente AUTOMACAO_GRAFICA_DB
      2. Configuração passada explicitamente ('banco_dados' ou 'caminho_banco')
      3. Constante caminhos.BANCO_DADOS (se módulo disponível)
      4. Padrão: ~/AutomacaoGrafica/dados.db
    """
    env_caminho = os.environ.get("AUTOMACAO_GRAFICA_DB")
    if env_caminho:
        return pathlib.Path(env_caminho)

    if config is not None:
        if isinstance(config, dict):
            c = config.get("banco_dados") or config.get("caminho_banco")
            if c:
                return pathlib.Path(c)
        elif hasattr(config, "banco_dados") and getattr(config, "banco_dados"):
            return pathlib.Path(getattr(config, "banco_dados"))
        elif hasattr(config, "caminho_banco") and getattr(config, "caminho_banco"):
            return pathlib.Path(getattr(config, "caminho_banco"))

    try:
        import caminhos
        if hasattr(caminhos, "BANCO_DADOS"):
            return pathlib.Path(caminhos.BANCO_DADOS)
        if hasattr(caminhos, "PASTA_BASE"):
            return pathlib.Path(caminhos.PASTA_BASE) / "dados.db"
    except Exception:
        pass

    return pathlib.Path.home() / "AutomacaoGrafica" / "dados.db"


def configurar_pragmas(conn: sqlite3.Connection) -> None:
    """
    Aplica os PRAGMAs obrigatórios para alta concorrência e integridade:
      - journal_mode = WAL: leitores não bloqueiam escritores e vice-versa.
      - synchronous = NORMAL: equilíbrio ideal entre segurança de disco e velocidade.
      - foreign_keys = ON: validação estrita de integridade referencial.
      - busy_timeout = 5000: aguarda até 5 segundos em concorrência antes de falhar.
    """
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA busy_timeout = 5000;")


def criar_conexao(caminho: Optional[CaminhoBanco] = None, timeout: float = 5.0) -> sqlite3.Connection:
    """
    Cria e configura uma conexão SQLite com PRAGMAs WAL ativos e row_factory=Row.
    """
    if caminho is None:
        caminho_resolvido = obter_caminho_banco()
        caminho_resolvido.parent.mkdir(parents=True, exist_ok=True)
        alvo = str(caminho_resolvido)
    elif str(caminho) == ":memory:":
        alvo = ":memory:"
    else:
        caminho_resolvido = pathlib.Path(caminho)
        caminho_resolvido.parent.mkdir(parents=True, exist_ok=True)
        alvo = str(caminho_resolvido)

    conn = sqlite3.connect(alvo, timeout=timeout, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    configurar_pragmas(conn)
    return conn


@contextlib.contextmanager
def abrir_conexao(caminho: Optional[CaminhoBanco] = None) -> Generator[sqlite3.Connection, None, None]:
    """
    Gerenciador de contexto seguro para transações SQLite.
    Garante:
      - Abertura com configurações corretas de WAL e Foreign Keys
      - Commit automático se o bloco terminar sem erros
      - Rollback automático se uma exceção for levantada
      - Fechamento determinístico da conexão ao final
    """
    conn = criar_conexao(caminho=caminho)
    try:
        yield conn
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        try:
            conn.close()
        except Exception:
            pass
