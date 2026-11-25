# D535 — recuperação do backtest anual sem repetir D533

## Evidência de execução

D534 integrado em 62275c93ac5ebb35c704173819e4d0fb8cbef3d9, CI 45626662806/45626662887 SUCCESS. Recibo owner 25/11/2026: anual 1h rejeitado antes de progresso, erro DataValidationError; residual 90d/5m completou 288 cenários, 52.283 slots de cobertura pareada em 48h/168h, 66 e 65 cenários positivos respectivamente. Melhor 168h no recibo: sq_w04_v15, runner_25_wide_protected, stop 100bps, 75 caminhos, 33 positivos (incluem marcações), 70 encerrados e 5 abertos, média 60,70bps, PF 1,9184, net pré-funding +22,7638373678 USDT; realizado após custos -8,01721875, não realizado bruto +30,8650846940. Mesmo par 48h +15,4993844399 USDT, média 41,33bps. O relatório privado completo não foi inspecionado; top10 não comprova que TP4 seja inferior em todos os pares. Evidência issue #4 comentário 7167035695.

## Correção

O comando anual forneceu --stop-grid-bps 150, mas D529 reutilizava parse_stop_grid de D520/D524, que exigia dois valores. D535 opta explicitamente por 1..8 stops apenas no replay longo, mantendo o contrato anterior (2..8) para o painel e D520. Regressão com a matriz anual real, 8 entradas x 6 saídas x 5 horizontes x 1 stop = 240 cenários, sinais injetados em dois ativos sintéticos, caminho/custos/contagens/partições reais do motor. Erros da CLI incluem estágio de falha constante, sem mensagem de exceção arbitrária nem dados privados.

## Próxima execução

Após revisão e CI, executar somente anual 365d/1h com stop 150bps, horizontes 48/168/720/1440/2160h, --preserve-recent-90d --separate-open-mark --target-diagnostics. Usar matriz D532 e saídas D533, oito nomes anteriores. Não repetir o residual 90d/5m: ler seu JSON salvo para comparar alvos fixos e residual em pares idênticos. Coleta anual 1h 464770/465609, 839 faltantes; 5m interrompida por retCode 10006 após 356 GETs, checkpoints preservados, cobertura atual desconhecida. Retomar coleta só após quota normalizar, separadamente, lotes pequenos; sem retries após bloqueio. Não inferir funding, liquidação, carteira ou OOS; 50x, sizing adiado, sem ordens, release, J1, perfil ou custo.
