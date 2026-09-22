# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## O que é este projeto

Sistema de produção da **Uny CV / Unyco Cenografia** (estandes, cenografia e comunicação visual
em grande formato). Começou como gerador de etiquetas e hoje cobre cinco coisas que compartilham
o mesmo `config.json` e o mesmo leitor de nome de arquivo:

1. **Etiquetas / OS / checklist** — `main.py` → `gui.py` → `processamento.py`
2. **Envio para as impressoras** — `producao.py` → `envio_impressao.py` → `rasterlink_hotfolder.py`
3. **Comprovação do que foi produzido** — registro permanente → `relatorio_producao.py`
4. **Corte na fresa CNC** — `corte_parametros.py` → gadget Lua dentro do Aspire
5. **Recebimento das artes** — `gui_receber.py` → `origem_artes.py` → `receber_artes.py`

O `README.md` descreve as quatro primeiras frentes para quem vai *usar* o sistema. Este arquivo é o mapa
fundo: arquitetura, decisões e as armadilhas que já custaram material.

**Tudo aqui é escrito em português** — código, comentários, docstrings, mensagens de tela,
nomes de função e mensagens de commit. Mantenha assim.

## Comandos

```bash
# Testes (o projeto tem .venv próprio; use-o, o Python do sistema não tem as dependências)
.venv/Scripts/python.exe -m pytest tests/ -q
.venv/Scripts/python.exe -m pytest tests/test_dimensoes.py -q          # um arquivo
.venv/Scripts/python.exe -m pytest tests/ -q -k "nome_do_teste"        # um teste

# Programa
python main.py                    # GUI; abrir_gerador.bat faz o mesmo usando a .venv
python main.py --cliente "X" --gerente "Y" --produtor "Z" --pasta-entrada entrada

# Vigia das hot folders — uma passada e sai (é assim que a tarefa agendada roda)
python -m rasterlink_hotfolder --uma-vez             # posto do RIP (UJV, SWJ)
python -m rasterlink_hotfolder --uma-vez --posto sai # posto da DOCAN
python -m rasterlink_hotfolder --autoteste           # só diz se consegue iniciar

# Depois de mexer em corte_parametros.py, REGERE o que o Aspire lê:
.venv/Scripts/python.exe -c "import corte_parametros as c; print(c.exportar_para_lua())"
.venv/Scripts/python.exe -c "import corte_parametros as c; c.gerar_gadgets(instalar=True)"

# Antes de salvar qualquer .lua
.venv/Scripts/python.exe ferramentas/conferir_lua.py aspire/corte_nucleo.lua
```

## Arquitetura

### O nome do arquivo é o banco de dados

`dimensoes.py` + `config.json` extraem **quantidade, material e medida** do nome do arquivo
(`"30UN PS ADESIVADO 1,26X2,02M_....pdf"`). Isso alimenta etiqueta, OS, cálculo de desperdício,
escolha de máquina e m² do relatório. Mexer nesse leitor muda tudo ao mesmo tempo — inclusive
relatórios de dias passados, que são regerados na hora a partir do registro bruto.

Duas regras já fixadas: com **duas medidas no nome, vale a PRIMEIRA** (é a do cliente; a segunda é
acréscimo da produção). Sem medida utilizável no nome, `relatorio_producao` abre o arquivo e mede
**a arte** (não a folha do gabarito) — e aí o m² **não** é multiplicado pela quantidade.

### Duas máquinas, um código, "postos"

O vigia roda em dois PCs diferentes, com o mesmo arquivo:

- **`POSTO_RIP`** — UJV 100 e SWJ320A, no PC do RIP (`C:\RasterLink\rasterlink_hotfolder.py`)
- **`POSTO_SAI`** — DOCAN, no PC principal, rodando direto desta pasta do repositório

`POSTO_PADRAO = POSTO_RIP` de propósito: a tarefa antiga do RIP chama sem `--posto` e continua
funcionando sem alteração nenhuma. Cada posto tem sua trava e seu `_sinal_de_vida_<posto>.json`.

Consequência prática: **editar `rasterlink_hotfolder.py` muda a DOCAN na hora** (o PC principal roda
do repositório), mas **não muda a UJV nem a SWJ** — aquelas só mudam quando o arquivo é levado pro
PC do RIP. Ver `maquina_rip/atualizar.bat`.

### O registro guarda fato bruto, não interpretação

`registrar_envio` grava uma linha JSON por arquivo entregue em
`OneDrive/.../Relatório de Impressão Diária/_registro/AAAA-MM.jsonl`: quando, máquina, arquivo,
bytes, se girou, tamanho da página. **Nada interpretado** — o PC do RIP só tem esse módulo, não o
projeto inteiro. Quem transforma nome em material/medida/m² é `relatorio_producao.py`, no PC
principal, que tem `config.json` e `dimensoes.py`.

