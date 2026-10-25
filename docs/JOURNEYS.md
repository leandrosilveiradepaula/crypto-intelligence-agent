# Jornadas — plano de execução

| Jornada | Entrega verificável | Dependências | Issue |
| --- | --- | --- | --- |
| J0 Fundação | Especificações, decisões, arquitetura, backlog e CI documental | Repositório | #1 |
| J1 Dados | Coleta de perpétuos, histórico, qualidade, persistência e conformance | J0 | #2 |
| J2 Entradas | Indicadores, regimes, estratégias e seleção | J1 | #3 |
| J3 Pesquisa | Backtest, funding, slippage, alavancagem, liquidação e validação | J1 e J2 | #4 |
| J4 Winner Management | Posições, saídas parciais, trailing e runner | J2 e contratos de J3 | #5 |
| J5 Produto | Interface PT-BR, posições, histórico e alertas | J2 e J4 | #6 |
| J6 Homologação | Simulação contínua, observabilidade e evidências, sem ordens reais | J1–J5 | #7 |
| J7 Evolução | ML e contexto ampliado, somente com melhoria validada | J3 e J6 | #8 |

## J1 — Work units
- WU1 #9 / PR #12: adaptador read-only e contratos, integrada.
- WU2 #13 / PR #14: backfill e SQLite com integridade, integrada.
- WU3 #15 / PR #16: pipeline CLI e auditoria offline, integrada.
- WU4 #17 / PR #18: relógio remoto e gate de diferença, integrada.
- WU5 #19: conformance Binance e evidência de HTTP 451, permanece aberta sem feed live homologado.
- WU6 #23 / PR #24: Kraken Futures independente, GET instrumentos HTTP200 (run 40198042787), 231 instrumentos e 213 candidatos heurísticos; concluída, sem troca de venue.
- WU7 #25 / PR #26/#27: schema real instrumentos/tickers/candles BTC Kraken, run 40198745112 SUCCESS, 3 GET200; encerrada, ainda sem Top50 crypto.
- WU8 #28 / PR #29: taxonomia Kraken observada em run 40199111677 (xStocks com tradfi=false), concluída.
- WU9 #30 / PR #31: seletor Kraken crypto-only fail-closed por registro versionado externo, Decimal USD, CI 115 testes, integrada; não produz Top50 real sem registro.
- WU10 #32 / PR #33: infraestrutura de registro de identidade/sha256 e point-in-time integrada, CI 135 testes; issue aberta para fonte/licença de ativos reais.
- WU11 #34 / PR #35: parser Kraken OHLC fechado UTC, volume bruto não verificado, integrado com 149 testes offline.
- WU12 #36 / PRs #37/#38: diagnóstico real do volume/ticker, run #40201868577 (2 GET HTTP200, 24 barras fechadas); **unidade base/quote ainda não comprovada**, issue aberta.
- WU13 #39 / PR #40: parser Decimal exato compartilhado para volume bruto documentado int64/real decimal-string, integrada, 169 testes offline, run live #40201868577, issue encerrada.
- WU14 #42 / PR #43: gate de 50x global versus cap por instrumento/exposição agregada Kraken, integrado SHA `3f1e829467ada401e607ab6d857751f75ae2903d`, CI 185 testes; só pesquisa.
- WU15 #44 / PR #45: Decimal exato desde JSON e seletor de ticker Kraken sem float financeiro, integrado SHA `c1d2c714d30daefe76804d1ed8d1792b919f8fee`, CI 197 testes offline.
- WU16 #46 / PR #47: cliente Kraken público opt-in GET-only, Decimal/exclusão xStocks, OHLC staging fechado, integrado SHA `6d5b37aba154b0fb6a950fbffa4ba3e18d01410e`, CI 213 testes offline/11 docs.
- WU17 #48: matriz de direitos de mercado e gate para exposição/uso comercial de dados Kraken; documentação em andamento, autorização externa não presumida.

A J1 só termina com aceite e evidência; testes sintéticos, CI verde ou ausência de erros de código não comprovam dados live confiáveis nem lucro. Seguir AGENTS.md: avançar sem pedir "prossiga" por microtarefas.
