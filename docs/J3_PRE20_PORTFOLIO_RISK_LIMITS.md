# J3/PRE20 #375 — gate global de risco em carteira sintética

Implementação **offline e somente de pesquisa**. Reutiliza `replay_synthetic_portfolio` e todas as validações existentes de `synthetic_mark_replay`, funding, margens por tier PIT e cronologia. Não consulta exchange, não calcula ordens nem altera posições.

## Controles explícitos
O contrato `SyntheticPortfolioRiskLimits` recebe limites configuráveis `Decimal` em `SYNTHETIC_USDT`: total de margem inicialmente alocada, margem por leg, bruto de entrada, bruto aberto por marcação, valor absoluto do líquido aberto, maior nocional individual aberto, fração de concentração e drawdown máximo do **prefixo conhecido**, além de alavancagem máxima de abertura inteira. Nenhum limite vem da Bybit ou Binance, e valores das fixtures não são tarifas ou caps reais.

A auditoria reavalia apenas os dados sintéticos conhecidos em cada checkpoint; `entry_...` e `opening_leverage_exceeded` são critérios da abertura e não mudam quando outra posição fecha. `open_...` usa preços de **mark** da observação para exposição bruta/líquida; posições com stop/alvo hipotéticos saem do total aberto, mas seu resultado condicional não vira PnL real. Não se compensam exposições long e short para reduzir o bruto. Para noção individual usa-se `max_open_notional_quote` derivado das legs abertas, não o produto arredondado da concentração. Violações anteriores permanecem registradas de modo conservador nesta execução; não é motor de ordens, nem desenha operações para sanar a violação.

A primeira condição de liquidação sem fill confirmado transforma o estado em `unknown_due_to_liquidation` para esse e os próximos checkpoints. Não se presume perda da margem, liberação de capital, fechamento de legs ou PnL restante. A elegibilidade `new_position_research_allowed` vale **apenas** para avaliar uma nova hipótese offline quando todas as verificações sintéticas passam. É sempre falsa em violação ou condição desconhecida e nunca permite ordens, testnet, deploy ou live. A análise de drawdown é apenas causal em relação ao prefixo dos checkpoints já observados e não supõe trajetória intrabar entre eles.

O relatório `sanitized_report` contém códigos de violação e contagens, sem símbolos, preços, caminhos, IDs, dados de conta ou timestamps originais; digest determinístico para auditabilidade da fixture. `financial_backtest_approved=false`, `net_pnl_verified=false`, `liquidation_formula_verified=false` e `orders_sent=false` invariantes.

## Aceite e limites
Testes `tests/test_synthetic_portfolio_risk_limits.py` e regressões PRE19: carteira LONG/SHORT com net zero e bruto alto, concentração no primeiro e nos demais ticks, limites por margem/nocional/alavancagem, drawdown causal, saída condicional sem dupla contabilização, múltiplas liquidações no mesmo tick com estado irreversivelmente desconhecido, determinismo sob permutação e precisão, proibição de rede e inputs inválidos. Exigir CI docs/Linux, Windows offline, Chrome/PAPER, revisão e SHA final confirmado antes do merge.

A amostra sintética não comprova edge, controle real de risco de um broker, diversificação, execução, rendimento líquido, uso de 50x ou qualificação do Top 50. J1 #2/#217/#319, J2 #3 e J3 #4 continuam abertas; nenhuma mudança de infraestrutura/VPS, autenticação, ordem real ou gasto adicional.