**Nenhuma linha nasce direto no OneDrive.** Nasce na fila local ao lado do módulo
(`CAMINHO_REGISTRO_PENDENTE`) e `conciliar_registro`, a cada passada, escreve e **relê pra
conferir**, seguindo conferindo por 20 dias. Aconteceu de 09 a 16/09/2026: 61 entregas (1.311 m² de
lona) sumiram do relatório — a gravação falhava, o aviso ficava no log do PC do RIP e a linha
morria. Gravar sem erro não é prova. A prova de que uma entrega aconteceu é o arquivo em
`Fila\<máquina>\Enviados` (guardado 15 dias); é dali que se recupera, marcando a linha com
`recuperado`.

### Entrega atômica na hot folder

Arquivo nunca é escrito dentro da hot folder: é montado na pasta-mãe (`~montando~*.parcial`) e entra
por `os.replace`. O RIP vigia ativamente e ripa arquivo pela metade se deixar. Uma faxina remove
montagens abandonadas.

### Recebimento: a origem não importa, a arte manda

Arte chega com caderno (`caderno_arte` → `receber_artes.baixar_lote`) ou sem ele — só o link ou o
arquivo. Sem caderno é a tela `gui_receber.py`, em dois passos: **prévia com caixinhas antes de
baixar** e conferência antes de arquivar. Cada origem de `origem_artes.py` responde igual
(`listar`, `miniatura`, `baixar`): Drive (API, com a miniatura que o Google gera), **WeTransfer**,
pasta local e ZIP. O WeTransfer não tem API de download: usamos os endereços que o próprio site usa
(`prepare-download`, `download`), e o servidor aceita Range, então `ArquivoHttp` deixa o `zipfile`
ler o índice de um ZIP remoto sem baixá-lo. Não é oficial e pode mudar — o plano B é baixar o ZIP no
navegador e abrir como ZIP.

Regras do usuário (2026-09-21), que o código segue sem perguntar: **a medida vale sempre a da
arte**, nunca a do nome; o que o nome do arquivo especificar (`10UN`, `LONA`) vale; sem
especificação, **1 unidade e `A DEFINIR`**. `1UN` é resposta; `A DEFINIR` é pendência — fica em
`falta_confirmar` no registro, porque o material escolhe a máquina.

O que baixa espera em `caminhos.PASTA_RECEBENDO`, **local e fora do OneDrive**: arte que ele ainda
pode recusar não sincroniza, e cliente novo só nasce ao arquivar. O Illustrator e o Photoshop
trabalham lá também, nunca dentro de ARTES. PDF com páginas de **tamanhos diferentes** vira uma peça
por página (o TOTEM do Mandarin escondia um quadrado de 0,50 m na página 2 — a máquina imprime só a
primeira). Numa **imagem**, a marca de corte não é declarada: `marcas_de_corte.detectar_corte_em_imagem`
acha a linha pelas marcas cruzando margens opostas (é isso que limpa a tarja do Illustrator), e a
medida da arte passa a ser a distância entre as marcas, não a imagem inteira. O corte só acontece
depois que ele aprova, no Photoshop, conferido — mantendo a sangria, como no PDF.

### Corte CNC: uma fonte só de parâmetros

`corte_parametros.py` é a **fonte única** de fresa, passada, profundidade e ordem de usinagem.
Ele exporta para `aspire/parametros_corte.lua`, que `aspire/corte_nucleo.lua` (o gadget) lê. Editar o
`.lua` à mão não adianta: a próxima exportação apaga. A ordem **CORTE INTERNO antes de CORTE
EXTERNO** não é estética — quando o contorno externo fecha, a peça solta da chapa e qualquer furo
feito depois sai torto.

## OS e Checklist são MODELOS PADRÃO — nunca redesenhe

**Antes de gerar qualquer documento, procure o modelo no código.** OS, Checklist,
etiqueta, relatório: todos já existem e já foram aprovados pelo usuário depois de
muita iteração. O padrão não é "um jeito de fazer", é *o* jeito.

- **OS** → `relatorios.gerar_os` — agrupada por material, miniatura da arte,
  quadrinho pra marcar a caneta, página final "Subtotal por material" com m² por
  material e tempo de máquina. Escreve `OS - <CLIENTE>.pdf`.
- **Checklist** → o PDF de etiquetas **meia A4** (`ALTURA_ETIQUETA = ALTURA_A4/2`,
  2 por folha), montado dentro de `processamento.processar_etiquetas` com
  `pdf_layout.iniciar_pagina_com_banner`. Escreve `Checklist <CLIENTE>.pdf`.
- **Relatório de produção / recebimento** → `relatorio_producao`,
  `relatorio_recebimento`.

Aconteceu em 2026-09-12: pediram um checklist da pasta de produção e eu inventei
um layout próprio em vez de usar `gerar_os`. Foi recusado — *"precisa lembrar o
padrão que era a OS e checklist no codigo"*. Refazer custou uma rodada inteira.

Se o modelo não encaixa no caso novo, **estenda por parâmetro opcional** (foi
assim que o selo de status entrou em `_desenhar_item_os`: quem não passa `selo`
não vê diferença nenhuma) — nunca clonando o desenho num módulo novo.

