"""
Testes abrangentes do subsistema de persistência relacional SQLite (WAL).

Cobre:
  1. Inicialização do esquema, verificação do modo WAL e foreign keys
  2. Isolamento transacional e rollback em caso de falha
  3. Repositório de pedidos e itens com integridade referencial e deleção em cascata
  4. Repositório de montagens e alocação de peças com métricas de aproveitamento
  5. Registro e agregações de histórico de produção por máquina e data
  6. Controle de estoque, cálculo de custo por m² e histórico de movimentações
  7. Migração de dados legados do arquivo estoque.json
  8. Concorrência multithread real com múltiplas conexões simultâneas sob WAL
"""
import json
import sqlite3
import threading
from datetime import datetime
import pytest

import banco
from banco import (
    abrir_conexao,
    criar_conexao,
    inicializar_banco,
    migrar_estoque_legado,
    RepositorioPedidos,
    RepositorioMontagens,
    RepositorioHistorico,
    RepositorioEstoque,
)


@pytest.fixture
def db_path(tmp_path):
    """Caminho isolado para banco de teste em disco."""
    return tmp_path / "test_automacao.db"


def test_inicializacao_esquema_wal_e_foreign_keys(db_path):
    """Verifica criação de tabelas, índices e ativação de PRAGMA WAL e foreign keys."""
    inicializar_banco(db_path)
    assert db_path.exists()

    with abrir_conexao(db_path) as conn:
        # 1. Verifica modo WAL
        modo_journal = conn.execute("PRAGMA journal_mode;").fetchone()[0]
        assert modo_journal.lower() == "wal"

        # 2. Verifica Foreign Keys ativas
        fk = conn.execute("PRAGMA foreign_keys;").fetchone()[0]
        assert fk == 1

        # 3. Verifica existência de todas as tabelas principais
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tabelas = {row["name"] for row in cursor.fetchall()}
        tabelas_esperadas = {
            "pedidos", "itens_pedido", "montagens", "itens_montagem",
            "historico_producao", "estoque", "movimentacoes_estoque"
        }
        assert tabelas_esperadas.issubset(tabelas)

        # 4. Verifica índices de performance
        cursor_idx = conn.execute("SELECT name FROM sqlite_master WHERE type='index';")
        indices = {row["name"] for row in cursor_idx.fetchall()}
        assert "idx_pedidos_cliente" in indices
        assert "idx_pedidos_status" in indices
        assert "idx_pedidos_data" in indices
        assert "idx_itens_pedido_material" in indices
        assert "idx_historico_maquina" in indices
        assert "idx_historico_data" in indices
        assert "idx_estoque_codigo" in indices


def test_isolamento_transacional_e_rollback(db_path):
    """Verifica que transações com falha sofrem rollback e transações válidas persistem."""
    inicializar_banco(db_path)

    # Caso 1: Sucesso com commit automático ao sair do with
    with abrir_conexao(db_path) as conn:
        conn.execute(
            "INSERT INTO pedidos (numero, cliente, data_criacao, status) VALUES (?, ?, ?, ?)",
            ("PED-001", "CLIENTE TESTE SUCESSO", datetime.now().isoformat(), "pendente"),
        )

    with abrir_conexao(db_path) as conn:
        p1 = conn.execute("SELECT * FROM pedidos WHERE numero = 'PED-001'").fetchone()
        assert p1 is not None
        assert p1["cliente"] == "CLIENTE TESTE SUCESSO"

    # Caso 2: Falha no meio da transação gera rollback completo
    with pytest.raises(RuntimeError, match="Erro intencional de transacao"):
        with abrir_conexao(db_path) as conn:
            conn.execute(
                "INSERT INTO pedidos (numero, cliente, data_criacao, status) VALUES (?, ?, ?, ?)",
                ("PED-002", "CLIENTE TESTE FALHA", datetime.now().isoformat(), "pendente"),
            )
            # Simula falha catastrófica antes do fim do bloco
            raise RuntimeError("Erro intencional de transacao")

    # Garante que o pedido PED-002 não foi persistido
    with abrir_conexao(db_path) as conn:
        p2 = conn.execute("SELECT * FROM pedidos WHERE numero = 'PED-002'").fetchone()
        assert p2 is None


