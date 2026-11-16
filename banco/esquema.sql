-- Esquema relacional SQLite para Automação Gráfica
-- Otimizado para alta concorrência em modo WAL e integridade referencial

PRAGMA foreign_keys = ON;

-- 1. Pedidos (Ordens de Serviço / Lotes de produção)
CREATE TABLE IF NOT EXISTS pedidos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    numero TEXT UNIQUE NOT NULL,
    cliente TEXT NOT NULL,
    data_criacao TEXT NOT NULL,
    data_atualizacao TEXT,
    status TEXT NOT NULL DEFAULT 'pendente',
    observacoes TEXT,
    total_m2 REAL DEFAULT 0.0,
    total_itens INTEGER DEFAULT 0,
    metadados TEXT
);

-- 2. Montagens (Folhas de impressão para Bobina ou Chapa)
CREATE TABLE IF NOT EXISTS montagens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo TEXT UNIQUE NOT NULL,
    tipo TEXT NOT NULL DEFAULT 'bobina',
    maquina TEXT,
    material TEXT NOT NULL,
    largura_util_mm REAL NOT NULL,
    comprimento_util_mm REAL NOT NULL,
    aproveitamento_percentual REAL DEFAULT 0.0,
    area_total_m2 REAL DEFAULT 0.0,
    area_usada_m2 REAL DEFAULT 0.0,
    arquivo_saida TEXT,
    data_criacao TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'gerada',
    observacoes TEXT,
    metadados TEXT
);

-- 3. Itens do Pedido (Peças individuais / artes)
CREATE TABLE IF NOT EXISTS itens_pedido (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pedido_id INTEGER NOT NULL REFERENCES pedidos(id) ON DELETE CASCADE,
    arquivo TEXT NOT NULL,
    material TEXT NOT NULL,
    variante TEXT,
    largura_mm REAL NOT NULL,
    altura_mm REAL NOT NULL,
    quantidade INTEGER NOT NULL DEFAULT 1,
    m2_unitario REAL NOT NULL DEFAULT 0.0,
    m2_total REAL NOT NULL DEFAULT 0.0,
    status TEXT NOT NULL DEFAULT 'pendente',
    montagem_id INTEGER REFERENCES montagens(id) ON DELETE SET NULL,
    metadados TEXT
);

-- 4. Peças Alocadas na Montagem (Posicionamento e Layout)
CREATE TABLE IF NOT EXISTS itens_montagem (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    montagem_id INTEGER NOT NULL REFERENCES montagens(id) ON DELETE CASCADE,
    item_pedido_id INTEGER REFERENCES itens_pedido(id) ON DELETE SET NULL,
    nome_peca TEXT NOT NULL,
    largura_mm REAL NOT NULL,
    altura_mm REAL NOT NULL,
    pos_x_mm REAL DEFAULT 0.0,
    pos_y_mm REAL DEFAULT 0.0,
    girado INTEGER DEFAULT 0,
    m2 REAL DEFAULT 0.0,
    metadados TEXT
);

-- 5. Histórico Permanente de Produção (comprovação e telemetria de máquinas)
CREATE TABLE IF NOT EXISTS historico_producao (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    data_hora TEXT NOT NULL,
    data TEXT NOT NULL,
    maquina TEXT NOT NULL,
    arquivo TEXT NOT NULL,
    material TEXT,
    m2 REAL NOT NULL DEFAULT 0.0,
    tamanho_bytes INTEGER DEFAULT 0,
    girado INTEGER DEFAULT 0,
    pedido_id INTEGER REFERENCES pedidos(id) ON DELETE SET NULL,
    montagem_id INTEGER REFERENCES montagens(id) ON DELETE SET NULL,
    status TEXT NOT NULL DEFAULT 'concluido',
    detalhes TEXT
);

-- 6. Estoque de Materiais e Produtos (Rolos, Chapas e Insumos)
CREATE TABLE IF NOT EXISTS estoque (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo TEXT UNIQUE NOT NULL,
    descricao TEXT NOT NULL,
    tipo TEXT NOT NULL,
    unidade TEXT NOT NULL,
    categoria_vinculada TEXT,
    variante_vinculada TEXT,
    comprimento_rolo_m REAL DEFAULT 0.0,
    largura_m REAL DEFAULT 0.0,
    minimo REAL DEFAULT 0.0,
    maximo REAL DEFAULT 0.0,
    codigo_planilha TEXT,
    capacidade_ml REAL,
    custo_unitario REAL,
    custo_m2 REAL,
    saldo REAL NOT NULL DEFAULT 0.0,
    metadados TEXT
);

