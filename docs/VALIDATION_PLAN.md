# Plano de validação e gates

Toda entrega deve vincular issue, PR, SHA, testes reais e limitações. Implementação não é evidência de retorno financeiro.

- J0: documentos e decisões coerentes, testes de integridade documental e backlog rastreável.
- J1: fixtures de APIs, UTC, fechamento de vela, limites de requests, símbolos elegíveis, falhas, backfill, lacunas, duplicatas e histórico ponto-no-tempo. CI deve permanecer offline. Smoke live exclusivamente GET público, sob comando explícito restrito ao proprietário na issue #19, 1 símbolo/3 candles/3 min, sem credenciais e fora do gate automático. Registrar URI do run, horário, resultado, erros de acesso/DNS/região/429, parâmetros e limitações; não aceitar J1 integralmente só por teste pontual.
- A J1 Kraken independente exige um probe real com contagens e taxonomia crypto-only verificada, ticker/volume cotado comparável, precisão do contrato e fechamento temporal de velas. Não inferir Top50 nem histórico ponto-no-tempo de um endpoint de instrumentos que inclui ativos tokenizados.
- Gate adicional J1: Kraken inclui tokenizados. A classificação crypto-only deve excluir ativos TradFi, demonstrar tags/categorias observadas e confirmar volumeQuote/unidades de contrato; nenhuma inferência de universo Top50 por prefixo PI_/PF_.
- J2: cálculos de indicadores conferidos por referência independente, sinais sem look-ahead, equivalência entre histórico e tempo real, deduplicação.
- J3: testes numéricos de margem, taxas, slippage, funding e liquidação. Se o caminho intrabar for incerto, usar dados mais finos ou hipótese conservadora; uma posição liquidada antes do alvo não é vitória. Walk-forward, fora da amostra, benchmarks, reprodutibilidade e avaliação da carteira.
- J4: percentuais sobre inicial e restante, sequência 50% / 60% / 70% deixando 6%, idempotência, arredondamento, runner, trailing e reconciliação financeira.
- J5: autenticação de dados de usuário, PT-BR, responsividade, acessibilidade e alertas sem duplicação.
- J6: dry-run prolongado sem ordens reais, observabilidade, reconciliação e recuperação após falhas.
- J7: experimentos de ablação comparando baseline, derivativos, ML e contexto. Aceitar somente melhorias fora da amostra.

CI verde e retorno histórico alto nunca comprovam lucratividade futura ou prontidão completa do produto. Mudanças financeiras exigem testes de regressão e análise de segurança.
