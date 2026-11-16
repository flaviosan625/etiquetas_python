# ISSUE-05: Renderizador de Miniaturas e Gerador de Relatórios (`motor_pdf/miniaturas.py`)

**Ordem de Execução:** 5º  
**Status:** Pronta para Início  
**Dependência:** ISSUE-04  
**Módulos a Criar:** `motor_pdf/miniaturas.py`, `motor_pdf/relatorios_pdf.py`.  
**Módulos a Refatorar:** `miniaturas.py`, `relatorios.py`, `retirada_material.py`, `branding.py`.

---

## 1. Contexto

Além da montagem de produção em bobina, o sistema gera diariamente três documentos cruciais em formato A4:
1. **Ordem de Serviço (OS):** Lista de peças com miniaturas, medidas, materiais e centros de custo de tinta por cor (CMYK).
2. **Romaneio de Retirada de Material:** Documento logístico com miniaturas, campos de transportadora, placa de veículo e assinaturas de conferência.
3. **Checklist e Etiquetas A4:** Folhas com etiquetas adesivas para identificação física de cada pacote.

Atualmente, a geração das miniaturas gráficas e a montagem das páginas A4 dependem do PyMuPDF (`get_pixmap()` e `insert_textbox()`).

---

## 2. Solução Técnica Livre de Licenças Restritivas

### 2.1. Renderização Rápida de Miniaturas (*Thumbnails*)
Para gerar miniaturas com zero contaminação jurídica:
* **Estratégia Principal (Extração Direta de Raster):** Para PDFs que contêm imagens bitmap embutidas, extrair diretamente o stream DCT/JPEG ou Flate para um objeto `Pillow.Image` (Licença HPND permissiva), redimensionando para $200 \times 200\text{ px}$.
* **Estratégia Vetorial (PDFium Isolado sob Apache 2.0):** Para páginas complexas compostas puramente por vetores, utilizar o motor **Google PDFium** (código aberto sob licença Apache 2.0 / BSD 3-Clause, padrão do Chromium), compilado como DLL utilitária isolada.

### 2.2. Gerador Nativo de Documentos A4 (`relatorios_pdf.py`)
Utilizar a capacidade do `motor_pdf/escritor.py` desenvolvido na ISSUE-04 para compor páginas A4 com:
- Tabelas com linhas zebradas.
- Inserção de logotipos (`branding.py`) como objetos `/Image`.
- Quebra automática de páginas com paginação no rodapé ("Página X de Y").
- Suporte a formulários de expedição com campos de preenchimento manual (motorista, veículo, conferência).

---

## 3. Critérios de Aceite

1. Os PDFs de OS e Retirada de Material devem ser gerados sem nenhuma chamada ao `fitz` ou `pymupdf`.
2. As miniaturas devem carregar de forma nítida e com proporção preservada no relatório A4.
3. A suíte de testes `test_retirada_material.py` deve passar integralmente sem erros.
