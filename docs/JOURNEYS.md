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
- WU17 #48 / PR #49: matriz de direitos de dados Kraken e gate de release integrada SHA `4d06ce7fee2ddb459fbf08a7efa98d6d2bff4997`, CI 213 testes/12 docs; issue permanece aberta para eventual permissão externa aplicável.

- WU18 #50 / PR #51: parser Bybit V5 linear de OHLCV sintético com volume-base e turnover USDT/USDC, integrado SHA `6f147844a514f2b83b29084fb3bc5d4b2377355d`, 229 testes offline/12 docs; nenhum GET ou direito comercial adquirido.

- WU19 #52 / PR #53: gate técnico de finalidade/provedor/dataset integrado, merge `f19ce8b854bd024e22ccaf6bc6b0d276b70efec2`; CI #40205837293 SUCCESS, 240 testes offline segundo revisão.
- WU20 #54 / PR #55: relatório offline conservador de prontidão J1 integrado SHA `7c0642d2d2769a8d12f5651af3f7280fce06ed88`, CI #40209121605 SUCCESS; nenhum Top50 real ou OHLCV canônico aprovado.
- WU21 #56 / PR #58: validador offline de proveniência, digest, tempo e unidade cotada por provedor integrado SHA `c73817ddda007355696ed0649b43c6ca59da9fcf`, CI #40212786207 SUCCESS; nenhuma alegação de dados live, direito ou unidade se torna prova.

- WU22 #60 / PR #61: parser OKX V5 SWAP offline, volumes contratos/base/quote + confirm documentados, integrado SHA `ee8c36d09a90192cbf5220c10ec28b876852508c`, CI PR #40214317197 SUCCESS (279 testes e 12 docs). Nenhuma identidade crypto-only, licença de redistribuição, feed live ou troca de venue validada.

- WU23 #63 / PR #64: manifesto Vike keyless validado no run real `40215045758` job `121234257255` SUCCESS (SHA256 `9329c928aba6fc710a981ee9f985a75006af61147ac887bd960a544a6812ce7a`), issue fechada para diligência de manifesto. Parquet, licença upstream e Top50 não validados.

- WU24 #69 / PR #70: pesquisa de contrato nativo Hyperliquid /info, perps e candles somente por fixtures, integrada SHA `49458f5db870651035d77c2470fe62386cfab652`; CI PR #40217228473 SUCCESS (338 testes offline/12 docs). Não comprova unidade de volume, licença, 5.000 candles reais, identidade crypto-only ou execução. Não muda venue operacional; issue encerrada.

- WU25 #72 / PR #73: run real `40218132668` job `121243633007` FAILURE após primeiro POST /info, `invalid_provider_schema`/1 request; nenhum candleSnapshot executado. Origem do desvio não demonstrada sem corpo de resposta, issue segue aberta sem repetir sondagem.

- WU26 #75 / PR #76: audit read-only de 54 runs issue_comment do GitHub Actions, recuperados IDs/logs originais de Vike e Hyperliquid; CI #40219481048 SUCCESS (378 tests, 12 docs), auditoria #40219481021 SUCCESS, merged SHA `9d20a34404146f3ee7a8290542cd46d519dfb7c7`, issue encerrada. Nenhum novo GET/POST de mercado ou permissão de escrita.

- WU27 #78 / PR #79: correção offline de potencial falso negativo estrutural ao validar metadata nativa Hyperliquid. Integrada SHA `da62b41f69596c756d04cc5188b755bfaa97f862`, CI #40221224643 SUCCESS (387 testes/12 docs), issue encerrada; BTC estrito, outros instrumentos inertes, diagnóstico seguro. Causa do run #72 não comprovada, nenhum novo POST autorizado.

## Preparação independente de J2 (J1 permanece aberta)
- J2/PRE1 #66 / PR #67: motor matemático offline de indicadores causais somente para `ClosedCandle` sintéticos, integrado SHA `cf1c4cacffa4f5b46475a73dcc6bc9f5631b2e5d`, CI #40216432146 SUCCESS (315 testes, 12 docs). Sem habilitar estratégias, backtest, negociação ou antecipar aceite J1/J2; issue encerrada.

## Preparação matemática independente de J4 (J1/J2/J3 e J4 operacional permanecem abertos)
- J4/PRE1 #81: porcentagens INITIAL_POSITION/REMAINING_BALANCE, runner piso da quantidade inicial e conservação exata em Decimal, somente unidades **sintéticas**. Em implementação/CI, não cria ledger de posições, PnL, trailing ou ordens.

A J1 só termina com aceite e evidência; testes sintéticos, CI verde ou ausência de erros de código não comprovam dados live confiáveis nem lucro. Seguir AGENTS.md: avançar sem pedir "prossiga" por microtarefas.
