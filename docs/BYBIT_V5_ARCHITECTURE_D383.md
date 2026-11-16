# D383 — arquitetura Bybit V5 como corretora única (16/11/2026)

## Decisão do Product Owner e limites

Em 16/11/2026, o Product Owner escolheu explicitamente **Bybit** para a plataforma de futuros perpétuos. A partir desta decisão, **Bybit V5 `linear` de contratos cripto USDT liquidados em USDT** é a venue operacional-alvo e a fonte primária de dados para o produto. Binance/Kraken/OKX/Hyperliquid permanecem como pesquisa histórica, sem nova implementação equivalente, roteamento de ordens ou fallback de execução. Não misturar feeds/identificadores/contas de corretoras para gerar uma ordem. Qualquer mudança de venue exige nova decisão do Product Owner.

**A seleção de Bybit não prova acesso da conta, permissões da API, elegibilidade regional, disponibilidade de instrumentos, homologação de risco, capacidade de ordem nem autorização de negociação financeira.** Modo de desenvolvimento `offline_paper`, `order_submission_enabled=false`, `live_trading_enabled=false`. **sem chaves** da conta neste estágio, nenhum POST autenticado de ordens. Testnet requer gate próprio; live requer gate distinto J6 e autorização humana explícita; nenhum segredo no GitHub público, nenhuma ordem real e custo adicional R$0.

## Revisão do que já existe

- J1 possui **REST Bybit real de pesquisa**: `crypto_intelligence_agent/bybit_public_j1_transport.py`, `j1_rest_incremental_owner.py`, `scripts/run_j1_rest_hourly_once.py`; serviço REST foi fallback do WS, não é novidade a implementar.
- J1 possui **WS Bybit N50 de janela curta próxima ao fechamento**: usa `confirm=true` para evidência da vela de 1h e mantém diário owner da coorte. D380/D381 recuperaram sua implantação em 16/11/2026; habilitação de timers NÃO é prova de primeiro novo fechamento após recuperação.
- `bybit_linear_candle_research.py` documenta parser isolado; J2/J3 e J4 PAPER têm componentes sintéticos. **Não há feed público persistente intrahorário de 50 contratos nem executor real autenticado homologado**.
- Logo, não refazer seleção/homologação histórica J1, nem reaproveitar WS de 1h como se fosse supervisor de posições. Não iniciar dois escritores sobre o mesmo SQLite owner.

## Matriz Bybit V5 — função e API

| Responsabilidade | Canal principal | Contratos documentados |
| --- | --- | --- |
| Inventário e regras | REST público | `GET /v5/market/instruments-info?category=linear&status=Trading`: paginação por cursor (>500 símbolos), `contractType`, `quoteCoin`, `settleCoin`, `priceFilter.tickSize`, `lotSizeFilter.minOrderQty/qtyStep/minNotionalValue`, `leverageFilter.maxLeverage`, modo/limites de mercado |
| Ranking Top50 ponto-no-tempo | REST público snapshot, não polling intratick | `GET /v5/market/tickers?category=linear` e `turnover24h` em unidade comparável, timestamp/epoch; excluir contratos não cripto, não perpétuos e não elegíveis |
| História e gaps de velas fechadas | REST público | `GET /v5/market/kline` com `category=linear,interval=60`, `start/end`, páginas de até 1000 em ordem descendente; **excluir vela aberta**; mark-price OHLC por `/v5/market/mark-price-kline` quando necessário |
| Pesquisa histórica intrahorária (quando houver cobertura) | Arquivos CSV oficiais Bybit + replay controlado | Bybit documenta downloads públicos de históricos de trades, kline, snapshots de livro e funding; **verificar disponibilidade real por ativo/período, ordem de eventos, unidades, custo e condições de uso antes de importar**. Não inferir qualidade de execução a partir de OHLC ou snapshots esparsos. |
| Mercado intrahorário 24×7 | WS público `wss://stream.bybit.com/v5/public/linear` | `tickers.{symbol}` (snapshot e delta nominal 100 ms; ausência de campo em delta significa inalterado), `kline.60.{symbol}` com `confirm=true`, subscrições seletivas `orderbook.1/50.{symbol}` e `publicTrade` quando justificado |
| Envio de abertura/redução/alteração | REST **autenticado, somente após gate** | `POST /v5/order/create`, `/amend`, `/cancel`; `orderLinkId` único até 36 chars, `positionIdx` explícito, `reduceOnly` para reduções; ACK **não é** FILL |
| Proteção real da posição | REST **autenticado, somente após gate** | `POST /v5/position/trading-stop`, com `Full/Partial`, `takeProfit/stopLoss/trailingStop`, trigger `MarkPrice/LastPrice/IndexPrice`; Partial **adiciona** TP/SL, `tpSize=slSize`; verificar proteção após confirmação |
| Posições, ordens e fills | WS privado + REST de recuperação, somente após gate | WS `/v5/private`: `order.linear`, `execution.linear`, `position.linear`; REST `GET /v5/order/realtime`, `/v5/order/history`, `/v5/execution/list`, `/v5/position/list`, saldo; não inferir fill de ACK |
| Envio alternativo futuro | WS Trade autenticado, **não prioritário** | `wss://stream.bybit.com/v5/trade` suporta `order.create/amend/cancel`, mas requer análise de benefício e não elimina confirmações privadas |