-- 7. Histórico de Movimentações de Estoque (Auditoria e rastreamento de saldo)
CREATE TABLE IF NOT EXISTS movimentacoes_estoque (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    produto_codigo TEXT NOT NULL REFERENCES estoque(codigo) ON DELETE CASCADE,
    tipo TEXT NOT NULL,
    quantidade REAL NOT NULL,
    data_hora TEXT NOT NULL,
    observacao TEXT,
    origem_pedido TEXT,
    estorno_de INTEGER REFERENCES movimentacoes_estoque(id) ON DELETE SET NULL,
    custo_momento REAL
);

-- 8. Cadastro de Máquinas e Equipamentos Gráficos (RIPs, Spoolers e Mesas)
CREATE TABLE IF NOT EXISTS maquinas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT UNIQUE NOT NULL,
    tipo TEXT NOT NULL DEFAULT 'rolo',
    largura_util_m REAL,
    mesa_largura_m REAL,
    mesa_altura_m REAL,
    hot_folder TEXT,
    pasta_entrada TEXT,
    rip_tipo TEXT NOT NULL DEFAULT 'generico',
    posto TEXT NOT NULL DEFAULT 'local',
    setup_sai TEXT,
    montagem INTEGER NOT NULL DEFAULT 1,
    largura_montagem_m REAL,
    margem_montagem_m REAL DEFAULT 0.0,
    girar INTEGER NOT NULL DEFAULT 1,
    entrega_byhx INTEGER NOT NULL DEFAULT 0,
    ativo INTEGER NOT NULL DEFAULT 1,
    metadados TEXT,
    data_atualizacao TEXT
);

-- ============================================================================
-- ÍNDICES DE PERFORMANCE (Busca por Cliente, Status, Data e Material)
-- ============================================================================

-- Índices em Pedidos
CREATE INDEX IF NOT EXISTS idx_pedidos_cliente ON pedidos (cliente);
CREATE INDEX IF NOT EXISTS idx_pedidos_status ON pedidos (status);
CREATE INDEX IF NOT EXISTS idx_pedidos_data ON pedidos (data_criacao);

-- Índices em Itens de Pedido
CREATE INDEX IF NOT EXISTS idx_itens_pedido_pedido_id ON itens_pedido (pedido_id);
CREATE INDEX IF NOT EXISTS idx_itens_pedido_material ON itens_pedido (material);
CREATE INDEX IF NOT EXISTS idx_itens_pedido_status ON itens_pedido (status);
CREATE INDEX IF NOT EXISTS idx_itens_pedido_montagem_id ON itens_pedido (montagem_id);

-- Índices em Montagens
CREATE INDEX IF NOT EXISTS idx_montagens_codigo ON montagens (codigo);
CREATE INDEX IF NOT EXISTS idx_montagens_material ON montagens (material);
CREATE INDEX IF NOT EXISTS idx_montagens_data ON montagens (data_criacao);
CREATE INDEX IF NOT EXISTS idx_montagens_status ON montagens (status);
CREATE INDEX IF NOT EXISTS idx_montagens_maquina ON montagens (maquina);

-- Índices em Itens de Montagem
CREATE INDEX IF NOT EXISTS idx_itens_montagem_montagem_id ON itens_montagem (montagem_id);
CREATE INDEX IF NOT EXISTS idx_itens_montagem_item_pedido ON itens_montagem (item_pedido_id);

-- Índices em Histórico de Produção
CREATE INDEX IF NOT EXISTS idx_historico_maquina ON historico_producao (maquina);
CREATE INDEX IF NOT EXISTS idx_historico_data ON historico_producao (data);
CREATE INDEX IF NOT EXISTS idx_historico_data_hora ON historico_producao (data_hora);
CREATE INDEX IF NOT EXISTS idx_historico_material ON historico_producao (material);
CREATE INDEX IF NOT EXISTS idx_historico_status ON historico_producao (status);

-- Índices em Estoque
CREATE INDEX IF NOT EXISTS idx_estoque_codigo ON estoque (codigo);
CREATE INDEX IF NOT EXISTS idx_estoque_tipo ON estoque (tipo);
CREATE INDEX IF NOT EXISTS idx_estoque_categoria ON estoque (categoria_vinculada);

-- Índices em Movimentações de Estoque
CREATE INDEX IF NOT EXISTS idx_mov_produto ON movimentacoes_estoque (produto_codigo);
CREATE INDEX IF NOT EXISTS idx_mov_data ON movimentacoes_estoque (data_hora);
CREATE INDEX IF NOT EXISTS idx_mov_tipo ON movimentacoes_estoque (tipo);

-- Índices em Máquinas
CREATE INDEX IF NOT EXISTS idx_maquinas_nome ON maquinas (nome);
CREATE INDEX IF NOT EXISTS idx_maquinas_rip ON maquinas (rip_tipo);

