# J4/RUNNER1 #383 — trailing de runner residual PAPER, sem ordens

Após a execução **simulada** de parciais, o componente `paper_runner_trailing.py` monitora o restante de uma posição do diário `SQLitePaperPositionJournal` sem escrever no banco, emitir intenção de ordem ou supor stop nativo.

## Contrato
- Entrada: `PaperPositionBalance` derivado do diário de posição PAPER, lista limitada de observações tipadas `PaperRunnerMark` (preço **mark** fictício e instante UTC), `PaperRunnerTrailPolicy` com ativação e distância em bps exatos e limites de intervalos/staleness, `as_of_ms` explícito.
- Gatilho só pode ser monitorado quando todas as tranches estão preenchidas, nenhuma quantidade está reservada, nenhum pedido pendente/UNKNOWN exige reconciliação, e o saldo remanescente confirmado corresponde exatamente ao runner floor maior que zero. Isso inclui o exemplo de `100→50→20→6` com percentuais REMAINING_BALANCE 50/60/70.
- LONG: após uma observação atingir a ativação versus o primeiro preço mark da **série fornecida**, o máximo favorável ratcheteia o nível do stop para cima. SHORT: mínimo favorável e stop que apenas desce. O **stop anterior** é testado antes da atualização no tick atual, evitando usar preço futuro no gatilho do passado. Quando o mark observado cruza o nível já ativo, emitir `TRIGGERED_HYPOTHETICAL_ONLY`; **não** inferir preço de fill, PnL ou presença de stop na corretora.
- Estados possíveis: `WAITING_FOR_CONFIRMED_RUNNER`, `NOT_ACTIVATED`, `TRACKING` e `TRIGGERED_HYPOTHETICAL_ONLY`. `last_stop_mark_quote` é observável apenas em memória, nunca exposto no relatório público. O relatório `sanitized_report()` emite estado/contagem/digest, sem símbolo/posição/mark/preço/UTC.
- A série deve começar após o checkpoint da posição, respeitar ticks estritamente cronológicos, mesma identidade de ticker, validade do cutoff e os limites explícitos de intervalo. A referência inicial é **somente o primeiro mark observado**; este não é necessariamente o preço real de entrada e não deve ser usado como tal.
- Sem persistência do pico/stop, este é um **replay determinístico de pesquisa**; reinicializar com série truncada muda a referência e NÃO garante stop durável após restart. Não usar para posicionamento, execução automática, colocação de proteção real ou gestão live. Proteção real precisa do fluxo J4/J6 e autorização própria.

## Testes e aceite
`tests/test_paper_runner_trailing.py` usa `SQLitePaperPositionJournal` real de fixture com fills, reservas, runner residual 6%, LONG/SHORT, ativações, gaps, escala Decimal, cronologia, identidade, invariância de replay, no-network e DB imutável. CI docs/Linux, Windows offline e Chrome/PAPER em SHA exato; revisão e merge sem deploy.

`orders_sent=false`, `order_submission_enabled=false`, `native_stop_verified=false`, `approved_for_live_use=false`, `financial_pnl_available=false`, sem trades, conta, acesso VPS, chave ou gasto. J1 #2/#319 permanecem pendentes de owner-run, **adiado pelo proprietário**, sem interferir nesta jornada.


## Extensão RUNNER2 — durabilidade apenas da pesquisa local PAPER

O contrato da RUNNER1 continua funcional e read-only. RUNNER2 permite gravar sequência tipada de mark hipotético em um banco SQLite **novo** e separado, vinculada ao checkpoint exato de posição PAPER e à política explícita. Reiniciar e executar `load_paper_runner_journal` restaura histórico e stop hipotético anterior; reentrada de tick idêntico é idempotente, divergência falha. O gatilho terminal impede novas marcações sem declarar fill, ordem ou stop instalado. Bancos AUTO2/AUTO4/J1 não são modificados por este journal. O replay recusa períodos sem ticks ou cutoff muito distante; dados da corretora não são autenticados. Não há atomicidade de snapshots entre DB de posição e DB de trailing.
