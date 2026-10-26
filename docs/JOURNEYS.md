# Jornadas — plano de execução

| Jornada | Entrega verificável | Dependências | Issue |
| --- | --- | --- | --- |
| J0 Fundação | Especificações, decisões, arquitetura, backlog e CI documental | Repositório | #1 |
| J1 Dados | Coleta de perpétuos, histórico, qualidade, persistência e conformance | J0 | #2 |
| J2 Entradas | Indicadores, regimes, estratégias e seleção | J1 | #3 |
| J3 Pesquisa | Backtest, funding, slippage, alavancagem, liquidação e validação | J1 e J2 | #4 |
| J4 Winner Management/Execução | Ledger de ordens/fills, entradas/saídas automáticas, parciais, trailing, runner e reconciliação | J2 e contratos de J3 | #5 |
| J5 Produto | Interface PT-BR, posições, histórico, alertas, estado do bot e kill-switch | J2 e J4 | #6 |
| J6 Homologação | Paper trading contínuo, testnet autorizada, incidentes e gates de eventual live, sem ordens reais na homologação inicial | J1–J5 | #7 |
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

## Preparação independente de J3 (J1/J2/J3 operacionais ainda não homologadas)
- J3/PRE1 #94 / PR #95: detector de toques de barreiras em OHLC SINTÉTICO, com gaps/ambiguidade e liquidação hipotética, integrada SHA `3a30150268d6ead7daabe16884827b655b5b1e7c`, CI #40229271296 SUCCESS (**548 testes offline**, 12 docs); issue encerrada, J3 #4 segue sem aceite.
- J3/PRE2 #96 / PR #97: custo hipotético de fees, slippage e funding assinado em quote ABSTRATA, integrada SHA `ea13ea60c617eb57973a6b6e708b06fc325afc96`, CI #40229681278 SUCCESS (**577 testes offline, compileall, 12 docs**), issue encerrada. Resultado NÃO é PnL, taxas reais ou backtest validado; J3 #4 permanece aberta.

## Preparação matemática independente de J4 (J1/J2/J3 e J4 operacional permanecem abertos)
- J4/PRE1 #81 / PR #82: percentuais INITIAL_POSITION/REMAINING_BALANCE e runner em unidades sintéticas, código integrado SHA `c4f6b94fd5a89724185b9a486818a6c8fa84adf0`, CI #40223997038 SUCCESS (**414 testes offline, 12 docs**). Issue encerrada; sem ledger, PnL ou ordens.
- J4/PRE2 #83 / PR #84: replay offline de eventos manuais FICTÍCIOS com IDs idempotentes apenas em memória, progresso de tranche, timestamp e controle de overfill; código integrado SHA `f051ab5c681bb9b4bd15e0384fb779a142330475`, CI #40224464764 SUCCESS (443 testes offline, 12 docs), issue encerrada. Não é contabilidade financeira real, preço de execução, ordem ou aceite J1/J3/J4.

- J4/PRE3 #86 / PR #87: posição fictícia com leverage_at_open e replay PRE2 vinculado, merged SHA `afb034d3435162402af673a8946bb2d747950326`, CI #40225049332 SUCCESS (473 testes offline, 12 docs), issue concluída. Não atesta posições reais.
- J4/PRE4 #88 / PR #89: auditoria de step/min-exit/residual por regras Decimal **hipotéticas** em planos e fills PRE1/PRE2/PRE3, integrada SHA `677f0c299cbfc1b0dc772f6d5d110a63c277dea9`, CI #40225440872 SUCCESS (**502 testes offline**, 12 docs), issue encerrada. Nunca arredondar nem indicar executabilidade na venue. J4 #5 segue aberta, sem aceite operacional.

- J1/WU28 #91 / PR #92: auditoria fail-closed do escopo documental Kraken Futures PF_ versus Kraken Spot OHLCVT e Derivatives US CME/Bitnomial, integrada SHA `d3af3088088c7e7f638cb745ca5848ddbb2b9a43`, CI #40227134838 SUCCESS (515 testes offline/12 docs). Issue encerrada, sem resolver fonte independente crypto-only, unidade de volume ou licença. J1 #2 e #32/#36/#48 permanecem abertas.

