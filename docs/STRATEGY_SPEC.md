# Estratégias e gestão de vencedores

## Entradas: hipóteses, não promessas
- A: expansão depois de compressão de volatilidade, com validação de volume, liquidez e contexto.
- B: continuação de tendência após correção e retomada.
- C: força relativa frente ao Bitcoin e demais ativos.
- D: recuperação após falso rompimento como experimento posterior.

O regime de mercado deve modular elegibilidade e decisão. Dados de derivativos são candidatos a adicionar valor, não confirmação automática. Scores não podem ser tratados como probabilidades calibradas.

## Alavancagem e posições
Padrão global 50x; cada posição registra leverage_at_open e margem, e não é alterada retroativamente quando a configuração muda. Não impor número fixo de operações.

## Saídas
- INITIAL_POSITION: o percentual incide sobre quantidade inicial; soma das realizações não ultrapassa 100%.
- REMAINING_BALANCE: o percentual incide sobre o saldo de posição imediatamente anterior. Exemplo: 50%, 60% e 70% sucessivos deixam 6% da quantidade inicial.
- Runner opcional para movimentos prolongados, com trailing e invalidação baseados em regras testáveis.
- Ordem e tamanho das saídas precisam respeitar precisão e mínimos de contrato; nunca supor que uma parcial de tamanho arbitrário seja executável.

## Avaliar
PnL líquido, risco e drawdown da carteira, MAE/MFE, taxa de liquidação, sobrevivência a recuos, eficiência de captura e estabilidade fora da amostra. Não usar máximos futuros para decidir no presente; distinguir marcação de preço e preço negociado.


## Pré-trabalho J2/PRE1 — features causais com candles exclusivamente sintéticos (#66)
O módulo puro `synthetic_feature_engine.py` recebe a estrutura `ClosedCandle` já existente, porém exige **somente** `quality=synthetic_fixture`, mercado `linear_perpetual`, série de um único exchange/símbolo/intervalo, timestamps UTC contíguos alinhados e velas fechadas até `decision_at_ms - close_safety_ms`. No máximo 10.000 candles e períodos explícitos de 2 a 500; não usa rede, storage, outro ativo, cache, lookahead, alavancagem ou ordens.

Definições matemáticas configuráveis e determinísticas (Decimal com contexto interno 50 dígitos):
- **EMA(close, N):** primeiras N-1 saídas são `None`; valor inicial é SMA dos N primeiros closes; a seguir `EMA_t = EMA_(t-1) + (2/(N+1))*(close_t-EMA_(t-1))`. Não iniciar EMA artificialmente em close[0].
- **TR e ATR Wilder (N):** `TR_0=high_0-low_0`; de t>=1, `TR_t=max(high-low, abs(high-close_(t-1)), abs(low-close_(t-1)))`. `ATR_(N-1)=mean(TR_0..TR_(N-1))`; depois `ATR_t=((N-1)*ATR_(t-1)+TR_t)/N`.
- **Extremos anteriores (N):** `preceding_high_t=max(high_(t-N)..high_(t-1))` e mínimo análogo, nunca incluem a vela atual. Sem N candles anteriores, `None`.
- **Atividade de volume (N):** `quote_volume_t / mean(quote_volume_(t-N)..quote_volume_(t-1))`, sem incluir a barra atual na base. Se a média anterior for zero ou houver aquecimento insuficiente, `None` (não inventar divisão/volume).
- **Retorno simples:** `close_t/close_(t-1)-1`; primeiro retorno `None`. Volume cotado é comparável **somente dentro da mesma série e unidade**, não entre venues ou moedas. Nenhuma probabilidade, score ou regra buy/sell é produzida.

A linha de features mantém o instante do candle e propriedades de aprovação de sinal sempre `false`; a série guarda `quality=synthetic_fixture` e `approved_for_live_use=false`. Esta implementação é uma **pré-condição técnica independente**, não o início operacional ou aceite da J2. Para quaisquer dados reais, ainda serão exigidos gate J1, licença, qualidade, reconstrução point-in-time, provas quantitativas e J3. Nenhuma parametrização sugere rentabilidade.


