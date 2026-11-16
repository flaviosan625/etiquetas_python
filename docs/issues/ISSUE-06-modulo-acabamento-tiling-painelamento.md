# ISSUE-06: Módulo de Acabamento — Painelamento Automático de Grandes Formatos (`tiling.py`)

**Ordem de Execução:** 6º  
**Status:** Pronta para Início  
**Dependência:** ISSUE-04  
**Módulos a Criar:** `tiling.py`, `tests/test_tiling.py`.  
**Integração:** `montagem.py`, `gui.py`.

---

## 1. Descrição do Recurso

O painelamento (*Tiling*) é o processo de fatiar automaticamente uma arte gráfica de dimensões superiores à largura máxima da bobina ou mesa da impressora em múltiplas faixas que serão posteriormente unidas por solda vulcanizada, fita dupla-face estrutural ou sobreposição de adesivo.

Exemplo real: Um painel de $10{,}00 \times 3{,}50\text{ m}$ precisa ser impresso em uma máquina de $3{,}20\text{ m}$. O sistema deve fatiar o arquivo em 4 faixas verticais de $2{,}50 \times 3{,}50\text{ m}$ ou 2 faixas horizontais.

---

## 2. Requisitos Técnicos

### 2.1. Parâmetros de Entrada
- `largura_maxima_faixa_m`: Largura útil da máquina (ex: 3,20 m).
- `sobreposicao_solda_mm`: Margem extra de transpasse em cada emenda (padrão 25 mm).
- `orientacao_fatiamento`: Vertical (padrão) ou Horizontal.
- `bainha_extra_mm`: Margem para dobra/solda perimetral nos limites externos (ex: 50 mm).

### 2.2. Geração Geométrica via Form XObject
- Não rasterizar nem cortar fisicamente as imagens:
  - Cada faixa gerada é uma página PDF com `/MediaBox` igual ao tamanho da faixa mais a sobreposição.
  - A arte original inteira é inserida como um `/Subtype /Form`, com a matriz afim deslocada em $X$ ou $Y$ negativo para exibir apenas a janela daquela faixa correspondente.
  - O recorte da janela é feito por operador de clipping `/W n`.

### 2.3. Marcas de Acabamento no Fatiamento
1. **Cruzetas de Alinhamento de Solda:** Marcas impressas exatamente no eixo da sobreposição para que o operador da solda posicione uma faixa sobre a outra com precisão milimétrica.
2. **Identificação da Faixa:** Anotação automática no rodapé:  
   `CLIENTE X - FACHADA - FAIXA 02 DE 04 (OVERLAP 25MM) - [>>> SENTIDO DE MONTAGEM]`

---

## 3. Critérios de Aceite

1. Uma arte de $10\text{ m}$ dividida em 4 faixas deve recompor os $10\text{ m}$ perfeitamente ao sobrepor as marcas de solda de $25\text{ mm}$.
2. Cada faixa gerada deve ser encaminhada diretamente para a fila de montagem e identificada como peça vinculada ao mesmo pedido.