- J1/WU29 #99 / PR #100: proteção fail-closed de inconsistência entre símbolo PF_ e base/pair Kraken com alias oficial XBT→BTC, merged SHA `2fcc768ea878ce1a78060fbb9abb5be7bbffb97a`, CI #40231112282 SUCCESS (**591 testes offline**, 12 docs), issue fechada. Não prova registro crypto-only, volume financeiro ou Top50 real.

- J1/WU30 #101 / PR #102: `CryptoRegistryHistory.append` revalida manifesto v1 e SHA/evidence derivados mesmo para dataclass direta, merged SHA `e7f62a5fd56d1cc30ee84238cb313d18a029d9d1`, CI #40231467471 SUCCESS (**610 testes offline**, 12 docs), issue fechada. Autenticidade externa/Top50 permanecem bloqueados; J1 #2/#32/#36/#48 abertas.

A J1 só termina com aceite e evidência; testes sintéticos, CI verde ou ausência de erros de código não comprovam dados live confiáveis nem lucro. Seguir AGENTS.md: avançar sem pedir "prossiga" por microtarefas.


- J1/WU31 #104 — defesa OFFLINE contra variantes textuais de categorias TradFi no seletor Kraken, sem aceitação positiva de crypto-only; PR/CI pendentes nesta etapa, J1 bloqueada por #32/#36/#48.

- J1/WU32 #107 — experimento mínimo privado de conformidade OKX BTC perp, reutilizando parser WU22 com até dois GETs e três candles fechados, sem direitos para release, identidade cripto aprovada ou `ClosedCandle` canônico. PR #108 integrada SHA `9b66a359d1fa1d7a3ce83f66e1e002aa825de354`, CI #40236541641 SUCCESS (626 testes). Primeiro owner-run #40236605217 falhou antes de GET por import no entrypoint; fix módulo em andamento, J1 não homologada. Não concluir J1 por um único BTC.


- J1/WU33 #110 — PR #111 merged squash SHA `9f364a244bedba42803ca9803585023777813bb1`, CI #40237458174 SUCCESS (**633 testes offline, compileall, 12 docs**); seed BTC/ETH real com duas referências por ativo, revisão documental assistida por IA, sem Top50/rights.


- J1/WU34 #112 CONCLUÍDA como preço OHLC real de pesquisa: PR #113 merged `87b3f96653f97ef05798e918686b7fbe951622c2`; correção inclusive-`to` PR #114 merged `e7a5c21c639b14917216dc30df001daa083cfe0f`, CI #40237998812 SUCCESS (652 testes), **owner-run #40238058772 SUCCESS**, 1 GET e 3 candles preço PF_XBTUSD/1h válidos em SQLite TEMP com cobertura completa. Sem volume canônico nem retenção de dados/rights. Issue #112 fechada.

- J1/WU35 #115 CONCLUÍDA como seleção corrente BTC/ETH com dados REAIS Kraken: PR #116 merged squash SHA `7d54f5b13a1430d94cc9344781d8a63035bafbce`, HEAD revisado `01fa73fe2b88b2ecd74fb68b3c194268e0b523c0`, review #5645560006, CI PR #40238326403 SUCCESS (**663 testes offline, compileall, 12 docs**) e pós-merge #40238366580 SUCCESS. Owner-run #40238374774/job #121304703192 SUCCESS: 2 GETs, 231 instrumentos observados, 2 elegíveis BTC/ETH e 229 excluídos; snapshot atual SQLite TEMP roundtrip, sem dados retidos ou publicados. Issue #115 fechada, não é Top50 nem OHLCV.
- J1/WU36 #117 CONCLUÍDA apenas como desenvolvimento local: PR #118 merged `4d6ba02ea61ceeb64fe65ae4ea04c37d0972ea6d`, HEAD `6c286d302b92757bfe0339badfe5d5671cd10859`, review #5645586105, CI PR #40238785901 SUCCESS (**675 testes offline**, compileall, 12 docs), pós-merge #40238834784 SUCCESS. CLI privada integra GET-only Kraken BTC/ETH e 3 candles BTC price-only no mesmo SQLite LOCAL fora do Git e sem cron; nenhuma execução combinada live ou VPS realizada, duas provas anteriores separadas #40238058772/#40238374774 continuam evidências. Registro para no máximo duas bases, direitos/volume e Top50 histórico ainda bloqueados; J1 #2/#32/#36/#48 abertas.


