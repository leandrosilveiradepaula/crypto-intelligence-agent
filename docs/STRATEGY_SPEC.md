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
O Product Owner informou que tem contas na Binance e na Bybit. **Isso não é evidência de acesso a futuros, habilitação regional de API, qualidade de OHLCV, alavancagem, ou autorização para usar credenciais.** Ambas são **candidatas**, nenhuma foi selecionada. O produto mantém **execução real bloqueada** e operações exclusivamente PAPER/offline; a execução automática de entradas e saídas é requisito futuro (D77), sujeita aos gates de produção, e não está habilitada. Fonte de pesquisa não precisa coincidir com a venue de eventual execução, mas um sinal só poderá ser considerado executável após reconciliação de preço, símbolo, contrato, quote/settle, lot/step/min notional, funding, taxas, liquidez, limites de risco e disponibilidade na venue específica. Kraken price-only é pesquisa auxiliar e não certifica Binance/Bybit.
Binance USD-M já tem adaptador/fixtures offline, mas o run real anterior foi bloqueado HTTP451 (#19). Bybit linear V5 possui parser documentado de volume BASE/turnover QUOTE em USDT/USDC, porém o único run real foi restrito no primeiro GET (WU44, 0 candles). Não repetir nem contornar restrições. O relatório `scripts/j1_readiness_report.py` distingue as duas candidatas com flags `account_access_verified=false`, `live_signal_approved=false`, `manual_plan_approved=false`, `order_execution_enabled=false`. Essa enumeração não concede direitos de dados, não escolhe venue nem homologa J1 #2, #32, #36 ou #48. Custo adicional R$0; sem credenciais, dados de conta, ordens, deploy ou feed público.


## D77 — estratégia dispara entradas e saídas AUTOMÁTICAS (alvo)
Quando J1/J2/J3/J4/J6 e os gates de produção forem comprovados, uma estratégia elegível produz intenção de entrada e ordens **automáticas**, sem clique humano por trade. A mesma política controla stops, takes parciais por `INITIAL_POSITION` ou `REMAINING_BALANCE`, trailing stop, runner e fechamento, sempre a partir do saldo/fills efetivamente confirmado pela exchange. Sinais de alta pontuação não pulam avaliação de liquidez, risco, alavancagem/tier, mínimos, custos, concorrência, saúde do feed, limites de perda ou `kill-switch`. `50x` não garante margem segura nem elegibilidade por contrato. As decisões anteriores de execução manual estão substituídas como requisito FINAL; os módulos J4 sintéticos são insumos de pesquisa, não bots operacionais. Por ora `offline_paper` sem POST, `testnet` sob gate e `live` bloqueado até aprovação separada; ver `docs/AUTOMATED_EXECUTION_SPEC.md`.


## J4/AUTO1 #149 — eventos de ordens, distintos de planejamento de parciais
O módulo `synthetic_order_lifecycle.py` não produz sinais ou decisões de compra; modela eventos criados explicitamente em fixtures (`ACKNOWLEDGED`, `UNKNOWN`, `FILL`, `REJECTED`, `CANCELLED`) para preparar o controle de entradas/saídas AUTOMÁTICAS. `PaperOrderEffect.REDUCE_ONLY` exige lado oposto e teto de saldo de posição fornecido pelo teste; isto não confirma regra real da Binance/Bybit, saldo da conta ou stop instalado. PRE1 permanece fonte de percentuais, PRE2/PRE3 de quantidades de preenchimentos fictícios. Mesmo quando `status=FILLED`, `orders_sent=false`, `approved_for_live_use=false`, sem PnL/fee/funding/mark e sem aceitação J4/J6.


## J4/AUTO4 — conservation e coordenação de saídas simuladas
A execução automática requer impedir que duas realizações parciais reservem a mesma quantidade de uma posição. Para o modo PAPER, `SQLitePaperPositionJournal` compara a soma de fills e reservas ativas de todas as ordens com a quantidade inicial **confirmada por FILL** e o runner mínimo do plano; respeita cada `INITIAL_POSITION`/`REMAINING_BALANCE` da PRE1. Para 100 unidades, 50%, 60%, 70% sobre saldo remanescente produzem saídas 50/30/14 e runner 6. ACK não conta como fill; timeout UNKNOWN não libera reserva; cancelamento libera só saldo pendente. Essa contabilidade é hipótese sem execução de exchange, não protege contra encerramento inverso na Binance/Bybit real nem valida precisões, custos, funding, stops, margem ou alavancagem 50x.



## J2/PRE2 #172 — hipótese A de rompimento pós-compressão, estritamente sintética

O módulo `synthetic_entry_hypotheses.py` reutiliza `compute_synthetic_features` (J2/PRE1) e avalia a hipótese **A**, não comprovada: em uma série `ClosedCandle` com `quality=synthetic_fixture`, uma barra fechada cruza **estritamente** o máximo/mínimo das N barras anteriores, permanece do lado correspondente da EMA e possui volume cotado da própria série acima de um multiplicador configurado. Para qualificar a compressão, exige média ATR Wilder **positiva** das `compression_bars` imediatamente anteriores ao candle e compara com a média ATR positiva de `baseline_bars` **ainda anteriores**, sem sobreposição ou acesso à ATR do candle candidato. Se uma janela não está aquecida, não há sinal. `max_atr_ratio` em (0,1], `min_quote_volume_ratio` >=1 e `cooldown_bars` não negativo são parâmetros de HIPÓTESE explícitos, nunca calibrados por desempenho. O cooldown filtra candidatos de pesquisa próximos, não define carteira ou limite de posições.

Saída `SyntheticEntryResearch` / `SyntheticEntryCandidate` conserva horário de fechamento/instante mais cedo de pesquisa (fechamento + margem de segurança), símbolo, timeframe, lado LONG/SHORT, barreira anterior, EMA, médias ATR e razão de volume. **Não** gera ordem, probabilidade, edge, PnL, expectativa ou decisão operacional; `approved_for_signals=false`, `approved_for_live_use=false`, `order_capable=false`, `orders_sent=false`. Não habilitar sinais reais antes de J1 dados canônicos/licenças, validação fora da amostra e risco J3/J4. Uma observação que parece rompimento em OHLC fictício não demonstra rentabilidade real.



## J3/PRE3 — separar treino e teste sem escolher parâmetro pelo futuro

A hipótese J2/PRE2 pode futuramente ser examinada em folds walk-forward, mas `synthetic_walk_forward.py` **apenas** estabelece janelas temporais com embargo simples e teste não sobreposto. Os thresholds e testes fora da amostra continuam não validados: não retroajustar parâmetros após observar o OOS do MESMO fold; não chamar separação temporal de estratégia rentável; nenhum sinal para exchange. Gaps entre treino e teste evitam usar candle não fechado sob `close_safety_ms`; isso não resolve sobreposição de labels de trades sem horizonte explícito, nem viés de seleção/dados. J3 #4 e J2 #3 seguem abertas.


## J3/PRE5 #178 — contrato de aproximação da hipótese J2 ao OOS

`synthetic_oos_replay.py` coordena **somente pesquisa sintética**: usa a hipótese A já existente, o plano causal PRE3 e a purga/censura PRE4, sem reimplementar EMA, ATR, volume ou rompimentos. Para cada candle OOS elegível, recalcula J2 exclusivamente a partir do prefixo até seu fechamento; registra abstenção ou candidato emitido naquele candle. Só depois observa `close[i+h]` e classifica direção relativa como alinhada/contrária/estável, com identidade, índice e UTC auditáveis. O método não refaz o treinamento, não escolhe parâmetros, não impede dependência dos labels entre si e não calcula retorno, PnL, custo, slippage ou fill. Reavaliar hipótese com dados reais canônicos, composição histórica, autorização de uso e teste financeiro é obrigação futura. Não conectar esse relatório PAPER à automação de ordens de D77.

## J3/PRE7 #184 — ciclo causal com abstenção explícita

Com `close_safety_ms=1000`, a abertura da barra imediatamente posterior ocorre 1 ms após o fechamento e não é elegível para um candidato disponível 1000 ms depois. PRE7 seleciona a primeira barra posterior realmente elegível ou abstém; nunca retrodata o plano. Cenários STOP/TARGET/LIQUIDAÇÃO são hipóteses externas e alternativas, nunca escolhidas pelo fechamento futuro.

**Revisão do isolamento OOS:** o horizonte usado para examinar as barreiras não pode ultrapassar `i + horizon_bars` nem `test_end-1`. Se `close_safety_ms` deslocar a primeira barra inteira elegível para depois desse limite, o evento é recusado. Não interpretar uma observação LONG/SHORT ex-post do PRE5 como autorização para manter posição depois do fold. A entrada financeira segue hipótese explicitamente timestampada no OPEN da primeira barra elegível, nunca um preço obtido da vela anterior como fill comprovado.


## J4/AUTO7 #188 — isolamento do sinal de entrada PAPER

A emissão da hipótese J2 na barra fechada não é ordem nem evento financeiro. AUTO7 recalcula a hipótese apenas sobre histórico fechado **até a última barra passada pelo chamador**, com relógio exato (`close+safety`) e nunca escolhe parâmetros pela direção futura de PRE5. Se não houver candidato na barra atual, históricos anteriores são ignorados. A proposta de intenção PAPER exige quantidade, mark, exposição, saldo de risco, janela de observação e limites **explicitamente sintéticos**; nenhuma dessas grandezas é inferida de um resultado PRE7. Sinal estável por venue para deduplicação não valida mercado real, nem é critério de trading aprovado.


## J3/PRE15 #290 — risco condicional sobre margem solicitada, não retorno

O laboratório combina a razão de perda hipotética por cenário PRE6 com margem e alavancagem declaradas, não colateral da corretora. Para múltiplos níveis OHLC atingidos, o envelope avalia o pior e o melhor, sem selecionar o alvo ou somar alternativas como trades. Taxas e slippage adicionais são hipóteses adversas sobre a matemática PRE6, não fills. 50x magnifica a importância da validação; permanece proibido inferir probabilidade de liquidação, performance OOS ou pronto para live. Direito de dados, instrumento, mark, funding, manutenção e liquidação reais continuam pendentes.


## J3/PRE16 #293 — preço de marcação versus trade em trajetória explícita

Uma posição sintética a 50x pode atingir uma condição hipotética de manutenção mesmo quando o TRADE mostra alvo favorável: MARK governa equity e manutenção antes de qualquer indicação de alvo no mesmo tick. Replays usam timestamps explícitos e funding declarado estritamente anterior ao tick; STOP/TARGET no trade usa o preço declarado, nunca preço-limite inferido em gap. Caso a condição de liquidação hipotética ocorra, o motor retorna sem fill/PnL realizado. Nenhum desses sinais é equação de liquidação da Binance/Bybit nem demonstra edge; J3 financeira real depende de mark, tiers, fees, funding e preço executável verificados, dados J1 autorizados e validação OOS.


## J3/PRE17 #295 — exposição e concentração não equivalem a proteção

Em duas posições fictícias de 200 unidades quote, uma LONG e outra SHORT no mesmo ativo, exposição líquida assinada pode ser zero, mas exposição bruta continua 400. A perda de margem hipotética de um bucket a 50x não pode ser neutralizada pela equity positiva do outro quando o modelo está explicitamente em modo isolado. Coestresse é só observação de movimentos MARK desfavoráveis simultâneos, não coeficiente de correlação, cobertura de hedge nem evidência de desempenho OOS. A simulação interrompe o conjunto no primeiro gatilho terminal, retendo estados simultâneos sem inventar PnL agregado ou futuro após encerramento.


## J1/PIT1 #306 — proxy de volume quote não é estratégia vencedora

Para pesquisa multiativo, a ordenação local de 24 candles de 1h anteriores à decisão, em quote USDT sem conversão cambial, é apenas **estatística descritiva da amostra retida**. Não usar candle que abre na hora da decisão, não classificar dados faltantes como zero, não preservar universo retroativamente a partir da lista disponível hoje e não supor que uma posição alta em volume gera compra, retorno positivo ou liquidez executável. `historical_top50_verified` e `financial_backtest_approved` continuam FALSE. Dataset Vision nunca alimenta ordens live.


## D177 — desbloqueio de pesquisa independente do gate de trading real (30/10/2026)

**Decisão fechada:** Bybit continua candidata preferencial para feed prospectivo, usando WS/REST/cache local, sem considerar `10006` resolvido. Binance Vision previamente retido pelo titular fica restrito à pesquisa pessoal offline não produtiva, sem alimentação de sinais/live. J1 #319/#217 permanecem gates operacionais de dados/identidade/direitos. A execução automática permanece objetivo final (D77), mas nenhuma ordem live, testnet, deploy ou credencial foi ativada. J2/J3 podem pesquisar offline sem esperar homologação integral do Top50 de produção. Não exigir novo `prossiga` para tarefas seguras em sessão.

A biblioteca `vision_dynamic_replay.py` reutiliza candles já auditados por `offline_vision_month` e `offline_vision_series`, e gera replay determinístico de decisões com volume de cotação USDT em 24h FECHADAS para uma amostra de até 50 contratos, por prefixos, em até 720 decisões. Flags de Top50 de mercado, origem autenticada, direitos live, backtest financeiro aprovado e ordens continuam negativas. Testes de alinhamento, relógio, duplicata, determinismo, não-lookahead e recursos. **Não é autenticação de fonte ou universo histórico global.**


## J2/J3 #357 — avaliação causal mensal de hipótese líquida, somente pesquisa (30/10/2026)

`vision_costed_oos.costed_vision_monthly_oos` reutiliza séries de meses Vision previamente inspecionadas, alinha múltiplos ativos e ranqueia pela soma das últimas 24h de volume cotado fechado. Regra fixa de tendência/contratendência é selecionada exclusivamente no histórico anterior, com alternativa de permanecer em caixa se não houver valor líquido hipotético positivo; o mês atual nunca treina sua própria escolha. Entrada hipotética no open do candle seguinte, saída no close, taxa/slippage hipotética agregada em bps por lado, benchmark buy-long e drawdown proxy. Não incorpora mark, funding, intrabar, slippage reais, liquidação, alavancagem, fills executáveis, custos de portfólio nem valida edge; `financial_backtest_approved=false` sempre. Não encaminhar a sinal real, ordens ou conta. Amostra restrita ao dataset local; sem autenticação de fonte, direitos de live ou Top50 de mercado. Sem downloads, storage, deploy ou novos gastos.


## J3/STRESS1 #359 — limites intrabar OHLC condicionais (30/10/2026)

`vision_intrabar_stress.py` introduz estresse matemático estritamente offline para uma barra Vision, com margem sintética, alavancagem fixa por avaliação, stop, target, limiar de liquidação proxy por equity e manutenção hipotética, funding assinado e custos Decimal por lado. Como OHLC não informa a ordem dos eventos, retorna **dois limites condicionais**: downside (liquidação/stop antes de target) e upside (target antes de stop), marcando ambiguidade e toques simultâneos. A marcação e a fórmula de liquidação reais da corretora NÃO são inferidas. Não há integração com execução nem estimativa de perda garantida. `financial_backtest_approved=false`, nenhuma ordem, rede, licença, dado canônico ou homologação Top50. Testes de 50x/1x, long/short, ambiguidade, taxa, funding e corrupção. A integração com seleção OOS mensal e CLI é **pendência da issue #359**, não alegar entrega completa.

## J3/PRE21 #407 — OOS mensal condicionado por OHLC

O avaliador OOS mensal usa escolha causal compartilhada, mantendo o proxy open→close legado e adicionando apenas a visão opt-in de estresse. Cada barra exposta preserva ambos os ramos OHLC adverso/favorável; abstenção não ganha PnL. Toques simultâneos de stop, alvo e liquidação proxy são ambíguos, não vitórias. Ver `docs/J3_PRE21_MONTHLY_INTRABAR_OOS.md`.


## #359 — ligação de stress à seleção mensal OOS sem refitting (30/10/2026)

`vision_stress_oos.audit_costed_vision_intrabar_oos` chama o avaliador causal mensal de J2/J3 para congelar a regra exclusivamente treinada no mês anterior e, no mês OOS, estressa o candle selecionado com os limites condicionais OHLC adverso/favorável da etapa STRESS1. Retorna contagens agregadas de exposições, toques ambiguamente ordenados, condições de liquidação hipotética e resultados condicionais quote do modelo (sem garantia de perda executável). Não refaz ranking com futuro, não otimiza parâmetros no mês de teste, não publica OHLC/ativos ou preços. Não é backtest financeiramente homologado, execução, feed live, autenticação Binance nem validação Top50. A CLI privada ainda não publica a nova modalidade; issue #359 continua aberta até integração final e gates.


## J3/ROBUST1 #367 — sensibilidade de risco OOS em cenários privados

A auditoria `vision_risk_sensitivity.py` reutiliza a mesma seleção mensal OOS causal e compara base, custos/manutenção adversos e duas hipóteses de funding assinado. As quatro saídas são ramos de **simulação**, não quatro operações ou previsões. Uma alta de taxas não deve melhorar o envelope sob funding constante; funding com sinais opostos pode favorecer LONG e SHORT de modo diferente, logo não se conclui monotonicidade universal. Sem mark, ordem intrabar, preço executável, financiamento liquidado ou tier real de margem, não promover resultado a PnL, retorno esperado ou sinal live. Contrato e CLI opt-in em `docs/J3_ROBUST1.md`.


## J3/PRE17 — margem de manutenção sintética por nocional e ponto no tempo

Manutenção pode ser testada por faixas de nocional de marcação, taxa e dedução contínua conhecidas no instante do tick, sob snapshots `fixture_...` versionados. Trade aciona apenas stop/target; mark calcula equity e condição de liquidação hipotética, sem preço de fill, trajetória intrabar ou fórmula da corretora. Dados desconhecidos/futuros e períodos sem ticks suficientes falham quando configurados os gates; nunca inferir funcionamento real de margem cross ou alavancagem 50x. Issue #369.


## J3/PRE18 — ausência de settlement não implica financiamento zero

No replay causal, a grade de eventos de funding é fixture explícita e opt-in. Sem evento para um horário da grade, recusar a simulação em vez de assumir custo zero. Eventos com horário igual a marcação de tick não possuem ordem verificável; recusar. Rate, nocional, preço de mark, manutenção, fees e slippage reais continuam independentes da grade, sem inferência de PnL ou ganho. Issue #371.


## J3/PRE19 — visão de carteira com perdas desconhecidas

A soma de posições fictícias só é coerente com um relógio e uma moeda sintética em comum. Equity por mark e valores condicionais após stop/target não constituem PnL de fills. Se uma posição é liquidada no modelo sem preço de saída certificado, a carteira perde estado financeiro completo: não substituir por zero, margem perdida ou ganho presumido. Drawdown é apenas de prefixo verificável, e correlação pós-amostra entre séries de mark é descritiva, não decisão de entrada. Não pressupor diversificação garantida, 50x viável ou execução real. Issue #373.


## J3/PRE20 — risco de carteira não deve ser ocultado por hedge

Para long e short simultâneos, exposição bruta por marcação permanece alta mesmo quando líquido assinado é zero; dois limites são avaliados independentemente. Margem e alavancagem são fixadas para cada posição na abertura; saídas condicionais não geram automática liberação de margem ou trading. Breach de concentração, nocional por ativo e drawdown do prefixo bloqueiam nova pesquisa de entrada. Uma liquidação hipotética sem preço de fill torna desconhecido o PnL/equity de carteira, e nenhuma decisão de entrada recebe autorização. Isto é gate para pesquisa, não execução nem homologação J3. Issue #375.


## J4/RUNNER1 — trailing do runner residual (somente PAPER)

Depois de preenchimentos confirmados das tranches e sem reservas/UNKNOWN, a parcela residual configurada pode ser observada por trailing sobre mark sintético. LONG ratcheteia stop para cima com máximo favorável; SHORT para baixo com mínimo favorável. A ação resultante é sinal de pesquisa `TRIGGERED_HYPOTHETICAL_ONLY` e não ordem, fill, PnL ou stop garantido. Antes de confirmar runner, status `WAITING_FOR_CONFIRMED_RUNNER`. A política não altera posição, margem, alavancagem, ledger, nem autoriza capital real.


## J5/PRE14 — apresentação de runner não altera a estratégia

Mostrar se as parciais foram preenchidas o suficiente para deixar o runner residual no PAPER; em qualquer caso informar ausência de stop confirmado. A UI não calcula preço de disparo, não altera percentuais, não reativa trailing após restart e não pode transformar status confirmado do runner em permissão de trading. O cálculo J4/RUNNER1 permanece separado e puramente hipotético.



### J3/PRE22 — sensibilidade financeira sem seleção retrospectiva

Para um conjunto OOS com decisão por 24h já fechadas, manter regra/ativo/direção congelados entre cenários de custos, margem e alavancagem. `VisionStressAssumptions` modifica somente as hipóteses do ramo financeiro de `stress_vision_candle`, nunca os candles ou a escolha de oportunidade. O relatório registra perdas condicionais, ambiguidade, liquidação proxy e abstenções por fold; variações de alavancagem ou exposição não permitem supor monotonicidade de retorno. Desautorizar ranking de melhor configuração pós-teste, ROI de carteira, aprovação de PnL, segurança 50x ou sinal de execução. Contrato `docs/J3_PRE22_OOS_STRESS_SENSITIVITY.md`.


### J3/PRE23 — comparar alavancagem sem escolher vencedora pós-amostra

A CLI privada usa o histórico Vision já auditado e a mesma regra causal OOS treinada antes do mês de teste; varia somente o multiplicador 1x vs Nx sobre igual margem/termos, com nocional coerente em cada cenário. A diferença no resultado financeiro é hipotética e não implica segurança de 50x, retorno realizado ou melhor configuração. A escolha causal da entrada e a classificação de risco permanecem separadas de qualquer autorização real. PRE23 é opt-in exclusivo de pesquisa, contrato `docs/J3_PRE23_PRIVATE_OOS_LEVERAGE_CLI.md`.


## J3/PRE24 #413 — integridade de decisões OOS, 31/10/2026

Partindo de main 97a990c2f62fa6888e80c1c509df1ab453da7d8d (PRE23/PR #412 integrada, zero PRs abertas), PRE24 corrige a insuficiência de comparações por contagem: fingerprints de decisões OOS por fold e global permitem detectar seleção diferente com exposição igual; PRE22 falha fechado quando houver discrepância. Relatório aditivo inclui drawdown e perda máxima por margem, preservando digest financeiro PRE21. Branch work/j3-pre24-oos-decision-fingerprint-risk; issue #413. Testes/CI/revisão/merge dependem de evidência de execução, sem alegação antecipada. J1 #2/#319: worker agendado às 15:00:15 UTC, conclusão não verificável pelo GitHub, sem reiniciar. Sem dados reais, VPS, ordens, credenciais, deploy ou custo.


## J3/PRE25 #415 — benchmark LONG pareado por exposição, 31/10/2026

Base `main=fea791dfd6dfb565a5254e4bb6dbb137cc2762ca` com PRE24 #413/PR #414 integradas, todos gates pre/postmerge verdes. PRE25 adiciona LONG contrafactual nos **mesmos** ativos/barras de exposição da estratégia, reutilizando envelope LONG já calculado, sem substituir LONG integral, sem retreinar regra OOS, alterar fingerprints PRE24 ou digest financeiro legado PRE21. O relatório por fold/agregado e em PRE22/PRE23 inclui exposições, ambiguidade, toques stop/alvo/liquidação proxy, riscos condicionais e deltas adverso/favorável; não confundir deltas com alpha, fills, retorno composto ou vantagem comprovada. Testes de tendências sintéticas, LONG, reversão SHORT, abstenção, custo 1x/50x, privacidade. Issue #415 e branch `work/j3-pre25-exposure-matched-oos-benchmark`. CI/revisão/merge sujeitos a comprovação; J1 #319 worker VPS continua sem resultado verificado, sem coleta ou acesso remoto novo. Sem ordens, contas, testnet/live, deploy ou gasto adicional.


## J6/PRE10 #417 — matriz integrada de interrupção causal PAPER (31/10/2026)

Base confirmada `main=87f6221c82c4f38a6307a2daaf023ed26aeb21e8`, zero PRs abertas antes da tarefa. A demo existente `scripts.demo_full_offline_paper_lifecycle` agora usa auditoria AUTO8 e PRE8, operador AUTO6 e ramo AUTO4 descartável com FILL divergente para afirmar bloqueio nas fronteiras J2/AUTO2/AUTO4/REDUCE_ONLY/runner sem alterar caminho de sucesso. Sete checkpoints sanitizados `interruption_checks`; testes de determinismo, contadores, travas de native stop/live e auditor adulterado. Issue #417; branch `work/j6-pre10-causal-interruption-matrix`. CI, PR, revisão e merge somente após evidências no SHA exato, sem promessas antecipadas. J1 #319: worker VPS agendado no último registro mas sem resultado privado verificado, não reiniciar/coletar. Sem conta, rede, ordens, deploy ou gastos.


## J6/PRE11 #419 — cutoff causal e recuperação em PAPER, 31/10/2026

Base verificada `main=97840c8f4245ed7692b372d06ed68b611c50cbab` (J6 PRE10/PR #418 integrada, CI pós-merge verde, zero PRs abertas). PRE11 implementa fail-closed em snapshot futuro AUTO2 cursor/pause no status de operador e recuperação; runner-close PENDING/FILLED com cutoff antigo; classificação de incidente RUNNER2 com AUTO4 posterior ao cutoff. Testes adversariais de instante anterior/igual, recusa de leitura retrocausal e imutabilidade do diário. Issue #419 branch `work/j6-pre11-causal-recovery-cutoff`. CI, revisão e merge dependem de evidência verificável. J1 #319 permanece sem resultado auditado da tentativa VPS; sem novo GET, restart, trade, credenciais, release, deploy ou gasto.


## J6/PRE12 #421 — sanidade temporal completa de eventos AUTO2, 31/10/2026

Base real `main=386e364eeebfb70583b7f38bedac87444a71829d` com PRE11 #419/PR #420 integrada, testes Linux/Windows/Chrome verdes e zero PRs abertas no início. PRE12 fecha lacuna em `paper_operator_status`: cursor e pausa estavam limitados pelo cutoff, mas o scan de OPEN/REDUCE_ONLY ainda aceitava snapshots de FILL/eventos futuros. O scan agora valida `created_at_ms` e `snapshot.as_of_ms` de **todas** as intenções AUTO2 sob a mesma transação read-only, antes de calcular pendência. O modo sem cutoff permanece compatível. Recuperação anterior usa o novo bloqueio e a demonstração PAPER acrescenta dois checkpoints de impossibilidade retrocausal (abertura e runner). Testes com SQLite, abstinência de rede, sem writes e saídas sanitizadas. Issue #421 e branch `work/j6-pre12-auto2-event-causal-cutoff`. CI e merge ainda exigem evidências; nenhuma VPS, coleta J1, conta, ordem, testnet/live, release, migration ou gasto.


## J3/PRE26 #423 — diagnóstico adversarial OOS/risco multicenário, 31/10/2026

Base observada `main=bdb7fcdd7474a842e46eeb2c71249ec933b1bf95`, zero PRs abertas; J6 PRE12/PR #422 integrada e CI pós-merge verde. PRE26 introduz política tipada com limites de amostra, liquidação proxy, ambiguidade, perda por barra, drawdown e ramo adverso por fold **para cada cenário** PRE22, sem aceitação por média ou cenário melhor. Verificações de integridade cruzam contagens OOS, matched LONG e fingerprints. CLI privada reutiliza grid 1x/Nx já calculada, com opt-in e limites obrigatórios; sem novo acesso a arquivos privados. Testes para 1x/50x, tendencia sintética, flat/zero exposição, taxas, permutação, falsificação de fingerprint, limites inválidos e privacidade. Issue #423, branch `work/j3-pre26-robustness-oos-screen`. CI, revisão e merge não presumidos; J1 #319 sem resultado verificável VPS. Sem mercado, ordem, testnet/live, migration, release, deploy ou gasto.


## J3/PRE27 + J6/PRE13 — caminhos intrabar e stop ausente (#425), 01/11/2026

Base verificada `main=5c59103fa0718ed80e8e4bcb29daa40c6825eee1`, 0 PRs abertas; PRE26 #423/PR #424 integrado, Linux/Windows/Chrome verdes. PRE27 adiciona simulação determinística e explicitamente condicional em dois caminhos intrabar e dois estados hipotéticos de STOP, com custos, margem, funding e limiar de liquidação proxy PRE21. Agrega por fold/scenario nas decisões causalmente congeladas PRE22 (fingerprint e contagens validados), mede diferença frente ao pior envelope PRE21, sem trocar estratégia. Novo opt-in no replay privado `--audit-oos-path-outage` só com par 1x/Nx, sem novos arquivos. J6/PRE13 adiciona contrafactual isolado à demo PAPER sem injetar ordens/fills de execução. Testes LONG/SHORT, ambiguidade, piora por outage, 1x/50x, custos, permutação e integridade OOS. Issue #425 e branch `work/j3-pre27-stop-outage-intrabar-paper`. Aguardar CI e revisão SHA antes de merge; J1 #2/#319 permanece sem evidência privada de execução VPS, nunca reiniciar. Nenhum GET de mercado, trading real, testnet/live, credenciais, deploy, migração ou gasto.


## J1/EXIT5 #427 — recuperação da prova VPS de 50 ativos (01/11/2026)

Fatos comprovados: o usuário rodou diagnóstico read-only na VPS; `capture_exit_code=1`, `audit_exit_code=0`, 50 ativos, 36.000 candles 1h, 720h cada, 50 páginas, PIT único `2026-10-31 15:00 UTC`, `sqlite_integrity_passed=true`, `private_page_replay_passed=true`. Erro factual: `provider_rate_limit_no_retry`, retCode `10006`, etapa `closed_kline_24h`, após 157 GETs, captura já encerrada. A VPS estava no checkout `c852c4002b84b74be24b1dd986154c242971d09e`. Nenhuma mutação/GET foi executada nesta sessão pelo assistente. O caminho antigo `resume_private_bybit_j1` suporta apenas 13 ativos, então EXIT5 amplia para 50 dentro de `expanded-52` e catch-up de janelas 1..72h, preservando 720h iniciais. Dados existentes, ranking, flags live, e PIT atual não são presumidos marketwide. Issue #427, branch `work/j1-exit5-resume50-bounded`. CI e revisão obrigatórias antes do merge, sem deploy automático remoto. J1 #319 ainda aberta até 2 PIT posteriores reais confirmados pelo auditor VPS.


## J1/OPS3 — precondição de sinais com WS confirmado

Somente candles 1h confirm=true recebidos depois de inscrição validada podem alimentar o ranking local causal da OPS2. Dados incompletos/fechamentos perdidos impedem ranking e sinais; não usar ticker móvel nem candles abertos. O supervisor WS de pesquisa não habilita negociação live.