## J4/PRE1 — Planejador puro de fatias sintéticas (issue #81)
O módulo `synthetic_partial_exits.py` formaliza **somente o tamanho relativo** das realizações. Não responde *quando* executar e não mantém estado de posições reais. Para `initial_units=100` e `REMAINING_BALANCE` com percentuais 50, 60 e 70, as saídas são 50, 30 e 14 unidades abstratas e ficam 6. Com `INITIAL_POSITION`, cada percentual da fatia incide sobre 100 independentemente do saldo corrente; percentuais podem ser misturados, mas nunca exceder o saldo disponível. Um runner configurável é piso percentual da posição **inicial**; a rotina rejeita qualquer parcial que o ultrapasse, sem ajuste ou clipping. Passos são sequenciais, determinísticos, conservam quantidade exata via Decimal e não fazem quantização de lotes.

Esta unidade não possui preços, stop, trailing, executor, exchange, multiplicador contratual, marcação de PnL, funding, taxas ou corretagem. `Decimal` limita entradas a números finitos e mantém contexto interno reproduzível, sem depender da precisão global; limitações de escala/64 passos são **de proteção do experimento**, não metas ou regras do produto. Todas as flags de execução e validação do tamanho de lote são falsas. Antes de integrar à J4 operacional será necessário definir contrato real de posição, lot size/step size, fills manuais idempotentes, proteção contra double-close, PnL e custos, interface, triggers causais e backtest com intrabar/risco. Nenhum plano percentual isolado prova ganho ou é ordem.


## J4/PRE2 — Progresso de fills manuais simulados sem execução
`synthetic_manual_exit_replay.py` recebe um plano PRE1 sintético e uma sequência **ordenada** de eventos fictícios de saída (ID, tranche 1-based, quantidade Decimal em unidades abstratas, horário UTC-ms) com instante de criação e corte `as_of_ms`. O plano preserva os alvos 50/60/70 do REMAINING (50+30+14 para 100 com runner de 6), mas o saldo **não diminui** até um evento efetivamente registrado no replay. Exemplo: preencher 30 e depois 20 unidades da tranche 1 permite avançar para a tranche 2; um evento de 10 unidades na tranche 2 preserva 40 unidades restantes, enquanto 20 da tranche 2 ainda não foram preenchidas. Passos futuros não podem saltar tranches anteriores incompletas e excessos não são aceitos.

Idempotência é limitada à mesma execução em memória: dois eventos com ID/payload exatos idênticos são contabilizados uma vez; conflito de ID é erro, nunca update silencioso. **IDs diferentes ainda podem representar a mesma execução financeira**, portanto este código NÃO é ledger confiável de operações reais. A saída representa quantidade prevista/preenchida/pendente por tranche e saldo sintético, sem preço, taxa, funding, PnL, trailing, gatilho, contrato, ordens, execução ou persistência. Isso não altera a obrigação de entradas/saídas manuais no produto nem homologa J4 operacional.


## J4/PRE3 — Posição de fixture imutável, margem variável e leverage_at_open
O contrato `synthetic_position_state.py` separa configuração global **para abertura de novas posições** (padrão 50x de pesquisa) do snapshot de cada posição. A posição fictícia recebe ID explicitamente `fixture_*`, enum LONG/SHORT, horário UTC, quantidade abstrata do `SyntheticExitPlan` PRE1, margem `Decimal` abstrata por posição e alavancagem gravada no momento de abertura. Alterar a configuração de 50x para 20x cria apenas um novo objeto de configuração; snapshots anteriores continuam em 50x. Não há quantidade fixa de posições ou meta por universo. Nenhum parâmetro confere viabilidade econômica, margem de manutenção, multiplicador, tamanho de lote executável, taxa, preço, liquidação ou exposição.

