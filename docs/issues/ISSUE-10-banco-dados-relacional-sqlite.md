# ISSUE-10: Banco de Dados Relacional Embutido (SQLite WAL)

**Ordem de Execução:** 10º  
**Status:** Pronta para Início  
**Dependência:** Nenhuma  
**Módulos a Criar:** `banco/conexao.py`, `banco/esquema.sql`, `banco/repositorios.py`.  
**Módulos a Migrar:** `relatorio_producao.py`, `estoque.py`, `rasterlink_hotfolder.py`.

---

## 1. Motivação Arquitetural

O armazenamento atual baseado em arquivos `.jsonl` em pastas sincronizadas por OneDrive causou perda de registros no passado devido a conflitos de sincronização entre computadores.

Para um produto comercial, a persistência deve ser **transacional (ACID), embutida (sem instalação de servidores pesados) e à prova de corrupção**:
- Utilizaremos **SQLite** no modo **WAL** (*Write-Ahead Logging*).
- O SQLite suporta milhares de gravações por segundo e leituras concorrentes por múltiplas estações na rede local sem locks de arquivo exclusivos.

---

## 2. Esquema Relacional de Dados

```sql
CREATE TABLE IF NOT EXISTS pedidos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    numero_pedido TEXT UNIQUE,
    cliente TEXT NOT NULL,
    data_criacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status TEXT DEFAULT 'ABERTO'
);

CREATE TABLE IF NOT EXISTS itens_pedido (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pedido_id INTEGER REFERENCES pedidos(id),
    caminho_arquivo TEXT NOT NULL,
    material TEXT NOT NULL,
    largura_m REAL NOT NULL,
    altura_m REAL NOT NULL,
    quantidade INTEGER DEFAULT 1,
    escala_fator REAL DEFAULT 1.0,
    status TEXT DEFAULT 'FILA_MONTAGEM'
);

CREATE TABLE IF NOT EXISTS montagens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    maquina_nome TEXT NOT NULL,
    largura_folha_m REAL NOT NULL,
    comprimento_folha_m REAL NOT NULL,
    arquivo_pdf_gerado TEXT NOT NULL,
    data_montagem TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS historico_producao (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    maquina TEXT NOT NULL,
    arquivo_prt TEXT,
    m2_produzido REAL,
    data_conclusao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status_rip TEXT
);

CREATE TABLE IF NOT EXISTS estoque (
    material TEXT PRIMARY KEY,
    tipo TEXT CHECK (tipo IN ('rolo', 'chapa')),
    largura_cm REAL,
    comprimento_cm REAL,
    saldo_atual REAL DEFAULT 0,
    custo_m2 REAL DEFAULT 0
);
```

---

## 3. Critérios de Aceite

1. O banco deve ser inicializado e migrado automaticamente na primeira execução do software.
2. Desligamentos repentinos de energia ou travamentos do PC não podem corromper os dados (garantido por `PRAGMA synchronous = NORMAL` e `PRAGMA journal_mode = WAL`).
3. Uma camada de compatibilidade deve importar todos os registros históricos de arquivos `.jsonl` legados.
