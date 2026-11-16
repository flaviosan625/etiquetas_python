# ISSUE-02: Construção do Motor Próprio de Manipulação, Imposição e Geração de PDF (Modelo CNC CAM)

**Status:** Aberta  
**Prioridade:** Crítica (Bloqueante Técnico)  
**Módulos Afetados:** `montagem.py`, `processamento.py`, `preflight.py`, `miniaturas.py`, `dimensoes.py`, `relatorios.py`, `retirada_material.py`.

---

## 1. Justificativa Técnica e Arquitetural

No `CNC CAM C++`, a equipe desenvolveu o `src/io/pdf_vector.cpp` (~2.000 linhas de código C++ puro), criando um leitor e interpretador completo de PDF que descompacta streams Flate/LZW/ASCII85, analisa tabelas XRef e extrai vetores diretamente para o pipeline geométrico, sem tocar em bibliotecas AGPL.

Para o sistema de produção gráfica, precisamos de um motor com **capacidade bidirecional**:
1. **Leitura e Inspeção (Parser):** Ler caixas de página (`MediaBox`, `TrimBox`, `BleedBox`), analisar imagens embutidas (DPI e espaço de cor) e calcular a **caixa de tinta real** a partir dos traçados vetoriais.
2. **Imposição e Escrita (Assembler):** Gerar arquivos PDF montados em rolo (bobinas de 1,27 m a 5,00 m) e chapas (mesas de 2,50 m), inserindo páginas de entrada como referências diretas de **Form XObjects** (`/Subtype /Form`), sem recompactação nem decodificação de pixels.

---

## 2. Especificação do Motor Próprio (`motor_pdf`)

O motor deve ser desenhado para operar como um módulo nativo de altíssima velocidade e zero custo de licença.

### 2.1. Submódulo de Leitura e Parsing (Sintaxe ISO 32000-1)
- **Localizador de XRef:** Varredura a partir do final do arquivo para encontrar `startxref`, tratando tanto tabelas tradicionais de `xref` quanto streams compactados de objetos cruzados (`/XRef`).
- **Parser de Objetos Indiretos:** Leitura de tipos primitivos:
  - Booleanos (`true`, `false`)
  - Numéricos (inteiros e ponto flutuante)
  - Strings literais `(...)` e hexadecimais `<...>`
  - Nomes `/<Nome>`
  - Dicionários `<< ... >>` e Arrays `[ ... ]`
  - Streams `stream ... endstream`
- **Descompressão de Streams:** Implementar descompressão de streams em formato **Flate/Deflate** (usando o módulo padrão `zlib` ou rotina nativa Huffman idêntica à do `pdf_vector.cpp`), ASCIIHex e ASCII85.

### 2.2. Medição da Caixa de Tinta Real (`caixa_da_arte` sem PyMuPDF)
Um dos maiores acertos do sistema atual é a medição da **área impressa real** para evitar franjas brancas de exportação de 1 pt do Illustrator.
* **Operadores a processar no stream de conteúdo:**
  - Matriz de transformação corrente (CTM): `cm`
  - Pilha gráfica: `q` (push) e `Q` (pop)
  - Caminhos vetoriais: `m` (moveto), `l` (lineto), `c`/`v`/`y` (curveto de Bézier), `re` (retângulo), `h` (closepath)
  - Clipping: `W` e `W*` (máscaras de recorte que delimitam a tinta)
  - Objetos externos: `Do` (desenho de Form XObject ou Imagem XObject)
* **Algoritmo:** Acompanhar a CTM ativa, multiplicar cada vértice pela matriz acumulada e calcular o `BoundingBox` real $(X_{\min}, Y_{\min}, X_{\max}, Y_{\max})$ da tinta sem precisar rasterizar a página em bitmap (o que derrubaria a memória em lonas de 30 metros).

### 2.3. Imposição por "Form XObject" (Preservação Cega de Bytes)
A montagem em rolo ou chapa **nunca deve abrir as imagens para reamostragem**.
* **Mecanismo:**
  1. Cria-se o cabeçalho do novo PDF `%PDF-1.6`.
  2. Cada PDF de entrada tem suas páginas convertidas em um dicionário `/Type /XObject /Subtype /Form`:
     - O `/BBox` do Form é a caixa de corte da arte (`caixa_da_arte` ou `TrimBox`).
     - Os recursos (`/Resources`) da página original são referenciados diretamente.
     - O stream de conteúdo original é copiado byte a byte para o novo arquivo.
  3. Na página mestre da montagem (ex: 5,00 m de largura pelo comprimento necessário), o stream de conteúdo apenas chama a matriz de transformação:
     ```postscript
     q
     <escala_x> 0 0 <escala_y> <pos_x_pt> <pos_y_pt> cm
     /Fm1 Do
     Q
     ```
  4. **Vantagens:** 
     - Montagem de 50 artes leva menos de 500 ms.
     - 100% dos bytes de cor, perfis ICC e canais especiais (como Branco/Verniz) continuam intactos.
     - Resolução original inalterada.

### 2.4. Motor de Preflight e Inspeção Técnica (Substituição de `preflight.py`)
- Inspecionar o dicionário `/Resources /XObject` das páginas:
  - Para cada `/Subtype /Image`: extrair `/Width`, `/Height`, `/ColorSpace` (identificando se é `/DeviceRGB`, `/DeviceCMYK` ou `/Separation`).
  - Calcular o **DPI efetivo**:
    $$\text{DPI} = \frac{\text{Width}_{\text{pixels}}}{\text{Largura}_{\text{pontos}} / 72.0} \times \frac{1}{\text{fator\_escala}}$$
  - Detecção de texto vivo vs curvas: inspecionar o dicionário `/Font`. Se contiver `/Subtype /TrueType` ou `/Type0` e o operador `Tj` aparecer nos streams, disparar aviso de "Texto não convertido em curvas".

### 2.5. Renderizador de Miniaturas (Thumbnails) 100% Permissivo
Para exibir prévias rápidas na interface gráfica e gerar os relatórios de OS e romaneios:
* **Alternativa A (Nativa C++):** Compilar o pipeline de visualização do `CNC CAM C++` em um módulo C++ (`.pyd` via pybind11 ou C-ABI) que rasteriza diretamente para buffer de imagem.
* **Alternativa B (Biblioteca Permissiva C/C++):** Utilizar uma biblioteca sob licença **Apache 2.0 / BSD**, como o **Google PDFium** (o motor de PDF oficial do Google Chrome e Android, sem copyleft), encapsulado de forma isolada para gerar bitmaps rápidos de visualização.

---

## 3. Plano de Implementação

- [ ] **Fase 1:** Criar o pacote `motor_pdf/` com classes `PdfParser`, `PdfWriter` e `PdfObject` em Python puro ou C++ compilado.
- [ ] **Fase 2:** Implementar descompressão Flate/zlib e leitura das caixas de dimensão (`MediaBox`, `TrimBox`, `CropBox`).
- [ ] **Fase 3:** Implementar o interpretador do stream de vetores para cálculo da caixa de tinta real (`caixa_da_arte`).
- [ ] **Fase 4:** Construir o montador de Form XObjects e validar que uma folha montada preserva o hash SHA1 dos streams de imagem originais.
- [ ] **Fase 5:** Migrar `preflight.py`, `montagem.py` e `dimensoes.py` para usar exclusivamente o `motor_pdf`.
- [ ] **Fase 6:** Remover `PyMuPDF` do `requirements.txt` e validar todos os 500+ testes unitários da suíte.