Cada `SyntheticPositionExitFill` envelopa um evento fictício PRE2 e exige exatamente o `fixture_position_id` da posição de pesquisa; eventos de posições diferentes são recusados, nunca agregados. `replay_synthetic_position` delega a conservação, deduplicação **somente in-memory**, cronologia, runner residual e overfill ao módulo PRE2, sem reescrever a matemática. Saída imutável inclui progresso por tranche, parcial efetivamente informada, quantidade restante, margem abstrata e leverage capturada, com todos os gates live/ordem/identidade/lot/rights falsos. Não se deve tratar essa camada como posição financeira, ledger de fills ou simulação de execução. Etapas futuras da J4 exigem J1/J3, fonte de preço e contrato real, persistência transacional, idempotência entre sessões e cálculo de risco/taxas verificável.


## J4/PRE4 — Viabilidade matemática dos lotes e parciais
A rotina pura `synthetic_lot_feasibility.py` recebe uma posição `fixture_*` PRE3, uma regra de lote puramente hipotética (`size_step_units`, `minimum_exit_units`, `minimum_nonzero_remaining_units` em Decimal) e, opcionalmente, eventos manuais FICTÍCIOS PRE2 já vinculados à posição. Não modifica planos, fills ou saldos, e não calcula quantidade executável nem envia ordens. A compatibilidade é calculada por múltiplos exatos, sem tolerância de ponto flutuante e sem arredondamento; uma tranche de 25 unidades não se torna válida apenas porque outra tranche de 25 completa 50 num step de 2 — cada evento parcial deve ser conferido separadamente. O residual de um plano 50/60/70 sobre inicial 100 é 6; se o mínimo hipotético restante for 7, a avaliação falha mesmo com step de 2. Fechamento total com residual zero pode satisfazer mínimos de residual apenas após evento explícito.

A regra é **fixture não homologada**: tamanho de lote, multiplicador, mín. notional, casa decimal de preço, moeda de margem e restrições dinâmicas da exchange exigirão fontes originais, temporalidade, identidade crypto-only e direitos aceitos. `arithmetically_compatible` não é `approved_for_live_use`. A J4 operacional ainda precisa de ledger durável, proteção cross-session, fills manuais reais, custo, funding, liquidação e testes J3, sem iniciar ordens automáticas.


## J3/PRE1 — Primeiro toque de barreira em OHLC SINTÉTICO: ambiguidade sem prêmio
O detector `synthetic_intrabar_barriers.py` não é motor de backtest financeiro. Recebe níveis de referência LONG/SHORT (`entry`, `stop`, `target`, e `hypothetical_liquidation` opcional), declarados antes do primeiro candle de uma **fixture sintética**. A decisão `as_of_ms` só pode enxergar velas completamente fechadas e validadas pelo mesmo contrato causal da J2. O primeiro candle com toque gera `levels_reached` em ordem de categorias fixa, **não em ordem cronológica real**. LONG considera `low <= stop/liquidation` e `high >= target`; SHORT inverte os sentidos. Quando o preço de abertura já cruza algum nível, classifica `OPEN_AT_OR_BEYOND_LEVEL` e NÃO assume o preço de fill. Quando dois ou três níveis são atingidos pela mesma faixa high/low, classifica `MULTIPLE_LEVELS_UNORDERED` independentemente de candle close ou direção. Um toque único não implica execução, lucro, liquidação financeira nem segurança da alavancagem de pesquisa 50x.

Esse método é deliberadamente conservador em *evidência*, não inventa um caminho "pior" ou "melhor". J3 posterior deverá comparar resolução mais fina, implementar regras explícitas e testáveis de caminho intrabar pessimista com fill, liquidação por mark/maintenance margin, taxas, slippage, funding, atraso e walk-forward, e sempre reconhecer limites de causalidade. Sem homologação de dados J1 e modelos de risco/contrato, `profitable_trade_verified=false` e `financial_backtest_approved=false` são invariantes.


