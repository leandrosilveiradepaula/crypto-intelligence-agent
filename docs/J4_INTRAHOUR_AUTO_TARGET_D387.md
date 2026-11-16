# J4 / D387 — realização parcial automática intrahorária (PAPER)

## Resultado deste incremento da issue #676

`crypto_intelligence_agent/paper_intrahour_target_step_d387.py` é o
**primeiro componente que transforma cotações intrahorárias tipadas da
Bybit D385 em uma intenção de REDUCE_ONLY reservada AUTOMATICAMENTE**
no **journal PAPER AUTO4 existente** `SQLitePaperPositionJournal`.

Não exige clique do Product Owner nem novo candle de 1h. O serviço
pode receber uma cotação de 10h12 e gerar a intenção da tranche 1,
receber um fill PAPER **explícito** e acionar a tranche 2 às 10h19
dentro da mesma vela, mantendo o runner para o módulo J4/RUNNER já
implementado. A hora pode ser escolhida por estratégia; o motor só
exige ordem causal dos timestamps.

**Limite atual:** este módulo não envia ordens nem cria fills; não
implementa ainda stop-loss automático *antes* das parciais, ajuste
de trailing intrabar de toda posição ou proteção nativa Bybit.
O runner existente (`paper_runner_close_step.py`) continua exclusivo
da sua fase e do seu journal. Essas capacidades seguem pendentes
na #676; este é um incremento implementado, não a conclusão da J4.

## Regras duráveis e gates

- A posição deve existir no AUTO4, derivada de `OPEN` com evento
  de **FILL PAPER explícito**, venue `PaperVenue.BYBIT_V5`,
  `SyntheticExitPlan` fixo e versão de plano coincidente.
  Nunca tratar ACK como posição aberta.
- Um `PaperIntrahourTargetPolicy` contém níveis `Decimal`
  **estritamente ascendentes para LONG / descendentes para SHORT**,
  exatamente um por tranche já versionada no journal. O cálculo
  do tamanho é o **já existente PRE1/AUTO4**: percentual sobre posição
  inicial ou saldo restante, validado por passo de lote sintético,
  runner e reservas. Nenhuma segunda contabilidade criada.
- Um alvo LONG dispara somente com **bid** no nível ou superior;
  SHORT somente com **ask** no nível ou inferior. Last/Mark
  são informativos, **não** fill nem gatilho executável garantido.
- Exigir quote D385 do símbolo da posição, timestamp causal de
  exchange/recepção, idade máxima configurada (default 3s), book
  com tamanho bid/ask positivo e spread limitado em basis points.
  Dados obsoletos ou sem profundidade implicam **abstenção**.
- Antes de cada alvo conferir TODAS as ordens anteriores: PENDING,
  ACK, UNKNOWN e preenchimento parcial mantêm a reserva e bloqueiam
  novas reduções até reconciliação; cancelamento/rejeição não provoca
  reenvio automático. Uma tranche só avança depois do preenchimento
  completo explicitamente anexado ao AUTO4.
- ID da intenção deriva deterministicamente de posição, plano,
  tranche e nível; `reserve_exit` valida saldo,
  `reduce-only`, timestamp e saldo da carteira em transação
  `BEGIN IMMEDIATE`. Em concorrência não pode haver
  duas reservas para a mesma intenção. Intenção ≠ execução.
- Alteração posterior da alavancagem global NÃO altera o campo
  `leverage_at_intent` da posição persistida; quando ausente,
  o resultado deve indicar `None` e não inferir alavancagem real.
  `native_stop_verified=false`, `net_pnl_verified=false`,
  `order_submission_enabled=false`, `orders_sent=false`.

## Testes

`python -m unittest discover -s tests -p test_paper_intrahour_target_step_d387.py -v`

Fixtures em temp SQLite e cotações intrahorárias: 10h05 OPEN
confirmado, 10h12 alvo 1 reserva, UNKNOWN/duplicata não reenvia,
10h19 alvo 2 após fill explícito, residual runner preservado.
LONG e SHORT, spread/staleness, quote de símbolo errado,
venue errada, timestamps futuros, preço Last sem BID compatível,
cancel/reject e corrida de duas threads. Zero rede.

## Caminho de conclusão da #676

1. Proteger stop inicial com prioridade sobre alvos em qualquer
   instante, inclusive antes do primeiro parcial, com ledger que
   permita fechamento do saldo residual em emergência.
2. Integrar trailing e runner ao mesmo supervisor de eventos,
   reusar `paper_runner_trailing.py`/`paper_runner_close_step.py`
   sem duplicação, e reconciliar fill parcial com proteção futura.
3. Ligar ao feed público #677, tratar drops, reconnect e
   preço obsoleto; teste prospectivo e backtest com custos,
   slippage, funding, liquidação e gap; nenhuma conclusão de lucro
   nem integração com conta antes de homologação.
4. Projetar adaptador REST/WS privado Bybit somente com fixtures
   até gate de testnet e, separadamente, gate de live.

Referências oficiais:
- https://bybit-exchange.github.io/docs/v5/websocket/public/ticker
- https://bybit-exchange.github.io/docs/v5/order/create-order
- https://bybit-exchange.github.io/docs/v5/position/trading-stop
