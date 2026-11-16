# ISSUE-07: Módulo de Acabamento — Ilhós Paramétrico, Sangria Automática e CutContour

**Ordem de Execução:** 7º  
**Status:** Pronta para Início  
**Dependência:** ISSUE-04  
**Módulos a Refatorar:** `acabamento.py`, `corte_dxf.py`.  
**Módulos a Criar:** `tests/test_acabamento_completo.py`.

---

## 1. Descrição do Recurso

Consolidar as ferramentas de acabamento de comunicação visual diretamente integradas ao nosso motor de PDF:
1. **Marcas de Ilhós Industriais:** Eliminar a medição manual com trena na bancada de acabamento.
2. **Sangria Automática (*Mirror Bleed*):** Eliminar filetes brancos no refile de artes enviadas sem sangria pelo cliente.
3. **Contorno de Corte Digital (`CutContour`):** Geração de camadas vetoriais para plotters de recorte e mesas de corte com câmera ótica (Zünd, Kongsberg, iEcho, Summa).

---

## 2. Requisitos Técnicos

### 2.1. Refatoração de `acabamento.py` para o Motor Próprio
- Remover o import de `pymupdf`.
- Usar operadores nativos de desenho do PDF (`0 g`, `1 G`, `w`, `m`, `l`, `c`, `re`, `S`, `B`):
  - **Mira de Ilhós de Duplo Contraste:** Círculo externo branco de $10\text{ mm}$ (halo de contraste) sobreposto por círculo preto com cruz central e ponto de centro de agulha de $1\text{ mm}$.
  - **Distribuição Paramétrica:** Cálculo automático da quantidade de furos com espaçamento de 30 cm, 40 cm ou 50 cm e recuo de 2,5 cm da borda.

### 2.2. Gerador de Sangria por Espelhamento (*Mirror Bleed*)
- Quando ativado, o motor expande a caixa da página em $10\text{ mm}$ em cada lado.
- As quatro faixas de margem são preenchidas por reflexão (espelhamento horizontal e vertical dos pixels da borda da arte), garantindo que lâminas de corte tenham tolerância sem cortar o design nem deixar borda branca.

### 2.3. Camada Vetorial `CutContour` (Spot Color Magenta)
- Criar a camada `/OCG` (Optional Content Group) nomeada `CutContour` com uma cor especial `/Separation` baseada em $100\%$ Magenta.
- Inserir o caminho vetorial de contorno do retângulo da peça ou desenho curvo para que o RIP envie o arquivo de corte diretamente para a plotter.

---

## 3. Critérios de Aceite

1. O PDF gerado com marcas de ilhós deve abrir perfeitamente sem erros de sintaxe em RIPs e no Acrobat.
2. A camada `CutContour` deve ser reconhecida automaticamente por softwares de corte (Summa CutServer, Zünd Cut Center, Mimaki FineCut).
