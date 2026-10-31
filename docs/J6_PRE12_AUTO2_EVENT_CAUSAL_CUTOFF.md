# J6/PRE12 — corte temporal de eventos AUTO2

## Lacuna e correção
Com PRE11, `inspect_local_paper_operator_status(..., decision_at_ms=T)` já rejeitava cursor e alteração de pausa após T; porém o verificador de intenções AUTO2 retornava a contagem do snapshot mais recente, inclusive FILL posterior. Isso podia transformar um OPEN pendente em "zero pendências" retroativamente. PRE12 adiciona argumento opcional `decision_at_ms` ao leitor compartilhado `SQLitePaperOrderJournal._pending_open_from_connection` e compara T com o `intent.created_at_ms` e `snapshot.as_of_ms` de cada linha validada por `_checked_entry`. Essa verificação precede o filtro `effect is OPEN`; REDUCE_ONLY também não pode ocultar evento posterior. Nada é excluído nem retroprojetado: presença de futuro gera `DataValidationError`.

## Contratos existentes mantidos
- Sem cutoff, `_pending_open_from_connection` mantém tipo, contadores, semântica AUTO6/risco e journal.
- `paper_operator_status` passa cutoff na mesma conexão read-only em que confere cursor e pausa.
- `paper_recovery_status` já encaminha cutoff desde PRE11; agora um OPEN/REDUCE_ONLY futuro causa `UNVERIFIED/paper_journal_unverified`, jamais um falso flat/permite OPEN.
- `scripts.demo_full_offline_paper_lifecycle` acrescenta checkpoints sanitizados `future_open_fill_rejected_at_prior_cutoff` e `future_runner_fill_rejected_at_prior_cutoff`. O fluxo causal J2→AUTO2→AUTO4→parciais→RUNNER2→PRE8 e suas fixtures explícitas permanecem.

## Testes e limitações
Regressões em SQLite temporário para FILL de OPEN no instante T+1, REDUCE_ONLY com FILL T+1 ou intenção T+2, cutoff T/T+1, pendência desconhecida, recuperação UNVERIFIED, bytes preservados, no-network e integração PAPER determinística. CI Linux/docs, Windows/offline e Chrome/PAPER verde no SHA final antes do merge. Não é snapshot histórico reproduzido, não garante atomismo entre bancos, estado real da exchange, stop nativo, ganhos ou ativação de trading. Sem VPS/J1, ordens, chaves, HTTP, testnet/live, deploy, migrations e custo extra.