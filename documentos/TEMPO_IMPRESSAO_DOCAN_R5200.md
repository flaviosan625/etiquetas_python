# Tempo estimado de impressão — DOCAN R5200

Implementado em 09/10/2026 a partir de `estimativa_tempo_impressao_passadas.pdf`, fornecido pelo usuário. O documento foi usado como referência de medição; as mudanças seguem o pedido do usuário.

## Conferência da conta

Área: **4,85 × 27,251 = 132,16735 m²**. Com 30% impressos em 47 minutos, o tempo projetado para o arquivo inteiro em 8 passadas é **156,6667 minutos = 2h36min40s**.

Taxa de referência: **1,1853658764 min/m²**, aproximadamente **1min11s/m²**, ou **50,62 m²/h**. O sistema usa a precisão da medição, em vez de multiplicar o valor arredondado de 1,19 min/m² da tabela.

`tempo em minutos = área em m² × (47 ÷ 0,30) ÷ (4,85 × 27,251) × passadas ÷ 8`

| Passadas | Min/m² | m²/h | Tempo para 100 m² |
| --- | ---: | ---: | ---: |
| 2 | 0,2963 | 202,47 | 29min38s |
| 4 | 0,5927 | 101,23 | 59min16s |
| 5 | 0,7409 | 80,99 | 1h14min05s |
| 6 | 0,8890 | 67,49 | 1h28min54s |
| 8 | 1,1854 | 50,62 | 1h58min32s |
| 10 | 1,4817 | 40,49 | 2h28min10s |
| 12 | 1,7780 | 33,74 | 2h57min48s |
| 16 | 2,3707 | 25,31 | 3h57min04s |
| 24 | 3,5561 | 16,87 | 5h55min37s |
| 32 | 4,7415 | 12,65 | 7h54min09s |

As outras passadas são projeções proporcionais, conforme a tabela fornecida. Não são medições adicionais. A conta é uma estimativa e exclui preparação, tempo de RIP, limpeza e pausas. O PDF informa que o perfil real pode produzir variação de aproximadamente 10–20%; o sistema não acrescenta essa margem automaticamente como se fosse tempo medido.

## Onde mudou

- **Enviar para impressão:** seletor “Estimativa DOCAN — passadas”. O padrão é “8 (referência)”; escolher outro valor registra o modo usado para planejamento. O rodapé estima o tempo dos arquivos DOCAN marcados, por material. Arquivos de outras impressoras não recebem a taxa da DOCAN.
- **Montar arte para impressão → DOCAN R5200:** seletor de passadas no quadro inferior. Depois de recalcular, a previsão aparece por material. A área usada inclui espaços e cabeçalho da folha completa. A ficha JSON salva área, passadas, taxa, duração e origem da estimativa junto do PDF, sem acrescentar texto sobre a arte.
- **Documento Enviados:** duração prevista em cada envio DOCAN e subtotal dos tempos DOCAN por material. Cópias e reenvios entram na conta. A estimativa de cada novo envio fica gravada no histórico para reprodução posterior.
- **Relatório diário:** duração estimada dos trabalhos DOCAN, separada do tempo real informado pela máquina, e subtotal por material. Quando o registro de entrega não informa o perfil, aparece “8 passadas (referência)”. As escolhas feitas na tela do computador principal não são transferidas automaticamente para os registros dos agentes já instalados nas impressoras; o relatório não afirma conhecer esse perfil.
- **OS de Decorflex:** referência de tempo da DOCAN R5200 no subtotal do material. Usa área das peças; não conhece ainda o encaixe definitivo nem o perfil que será escolhido no RIP. Uma taxa “Min/m²” cadastrada pelo operador continua prevalecendo. Lona e adesivo genéricos conservam os destinos e as regras existentes.

Escolher passadas nessas telas modifica a estimativa de planejamento. O perfil de impressão continua sendo configurado no RIP pelo operador. Medidas, conteúdo da arte e qualidade de exportação não são alterados por esse cálculo.

## Exemplos para revisão

- [Documento Enviados com dois envios DOCAN e um SWJ](EXEMPLO_ENVIADOS_DOCAN.pdf).
- [OS de Decorflex com referência da DOCAN](EXEMPLO_OS_DECORFLEX.pdf).

Os exemplos usam dados fictícios locais. Não foram enviados arquivos às impressoras nem alterados documentos de clientes.

Validação conjunta: **697 testes passaram**, incluindo reprodução dos tempos da tabela, cópias/reenvios, documentos com várias páginas, limites do texto e preservação das regras existentes. Exemplos revisados visualmente.
