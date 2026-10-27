# Montagem e fluxo das impressoras â€” atualizado em 09/10/2026

Objetivo: reduzir a escolha manual de arquivos e o retrabalho, conservando as regras de medida e a qualidade da arte. A pasta analisada foi `C:\Users\flavi\OneDrive\UNYCOMUNICACAO\MONTAGEM ARTES MAQUINAS`. O desenvolvimento e os testes usam o projeto local e entradas isoladas; os lotes reais dessa pasta nÃ£o foram remontados.

## MudanÃ§as na montagem

- **Sem divisÃ£o automÃ¡tica em 10 metros:** o planejamento de rolo gera uma folha contÃ­nua por material. Uma arte permanece inteira. A largura de cada mÃ¡quina continua valendo.
- **EspaÃ§o entre artes em centÃ­metros:** o operador escolhe a folga do lote e recalcula para comparar a metragem. O valor inicial continua sendo 5 cm. O mÃ­nimo Ã© 1 cm, condicionado ao espaÃ§o necessÃ¡rio para escrever o nome completo.
- **PreferÃªncia por mÃ¡quina:** â€œSalvar espaÃ§o para esta mÃ¡quinaâ€ guarda a folga para os prÃ³ximos lotes, inclusive os automÃ¡ticos. A configuraÃ§Ã£o sÃ³ muda ao clicar nesse botÃ£o.
- **Imagem, seleÃ§Ã£o e nome juntos:** a lista permite marcar arquivos individualmente ou em lote. A miniatura representa a primeira pÃ¡gina; PDFs com vÃ¡rias pÃ¡ginas precisam da conferÃªncia das demais pÃ¡ginas no original.
- **Mapa do encaixe:** as peÃ§as sÃ£o mostradas nas posiÃ§Ãµes e proporÃ§Ãµes do plano, com zoom e navegaÃ§Ã£o. Selecionar uma peÃ§a identifica seu arquivo, pÃ¡gina e cÃ³pia.
- **PossÃ­veis defeitos visÃ­veis:** resoluÃ§Ã£o baixa, resoluÃ§Ã£o nÃ£o verificada, diferenÃ§a entre a medida do nome e a saÃ­da, problemas de leitura e peÃ§as que nÃ£o cabem recebem avisos. SÃ£o verificaÃ§Ãµes tÃ©cnicas; erros de conteÃºdo, cor ou grafia dentro da arte ainda exigem conferÃªncia visual.
- **ConferÃªncia por pÃ¡gina:** PDFs com vÃ¡rias pÃ¡ginas deixam de reutilizar a medida da primeira para todas as demais. O original Ã© tratado como uma unidade: se uma pÃ¡gina ou cÃ³pia nÃ£o puder entrar, o arquivo nÃ£o Ã© considerado concluÃ­do parcialmente.
- **PendÃªncias preservadas:** arquivamento considera as peÃ§as que realmente entraram nas posiÃ§Ãµes produzidas. Arquivos que nÃ£o cabem permanecem na entrada; recusas de leitura seguem o fluxo de `_conferir`, com motivo.
- **PrÃ©via vinculada Ã  seleÃ§Ã£o:** trocar a folga ou os arquivos exige novo cÃ¡lculo. Uma arte alterada depois da prÃ©via exige nova conferÃªncia antes de montar.
- **GravaÃ§Ã£o do lote inteiro:** PDFs e fichas sÃ£o preparados e relidos antes da publicaÃ§Ã£o. Uma falha de gravaÃ§Ã£o desfaz as saÃ­das novas do lote; homÃ´nimos anteriores sÃ£o preservados.
- **Retomada sem remontar:** se um original estiver aberto e nÃ£o puder ser arquivado, o lote publicado fica registrado. A prÃ³xima passada tenta arquivar novamente e nÃ£o produz outro PDF daquela mesma versÃ£o. Uma publicaÃ§Ã£o interrompida e incompleta recebe um aviso de revisÃ£o.
- **Trava compartilhada:** montagem manual, conversÃ£o pela tela e monitor usam a mesma trava por pasta.
- **ConversÃ£o conferida:** na montagem automÃ¡tica, EPS/PSD sÃ£o preparados numa pasta temporÃ¡ria; o original sÃ³ Ã© arquivado depois da publicaÃ§Ã£o confirmada do lote. Falha de publicaÃ§Ã£o remove a derivada temporÃ¡ria e conserva o original. Falha de arquivamento nÃ£o repete a conversÃ£o nem a impressÃ£o. Adobe indisponÃ­vel deixa o original pendente na entrada. As opÃ§Ãµes de qualidade do Adobe permanecem as anteriores.
- **Montagem manual sob controle:** a montagem automÃ¡tica do vigia inicia pausada. Um botÃ£o na tela alterna pausa e ativaÃ§Ã£o e grava a preferÃªncia. O vigia segue cuidando de OS, cadernos e avisos de fila; as artes sÃ³ sÃ£o montadas depois de clicar em â€œMontar e salvar o PDFâ€.
- **Largura por mÃ¡quina:** cada aba permite escolher a largura mÃ¡xima em centÃ­metros, limitada pelo cadastro daquela impressora. A prÃ©via, o encaixe, o aproveitamento e o PDF usam esse limite. A combinaÃ§Ã£o ainda precisa comportar as artes, a folga e a identificaÃ§Ã£o completa.
- **UJV 100 inclu?da:** h? uma aba pr?pria com largura m?xima de montagem de 1,52 m, conforme o rolo maior informado. A entrada e a sa?da usam os nomes curtos `UJV 100` e `SAIDA UJV 100`; o identificador interno `UJV 100 UNY CV` permanece para preservar o roteamento da impressora.
- **PrÃ©via mais larga:** aumentei a Ã¡rea lateral do mapa do encaixe para facilitar a leitura.

