# Jornadas — plano de execução

| Jornada | Entrega verificável | Dependências | Issue |
| --- | --- | --- | --- |
| J0 Fundação | Especificações, decisões, arquitetura, backlog e CI documental | Repositório | #1 |
| J1 Dados | Coleta de perpétuos, histórico, qualidade e persistência | J0 | #2 |
| J2 Entradas | Indicadores, regimes, estratégias e seleção | J1 | #3 |
| J3 Pesquisa | Backtest, funding, slippage, alavancagem, liquidação e validação | J1 e J2 | #4 |
| J4 Winner Management | Posições, saídas parciais, trailing e runner | J2 e contratos de J3 | #5 |
| J5 Produto | Interface PT-BR, posições, histórico e alertas | J2 e J4 | #6 |
| J6 Homologação | Simulação contínua, observabilidade e evidências, sem ordens reais | J1–J5 | #7 |
| J7 Evolução | ML e contexto ampliado, somente com melhoria validada | J3 e J6 | #8 |

Primeira work unit Codex delimitada de J1: issue #9. Não equivale à J1 inteira.

Cada jornada tem aceite e evidências. Desenvolver em blocos coerentes sem exigir nova autorização após microtarefas. Não confundir CI verde com lucro ou produto pronto.
