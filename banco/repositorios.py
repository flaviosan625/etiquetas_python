"""
Repositórios de acesso a dados para o subsistema relacional SQLite.

Implementa operações para:
  - RepositorioPedidos: criação de pedidos, itens, consultas e transições de status.
  - RepositorioMontagens: folhas/bobinas de montagem e alocação de peças.
  - RepositorioHistorico: registro de produção e cálculos de m² por máquina/data.
  - RepositorioEstoque: catálogo de materiais, saldos, custos e movimentações auditáveis.
"""
from __future__ import annotations

import contextlib
import json
import sqlite3
import uuid
from datetime import datetime
from typing import Any, Dict, Generator, List, Optional, Union

from banco.conexao import abrir_conexao, CaminhoBanco


def _linha_para_dict(row: Optional[sqlite3.Row]) -> Optional[Dict[str, Any]]:
    if row is None:
        return None
    d = dict(row)
    # Converte colunas JSON se existirem
    for k in ("variante_vinculada", "metadados", "detalhes"):
        if k in d and isinstance(d[k], str) and d[k].strip().startswith(("{", "[")):
            try:
                d[k] = json.loads(d[k])
            except Exception:
                pass
    return d


class RepositorioBase:
    """Classe base que suporta injeção de conexão existente ou caminho do banco."""

    def __init__(
        self,
        conexao: Optional[sqlite3.Connection] = None,
        caminho: Optional[CaminhoBanco] = None,
    ):
        self._conexao = conexao
        self._caminho = caminho

    @contextlib.contextmanager
    def _obter_conexao(self) -> Generator[sqlite3.Connection, None, None]:
        if self._conexao is not None:
            yield self._conexao
        else:
            with abrir_conexao(self._caminho) as conn:
                yield conn


