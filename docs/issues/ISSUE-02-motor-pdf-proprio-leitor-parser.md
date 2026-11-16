# ISSUE-02: Motor Próprio de Leitura de PDF (Parser Sintático ISO 32000)

**Ordem de Execução:** 2º  
**Status:** Pronta para Início  
**Dependência:** ISSUE-01  
**Módulos a Criar:** `motor_pdf/leitor.py`, `motor_pdf/sintaxe.py`, `motor_pdf/descompressao.py`.  
**Módulos a Desacoplar:** `preflight.py`, `dimensoes.py`.  
**Referência de Base:** `c:\Users\flavi\Desktop\CNC CAM C++\src\io\pdf_vector.cpp`.

---

## 1. Objetivo

Construir o componente de leitura e análise sintática de arquivos PDF seguindo a especificação **ISO 32000-1**, sem utilizar PyMuPDF, Poppler ou qualquer biblioteca AGPL/GPL.

O leitor deve ser capaz de:
1. Abrir qualquer arquivo PDF válido (versões 1.3 a 1.7 e PDF 2.0).
2. Localizar e carregar a tabela ou stream de referências cruzadas (`xref`).
3. Analisar objetos indiretos, dicionários, arrays e streams de conteúdo.
4. Descomprimir streams em formato **Flate/Deflate** nativamente (utilizando o módulo padrão `zlib`).
5. Extrair as caixas de página: `MediaBox`, `CropBox`, `TrimBox`, `BleedBox` e a rotação da página (`/Rotate`).
6. Identificar imagens embutidas (`/XObject /Subtype /Image`) com suas dimensões em pixels (`/Width`, `/Height`), espaço de cor e cálculo do DPI efetivo.

---

## 2. Detalhes de Implementação

### 2.1. Estrutura de Classes em `motor_pdf/`
* `Token`: Enumeração e estrutura de dados para literais, nomes, números, delimitadores (`<<`, `>>`, `[`, `]`).
* `PdfTokenizer`: Scanner léxico que varre os bytes do arquivo ignorando espaços em branco e comentários PDF (`%`).
* `PdfReader`:
  - `ler_trailer()`: Busca reversa de `startxref` nos últimos 1024 bytes do arquivo.
  - `carregar_xref()`: Processamento da tabela de offsets ou de `/Type /XRef` (PDF 1.5+).
  - `obter_objeto(num_obj, geracao)`: Recuperação preguiçosa (*lazy loading*) de objetos indiretos por offset.
  - `obter_paginas()`: Navegação recursiva na árvore de páginas (`/Type /Pages`).

### 2.2. Algoritmo de Descompressão Flate
O módulo `motor_pdf/descompressao.py` deve processar os streams de conteúdo e streams de imagem:
- Utilizar `zlib.decompress()` com tratamento robusto para streams com ou sem cabeçalho zlib e suporte aos parâmetros de predição PNG/TIFF (`/Predictor`, `/Columns`).
- Se houver interesse em performance máxima, pode-se compilar a rotina Huffman/BitReader de `pdf_vector.cpp` do CNC CAM como uma extensão C/PyBind11 opcional, mantendo o fallback Python puro em `zlib` para portabilidade total.

### 2.3. Cálculo do DPI Efetivo (Preflight)
Para cada imagem `/Subtype /Image` associada a uma página:
$$\text{DPI}_x = \frac{\text{Width}_{\text{pixels}}}{\text{LarguraExibida}_{\text{pontos}} / 72.0} \times \frac{1}{\text{FatorEscala}}$$
O leitor deve reportar o menor DPI encontrado para permitir que o alerta de acuidade visual do sistema continue operando.

---

## 3. Testes e Validação

- [ ] Teste unitário comparativo: ler 50 PDFs reais da pasta de produção e conferir se `largura_pt`, `altura_pt` e `rotacao` batem exatamente com as medições históricas.
- [ ] Teste de resiliência: arquivos com trailer corrompido ou tabelas de xref incrementais não devem lançar exceções não tratadas.
- [ ] Teste de isolamento: executar o módulo em um ambiente virtual onde o `PyMuPDF` foi desinstalado (`pip uninstall pymupdf`).
