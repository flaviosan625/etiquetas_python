"""
Módulo de migração e inicialização do banco relacional SQLite.

Responsável por:
  - Inicializar esquema relacional e índices (inicializar_banco)
  - Migrar dados legados de estoque.json para a persistência relacional (migrar_estoque_legado)
"""
from __future__ import annotations

import json
import pathlib
import re
from typing import Any, Dict, Optional, Union

from banco.conexao import abrir_conexao, obter_caminho_banco, CaminhoBanco
from banco.repositorios import RepositorioEstoque

_PASTA_BANCO = pathlib.Path(__file__).resolve().parent
_CAMINHO_ESQUEMA = _PASTA_BANCO / "esquema.sql"


def inicializar_banco(caminho: Optional[CaminhoBanco] = None) -> None:
    """
    Executa o script de esquema inicial caso as tabelas não existam.
    Cria tabelas relacionais com integridade referencial e índices de busca.
    """
    if not _CAMINHO_ESQUEMA.exists():
        raise FileNotFoundError(f"Arquivo de esquema SQL não encontrado em: {_CAMINHO_ESQUEMA}")

    with open(_CAMINHO_ESQUEMA, "r", encoding="utf-8") as f:
        script_sql = f.read()

    with abrir_conexao(caminho) as conn:
        conn.executescript(script_sql)

        # Validação de integridade das tabelas esperadas
        tabelas_esperadas = {
            "pedidos", "itens_pedido", "montagens", "itens_montagem",
            "historico_producao", "estoque", "movimentacoes_estoque"
        }
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tabelas_existentes = {row[0] for row in cursor.fetchall()}
        ausentes = tabelas_esperadas - tabelas_existentes
        if ausentes:
            raise RuntimeError(f"Falha na criação das tabelas no SQLite. Ausentes: {ausentes}")


def _extrair_dimensoes_rolo(descricao: str) -> tuple[float, float]:
    """
    Tenta inferir largura_m e comprimento_m a partir da descrição do produto.
    Ex: 'Lona Fosca Front 440g 3,20x50m' -> (3.20, 50.0)
    """
    largura = 0.0
    comprimento = 0.0

    m_dim = re.search(r"(\d+[\.,]\d+)x(\d+[\.,]?\d*)m", descricao, re.IGNORECASE)
    if m_dim:
        try:
            largura = float(m_dim.group(1).replace(",", "."))
            comprimento = float(m_dim.group(2).replace(",", "."))
            return largura, comprimento
        except Exception:
            pass

    m_larg = re.search(r"(\d+[\.,]\d+)m", descricao, re.IGNORECASE)
    if m_larg:
        try:
            largura = float(m_larg.group(1).replace(",", "."))
        except Exception:
            pass

    return largura, comprimento


