# J3/CONFLUENCE-OOS1 — Ablation OOS da confirmação J2 (issue #617)

## Pergunta de pesquisa
Em oportunidades sintéticas **idênticas**, no mesmo fold e no mesmo candle fechado, quanto se perde ou ganha no **mark ex-post hipotético** quando o screen BTC/rompimento J2 PRE4 exige também o pullback J2 CONFLUENCE1? A comparação responde apenas sobre as fixtures; não demonstra lucro, execução ou previsibilidade.

## Reutilização e contrato
`crypto_intelligence_agent/synthetic_confluence_costed_oos.py` compõe:
- `plan_synthetic_walk_forward` e `purge_synthetic_label_horizons` (com recomputação independente) para treino/gap/OOS, labels maturados dentro do mesmo fold;
- `research_synthetic_entry_confluence` por prefixo `[:i+1]` em BTC e ativos (mesmo UTC), que já compõe screen BTC, rompimento e tendência/pullback contemporâneos;
- `_event` e `SyntheticABCostAssumptions` já existentes em J3 para marks e custos hipotéticos, sem fórmulas paralelas.

Cada oportunidade do calendário OOS considera cada ativo, mesmo quando não há candidato. **Baseline** inclui apenas `breakout_research_rank != None`; **confluência** é subconjunto baseline com estado `CONFLUENT_RESEARCH_ONLY`. Não se fabricam fills para ativos ausentes; a ausência aparece em contagens. Taxas/slippage/funding são fixtures fixas iguais para os braços. Entrada de referência é o fechamento do candle do sinal e saída de referência o fechamento de `horizon_bars` futuros, sem alegar preço negociável. O mesmo evento elegível mantém gross, custos e net, distinguindo só o ID do braço.

Limites: até 1000 ativos sintéticos, 10 mil candles por série conforme PRE1 e no máximo 512 oportunidades ativo × candle OOS; não são limites comerciais ou metas de posições. Todas séries têm venue, market, qualidade, intervalo, UTC de abertura/fechamento e comprimento idênticos, BTCUSDT benchmark próprio. Sem rede, banco, posição real, sinais ou ordens.

## Relatório e critérios de aceite
`sanitized_report` divulga apenas contagem global e por fold, oportunidades, baseline, confluência, exclusões, soma decimal exacta do gross, custos e net ex-post e número de marks positivos. Sem ticker, OHLC, preço de fill, account, sinal ou payload de mercado. Flags `financial_backtest_approved`, `out_of_sample_results_validated`, `approved_for_signals`, `approved_for_live_use`, `orders_sent` sempre falsas.

Testes: `tests/test_synthetic_confluence_costed_oos.py` + regressões J2/J3, `compileall`, docs; CI Linux/docs, Windows/offline e PAPER/mobile no SHA exato, revisão de diff antes de merge sem deploy. Testar resultado mudar ao alterar **somente** candle futuro, while candidate stays; custo maior não inventa nova seleção; planos alterados, duplicatas, contaminação da origem e clocks incoerentes falham fechado.

## Interpretação
Diferença entre somas ex-post com contagem diferente NÃO mede ganho por risco ajustado e nem comprova que confluência aumenta retorno. Próximo experimento legítimo precisa histórico elegível PIT, dados confiáveis, mark intrabar, custos venue, funding, liquidação e robustez OOS independente. J1 N50/24h/36h e crypto-only #319 permanecem gates distintos. Custo adicional R$ 0. Sem deploy ou ordens.