# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## O que é este projeto

Sistema de produção da **Uny CV / Unyco Cenografia** (estandes, cenografia e comunicação visual
em grande formato). Começou como gerador de etiquetas e hoje cobre cinco coisas que compartilham
o mesmo `config.json` e o mesmo leitor de nome de arquivo:

1. **Etiquetas / OS / checklist** — `main.py` → `gui.py` → `processamento.py`
2. **Envio para as impressoras** — `producao.py` → `envio_impressao.py` → `rasterlink_hotfolder.py`
3. **Comprovação do que foi produzido** — registro permanente → `relatorio_producao.py`,
   cruzado com o que a máquina diz ter impresso (`_impressao`, lido do programa da impressora)
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
- **`POSTO_SAI`** — DOCAN, na máquina da impressora (`C:\VigiaDocan`), desde 03/10/2026

`POSTO_PADRAO = POSTO_RIP` de propósito: a tarefa antiga do RIP chama sem `--posto` e continua
funcionando sem alteração nenhuma. Cada posto tem sua trava e seu `_sinal_de_vida_<posto>.json`.

**Um posto tem UMA máquina, e quem garante isso é o sinal de vida.** A trava de instância única é um
arquivo LOCAL: ela impede duas passadas no mesmo PC e não enxerga nada do PC vizinho. Dois PCs no
mesmo posto pegariam o mesmo arquivo da fila (o RIP cria job duplicado) e gravariam no mesmo
`.jsonl` do OneDrive, que resolve conflito ficando com UMA versão — foi assim que 108 entregas
sumiram entre 17 e 22/09/2026. Desde 03/10/2026 a passada lê o sinal do posto antes de tocar em
qualquer coisa (`outro_vigia_no_posto`): se outra máquina escreveu há menos de
`MINUTOS_POSTO_DE_OUTRA_MAQUINA` (12 min, mais que o dobro dos 5 min em que o vigia vivo reescreve o
sinal), esta sai sem fazer nada e diz no log. **Quem sai é sempre quem chegou por último** — o dono
nunca se vê como intruso —, então trocar de máquina é desligar a tarefa da antiga; o
`maquina_sai/desinstalar_tarefa.ps1` apaga o sinal pra liberar o posto na hora, e sem isso a nova
assume sozinha em 12 min.