def migrar_estoque_legado(
    caminho_estoque_json: Optional[Union[str, pathlib.Path]] = None,
    caminho_banco: Optional[CaminhoBanco] = None,
) -> Dict[str, Any]:
    """
    Importa o arquivo JSON legado (caminhos.ESTOQUE ou caminho explícito) para o SQLite.
    Insere o catálogo em `estoque` e todo o histórico em `movimentacoes_estoque`,
    recalculando rigorosamente os saldos e custos unitários/m².
    """
    caminho_json = None
    if caminho_estoque_json:
        caminho_json = pathlib.Path(caminho_estoque_json)
    else:
        try:
            import caminhos
            if hasattr(caminhos, "ESTOQUE") and caminhos.ESTOQUE.exists():
                caminho_json = caminhos.ESTOQUE
        except Exception:
            pass

        if not caminho_json or not caminho_json.exists():
            candidato_local = pathlib.Path("estoque.json")
            if candidato_local.exists():
                caminho_json = candidato_local

    if not caminho_json or not caminho_json.exists():
        return {
            "status": "arquivo_nao_encontrado",
            "produtos_migrados": 0,
            "movimentos_migrados": 0,
        }

    try:
        with open(caminho_json, "r", encoding="utf-8") as f:
            dados = json.load(f)
    except Exception as e:
        return {
            "status": "erro_leitura",
            "mensagem": str(e),
            "produtos_migrados": 0,
            "movimentos_migrados": 0,
        }

    produtos = dados.get("produtos", {})
    movimentos = dados.get("movimentos", [])

    # Garante que o banco está estruturado
    inicializar_banco(caminho_banco)

    with abrir_conexao(caminho_banco) as conn:
        repo = RepositorioEstoque(conexao=conn)
        produtos_migrados = 0
        movimentos_migrados = 0

        for codigo, prod in produtos.items():
            existente = repo.obter_produto(codigo)
            tipo = prod.get("tipo", "insumo")
            comprimento = float(prod.get("comprimento_rolo_m") or 0.0)
            custo = prod.get("custo")
            custo_unit = float(custo) if custo is not None else None

            larg_inferida, comp_inferido = _extrair_dimensoes_rolo(prod.get("descricao", ""))
            largura = larg_inferida
            if comprimento == 0.0 and comp_inferido > 0:
                comprimento = comp_inferido

            custo_m2 = None
            if custo_unit is not None and custo_unit > 0:
                if tipo == "rolo" and comprimento > 0 and largura > 0:
                    custo_m2 = round(custo_unit / (comprimento * largura), 4)
                elif tipo == "chapa":
                    # Chapa padrão 2.44x1.22 = 2.9768 m²
                    custo_m2 = round(custo_unit / 2.9768, 4)

            if not existente:
                repo.cadastrar_produto(
                    codigo=codigo,
                    descricao=prod.get("descricao", codigo),
                    tipo=tipo,
                    unidade=prod.get("unidade", "un"),
                    categoria_vinculada=prod.get("categoria_vinculada"),
                    variante_vinculada=prod.get("variante_vinculada"),
                    comprimento_rolo_m=comprimento,
                    largura_m=largura,
                    minimo=float(prod.get("minimo", 0.0)),
                    maximo=float(prod.get("maximo", 0.0)),
                    codigo_planilha=prod.get("codigo_planilha"),
                    capacidade_ml=prod.get("capacidade_ml"),
                    custo_unitario=custo_unit,
                    custo_m2=custo_m2,
                    saldo_inicial=0.0,
                )
                produtos_migrados += 1
            else:
                # Atualiza custos e metadados se não existiam
                campos_up = {}
                if existente.get("custo_unitario") is None and custo_unit is not None:
                    campos_up["custo_unitario"] = custo_unit
                if existente.get("custo_m2") is None and custo_m2 is not None:
                    campos_up["custo_m2"] = custo_m2
                if campos_up:
                    repo.atualizar_produto(codigo, **campos_up)

        # Migração das movimentações históricas
        for mov in movimentos:
            cod_prod = mov.get("produto")
            if not cod_prod:
                continue

            # Se o produto não estiver cadastrado, cria registro básico para integridade
            if not repo.obter_produto(cod_prod):
                repo.cadastrar_produto(
                    codigo=cod_prod,
                    descricao=f"Material {cod_prod}",
                    tipo="insumo",
                    unidade="un",
                )
                produtos_migrados += 1

            dh = mov.get("data", "")
            tipo_mov = mov.get("tipo", "ajuste")
            qtd = float(mov.get("quantidade", 0.0))
            obs = mov.get("observacao", "") or ""
            origem = mov.get("origem_pedido")

            # Evita duplicar importação caso seja rodado mais de uma vez
            ja_existe = conn.execute(
                """
                SELECT id FROM movimentacoes_estoque
                WHERE produto_codigo = ? AND data_hora = ? AND quantidade = ? AND tipo = ?
                """,
                (cod_prod, dh, qtd, tipo_mov),
            ).fetchone()

            if not ja_existe:
                repo.registrar_movimentacao(
                    codigo=cod_prod,
                    tipo=tipo_mov,
                    quantidade=qtd,
                    observacao=obs,
                    origem_pedido=origem,
                    estorno_de=mov.get("estorno_de"),
                    data_hora=dh,
                )
                movimentos_migrados += 1

        # Sincronização final de saldos
        conn.execute(
            """
            UPDATE estoque
            SET saldo = (
                SELECT ROUND(COALESCE(SUM(quantidade), 0.0), 4)
                FROM movimentacoes_estoque
                WHERE produto_codigo = estoque.codigo
            )
            """
        )

        return {
            "status": "sucesso",
            "produtos_migrados": produtos_migrados,
            "movimentos_migrados": movimentos_migrados,
        }
