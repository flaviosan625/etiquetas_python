"""
Facade de acesso rápido ao subsistema de banco relacional SQLite (WAL).

Permite aos módulos do sistema utilizar funções diretas de alto nível
ou instanciar repositórios desacoplados para operações complexas.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

from banco.conexao import (
    abrir_conexao,
    criar_conexao,
    configurar_pragmas,
    obter_caminho_banco,
    CaminhoBanco,
)
from banco.migracao import (
    inicializar_banco,
    migrar_estoque_legado,
)
from banco.repositorios import (
    RepositorioBase,
    RepositorioPedidos,
    RepositorioMontagens,
    RepositorioHistorico,
    RepositorioEstoque,
)


def obter_repositorio_pedidos(caminho: Optional[CaminhoBanco] = None) -> RepositorioPedidos:
    """Retorna uma instância do repositório de pedidos."""
    return RepositorioPedidos(caminho=caminho)


def obter_repositorio_montagens(caminho: Optional[CaminhoBanco] = None) -> RepositorioMontagens:
    """Retorna uma instância do repositório de montagens."""
    return RepositorioMontagens(caminho=caminho)


def obter_repositorio_historico(caminho: Optional[CaminhoBanco] = None) -> RepositorioHistorico:
    """Retorna uma instância do repositório de histórico de produção."""
    return RepositorioHistorico(caminho=caminho)


def obter_repositorio_estoque(caminho: Optional[CaminhoBanco] = None) -> RepositorioEstoque:
    """Retorna uma instância do repositório de estoque."""
    return RepositorioEstoque(caminho=caminho)


# ============================================================================
# Facade - Funções de conveniência de uso direto
# ============================================================================

def criar_pedido(
    cliente: str,
    numero: Optional[str] = None,
    observacoes: Optional[str] = None,
    caminho: Optional[CaminhoBanco] = None,
) -> int:
    """Cria um novo pedido."""
    return obter_repositorio_pedidos(caminho).criar_pedido(
        cliente=cliente, numero=numero, observacoes=observacoes
    )


def obter_pedido(
    pedido_id: Optional[int] = None,
    numero: Optional[str] = None,
    caminho: Optional[CaminhoBanco] = None,
) -> Optional[Dict[str, Any]]:
    """Consulta um pedido por ID ou número acompanhado de seus itens."""
    return obter_repositorio_pedidos(caminho).obter_pedido(
        pedido_id=pedido_id, numero=numero
    )


def listar_pedidos(
    cliente: Optional[str] = None,
    status: Optional[str] = None,
    limite: int = 100,
    caminho: Optional[CaminhoBanco] = None,
) -> List[Dict[str, Any]]:
    """Lista pedidos filtrados."""
    return obter_repositorio_pedidos(caminho).listar_pedidos(
        cliente=cliente, status=status, limite=limite
    )


def registrar_producao(
    maquina: str,
    arquivo: str,
    m2: float,
    data_hora: Optional[str] = None,
    material: Optional[str] = None,
    caminho: Optional[CaminhoBanco] = None,
) -> int:
    """Registra uma entrada no log de produção de máquinas."""
    return obter_repositorio_historico(caminho).registrar_producao(
        maquina=maquina, arquivo=arquivo, m2=m2, data_hora=data_hora, material=material
    )


def calcular_m2_produzido(
    maquina: Optional[str] = None,
    data: Optional[str] = None,
    caminho: Optional[CaminhoBanco] = None,
) -> float:
    """Calcula a metragem quadrada total impressa por máquina ou data."""
    return obter_repositorio_historico(caminho).calcular_m2_produzido(
        maquina=maquina, data=data
    )


def obter_saldo_estoque(codigo: str, caminho: Optional[CaminhoBanco] = None) -> float:
    """Obtém o saldo atual de um produto no estoque."""
    return obter_repositorio_estoque(caminho).obter_saldo(codigo)


def obter_custo_m2_estoque(codigo: str, caminho: Optional[CaminhoBanco] = None) -> Optional[float]:
    """Obtém o custo por m² de um material cadastrado."""
    return obter_repositorio_estoque(caminho).obter_custo_m2(codigo)


def registrar_movimentacao_estoque(
    codigo: str,
    tipo: str,
    quantidade: float,
    observacao: str = "",
    origem_pedido: Optional[str] = None,
    caminho: Optional[CaminhoBanco] = None,
) -> int:
    """Registra entrada, saída ou ajuste de material no estoque."""
    return obter_repositorio_estoque(caminho).registrar_movimentacao(
        codigo=codigo,
        tipo=tipo,
        quantidade=quantidade,
        observacao=observacao,
        origem_pedido=origem_pedido,
    )


__all__ = [
    "abrir_conexao",
    "criar_conexao",
    "configurar_pragmas",
    "obter_caminho_banco",
    "CaminhoBanco",
    "inicializar_banco",
    "migrar_estoque_legado",
    "RepositorioBase",
    "RepositorioPedidos",
    "RepositorioMontagens",
    "RepositorioHistorico",
    "RepositorioEstoque",
    "obter_repositorio_pedidos",
    "obter_repositorio_montagens",
    "obter_repositorio_historico",
    "obter_repositorio_estoque",
    "criar_pedido",
    "obter_pedido",
    "listar_pedidos",
    "registrar_producao",
    "calcular_m2_produzido",
    "obter_saldo_estoque",
    "obter_custo_m2_estoque",
    "registrar_movimentacao_estoque",
]
