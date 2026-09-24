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

Medida do nome que é impossível o relatório **não usa, e só corrige com o arquivo aberto na mão**:
lado pequeno demais (`0.77X0.15CM`) vira a arte medida, e lado grande demais é vírgula perdida
(`8.28X320M` é 8,28 x 3,20 m — lido ao pé da letra virava 2.649 m² no lugar de 26,5 m², em 18 e
22/09/2026). Nos dois casos a prova é o arquivo batendo 100×, nunca palpite, e a linha sai
assinalada no PDF: `_nome_escreveu_metro` e `_nome_esqueceu_a_virgula`.

### Duas máquinas, um código, "postos"

O vigia roda em dois PCs diferentes, com o mesmo arquivo:

- **`POSTO_RIP`** — UJV 100 e SWJ320A, no PC do RIP (`C:\RasterLink\rasterlink_hotfolder.py`)
- **`POSTO_SAI`** — DOCAN, no PC principal, rodando direto desta pasta do repositório

`POSTO_PADRAO = POSTO_RIP` de propósito: a tarefa antiga do RIP chama sem `--posto` e continua
funcionando sem alteração nenhuma. Cada posto tem sua trava e seu `_sinal_de_vida_<posto>.json`.

Consequência prática: **editar `rasterlink_hotfolder.py` muda a DOCAN na hora** (o PC principal roda
do repositório), mas **não muda a UJV nem a SWJ** — aquelas só mudam quando o arquivo é levado pro
PC do RIP. Ver `maquina_rip/atualizar.bat`.

### Máquina de rolo e máquina plana decidem o giro por regras diferentes

`LimiteDaMaquina` (em `rasterlink_hotfolder.py`) é a **fonte única** de "cabe?" e "gira?" — a
mesma resposta serve a tela antes de mandar (`prever_giro`), o vigia na hora de copiar
(`_montar_para_hot_folder`) e o relatório depois (`nao_cabe`). A regra já esteve escrita nesses
três lugares, cada um com seu arredondamento.

- **Rolo** (`largura_util_m`: UJV, SWJ, DOCAN R5200) — uma medida é teto; o comprimento é a
  bobina, que anda. Por isso girar tem um segundo motivo além de caber: **economia**, deitar a
  arte alta e estreita pra sobrar material.
- **Mesa** (`mesa_util_m`: DOCAN H2525, plana) — os **dois** lados são teto, porque a chapa é
  finita nos dois sentidos. Girar serve só pra **encaixar** o que não entrou em pé; o que já
  cabe nunca gira, porque não há bobina pra economizar e girar brigaria com quem posicionou a
  chapa. Uma plana declarada com `largura_util_m` deixaria passar arte comprida demais pra mesa
  — daí `mesa_util_m` ganhar quando as duas aparecem.

O caso que separa as duas: 2,00 × 4,00 m passa deitado num rolo de 3,20 e imprime; numa mesa de
2,50 os 4,00 m não têm pra onde ir.

