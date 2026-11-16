# ISSUE-06: Modernização da Interface (UI/UX) e Visualizador Interativo WYSIWYG

**Status:** Aberta  
**Prioridade:** Alta  
**Módulos Afetados:** `gui.py`, `main.py`, `tema.py`, `gui_receber.py`, `previas_impressao.py`.

---

## 1. Contexto e Necessidade de Mercado

A interface gráfica atual em **Tkinter** foi fundamental para o desenvolvimento e validação interna na Uny CV. No entanto, para comercializar uma solução profissional para diretores e operadores de gráficas, o Tkinter apresenta limitações visuais e técnicas severas:
- Aparência defasada que transmite a impressão de software amador.
- Dificuldade para criar um canvas de alta performance com zoom e pan suaves em arquivos de grande porte (lonas de até 30 metros).
- Impossibilidade de arrastar e reposicionar artes na folha montada de forma interativa (*drag-and-drop*).

---

## 2. Nova Arquitetura de Interface

### 2.1. Tecnologia Recomendada: PySide6 (Qt6) — Alinhamento com o CNC CAM
A escolha técnica mais vantajosa é **PySide6 (Qt6 para Python)**:
* **Sinergia Total com o CNC CAM:** O `CNC CAM C++` já utiliza Qt6.8 (`Qt6::Widgets`, `Qt6::OpenGL`, `QPainter`). A linguagem visual, temas, ícones e até componentes C++ podem ser reutilizados diretamente.
* **Licença Comercial Limpa:** O Qt Company oferece suporte e o PySide6 permite empacotamento com isolamento adequado de bibliotecas.
* **Alta Performance Gráfica:** Utilização de `QGraphicsView` ou `QOpenGLWidget` para renderizar a bobina inteira a 60 FPS com aceleração por hardware.

### 2.2. Visualizador Interativo da Folha Montada (WYSIWYG)
O grande diferencial de vendas frente a soluções antiquadas será a prévia visual interativa:
* **Controles do Canvas:**
  - Zoom suave com a roda do mouse e Pan segurando o botão do meio ou barra de espaço.
  - Régua milimétrica dinâmica nas bordas superior e lateral (em metros e centímetros).
  - Indicação clara da largura útil da bobina e das margens de segurança da impressora.
* **Manipulação Manual de Peças:**
  - O algoritmo de nesting posiciona as peças automaticamente, mas o operador tem autonomia para intervir.
  - Capacidade de clicar e arrastar uma arte para outra posição na folha.
  - Clique com botão direito para girar a peça $90^\circ$ ou alterar a quantidade.
* **Inspeção de Alertas em Tempo Real:**
  - Peças com resolução insuficiente piscam com um selo de aviso laranja (`DPI Baixo: 42 DPI`).
  - Peças que ultrapassam o limite da mídia são destacadas em vermelho com bloqueio de envio.

### 2.3. Painel de Chão de Fábrica (Fluxo Visual Kanban)
* Substituição de diálogos modais por abas operacionais fluidas:
  1. **Recepção & Triagem:** Recebimento de artes e atribuição rápida de medidas/materiais.
  2. **Mesa de Montagem:** Seleção de máquina e geração do encaixe/imposição.
  3. **Filas de Impressão:** Monitoramento das máquinas em tempo real (qual arquivo está rodando, tempo estimado, m² produzido).
  4. **Expedição & Romaneio:** Emissão rápida do PDF de retirada com assinaturas e conferência por código de barras.

### 2.4. Bandeja do Sistema Nativa (Substituição do `pystray`)
* Ícone na área de notificação do Windows implementado via `QSystemTrayIcon` (nativo do Qt) ou chamada direta a `Shell_NotifyIconW`, eliminando 100% da dependência de bibliotecas LGPL de terceiros.

---

## 3. Critérios de Aceite

1. O visualizador deve abrir e renderizar uma bobina de 5 metros contendo 40 artes vetoriais em menos de 1 segundo.
2. O operador deve poder reorganizar manualmente a montagem com drag-and-drop suave e sem travamentos.
3. Interface com tema escuro profissional (Dark Mode moderno), compatível com resolução 4K e escalonamento DPI do Windows 11.
