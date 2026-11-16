# ISSUE-03: Desacoplamento da Entrada e Painel de Triagem Visual de Pedidos

**Status:** Aberta  
**Prioridade:** Alta  
**Módulos Afetados:** `dimensoes.py`, `gui.py`, `processamento.py`, `gui_receber.py`.

---

## 1. Contexto e Problema de Mercado

O sistema foi concebido sobre o princípio operacional: **"O nome do arquivo é o banco de dados"** (`30UN PS ADESIVADO 1,26X2,02M_....pdf`).

No ambiente interno da Uny CV, essa convenção funciona porque a equipe foi treinada para nomear os arquivos assim. Porém, **ao comercializar o software para outros birôs de comunicação visual**, esse requisito torna-se uma barreira imediata de vendas:
- Agências de publicidade e clientes finais enviam arquivos com nomes arbitrários (`painel_aprovado_final.pdf`, `logo_loja_2.pdf`).
- Birôs que utilizam ERPs de gestão (Holdprint, Everflow, etc.) identificam arquivos pelo número do Pedido/OS (`OS_10523_arte1.pdf`).
- Exigir que o operador renomeie centenas de arquivos manualmente anula o ganho de tempo da automação.

---

## 2. Requisitos da Solução

### 2.1. Parser de Nomenclatura Configurável (Expressões Regulares Paramétricas)
* **Objetivo:** Permitir que cada gráfica configure suas próprias regras de leitura de nome de arquivo através da interface, sem tocar em código Python.
* **Recursos:**
  - Perfil de Nomenclatura personalizável por empresa.
  - Campos mapeáveis: `{quantidade}`, `{material}`, `{largura}`, `{altura}`, `{unidade}`, `{cliente}`, `{pedido}`, `{descricao}`.
  - Predefinições comuns de mercado:
    - Padrão Uny CV: `{quantidade}UN {material} {largura}X{altura}M_{cliente}_{descricao}.pdf`
    - Padrão ERP: `{pedido}_{cliente}_{largura}x{altura}_{material}.pdf`
    - Padrão Livre: Apenas lê as dimensões numéricas encontradas no texto.

### 2.2. Grade de Triagem Visual em Lote (Para Arquivos sem Nome Padronizado)
* **Objetivo:** Uma tela rápida de conferência onde arquivos que não possuem dados completos no nome possam ser classificados em segundos.
* **Fluxo de Trabalho:**
  1. O operador arrasta uma pasta ou lote de arquivos para a janela.
  2. O sistema abre uma tabela interativa com miniaturas dos arquivos.
  3. **Medição Automática:** O motor lê o `TrimBox`/`MediaBox` de cada PDF e preenche as medidas sugeridas.
  4. **Detecção Inteligente de Escala:** Se a arte mede `0,30 × 0,10 m` e o operador digita `3,00 × 1,00 m`, o sistema sugere automaticamente o fator de ampliação ×10 (escala 1:10).
  5. **Navegação por Teclado:** Campos editáveis em linha (`Material`, `Quantidade`, `Largura`, `Altura`, `Acabamento`) navegáveis por `Tab` e `Enter`.
  6. **Ação "Aprovar Lote":** Um clique converte todos os arquivos da triagem em ordens prontas para a fila de montagem.

### 2.3. Importador de Ordens via Planilha (Excel / CSV)
* **Objetivo:** Conectar planilhas de corte/impressão exportadas de ERPs diretamente aos arquivos de arte.
* **Funcionamento:**
  - O usuário carrega `pedidos.xlsx` ou `pedidos.csv`.
  - O sistema correlaciona a coluna "Nome do Arquivo" ou "Código da Peça" com os arquivos PDF na pasta de entrada.
  - As quantidades, medidas e materiais declarados na planilha assumem o controle da produção automaticamente.

---

## 3. Critérios de Aceite

1. O sistema deve continuar aceitando o formato clássico da Uny CV com 100% de retrocompatibilidade.
2. Arquivos sem nenhuma medida no nome não devem ser rejeitados ou travar o processo; devem ser direcionados para a tela de triagem visual.
3. A triagem visual deve permitir que 20 artes sejam conferidas e enviadas para montagem em menos de 1 minuto.
4. O operador deve poder salvar predefinições de materiais mais usados para seleção em 1 clique.
