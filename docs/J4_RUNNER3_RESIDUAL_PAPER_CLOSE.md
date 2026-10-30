# J4/RUNNER3 #391 — encerramento do residual somente em PAPER

## Problema resolvido
O AUTO4 mantinha uma reserva irredutível do runner: `tranche_step=1..n` cobria apenas as parciais e `unreserved >= runner_floor` impedia a alocação final. O novo `tranche_step=0` representa **exclusivamente o saldo residual do plano PAPER**, jamais uma tranche adicional. Não muda versão/esquema do SQLite nem altera os valores e a semântica de tranches 1..n.

## Invariantes
- Runner só é elegível quando todas as tranches planejadas têm fills completos, nenhuma reserva nem ordem parcial `UNKNOWN/PENDING/ACK/PARTIALLY_FILLED` sem reconciliação. O residual configurado deve ser positivo.
- Cada saída RUNNER3 é `REDUCE_ONLY`, mesma venue/symbol/side, contra a posição e respeitando passo Decimal, saldo confirmado, saldo não reservado e quota residual. `runner_filled_units + runner_reserved_unfilled_units <= runner_floor_units` é obrigatória mesmo após restart.
- `PENDING` e `UNKNOWN` retêm reserva; `CANCELLED` libera somente o não preenchido; `PARTIALLY_FILLED` reduz saldo. Sob `BEGIN IMMEDIATE` o AUTO4 verifica a posição e bloqueia reservas concorrentes, IDs em conflito e overfill. Os demais recibos e histórico permanecem íntegros.
- O `PaperPositionBalance` expõe `runner_filled_units`, `runner_reserved_unfilled_units` e `runner_unallocated_units` somente como quantidades de PAPER. `confirmed_remaining_units` e `filled_exit_units` continuam conservando a soma da posição inicial.
- Uma reserva runner altera o checkpoint da posição. Por isso, RUNNER2 ancorado na posição anterior **falha ao recuperar** e nunca prepara uma segunda ordem com base no mesmo gatilho. A auditoria da nova posição é responsabilidade do AUTO4.

## Preparação somente leitura
`preview_paper_runner_close(runner_path, position_path, position_id, policy=..., as_of_ms=...)` lê o journal RUNNER2 pela função já auditada, exige `TRIGGERED_HYPOTHETICAL_ONLY`, reabre a posição antes e depois, verifica parciais/residual sem UNKNOWN e gera um `PaperOrderIntent` sintético `REDUCE_ONLY` de ID determinístico para mesmo digest+cutoff. O preview **não grava** em nenhum banco nem envia ou agenda ordens. A reserva PAPER, caso usada por pesquisa, é uma segunda ação explícita com `SQLitePaperPositionJournal.reserve_exit(position_id, 0, intent, as_of_ms=...)`.

Os bancos de posição e trailing são diferentes e não oferecem snapshot atômico conjunto. A reconsulta detecta drift observável, mas não elimina corrida entre o fim da leitura e eventual reserva. A política e timestamps não provêm da corretora. Depois de uma reserva, eventuais cancelamentos ou preenchimentos parciais podem ser reconciliados ou substituídos diretamente no AUTO4, jamais fabricando segundo gatilho.

## Testes, gates e não-objetivos
`tests/test_paper_runner_close.py`: LONG/SHORT; 100→50→20→6→0; idempotência após restart; reserva concorrente/duplicada; UNKNOWN, cancel, partial fill e overfill; recusa de tranches incompletas; corrupção e stale; função read-only e no-network. CIs Linux/docs, Windows/offline e Chrome/PAPER no SHA revisado são obrigatórias antes de merge.

J1/Top50 owner-run da VPS continua adiado pelo proprietário. Sem dados de mercado novos, ordens de exchange, stop nativo, negociação real, testnet, rede, credenciais, migração, deploy ou custo adicional. Não comprova segurança de 50x ou retorno líquido. J4 #5 e J6 #7 permanecem sem homologação.
