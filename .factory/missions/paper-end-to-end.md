# Factory Mission — concluir o primeiro ciclo PAPER público e utilizável

## Contexto e repositório

Projeto: `leandrosilveiradepaula/crypto-intelligence-agent`. Código oficial no GitHub. Ler `AGENTS.md`, `docs/PRODUCT_SPEC.md`, `docs/DECISIONS.md`, `docs/OPERATIONAL_STATE.md` e verificar branch `codex/issue-677-public-kline-session` / PR #734 antes de começar. Não criar PRs pequenos ou forks paralelos. Trabalhar sobre a mesma entrega e preservar a J1.

## Resultado de produto obrigatório

Uma execução PAPER pública finita que percorra a cadeia inteira:

1. Bybit REST fornece histórico N50 da mesma coorte; WebSocket kline confirma 50 fechamentos legítimos da mesma hora; WebSocket ticker tem ACK e BBO causal atualizado.
2. J2 avalia hipóteses e força relativa ao BTC; J3 aplica custos, limites, frescor, risco, alavancagem gravada e abstenção quando inelegível.
3. J4 registra intenção OPEN PENDING em SQLite owner-only, exige novo BBO pós-latência para FILL hipotético, cria posição persistida, reserva saídas parciais ou stop, exige BBO posterior independente para FILL hipotético de REDUCE_ONLY (não só reserva), calcula PnL condicional antes de funding e recupera sem duplicatas em reinício.
4. J5 mostra a posição PAPER e o estado dos feeds, deixando claro histórico versus conexão ativa e falta de stop nativo/ordens reais.
5. Testes finitos sem rede provam o ciclo inclusive recuperação de ticker após falha de estado, perda de ACK, dados inválidos, queda de consumer, restart e ausência de posição quando risco barra. Uma prova pública de VPS demonstra somente o que de fato ocorreu.

## Primeiro bloqueio: D472

A execução D472 de 21/11/2026, SHA `0ef1cd6f8676e82eeeaabd68db988a5445a73ea2`, passou CI e recebeu 50/50 velas e 253.263 cotações; falhou na transição para operação com `ticker_failure_category=invalid_market_data`, sem causa específica no diagnóstico antigo e sem posições. Não atribuir automaticamente essa falha à Bybit. Prioridade técnica: separar falha do parser da falha do callback PAPER, corrigir o mecanismo de ressincronização de frames recuperáveis e comprovar o primeiro journal PAPER realista.

## Conclusão verificável

Aceite apenas com: HEAD conferido, regressões e CI verdes, relatório de teste público sanitizado, contador real de OPEN/PAPER-position no journal, leitura pelo J5, ausência de ordens, custos adicionais R$0 e atualização de STATUS/OPERATIONAL_STATE/DECISIONS. Se nenhuma estratégia passar os filtros, registrar motivo de abstenção (não inventar posição). O deploy permanente e trades reais são gates humanos separados.

## Como invocar quando Factory estiver conectado

`droid exec --mission --auto high -f .factory/missions/paper-end-to-end.md`

O arquivo é a entrada da missão, não prova de que a CLI, uma conta autenticada ou seus créditos já estejam disponíveis. Não executar um Droid pago sem direito existente comprovado e autorização para quaisquer gastos adicionais.
