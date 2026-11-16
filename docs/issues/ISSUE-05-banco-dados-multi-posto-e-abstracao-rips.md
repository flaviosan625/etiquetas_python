# ISSUE-05: Banco de Dados Relacional, Arquitetura Multi-Posto e Abstração de RIPs

**Status:** Aberta  
**Prioridade:** Média / Alta  
**Módulos Afetados:** `rasterlink_hotfolder.py`, `sai_setups.py`, `separar_ripados.py`, `relatorio_producao.py`, `estoque.py`, `config.py`.

---

## 1. Contexto e Lições do Sistema Atual

A documentação arquitetural (`CLAUDE.md`) registra episódios em que a persistência baseada em arquivos planos (`.jsonl`), arquivos de trava locais (`.lock`) e sincronização via nuvem (OneDrive) causou incidentes graves:
- **Conflito de Sincronização:** Em setembro/2026, dois postos gravando no mesmo `.jsonl` no OneDrive fizeram a nuvem resolver conflitos criando arquivos duplicados, resultando na perda de 108 registros de entrega de impressão.
- **Limites de Travas:** A trava de instância única em arquivo local não enxerga postos em máquinas vizinhas na rede.
- **Caminhos Fixos de Disco:** Caminhos rígidos como `D:\RIPADOS` ou `C:\VigiaDocan` quebram quando o cliente instala o software em um computador que possui apenas a partição `C:`.

---

## 2. Requisitos da Nova Arquitetura

### 2.1. Migração para Banco de Dados Relacional Embutido (SQLite WAL)
Substituir os arquivos `.jsonl` e arquivos temporários por um banco de dados relacional transacional (ACID):
* **Tecnologia:** **SQLite** no modo `WAL` (*Write-Ahead Logging*).
  - Zero configuração para o cliente (nenhum servidor complexo para instalar).
  - Suporta leitura e escrita concorrente com extrema segurança e velocidade.
  - Opção de conexão com **PostgreSQL** para birôs de grande porte com dezenas de estações.
* **Tabelas Principais:**
  - `pedidos` (id, cliente, data_criacao, status, orcamento_id, notas)
  - `itens_pedido` (id, pedido_id, arquivo_origem, material, largura_m, altura_m, quantidade, status)
  - `montagens` (id, maquina_id, folha_largura_m, folha_comprimento_m, pdf_gerado, status, data_montagem)
  - `pecas_montadas` (id, montagem_id, item_id, x_pos, y_pos, rotacao, fator_escala)
  - `historico_maquinas` (id, maquina_id, arquivo_impresso, m2_calculado, data_envio, rip_status)
  - `estoque_materiais` (id, nome, tipo [rolo/chapa], largura_m, comprimento_m, custo_m2, saldo)

### 2.2. Camada de Abstração de Hardware e RIPs (*Driver Engine*)
Eliminar o acoplamento rígido com a Mimaki e a DOCAN. Transformar a integração com RIPs em um sistema de "Drivers" configuráveis via interface:
* **Tipos de Drivers Suportados:**
  1. **Hot Folder Universal (Drop & Poll):** Compatível com qualquer RIP do mercado (Onyx, Caldera, Wasatch, Roland VersaWorks, EFI Fiery).
  2. **Mimaki RasterLink Driver:** Gestão das pastas de entrada e leitura do status.
  3. **SAi Production Manager Driver:** Gestão de portas `FILE:`, separação inteligente de arquivos `.prt`/`.prn` e leitura de `RIPLOG.HTML`.
* **Gerenciador de Máquinas (Zero Código):**
  - Cada máquina cadastrada possui: Nome amigável, Tipo (`Rolo` ou `Mesa Plana`), Largura útil, Comprimento máximo, Pasta de Hot Folder de entrada, e regras de rotação automática.

### 2.3. Desacoplamento da Nuvem e Comunicação em Rede Local
* O sistema não deve depender do cliente OneDrive para funcionar.
* Suporte nativo a caminhos de rede padrão Windows (UNC: `\\SERVIDOR\HotFolders\Entrada`).
* Substituição dos arquivos de "sinal de vida" por *heartbeats* transacionais registrados diretamente no banco de dados SQLite/PostgreSQL com verificação de timestamp Unix.

---

## 3. Critérios de Aceite

1. O sistema deve operar de forma 100% confiável mesmo se instalado em um computador sem partição `D:` ou sem OneDrive ativo.
2. Vários computadores na mesma rede devem poder acessar o banco de dados compartilhado sem travamento ou perda de registros.
3. Cadastrar uma nova impressora no sistema deve ser feito em uma tela intuitiva em menos de 2 minutos.