## Regras de tamanho e qualidade

A primeira medida do nome continua prevalecendo sobre uma medida posterior de acrÃ©scimo. SÃ£o preservadas as unidades M, CM e MM e as abreviaÃ§Ãµes cadastradas. Sem unidade, a regra existente continua sendo centÃ­metros.

O maior lado indicado no nome permanece como Ã¢ncora. O outro lado acompanha a proporÃ§Ã£o da arte, com os limites de divergÃªncia existentes; o sistema nÃ£o estica um eixo para forÃ§ar encaixe. DimensÃµes invÃ¡lidas e quantidade explicitamente zero precisam de revisÃ£o.

Na tela de envio, a passagem dos aliases foi corrigida: `3,20x10,00MTS` representa 3,20 Ã— 10 m e `58x60XM` representa 58 Ã— 60 cm. Uma unidade desconhecida nÃ£o pode mais fazer o leitor cortar dÃ­gitos: `600x400PIX` fica sem medida reconhecida, em vez de virar 600 Ã— 40 cm. TambÃ©m nÃ£o se troca uma primeira medida invÃ¡lida por uma segunda aparentemente vÃ¡lida.

As miniaturas sÃ£o recursos da tela. A montagem continua usando as pÃ¡ginas e imagens recebidas, sem recompressÃ£o de imagem na gravaÃ§Ã£o. A conversÃ£o de EPS/PSD depende do Adobe instalado e das opÃ§Ãµes existentes; os testes simulam conversores e nÃ£o certificam uma conversÃ£o no programa real. Os nomes completos das peÃ§as precisam caber na faixa reservada: uma escolha de espaÃ§amento incompatÃ­vel deve ser sinalizada, em vez de cortar o nome silenciosamente. O cabeÃ§alho conserva sua Ã¡rea prÃ³pria e ajusta a letra para aparecer inteiro nas folhas estreitas.

## Economia que pode ser conferida

A prÃ©via informa a metragem resultante e o uso estimado da largura disponÃ­vel da mÃ¡quina. Isso ajuda a comparar o mesmo lote com 5 cm, 3 cm e 1 cm de folga, quando os nomes comportarem esse espaÃ§o.

O percentual calculado pela largura aparada do PDF pode esconder sobra de bobina. Por exemplo, uma montagem antiga de 1,728 Ã— 6,18 m ocupava cerca de 98% do PDF, mas aproximadamente 53% de uma bobina de 3,20 m ao longo desse avanÃ§o. Por isso a estimativa pela largura da mÃ¡quina merece aparecer junto. O consumo real depende da bobina carregada e do avanÃ§o efetivo da impressora.

