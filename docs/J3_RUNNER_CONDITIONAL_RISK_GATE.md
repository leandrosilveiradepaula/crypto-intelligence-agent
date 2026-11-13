# J3/PRE29 — veto conservador de liquidação antes do runner sintético

## Motivação comprovada

A J4/RUNNER-COST1 (#607, PR #608) compõe 50%/60%/70% do saldo (50 + 30 + 14) e fecha um runner de 6 unidades com taxas, slippage e funding de fixtures. Ela **não** modela stop, trajetória de mark, margem de manutenção ou liquidação; o campo `liquidation_risk_verified` segue falso. Portanto, seu PnL hipotético pode ser calculado mesmo que uma trajetória de preços de **outro experimento**, previamente declarada, indique condição de liquidação antes da última saída.

A J3/PRE16 já possui `replay_synthetic_mark_path`, onde a prioridade por tick é **liquidação de mark/equity > stop de trade > target de trade**. O objetivo é recombinar os motores existentes de forma auditável, sem duplicar liquidação/custos ou fabricar fills. Não se introduz recomendação, probabilidade de ruína ou backtest intrabar real.

## Contrato `synthetic_runner_liquidation_gate.py`

`evaluate_synthetic_runner_risk_gate(position, partial_fills, runner_receipts, *, entry_reference_price_quote, cost_rates, mark_plan, mark_ticks, as_of_ms, max_tick_gap_ms, funding_events=(), risk_snapshots=None, max_risk_snapshot_age_ms=None)`:

1. Exige tipos exatos, janela de ticks UTC crescente com gap explícito, `as_of_ms = runner_close_ms = ultimo_tick_ms`; todos os fills parciais devem ter **tick de trade exatamente correspondente em horário e preço**, e o runner deve coincidir com o último tick de trade. Não acrescenta fills a partir de marca ou OHLC.
2. Vincula lado LONG/SHORT, horário e referência de entrada, quantidade integral, margem, alavancagem imutável de abertura, moeda sintética USDT e quatro parâmetros fee/slippage iguais entre as fontes J3 e J4. Se o fixture J4 possui margem abstrata sem relação financeira, deve ser construído outro fixture com `margin * leverage == entry_price * initial_units`; não há conversão implícita.
3. Compõe `evaluate_synthetic_runner_costed_closure` para contabilizar **uma vez** o fechamento/fee/slippage/funding do runner; e `replay_synthetic_mark_path` para avaliar uma trajetória declarada com **100% do notional inicial preservado** mesmo após as parciais. Essa exposição integral é um **proxy de estresse conservador**, e não uma simulação fiel de redução de posição; o campo `partial_derisking_in_mark_path_modeled` é sempre falso.
4. Qualquer estado terminal J3 (`LIQUIDATION_CONDITION`, `CONDITIONAL_STOP`, `CONDITIONAL_TARGET`) produz status de *abstenção* e suprime `hypothetical_net_if_no_unobserved_events_quote`. A liquidação é um **veto sintético**, não uma liquidação verificada de corretora; o stop/target é toque condicional, não fill garantido.
5. Apenas se todos os ticks declarados forem `OPEN_UNRESOLVED`, o valor líquido J4 é exposto como **referência condicional**, nunca como PnL realizado. Funding deve possuir IDs/relógios únicos e valor assinado total congruente em ambos os motores; violações, falta de tick, mark atrasado, risco PIT stale ou diferenças de contrato falham fechado.

**Limites essenciais:** ticks discretos não revelam o caminho intrabar, funding/fees de corretora, margem cruzada, mark de bolsa ou execução real. Um resultado condicional sem evento terminal **não prova sobrevivência entre os ticks**, nem segurança a 50x. Veto com posição original integral pode ser mais restritivo que o risco após parcial; sua finalidade é impedir vitórias não verificadas, não estimar taxa de liquidação. Desvios de tempo, preço ou contrato não se corrigem inferindo dados.

## Provas sintéticas

O teste `tests/test_synthetic_runner_liquidation_gate.py` constrói posição fictícia inicial 100 unidades a preço 100, margem sintética 200 a 50x, com saídas 50@101, 30@102, 14@99 e runner 6@103. A conta de taxas/slippage é usada integralmente uma vez (entrada 15, saídas parciais 14,244, runner 0,927) mais funding declarado 1. Bruto hipotético 114, líquido condicional **82,829 unidades de referência**. Não é desempenho de mercado.

Um tick anterior de mark 97 (trade 100), a 50x, faz o proxy atingir `LIQUIDATION_CONDITION` mesmo que as saídas de fixture posteriores pareçam lucrativas: **retorno líquido não é exposto**. Na mesma trajetória a 10x, margem1000, o proxy não atinge o mesmo limiar. Stop/target anterior também veta retorno. SHORT testa direção e crédito de funding, sem somar alavancagem ao PnL. Testes negativos de relógio e identidade, missing tick/price, funding futuro/duplicado, taxas divergentes e risco PIT preservam rejeição. Contextos Decimal de baixa precisão e rede proibida reforçam determinismo.

CI Linux/docs + Windows/offline + PAPER/mobile devem ficar verdes no HEAD exato antes do merge; **sem deploy**, sem posições/ordens reais, nenhuma modificação no J1/VPS. Epic J3 #4 permanece aberta; J4 #5 também permanece aberta. O sistema só poderá aceitar backtest financeiro após trajetória intrabar, execução/custos reais e controles de liquidação/risco verificáveis.

**Decisão J3/PRE29:** nunca promover um runner lucrativo de fixture ao ignorar um terminal de risco observado em uma trilha causal; só mostrar referência líquida condicional quando o proxy declarado não tiver terminal, sem confundir abstenção com previsão ou certificação.