**Custo de material só na cópia da gerência** (decisão de 2026-09-14): a OS impressa vai
pra produção e não leva valor. `gerar_os(custos=...)` escreve a cópia `CUSTOS - <CLIENTE>.pdf`
(`custos.py`), com cabeçalho "SÓ GERÊNCIA" em toda folha. **Ela nunca pode se chamar
`OS - ...`**: a tela de reimpressão (`gui._pedidos_para_impressao`) e o arquivamento acham OS
por `glob("OS - *.pdf")` — com esse nome, os valores iriam parar na mão de quem imprime pra
produção. Travado em `tests/test_custos.py`. Preço mora em `config.json` (por material e por
variante) — mais um motivo pra `config.json` nunca subir no commit.

## Clientes, saída descartável e o caminho pro executável

Decisões do usuário de 2026-09-13, que valem pro sistema inteiro:

- **"O sistema precisa funcionar totalmente pela janela."** Nada que ele use no dia a dia pode
  existir só como comando. Lógica sem Tk num módulo (`clientes.py`, `agentes.py`), tela em
  `gui_<coisa>.py` que só chama a lógica — é o que vai pro executável sem reescrever.
- **Todo caminho vem de `caminhos.py`.** Nunca `__file__` solto nem caminho relativo à pasta onde
  o programa foi aberto (era assim com `etiquetas_geradas`, e num .exe isso quebra). Ler sempre
  como `caminhos.X` na hora do uso, pra teste conseguir apontar pra `tmp_path`. Exceção:
  `rasterlink_hotfolder.py`, que vai sozinho pro PC do RIP.
- **Cliente = uma pasta em `OneDrive/UNYCOMUNICACAO/Recebimento de Artes/`** (`clientes.py`). Não
  existe lista central: a pasta é o cadastro, o `cliente.json` dentro dela é a configuração.
  Vários clientes em paralelo; nenhum nome de cliente escrito no código.
- **`etiquetas_geradas` é SAÍDA DESCARTÁVEL.** O usuário apaga pedido e cliente de lá quando o
  trabalho termina — *"preciso manter somente o que está em andamento"*. Então nada que o sistema
  precise **lembrar** mora lá: vai em `Recebimento de Artes/<cliente>/_sistema/`. Aconteceu em
  2026-09-13: uma limpeza pelo Explorer levou pra Lixeira a lista das 50 etiquetas já impressas,
  e o próximo lote teria reimpresso todas. O PDF se regera; a memória do que já saiu, não.

## Regras que já custaram material de verdade

- **Nunca escrever em pasta de produção sem pedido explícito.** As pastas de cliente em
  `OneDrive/UNYCOMUNICACAO/EVENTOS/...` são trabalho real, não bancada de teste.
- **Instalar, agendar ou copiar pra máquina só com autorização dele.** Aqui tudo é teste até ele
  dizer o contrário — gadget, tarefa agendada e deploy no RIP inclusive.
- **m² sempre subtotalizado POR MATERIAL.** Nunca um total somando materiais diferentes: cada um
  tem custo e máquina próprios, e o número combinado não significa nada.
- **Arquivo repetido no mesmo dia CONTA no subtotal** (refação consome material igual); fica
  sinalizado, nunca excluído.
- **Número deduzido nunca se passa por declarado.** O relatório de produção é comprovação pro
  cliente: medida obtida abrindo o arquivo, ou unidade corrigida, sai assinalada na linha.
- **Teste nunca pode tocar pasta real.** As constantes de módulo apontam pro OneDrive de verdade;
  um teste distraído já apagou o `estoque.json`. Use a fixture `autouse` que já existe em
  `tests/test_rasterlink_hotfolder.py`, `test_relatorio_producao.py` e outros três.
- **Antes de dizer "a API não permite X", sonde.** Já afirmei um limite do Aspire a partir de nota
  antiga, sem testar, e refiz um caminho que ele tinha recusado. A sonda aqui é barata.

## Armadilhas da plataforma (todas já quebraram na mão do usuário)

- **`.ps1` precisa de BOM UTF-8.** Sem BOM o PowerShell 5.1 lê acento como ANSI, o travessão vira
  aspa curva e o script quebra numa linha inocente. **`.bat` tem que ser ASCII puro.** Os dois estão
  travados por `tests/test_scripts_powershell.py`.
- **Não escreva `.lua` nem `.ps1` por heredoc do shell.** Cada camada come um nível de escape — já
  quebrou o mesmo Lua quatro vezes e um `\r` de caminho virou quebra de linha. Use a ferramenta de
  escrita de arquivo e depois `ferramentas/conferir_lua.py`.
- **PyMuPDF**: sempre `save(garbage=4, deflate=True)`; nunca segure um `Page` depois de acrescentar
  página (guarde o índice); `insert_htmlbox` embute um subconjunto de fonte **por chamada** (acumule
  a página inteira numa chamada só); `page.set_rotation(90)` só marca `/Rotate` e **distorce a arte**
  em quem lê a MediaBox junto — use `rasterlink_hotfolder._assar_giro`.
- **Fontes base-14 só falam Latin-1**: travessão, bullet e en-dash viram `·` silenciosamente.
- **O Aspire 8.5 não tem documentação pública de API.** O que se sabe foi sondado ao vivo; veja
  `aspire/api_8_5*.txt`. `MessageBox` do Aspire só aceita ASCII.
