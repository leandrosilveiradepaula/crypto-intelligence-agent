# J2 — continuação após correção: motor causal PAPER

Nova hipótese quantitativa **B**, independente da investigação individual de ativos da J1.

**Long:** tendência de EMA ascendente medida apenas em barras anteriores, fechamento anterior recuando até/abaixo da EMA, candle fechado atual retomando acima da máxima anterior e da EMA atual; volume mínimo e extensão máxima em unidades de ATR. **Short:** simétrico. Cooldown opcional. A EMA, ATR e volume são calculados pelo mesmo motor causal já existente.

API `research_synthetic_trend_pullbacks` aceita apenas `ClosedCandle` sintético validado, com dados contíguos, fechamento confirmado e relógio de decisão explícito. Devolve candidatos long/short sem execução, sem conta, sem rede e sem afirmar lucratividade. Não usar o fechamento do próprio candle para simular preenchimento no mesmo instante: uma execução hipotética deve ocorrer depois do sinal.

Validação: `tests/test_j2_trend_pullback.py` (long, short, ausência de correção, sem lookahead, entradas inválidas). Próximo bloco de produto: conectar estratégia B ao mesmo replay offline e ao motor de custos/saídas já existentes, comparar contra estratégia A em amostra fora do período de ajuste. Não confundir aprovação de testes com retorno financeiro positivo.

**Correção de causalidade e regressão CI (11/11):** a inclinação da EMA é medida entre os dois candles **anteriores ao candle de correção**, não entre o candle de correção e o anterior. Incluir o pullback na própria inclinação pode inverter o sinal e eliminar entradas long/short válidas. O candle corrigido e o gatilho atual continuam fechados antes de qualquer candidatura; ATR e extensão preservam validações causais. Primeiro CI apontou 2 falhas nos testes long/short; novo SHA exige suíte completa verde antes do merge.
