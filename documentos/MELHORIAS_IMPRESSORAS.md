# Melhorias no fluxo de impressão — 08/10/2026

Prioridade informada pelo usuário: diminuir o esforço para selecionar arquivos e enviá-los para cada máquina. A revisão foi feita no código local; a instalação que está rodando em cada PC ainda precisa ser conferida.

## Implementado no projeto

- **Atalho na tela principal:** “Enviar para impressão” voltou à área ATALHOS para dar acesso aos controles de lote. Esse acesso estava desativado.
- **Marcar nunca enviados:** seleciona os arquivos inéditos de todos os grupos em um clique. Preserva reimpressões marcadas manualmente. Fica indisponível quando o histórico está ilegível, pois nesse caso não há como identificar inéditos com segurança.
- **Máquina para os marcados:** permite escolher a impressora uma vez para o lote selecionado. Mantém as previsões de giro e encaixe e a troca individual de impressora.
- **Limpar seleção:** desmarca o lote em um clique.
- **Atualização dos totais por lote:** evita recalcular a lista inteira a cada item marcado em uma ação coletiva.
- **Correção do indicador do RIP:** a variável local de cores impedia a pintura do estado; a atualização periódica também usava variáveis que não existiam naquele método. Os avisos de máquina e de fila passam a ser renovados junto com o indicador.
- **Decorflex → DOCAN R5200:** essa máquina passa a ser sugerida pelo material, inclusive quando aparece “LONA DECORFLEX” no nome. A escolha continua editável.
- **Seleção visual:** cada arquivo reúne caixa de seleção, miniatura e nome no mesmo controle. Clicar na imagem ou no nome marca aquela arte. A prévia é da primeira página/imagem, carregada em segundo plano, mantendo a seleção e os controles de lote.
- **Prévia do arquivo atual:** o cache considera pasta, tamanho e data de alteração. Arquivo modificado durante o carregamento não recebe uma imagem antiga. Arquivos só na nuvem, muito grandes ou ilegíveis mostram uma mensagem no lugar da prévia; a lista não dispara downloads apenas para gerar imagens.

Uso: reabrir o sistema, ir a ATALHOS → “Enviar para impressão”, escolher a pasta, clicar em “Marcar nunca enviados”, ajustar as máquinas individualmente ou por lote e clicar em “Enviar”. Os novos controles ficam abaixo do indicador do RIP e acima da lista de arquivos. A conferência anterior à cópia permanece.

As regras existentes de medida, giro, montagem e cópias permanecem; a nova sugestão para Decorflex é a alteração de destino solicitada pelo usuário. As DOCAN continuam recebendo a arte sem giro automático. Nenhuma instalação, tarefa agendada ou configuração das impressoras foi alterada.

## Próximas prioridades

| Prioridade | Melhoria proposta | Evidência no código | Benefício no trabalho diário |
|---|---|---|---|
| 1 | Enviar arquivos em segundo plano, com progresso por arquivo e resumo do lote | `gui.py`, método `_executar_envio`: cópia, miniaturas e PDF são executados na mesma chamada da interface | Permite acompanhar arquivos grandes sem a janela deixar de responder. O envio permanece dependente da conferência já existente. |
| 2 | Mostrar as quatro máquinas na tela de envio, com fila, erros e última entrega | A tela chama `estado_do_rip()` para o posto padrão; os agentes já conhecem os postos RIP e SAi | Evita abrir outras telas para descobrir se o destino escolhido está recebendo. |
| 3 | Levar falhas por arquivo e problemas do registro de impressão ao painel central | `registrar_sinal_de_vida` considera `erro` da máquina, mas não a lista `falharam`; `_cuidar_do_ripado` deixa o diagnóstico das tarefas auxiliares no log local | Mostra o motivo de um arquivo ficar esperando, mesmo com o vigia ativo, reduzindo visitas ao PC da máquina. |
| 4 | Retomar uma entrega incompleta sem entregar novamente ao RIP | `_processar_arquivo_da_fila`: entrega na hot folder, registra e só depois move para Enviados | Se a última movimentação falhar, o arquivo permanece na fila e pode ser entregue novamente. Um controle persistente por tentativa permitiria repetir apenas a etapa pendente, mantendo reimpressões intencionais. |
| 5 | Conferir automaticamente a configuração de entrada e a versão instalada em cada posto | O cadastro das hot folders está em `MAQUINAS`; há diagnósticos e atualizadores separados, mas o sinal de vida não informa a versão instalada | Descobre uma configuração divergente ou uma atualização incompleta antes de atrasar o lote. A leitura deve usar a configuração efetiva do RIP e não alterar seus perfis. |

## Evoluções após as prioridades

- **Pendências por cliente:** reunir os registros já existentes em “na fila”, “entregue ao RIP” e, nas DOCAN, “impressão confirmada”. O sistema já lê provas do BYHX; as Mimaki ainda não têm essa confirmação integrada. Ausência de prova não significa que a peça não foi impressa.
- **Atalho para o pedido atual:** abrir a tela de envio diretamente no pedido em trabalho, preservando a possibilidade de trocar a pasta. Reduz a procura repetida de diretórios.
- **Preferência explícita de máquina por material ou pedido:** só vale se o operador optar por guardar essa escolha. Materiais novos seguem a sugestão atual e a máquina continua editável.

## Critérios para as próximas mudanças

- A tela continua abrindo com os arquivos desmarcados.
- A escolha da máquina continua nas mãos do operador.
- A conferência e os bloqueios de conflitos permanecem antes da cópia.
- Uma tentativa interrompida e uma reimpressão intencional precisam ter identidades diferentes.
- Testes usam arquivos e pastas isolados, sem enviar trabalhos às impressoras reais.
- A melhoria de retomada precisa ser testada com falha depois da entrega e reinício do processo; apenas um bloqueio por nome de arquivo não resolve o caso.

As primeiras mudanças estão em `gui.py`, com regressões cobertas em `tests/test_gui_envio_lote.py`. A seleção em lote, a manutenção da conferência, o envio, o vigia, o fluxo ponta a ponta e o tema foram verificados: **193 testes passaram**. Dois testes antigos de recuperação passaram a usar datas dentro do prazo de guarda, sem mudar os 20 dias de retenção do sistema.

A evolução com Decorflex e prévias também foi testada em widgets reais de uma janela oculta, sem acessar produção: seleção pelo controle com imagem e nome, manutenção da conferência e rejeição de imagens de arquivos alterados. A revisão visual pelo operador e a validação nos computadores das impressoras continuam necessárias antes de afirmar que a melhoria está em operação nesses postos.
