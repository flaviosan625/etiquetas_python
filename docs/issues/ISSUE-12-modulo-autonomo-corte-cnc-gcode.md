# ISSUE-12: Módulo Autônomo de Corte CNC e G-Code (`corte_autonomo.py`)

**Ordem de Execução:** 12º  
**Status:** Pronta para Início  
**Dependência:** Nenhuma  
**Módulos a Criar:** `corte_autonomo.py`, `gerador_gcode.py`.  
**Módulos a Substituir:** `aspire/corte_nucleo.lua`, chamadas dependentes do Vectric Aspire em `corte_parametros.py`.  
**Referência de Base:** Algoritmos de percurso e furação de `c:\Users\flavi\Desktop\CNC CAM C++`.

---

## 1. Contexto e Motivação

Atualmente, o sistema gera um gadget em Lua (`aspire/corte_nucleo.lua`) projetado para rodar exclusivamente dentro do software comercial **Vectric Aspire**.

Isso impõe uma dependência externa pesada: gráficas que usam outras routers CNC ou softwares de corte (como ArtCAM, SheetCAM, Mach3, LinuxCNC, GRBL ou o próprio CNC CAM C++) não conseguem utilizar a automação de usinagem.

O objetivo desta issue é criar um **módulo de corte 100% autônomo**, capaz de:
1. Gerar **G-Code ISO padrão** diretamente pelo próprio sistema.
2. Exportar arquivos **DXF estruturados em camadas universais**.
3. Oferecer **interoperabilidade direta com o CNC CAM C++**, sem torná-lo uma dependência obrigatória.

---

## 2. Requisitos Técnicos

### 2.1. Ordenação Inviolável de Usinagem
O motor autônomo deve respeitar a regra física essencial do chão de fábrica:
1. **1º Passo:** Furos internos de fixação / ilhós (a chapa ainda está totalmente presa na mesa).
2. **2º Passo:** Contornos e cortes internos (vazados das letras e recortes centrais).
3. **3º Passo:** Contorno externo final (quando a peça finalmente se solta da sobra da chapa).

### 2.2. Gerador Universal de G-Code ISO (`gerador_gcode.py`)
- Geração de código G puro (compatível com Mach3, RichAuto, Syntec, DSP, NcStudio e GRBL):
  - Cabeçalho: `G21` (milímetros), `G90` (coordenadas absolutas), `G17` (plano XY).
  - Controle de Spindle: `M3 S<rpm>` e parada `M5`.
  - Controle de Velocidades: Avanço de corte (`F<feedrate>`) e velocidade de mergulho (`F<plunge>`).
  - Passadas Múltiplas em Z: Divisão paramétrica por espessura de material (ex: chapa de acrílico de 10 mm cortada em 3 passadas de 3,5 mm).
  - Movimentos rápidos (`G0`) e interpolação linear (`G1`) / circular (`G2`/`G3`).

### 2.3. Exportador DXF Estruturado & Interoperabilidade com CNC CAM
- Geração de DXF (versão R12 / R2000 puramente vetorial, sem bibliotecas pesadas de CAD):
  - Camada `FUROS`: Círculos e centros de furação.
  - Camada `CORTE_INTERNO`: Vetores fechados internos.
  - Camada `CORTE_EXTERNO`: Contorno externo da peça.
- **Conector com o CNC CAM C++:** Se o operador tiver o CNC CAM instalado no mesmo PC ou rede, o sistema exibe o botão *"Abrir no CNC CAM"*, exportando o lote diretamente para a fila de usinagem com ferramentas pré-configuradas.

---

## 3. Critérios de Aceite

1. O G-Code gerado deve ser aceito e simulado sem erros em controladores CNC comuns (Mach3, Candle, Universal Gcode Sender).
2. O sistema não deve exigir que o Vectric Aspire esteja instalado no computador.
3. Se o CNC CAM C++ não estiver presente, o usuário continua conseguindo exportar seu G-Code e DXF normalmente de forma autônoma.
