# Índice Geral de Issues: Transformação Comercial e Motor Próprio — Automação Gráfica

Este diretório contém o plano de engenharia e a especificação detalhada de todas as **15 Issues** necessárias para transformar o sistema de produção e montagem (`etiquetas_python`) em um **produto de software comercial proprietário, autônomo e vendável**.

O projeto terá seu **próprio motor nativo de PDF e acabamento**, eliminando 100% de dependências restritivas de licenças (especialmente o PyMuPDF/AGPLv3) e operando de forma **totalmente independente do `CNC CAM C++`** (embora utilize o repositório do CNC CAM como base conceitual e exemplos de arquitetura).

> 📌 **Para a sequência detalhada de início e grafo de dependências, consulte:**  
> [**`ORDEM_DE_EXECUCAO.md`**](file:///c:/Users/flavi/Desktop/etiquetas_python/docs/issues/ORDEM_DE_EXECUCAO.md)

---

## Tabela de Issues e Ordem de Início

| # | Issue | Foco Principal | Módulos Principais | Referência no CNC CAM |
|:---:|---|---|---|---|
| **01** | [**ISSUE-01: Auditoria de Licenças e Eliminação de AGPL**](file:///c:/Users/flavi/Desktop/etiquetas_python/docs/issues/ISSUE-01-auditoria-licencas-eliminacao-agpl-terceiros.md) | Eliminação de `pystray` (LGPL), isolamento PyMuPDF, remoção Aspire e Adobe COM | `requirements.txt`, `corte_parametros.py` | — |
| **02** | [**ISSUE-02: Leitor & Parser de PDF Próprio**](file:///c:/Users/flavi/Desktop/etiquetas_python/docs/issues/ISSUE-02-motor-pdf-proprio-leitor-parser.md) | Parser sintático ISO 32000, XRef e descompressão Flate nativa (sem PyMuPDF) | `motor_pdf/leitor.py`, `preflight.py` | `src/io/pdf_vector.cpp` |
| **03** | [**ISSUE-03: Medição de Tinta Real (`caixa_da_arte`)**](file:///c:/Users/flavi/Desktop/etiquetas_python/docs/issues/ISSUE-03-motor-pdf-medicao-caixa-de-tinta.md) | Avaliação vetorial de operadores gráficos (`cm, q, Q, m, l, c, re, W`) sem rasterizar | `motor_pdf/geometria.py`, `dimensoes.py` | `src/io/pdf_vector.cpp` |
| **04** | [**ISSUE-04: Imposição por Form XObject**](file:///c:/Users/flavi/Desktop/etiquetas_python/docs/issues/ISSUE-04-motor-pdf-imposicao-form-xobject.md) | Montagem de bobinas/chapas preservando 100% dos bytes originais e rótulos de 300mm | `motor_pdf/montador.py`, `montagem.py` | Padrão ISO 32000-1 |
| **05** | [**ISSUE-05: Renderizador de Miniaturas & Relatórios**](file:///c:/Users/flavi/Desktop/etiquetas_python/docs/issues/ISSUE-05-motor-pdf-miniaturas-e-relatorios.md) | Geração de prévias e PDFs de OS / Romaneio de Retirada sem bibliotecas AGPL | `motor_pdf/miniaturas.py`, `relatorios.py` | Permissivo (PDFium/Pillow) |
| **06** | [**ISSUE-06: Painelamento Automático (*Tiling*)**](file:///c:/Users/flavi/Desktop/etiquetas_python/docs/issues/ISSUE-06-modulo-acabamento-tiling-painelamento.md) | Fatiamento de lonas gigantes com sobreposição de solda (*overlap*) e marcas guia | `tiling.py`, `montagem.py` | — |
| **07** | [**ISSUE-07: Ilhós Paramétrico, Sangria & CutContour**](file:///c:/Users/flavi/Desktop/etiquetas_python/docs/issues/ISSUE-07-modulo-acabamento-ilhos-sangria-corte.md) | Miras de prensagem, espelhamento de borda e vetor para mesas digitais (Zünd, iEcho) | `acabamento.py`, `corte_dxf.py` | — |
| **08** | [**ISSUE-08: Parser Paramétrico de Nomes**](file:///c:/Users/flavi/Desktop/etiquetas_python/docs/issues/ISSUE-08-desacoplamento-entrada-parser-parametrico.md) | Expressões regulares configuráveis por gráfica para romper a rigidez do nome | `parser_regras.py`, `dimensoes.py` | — |
| **09** | [**ISSUE-09: Grade de Triagem Visual em Lote**](file:///c:/Users/flavi/Desktop/etiquetas_python/docs/issues/ISSUE-09-painel-triagem-visual-em-lote.md) | Tela rápida de classificação para arquivos sem medidas no nome e importador Excel | `gui_triagem.py`, `gui.py` | — |
| **10** | [**ISSUE-10: Banco de Dados Relacional (SQLite WAL)**](file:///c:/Users/flavi/Desktop/etiquetas_python/docs/issues/ISSUE-10-banco-dados-relacional-sqlite.md) | Persistência transacional ACID, eliminando perdas do OneDrive e locks manuais | `banco/conexao.py`, `relatorio_producao.py` | — |
| **11** | [**ISSUE-11: Gerenciador de Máquinas & Abstração de RIPs**](file:///c:/Users/flavi/Desktop/etiquetas_python/docs/issues/ISSUE-11-gerenciador-maquinas-abstracao-rips.md) | Drivers configuráveis em tela para Mimaki, SAi, Onyx, Caldera e hot folders genéricas | `hardware/gerenciador.py`, `hardware/drivers/` | — |
| **12** | [**ISSUE-12: Módulo Autônomo de Corte CNC e G-Code**](file:///c:/Users/flavi/Desktop/etiquetas_python/docs/issues/ISSUE-12-modulo-autonomo-corte-cnc-gcode.md) | Eliminação do Aspire; gerador de G-Code (furos $\rightarrow$ internos $\rightarrow$ externos) e DXF universal | `corte_autonomo.py`, `gerador_gcode.py` | Integração amigável CNC CAM |
| **13** | [**ISSUE-13: UI Profissional & Canvas WYSIWYG**](file:///c:/Users/flavi/Desktop/etiquetas_python/docs/issues/ISSUE-13-interface-profissional-canvas-wysiwyg.md) | Interface PySide6 com aceleração gráfica a 60 FPS e arrasto manual na bobina | `ui/app.py`, `ui/canvas_montagem.py` | Padrão visual Qt6 do CNC CAM |
| **14** | [**ISSUE-14: Licenciamento Criptográfico (Ed25519)**](file:///c:/Users/flavi/Desktop/etiquetas_python/docs/issues/ISSUE-14-licenciamento-criptografico-ed25519.md) | Amarração de hardware (Hardware ID) e assinaturas digitais assimétricas | `licenciamento/`, `emissor_licenca.py` | `tools/license_tool/` (Monocypher) |
| **15** | [**ISSUE-15: Compilação Nativa & Instalador Setup.exe**](file:///c:/Users/flavi/Desktop/etiquetas_python/docs/issues/ISSUE-15-compilacao-nativa-instalador-setup.md) | Compilação C++ com Nuitka e instalador profissional de 1 clique (Inno Setup) | `scripts/compilar_nuitka.ps1`, `instalador.iss` | Estratégia de Release do CNC CAM |

---

## Princípios de Independência

1. **Autonomia Completa:** O software gráfico deve ser vendido e executado sozinho. Ele **não** depende da presença do `CNC CAM C++` para funcionar.
2. **Reaproveitamento de Conhecimento:** Usamos o `CNC CAM C++` como nosso "banco de referências comprovadas" (leitura de PDF em C++, arquitetura de licenciamento por curva elíptica e ergonomia de viewport Qt).
3. **Sem Cópia, com Excelência de Engenharia:** Todo módulo é desenhado do zero para atender especificamente o fluxo de grandes formatos (impressão digital em rolo e mesa plana), superando concorrentes comerciais como Caldera e Enfocus no custo-benefício e facilidade de chão de fábrica.
