# ISSUE-13: Interface Profissional PySide6 e Canvas Interativo WYSIWYG

**Ordem de Execução:** 13º  
**Status:** Pronta para Início  
**Dependência:** Fases 1 a 4 (Módulos de PDF, Acabamento, Banco e Hardware prontos)  
**Módulos a Criar:** `ui/app.py`, `ui/janela_principal.py`, `ui/canvas_montagem.py`, `ui/tema.py`.  
**Módulos a Descontinuar:** `gui.py`, `tema.py` (Tkinter).  
**Referência de Base:** Design de interface, paleta de cores e widgets de `c:\Users\flavi\Desktop\CNC CAM C++\src\ui\`.

---

## 1. Motivação de Produto

Para que diretores e operadores de birôs comprem o software, a interface gráfica precisa transmitir solidez, modernidade e produtividade:
- O **Tkinter** atendeu perfeitamente ao período de testes internos, mas sua limitação de aceleração de vídeo impede uma navegação fluida em folhas de grande formato.
- Adotar **PySide6 (Qt6)** unifica a identidade visual e o padrão técnico com o `CNC CAM C++`, permitindo reutilização direta de ícones, estilos de botões, paleta de cores e conceitos de viewport OpenGL.

---

## 2. Especificação do Canvas Interativo WYSIWYG (`canvas_montagem.py`)

O coração visual da nova interface é o canvas de montagem baseado em `QGraphicsView` com suporte a aceleração gráfica por hardware:

### 2.1. Navegação e Réguas Dinâmicas
* **Zoom e Pan Fluido (60 FPS):** Zoom centrado no cursor através da roda do mouse; navegação em pan segurando o botão do meio ou barra de espaço.
* **Réguas Métricas Dinâmicas:** Exibição da largura da bobina (ex: 3,20 m) e do comprimento em tempo real, com marcações em centímetros e metros que se adaptam conforme o nível de zoom.
* **Margens de Segurança:** Linhas tracejadas indicando a largura útil máxima da máquina e os limites da bobina.

### 2.2. Manipulação Interativa de Peças na Bobina
* O algoritmo de aproveitamento faz o posicionamento inicial ideal.
* **Intervenção Manual do Operador:**
  - O operador pode clicar e arrastar qualquer peça para reordenar o encaixe na bobina.
  - **Detecção de Colisão em Tempo Real:** Se uma peça colidir com outra ou sair para fora da largura útil da máquina, sua borda acende em vermelho e o botão de envio para a impressora é bloqueado temporariamente.
  - **Menu de Contexto (Botão Direito):** Rotacionar $90^\circ$, alterar quantidade de cópias, aplicar fatiamento (*tiling*) ou remover peça da folha.

### 2.3. Painel de Máquinas e Fila de Produção
* Exibição em cartões (*cards*) laterais de cada impressora cadastrada:
  - Status em tempo real: `Ociosa`, `Ripando`, `Imprimindo`, `Aguardando Mídia`.
  - Prévia em miniatura do trabalho corrente e progresso em porcentagem / m².

---

## 3. Critérios de Aceite

1. O canvas deve renderizar uma bobina de $5\text{ m} \times 20\text{ m}$ contendo 50 artes com fluidez total (sem engasgos ou atrasos de resposta).
2. O tema visual deve ser escuro (*Dark Mode* moderno com contraste profissional), idêntico aos padrões industriais de pré-impressão.
3. Não deve restar nenhuma dependência de bibliotecas Tkinter no aplicativo principal.
