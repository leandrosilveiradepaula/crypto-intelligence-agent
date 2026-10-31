# J3/PRE21 — avaliação mensal OOS com envelope intrabar condicional

## Contrato

`vision_stress_oos.audit_costed_vision_intrabar_oos` avalia folds mensais já
inspecionados, somente offline. A escolha por barra usa
`vision_costed_oos.causal_oos_bar_choice`: soma volume quote das 24 velas
**fechadas anteriores**, desempata por símbolo e determina direção pelos dois
fechamentos anteriores. A mesma primitiva é usada pelo proxy legado
`costed_vision_monthly_oos`; a visão de estresse não pode trocar ativo,
direção ou regra do fold.

O treino de cada fold termina antes do mês de teste. Ele escolhe continuação,
reversão ou abstenção pelo retorno líquido hipotético de meses anteriores. O
custo `cost_bps_per_side` pertence exclusivamente a essa seleção legada; os
custos de entrada/saída do envelope são os campos explícitos de
`VisionStressAssumptions`, portanto não há cobrança implícita dupla.

Para cada exposição, `stress_vision_candle` produz dois ramos condicionais
OHLC: adverso (liquidação proxy/stop antes de alvo) e favorável (alvo antes de
stop). O relatório por fold e agregado inclui barras, exposições, abstenções,
toques de stop/alvo/liquidação proxy, ambiguidade, retorno quote e retorno por
margem, benchmark LONG condicionado e drawdown de prefixo. Nenhum ramo é fill,
intervalo garantido, preço de mark ou PnL realizado. Uma condição de
liquidação é proxy hipotético e não pode ser vencedora.

## Limites e gates

Margem, leverage (inclusive 1x/50x), manutenção, fee, slippage e funding são
hipóteses tipadas injetadas. Funding não representa settlement; a fórmula de
liquidação de Binance/Bybit, gaps, trajetória intrabar, mark e liquidez seguem
desconhecidos. O contrato falha fechado para estruturas OOS inválidas e não
converte desconhecido em zero.

O relatório sanitizado não expõe OHLC, símbolos, caminhos ou IDs privados e
mantém `marketwide_top50_verified=false`, `source_authenticated=false`,
`financial_backtest_approved=false`, `orders_sent=false` e
`live_trading_authorized=false`. Não há rede, escrita, downloader, credencial,
conta, testnet, live ou uso de VPS.


A revisão de integração acrescenta resultados **líquidos acumulados divididos pela margem fixa hipotética por exposição** tanto em cada fold quanto no agregado: `strategy_worst_cumulative_net_over_margin`, `strategy_best_cumulative_net_over_margin` e equivalentes do benchmark. São somas condicionais por trade em unidade de margem de referência, **não** ROI sobre capital da carteira, nem rendimento composto. Não substituir risco real de liquidação por esses quocientes. Um teste independente confirma seleção por 24 barras fechadas e invariância a mudanças da barra atual/futuras.
