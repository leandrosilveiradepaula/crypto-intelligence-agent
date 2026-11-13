# J4 / RUNNER-COST1 — liquidação sintética do runner com custos, sem ordem

## Lacuna e decisão

A J4 já possui duas construções diferentes e **não intercambiáveis**:

- RUNNER1–RUNNER3: acompanhamento, preview, reserva e fechamento **PAPER** em ledger, sem preço financeiro afirmado da corretora.
- J4/PRE4 `synthetic_partial_costed_replay.py`: apuração de referências e custos para parciais **explicitamente declaradas em fixtures**, e marca fictícia do runner residual, mas **não contabilizava o custo de uma declaração de encerramento do runner**.

A entrega #607 não duplica esses motores. `synthetic_runner_costed_close.py` compõe PRE4/J3 para uma última declaração de fechamento de **toda** a quantidade residual. Não há OHLC, trailing, WebSocket, REST, API, ordem real nem execução PAPER. Decisão: manter as capacidades J4 e J3 existentes como autoridades de custo e validação, sem expandir os estados AUTO4 e sem inferir preenchimento.

## Contrato de execução

Entrada tipada `SyntheticRunnerCloseMarkFill`: identificador da posição sintética, event ID fixture, quantidade positiva exata, preço fictício de saída, relógio UTC. `evaluate_synthetic_runner_costed_closure` recebe os fills parciais PRE4, taxas J3, funding de fixture e momento de corte `as_of_ms`. O mesmo recibo repetido com **ID e representação Decimal idênticos** conta uma vez. IDs diferentes, representações de payload divergentes ou colisões de IDs parciais falham fechado. Idempotência apenas *dentro do replay*; não é exactly-once persistente.

Gates:

1. Todas as parciais do plano devem estar inteiramente preenchidas antes de fechar o residual. `remaining_units == runner_floor_units > 0`; uma posição sem runner não admite essa operação.
2. `runner.filled_units == remaining_units` e `initial_units == filled_partials + runner`; saldo final é 0, sem ultrapassar limites. Uma intenção `REDUCE_ONLY`/trailing não é um fill.
3. Encerramento é estritamente posterior ao último fill parcial; não deve colidir com funding. Eventos de funding depois de fechamento não são cobrados. Todos os relógios tipados e limitados, sem lookahead.
4. Abertura (fee e slippage) já foi cobrada sobre **100% da posição inicial** pelo PRE4, portanto o evento final adiciona **somente custo de saída** do residual, reaproveitando `evaluate_synthetic_costs` J3. A direção LONG/SHORT altera bruto e sinal de funding, nunca o sinal das taxas.
5. `leverage_at_open` é imutável e **não** multiplica PnL. O campo `as_of_ms` posterior ao último fill não refaz marca nem funding de posição fechada.

## Exemplo exato

Plano 100 unidades, saídas de 50%, 60% e 70% do **saldo restante**: 50 + 30 + 14, runner = 6. Entrada hipotética 100 quote/unidade; exits 110, 120 e 90; runner fictício 130; custo de fee 10 bps + slippage 5 bps em cada lado; funding LONG hipotético 2 bps antes de segunda parcial sobre 5.000 unidades quote.

| Componente | LONG (quote referência) |
| --- | ---: |
| Bruto das parciais | +960 |
| Bruto runner encerrado | +180 |
| Custos totais de entrada | 15 |
| Custos das saídas parciais | 15,54 |
| Custo **somente saída** runner | 1,17 |
| Funding sintético | 1 |
| **Líquido hipotético com residual fechado** | **1.107,29** |

Sem custo do runner, o módulo antigo marcava 1.108,46; diferença exclusivamente de 1,17. Em SHORT com mesmas hipóteses e funding assinado por lado, bruto = −1.140, funding = −1 (crédito), fees iguais, total = **−1.170,71**.

## Aceite e limitações

`tests/test_synthetic_runner_costed_close.py`: cálculo LONG/SHORT, conservação, funding entre parciais, custo e 50x imutáveis, contexto Decimal de baixa precisão, idempotência do mesmo ID e rejeição de nova closure, quantidade 5/7/100, parcial pendente, zero residual, clock passado/futuro, tipos errados, preço inválido e custódia de flags. Regressão `test_synthetic_partial_costed_replay.py` e suites existentes precisam continuar verdes em Linux e Windows. Browser/PAPER não pode ser impactado. Merge com SHA exact e CI, **sem deploy**.

`sanitized_report()` não serializa IDs de posições nem IDs de eventos ou preços individuais; valores são referências *sintéticas* sem autenticação. Todas as flags `realized_pnl_verified`, `liquidation_risk_verified`, `venue_fees_verified`, `venue_fill_verified`, `funding_settlement_verified`, `financial_backtest_approved`, `persistent_idempotency_verified`, `approved_for_live_use` e `orders_sent` permanecem **false**. Isto não valida lucratividade, stop, risco 50x, saúde de margens nem execução real. J4 #5 continua aberta para integração e homologação posterior.
