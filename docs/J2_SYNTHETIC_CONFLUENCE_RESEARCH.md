# J2/CONFLUENCE1 — Concordância causal de hipóteses com BTC como veto

## Problema e decisão

Os algoritmos J2 de compressão/rompimento (PRE2), força relativa e regime BTC (PRE3), ranking de rompimentos sob contexto BTC (PRE4) e retomada após correção de tendência existem como pesquisadores de **candles exclusivamente sintéticos**. Antes desta entrega, não havia uma única interface pura que tratasse concordância contemporânea, ausência de segunda hipótese e conflito entre abordagens distintas. O risco seria promover um breakout sem confirmação, usar um pulback antigo como se fosse contemporâneo ou deixar o ambiente BTC reprovado ser ignorado por outro algoritmo.

**Decisão:** compor os motores existentes sem criar nova fórmula, score arbitrário, probabilidade, número fixo de posições ou alvo financeiro. O consenso é só uma **classificação de pesquisa**, não aprovação para sinal ou operação.

## Contrato técnico

Módulo `crypto_intelligence_agent/synthetic_entry_confluence.py`:

1. `SyntheticConfluenceConfig(screen: SyntheticScreenConfig, pullback: TrendPullbackConfig)` exige que BTC, breakout e pullback usem os mesmos períodos de features. Configurações individuais permanecem explícitas, sem hardcodes econômicos novos.
2. `research_synthetic_entry_confluence(btc_candles, asset_series, *, config, decision_at_ms, close_safety_ms=1000)` passa **as mesmas velas fechadas**, horário e margem de segurança aos motores existentes. PRE1/PRE2/PRE3/PRE4 validam por conta própria candles sintéticos, intervalos UTC, continuidade, qualidade, contrato perpétuo, volume, EMA, ATR, rompimento estrito e regime BTC, sem rede ou credenciais.
3. `arbitrate_synthetic_entry_confluence(screen, trends)` é avaliador determinístico de outputs tipados. Exige exatamente uma pesquisa pullback por ativo do screener, venue, intervalo, símbolo, candle fechado e instante causal coincidentes; rejeita duplicação, ranking incoerente, candidato corrente faltante/alterado, recepção futura, side sem enum e versão de estratégia diferente. Histórico de hipóteses anteriores pode ser informado, mas nunca vira voto atual.
4. Para cada membro, a `ConfluenceDisposition` é:
   - `confluent_research_only`: o screener BTC+breakout classificou o ativo e a retomada de tendência gerou **no mesmo último fechamento UTC** uma hipótese na mesma direção;
   - `no_pullback_confirmation`: breakout/contexto BTC classificados, mas nenhuma hipótese de retomada atual;
   - `direction_conflict_abstain`: as duas hipóteses atuais têm sentidos opostos; nunca escolher uma silenciosamente;
   - `btc_or_breakout_veto`: sem breakout atual, regime BTC insuficiente, lateral, estressado, contrário ou força relativa fraca, independentemente de outra hipótese.
5. Somente o primeiro estado entra na shortlist **de pesquisa**, ordenada pelo **ranking PRE4 pré-existente** (força relativa/volume; sem recalcular score). O rank após veto pode ser denso em ordem anterior; não converter a classificação em recomendação de investimento. Todos os outros estados ficam explícitos na avaliação de cada ativo.

Há limite técnico de até 1000 séries sintéticas (da PRE4) e 10 mil velas por série (da PRE1), **não** limite de 50 posições nem objetivo de exposição. O universo N50 operacional J1 não é consumido por este módulo; futura integração exige gate de elegibilidade crypto-only, provenance, direitos, validade histórica e J3 financeiro.

## Segurança e evidências

O relatório `sanitized_report` contém **somente contagens** de disposições, horários sintéticos e flags: `approved_for_signals=false`, `approved_for_live_use=false`, `order_capable=false`, `orders_sent=false`, `probabilities_calibrated=false`, `returns_backtested=false`, `marketwide_top50_verified=false`, `network_requests=0`. Não serializa símbolos nem preços, IDs de evento, credenciais ou suposto resultado.

Teste `tests/test_synthetic_entry_confluence.py`: caminhos end-to-end LONG e SHORT montados com candles sintéticos que satisfazem ambos motores; veto BTC em sideways/stress/contra-regime, comparação de dois ativos sem meta fixa, ranking invariante à ordem, ausência de pullback, abstinência de hipóteses anteriores e de sinais conflitantes, dados futuros/stale, mismatch de venue/interval/feature/clock, IDs duplicados e não-fixture, baixa precisão Decimal e proibição de rede. As rotas `arbitrate` testam inclusive votos conflitantes *deliberadamente construídos em fixture* (não afirmam que a combinação de motores reais produza esse caso).

Merge autorizado sem deploy somente após CI Linux/docs, Windows/offline e PAPER/mobile no HEAD exato e revisão do diff. Manter J2 épica #3 aberta; não provar acurácia, rentabilidade, robustez OOS, segurança de alavancagem, execução venue ou ordens reais. R$0 adicional. Issue #615.
