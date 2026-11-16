"""
Pacote de persistência relacional SQLite com modo WAL para Automação Gráfica.

Exporta gerenciador de conexões, esquema relacional, utilitários de migração,
repositórios e facade conveniente para operações de pedidos, montagens,
histórico de produção e controle de estoque.
"""
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
    RepositorioMaquinas,
)


def obter_repositorio_maquinas(caminho=None) -> RepositorioMaquinas:
    """Retorna uma instância do repositório de máquinas."""
    return RepositorioMaquinas(caminho=caminho)


def obter_repositorio_pedidos(caminho=None) -> RepositorioPedidos:
    """Retorna uma instância do repositório de pedidos."""
    return RepositorioPedidos(caminho=caminho)


def obter_repositorio_montagens(caminho=None) -> RepositorioMontagens:
    """Retorna uma instância do repositório de montagens."""
    return RepositorioMontagens(caminho=caminho)


def obter_repositorio_historico(caminho=None) -> RepositorioHistorico:
    """Retorna uma instância do repositório de histórico de produção."""
    return RepositorioHistorico(caminho=caminho)


def obter_repositorio_estoque(caminho=None) -> RepositorioEstoque:
    """Retorna uma instância do repositório de estoque."""
    return RepositorioEstoque(caminho=caminho)


# Facade de alto nível
def criar_pedido(cliente, numero=None, observacoes=None, caminho=None):
    return obter_repositorio_pedidos(caminho).criar_pedido(cliente, numero=numero, observacoes=observacoes)


def obter_pedido(pedido_id=None, numero=None, caminho=None):
    return obter_repositorio_pedidos(caminho).obter_pedido(pedido_id=pedido_id, numero=numero)


def listar_pedidos(cliente=None, status=None, limite=100, caminho=None):
    return obter_repositorio_pedidos(caminho).listar_pedidos(cliente=cliente, status=status, limite=limite)


def registrar_producao(maquina, arquivo, m2, data_hora=None, material=None, caminho=None):
    return obter_repositorio_historico(caminho).registrar_producao(
        maquina=maquina, arquivo=arquivo, m2=m2, data_hora=data_hora, material=material
    )


def calcular_m2_produzido(maquina=None, data=None, caminho=None):
    return obter_repositorio_historico(caminho).calcular_m2_produzido(maquina=maquina, data=data)


def obter_saldo_estoque(codigo, caminho=None):
    return obter_repositorio_estoque(caminho).obter_saldo(codigo)


def obter_custo_m2_estoque(codigo, caminho=None):
    return obter_repositorio_estoque(caminho).obter_custo_m2(codigo)


def registrar_movimentacao_estoque(codigo, tipo, quantidade, observacao="", origem_pedido=None, caminho=None):
    return obter_repositorio_estoque(caminho).registrar_movimentacao(
        codigo=codigo, tipo=tipo, quantidade=quantidade, observacao=observacao, origem_pedido=origem_pedido
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
    "RepositorioMaquinas",
    "obter_repositorio_pedidos",
    "obter_repositorio_montagens",
    "obter_repositorio_historico",
    "obter_repositorio_estoque",
    "obter_repositorio_maquinas",
    "criar_pedido",
    "obter_pedido",
    "listar_pedidos",
    "registrar_producao",
    "calcular_m2_produzido",
    "obter_saldo_estoque",
    "obter_custo_m2_estoque",
    "registrar_movimentacao_estoque",
]