- J1/WU37 #120 CONCLUÍDA: PR #121 merged SHA `c967d244c4ce289387a8c381f331e51dcfaf292c`, HEAD revisado `1a555238d8209cf9e8c65716e271fbd5c1af56fb`, review #5645747468, CI #40241827002 SUCCESS (**685 testes offline**, compileall, 12 docs), CI pós-merge #40241879286 SUCCESS. Owner-run real #40241888934/job #121315259119 SUCCESS 2026-10-25T22:48:27Z: 2 GETs Kraken, 231 instrumentos, **10 elegíveis, 221 excluídos**, SQLite TEMP roundtrip; zero market data retido. Registro SHA `a95179a342289833f3b14f0c2442163acdcb32f1ca0c9569fa01adeaa3534746`; issue #120 fechada. J1 #2/#32/#36/#48 abertas.
- J1/WU38 #122 CONCLUÍDA como conformance REAL de três páginas price-only em uma sessão: PR #123 merged SHA `42887e8338bc45e65cc58f5f32cf0ccbf8034d6b`, revisão HEAD `8ed058a27f230e80e142fa2c4721aab3de5e471f`/review #5645766424, CI #40242225054 SUCCESS (**692 testes offline**, compileall/12 docs), pós-merge #40242283400 SUCCESS. Owner-run #40242292478/job #121316477151 SUCCESS às 2026-10-25T22:53:58Z: 5 GETs Kraken, 3 contratos crypto elegíveis escolhidos (BTC e 2 pelo ranking real), 9 candles 1h fechados price-only em SQLite TEMP, qualidade completa, nenhum volume financeiro canônico. Issue #122 fechada; sem VPS/release/Top50 histórico/direitos comerciais/trading; J1 #2/#32/#36/#48 abertas.

- J1/WU39 #125 CONCLUÍDA só como validação OFFLINE de instrumento+kline Bybit com volumes documentados (base/quote em USDT/USDC linear), sem `ClosedCandle`: PR #126 merged SHA `bb3ecaf02f392bc8a1d06702a412d979b6ef1712`, HEAD `dca9326df8d675ea857bcd284470db9cda0875f1`, review #5645815578, CI #40243415573 SUCCESS (**706 testes offline**, compileall, 12 docs), pós-merge #40243468762 SUCCESS. Zero GET/live Bybit; licença não comprovada e restrições API; volume Kraken #36, rights #48, Top50 #32 e épica J1 #2 ABERTAS.

- J1/WU41 #130 CONCLUÍDA como janela price-only Kraken de 3..72h (default3): PR #131 merged SHA `e2b7db5d30864ba57c5ab5b6c438049ae35dc488`, review #5646098358, CI PR #40247855472 SUCCESS (**730 testes offline**, compileall, 12 docs), pós-merge #40247914420 SUCCESS. Owner-run #40247946123/j #121333418424 SUCCESS: 3 GETs, 24 BTC candles reais 1H contíguos em SQLite TEMP, 10 elegíveis/221 excluídos nos metadados correntes. 72h validada offline e NÃO executada live. WU40 dYdX #128/PR #129 não entregou candle por restrição de origem. J1 #2/#32/#36/#48 ainda ABERTAS sem direitos, volume canônico, Top50 histórico ou ordem.


