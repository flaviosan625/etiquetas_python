# ISSUE-09: Grade de Triagem Visual em Lote para Arquivos Sem Padrão (`gui_triagem.py`)

**Ordem de Execução:** 9º  
**Status:** Pronta para Início  
**Dependência:** ISSUE-05, ISSUE-08  
**Módulos a Criar:** `gui_triagem.py`, `importador_planilha.py`.  
**Integração:** `main.py`, `gui.py`.

---

## 1. Contexto

Quando arquivos com nomes arbitrários (ex: `logo_nova_fachada.pdf`, `adesivo_carro_joao.pdf`) são colocados na entrada, o software não deve parar ou emitir erros obscuros.

O operador deve ter uma **tela ágil de conferência em grade** para revisar, preencher os dados faltantes e enviar o lote inteiro para a produção em segundos.

---

## 2. Requisitos Técnicos

### 2.1. Interface de Triagem Rápida
- **Tabela em Grade:**
  - Coluna 1: Miniatura da arte (gerada via `motor_pdf/miniaturas.py`).
  - Coluna 2: Nome original do arquivo.
  - Coluna 3: Medida física detectada no PDF (`largura_pt` $\times$ `altura_pt` convertidas para metros).
  - Coluna 4: Seletor de Escala (`1:1`, `1:10`, `1:20` ou `Personalizada`).
  - Coluna 5: Quantidade de cópias (campo numérico com foco rápido).
  - Coluna 6: Seletor de Material (Dropdown com histórico e autocompletar).
  - Coluna 7: Cliente / Pedido.
- **Detecção Inteligente de Escala:** Se o PDF mede $30 \times 10\text{ cm}$ mas o operador digita $3{,}00 \times 1{,}00\text{ m}$, o sistema sugere automaticamente a escala $1:10$.
- **Edição em Lote:** Selecionar múltiplas linhas com `Shift` ou `Ctrl` e alterar o material ou cliente de todas de uma só vez.

### 2.2. Importador de Planilha (Excel / CSV)
- Botão "Importar Planilha de Pedido" que lê arquivos `.xlsx` ou `.csv` contendo listas de itens.
- O sistema faz o cruzamento automático (*matching*) do nome do arquivo na pasta com a linha correspondente da planilha, preenchendo todas as colunas automaticamente.

---

## 3. Critérios de Aceite

1. O operador deve conseguir triar e despachar um lote de 20 arquivos avulsos em menos de 60 segundos.
2. Teclas de atalho `Tab` e `Enter` devem permitir navegação sequencial contínua sem necessidade de tirar a mão do teclado para usar o mouse.
