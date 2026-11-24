# D511 — J3/J5 Scorecard de desempenho PAPER (código, sem release)

## Valor funcional
O painel privado J5 passa a apresentar um scorecard da amostra de posições PAPER visíveis no diário AUTO4: operações CLOSED com FILL e preço hipotético D454, ganhos/perdas, acerto de operações precificadas, resultado acumulado em USDT antes de funding e recuo máximo entre fechamentos. OPEN/PARTIAL não se tornam vitórias, embora possam ter saídas parciais. Nenhum novo ledger, posição, ordem ou regra de estratégia é criado.

## Fonte e limitações
A amostra vem das últimas 50 operações do diário, acrescidas de posições ativas antigas fixadas pelo D505. `total_closed_positions_in_journal` permite indicar quando operações anteriores ficaram fora da janela; nenhuma linha ausente entra como zero. Fechamentos sem FILL precificado não entram nas contas financeiras. A ordenação do drawdown é a data do checkpoint CLOSED; não mede patrimônio ou trajetória intrabar. A métrica é indicativa de pesquisa, não backtest walk-forward/OOS nem resultado líquido na corretora. Funding, liquidação, mark, slippage real e comissões efetivas permanecem desconhecidos.

## Aceite e segurança
- Função pura `paper_closed_scorecard` só consome projeções já validadas; rejeita flags live/ordem, timestamps e decimais inválidos.
- Usa D454 como única fonte de retorno condicional individual, sem duplicar cálculos de taxas ou resultados.
- Endpoint existente `/api/paper-session` agrega `paper_scorecard` sem novo caminho de rede; interface J5 mostra quantidade precificada, vitórias/derrotas, resultado e recuo, com ressalvas explícitas.
- Testes D511 cobrem vitória/perda/posição parcial, amostra incompleta, sem preços, ausência de operações e contratos inválidos. CI e QA mobile precisam passar no SHA final antes de merge.
- Nenhuma mudança em J1, VPS, configuração de estratégia, alavancagem, financiamento, serviço, credenciais, migração ou ordens reais.

## Próximas etapas de produto
Depois de integrar e autorizar release PAPER, acompanhar várias operações genuínas por WS e saídas TP1/TP2. Somente com histórico cronológico mais profundo, candles intrabar e financiamento quantificado realizar validação J3 walk-forward/OOS; não inferir vantagem a partir da primeira operação ARBUSDT.
