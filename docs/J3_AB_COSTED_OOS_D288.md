# J2/J3 — Comparação A/B no MESMO OOS purgado, com custos hipotéticos (D288)

11/11/2026. Issues #3 (entradas), #4 (pesquisa/backtest). Pesquisa offline.

## Problema fechado por esta entrega

Duas hipóteses já existem: A = \`synthetic_compression_breakout_v1\` (rompimento após compressão de ATR), B = \`synthetic_trend_pullback_v1\` (tendência EMA anterior, pullback e retomada). Testes unitários de cada estratégia não são uma comparação justa; diferentes janelas ou custos mascarariam a diferença. O módulo \`synthetic_ab_costed_oos.py\` combina **os mesmos índices OOS maduros** da preparação PRE3/PRE4 para ambas as hipóteses, sem escolher parâmetros a posteriori.

- Revalida o plano walk-forward completo e o purge do horizonte em cada chamada; erro de fronteira/tempo interrompe a análise. Limita o total de observações ao máximo já autorizado PRE5 (512).
- Calcula um sinal A e um sinal B sobre **exatamente o mesmo prefixo fechado** \`candles[:i+1]\`. Nunca mostra o candle \`i+h\` para os motores de entrada.
- Marca o resultado **ex post**, no fechamento sintético \`i+h\`, com a mesma referência de entrada \`close(i)\`, direção LONG/SHORT e tamanho hipotético. NÃO assume que \`close(i)\` foi preço executável; com \`close_safety_ms\`, a observação só existe DEPOIS do fechamento.
- Usa a infraestrutura \`SyntheticCostScenario\` existente para taxa de entrada/saída, slippage adverso e um evento de funding **inteiramente fictício** no meio do horizonte (quando explicitamente parametrizado). Usa \`Decimal\` exato sem floats.
- Retorna por fold os eventos e abstenções e uma síntese de contagem/variação bruta, custo assumido e variação líquida de marcas. Não mostra os símbolos, não calcula um número de ganhos como previsão nem seleciona um vencedor automaticamente. Eventos de estratégias distintas podem se sobrepor; os somatórios não constituem carteira alavancada.

## Critérios de integridade e limitações

**Não é backtest financeiro homologado.** Não implementa trajetória intrabar, prioridade stop/target, liquidação por mark/maintenance, lot-size, restrições da venue, funding real, regime BTC, correlação, fills, latência nem seleção causal PIT de ativos reais. Não há PnL verificado, sinal autorizado ou ordens. Flags \`financial_backtest_approved\`, \`out_of_sample_results_validated\` e \`approved_for_live_use\` permanecem **false**. O plano e estratégias são congelados pelo chamador; esses testes sintéticos não justificam retorno positivo nem uso de 50×.

A contribuição concreta é evitar comparar A e B em amostras ou custos diferentes antes de integrar mais hipóteses aos dados de mercado.

## Testes / gates

\`tests/test_synthetic_ab_costed_oos.py\` cobre: mesmos índices OOS, abstinência distinta, sinal de pullback, invariância de candidato quando só muda o resultado futuro, mudança de variação líquida diante de taxas/slippage, funding assumido, chamada de ambas as estratégias só com prefixo, plano adulterado, tipo errado, input não-Decimal, determinismo e nenhum acesso à rede/SQLite.

Gates obrigatórios: Linux/docs, Windows/offline e Chrome/PAPER no HEAD final, revisão e squash merge sem deploy. Esta PR não altera nenhum arquivo de coletor J1, serviço/timer, banco de dados, API, credencial ou execução real.

Próximo trabalho J3: acoplar as duas hipóteses ao replay intrabar com mark/funding/liquidação e, em outra etapa, validar por walk-forward/OOS com histórico real de um universo PIT. A coleta N50 D287 na VPS está em jobs **independentes**, sem bloqueio nesta entrega.