def test_repositorio_pedidos_itens_integridade_referencial(db_path):
    """Testa criação de pedido, adição de itens, cálculo de totais e restrição de integridade referencial."""
    inicializar_banco(db_path)
    repo = RepositorioPedidos(caminho=db_path)

    pedido_id = repo.criar_pedido(
        cliente="ACME CORP",
        numero="OS-2026-001",
        observacoes="Urgente para evento",
    )
    assert pedido_id > 0

    # Adiciona itens
    # Item 1: 1000 x 2000 mm = 2 m² x 2 un = 4 m²
    item1_id = repo.adicionar_item(
        pedido_id=pedido_id,
        arquivo="banner_entrada.pdf",
        material="LONA",
        largura_mm=1000,
        altura_mm=2000,
        quantidade=2,
    )
    # Item 2: 500 x 500 mm = 0.25 m² x 4 un = 1 m²
    item2_id = repo.adicionar_item(
        pedido_id=pedido_id,
        arquivo="adesivo_logo.pdf",
        material="ADESIVO",
        largura_mm=500,
        altura_mm=500,
        quantidade=4,
    )

    # Consulta pedido e verifica itens embutidos e totais calculados
    pedido = repo.obter_pedido(pedido_id=pedido_id)
    assert pedido is not None
    assert pedido["cliente"] == "ACME CORP"
    assert pedido["total_itens"] == 6  # 2 + 4
    assert pedido["total_m2"] == pytest.approx(5.0, 0.001)  # 4 + 1
    assert len(pedido["itens"]) == 2

    # Atualiza status do pedido e de item individual
    repo.atualizar_status(pedido_id, "em_producao")
    repo.atualizar_status_item(item1_id, "pronto")

    pedido_atualizado = repo.obter_pedido(pedido_id=pedido_id)
    assert pedido_atualizado["status"] == "em_producao"
    item1_atualizado = next(i for i in pedido_atualizado["itens"] if i["id"] == item1_id)
    assert item1_atualizado["status"] == "pronto"

    # Teste de integridade referencial: item apontando para pedido inexistente deve falhar
    with pytest.raises(sqlite3.IntegrityError):
        with abrir_conexao(db_path) as conn:
            conn.execute(
                """
                INSERT INTO itens_pedido (pedido_id, arquivo, material, largura_mm, altura_mm, quantidade)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (999999, "fantasma.pdf", "LONA", 100, 100, 1),
            )

    # Teste de deleção em cascata
    removido = repo.excluir_pedido(pedido_id)
    assert removido is True
    assert repo.obter_pedido(pedido_id=pedido_id) is None
    with abrir_conexao(db_path) as conn:
        itens_restantes = conn.execute("SELECT COUNT(*) FROM itens_pedido WHERE pedido_id = ?", (pedido_id,)).fetchone()[0]
        assert itens_restantes == 0


def test_repositorio_montagens_e_alocacao_pecas(db_path):
    """Testa cadastro de montagem de bobina e alocação de peças com aproveitamento percentual."""
    inicializar_banco(db_path)
    repo_p = RepositorioPedidos(caminho=db_path)
    repo_m = RepositorioMontagens(caminho=db_path)

    # Cria pedido e item
    pid = repo_p.criar_pedido(cliente="FESTA ALEMA")
    item_id = repo_p.adicionar_item(
        pedido_id=pid,
        arquivo="painel_principal.pdf",
        material="LONA",
        largura_mm=3000,
        altura_mm=2000,
        quantidade=1,
    )

    # Cria montagem: bobina 3200mm largura x 5000mm comprimento = 16 m²
    montagem_id = repo_m.criar_montagem(
        codigo="MONT-SWJ-001",
        tipo="bobina",
        material="LONA",
        largura_util_mm=3200,
        comprimento_util_mm=5000,
        maquina="SWJ-320EA",
    )
    assert montagem_id > 0

    # Aloca peça na montagem: 3000 x 2000 mm = 6 m² (6 / 16 = 37.5% de aproveitamento)
    peca_id = repo_m.alocar_peca(
        montagem_id=montagem_id,
        nome_peca="painel_principal.pdf",
        largura_mm=3000,
        altura_mm=2000,
        pos_x_mm=0,
        pos_y_mm=0,
        item_pedido_id=item_id,
    )
    assert peca_id > 0

    # Verifica aproveitamento na montagem
    montagem = repo_m.obter_montagem(montagem_id=montagem_id)
    assert montagem is not None
    assert montagem["area_total_m2"] == pytest.approx(16.0, 0.001)
    assert montagem["area_usada_m2"] == pytest.approx(6.0, 0.001)
    assert montagem["aproveitamento_percentual"] == pytest.approx(37.5, 0.01)
    assert len(montagem["pecas"]) == 1

    # Verifica que o item do pedido foi marcado como montado e vinculado
    pedido = repo_p.obter_pedido(pedido_id=pid)
    item = pedido["itens"][0]
    assert item["status"] == "montado"
    assert item["montagem_id"] == montagem_id


def test_repositorio_historico_producao_e_agregacoes(db_path):
    """Testa telemetria de produção, registro por máquina e cálculos analíticos de m²."""
    inicializar_banco(db_path)
    repo = RepositorioHistorico(caminho=db_path)

    # Registra trabalhos de produção
    repo.registrar_producao(
        maquina="DOCAN R5200",
        arquivo="lona_5x10_festa.pdf",
        m2=50.0,
        data_hora="2026-11-16T10:00:00",
        material="LONA",
    )
    repo.registrar_producao(
        maquina="DOCAN R5200",
        arquivo="lona_5x4_stand.pdf",
        m2=20.0,
        data_hora="2026-11-16T14:30:00",
        material="LONA",
    )
    repo.registrar_producao(
        maquina="SWJ-320EA",
        arquivo="adesivo_vitrine.pdf",
        m2=15.5,
        data_hora="2026-11-16T11:00:00",
        material="ADESIVO",
    )
    repo.registrar_producao(
        maquina="SWJ-320EA",
        arquivo="adesivo_ontem.pdf",
        m2=10.0,
        data_hora="2026-11-15T09:00:00",
        material="ADESIVO",
    )

    # 1. Total geral de m²
    total_geral = repo.calcular_m2_produzido()
    assert total_geral == pytest.approx(95.5, 0.001)

    # 2. Total por máquina DOCAN R5200 (50 + 20 = 70 m²)
    total_docan = repo.calcular_m2_produzido(maquina="DOCAN R5200")
    assert total_docan == pytest.approx(70.0, 0.001)

    # 3. Total por data 2026-11-16 (50 + 20 + 15.5 = 85.5 m²)
    total_hoje = repo.calcular_m2_produzido(data="2026-11-16")
    assert total_hoje == pytest.approx(85.5, 0.001)

    # 4. Resumo por máquina
    resumo_maq = repo.resumo_producao_por_maquina()
    assert len(resumo_maq) == 2
    assert resumo_maq[0]["maquina"] == "DOCAN R5200"
    assert resumo_maq[0]["total_m2"] == pytest.approx(70.0, 0.001)
    assert resumo_maq[0]["total_trabalhos"] == 2
    assert resumo_maq[1]["maquina"] == "SWJ-320EA"
    assert resumo_maq[1]["total_m2"] == pytest.approx(25.5, 0.001)
    assert resumo_maq[1]["total_trabalhos"] == 2


def test_repositorio_estoque_e_movimentacoes(db_path):
    """Testa cadastro de produto, cálculo de custo por m², movimentações e estorno."""
    inicializar_banco(db_path)
    repo = RepositorioEstoque(caminho=db_path)

    # Cadastro de Rolo: Lona 3.20x50m, custo R$ 1250,00 -> área 160 m² -> custo R$ 7,8125 / m²
    repo.cadastrar_produto(
        codigo="LONA_FOSCA_440_320",
        descricao="Lona Fosca Front 440g 3,20x50m",
        tipo="rolo",
        unidade="rolo",
        categoria_vinculada="LONA",
        comprimento_rolo_m=50,
        largura_m=3.20,
        custo_unitario=1250.00,
        minimo=5,
    )

    p = repo.obter_produto("LONA_FOSCA_440_320")
    assert p is not None
    assert p["saldo"] == 0.0
    assert repo.obter_custo_m2("LONA_FOSCA_440_320") == pytest.approx(7.8125, 0.001)

    # Movimentação 1: Entrada de 10 rolos
    repo.registrar_movimentacao(
        codigo="LONA_FOSCA_440_320",
        tipo="entrada",
        quantidade=10.0,
        observacao="Compra NF 1234",
    )
    assert repo.obter_saldo("LONA_FOSCA_440_320") == 10.0

    # Movimentação 2: Saída fracionada pela OS (-0.248 rolo = 12.4m)
    mov_saida_id = repo.registrar_movimentacao(
        codigo="LONA_FOSCA_440_320",
        tipo="saida",
        quantidade=-0.248,
        observacao="Saída OS-100",
        origem_pedido="OS-100",
    )
    assert repo.obter_saldo("LONA_FOSCA_440_320") == pytest.approx(9.752, 0.001)

    # Movimentação 3: Estorno da saída
    estorno_id = repo.desfazer_movimentacao(mov_saida_id, observacao="Cancelamento de OS")
    assert estorno_id is not None
    # Saldo deve voltar a 10.0 rolos
    assert repo.obter_saldo("LONA_FOSCA_440_320") == pytest.approx(10.0, 0.001)

    # Tentar estornar novamente deve levantar exceção
    with pytest.raises(ValueError, match="já foi estornada"):
        repo.desfazer_movimentacao(mov_saida_id)


def test_migracao_estoque_legado(tmp_path, db_path):
    """Testa importação automática do arquivo estoque.json legado para o SQLite."""
    arquivo_legado = tmp_path / "estoque_legado.json"
    dados_mock = {
        "produtos": {
            "LONA_320": {
                "descricao": "Lona Fosca Front 440g 3,20x50m",
                "tipo": "rolo",
                "unidade": "rolo",
                "comprimento_rolo_m": 50,
                "categoria_vinculada": "LONA",
                "variante_vinculada": None,
                "minimo": 6,
                "maximo": 60,
                "custo": 1250.0,
            },
            "PVC_10MM": {
                "descricao": "PVC 10mm Branco",
                "tipo": "chapa",
                "unidade": "chapa",
                "categoria_vinculada": "PVC",
                "variante_vinculada": {"espessura": "10MM", "cor": "BRANCO"},
                "minimo": 5,
                "maximo": 20,
                "custo": 280.0,
            },
        },
        "movimentos": [
            {
                "id": 1,
                "data": "10/11/2026 10:00:00",
                "produto": "LONA_320",
                "tipo": "entrada",
                "quantidade": 10,
                "observacao": "Carga inicial",
                "origem_pedido": None,
                "estorno_de": None,
            },
            {
                "id": 2,
                "data": "11/11/2026 15:30:00",
                "produto": "LONA_320",
                "tipo": "saida",
                "quantidade": -1.5,
                "observacao": "Consumo evento",
                "origem_pedido": "OS 456",
                "estorno_de": None,
            },
            {
                "id": 3,
                "data": "12/11/2026 09:00:00",
                "produto": "PVC_10MM",
                "tipo": "entrada",
                "quantidade": 15,
                "observacao": "Lote novo",
                "origem_pedido": None,
                "estorno_de": None,
            },
        ],
    }

    with open(arquivo_legado, "w", encoding="utf-8") as f:
        json.dump(dados_mock, f, ensure_ascii=False)

    resultado = migrar_estoque_legado(
        caminho_estoque_json=arquivo_legado,
        caminho_banco=db_path,
    )
    assert resultado["status"] == "sucesso"
    assert resultado["produtos_migrados"] == 2
    assert resultado["movimentos_migrados"] == 3

    # Valida dados importados no SQLite
    repo = RepositorioEstoque(caminho=db_path)
    prod_lona = repo.obter_produto("LONA_320")
    assert prod_lona is not None
    assert prod_lona["comprimento_rolo_m"] == 50.0
    assert prod_lona["largura_m"] == 3.20
    assert prod_lona["custo_m2"] == pytest.approx(7.8125, 0.001)
    # Saldo LONA: 10 - 1.5 = 8.5
    assert repo.obter_saldo("LONA_320") == pytest.approx(8.5, 0.001)

    # Saldo PVC: 15
    assert repo.obter_saldo("PVC_10MM") == pytest.approx(15.0, 0.001)

    # Idempotência: rodar novamente não duplica movimentações
    resultado_segunda = migrar_estoque_legado(
        caminho_estoque_json=arquivo_legado,
        caminho_banco=db_path,
    )
    assert resultado_segunda["status"] == "sucesso"
    assert resultado_segunda["produtos_migrados"] == 0
    assert resultado_segunda["movimentos_migrados"] == 0
    assert repo.obter_saldo("LONA_320") == pytest.approx(8.5, 0.001)


def test_concorrencia_wal_multiplas_conexoes(db_path):
    """
    Testa persistência concorrente real:
    Múltiplas threads lendo e escrevendo simultaneamente em conexões distintas
    sob PRAGMA journal_mode = WAL e busy_timeout = 5000.
    """
    inicializar_banco(db_path)

    erros = []
    num_threads = 6
    operacoes_por_thread = 25

    def trabalhador_escrita_pedidos(t_id):
        try:
            repo = RepositorioPedidos(caminho=db_path)
            for i in range(operacoes_por_thread):
                pid = repo.criar_pedido(
                    cliente=f"CLIENTE_CONCORRENTE_{t_id}",
                    numero=f"PED-{t_id}-{i}-{datetime.now().timestamp()}",
                )
                repo.adicionar_item(
                    pedido_id=pid,
                    arquivo=f"arte_{t_id}_{i}.pdf",
                    material="LONA",
                    largura_mm=1000,
                    altura_mm=1000,
                    quantidade=1,
                )
        except Exception as e:
            erros.append(f"Erro escrita pedidos thread {t_id}: {e}")

    def trabalhador_escrita_historico(t_id):
        try:
            repo = RepositorioHistorico(caminho=db_path)
            for i in range(operacoes_por_thread):
                repo.registrar_producao(
                    maquina=f"MAQUINA_{t_id}",
                    arquivo=f"trabalho_{t_id}_{i}.pdf",
                    m2=1.5,
                )
        except Exception as e:
            erros.append(f"Erro escrita historico thread {t_id}: {e}")

    def trabalhador_leitura(t_id):
        try:
            repo_p = RepositorioPedidos(caminho=db_path)
            repo_h = RepositorioHistorico(caminho=db_path)
            for _ in range(operacoes_por_thread):
                repo_p.listar_pedidos(limite=10)
                repo_h.calcular_m2_produzido()
        except Exception as e:
            erros.append(f"Erro leitura thread {t_id}: {e}")

    threads = []
    # Cria threads mistas de escrita e leitura
    for t_id in range(2):
        threads.append(threading.Thread(target=trabalhador_escrita_pedidos, args=(t_id,)))
    for t_id in range(2, 4):
        threads.append(threading.Thread(target=trabalhador_escrita_historico, args=(t_id,)))
    for t_id in range(4, 6):
        threads.append(threading.Thread(target=trabalhador_leitura, args=(t_id,)))

    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not erros, f"Ocorreram erros durante execução concorrente WAL: {erros}"

    # Validação de consistência
    with abrir_conexao(db_path) as conn:
        total_pedidos = conn.execute("SELECT COUNT(*) FROM pedidos").fetchone()[0]
        total_itens = conn.execute("SELECT COUNT(*) FROM itens_pedido").fetchone()[0]
        total_historico = conn.execute("SELECT COUNT(*) FROM historico_producao").fetchone()[0]

        # 2 threads de pedidos x 25 = 50 pedidos e 50 itens
        assert total_pedidos == 50
        assert total_itens == 50
        # 2 threads de histórico x 25 = 50 registros
        assert total_historico == 50


def test_facade_banco_raiz(db_path):
    """Testa a interface facade rápida banco.py na raiz do projeto."""
    inicializar_banco(db_path)

    # 1. Cria pedido via facade
    pid = banco.criar_pedido(
        cliente="CLIENTE FACADE",
        numero="OS-FACADE-01",
        caminho=db_path,
    )
    assert pid > 0

    ped = banco.obter_pedido(pedido_id=pid, caminho=db_path)
    assert ped["cliente"] == "CLIENTE FACADE"

    # 2. Registra produção via facade
    hid = banco.registrar_producao(
        maquina="ROUTER CNC",
        arquivo="corte_acrilico.dxf",
        m2=3.2,
        caminho=db_path,
    )
    assert hid > 0
    assert banco.calcular_m2_produzido(maquina="ROUTER CNC", caminho=db_path) == 3.2
