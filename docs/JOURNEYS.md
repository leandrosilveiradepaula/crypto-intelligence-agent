# Jornadas — plano de execução

| Jornada | Entrega verificável | Pré-requisitos |
| --- | --- | --- |
| J0 Fundação | Especificações, decisões, arquitetura candidata, backlog e CI documental | Repositório |
| J1 Dados | Coleta de perpétuos, histórico, qualidade e persistência | J0 |
| J2 Entradas | Indicadores, regimes, estratégias e seleção | J1 |
| J3 Pesquisa | Backtest, funding, slippage, alavancagem, liquidação, validação | J1 e J2 |
| J4 Winner Management | Ledger, saídas parciais, trailing e runner | J2 e contratos de J3 |
| J5 Produto | Interface, posições, histórico e alertas | J2 e J4 |
| J6 Homologação | Simulação contínua, observabilidade e evidências; sem ordens reais | J1–J5 |
| J7 Evolução | ML e contexto ampliado, apenas se comprovarem melhoria | J3 e J6 |

Cada jornada tem issue épica, dependências, critérios de aceite, testes e evidências. Desenvolver por work units coerentes, sem pedir nova autorização após microtarefas; bloquear apenas gates realmente necessários.