- J1/WU42 #133 CONCLUÍDA SOMENTE como código candidato CandleFeed Free: PR #134 merged SHA `dcdaf90a07c36c5db044a31f041dd3ae2e08b2ea`, review #5646551100, CI PR #40255910737 SUCCESS (**744 testes offline**, compileall 12 docs), pós-merge #40255988914 SUCCESS. Nenhuma conta/key/GET CandleFeed, fonte Free 5 símbolos/30 dias, origem Binance com USD agregado não equivale a USDT settlement. Direitos upstream continuam gate, `ClosedCandle` financeiro false.
- J1/WU43 #135 CONCLUÍDA no escopo de integridade local: PR #136 merged `8e2a61d352bd4f0d40a4b1de86bfccf039cad4cb`, HEAD `f55e2da431561a913bf34f6bb295ec135476637f`, review #5646590380, CI PR #40256399524 SUCCESS (**750 testes offline**, compileall, 12 docs), pós-merge #40256467576 SUCCESS. Universo Kraken e 1..5 páginas preço-only gravados atomicamente no SQLite, rollback garantido também em DB existente sob conflito tardio; APIs individuais compatíveis, sem novo schema/rede/ordem. WU42 CandleFeed Free código entregue sem LIVE/conta, J1 #2/#32/#36/#48 abertas.

- J1/WU44 #138 CONCLUÍDA como investigação de acesso com sonda REAL BLOQUEADA: PR #139 merged `61566e2d9377f7565579c1516d738f1f7748ecae`, HEAD `4077b5101c7d543694567d40afe8526765ed1285`, review #5646635581, CI PR #40257293302 SUCCESS (**760 offline**, compileall 12 docs), pós-merge #40257371491 SUCCESS. Único real run #40257405663/j #121362109826: 1 GET metadados BTCUSDT Bybit e acesso restrito; 0 candles, sem bypass/retry. Por documentação Bybit volumes BASE BTC e turnover QUOTE USDT, mas sem conformance REAL no runner. Matriz `docs/J1_SOURCE_GATES.md` contém gates comparativos; Kraken 24h price-only real não se converte em OHLCV. J1 #2/#32/#36/#48 continuam ABERTAS.


## D77 — mudança material aprovada para o destino das jornadas
O requisito final é **trading automatizado** com entradas e saídas (stops/parciais/trailing/runner), diferentemente dos protótipos anteriores descritos como "manuais". O histórico de WUs e PRs não é reescrito: continuam implementações sintéticas, não ordens reais. Acrescentar simulador de intenções/fills e reconciliação a J4, monitor de estado/kill-switch a J5, paper prospectivo/testnet condicionada e release gate separado a J6. J1 continua ativa e bloqueada por dados/rights; nenhum salto direto a `live`. Fonte: `docs/AUTOMATED_EXECUTION_SPEC.md` e issue #147.


## Checkpoint de implementação — 26/10/2026 UTC
J4 tem AUTO1–AUTO6 como **componentes de simulação** (incluindo posições/ordens/fills/risco transacional PAPER); não é negociação real nem aceite da jornada #5. J5 recebeu apenas PRE1 #161/PR #162, tela `web/paper-demo.html` estática PT-BR para o roteiro fictício; não é UI operacional nem aceite #6. J1 segue bloqueada e não homologada; J2/J3/J6 sem validação necessária para produção. CI pós-J5/PRE1 #40300735438 SUCCESS (848 testes offline, 14 docs), sem evidência de lucro, direitos de mercado ou permissão de ordens.


## J5/PRE2 — exportação do replay fictício (26/10/2026 UTC)
Após PRE1 com página estática, J5/PRE2 #164 cria uma interface local em HTML obtida de snapshots `paper_dashboard_snapshot_v1` **gerados e validados em processo** de fixtures J4/AUTO5. Sem rede, sem live e sem sobrescrita de arquivos de usuário; entrega em validação. J5 permanece **não homologada** até ter UI operacional, provas visuais/acessibilidade e dados/ordens legítimos. J1/J2/J3/J4/J6 seguem com seus gates independentes, sem qualquer autorização de dinheiro real.