A referência comercial https://www.bybit.com/pt-BR/derivative-activity/developer destaca REST para trading automático. Ela não restringe WS a histórico/privado: **WS público serve dados ao vivo**, WS privado serve mudanças da conta, e REST serve histórico/snapshots e ordens. Não fazer 50× chamadas REST a cada variação de preço.

## Fluxo final — dois relógios e ledger único

1. **Descoberta periódica**: consulta REST paginada de instrumentos e ticker, valida `status=Trading`, `contractType=LinearPerpetual`, quote/settle USDT, elegibilidade crypto-only por evidência apropriada (sufixo USDT não basta), liquidez e notional. Ordena por `turnover24h` comparável; salva instante e digest PIT. Escolhe os 50 elegíveis. Se há posição aberta cujo contrato saiu do Top50, mantém monitoramento e proteção.
2. **Pesquisa causal/história**: coleta REST apenas páginas de velas já encerradas, marca fonte e hora de fechamento. WS `kline.60` confirmado pode produzir o mesmo evento em streaming; **um único escritor e contrato de reconciliação econômica** para não duplicar candles ou sobrescrever divergências. O WS curto da J1 continua isolado durante a validação da alternativa persistente; cutover só por release revisado, sem abrir nova J1.
3. **Coleta em tempo real**: conexão pública de longa duração com heartbeat a cada ~20 s conforme orientação da venue, reconexão limitada com backoff, resubscribe e validação de snapshot/delta, símbolo, sequência e idades. `ticker` dos 50 como base leve; orderbook/trades detalhados sob demanda para oportunidades e posições; avaliar throughput em VPS antes de escolher granularidade de persistência. No ticker, carregar campos delta ausentes do último snapshot válido; jamais usá-los como zero.
4. **Sinais/posição**: contexto de 1h alimenta sinais quantitativos; motor PAPER consome evento com `exchange_ts`, `received_ts`, origem, qualidade, bid/ask, last/mark e cursor causal. Entradas podem ser condicionadas à vela fechada por estratégia; **stops, parciais, trailing, runner e vigilância de margem funcionam intrahora**. Dados obsoletos/seq inválida bloqueiam **novas entradas**; proteções existentes mantidas ou reconciliadas.
5. **Ordens automáticas (quando autorizadas)**: `Signal -> RiskGate -> Intent persistida -> REST order -> WS order/execution/position -> ledger de fills`. A mesma `orderLinkId` não é reenviada cegamente após timeout; consulta e reconcilia antes de nova ação. `UNKNOWN`, parcial, race cancel-vs-fill, desconexão, reinício e posições fora do bot são gates de segurança.
6. **Proteções nativas**: após fill e posição confirmados, instalar e comprovar stop/TP/SL/runner na venue (ou política de proteção pré-definida e validada para janela de fill). `Full` e `Partial` têm restrições diferentes; recalcular apenas usando fills confirmados, `reduceOnly` não deve inverter a posição. O plano de risco deve cobrir desconexão da VPS, cancelamento inesperado e ordens não preenchidas; stop não garante preço.
7. **Observabilidade e celular**: VPS opera sem celular. UI PT-BR mostra modo, bot ligado/pausado, fonte e atraso, watchlist, risco, ordens, fills, parciais, funding/custos e kill-switch. Kill-switch impede novas entradas, **não cancela cegamente stops de posições abertas**.

## Cuidados de contabilidade e risco que não podem ser ignorados

