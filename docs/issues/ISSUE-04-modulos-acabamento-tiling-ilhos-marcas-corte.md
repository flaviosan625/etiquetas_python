# ISSUE-04: Módulos Essenciais de Acabamento para Grandes Formatos (Tiling, Ilhós, Sangria e Marcas Óticas)

**Status:** Aberta  
**Prioridade:** Alta  
**Módulos Afetados:** `acabamento.py`, `montagem.py`, `aproveitamento.py`, `corte_dxf.py`.

---

## 1. Contexto de Mercado

Softwares internacionais de pré-impressão (como Caldera PrimeCenter, Onyx Thrive e Esko i-cut) cobram licenças elevadas principalmente pela capacidade de preparar o arquivo para o **acabamento pós-impressão**.

No chão de fábrica da comunicação visual, a impressão é apenas a primeira etapa; o gargalo e os maiores prejuízos acontecem na solda de lonas gigantes, na furação de ilhoses na trena e no recorte de vinis e placas.

Esta issue formaliza a implementação de quatro ferramentas industriais de acabamento no motor do sistema.

---

## 2. Especificação dos Módulos de Acabamento

### 2.1. Painelamento Automático de Grandes Formatos (*Tiling / Fatiamento*)
Quando uma arte excede a largura útil da bobina (ex: painel de fachada de $12{,}00 \times 4{,}00\text{ m}$ em uma impressora de $3{,}20\text{ m}$):
* **Fatiamento Paramétrico:** O sistema divide a arte em faixas verticais ou horizontais ajustadas à largura máxima da máquina.
* **Sobreposição de Solda (*Overlap*):** Adição de margem de transpasse configurável (ex: $25\text{ mm}$ ou $30\text{ mm}$) em cada emenda, necessária para a solda vulcanizada de alta frequência ou sobreposição de adesivo de envelopamento.
* **Marcas Guia de Casamento (*Tick Marks*):** Pequenas cruzetas impressas na área da emenda para que o operador da máquina de solda alinhe perfeitamente a arte sem distorção.
* **Rótulos de Identificação de Painel:** Texto impresso na sobra de cabeçalho/rodapé de cada faixa:  
  `FAIXA 01/04 - SOBREPOSIÇÃO 25MM - CLIENTE X - PAINEL FACHADA`

### 2.2. Marcas de Ilhós Paramétricas (*Grommet Engine*)
Integrar a lógica já esboçada em `acabamento.py` ao motor próprio:
* **Mira de Precisão com Duplo Halo:**
  - Traçado externo branco com espessura de $1{,}8\text{ pt}$ (garante contraste em fundos escuros).
  - Traçado interno preto com diâmetro de $10\text{ mm}$ (anel de ilhós padrão).
  - Cruz central e furo-guia de $1\text{ mm}$ no centro para posicionamento exato da agulha da prensa pneumática.
* **Espaçamento e Recuo:**
  - Recuo configurável da borda (padrão de $2{,}5\text{ cm}$, caindo exatamente na dobra da bainha/solda).
  - Distribuição automática a cada $30\text{ cm}$, $40\text{ cm}$ ou $50\text{ cm}$, além dos quatro cantos obrigatórios.

### 2.3. Gerador de Sangria Automática (*Mirror Bleed*)
* Arquivos que chegam de clientes sem sangria ($0\text{ mm}$ de margem) causam filetes brancos no refile com estilete ou na mesa de corte.
* **Geração Inteligente:**
  - Opção de espelhamento (*mirror bleed*) de $5\text{ a }20\text{ mm}$ das bordas externas.
  - Opção de borda esticada (*pixel clone/stretch*) para fundos sólidos.
  - Permite corte preciso sem perder nenhum detalhe do conteúdo original.

### 2.4. Marcas de Registro Ótico e Códigos para Mesas de Corte (Zünd, iEcho, Summa)
* Para empresas que utilizam mesas digitais de corte com câmera:
  - **Marcas Circulares de Alinhamento:** Círculos pretos de $4\text{ a }6\text{ mm}$ de diâmetro posicionados nos quatro cantos da folha e ao longo das laterais.
  - **Camada Spot `CutContour`:** Inclusão do vetor de corte em uma camada separada com cor especial (Spot Color 100% Magenta, nomeada `CutContour`), padrão lido por todos os RIPs e softwares de mesa de corte.
  - **Identificação por Código de Barras / QR Code:** Código impresso no cabeçalho contendo o ID do trabalho, permitindo que a câmera da mesa leia o código e carregue o arquivo de corte automaticamente.

---

## 3. Critérios de Aceite

1. O operador pode selecionar uma arte de $10\text{ m}$ de largura, definir a bobina de $3{,}20\text{ m}$ e $2{,}5\text{ cm}$ de sobreposição, e o sistema gera automaticamente os PDFs de cada faixa já numerados e com as marcas de solda.
2. As marcas de ilhós devem ser visíveis tanto em fundos pretos quanto em fundos brancos.
3. Todas as marcas devem ser geradas vetorialmente no Form XObject sem degradar a resolução da arte do cliente.
