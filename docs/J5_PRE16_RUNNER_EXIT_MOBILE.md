# J5/PRE16 #393 — estados de encerramento de runner PAPER no celular

## Finalidade
A RUNNER3 #391 introduziu alocação `tranche_step=0` para o residual de posições fictícias após todas as parciais. O painel J5/PRE14 não podia inferir essas saídas e, depois de algum fill do runner, apresentava incorretamente “aguardando preenchimento das parciais”. Esta etapa classifica o ciclo real **do diário local PAPER**, não o da corretora.

## Fonte e classificação
`scripts.inspect_paper_positions._paper_runner_readiness` recebe apenas `PaperPositionInspection` validada por SQLite `mode=ro`, sem leitor/writer de mercado. Se não existir exit passo zero, estados legados permanecem: runner inexistente, tranches pendentes, runner confirmado sem stop, ou reconciliação de ordens parciais.

Quando existir ao menos uma ordem do runner (`tranche_step=0`), os novos estados são:
- `RUNNER_EXIT_PENDING_RECONCILIATION`: qualquer saldo reservado ou ordem runner que exija reconciliação (`PENDING/ACKNOWLEDGED/UNKNOWN/PARTIALLY_FILLED`), mesmo que já exista preenchimento parcial.
- `RUNNER_EXIT_PARTIALLY_FILLED`: parte do runner confirmada por FILL PAPER, sem pedido pendente após cancelamento/terminal e ainda existe saldo.
- `RUNNER_CLOSED_PAPER_ONLY`: todas as unidades residuais preenchidas no diário e saldo da posição igual a zero.
- `RUNNER_EXIT_CANCELLED_REMAINDER`: tentativa cancelada/recusada sem FILL e saldo runner liberado, não encerrar.

O contrato JSON `paper_positions_snapshot_v1` mantém campos existentes e acrescenta `runner_filled_units`, `runner_reserved_unfilled_units` e `runner_unallocated_units` como strings Decimal. São **unidades do instrumento**, sem conversão/soma financeira. O HTML PT-BR acrescenta o estado e as três quantidades nos cartões, reutilizando a coluna “Runner PAPER” e a navegação horizontal acessível. Não altera CSP, endpoints, schema SQLite, credenciais ou writer.

A apresentação de observação RUNNER2 antiga é recusada após alteração do checkpoint AUTO4: um trailing sintético anterior não pode ser interpretado como stop ainda ativo ou ordem real. Todas as telas preservam `native_stop_verified=false`, `trailing_stop_active=false`, `orders_sent=false`, `live_trading_authorized=false` e `financial_pnl_available=false`.

## Verificação
`tests/test_paper_runner_exit_mobile.py` cobre PENDING/UNKNOWN/CANCEL/FILL2/CANCEL/FILL4, runner zerado, configurações sem residual, LONG/SHORT, rejeição de replay antigo, SQLite apenas leitura, no-network, CSP e texto. Exigir CI docs/Linux, Windows/offline e Chrome/PAPER, revisão do head SHA e merge sem produção. Nenhuma execução na VPS/ordem/testnet/live; J1 #2/#319 segue pendente de owner-run privado adiado pelo Product Owner.
