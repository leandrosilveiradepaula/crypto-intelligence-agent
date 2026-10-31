# J6/PRE11 — Cutoff causal em recuperação e runner PAPER

## Risco demonstrável
Um status durável lido no tempo atual não necessariamente existia em um instante UTC anterior escolhido pelo usuário. PRE11 impede que o leitor de recuperação (AUTO2/operador) aceite cursor de replay ou transição de pause posteriores a `decision_at_ms`. Impede que a função do runner devolva uma reserva ou FILL ocorrido depois de `as_of_ms`. O auditor de incidentes com RUNNER2 e cutoff explícito não classifica como conhecido o estado futuro do AUTO4.

## Contratos aditivos e comportamentos
- `inspect_local_paper_operator_status(..., decision_at_ms=None)`: cutoff opcional e validado. No mesmo snapshot SQLite verifica `cursor.seal.decision_at_ms` e `kill_switch.changed_at_ms`, ambos limitados pelo cutoff. Sem cutoff, comportamento/DTO existentes mantidos.
- `inspect_local_paper_recovery_status(..., decision_at_ms=...)` propaga o instante para ambas as leituras de operador, além do auditor de saúde já temporal. Rejeição temporal resulta em `UNVERIFIED/paper_journal_unverified`, `new_open_authorized=False`.
- `step_durable_paper_runner_close(..., as_of_ms=...)` verifica policy tipada e `AUTO4.balance.as_of_ms <= cutoff` **antes** de interpretar qualquer runner PENDING/FILLED existente. Falha lança `DataValidationError` e não reserva.
- `audit_paper_runner_incident(..., runner_journal_path, policy, as_of_ms)` devolve `INSUFFICIENT_EVIDENCE/BLOCKED`, sem balances retrospectivos, quando `AUTO4.as_of_ms > cutoff`. Sem RUNNER2+cutoff, o observador continua descritivo, sem claim temporal.

## Validação e limites
Testar cutoff anterior/igual/posterior em cursor, pausa, runner pendente e fechado, auditor com ramo prévio de classificador, bytes de diários invariantes sob leitura, política inválida, sem rede e flags de live falsas. Esses contratos **não reconstroem historicamente** uma transação anterior após escritura atual nem prometem snapshot atômico entre SQLite, ordem/fill de venue, proteção nativa ou PnL. Um dado do futuro bloqueia o diagnóstico em vez de fingir regressão temporal. CI docs/Linux, Windows/offline, Chrome/PAPER e revisão no SHA exato. J6 #7 continua aberta e J1 #319 depende de prova privada; nenhuma coleta, VPS, trading, testnet/live, migration, deploy ou gasto.
