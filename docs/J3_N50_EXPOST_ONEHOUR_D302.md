# J3/D302 — duas publicações N50 consecutivas e resultado ex post

## Intenção
Construir a primeira ponte reproduzível da J3 para dados reais do N50, ainda como pesquisa privada. A coorte deve possuir duas horas consecutivas realmente publicadas por M1. A escolha é fixada pelo retorno passado em 24 barras fechadas no checkpoint t; o candle seguinte só é usado DEPOIS do checkpoint t+1h para calcular marcação de referência. Não há tentativa de executar operação, inferir fill, lucro, OOS aprovado ou vantagem preditiva.

## Dados e causalidade
O leitor owner-only j3_n50_expost_onehour exige scope D287 vigente e ponteiro D294 com SHA ligado, auditoria D290/D292 de todos os 50 contratos e journal sem gaps/halt/candles parciais, publicação anterior e última com timestamps plausíveis dentro de HH:01..HH:15, última publicação recente, e 50 × 25 = 1.250 linhas verificadas na MESMA transação SQLite read-only. Os primeiros 24 candles por símbolo devem ter sido recebidos até a primeira publicação; o 25º só até a segunda. Todos os candles devem ser consecutivos e possuir hashes corretos. Sem evidência de 2 publicações, o estudo abstém. Não mistura epochs/horas retroativas.

## Modelo observacional de referência
Reutiliza a métrica J2 D300 apenas nas primeiras 24 barras já conhecidas. Ordena os 50 contratos pelo retorno PAST 24h e seleciona N maiores (LONG de referência) e N menores (SHORT de referência), com N de 1 a 25, padrão 5; exibe também benchmark hipotético LONG dos 50. Resultado posterior é 25º fechamento / fechamento em t − 1, nunca visto na classificação. Um notional de 100 USDT por ativo e custos de 6+6 bps fees e 3+3 bps slippage são APENAS premissas de estudo editáveis, não taxas da corretora nem valores recomendados. O custo fixo é debitado por observação em ambos os sentidos, sem financiamento/execução real.

Esses somatórios são exclusivamente marks ex post. Preço de fechamento t não prova preço executável após latência; OHLC não prova caminho intrabar, stop, target ou liquidação. Funding, mark price/maintenance, regras da exchange, correlação de carteira, concorrência de posições e custos reais continuam desconhecidos. Sem OOS purgado ou teste prospectivo persistente, não converter resultado num sinal.

## Integridade e evidências
O relatório por padrão não inclui símbolos; opt-in privado pode mostrar retorno anterior e retorno posterior por símbolo. Sempre retorna financial_backtest_approved=false, out_of_sample_results_validated=false, fill_prices_verified=false, approved_for_signals=false, orders_sent=false, network_requests=0 e database_mutation_statements=0.

Testes POSIX test_j3_n50_expost_onehour.py: 50×25 candles real SQLite de fixtures (1.250), scope, cursor, publicações, recibos antes de sua publicação, SHA, invariância do rank anterior quando o resultado futuro muda, custo matemático exato (40 bps equivale a 0,4 USDT/notional 100 por símbolo; diferença de 2 em 5 e 20 em 50), uma publicação insuficiente, relógio velho, auditor tamper, owner e ausência de campos privados/ordens. **10 testes PASS** na VPS no candidato ca7f513d157673575e6e4b1156afd6d1bc6d4e73. CI Linux/Windows/PAPER, revisão de SHA e merge sem deploy obrigatórios. Só validar sobre dados N50 reais após segundo fechamento, não antecipar resultados.

## Próximo
Adicionar stress intrabar/mark/liquidação, custos/funding verificáveis, walk-forward e avaliação OOS em históricos PIT completos e com rotatividade de coortes; nunca usar isso para trades reais antes de J1–J6.
