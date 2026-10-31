# J6/PRE10 — matriz causal de interrupções AUTO2/AUTO4/runner em PAPER

## Escopo
`scripts.demo_full_offline_paper_lifecycle` permanece a demonstração sintética existente da abertura causal J2 com cursor durável AUTO2, confirmação explicitamente injetada por fixture AUTO4, parciais, runner RUNNER2 e PRE8. PRE10 acrescenta **somente observações read-only** com `audit_paper_open_health`, `inspect_local_paper_operator_status` e `audit_selected_paper_portfolio_incidents`, retornadas como `interruption_checks` no JSON legado. A demo cria um AUTO4 divergente apenas num arquivo SQLite temporário separado, sem tocar o AUTO4 correto.

## Checagens exatas
1. `pending_open_without_fill`: AUTO8 retorna `no_filled_open_or_position_requires_protection`, porém operador confirma PENDING; AUTO6 é requisito independente e não se autoriza nova OPEN.
2. `filled_open_without_auto4_position`: `paper_open_unprotected`, nova OPEN negada.
3. `isolated_auto4_mismatched_fill_identity`: `paper_open_health_unknown` e PRE8 `INVALID_OR_INCONSISTENT_SELECTED_JOURNALS` / `BLOCKED`, nenhuma posição aceita no lote; arquivo divergente descartável.
4. `auto4_open_confirmed_no_native_stop`: `paper_open_unverified_protection`, incidente `PARTIALS_INCOMPLETE` / `REVIEW`.
5. `partial_exits_leave_runner`: risco de runner sem stop, `RUNNER_UNPROTECTED` / `REVIEW`.
6. `pending_runner_after_restart`: `paper_open_health_unknown`, incidente `RUNNER_EXIT_PENDING_RECONCILIATION` / `REVIEW`; zero duplicações.
7. `fully_flat_after_runner_fill`: `all_paper_positions_fully_flat_hypothetical_only`, `RUNNER_CLOSED_PAPER_ONLY` / `INFO`. Permissão PAPER hipotética não implica autorização de trading real.

Em todos os checkpoints, divergência de saúde/gravidade esperada levanta `DataValidationError` sem emitir JSON de sucesso. A matriz não enumera arquivos do usuário, só trabalha no `TemporaryDirectory` existente. Saída somente códigos constantes e booleanos; sem symbols, IDs, paths, preços, hashes privados, credenciais, PnL ou endpoints.

## Testes e limites
`tests/test_full_offline_paper_lifecycle.py` verifica checkpoints exatos, sem rede, repetibilidade, curso 2→1.88→0.12→0, auditor forjado, ausência de FILL implícito e flags negativas. CI Linux/docs, Windows/offline e Chrome/PAPER deve ser SUCCESS no SHA revisado. Não existe atomicidade interbancos, reconciliação da corretora, stop nativo, homologação de dados ou trade live/testnet. J1 #319 permanece externa. Custo adicional R$ 0.
