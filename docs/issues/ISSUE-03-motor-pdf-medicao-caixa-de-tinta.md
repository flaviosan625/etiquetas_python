# ISSUE-03: Medição de Caixa de Tinta Vetorial sem Rasterização (`caixa_da_arte` Própria)

**Ordem de Execução:** 3º  
**Status:** Pronta para Início  
**Dependência:** ISSUE-02  
**Módulos a Criar:** `motor_pdf/geometria.py`, `motor_pdf/interpretador_stream.py`.  
**Módulos a Refatorar:** `dimensoes.py`, `montagem.py`.  
**Referência de Base:** Traçados vetoriais de `c:\Users\flavi\Desktop\CNC CAM C++\src\io\pdf_vector.cpp`.

---

## 1. O Problema Prático no Chão de Fábrica

Em outubro/2026, foi descoberto no chão de fábrica que artes exportadas pelo Adobe Illustrator frequentemente apresentam:
1. Uma franja branca de **1 pt** ($0{,}35\text{ mm}$, que vira $7{,}1\text{ mm}$ ao ampliar $\times 10$ uma arte em escala $1:10$).
2. Um traçado de corte com desalinhamento de $0{,}6\text{ pt}$ que encolhe a largura da peça.

Se medirmos apenas o `MediaBox` da página, a peça montada na bobina sai com falta de largura. Por outro lado, **rasterizar uma lona de 29 metros em alta resolução para achar a borda é inviável e trava o computador por falta de memória RAM**.

A solução estabelecida no sistema é a **medição da área de tinta via interpretação vetorial do stream de conteúdo**. Esta issue recria essa capacidade no motor próprio, sem PyMuPDF.

---

## 2. Implementação do Interpretador Vetorial

O módulo `motor_pdf/interpretador_stream.py` deve processar a sequência de operadores gráficos do stream descompactado da página:

### 2.1. Manutenção do Estado Gráfico
* **Matriz de Transformação Corrente (CTM):** Uma matriz afim $3 \times 3$:
  $$\begin{bmatrix} a & b & 0 \\ c & d & 0 \\ e & f & 1 \end{bmatrix}$$
  Atualizada pelo operador `<a b c d e f cm>`.
* **Pilha de Estados Gráficos:**
  - `q`: Salva a CTM e o caminho de recorte atual na pilha.
  - `Q`: Restaura o estado anterior do topo da pilha.

### 2.2. Avaliação de Traçados e Vértices
* Para cada ponto $(x, y)$ lido no stream:
  $$\begin{bmatrix} x' & y' & 1 \end{bmatrix} = \begin{bmatrix} x & y & 1 \end{bmatrix} \times \text{CTM}$$
* Operadores:
  - `m` (moveto): Inicia novo subcaminho em $(x', y')$.
  - `l` (lineto): Adiciona segmento de reta até $(x', y')$.
  - `c`, `v`, `y` (curveto): Curvas de Bézier cúbicas. Os pontos de controle e extremidades são transformados pela CTM para delimitar o retângulo envolvente (*bounding box*).
  - `re` (retângulo): Equivale a `m x y`, `l x+w y`, `l x+w y+h`, `l x y+h`, `h`.
  - `W` / `W*` (clipping): Define a máscara de recorte ativa. Qualquer elemento desenhado fora da máscara de recorte tem suas coordenadas limitadas (*clamped*) à área visível.

### 2.3. Objetos Externos (`Do`)
* Se o operador `Do` invocar um `/XObject` do tipo `/Image`, o retângulo de dimensões $1 \times 1$ da imagem sob a CTM corrente é computado diretamente:
  $$(X_{\min}, Y_{\min}) = (e, f) \quad \text{e} \quad (X_{\max}, Y_{\max}) = (e + a, f + d)$$
* Se invocar um `/Form XObject`, o parser desce recursivamente no stream do Form com a matriz acumulada.

---

## 3. Critérios de Aceite

1. O cálculo de `caixa_da_arte()` deve processar lonas de 10 a 30 metros em menos de 10 milissegundos.
2. A tolerância da largura medida não pode exceder $0{,}05\text{ mm}$ em comparação com as peças de teste do repositório (`tests/test_montagem.py`).
3. O algoritmo deve ignorar traçados transparentes ou máscaras invisíveis que fiquem fora da área de design.