## J3/PRE2 — Cenários de custo bruto sintético sem preço, PnL ou exchange
`synthetic_cost_scenarios.py` recebe notionals de entrada/saída em unidades **abstratas de quote** e bps hipotéticos de taxas e slippage adverso separados por perna. O custo aritmético de cada um é `notional * bps / 10000` em `Decimal` exato. Funding só é aplicado a eventos fictícios explicitamente fornecidos e conhecidos no intervalo de posse simulado, com custo assinado: LONG paga taxa positiva, SHORT recebe, e taxa negativa inverte. Exemplo de referência (unidades sintéticas): entrada 1.000, saída 800, taxas 10/20 bps e slippage 5/15 bps custam 1 + 1,6 + 0,5 + 1,2 = 4,3 unidades; um funding LONG 5 bps sobre notional 1.000 adiciona 0,5, total 4,8, enquanto o cenário SHORT subtrai 0,5, total 3,8. Isso NÃO constitui PnL de trade nem permite comparar moedas da exchange.

A função não obtém preço de execução de um toque intrabar PRE1 nem presume fills; os eventos de funding são IDs sintéticos, com deduplicação dentro da mesma chamada, e não são eventos de conta verificáveis. Um `total_signed_cost_units < 0` representa crédito hipotético líquido de funding e despesas, não uma estratégia lucrativa. O backtest financeiro J3 #4 exige dados e direitos J1, identidade e moeda reais, contract multiplier, fees maker/taker por tier, funding efetivamente liquidado, slippage por regime e profundidade, mark/liquidação e spread, gatilhos causais, margin 50x avaliada por risco e testes walk-forward/out-of-sample. Nenhum desses requisitos foi homologado por PRE2.


## J1/WU47 — Binance/Bybit como candidatas de execução manual (26/10/2026 UTC)
O Product Owner informou que tem contas na Binance e na Bybit. **Isso não é evidência de acesso a futuros, habilitação regional de API, qualidade de OHLCV, alavancagem, ou autorização para usar credenciais.** Ambas são **candidatas**, nenhuma foi selecionada. O produto mantém execução **manual**, sem endpoints de ordens, chaves ou conexão à conta. Fonte de pesquisa não precisa coincidir com a venue de eventual execução, mas um sinal só poderá ser considerado executável após reconciliação de preço, símbolo, contrato, quote/settle, lot/step/min notional, funding, taxas, liquidez, limites de risco e disponibilidade na venue específica. Kraken price-only é pesquisa auxiliar e não certifica Binance/Bybit.
Binance USD-M já tem adaptador/fixtures offline, mas o run real anterior foi bloqueado HTTP451 (#19). Bybit linear V5 possui parser documentado de volume BASE/turnover QUOTE em USDT/USDC, porém o único run real foi restrito no primeiro GET (WU44, 0 candles). Não repetir nem contornar restrições. O relatório `scripts/j1_readiness_report.py` distingue as duas candidatas com flags `account_access_verified=false`, `live_signal_approved=false`, `manual_plan_approved=false`, `order_execution_enabled=false`. Essa enumeração não concede direitos de dados, não escolhe venue nem homologa J1 #2, #32, #36 ou #48. Custo adicional R$0; sem credenciais, dados de conta, ordens, deploy ou feed público.


## D77 — estratégia dispara entradas e saídas AUTOMÁTICAS (alvo)
Quando J1/J2/J3/J4/J6 e os gates de produção forem comprovados, uma estratégia elegível produz intenção de entrada e ordens **automáticas**, sem clique humano por trade. A mesma política controla stops, takes parciais por `INITIAL_POSITION` ou `REMAINING_BALANCE`, trailing stop, runner e fechamento, sempre a partir do saldo/fills efetivamente confirmado pela exchange. Sinais de alta pontuação não pulam avaliação de liquidez, risco, alavancagem/tier, mínimos, custos, concorrência, saúde do feed, limites de perda ou `kill-switch`. `50x` não garante margem segura nem elegibilidade por contrato. As decisões anteriores de execução manual estão substituídas como requisito FINAL; os módulos J4 sintéticos são insumos de pesquisa, não bots operacionais. Por ora `offline_paper` sem POST, `testnet` sob gate e `live` bloqueado até aprovação separada; ver `docs/AUTOMATED_EXECUTION_SPEC.md`.