**Nas DOCAN o sistema só entrega** (regra do usuário, 24/09/2026: *"não barre nenhuma arte... antes
de ripar devo colocar no tamanho que preciso, então você mexer é desnecessário, é só subir para o
programa de RIP, eu resolvo o restante lá dentro"*). `"girar": False` no cadastro: a arte chega ao
SAi byte a byte como saiu da fila; a medida segue valendo pro aviso de "não cabe" e pro registro.
O que motivou: uma lona em escala 1:10 (página 0,70 × 0,32 de uma peça de 7 × 3,20) girada pela
medida da página — que numa arte em escala não quer dizer nada. As Mimaki seguem girando.

**A saída do SAi não se configura por arquivo, e apagar a pasta dela derruba o RIP.** Quem decide
onde o `.prt` nasce é a **porta** do setup no Production Manager (porta `FILE:`), ajustada na tela.
Em 23/09/2026 a pasta velha (`Desktop\Ripados`) foi apagada por estar vazia, dez minutos antes de
dois testes: os dois morreram com **"Não foi possível abrir a porta"** e 3 GB de dados ripados
ficaram presos nos temporários do SAi. A porta não avisa que perdeu o destino — ela só não abre.
**A saída se configura na tela "Mudar Porta", nunca em Propriedades** (documentado pela SAi:
botão direito no setup → *Mudar Porta*, ou duplo clique na aba dele). Na porta `FILE:`,
**"Solicitar caminho de arquivo para cada arquivo"** marcada abre "Salvar como" a cada trabalho;
desmarcada, grava sozinha no **"Local padrão"**. Setup novo nasce com ela marcada e o Local padrão
em `Jobs and Settings` — por isso a H2525 abria o diálogo e a R5200 não. O campo de pasta da tela de
**Propriedades** é a **hot folder, a ENTRADA**: em 23/09/2026 ela foi trocada ali achando que era a
saída, o que faria o Production Manager parar de receber o que o vigia entrega — e, com entrada e
saída na mesma pasta, ripar o próprio ripado em círculo. O `SETTINGS.PRF` guarda por setup
`[pergunta?][Local padrão][extensão personalizada?][extensão]` em strings do MFC; é só leitura,
porque o Production Manager o regrava com o programa **aberto**. O `PMSetups.ini` só é atualizado
depois, então `sai_setups.conferir_maquinas` pode demorar a acusar uma hot folder trocada.

**A porta é do DISPOSITIVO, não da configuração.** As duas DOCAN são configurações do mesmo
dispositivo `Docan Docan@FILE:` (aba de cima; o "Mudar porta..." fica na seta ▼ dela, ao lado de um
"Apagar" que apaga o dispositivo): trocar a Localização padrão de uma trocou a das duas (conferido no
`SETTINGS.PRF` em 24/09/2026 06:58). Então o SAi grava os ripados das DUAS em `D:\RIPADOS\DOCAN H2525`,
e quem manda o da R5200 pra `D:\RIPADOS\DOCAN R5200` é `separar_ripados.py`, a cada passada do vigia
da DOCAN. A prova de quem gerou cada `.prt` é o bloco "Iniciar a impressão" do `RIPLOG.HTML`
("Nome do dispositivo" + nome do trabalho + "Término da Saída", que bate com a hora do arquivo em menos
de 1 s). Sem as três coisas — e o arquivo parado há 30 s —, fica onde está e vira aviso uma vez.
Antes de ligar, três revisores reproduziram em pasta temporária: arquivo sendo gravado herdando a prova
de uma saída anterior de mesmo nome, cópia a cada minuto até encher o disco, e dois homônimos se
apagando. Os três viraram teste.

Cada trabalho **guarda o destino da hora em que entrou no SAi**: reenviar um trabalho antigo grava no
destino velho (`Desktop\Ripados`, no C:) — por isso o separador também varre ali. `Desktop\Ripados` é
pasta comum (a junção de 23/09 foi desfeita), e o setup **XLF** (Epson, de outra máquina, não se toca)
grava `.prn` nela: o separador só toca `.prt` de dispositivo DOCAN. E a saída só é gravada no
**Enviar**: ripar sozinho deixa o trabalho "Mantendo".

**Cada máquina grava na SUA pasta** (`D:\RIPADOS\<nome da máquina>`, o mesmo nome da fila).
Duas na mesma pasta misturariam os `.prt`, e um ripado de plana mandado pra máquina de rolo é
chapa perdida. `ripados_para_nuvem.garantir_pastas()` cria as duas, porque a porta do SAi não cria
pasta — destino faltando mata o trabalho **depois** de ripado.

**O ripado da DOCAN é `.prt`, e só `.prt`.** Em 23/09/2026 um `.prn` de 9,4 GB apareceu na pasta e
eu concluí que "a DOCAN às vezes sai `.prn`" — e fiz `listar()` aceitar os dois. Estava errado: o
RIPLOG mostrava `Impressora: XLF_HS_NET_EPS3200UV_LM`, perfil KALTECH; o `.prn` vinha da extensão
personalizada da porta do XLF. Aceitar `.prn` mandaria dado de Epson pra DOCAN. Antes de tirar
conclusão sobre um ripado, leia no `RIPLOG.HTML` **qual impressora** o gerou.

**O ripado mora no D:, e a entrega atravessa disco.** Um `.prt` acompanha a ÁREA impressa, não o
PDF — já medimos 13,8 GB saindo de um PDF de 582 KB. Desde 23/09/2026 `ripados_para_nuvem.
PASTA_RIPADOS` é `D:\RIPADOS` (462 GB livres contra 183 do C:, e encher o disco do Windows trava a
máquina inteira), com atalho na área de trabalho. Como o OneDrive continua no C:, `os.replace`
falha entre volumes: a entrega copia pra `~montando~<nome>.parcial` **na pasta do destino** e só
então faz o rename local — mesma disciplina da hot folder, mas aqui quem não pode ver arquivo pela
metade é o OneDrive. E `PASTA_NUVEM` fica **ao lado** da fila, nunca dentro: o vigia avisa a cada
passada sobre pasta dentro da fila que não seja máquina cadastrada.

**A hot folder do SAi nunca é escrita de cabeça**, porque o SAi corta o nome da pasta em 12 letras
(`XLF_HS_NET_EPS3200UV_LM` → `XLF_HS_NET_E`) e não usa o nome do setup (`Docan_H2525` virou
`Docan_1`). Caminho escrito de cabeça erra calado: o vigia diz "enviado" e a máquina nunca recebe.
Mas o `PMSetups.ini` **também mente, por atraso**: em 24/09/2026 a Hot Folder da H2525 foi trocada na
tela para `D:\RIPADOS\DOCAN H2525`, o `.ini` continuou dizendo `Docan_1`, e o adesivo das 06:39 ficou
parado na pasta que ninguém vigiava. A verdade viva é o `SETTINGS.PRF` (campo que o `PMConfig.xml`
chama de `<HotFolder>`); a prova definitiva é largar um arquivo na pasta e ver se ele entra na lista.
Hoje o cadastro da H2525 segue o SAi (`D:\RIPADOS\DOCAN H2525`), e por isso a SAÍDA dela nunca pode
ser essa mesma pasta.

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
`Fila\<máquina>\Enviados` (guardado 15 dias); é dali que se recupera, e quem faz isso é
`recuperar_registro.py` — marcando a linha com `recuperado`, que o relatório mostra na linha
(horário e giro de linha refeita são deduzidos, e isso tem que estar escrito).

**O nome em "Enviados" não é sempre o nome registrado.** O vigia registra o nome que o arquivo tem
na FILA e só depois move; se em "Enviados" já houver um com esse nome (a mesma arte entregue de
novo), o que entra ganha um `_<epoch>` no fim. Comparar as duas listas por nome cru faz a segunda
entrega parecer não registrada, e "recuperar" ela grava linha DUPLICADA — material contado duas
vezes na comprovação do cliente. Aconteceu em 23/09/2026: 21 das 108 linhas recuperadas eram
duplicatas, achadas na conferência do dia seguinte. `recuperar_registro.nome_no_registro` desfaz o
sufixo, e o casamento é em **duas voltas**: nome exato primeiro, sobra tenta sem o sufixo.

**Dois vigias no mesmo arquivo perdem linha sem dar erro.** De 17 a 22/09/2026 sumiram mais 108
entregas: o PC do RIP tinha DOIS loops antigos `.pyw` rodando junto com a tarefa agendada, e os
três gravavam no mesmo `.jsonl` do OneDrive. O OneDrive resolve conflito ficando com UMA versão —
as linhas dos outros evaporam, sem erro em log nenhum. Antes de investigar registro faltando,
confira **quantos processos** estão vigiando (`maquina_rip/parar_loop_antigo.bat`). A fila local
protege contra escrita falhada, não contra outro processo sobrescrevendo o arquivo inteiro.

**Quem descobre o problema não pode ser só a tela.** Em 23/09/2026 o vigia do PC do RIP deu o
último sinal às 15:03 e isso só apareceu às 19:22, quando alguém abriu o painel de agentes — a
tela de envio e o painel diziam a coisa certa desde as 15:15, mas ninguém estava olhando. Daquele
dia nasceu `aviso_fila.py`: notificação do Windows quando tem arquivo parado na fila há mais de
20 min, chamada no fim de cada passada do `rasterlink_hotfolder` (import tardio dentro de
try/except, porque lá no PC do RIP esse módulo viaja sozinho e o resto do projeto não existe).
Ele mede o FATO — arquivo parado —, não a causa, e por isso serve igual pro vigia derrubado, pro
OneDrive travado e pra hot folder sumida. Fila vazia não avisa nada, e o mesmo aviso não repete
antes de uma hora: alarme que toca sessenta vezes por hora vira alarme que se aprende a ignorar.

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

## Documento que lista arte MOSTRA a arte

Regra do usuário (2026-09-23): *"relatório de produção e impressão, todos precisam conter prévia
da arte — afinal somos uma gráfica, o nome é a arte, é sempre muito importante"*. Nome de arquivo
não identifica peça; a arte identifica.

A miniatura é uma função só, `miniaturas.de_arquivo` — eram três cópias iguais espalhadas
(OS, checklist, documento de Enviados) até virarem uma. Quem desenha usa `miniaturas.encaixar`
pra **nunca esticar** a arte, e mostra o quadrado cinza quando não dá pra abrir (EPS, arquivo
corrompido, arquivo grande demais): miniatura é conforto visual e nunca impede o documento de sair.

Dois detalhes que custaram tempo:

- **Renderize já na escala final.** Tem TIF de 1,8 GB e lona de 29 m nessas pastas; rasterizar
  inteiro pra fazer um quadradinho derruba a máquina. Acima de `miniaturas.LIMITE_BYTES` nem abre.
- **O relatório diário GUARDA a miniatura** (`Relatório de Impressão Diária/_miniaturas/AAAA-MM/`).
  O arquivo da arte sai de "Enviados" em 15 dias e o relatório é refeito a partir do registro a
  qualquer momento — sem guardar, refazer o relatório de um dia velho devolveria um documento sem
  arte nenhuma. São ~4 KB por peça.

No PDF a prévia entra por `<img src=...>` dentro do **mesmo** `insert_htmlbox` da página, com um
`pymupdf.Archive` ligando nome a bytes — não como `insert_image` separado, que desfaria a economia
de uma caixa de HTML por página. Uma `<table>` de duas colunas dá a coluna da arte; e vigie o
segundo valor devolvido pelo `insert_htmlbox` (`_Folha.menor_escala`): abaixo de 1 ele ENCOLHEU a
letra calado pra fazer caber.

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
- **Toda cor vem de `tema.py`** (decisão de 2026-09-22: *"mudar todas as telas para fundo escuro,
  colocar um botão pequeno na primeira página para mudar a cor quando eu desejar"*). Escuro é o
  padrão; o botãozinho do cabeçalho troca e grava em `config["tema"]`. Nunca escreva `#rrggbb` numa
  tela — é `cores.<coisa>`, lido **na hora de criar o widget**, porque widget do Tk não muda de cor
  depois de pronto: quem troca o tema **remonta** a tela principal (guardando o que estava digitado
  e o log) e as outras janelas nascem na cor nova quando abrem. As telas que não pedem cor nenhuma
  ficam certas por `tema.aplicar_padroes` (o `option_add` da aplicação + tema `clam` no ttk, que é
  o único que aceita cor) — chamado **antes** do primeiro widget, senão não vale pra nada.
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
- **`.bat` engole `)` e `^`.** Um `)` dentro de um `echo` fecha o bloco do `if` antes da hora e os
  DOIS ramos rodam; e dentro de aspas o `^` não escapa nada, então um `^|` chega literal no comando
  e ele quebra calado. As duas coisas quebraram a trava de máquina do `atualizar.bat` em 22/09 —
  e só apareceram porque o `.bat` foi RODADO. Rode antes de dizer que funciona:
  `MSYS_NO_PATHCONV=1 cmd.exe /c "echo. | maquina_rip\atualizar.bat"`.
- **Deploy no PC errado não dá erro.** O `atualizar.bat` copia pra `C:\RasterLink` da máquina onde
  roda, e no PC errado ele ainda diz "TUDO CERTO" — aconteceu em 22/09, e a UJV e a SWJ seguiram um
  dia a mais com a versão antiga. Hoje ele compara `%COMPUTERNAME%` com o nome que o próprio vigia
  grava no sinal de vida. Quem confirma um deploy é o **sinal de vida**, não a mensagem do script.
- **Não escreva `.lua` nem `.ps1` por heredoc do shell.** Cada camada come um nível de escape — já
  quebrou o mesmo Lua quatro vezes e um `\r` de caminho virou quebra de linha. Use a ferramenta de
  escrita de arquivo e depois `ferramentas/conferir_lua.py`.
- **PyMuPDF**: sempre `save(garbage=4, deflate=True)`; nunca segure um `Page` depois de acrescentar
  página (guarde o índice); `insert_htmlbox` embute um subconjunto de fonte **por chamada** (acumule
  a página inteira numa chamada só); `page.set_rotation(90)` só marca `/Rotate` e **distorce a arte**
  em quem lê a MediaBox junto — use `rasterlink_hotfolder._assar_giro`.
- **Fontes base-14 só falam Latin-1**: travessão, bullet e en-dash viram `·` silenciosamente.
- **No ttk, `map` ganha de `configure`** — e o tema `clam` já vem com mapas de estado próprios, em
  cinza claro de fábrica. Pintar só com `configure` deixa o widget certo parado e ERRADO quando
  muda de estado: a barra de rolagem sem nada pra rolar fica `disabled` e voltava branca no meio da
  tela escura; o mesmo vale pra botão apertado, aba não selecionada e Treeview. Ver
  `tema._estilo_ttk`. E cuidado: `style.map(...)` **substitui a lista inteira** daquela opção, o que
  aqui é bom — é assim que o cinza de fábrica sai.
- **O Aspire 8.5 não tem documentação pública de API.** O que se sabe foi sondado ao vivo; veja
  `aspire/api_8_5*.txt`. `MessageBox` do Aspire só aceita ASCII.
