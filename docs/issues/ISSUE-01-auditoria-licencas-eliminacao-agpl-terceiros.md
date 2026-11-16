# ISSUE-01: Auditoria Completa de Licenças e Eliminação de Dependências Restritivas

**Status:** Aberta  
**Prioridade:** Crítica (Bloqueante Comercial)  
**Módulos Afetados:** `requirements.txt`, todos os módulos com importação de `pymupdf`/`fitz`, `pystray`, `corte_parametros.py`, `conversao_adobe.py`.

---

## 1. Contexto e Motivação

Para transformar o sistema em um **software comercial proprietário (fechado/vendável)**, é juridicamente proibido distribuir ou comercializar binários vinculados a licenças de software com **Copyleft Forte/Viral (GPL / AGPL)** sem disponibilizar 100% do código-fonte do produto sob a mesma licença, ou pagar royalties recorrentes de licenciamento comercial.

O objetivo desta issue é mapear e erradicar **todas** as dependências que criam contaminação jurídica ou dependência técnica de terceiros, garantindo independência tecnológica total.

---

## 2. Inventário de Riscos Jurídicos e Dependências

### 2.1. PyMuPDF (fitz) — RISCO CRÍTICO (AGPLv3)
* **O que é:** Interface Python para a biblioteca MuPDF (Artifex Software).
* **Licença Atual:** **GNU AGPLv3** (Affero General Public License v3) ou Licença Comercial Proprietária paga à Artifex.
* **Impacto:** A AGPLv3 estipula que qualquer distribuição de binário ou até mesmo disponibilização de software como serviço (SaaS pela rede) exige a abertura irrestrita de todo o código-fonte proprietário. As licenças comerciais da Artifex costumam custar dezenas de milhares de dólares por ano.
* **Ação:** **Substituição completa por motor próprio**, espelhando o que foi feito no `CNC CAM C++` (`src/io/pdf_vector.cpp`), sem depender de MuPDF ou Poppler (ambos GPL/AGPL).

### 2.2. pystray — RISCO MÉDIO/ALTO (LGPLv3)
* **O que é:** Biblioteca usada para exibir o ícone do vigia na bandeja do sistema (System Tray).
* **Licença Atual:** **GNU LGPLv3**.
* **Impacto:** Embora a LGPL permitaリンク dinâmico, o empacotamento estático em executável Windows (.exe via PyInstaller ou Nuitka) cria complexidade jurídica quanto aos requisitos de re-link e engenharia reversa exigidos pela LGPLv3.
* **Ação:** Substituir por integração nativa direta com a API do Windows (`Shell_NotifyIconW`) usando `ctypes` ou `pywin32` (licença PSF permissiva), eliminando a biblioteca de terceiros.

### 2.3. Gadget Lua para Vectric Aspire — RISCO DE DEPENDÊNCIA DE PRODUTO DE TERCEIROS
* **O que é:** Em `corte_parametros.py` e `aspire/corte_nucleo.lua`, o sistema exporta scripts Lua para rodar dentro do **Vectric Aspire**.
* **Problema Comercial:** O Aspire é um software de terceiros que custa mais de US$ 2.000 por assento. O cliente do seu software que não tem o Aspire (ou que usa mesas router com outros softwares) fica órfão.
* **Ação:** 
  1. Integrar diretamente com o **CNC CAM C++ próprio** (via geração de projeto nativo ou DXF padronizado com camadas semânticas de fresa/profundidade/ordem).
  2. Gerador nativo de G-Code padrão (ISO G-Code: G0, G1, G2, G3 com percursos ordenados: furos $\rightarrow$ cortes internos $\rightarrow$ cortes externos).

### 2.4. Automação COM do Adobe Illustrator (`conversao_adobe.py`)
* **O que é:** Scripts que acionam o Illustrator instalado via OLE/COM para converter arquivos `.ai` e `.eps`.
* **Problema Comercial:** Obriga o cliente final a ter uma assinatura ativa da Adobe Creative Cloud no mesmo PC.
* **Ação:** Arquivos `.ai` modernos desde a versão CS2 são, na verdade, arquivos PDF encapsulados (com stream de compatibilidade PDF). O motor próprio de PDF deve ler e abrir arquivos `.ai` diretamente através do seu leitor de PDF nativo.

---

## 3. Critérios de Aceite para Licenças Permissivas

Qualquer biblioteca de terceiros mantida no projeto deve obrigatoriamente possuir uma das seguintes licenças permissivas:
1. **MIT / Expat**
2. **Apache 2.0**
3. **BSD (2-Clause ou 3-Clause)**
4. **Zlib / libpng**
5. **Python Software Foundation License (PSFL)**

**Regra Absoluta:** Nenhuma biblioteca GPLv2, GPLv3, AGPLv3 ou com cláusulas "Non-Commercial / CC-BY-NC" será aceita no repositório.

---

## 4. Plano de Execução

1. **Varredura Completa de Imports:** Confirmar que nenhum arquivo remanescente importa `fitz`, `pymupdf` ou `pystray`.
2. **Substituição da Bandeja (Tray Icon):** Criar `win32_tray.py` usando `ctypes.windll.shell32.Shell_NotifyIconW`.
3. **Substituição do Aspire:** Adicionar exportador universal de percursos (G-Code e DXF limpo para o CNC CAM próprio).
4. **Isolamento de APIs Proprietárias de Terceiros:** Tornar módulos do Google Drive/OAuth e Canva puramente opcionais/desacoplados via plugins, sem travar o núcleo da aplicação.
