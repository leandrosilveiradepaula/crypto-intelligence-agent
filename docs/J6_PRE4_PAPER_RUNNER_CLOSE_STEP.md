# J6/PRE4 #395 — gatilho RUNNER2 para reserva durável REDUCE_ONLY PAPER

## Escopo de automação
A função `step_durable_paper_runner_close(runner_path, position_path, position_id, policy=..., as_of_ms=...)` constitui o primeiro elo causal local entre o gatilho hipotético de trailing RUNNER2 e a reserva REDUCE_ONLY do saldo residual no mesmo ledger AUTO4. É um motor **exclusivamente PAPER**, sem API, ordem real, FILL implícito, credencial, posição de corretora, preço real, stop nativo ou execução em background.

## Estados e crash recovery
- **Sem ordem RUNNER3 existente:** `preview_paper_runner_close` exige um evento final `TRIGGERED_HYPOTHETICAL_ONLY` no diário de marcações hipotéticas, cutoff e policy válidos e checkpoint de posição inalterado. A mesma `PaperOrderIntent` determinística é reservada sob `BEGIN IMMEDIATE` do AUTO4 em `tranche_step=0`. Após commit, o inspetor RO revalida a ordem persistida como `PENDING` com eventos vazios. Retorno `reserved_paper_only` não significa envio.
- **Restart com ordem residual persistida:** a função lê **somente AUTO4**. Nunca tenta rearmar/ler RUNNER2 antigo porque este aponta a um checkpoint anterior. Se há `PENDING/ACK/UNKNOWN/PARTIALLY_FILLED`, retorna `pending_reconciliation_paper_only`, sem reenvio. Se todas as unidades foram preenchidas *no simulador*, retorna `closed_paper_only`. Se uma tentativa terminou ou foi parcialmente cancelada, retorna `terminal_manual_review_required` e não retenta.
- **Falha antes do commit:** nenhum intent confirmado. Próxima execução pode revalidar o gatilho. **Falha depois do commit:** o AUTO4 já contém a reserva e a função retorna estado durável, sem segunda reserva. Dois processos concorrentes usam lock/ID e não podem reservar o mesmo residual duas vezes.
- Corrupção, falta de gatilho, transição temporal futura, conflito de posição, overfill ou stale falham fechados. Não existe garantia de atomicidade simultânea RUNNER2/AUTO4; a origem é uma prova **local de replay fictício**, não informação autenticada da corretora.
- Qualquer `PaperRunnerCloseStepResult` mantém `orders_sent=false`, `native_stop_verified=false`, `order_submission_enabled=false`, `approved_for_live_use=false`. `sanitized_report` não revela IDs, preços, posições ou histórico de ticks.

## Evidências e gates
`tests/test_paper_runner_close_step.py` cobre primeira reserva, restart sem alterações, UNKNOWN, cancel, parcial, fill final, LONG/SHORT, concorrência, stale, checksum corrompido, ausência de trigger e no-network. CI docs/Linux, Windows/offline e Chrome/PAPER no commit exato + revisão antes de squash merge sem produção.

J6 #7 **permanece aberta**: este fluxo não contempla feed prospectivo validado, conta real, ordens executáveis, stops nativos nem homologação financeira. O owner-run J1/Top50 #2/#319 na VPS permanece adiado pelo Product Owner. Nenhum gasto adicional, migration, release, testnet ou live.