NÃ£o hÃ¡ uma economia percentual garantida: ela varia com as medidas, quantidades, restriÃ§Ãµes de giro e folga de cada lote. A comparaÃ§Ã£o deve usar o mesmo conjunto de artes.

## PrÃ³ximas melhorias gerais, propostas para uma etapa separada

| Prioridade | Melhoria | ReduÃ§Ã£o de esforÃ§o ou risco |
|---|---|---|
| 1 | Copiar para um arquivo temporÃ¡rio e publicar sÃ³ o arquivo completo na fila das impressoras | Evita que uma cÃ³pia grande pausada seja confundida com um arquivo pronto; protege homÃ´nimos que apareÃ§am durante a cÃ³pia. |
| 2 | Envio em segundo plano com progresso por arquivo e resumo do lote | MantÃ©m a janela utilizÃ¡vel durante cÃ³pias grandes e deixa claro qual arquivo falhou. |
| 3 | Painel Ãºnico com fila, falhas, Ãºltimo sinal e versÃ£o de cada posto | Reduz a necessidade de abrir pastas ou visitar o computador da impressora para descobrir o motivo de um atraso. |
| 4 | Retomada persistente por etapa de entrega | Se uma movimentaÃ§Ã£o falhar depois da entrega ao RIP, repete sÃ³ a etapa pendente, evitando entregar o mesmo trabalho novamente. ReimpressÃµes intencionais continuam possÃ­veis. |
| 5 | Aviso de clientes misturados e identificaÃ§Ã£o do cliente por peÃ§a | MantÃ©m o aproveitamento coletivo, mas evita atribuir o lote todo a um Ãºnico cliente por causa do nome final. |
| 6 | Acompanhar a ficha da montagem atÃ© o registro de produÃ§Ã£o | Permite localizar quais artes, pÃ¡ginas e cÃ³pias foram incluÃ­das em cada PDF entregue. |
| 7 | Confirmar que um arquivo terminou de chegar pela mudanÃ§a de tamanho/data entre observaÃ§Ãµes | Uma data antiga preservada pela cÃ³pia nÃ£o basta para provar que a transferÃªncia terminou. |
| 8 | Ampliar formatos de medida escritos no nome, com exemplos e testes | Escritas como `50cm x 70cm`, `1m x 2m` e o separador `Ã—` podem receber suporte explÃ­cito, sem adivinhar unidade nem alterar medidas existentes. |

Decorflex continua sugerindo DOCAN R5200, com troca manual disponÃ­vel. AlteraÃ§Ãµes nos agentes instalados nos computadores das impressoras, tarefas agendadas e perfis de RIP precisam de validaÃ§Ã£o prÃ³pria antes de instalaÃ§Ã£o.

O cÃ¡lculo por mÂ² da DOCAN R5200 foi acrescentado Ã s telas de envio/montagem, fichas e documentos. A referÃªncia e os locais alterados estÃ£o em [Tempo de impressÃ£o DOCAN R5200](TEMPO_IMPRESSAO_DOCAN_R5200.md).

## ValidaÃ§Ã£o

ValidaÃ§Ã£o anterior: **697 testes passaram** para a revisÃ£o de montagem e o cÃ¡lculo DOCAN antes destes Ãºltimos controles de vigia, largura e UJV. As alteraÃ§Ãµes finais de controles ainda precisam dessa rodada automatizada de validaÃ§Ã£o. Os lotes reais nÃ£o foram montados.

## Onde encontrar os controles

Reabra o sistema e entre em **Montar arte para impressÃ£o**, na aba DOCAN R5200 ou SWJ320A. Acima da lista ficam **Marcar todos**, **Limpar seleÃ§Ã£o**, **EspaÃ§o entre artes (cm)** e **Salvar espaÃ§o para esta mÃ¡quina**. A lista reÃºne imagem, nome, marcaÃ§Ã£o, medidas e possÃ­veis defeitos. Ã€ direita fica o mapa; abaixo, **Recalcular seleÃ§Ã£o** e **Montar e salvar o PDF**.

Avisos tÃ©cnicos permitem revisar e decidir; arquivos recusados ficam fora do plano. Uma miniatura nÃ£o Ã© usada como arquivo de impressÃ£o. Para PDF com vÃ¡rias pÃ¡ginas, a miniatura Ã© da primeira; o mapa identifica as pÃ¡ginas e cÃ³pias individualmente.

