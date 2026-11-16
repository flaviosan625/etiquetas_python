# ISSUE-08: Desacoplamento da Entrada e Parser de Nomes Paramétrico (`dimensoes.py`)

**Ordem de Execução:** 8º  
**Status:** Pronta para Início  
**Dependência:** Nenhuma (independente do motor de PDF)  
**Módulos a Refatorar:** `dimensoes.py`, `config.py`.  
**Módulos a Criar:** `parser_regras.py`, `tests/test_parser_regras.py`.

---

## 1. Contexto

Hoje o arquivo `dimensoes.py` possui expressões regulares fixas adaptadas ao padrão interno da Uny CV (`"30UN PS ADESIVADO 1,26X2,02M_....pdf"`).

Para comercializar o software, precisamos que **cada gráfica possa definir como seus arquivos são nomeados**, ou escolher entre diferentes perfis de clientes/agências.

---

## 2. Requisitos Técnicos

### 2.1. Construtor de Perfis de Nomenclatura (`parser_regras.py`)
Permitir que regras de regex sejam definidas via arquivo JSON de configuração ou interface:
* **Tokens Mapeáveis:**
  - `{QTD}`: Quantidade de cópias (`(\d+)\s*(?:UN|un|PÇS)?`)
  - `{MATERIAL}`: Nome ou sigla do substrato (`([A-Za-z0-9_ -]+)`)
  - `{LARG}` e `{ALT}`: Medidas numéricas (`(\d+(?:[.,]\d+)?)\s*(?:[xX*])\s*(\d+(?:[.,]\d+)?)`)
  - `{UNIDADE}`: `M`, `CM`, `MM`
  - `{CLIENTE}`: Nome do cliente ou ID da OS
  - `{DESCRICAO}`: Nome da peça ou detalhe

### 2.2. Perfis Padrão Fornecidos de Fábrica
1. **Padrão Comunicação Visual Clássico:** `{QTD}UN {MATERIAL} {LARG}X{ALT}{UNIDADE}_{CLIENTE}_{DESCRICAO}`
2. **Padrão Ordem de Serviço ERP:** `OS{PEDIDO}_{CLIENTE}_{MATERIAL}_{LARG}x{ALT}`
3. **Padrão Apenas Dimensões:** Procura qualquer ocorrência de `LxA` no nome e assume quantidade 1.

### 2.3. Validação e Fallback Automático
- Se um arquivo não casar com o perfil principal, o parser tenta os perfis secundários.
- Se nenhum perfil casar, o arquivo não é rejeitado: ele é marcado como `status: "PENDENTE_TRIAGEM"` e direcionado para a grade visual da ISSUE-09.

---

## 3. Critérios de Aceite

1. O parser deve continuar compreendendo 100% dos nomes antigos da suíte de testes de `test_dimensoes.py`.
2. Adicionar uma nova regra customizada deve exigir apenas alterar uma linha do arquivo de configuração JSON sem modificar o código-fonte Python.