**O posto da DOCAN está indo pro PC da impressora** (pedido dele, 02/10/2026 à noite: *"quero que o
caminho delas venha da outra máquina para o OneDrive... quando eu jogar na pasta do OneDrive, de
entrar no programa de RIP direto, porém o da máquina de impressão"*). Ele instalou o Production
Manager 22.0 lá. O kit é `maquina_docan/` (espelhado em `OneDrive/UNYCOMUNICACAO/INSTALAR NAS MAQUINAS/DOCAN/`,
como o do RIP): o `rasterlink_hotfolder.py` viaja sozinho pra `C:\VigiaDocan` e a tarefa chama o
Python do sistema — fora da biblioteca padrão ele não precisa de nada, porque o PyMuPDF só entra
quando há giro e as DOCAN não giram. A hot folder do SAi **nunca** pode ser a pasta do OneDrive
direto: arquivo que o OneDrive ainda não baixou é marcador, e o RIP ripa o que vê. O ganho grande é
a segunda perna: com o RIP do lado da impressora, o `.prt` nasce lá e para de subir pelo OneDrive.

Consequência prática desde 03/10/2026: **editar `rasterlink_hotfolder.py` não muda máquina nenhuma
na hora.** O PC principal roda do repositório, mas ele atende só o posto do RIP — e as duas máquinas
que importam rodam CÓPIAS: `C:\RasterLink` (UJV, SWJ) e `C:\VigiaDocan` (as DOCAN). Cada uma só muda
quando o arquivo é levado: `maquina_rip/atualizar.bat` e `maquina_docan/atualizar.bat`.

**E o vigia não viaja mais sozinho.** Desde 04/10/2026 ele separa o ripado por máquina também na
máquina da DOCAN, e pra isso leva `separar_ripados.py`, `ripados_para_nuvem.py` e `caminhos.py` —
145 KB nos quatro, todos só de biblioteca padrão. O import é tardio em `try`: instalação antiga, com
um arquivo só, continua entregando e só não separa. O `maquina_docan/atualizar.bat` guarda os quatro
antes de copiar e devolve **o conjunto** quando o `--autoteste` falha: vigia novo com separador velho
é combinação que nunca foi testada.

**A raiz do ripado NÃO é a mesma nas duas máquinas.** No PC principal é `D:\RIPADOS`; na máquina da
DOCAN não existe D: nenhum (um disco só de 1,8 TB) e o ripado cai em `C:\RIPADOS` e no
`Desktop\RIPADOS`. Com o caminho fixo em D:, o separador varria pasta inexistente e não separava
nada, calado. Hoje quem responde é `ripados_para_nuvem.raiz_dos_ripados()`: `PASTA_RIPADOS` quando
ela existe, senão a primeira das `RAIZES_ALTERNATIVAS`. A procura por alternativa só acontece quando
`PASTA_RIPADOS` é o padrão de fábrica (`_PASTA_RIPADOS_PADRAO`) — é a trava que impede teste de
apontar a constante pra `tmp_path` e, porque ela ainda não existe, cair no `D:\RIPADOS` DE VERDADE,
onde tem ripado de gigabytes de trabalho em andamento. `rasterlink_hotfolder --preparar-ripados` cria
a pasta de cada máquina do posto e imprime a raiz, pro atualizador fazer o atalho sem adivinhar
caminho.

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

**Quem segura o giro é o campo, não a falta da biblioteca.** Até 04/10/2026 metade dessa regra valia
por acidente: a máquina da DOCAN não tinha PyMuPDF, então o vigia não conseguia medir nem girar nada.
Ele autorizou a instalação (*"vamos instalar e deixar completo"*, `maquina_docan/instalar_pymupdf.bat`)
pra ganhar duas coisas que faltavam ali — a **medida da página** no registro (é dela que o relatório
tira o m² quando o nome não traz medida, e sem ela a linha saía "medida não lida" sem recuperação,
porque o arquivo sai de "Enviados" em 15 dias) e o **aviso de "não cabe"**. Giro continua desligado
por `"girar": False` → `LimiteDaMaquina.decidir_giro` devolve None, e a cópia é `shutil.copy2`, byte
a byte. Travado em teste, inclusive a cópia byte-idêntica: tirar esse campo do cadastro faria a arte
chegar girada no SAi sem ninguém desconfiar do commit.

Uma consequência que o teste também escreve: numa máquina que não gira, arte que **só cabe deitada**
(6,00 × 2,00 m numa bobina de 5,00) passa **calada** — `cabe()` pergunta se cabe em alguma posição, e
quem ripa vai deitar. O aviso é pra arte sem salvação (os dois lados maiores que a máquina), não pra
essa. É a pergunta que alguém vai fazer olhando o log vazio.

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

### Montagem: a pasta encaixa as artes e fecha a folha sozinha

Pedido dele (04/10/2026): *"se a lona tem 500cm largura preciso jogar diversos arquivos dentro,
preciso que redimensione esses arquivos para ter o melhor aproveitamento... se eu jogar 10 arquivos
que tenha 10 nomes diferentes precisa ir um do lado de cada arte"*, fechando com *"essas pastas devem
fazer a leitura pelo nome, ver o tamanho do arquivo e redimensionar para a medida que pede no nome
conforme a regra antes de montar"*.

Ele larga arquivo em `MONTAGEM ARTES DOCAN 5200` ou `MONTAGEM ARTES SWJ 3200` (no OneDrive) e
`montagem.py` resolve. A largura é a da máquina, lida de `MAQUINAS` — o nome da pasta é só rótulo.

**Aqui o NOME manda no tamanho — e isso é o inverso do recebimento, de propósito.** Lá vale a medida
da arte (regra de 21/09); aqui o arquivo já foi recebido, conferido e nomeado, então o nome é a
medida combinada e arte fora dela está errada. `ajuste_para` decide: `igual`, `girar`, `escalar`
(a arte em 1:10 vira ×10; a exportada 3% maior é corrigida) — e **`recusar` quando a PROPORÇÃO não
bate**, porque aí não existe escala que conserte e distorcer entregaria peça deformada que só se
descobre impressa. O recusado vai pra `_conferir` **com o motivo num .txt ao lado**: peça que some
sem explicação é peça que não vai ser produzida.

**O encaixe é o mesmo de `aproveitamento.py`** — a fonte única continua uma só. O que mudou lá:
`posicoes_no_rolo` devolve **onde** cada peça fica, que até então era calculado e jogado fora, e a
**identidade atravessa o encaixe** (`_Pedaco.marcas`). Sem ela, duas peças de mesma medida trocariam
de rótulo — a LATERAL_ESQUERDA e a DIREITA têm 0,90 × 2,40 as duas, e quem corta penduraria a arte
errada na parede errada.

**A canaleta é espaço RESERVADO, não sobra.** Os 5 cm de dados entram somados à altura da peça
ANTES do encaixe; no primeiro desenho o rótulo de 5 cm foi escrito num vão de 1 cm e invadiu a peça
de baixo. O cabeçalho também tem faixa própria: escrever sobre a arte estraga a peça. Medidas dele:
folga de 1 cm, canaleta de 5 cm, nome em 30 cm. O rótulo encolhe de 18 até 9 mm e, no limite, corta
**a descrição, nunca a especificação** — cortar pelo fim deixava `1UN DECORFLEX 4.30X0.80M_~` e
jogava fora o `SPFW26_PASSARELA_PISO`, que é o que diz qual peça é.

**Uma folha por MATERIAL**, porque lona e adesivo não dividem bobina — a mesma regra do m² que nunca
mistura material. O nome de saída segue o padrão do sistema (`1UN LONA 5.00X9.86M_<CLIENTE>_MONTAGEM_
13pecas_<carimbo>.pdf`): a folha montada é UMA peça de material, e é assim que a etiqueta, a OS e o
relatório a leem. O cliente sai dos nomes dos arquivos (`cliente_das_pecas`), como ele pediu.

**O `.json` ao lado da folha é o que impede a montagem de APAGAR a comprovação.** Pro registro de
produção a folha é UM arquivo entregue; sem a ficha, as 13 peças sumiriam do relatório do cliente.
Ela guarda posição, medida, giro e o fator de escala de cada peça — número deduzido nunca se passa
por declarado.

A montagem pega carona na passada do **Checklist de Produção** (como o `vigia_caderno`), e só monta
pasta **parada** há `MINUTOS_PARADA`: largando dez arquivos seguidos, montar no primeiro faria uma
folha de uma peça e jogaria as outras nove numa segunda.

### Consumo de material é do LOTE, não da peça

Regra do usuário (28/09/2026): *"tirar melhor proveito do material sempre, independente se for chapa
ou rolo... o desperdício deve ser calculado como um todo, assim podemos calcular melhor nossa saída de
material do estoque"*. `aproveitamento.consumo_por_material` é a **fonte única** de metros, chapas e
sobra — a baixa de estoque, a cópia de CUSTOS e o resumo do fim da rodada chamam a mesma conta. As
peças do mesmo material **e variante** são encaixadas juntas: rolo minimiza metros (a largura é teto),
chapa minimiza chapas (os dois lados são teto), sempre com giro e sempre em **guilhotina** — encaixe que
só a fresa cortaria é economia de papel. A conta antiga (`dimensoes.calcular_desperdicio_item`, cada
peça sozinha na largura do rolo) ainda existe, mas não alimenta mais nada.

Duas coisas que a conta antiga escondia e que mudam o número pra CIMA: peça maior que o rolo ficava
**fora da conta** (agora entra dividida em faixas), e a sobra da chapa agora é a chapa inteira que sai
do estoque menos as peças (o resto aparece como "maior retalho"). A emenda de peça dividida **não** é
contada e sai escrita. Comparado em pedidos reais: Mercado Livre, lona de 836 m → 608 m (93%);
ASICS, adesivo de 6,2 m → 9,1 m (a peça larga passou a contar).

É estimativa de um encaixe bom e **possível** — o real sai do RIP ou de quem corta, e só bate se a
produção encaixar parecido. Por isso todo texto diz "estimativa, peças encaixadas juntas".

**Rolo no estoque é fração de rolo.** Cada baixa é um movimento (12,40 m de 50 = −0,248 rolo) e o saldo
se lê "19 fechados + aberto com 35,6 m". Até 28/09 os metros do rolo aberto iam pra um contador solto
(`acumulado_m`) e só viravam movimento quando um rolo fechava: pedido pequeno não deixava rastro, não
se desfazia e `pedido_ja_teve_saida` não o via. `carregar_estoque` converte o contador antigo em ajuste.
Variante no estoque casa por **espessura e cor** (`_mesma_variante`), nunca pelo dicionário — a peça
carrega cópia da variante do config com preço e rótulo. Chapa sem espessura no nome é ambígua e quem dá
baixa escolhe, como o acabamento do ADESIVO. `conferir_cadastro` mostra na tela de estoque o que o
config reconhece e o estoque não tem (e vice-versa).

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

### O que a máquina imprimiu é outro registro

Até 03/10/2026 o sistema provava o que foi **entregue** à máquina. O que ela **imprimiu** só o
programa dela sabe — o BYHX Printer Manager, em `C:\PrinterManager`, na máquina da DOCAN. Ele
guarda em dois arquivos, que dizem coisas diferentes:

- **`PrintedArea.Log`** — uma linha por PASSADA, append-only desde janeiro: hora, ripado, início,
  duração e percentual. É a única prova de que o `.prt` rodou, e a única fonte de **tempo de
  máquina** que não é estimativa.
- **`Joblist_His.xml`** — os trabalhos, com status (`Printed`/`Idle`), cópias e o tamanho em
  **polegadas**: 196,96 × 19,69 pol no arquivo chamado `5.00X0.50M` (= 5,003 × 0,500 m). É a
  medida que a máquina usou de verdade.

Três coisas que a leitura descobriu e que mudam o desenho:

- **A lista de trabalhos é uma JANELA, não um histórico** — tinha 13 e vai rolando. Então copiar o
  arquivo pro OneDrive não serve de comprovação: o que sair entre duas passadas se perde. Quem
  guarda é `registrar_impressoes`, que anota linha por linha em `_impressao/AAAA-MM.jsonl` — fila
  local primeiro, mesma disciplina do registro de entregas. A cópia dos dois arquivos continua
  indo, mas como **diagnóstico**.
- **`_impressao` nunca pode cair dentro de `_registro`**: quem lê `_registro` conta cada linha como
  uma entrega, e misturar dobraria o m² do relatório do dia.
- **A área do log está zerada nos registros recentes** (todas as 31 linhas de setembro/2026; em
  janeiro vinha preenchida), e o percentual também. Então m² nunca sai dali: sai do tamanho em
  polegadas ou do nome do arquivo. O que presta no log é a **duração** e o fato da linha existir.

No relatório, `provas_de_impressao` casa pelo nome do ripado sem extensão, em duas voltas (exato,
depois o que começa com ele e cresceu até 12 letras — o SAi acrescenta `_1`, `_2`, ` U_impress`).
Só conta passada do horário da entrega pra frente, senão a entrega de hoje herdaria a impressão de
ontem. E **ausência de prova nunca vira aviso**: só as DOCAN têm programa que registra, as Mimaki
não — acusar "não imprimiu" num documento que o cliente lê seria mentira. Quando a medida da
máquina difere da da linha, isso sai **escrito** (`1UN LONA ... 3.15X3.77M` imprimiu 2,39 × 3,77:
quem ripou ajustou lá dentro, que é o combinado — "DOCAN só entrega").

**A faxina do ripado só apaga o que o programa diz que imprimiu.** Em 03/10/2026 havia 327 GB de
`.prt` parados num disco único de 1,8 TB (um arquivo de 88 GB) — e nenhum deles estava no log nem
na lista: foram ripados em 02/10 e nunca rodaram. Apagar por data sozinha jogaria fora trabalho que
ainda vai sair, e ripar de novo custa horas de máquina. Então: só `.prt`, só nas pastas declaradas
(`PASTAS_RIPADOS_LOCAIS`), só o que imprimiu, e **sem a lista não apaga nada**. Três dias é decisão
dele. O que está velho e não imprimiu vira aviso uma vez, e disco abaixo de
`ESPACO_MINIMO_RIPADOS_GB` também — disco cheio trava a máquina com o RIP junto.

**Arquivo do programa da impressora se PROCURA, não se supõe.** Em 04/10/2026 o registro de
impressão passou a noite inteira na máquina da DOCAN sem anotar uma linha: o `PrintedArea.Log` não
está na RAIZ de `C:\PrinterManager`, e eu tinha escrito o caminho de cabeça — o `coletar_historico_byhx.ps1`
que rodou lá já procurava recursivamente e eu não copiei esse cuidado pro vigia. Hoje quem acha é
`arquivo_do_byhx`: raiz primeiro, depois as subpastas, ficando com o MAIOR homônimo (há mais de um
`Setting.xml` e mais de um `Print.log` lá dentro). E duas regras que vieram com o defeito: **não achar
vira aviso** (uma vez, dizendo que a faxina não vai apagar nada), e **arquivo que existe e não abre
também** — silêncio ali era o pior resultado possível. Sem o log, `registrar_impressoes` **não desiste
mais**: o trabalho `Printed` da lista é prova independente, com o tamanho que a máquina usou.

Tudo isso roda em `_cuidar_do_ripado`, no fim da passada do posto do SAi e **fora** de
`vigiar_fila_uma_vez` (teste chama aquela com o posto do SAi e passaria a apagar arquivo de
verdade). Cada tarefa no seu `try`: programa fechado ou log em outro formato não param as outras.

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

**Caderno no Canva entra pela mesma tela** (2026-10-02, cliente VIBRA, caderno da LOJINHA MR2
CULTURAL: *"preciso que toda a parte de recebimento de arte leia esse caderno também em Canva"*).
Colar o link do design abre `origem_artes.OrigemCaderno`: `caderno_canva` lê as fichas e cada ficha
vira um cartão no passo 1, com o arquivo que o link dela aponta no Drive. Sondado no caderno de
verdade, e cada item virou teste em `tests/test_caderno_canva.py`:

- **O link de edição pede login; o de visualização não.** O documento inteiro vem embutido na página
  `/view` (`window['bootstrap'] = JSON.parse(...)`). Formato interno, não API: muda sem aviso.
- **O link ESCRITO na ficha não é o link.** O texto azul das 60 fichas era o mesmo endereço, sobra
  do modelo, apontando um JPG de outro trabalho; o hiperlink de cada página é o certo. Endereço
  escrito repetido em várias fichas nunca serve de link (`link_do_modelo`).
- **Drive público dispensa a API**: 1 byte pedido devolve nome e tamanho, e há miniatura e download
  sem login (`drive_artes.info_publica`). O caderno inteiro lê com o token do Google vencido; só
  arquivo restrito ou link de pasta vão pela API.
- **A ficha decide material e quantidade** (regra de 2026-09-11), a medida continua da arte. A
  descrição vem do NOME DO ARQUIVO (15 fichas se chamam só "PLACA PS"; os arquivos são PLACA_PS_1,
  CUPOM_FISCAL...), sem o trecho que se repete em todos (`trecho_comum`: "loja_de_incoveniencia_vibra").
  "PLACA PS" com material ADESIVO avisa e oferece `PS ADESIVADO` na lista — quem decide é ele.
- **Várias fichas no mesmo PDF**: N fichas num PDF de N páginas repartem as páginas pela ordem do
  caderno (os três QUADROS); com outro número de páginas, cada ficha leva o arquivo inteiro, com aviso.

**Arte em escala 1:10 é a exceção provada de "vale a arte".** A agência desenha a lona grande em
1:10 (o Illustrator não passa de 5,77 m): LONA A com 7,14 × 1,10 m no caderno e 0,714 × 0,110 no PDF.
A regra de 2026-08-29 é *não multiplicar sozinho sem referência*; aqui há referência — o caderno ou
o nome —, e `receber_artes.escala_provada` só multiplica quando a arte × 10 BATE com ela: os dois
lados, ou partes de uma peça (o piso em 3 lonas), ou um lado exato e o outro perto (a LONA 18, cuja
altura difere do caderno — e isso vira o aviso de sempre). O nome leva `ESCALA 1-10`, o registro
guarda `escala` e a medida do arquivo, e a tela tem a caixinha pra desligar. Sem isso o nome
sairia com um décimo do tamanho — 23 das 62 peças da LOJINHA.

E o nome final tira a palavra de OUTRO material na hora de nomear (`receber_artes._sem_outro_material`),
não só ao propor: "ADESIVO ESPELHOS" passado pra PS ADESIVADO na tela era lido como ADESIVO pelo
leitor do nome, e o PS sumia da OS e do estoque.

**Duas regras do usuário de 2026-10-02 pro nome do recebimento** (com ou sem caderno):

- *"Quando falar placa pode colocar o PS + adesivo"* — `regra_da_placa`: a palavra PLACA na ficha ou
  no nome do arquivo faz o material virar **PS ADESIVADO** (se era ADESIVO, A DEFINIR ou PS). Placa
  que cita outra chapa ("PLACA PVC") fica fora: a regra é de PS.
- *"O restante manter o tamanho maior sempre que é com sangria"* — `medidas_do_nome`: peça com sangria
  leva **na frente** o tamanho COM sangria e a medida final atrás, como `_final` — é o que a equipe já
  fazia à mão nas lonas (`7.44X1.40M_LONA_C_7,14x1,10m`). A **placa** é a exceção: chapa cortada no
  final, que vai na frente, com `_sangria` atrás. O rótulo da segunda medida diz qual é qual; vale
  sempre a primeira — então m², máquina e estoque passam a contar com a sangria. O fluxo antigo do
  caderno do Mercado Livre (`caderno_arte.nome_no_padrao`, por comando) continua com a final na frente.

Peça de chapa maior que a chapa cadastrada ganha aviso (o CUPOM FISCAL de 3,10 m caiu na regra da
placa, e a chapa de PS é 2,00 × 1,00).

**O relatório de recebimento é o do Mercado Livre, estendido** (pedido de 2026-10-02: *"relatório dos
arquivos com miniatura igual feito em Mercado Livre e link indicando de onde pegou a determinada
arte"*). `relatorio_recebimento.montar_blocos` ganhou o parâmetro `fonte`: `_FonteSlides` é o de
sempre, `_FonteCanva` muda só quais fichas contam (todas — não há carimbo), onde mora o registro de
cada uma (`canva|<design>|p<página>|<id do Drive>`) e pra onde os links apontam. O desenho é um só.
Toda linha diz agora **de onde a arte foi pega**: a pasta do Drive no Mercado Livre, o arquivo do
Drive no Canva — e o arquivamento passou a gravar `link_origem` e `link_caderno` no registro. Sai
sozinho ao arquivar um caderno do Canva (`RECEBIMENTO - <CLIENTE>.pdf` na pasta do cliente) e se
refaz pelo botão "Relatório de recebimento" da tela, a partir do caderno guardado em
`_sistema/recebidos/` — sem ler o Canva de novo.

**O link do caderno do Canva é o `/view` puro, sem `#<página>`.** Eu pus `#8` achando que o Canva
abria na página; nunca foi provado, e o usuário respondeu *"não está abrindo o link"*. O `#` que chega
no Canva como `%23` dá a página de erro dele (HTTP 404, testado). A página da ficha vai escrita na
linha (`p.08`). Antes de entregar relatório com link, teste cada endereço — os 58 do VIBRA abrem.

**E o visualizador do Canva não abre caderno grande: a página viaja como IMAGEM.** Resposta dele,
ainda em 02/10: *"os arquivos abrem, porém a parte onde está localizado no caderno continua travada"*
— o `/view` de 68 páginas não termina de carregar (nem num Chrome sem tela, que derrubou a aba). Quem
diz ONDE a peça fica na loja é a página do caderno (planta e 3D com a peça em vermelho), e ela está
no mesmo JSON do `/view`: `draft.imageSets.thumbnail.images`, uma imagem de **596 × 335 px** por
página, com endereço **assinado que vence em ~2 h**. Pedir outro tamanho no endereço dá HTTP 403 (a
assinatura cobre o tamanho) e o `preview` de 1024 px só existe da página 1 — então é esse tamanho ou
nada. Por isso `OrigemCaderno.listar` **baixa na hora** (o passo 1 pode ficar aberto a tarde inteira)
só das páginas que têm ficha, guarda em `_sistema/recebidos/<lote>/paginas/0008.png` ao lado do
`caderno.json` — e o endereço, que vence, **não** é guardado. No relatório cada página vira uma folha
A5 deitada no fim, e `abrir no caderno` **pula pra ela dentro do PDF** (`LINK_GOTO`), com `voltar à
lista` e `abrir no Canva` de volta. Sem imagem, a linha continua abrindo o Canva.

**O caderno é documento VIVO, e o vigia confere sozinho.** Pedido de 03/10/2026: *"o vigia está sempre
passando; de qualquer cliente deve ser um padrão conferir se o caderno tem coisa nova; se tiver link
novo deve baixar e gerar um aviso pra eu saber"*. `vigia_caderno.py` pega carona na passada do
**Checklist de Produção** (a única tarefa que já percorre todos os clientes de minuto em minuto neste
PC — por isso não nasceu tarefa nova), com import tardio em try/except: caderno fora do ar nunca pode
derrubar a regeneração da OS. Quem é vigiado se cadastra sozinho: todo cliente cujo
`_sistema/recebidos/*/caderno.json` tem link do Canva — acabou o trabalho, a pasta sai e o vigia para.

Três coisas contam como novidade: **ficha nova**, **link novo** (ficha que ganhou link, ou arte
TROCADA — o id do Drive muda) e **ficha mexida** (medida, material ou quantidade diferente do que
estava escrito quando a arte foi recebida; não baixa nada, mas é o aviso que mais vale: produzir no
tamanho velho é material perdido). A conta é por **ficha** (seção + nome + ordem entre homônimas),
**nunca por número de página** — página nova no meio empurra todas as seguintes e o vigia anunciaria o
caderno inteiro. Link que outra ficha já apontava não é arquivo novo (os três QUADROS dividem um PDF).

Ele **baixa pra espera local** (`PASTA_RECEBENDO/_novidades/<cliente>/<lote>`, com o mesmo prazo de
faxina do lote da tela) e **nunca arquiva**: nome, medida e material continuam sendo decisão dele na
tela de dois passos. Lê o Canva **a cada 15 min por cliente**, não a cada minuto — cada leitura puxa
~1,4 MB, e o Canva não dá ETag nem Last-Modified (HEAD volta sem os dois); o que vem dentro da página
e diz se mudou alguma coisa é o `version` do rascunho (274 na LOJINHA em 02/10). O aviso é **um por
passada**, no máximo 8 linhas, e a novidade só sai da fila de pendentes quando a notificação passa —
se avisar falhar, o que já foi baixado não é baixado de novo.

Recebimento antigo (o do VIBRA) completa pelo botão: `relatorio_recebimento.completar_paginas` lê o
Canva de novo e só guarda a página que ainda diz **exatamente** o que dizia no recebimento
(`caderno_canva.paginas_que_conferem` — mesmas fichas, mesmos campos e links). O cliente edita o Canva
quando quer, e **uma página nova no meio empurra a numeração de todas as seguintes**: ilustrar a peça
com a página errada é pior que não ilustrar.

Duas coisas do PyMuPDF que isso descobriu: **os links que o `insert_htmlbox` cria só aparecem na
folha relida** (na mesma folha, `get_links()` devolve nada; `reload_page` quebra com `AssertionError`
de contagem de referência quando alguém ainda segura a página) — por isso `_escrever` reabre o
documento (`open("pdf", doc.tobytes())`) antes de anexar; e as 60 folhas anexadas são desenhadas com
as **base-14** (`helv`/`hebo`), nunca `insert_htmlbox`, que custa ~90 KB de fonte por chamada.

Duas coisas do PDF que custaram uma rodada: o HTML do PyMuPDF **ignora a largura da célula** e
encolhia a coluna da miniatura até a imagem (a lona estreita e a placa alta deixavam o texto
começando em lugares diferentes) — segura com um PNG transparente esticado na largura; e a altura de
cada bloco agora é **medida** numa folha de rascunho (`_alturas`), não estimada — com o link a mais,
a linha quebrava e o `insert_htmlbox` encolheria a letra calado.

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
- **Uma pasta por cliente em `etiquetas_geradas`, com os lotes dentro** (03/10/2026: *"está gerando
  duas pastas de clientes na hora que estou gerando as etiquetas, uma vem com uma OS — deixar apenas
  uma pasta"*). Eram dois lugares pro mesmo cliente: o lote nascia como `CLIENTE_<carimbo>` na raiz e,
  ao lado, a pasta `CLIENTE` onde o vigia do checklist escreve a OS da PRODUÇÃO. Agora a pasta do
  cliente é a única: a OS da produção fica na raiz dela e cada rodada é uma subpasta `<carimbo>`.
  O formato antigo continua sendo LIDO (tem pedido em andamento no disco assim) — quem resolve os
  dois é `utils.cliente_do_pedido` / `utils.pastas_de_lote`, e todo mundo que lia nome de pasta passou
  por ali: `estado_pedido` (achar o pedido anterior), `gui._pedidos_para_impressao` (que agora lista
  também a OS da produção, rotulada) e `arquivamento` (que **nunca** arquiva a OS da produção: ela não
  está "pronta", muda sozinha amanhã). O nome da pasta é o `documento` do cliente — se o que ele digita
  na tela de etiquetas não bate com o nome do cliente, nascem duas pastas de novo; é pra isso que
  existe o `nome_documento` no `cliente.json` (o VIBRA ficou com "VIBRA LOJA CONVENIÊNCIA").
- **`etiquetas_geradas` é SAÍDA DESCARTÁVEL.** O usuário apaga pedido e cliente de lá quando o
  trabalho termina — *"preciso manter somente o que está em andamento"*. Então nada que o sistema
  precise **lembrar** mora lá: vai em `Recebimento de Artes/<cliente>/_sistema/`. Aconteceu em
  2026-09-13: uma limpeza pelo Explorer levou pra Lixeira a lista das 50 etiquetas já impressas,
  e o próximo lote teria reimpresso todas. O PDF se regera; a memória do que já saiu, não.

## Regras que já custaram material de verdade

- **O vigia da produção voltou — mas só como vigia.** `monitor_onedrive.py` ficou CONGELADO de
  12/09 a 03/10/2026 porque ORGANIZAVA a pasta sozinho, distribuindo arte por material. Com a pasta
  plana isso deixou de existir (`organizar_pasta_producao` não move nada), e ele foi religado a
  pedido dele: *"pode ativar aquele vigia de movimentação das pastas de produção, lembrando que não
  vai estar mais por material e sim uma simples pasta de PRONTOS; vigiar tudo que estiver fora de
  PRONTOS e avisar como era antes"*. Hoje ele notifica entrada/saída/alteração de arquivo e acende o
  alerta vermelho na bandeja enquanto houver peça fora de PRONTOS. O atalho voltou do `_congelado`
  pra inicialização do Windows, e o painel de Agentes passou a medir **se ele está de pé** (era o
  contrário: até 03/10 o alarme era o atalho ter voltado sozinho pra inicialização).
- **A pasta de produção é PLANA: arquivo solto + uma pasta `PRONTOS`.** Regra dele de 03/10/2026:
  *"assim que for criada a pasta de produção, criar somente uma pasta de PRONTOS; deixar os arquivos
  soltos e, na medida que for ficando pronto, eu arrasto pra pasta. Antes estava por material, gerava
  muita pasta — como no nome já consta o que vamos produzir, não precisamos dessa separação por
  pasta; só em lista, etiqueta e relatórios precisa ser tudo separado"*. As quatro subpastas por
  material saíram de `producao.garantir_estrutura_producao`, e `organizar_pasta_producao` **não move
  mais nada**. A separação por material não se perdeu: ela sempre veio do NOME do arquivo
  (`_pasta_de_trabalho_para`, que virou um RÓTULO), e é dali que a OS, as etiquetas e os relatórios
  agrupam. Quem dependia da PASTA teve de mudar: a tela de envio tirava o corte puro da lista porque
  ele morava em `CORTES/` — agora tira pelo rótulo. Cliente antigo continua com as subpastas e
  continua sendo lido; o status PRONTO aceita as duas grafias e os dois lugares.
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
- **No PowerShell 5.1, uma linha de stderr DERRUBA o script.** Com `$ErrorActionPreference = "Stop"`,
  cada linha que um programa escreve em stderr vira `NativeCommandError` e termina tudo — mesmo com
  o programa saindo em código 0. Em 04/10/2026 um `SyntaxWarning` do Python (um `\P` perdido numa
  docstring minha) matou o `maquina_docan/atualizar.bat` no meio, **depois** de ele já ter copiado
  os quatro arquivos: o vigia estava certo e rodando, quem quebrou foi o script que conferia. Quem
  roda programa nativo usa `Start-Process -Wait -PassThru` com redireção pra arquivo (a redireção
  acontece FORA do PowerShell), ou afrouxa pra `"Continue"` em volta da chamada — ver `RodarPython`
  no `atualizar.ps1` e o mesmo cuidado no `instalar_tarefa.ps1`.
- **E `pythonw.exe` não devolve código de saída.** Programa sem console não é esperado pelo
  PowerShell e `$LASTEXITCODE` fica **vazio** — não zero, vazio. Em 04/10/2026 o atualizador leu
  isso como falha e **desfez um deploy que estava certo**. Duas lições viraram código: trocar pelo
  `python.exe` da mesma pasta quando existir (tem console, e o acento chega inteiro com
  `PYTHONIOENCODING=utf-8`), e **"não sei" nunca se passar por "falhou"** — código ausente avisa e
  segue, porque quem prova o deploy é o sinal de vida. Cuidado também com
  `Start-Process -ArgumentList`: ele não protege argumento com espaço (um `-c "a; b"` chega partido);
  nas chamadas do kit nenhum argumento tem espaço, e é de propósito. E do lado do Python: **aviso de
  sintaxe nos arquivos que viajam é defeito**, travado em `tests/test_arquivos_que_viajam.py` junto
  com a outra regra deles — só biblioteca padrão no topo, porque lá não há `.venv` nem projeto.
- **Deploy no PC errado não dá erro.** O `atualizar.bat` copia pra `C:\RasterLink` da máquina onde
  roda, e no PC errado ele ainda diz "TUDO CERTO" — aconteceu em 22/09, e a UJV e a SWJ seguiram um
  dia a mais com a versão antiga. Hoje ele compara `%COMPUTERNAME%` com o nome que o próprio vigia
  grava no sinal de vida. Quem confirma um deploy é o **sinal de vida**, não a mensagem do script.
- **Mas o sinal de vida não serve de prova IMEDIATA.** Ele é reescrito a cada 5 min de propósito
  (`_INTERVALO_SINAL_MINUTOS`), então um script que dispara a tarefa e espera um minuto pelo sinal
  quase nunca vê mudança: em 04/10/2026 o sinal era de 08:48:01 e a espera começou às 08:49, sem a
  menor chance — e na véspera tinha funcionado por sorte, porque os 5 min venciam. Quem responde na
  hora é o **Agendador**: `Get-ScheduledTaskInfo` dá `LastRunTime` e `LastTaskResult` (`267009` =
  ainda rodando, espere). O sinal continua valendo pra dizer QUEM é o dono do posto — e aí a
  pergunta certa não é "mudou?", é "o nome que está nele é desta máquina?".
- **Não escreva `.lua` nem `.ps1` por heredoc do shell.** Cada camada come um nível de escape — já
  quebrou o mesmo Lua quatro vezes e um `\r` de caminho virou quebra de linha. Use a ferramenta de
  escrita de arquivo e depois `ferramentas/conferir_lua.py`.
- **PyMuPDF**: sempre `save(garbage=4, deflate=True)`; nunca segure um `Page` depois de acrescentar
  página (guarde o índice); `insert_htmlbox` embute um subconjunto de fonte **por chamada** (acumule
  a página inteira numa chamada só); `page.set_rotation(90)` só marca `/Rotate` e **distorce a arte**
  em quem lê a MediaBox junto — use `rasterlink_hotfolder._assar_giro`.
- **Fontes base-14 só falam Latin-1**: travessão, bullet e en-dash viram `·` silenciosamente.
- **`except ImportError` não pega módulo QUEBRADO.** Em 02/10/2026 um `'` solto antes da docstring do
  `aviso_fila.py` (caractere perdido num editor aberto, nem commit teve) virou `SyntaxError` — que não
  é `ImportError` — e derrubou a passada inteira do vigia da DOCAN por 12 minutos: tarefa com
  resultado 1 e nenhuma entrega, calada. Todo gancho de conforto importado tarde (`aviso_fila`,
  `vigia_caderno`) pega `Exception` e **registra no log**; o trabalho de verdade segue.
- **No ttk, `map` ganha de `configure`** — e o tema `clam` já vem com mapas de estado próprios, em
  cinza claro de fábrica. Pintar só com `configure` deixa o widget certo parado e ERRADO quando
  muda de estado: a barra de rolagem sem nada pra rolar fica `disabled` e voltava branca no meio da
  tela escura; o mesmo vale pra botão apertado, aba não selecionada e Treeview. Ver
  `tema._estilo_ttk`. E cuidado: `style.map(...)` **substitui a lista inteira** daquela opção, o que
  aqui é bom — é assim que o cinza de fábrica sai.
- **O Aspire 8.5 não tem documentação pública de API.** O que se sabe foi sondado ao vivo; veja
  `aspire/api_8_5*.txt`. `MessageBox` do Aspire só aceita ASCII.