- Em `one-way mode`, ordens de mesma direção para o mesmo símbolo tendem a compor **uma posição líquida** na exchange; o ledger deve distinguir estratégias/intenções sem fingir várias posições independentes. `hedge-mode` usa `positionIdx` e requer contrato expresso. Não mudar modo de posição com ordens/posições abertas fora do procedimento aprovado.
- `POST /v5/position/set-leverage` opera por símbolo, não por objeto abstrato de trade. A configuração global de **50x para novas entradas** não permite mudar alavancagem de posição existente inadvertidamente. Proibir entrada se a alavancagem requerida conflitar com posição ativa naquele instrumento/modo até política específica validada.
- Margem configurável de US$1–US$5 pode ficar abaixo de `minNotionalValue`, `minOrderQty` ou limites atuais da Bybit. Não arredondar para cima silenciosamente nem forçar 50x; abster-se e informar restrição. A 50x, variação adversa aproximada de 1% equivale a ~50% da margem inicial antes de custos, funding e mecanismos de liquidação.
- Triggers de stop por `MarkPrice`, `LastPrice` e `IndexPrice` não são equivalentes. Backtest e gestão usam a mesma referência do contrato; livro bid/ask importa para slippage e preenchimento. Ordem `Market` pode converter para IOC limite de proteção e **não ser totalmente preenchida**.
- Eventos privados são assíncronos, podem duplicar ou chegar em ordem diferente. WS posição emite mensagem mesmo com certas ações que não alteram quantidade. `execution.execId` e confirmações REST orientam reconciliação, não apenas status `Filled`.
- `GET /v5/market/kline` pode devolver a vela ainda aberta com último preço, não fechamento definitivo; reter apenas candles inteiros fechados pelo relógio e segurança temporal, ou `confirm=true` via WS. REST recupera **velas fechadas**, mas NÃO reconstitui perfeitamente a trajetória intrabar perdida durante uma desconexão; proibir backfill que finja preços/timestamps intermediários para performance/ordens.
- Tickers a 100 ms são **frequência nominal da fonte**, não latência de execução e nem mensagem garantida por símbolo a cada tick. Medir drop-rate, bytes/s, p95/p99 event-to-process, CPU/RAM, backlog, rate limit e qualidade em VPS existente. Persistir eventos úteis e agregados/reproduzíveis; não presumir que reter todos os ticks dos 50 cabe no orçamento.
- Verificar com prova de conta/região e documentação atual a disponibilidade de USDT Perp e APIs REST/WS **antes** de criar credenciais. Chaves privadas de teste, somente quando autorizadas, fora do GitHub, permissões mínimas (preferir sem saque), proteção local e auditoria. Zero custo extra não elimina **taxas de negociação, funding e perdas financeiras** quando houver live.

## Ordem de implementação e aceites

| Etapa | Escopo | Evidência necessária |
| --- | --- | --- |
| A — D383 | Escolha Bybit, mapa V5, contrato de 2 relógios | PR documental, CI, decisão versionada, sem ordens |
| B — J2 feed público contínuo | Adaptador Bybit WS read-only com payloads tipados, monitor 50 + posições, health, heartbeat/reconnect, testes de delta/stale | Replay offline adversarial; piloto isolado na VPS só após gate operacional; N50 atual intocado |
| C — J4 #676 | Motor **PAPER** orientado a eventos com entradas/saídas automáticas e ledger existente; prioridades stop/partials/trailing | Long/short e múltiplas saídas intrahora, nenhuma necessidade de clique ou nova vela; UNKNOWN e restart sem duplicatas |
| D — J2/J3/J6 | Integração de feed real read-only aos sinais/simulador, score prospectivo e backtest intrabar com custo/slippage/funding | Sem look-ahead, divergências/gaps explícitos e métricas líquidas OOS; nenhuma ordem real |
| E — adaptador de ordens Bybit offline | Contratos REST de ordens/TP-SL e WS privado com fixtures; risco e reconciliação | Testes de reordenação/fill/cancel, restrições de `positionIdx`, lote, alavancagem, nativo TP/SL, sem credenciais |
| F — testnet / live | Integração autenticada em ambientes separados, com gates próprios | Aprovação de credencial/testnet; J6 com proteção efetiva e incidente/resiliência; autorização específica **posterior** para live |

**Nenhuma linha da tabela é autorização de release ou de ordens.** Mesma estratégia/ledger e estados ao longo da pesquisa; evitar reescrever J1, duplicar executores ou deixar o bot depender do celular.

## Referências primárias (consultadas em 16/11/2026)

- https://bybit-exchange.github.io/docs/v5/intro
- https://bybit-exchange.github.io/docs/v5/market/instrument
- https://bybit-exchange.github.io/docs/v5/market/tickers
- https://bybit-exchange.github.io/docs/v5/market/kline
- https://bybit-exchange.github.io/docs/v5/market/mark-kline
- https://www.bybit.com/pt-PT/learn/bybit-guide/how-to-create-a-bybit-api-key (arquivos históricos públicos CSV de trades/livro/kline/funding; validar cobertura)
- https://bybit-exchange.github.io/docs/v5/ws/connect
- https://bybit-exchange.github.io/docs/v5/websocket/public/ticker
- https://bybit-exchange.github.io/docs/v5/websocket/public/kline
- https://bybit-exchange.github.io/docs/v5/websocket/public/orderbook
- https://bybit-exchange.github.io/docs/v5/order/create-order
- https://bybit-exchange.github.io/docs/v5/position/trading-stop
- https://bybit-exchange.github.io/docs/v5/position/leverage
- https://bybit-exchange.github.io/docs/v5/position/position-mode
- https://bybit-exchange.github.io/docs/v5/websocket/private/order
- https://bybit-exchange.github.io/docs/v5/websocket/private/execution
- https://bybit-exchange.github.io/docs/v5/websocket/private/position
- https://bybit-exchange.github.io/docs/v5/order/open-order
- https://bybit-exchange.github.io/docs/v5/position
- https://bybit-exchange.github.io/docs/v5/websocket/trade/guideline
- https://bybit-exchange.github.io/docs/v5/rate-limit