class RepositorioPedidos(RepositorioBase):
    """Gerencia pedidos (OS/Lotes) e seus respectivos itens de produção."""

    def criar_pedido(
        self,
        cliente: str,
        numero: Optional[str] = None,
        observacoes: Optional[str] = None,
        status: str = "pendente",
        metadados: Optional[Dict[str, Any]] = None,
        data_criacao: Optional[str] = None,
    ) -> int:
        if not cliente or not cliente.strip():
            raise ValueError("O nome do cliente é obrigatório para criar um pedido.")

        if not numero:
            ts = datetime.now().strftime("%Y%m%d%H%M%S")
            numero = f"PED-{ts}-{uuid.uuid4().hex[:6].upper()}"

        data_hora = data_criacao or datetime.now().isoformat()
        meta_str = json.dumps(metadados, ensure_ascii=False) if metadados else None

        with self._obter_conexao() as conn:
            cursor = conn.execute(
                """
                INSERT INTO pedidos (numero, cliente, data_criacao, data_atualizacao, status, observacoes, metadados)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (numero, cliente.strip(), data_hora, data_hora, status, observacoes, meta_str),
            )
            return int(cursor.lastrowid)

    def adicionar_item(
        self,
        pedido_id: int,
        arquivo: str,
        material: str,
        largura_mm: float,
        altura_mm: float,
        quantidade: int = 1,
        variante: Optional[str] = None,
        m2_unitario: Optional[float] = None,
        status: str = "pendente",
        montagem_id: Optional[int] = None,
        metadados: Optional[Dict[str, Any]] = None,
    ) -> int:
        if quantidade <= 0:
            raise ValueError("A quantidade do item deve ser maior que zero.")

        if m2_unitario is None:
            m2_unitario = round((float(largura_mm) * float(altura_mm)) / 1_000_000.0, 4)
        m2_total = round(m2_unitario * quantidade, 4)
        meta_str = json.dumps(metadados, ensure_ascii=False) if metadados else None

        with self._obter_conexao() as conn:
            # Valida existência do pedido caso foreign_keys estejam ativas
            cursor = conn.execute(
                """
                INSERT INTO itens_pedido (
                    pedido_id, arquivo, material, variante, largura_mm, altura_mm,
                    quantidade, m2_unitario, m2_total, status, montagem_id, metadados
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    pedido_id, arquivo, material, variante, float(largura_mm), float(altura_mm),
                    quantidade, m2_unitario, m2_total, status, montagem_id, meta_str,
                ),
            )
            item_id = int(cursor.lastrowid)

            # Atualiza totais do pedido
            conn.execute(
                """
                UPDATE pedidos
                SET total_m2 = (SELECT ROUND(COALESCE(SUM(m2_total), 0.0), 4) FROM itens_pedido WHERE pedido_id = ?),
                    total_itens = (SELECT COALESCE(SUM(quantidade), 0) FROM itens_pedido WHERE pedido_id = ?),
                    data_atualizacao = ?
                WHERE id = ?
                """,
                (pedido_id, pedido_id, datetime.now().isoformat(), pedido_id),
            )
            return item_id

    def adicionar_itens(self, pedido_id: int, itens: List[Dict[str, Any]]) -> List[int]:
        ids = []
        for item in itens:
            item_id = self.adicionar_item(
                pedido_id=pedido_id,
                arquivo=item["arquivo"],
                material=item["material"],
                largura_mm=item["largura_mm"],
                altura_mm=item["altura_mm"],
                quantidade=item.get("quantidade", 1),
                variante=item.get("variante"),
                m2_unitario=item.get("m2_unitario"),
                status=item.get("status", "pendente"),
                montagem_id=item.get("montagem_id"),
                metadados=item.get("metadados"),
            )
            ids.append(item_id)
        return ids

    def obter_pedido(
        self,
        pedido_id: Optional[int] = None,
        numero: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        if pedido_id is None and numero is None:
            raise ValueError("Informe pedido_id ou numero para consulta.")

        with self._obter_conexao() as conn:
            if pedido_id is not None:
                row = conn.execute("SELECT * FROM pedidos WHERE id = ?", (pedido_id,)).fetchone()
            else:
                row = conn.execute("SELECT * FROM pedidos WHERE numero = ?", (numero,)).fetchone()

            pedido = _linha_para_dict(row)
            if not pedido:
                return None

            cursor_itens = conn.execute(
                "SELECT * FROM itens_pedido WHERE pedido_id = ? ORDER BY id ASC",
                (pedido["id"],),
            )
            pedido["itens"] = [_linha_para_dict(i) for i in cursor_itens.fetchall()]
            return pedido

    def listar_pedidos(
        self,
        cliente: Optional[str] = None,
        status: Optional[str] = None,
        data_inicio: Optional[str] = None,
        data_fim: Optional[str] = None,
        limite: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        clausulas = []
        params: List[Any] = []

        if cliente:
            clausulas.append("cliente LIKE ?")
            params.append(f"%{cliente.strip()}%")
        if status:
            clausulas.append("status = ?")
            params.append(status)
        if data_inicio:
            clausulas.append("data_criacao >= ?")
            params.append(data_inicio)
        if data_fim:
            clausulas.append("data_criacao <= ?")
            params.append(data_fim)

        where = f"WHERE {' AND '.join(clausulas)}" if clausulas else ""
        query = f"SELECT * FROM pedidos {where} ORDER BY id DESC LIMIT ? OFFSET ?"
        params.extend([limite, offset])

        with self._obter_conexao() as conn:
            rows = conn.execute(query, params).fetchall()
            return [_linha_para_dict(r) for r in rows]

    def atualizar_status(self, pedido_id: int, novo_status: str) -> bool:
        agora = datetime.now().isoformat()
        with self._obter_conexao() as conn:
            cur = conn.execute(
                "UPDATE pedidos SET status = ?, data_atualizacao = ? WHERE id = ?",
                (novo_status, agora, pedido_id),
            )
            return cur.rowcount > 0

    def atualizar_status_item(self, item_id: int, novo_status: str) -> bool:
        with self._obter_conexao() as conn:
            cur = conn.execute(
                "UPDATE itens_pedido SET status = ? WHERE id = ?",
                (novo_status, item_id),
            )
            return cur.rowcount > 0

    def excluir_pedido(self, pedido_id: int) -> bool:
        with self._obter_conexao() as conn:
            cur = conn.execute("DELETE FROM pedidos WHERE id = ?", (pedido_id,))
            return cur.rowcount > 0


class RepositorioMontagens(RepositorioBase):
    """Gerencia registros de montagens (bobinas e chapas) e o layout de peças alocadas."""

    def criar_montagem(
        self,
        codigo: str,
        tipo: str,
        material: str,
        largura_util_mm: float,
        comprimento_util_mm: float,
        maquina: Optional[str] = None,
        arquivo_saida: Optional[str] = None,
        observacoes: Optional[str] = None,
        status: str = "gerada",
        metadados: Optional[Dict[str, Any]] = None,
        data_criacao: Optional[str] = None,
    ) -> int:
        if not codigo or not codigo.strip():
            raise ValueError("O código da montagem é obrigatório.")

        area_total_m2 = round((float(largura_util_mm) * float(comprimento_util_mm)) / 1_000_000.0, 4)
        data_hora = data_criacao or datetime.now().isoformat()
        meta_str = json.dumps(metadados, ensure_ascii=False) if metadados else None

        with self._obter_conexao() as conn:
            cursor = conn.execute(
                """
                INSERT INTO montagens (
                    codigo, tipo, maquina, material, largura_util_mm, comprimento_util_mm,
                    aproveitamento_percentual, area_total_m2, area_usada_m2,
                    arquivo_saida, data_criacao, status, observacoes, metadados
                ) VALUES (?, ?, ?, ?, ?, ?, 0.0, ?, 0.0, ?, ?, ?, ?, ?)
                """,
                (
                    codigo.strip(), tipo, maquina, material, float(largura_util_mm),
                    float(comprimento_util_mm), area_total_m2, arquivo_saida,
                    data_hora, status, observacoes, meta_str,
                ),
            )
            return int(cursor.lastrowid)

    def alocar_peca(
        self,
        montagem_id: int,
        nome_peca: str,
        largura_mm: float,
        altura_mm: float,
        pos_x_mm: float = 0.0,
        pos_y_mm: float = 0.0,
        girado: bool = False,
        item_pedido_id: Optional[int] = None,
        m2: Optional[float] = None,
        metadados: Optional[Dict[str, Any]] = None,
    ) -> int:
        if m2 is None:
            m2 = round((float(largura_mm) * float(altura_mm)) / 1_000_000.0, 4)
        meta_str = json.dumps(metadados, ensure_ascii=False) if metadados else None

        with self._obter_conexao() as conn:
            cursor = conn.execute(
                """
                INSERT INTO itens_montagem (
                    montagem_id, item_pedido_id, nome_peca, largura_mm, altura_mm,
                    pos_x_mm, pos_y_mm, girado, m2, metadados
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    montagem_id, item_pedido_id, nome_peca, float(largura_mm), float(altura_mm),
                    float(pos_x_mm), float(pos_y_mm), 1 if girado else 0, m2, meta_str,
                ),
            )
            peca_id = int(cursor.lastrowid)

            if item_pedido_id is not None:
                conn.execute(
                    "UPDATE itens_pedido SET montagem_id = ?, status = 'montado' WHERE id = ?",
                    (montagem_id, item_pedido_id),
                )

            # Recalcula área usada e aproveitamento percentual
            conn.execute(
                """
                UPDATE montagens
                SET area_usada_m2 = (
                        SELECT ROUND(COALESCE(SUM(m2), 0.0), 4) FROM itens_montagem WHERE montagem_id = ?
                    ),
                    aproveitamento_percentual = (
                        SELECT CASE
                            WHEN area_total_m2 > 0 THEN ROUND((COALESCE(SUM(m2), 0.0) / area_total_m2) * 100.0, 2)
                            ELSE 0.0
                        END
                        FROM itens_montagem WHERE montagem_id = ?
                    )
                WHERE id = ?
                """,
                (montagem_id, montagem_id, montagem_id),
            )
            return peca_id

    def alocar_pecas(self, montagem_id: int, pecas: List[Dict[str, Any]]) -> List[int]:
        ids = []
        for peca in pecas:
            peca_id = self.alocar_peca(
                montagem_id=montagem_id,
                nome_peca=peca["nome_peca"],
                largura_mm=peca["largura_mm"],
                altura_mm=peca["altura_mm"],
                pos_x_mm=peca.get("pos_x_mm", 0.0),
                pos_y_mm=peca.get("pos_y_mm", 0.0),
                girado=peca.get("girado", False),
                item_pedido_id=peca.get("item_pedido_id"),
                m2=peca.get("m2"),
                metadados=peca.get("metadados"),
            )
            ids.append(peca_id)
        return ids

    def obter_montagem(
        self,
        montagem_id: Optional[int] = None,
        codigo: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        if montagem_id is None and codigo is None:
            raise ValueError("Informe montagem_id ou codigo para consulta.")

        with self._obter_conexao() as conn:
            if montagem_id is not None:
                row = conn.execute("SELECT * FROM montagens WHERE id = ?", (montagem_id,)).fetchone()
            else:
                row = conn.execute("SELECT * FROM montagens WHERE codigo = ?", (codigo,)).fetchone()

            montagem = _linha_para_dict(row)
            if not montagem:
                return None

            cursor_pecas = conn.execute(
                "SELECT * FROM itens_montagem WHERE montagem_id = ? ORDER BY id ASC",
                (montagem["id"],),
            )
            montagem["pecas"] = [_linha_para_dict(p) for p in cursor_pecas.fetchall()]
            return montagem

    def listar_montagens(
        self,
        material: Optional[str] = None,
        tipo: Optional[str] = None,
        maquina: Optional[str] = None,
        status: Optional[str] = None,
        limite: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        clausulas = []
        params: List[Any] = []

        if material:
            clausulas.append("material = ?")
            params.append(material)
        if tipo:
            clausulas.append("tipo = ?")
            params.append(tipo)
        if maquina:
            clausulas.append("maquina = ?")
            params.append(maquina)
        if status:
            clausulas.append("status = ?")
            params.append(status)

        where = f"WHERE {' AND '.join(clausulas)}" if clausulas else ""
        query = f"SELECT * FROM montagens {where} ORDER BY id DESC LIMIT ? OFFSET ?"
        params.extend([limite, offset])

        with self._obter_conexao() as conn:
            rows = conn.execute(query, params).fetchall()
            return [_linha_para_dict(r) for r in rows]

    def atualizar_status(self, montagem_id: int, novo_status: str) -> bool:
        with self._obter_conexao() as conn:
            cur = conn.execute(
                "UPDATE montagens SET status = ? WHERE id = ?",
                (novo_status, montagem_id),
            )
            return cur.rowcount > 0


class RepositorioHistorico(RepositorioBase):
    """Gerencia telemetria permanente de produção por máquina, logs e cálculo de m²."""

    def registrar_producao(
        self,
        maquina: str,
        arquivo: str,
        m2: float,
        data_hora: Optional[str] = None,
        material: Optional[str] = None,
        tamanho_bytes: int = 0,
        girado: bool = False,
        pedido_id: Optional[int] = None,
        montagem_id: Optional[int] = None,
        status: str = "concluido",
        detalhes: Optional[Dict[str, Any]] = None,
    ) -> int:
        dh = data_hora or datetime.now().isoformat()
        # Garante data em formato YYYY-MM-DD para índices de agregação
        dt_str = dh[:10] if len(dh) >= 10 else datetime.now().strftime("%Y-%m-%d")
        detalhes_str = json.dumps(detalhes, ensure_ascii=False) if detalhes else None

        with self._obter_conexao() as conn:
            cursor = conn.execute(
                """
                INSERT INTO historico_producao (
                    data_hora, data, maquina, arquivo, material, m2,
                    tamanho_bytes, girado, pedido_id, montagem_id, status, detalhes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    dh, dt_str, maquina, arquivo, material, round(float(m2), 4),
                    int(tamanho_bytes), 1 if girado else 0, pedido_id, montagem_id,
                    status, detalhes_str,
                ),
            )
            return int(cursor.lastrowid)

    def obter_historico(
        self,
        limite: int = 100,
        maquina: Optional[str] = None,
        data_inicio: Optional[str] = None,
        data_fim: Optional[str] = None,
        material: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        clausulas = []
        params: List[Any] = []

        if maquina:
            clausulas.append("maquina = ?")
            params.append(maquina)
        if material:
            clausulas.append("material = ?")
            params.append(material)
        if data_inicio:
            clausulas.append("data >= ?")
            params.append(data_inicio)
        if data_fim:
            clausulas.append("data <= ?")
            params.append(data_fim)

        where = f"WHERE {' AND '.join(clausulas)}" if clausulas else ""
        query = f"SELECT * FROM historico_producao {where} ORDER BY id DESC LIMIT ?"
        params.append(limite)

        with self._obter_conexao() as conn:
            rows = conn.execute(query, params).fetchall()
            return [_linha_para_dict(r) for r in rows]

    def calcular_m2_produzido(
        self,
        maquina: Optional[str] = None,
        data: Optional[str] = None,
        data_inicio: Optional[str] = None,
        data_fim: Optional[str] = None,
    ) -> float:
        clausulas = ["status = 'concluido'"]
        params: List[Any] = []

        if maquina:
            clausulas.append("maquina = ?")
            params.append(maquina)
        if data:
            clausulas.append("data = ?")
            params.append(data)
        if data_inicio:
            clausulas.append("data >= ?")
            params.append(data_inicio)
        if data_fim:
            clausulas.append("data <= ?")
            params.append(data_fim)

        where = f"WHERE {' AND '.join(clausulas)}"
        query = f"SELECT COALESCE(SUM(m2), 0.0) FROM historico_producao {where}"

        with self._obter_conexao() as conn:
            resultado = conn.execute(query, params).fetchone()[0]
            return round(float(resultado), 4)

    def resumo_producao_por_maquina(
        self,
        data: Optional[str] = None,
        data_inicio: Optional[str] = None,
        data_fim: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        clausulas = ["status = 'concluido'"]
        params: List[Any] = []

        if data:
            clausulas.append("data = ?")
            params.append(data)
        if data_inicio:
            clausulas.append("data >= ?")
            params.append(data_inicio)
        if data_fim:
            clausulas.append("data <= ?")
            params.append(data_fim)

        where = f"WHERE {' AND '.join(clausulas)}"
        query = f"""
            SELECT maquina, COUNT(*) as total_trabalhos, ROUND(SUM(m2), 4) as total_m2
            FROM historico_producao
            {where}
            GROUP BY maquina
            ORDER BY total_m2 DESC
        """

        with self._obter_conexao() as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]

    def resumo_producao_diaria(
        self,
        maquina: Optional[str] = None,
        data_inicio: Optional[str] = None,
        data_fim: Optional[str] = None,
        limite_dias: int = 30,
    ) -> List[Dict[str, Any]]:
        clausulas = ["status = 'concluido'"]
        params: List[Any] = []

        if maquina:
            clausulas.append("maquina = ?")
            params.append(maquina)
        if data_inicio:
            clausulas.append("data >= ?")
            params.append(data_inicio)
        if data_fim:
            clausulas.append("data <= ?")
            params.append(data_fim)

        where = f"WHERE {' AND '.join(clausulas)}"
        query = f"""
            SELECT data, maquina, COUNT(*) as total_trabalhos, ROUND(SUM(m2), 4) as total_m2
            FROM historico_producao
            {where}
            GROUP BY data, maquina
            ORDER BY data DESC, maquina ASC
            LIMIT ?
        """
        params.append(limite_dias)

        with self._obter_conexao() as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]


class RepositorioEstoque(RepositorioBase):
    """Gerencia catálogo de materiais, saldos, custos e histórico auditável de movimentações."""

    def cadastrar_produto(
        self,
        codigo: str,
        descricao: str,
        tipo: str,
        unidade: str,
        categoria_vinculada: Optional[str] = None,
        variante_vinculada: Optional[Union[str, Dict[str, Any]]] = None,
        comprimento_rolo_m: float = 0.0,
        largura_m: float = 0.0,
        minimo: float = 0.0,
        maximo: float = 0.0,
        codigo_planilha: Optional[str] = None,
        capacidade_ml: Optional[float] = None,
        custo_unitario: Optional[float] = None,
        custo_m2: Optional[float] = None,
        saldo_inicial: float = 0.0,
        metadados: Optional[Dict[str, Any]] = None,
    ) -> int:
        if not codigo or not codigo.strip():
            raise ValueError("O código do produto é obrigatório.")

        var_str = (
            json.dumps(variante_vinculada, ensure_ascii=False)
            if isinstance(variante_vinculada, dict)
            else (str(variante_vinculada) if variante_vinculada else None)
        )
        meta_str = json.dumps(metadados, ensure_ascii=False) if metadados else None

        # Cálculo automático de custo por m² se não fornecido
        if custo_m2 is None and custo_unitario is not None and custo_unitario > 0:
            if tipo == "rolo" and comprimento_rolo_m > 0 and largura_m > 0:
                custo_m2 = round(custo_unitario / (comprimento_rolo_m * largura_m), 4)
            elif tipo == "chapa" and comprimento_rolo_m > 0 and largura_m > 0:
                custo_m2 = round(custo_unitario / (comprimento_rolo_m * largura_m), 4)

        with self._obter_conexao() as conn:
            cursor = conn.execute(
                """
                INSERT INTO estoque (
                    codigo, descricao, tipo, unidade, categoria_vinculada, variante_vinculada,
                    comprimento_rolo_m, largura_m, minimo, maximo, codigo_planilha,
                    capacidade_ml, custo_unitario, custo_m2, saldo, metadados
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0.0, ?)
                """,
                (
                    codigo.strip(), descricao.strip(), tipo, unidade, categoria_vinculada,
                    var_str, float(comprimento_rolo_m), float(largura_m), float(minimo),
                    float(maximo), codigo_planilha, capacidade_ml, custo_unitario,
                    custo_m2, meta_str,
                ),
            )
            produto_id = int(cursor.lastrowid)

            if saldo_inicial != 0.0:
                self.registrar_movimentacao(
                    codigo=codigo,
                    tipo="ajuste",
                    quantidade=saldo_inicial,
                    observacao="Saldo inicial no cadastro",
                )
            return produto_id

    def atualizar_produto(self, codigo: str, **campos: Any) -> bool:
        if not campos:
            return False

        colunas = []
        valores = []
        for chave, valor in campos.items():
            if chave == "variante_vinculada" and isinstance(valor, dict):
                valor = json.dumps(valor, ensure_ascii=False)
            elif chave == "metadados" and isinstance(valor, dict):
                valor = json.dumps(valor, ensure_ascii=False)
            colunas.append(f"{chave} = ?")
            valores.append(valor)

        valores.append(codigo)
        sql = f"UPDATE estoque SET {', '.join(colunas)} WHERE codigo = ?"

        with self._obter_conexao() as conn:
            cur = conn.execute(sql, valores)
            return cur.rowcount > 0

    def obter_produto(self, codigo: str) -> Optional[Dict[str, Any]]:
        with self._obter_conexao() as conn:
            row = conn.execute("SELECT * FROM estoque WHERE codigo = ?", (codigo,)).fetchone()
            return _linha_para_dict(row)

    def listar_produtos(
        self,
        tipo: Optional[str] = None,
        categoria: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        clausulas = []
        params: List[Any] = []

        if tipo:
            clausulas.append("tipo = ?")
            params.append(tipo)
        if categoria:
            clausulas.append("categoria_vinculada = ?")
            params.append(categoria)

        where = f"WHERE {' AND '.join(clausulas)}" if clausulas else ""
        query = f"SELECT * FROM estoque {where} ORDER BY codigo ASC"

        with self._obter_conexao() as conn:
            rows = conn.execute(query, params).fetchall()
            return [_linha_para_dict(r) for r in rows]

    def registrar_movimentacao(
        self,
        codigo: str,
        tipo: str,
        quantidade: float,
        observacao: str = "",
        origem_pedido: Optional[str] = None,
        estorno_de: Optional[int] = None,
        data_hora: Optional[str] = None,
        custo_momento: Optional[float] = None,
    ) -> int:
        if tipo not in ("entrada", "saida", "ajuste"):
            raise ValueError(f"Tipo de movimentação inválido: '{tipo}'. Use entrada, saida ou ajuste.")

        dh = data_hora or datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with self._obter_conexao() as conn:
            prod = conn.execute("SELECT custo_unitario FROM estoque WHERE codigo = ?", (codigo,)).fetchone()
            if not prod:
                raise ValueError(f"Produto '{codigo}' não encontrado no estoque.")

            custo_reg = custo_momento if custo_momento is not None else prod["custo_unitario"]

            cursor = conn.execute(
                """
                INSERT INTO movimentacoes_estoque (
                    produto_codigo, tipo, quantidade, data_hora, observacao,
                    origem_pedido, estorno_de, custo_momento
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (codigo, tipo, round(float(quantidade), 4), dh, observacao, origem_pedido, estorno_de, custo_reg),
            )
            mov_id = int(cursor.lastrowid)

            # Mantém a coluna saldo em estoque rigorosamente sincronizada com o somatório
            conn.execute(
                """
                UPDATE estoque
                SET saldo = (
                    SELECT ROUND(COALESCE(SUM(quantidade), 0.0), 4)
                    FROM movimentacoes_estoque
                    WHERE produto_codigo = ?
                )
                WHERE codigo = ?
                """,
                (codigo, codigo),
            )
            return mov_id

    def obter_saldo(self, codigo: str) -> float:
        with self._obter_conexao() as conn:
            row = conn.execute("SELECT saldo FROM estoque WHERE codigo = ?", (codigo,)).fetchone()
            if row is None:
                raise ValueError(f"Produto '{codigo}' não cadastrado no estoque.")
            return round(float(row["saldo"]), 4)

    def obter_custo_m2(self, codigo: str) -> Optional[float]:
        with self._obter_conexao() as conn:
            row = conn.execute("SELECT custo_m2 FROM estoque WHERE codigo = ?", (codigo,)).fetchone()
            if row is None:
                raise ValueError(f"Produto '{codigo}' não cadastrado no estoque.")
            val = row["custo_m2"]
            return round(float(val), 4) if val is not None else None

    def atualizar_custo(
        self,
        codigo: str,
        custo_unitario: Optional[float] = None,
        custo_m2: Optional[float] = None,
    ) -> bool:
        campos = {}
        if custo_unitario is not None:
            campos["custo_unitario"] = float(custo_unitario)
        if custo_m2 is not None:
            campos["custo_m2"] = float(custo_m2)
        return self.atualizar_produto(codigo, **campos)

    def listar_movimentacoes(
        self,
        codigo: Optional[str] = None,
        tipo: Optional[str] = None,
        limite: int = 100,
    ) -> List[Dict[str, Any]]:
        clausulas = []
        params: List[Any] = []

        if codigo:
            clausulas.append("produto_codigo = ?")
            params.append(codigo)
        if tipo:
            clausulas.append("tipo = ?")
            params.append(tipo)

        where = f"WHERE {' AND '.join(clausulas)}" if clausulas else ""
        query = f"SELECT * FROM movimentacoes_estoque {where} ORDER BY id DESC LIMIT ?"
        params.append(limite)

        with self._obter_conexao() as conn:
            rows = conn.execute(query, params).fetchall()
            return [_linha_para_dict(r) for r in rows]

    def desfazer_movimentacao(
        self,
        movimentacao_id: int,
        observacao: str = "Estorno de movimentação anterior",
    ) -> Optional[int]:
        with self._obter_conexao() as conn:
            row = conn.execute(
                "SELECT * FROM movimentacoes_estoque WHERE id = ?",
                (movimentacao_id,),
            ).fetchone()
            if not row:
                return None

            # Não permite estornar movimento que já foi estornado
            ja_estornado = conn.execute(
                "SELECT id FROM movimentacoes_estoque WHERE estorno_de = ?",
                (movimentacao_id,),
            ).fetchone()
            if ja_estornado:
                raise ValueError(f"A movimentação {movimentacao_id} já foi estornada pela movimentação {ja_estornado['id']}.")

            orig = dict(row)
            qtd_inversa = -round(float(orig["quantidade"]), 4)
            obs = f"{observacao} (ID #{movimentacao_id})"

            return self.registrar_movimentacao(
                codigo=orig["produto_codigo"],
                tipo="ajuste",
                quantidade=qtd_inversa,
                observacao=obs,
                origem_pedido=orig.get("origem_pedido"),
                estorno_de=movimentacao_id,
            )
