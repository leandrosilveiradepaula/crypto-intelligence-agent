# J3/PRE22 — sensibilidade de OOS às hipóteses financeiras

## Missão e contrato

O avaliador `compare_costed_vision_oos_stress_scenarios` em
`crypto_intelligence_agent/vision_stress_sensitivity.py` compara **2 a 6**
objetos tipados distintos `VisionStressAssumptions` sobre o **mesmo**
histórico Vision offline e o **mesmo** corte temporal `as_of_ms`.

A seleção causal do ativo por 24 horas fechadas anteriores, a direção dos
fechamentos passados e o ajuste da regra `continuation/reversal/abstain` são
inteiramente delegados ao `audit_costed_vision_intrabar_oos` PRE21.
`cost_bps_per_side` é constante para o treinamento mensal, não deve ser
confundido com taxas/derrapagem de execução hipotética em cada cenário.

O avaliador não implementa outra função de custos, um simulador de posições ou
outro ledger. Reexecuta a mesma função PRE21 para cada cenário e exige uma **moeda sintética
comum** entre os resultados em unidades quote (sem conversão cambial), além
de comparar a cobertura de **cada fold**: mês, barras, exposições, abstenções e exposição
do benchmark. Divergência de cobertura causa `DataValidationError`, nunca
uma comparação enganosa. Uma seleção que se abstém integralmente continua
possível e não é promovida a uma estratégia vencedora.

## Evidências sanitizadas

A API `VisionStressSensitivity.sanitized_report()` produz
`j3_pre22_oos_sensitivity_v1`. A lista de cenários preserva a ordem de
entrada, com `ordinal=1..N`; **ordinal não é ranking de desempenho**.
Cada cenário inclui alavancagem hipotética, margem e os parâmetros
numéricos de stop/alvo, manutenção, fee, slippage e funding (todos declarados
como hipóteses), contagens de exposição/abstenção, toques e ambiguidade,
possível liquidação proxy,
ramos líquidos condicionais adverso/favorável em unidades quote e somas por
margem de referência, além de resumos por fold e digest do PRE21.
Os agregados contam cenários com risco de liquidação e com resultado adverso
condicional negativo; não selecionam um "melhor cenário".

Resultados acumulados divididos pela margem usada repetidamente em cada
posição sintética **não são rentabilidade composta nem ROI de carteira**.
Os ramos OHLC não determinam ordem intrabar, fills, mark price, funding de
venue, liquidação real nem limites garantidos de perdas. Quando a liquidação
é impossível de interpretar com dados disponíveis, o comportamento permanece
um indicador de **possibilidade sob a hipótese**, não uma confirmação.

Saída sem símbolos, preços, paths locais, IDs de posições, OHLC ou dados de
conta. Flags negativas fixas: `marketwide_top50_verified`,
`source_authenticated`, `financial_backtest_approved`,
`net_pnl_verified`, `liquidation_formula_verified`,
`live_trading_authorized`, `orders_sent`, `data_stored`. Nenhuma
rede, download, escrita, credencial ou ordem de exchange.

## Validação e limitações

`tests/test_vision_stress_sensitivity.py` cobre alavancagem 1x/50x,
conciliação dos mesmos resultados PRE21, causalidade da cobertura,
determinismo sob permutação de ativos, custos crescentes de um cenário
**com termos base fixados**, entrada duplicada/fora dos limites, proteção
contra deriva das contagens, serialização sanitizada e bloqueio de rede.
Não presumir monotonicidade quando alavancagem/quantidade/direção mudam.

Exigir CI docs/Linux, Windows/offline e Chrome/PAPER no SHA final e revisão
de contratos antes de merge sem deploy.

**J1 #2/#319:** em 31/10/2026 a última evidência fornecida pelo titular
confirmou somente agendamento de worker VPS para 15:00:15 UTC, sem resultado
capturado por este coordenador. PRE22 não observa, agenda, recomeça ou acessa
a captura J1. Mesmo dados novos não validariam automaticamente cobertura
marketwide dos 50 perpétuos. J3 #4 permanece em pesquisa. Nenhum orçamento
adicional, deployment, testnet, live ou operação financeira.
