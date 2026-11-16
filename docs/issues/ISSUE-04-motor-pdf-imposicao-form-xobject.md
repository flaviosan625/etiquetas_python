# ISSUE-04: Motor Próprio de Imposição por Form XObject (`motor_pdf/montador.py`)

**Ordem de Execução:** 4º  
**Status:** Pronta para Início  
**Dependência:** ISSUE-03  
**Módulos a Criar:** `motor_pdf/montador.py`, `motor_pdf/escritor.py`.  
**Módulos a Substituir:** Rotinas de montagem de `montagem.py` dependentes de PyMuPDF (`show_pdf_page`, `insert_textbox`).

---

## 1. Princípio Arquitetural: Preservação Cega de Bytes

Softwares comuns de imposição frequentemente decodificam os PDFs em imagens rasterizadas ou reescrevem os fluxos DCT/JPEG, o que causa:
- Perda irreversível de nitidez tipográfica e vetorial.
- Inchaço desnecessário de arquivos (um PDF de 5 MB vira uma folha montada de 8 GB).
- Perda de camadas especiais de corte (`CutContour`) e canais de cor especiais (Branco e Verniz UV).

No nosso motor próprio, a imposição deve seguir estritamente o padrão **ISO 32000-1 via Form XObjects (`/Subtype /Form`)**:
- A folha montada atua como um "contêiner" geométrico.
- As artes originais entram como recursos `/XObject` independentes.
- O posicionamento na bobina é feito exclusivamente por matrizes afins (`cm`) e chamadas de desenho (`Do`).

---

## 2. Especificação do Montador (`montador.py`)

### 2.1. Estrutura do PDF Gerado
1. **Cabeçalho:** `%PDF-1.6` com comentário binário `%âãÏÓ`.
2. **Página Mestre (`/Type /Page`):**
   - `/MediaBox [0 0 largura_pt altura_pt]` (ex: 5,00 m $\times$ 12,40 m).
   - `/Resources`:
     - Dicionário `/XObject` contendo `/Fm1`, `/Fm2`, ..., `/FmN` (cada página importada de cada peça).
     - Dicionário `/Font` para fontes padrão de anotação de rodapé/rótulo (Type 1 padrão: Helvetica/Arial).
3. **Stream de Conteúdo da Página Mestre:**
   Para cada peça posicionada pelo algoritmo de encaixe (`aproveitamento.py`):
   ```postscript
   q
   % Matriz: escala_x, rotação, rotação, escala_y, translada_x, translada_y
   <a> <b> <c> <d> <pos_x_pt> <pos_y_pt> cm
   /Fm<id> Do
   Q
   ```

### 2.2. Geração dos Rótulos de 300 mm e Marcas de Refile
- O sistema atual possui a regra de que **o rótulo da peça deve medir exatamente 300 mm de largura**, localizado na meia-folga de 2,5 cm sem invadir a arte vizinha.
- O `montador.py` deve calcular o tamanho da fonte tipográfica para a string do rótulo fechar exatamente em 300 mm:
  $$\text{TamanhoFonte} = \frac{300\text{ mm} \times \text{PT\_POR\_MM}}{\text{LarguraTextoEmUnidadesDeGlifo}}$$
- Desenhar as linhas guia de refile de lâmina diretamente como operadores vetoriais finos (`0 0 0 RG 0.5 w m l S`).

---

## 3. Critérios de Aceite

1. O PDF montado final deve abrir perfeitamente em qualquer leitor de mercado (Adobe Acrobat, RIP RasterLink, RIP Production Manager SAi, navegadores).
2. Os streams de imagem originais devem ser copiados byte a byte (verificado por SHA1).
3. A velocidade de geração de uma folha montada de 5 metros com 30 peças não pode ultrapassar 1 segundo.
