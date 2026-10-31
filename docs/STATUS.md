# STATUS — Crypto Intelligence Agent

## J0 — Fundação
Concluída; issue #1 e PRs #10/#11 integradas. Requisitos, arquitetura, autonomia, jornadas e decisões versionados.

## J1 — Dados (épica #2 ABERTA)
| Unidade | Issue / PR | SHA integração | Evidência |
| --- | --- | --- | --- |
| WU1 contratos e adaptador Binance read-only | #9 / #12 | `c9bf70c3f8429b1474a9b68cc1aeb0a3cd209193` | testes offline |
| WU2 backfill SQLite e checkpoints | #13 / #14 | `f3567eb063f0b7cfeffe40169ba0b8e9fce1da96` | 42 testes offline |
| WU3 CLI offline e auditoria | #15 / #16 | `9631e4445678bc4c7067964b537da924b5b89a0b` | 58 testes |
| WU4 validação clock exchange | #17 / #18 | `8fc2f75460e93ef898ae14e3c48ef0348692c857` | 65 testes |
| WU5 Binance erro/restrição | #19 / #20/#21/#22 | `32c63d0beccdf4734cf06d0f37d04f9ae833fc1f` | live HTTP451, run 40197499250 |
| WU6 Kraken instrumentos | #23 / #24 | `76490ac8790138642f34de710c5f2e4bb2cf3d09` | GET200, 231 instrumentos, run 40198042787 |
| WU7 Kraken ticker/candles BTC | #25 / #26/#27 | `1c982eed74516ac70407c49ff5d2c98c2f88ee5b` | 3 GET200, run 40198745112, 99 testes |

**WU8 #28 concluída:** PR #29 integrada SHA `7e9b73bf3b5b19f5a56288326784d2280121c9d9`. Run `40199111677` SUCCESS, 1 GET HTTP200: 231 instrumentos, `category=xStocks` em PF_AAPLXUSD mas `tradfi=false` (mesmo valor que BTC/ETH), categorias DeFi/Meme/Equities/Forex etc; 102 testes offline verdes. Não existe filtro crypto-only automático aprovado ainda.

**WU9 #30 concluída:** PR #31 merged SHA `82236f2ee5345277fb3ffc92391594fb9d01fa3f`; CI pós-merge run 40199470161 SUCCESS com **115 testes Python offline** e 10 docs. Seletor conservador Kraken exige registro positivo e versionado de ativos cripto, exclui tokenizados e só então ranqueia volumeQuote USD até 50. Nenhum Top50 real validado.

**WU10 #32 parcialmente entregue:** PR #33 merged SHA `6be53f170edb81656d43d8ebf6e25c4ecdaaa9ed`, run CI pós-merge `40200232080` SUCCESS com **135 testes offline** e **11 docs**. Infraestrutura de registro/versionamento SHA256 e proteção point-in-time pronta, mas **issue #32 permanece aberta** porque falta validar fontes e licenças de ativos reais; não existe lista real aprovada.

**WU11 #34 concluída:** PR #35 merged SHA `a93f967cc4c5127e492f2878b62ccc9ce5f76428`, CI pós-merge run `40200619598` SUCCESS (**149 testes offline + 11 docs**). Parser estrito de OHLC Kraken fechado, sem volume/base/quote canônico fabricado. A issue #34 foi encerrada.

**WU12 #36 aberta, diagnóstico parcialmente executado:** PR #37 integrada no SHA `b607e2f32c5df8144790e58471133fb4fb9559a0`; CI pós-merge run 40201054020 SUCCESS (**163 testes offline + 11 docs**). Primeiro owner-run [40201172859](https://github.com/leandrosilveiradepaula/crypto-intelligence-agent/actions/runs/40201172859) em 25/10/2026 14:12:51 UTC: chart GET HTTP200 (~144ms), porém `invalid_chart_or_insufficient_data`; **somente 1 GET** realizado, sem ticker nem sumário financeiro. `unit_proof=false`. PR #38 integrada SHA `af0e431e5fba56e6fb5eb09c9c2e4e3418b93d1c` (CI pós-merge 40201436568 SUCCESS, 166 testes offline/11 docs). Segundo run [40201488833](https://github.com/leandrosilveiradepaula/crypto-intelligence-agent/actions/runs/40201488833) identificou causa precisa: **27 candles, 26 fechados e 27 volumes como strings decimais** apesar da documentação int64. Não houve segundo GET ou prova de unidade. WU12 continua em investigação.

**WU13 #39 CONCLUÍDA:** PR #40 merged SHA `e9b3b52b252b9319790ea188633392d13178b38f`; run CI pós-merge `40201833937` SUCCESS (**169 testes offline, compileall, 11 docs**). `volume` Kraken documentado int64 mas observado como string decimal agora é lido como Decimal exato, sem unidade base/quote. Run live [40201868577](https://github.com/leandrosilveiradepaula/crypto-intelligence-agent/actions/runs/40201868577) SUCCESS: **2 GET HTTP200**, 24 candles fechados, soma `volume` bruto `4122.747600000000`, ticker `vol24h=3928.2499` e `volumeQuote=314801204.5661`. `unit_proof=false`; **WU12 #36 permanece ABERTA** para comprovar unidades do dado e contrato. Nenhum `ClosedCandle` canônico, Top50 real, estratégia ou trading habilitado.

**WU14 #42 concluída:** PR #43 merged SHA `3f1e829467ada401e607ab6d857751f75ae2903d`, CI pós-merge [40202688033](https://github.com/leandrosilveiradepaula/crypto-intelligence-agent/actions/runs/40202688033) SUCCESS (**185 testes offline, compileall, 11 docs**). Gate de exposição agregada por símbolo/tier, recusa 50x se teto de pesquisa for 10x; não altera parâmetro global nem opera ordens. Sem tabela real aprovada.

**WU15 #44 concluída:** PR #45 merged SHA `c1d2c714d30daefe76804d1ed8d1792b919f8fee`, CI pós-merge [40203238118](https://github.com/leandrosilveiradepaula/crypto-intelligence-agent/actions/runs/40203238118) SUCCESS (**197 testes offline, compileall e 11 docs**). Frações de JSON Kraken são `Decimal` desde os bytes e qualquer float financeiro previamente arredondado é recusado, preservando ranking; sem mudar `unit_proof=false`.

**WU16 #46 concluída:** PR [#47](https://github.com/leandrosilveiradepaula/crypto-intelligence-agent/pull/47) merged SHA `6d5b37aba154b0fb6a950fbffa4ba3e18d01410e`; CI pós-merge [40203821568](https://github.com/leandrosilveiradepaula/crypto-intelligence-agent/actions/runs/40203821568) SUCCESS (**213 testes offline, compileall e 11 docs**). Cliente Kraken estritamente GET-only, rede desligada por padrão, snapshot de instrumentos/tickers e staging de OHLC fechado; não há `ClosedCandle` canônico, trading, Top50 real ou deploy.

**WU17 #48 — documentação integrada:** PR #49 merged SHA `4d06ce7fee2ddb459fbf08a7efa98d6d2bff4997`, CI pós-merge [40204178129](https://github.com/leandrosilveiradepaula/crypto-intelligence-agent/actions/runs/40204178129) SUCCESS (**213 testes offline e 12 documentos**). `docs/PROVIDER_RIGHTS.md` registra direitos Kraken e condições pré-release. **Issue #48 permanece ABERTA como gate externo**: nenhuma autorização comercial/redistribuição comprovada. Sem alteração de finalidade, gasto ou deploy.

**WU18 #50 concluída no escopo offline:** PR [#51](https://github.com/leandrosilveiradepaula/crypto-intelligence-agent/pull/51) merged SHA `6f147844a514f2b83b29084fb3bc5d4b2377355d`; CI pós-merge [40204649232](https://github.com/leandrosilveiradepaula/crypto-intelligence-agent/actions/runs/40204649232) SUCCESS (**229 testes offline, compileall, 12 docs**). Parser sintético Bybit V5 linear distingue `volume` base e `turnover` USDT/USDC, mas **não houve GET, feed real, licença comercial, troca de fornecedor ou `ClosedCandle` canônico**. Issue #50 encerrada. J1 #2 ainda aberta.

**WU16 #46 concluída:** PR #47 integrada SHA `6d5b37aba154b0fb6a950fbffa4ba3e18d01410e`, CI 213 testes offline. Cliente Kraken público GET-only, opt-in, Decimal e OHLC em staging, sem ordens.

**WU17 #48 parcialmente entregue:** PR #49 de política de direitos integrada SHA `4d06ce7fee2ddb459fbf08a7efa98d6d2bff4997`, 12 documentos validados; autorização de distribuição ainda não obtida.

**WU18 #50 concluída em pesquisa offline:** PR #51 integrada SHA `6f147844a514f2b83b29084fb3bc5d4b2377355d`, CI pós-merge **229 testes offline, 12 docs**; parser Bybit linear com base volume e quote turnover documentados em USDT/USDC, sem rede ou licença de uso homologada.

**WU19 #52 integrada:** PR #53 merged SHA `f19ce8b854bd024e22ccaf6bc6b0d276b70efec2`, CI PR run #40205837293 SUCCESS (240 testes offline segundo revisão). Gate de finalidade em código sem direitos externos autenticados.

**WU20 #54 integrada:** PR #55 merged SHA `7c0642d2d2769a8d12f5651af3f7280fce06ed88`, CI #40209121605 SUCCESS (docs, syntax, unittest offline). Relatório estático conservador, sem Top50/candles canônicos live. **WU21 #56 integrada:** PR #58 merged SHA `c73817ddda007355696ed0649b43c6ca59da9fcf`, CI #40212786207 SUCCESS (docs, sintaxe, unittest offline). Validador e CLI de proveniência aprovam apenas forma/digest/tempo dos claims, jamais direitos ou feed real. Issue #56 encerrada. WU12 #36 segue aberta: a especificação Kraken Market Candles não define a unidade financeira de `volume`.

**WU22 #60 concluída no escopo offline:** PR #61 merged SHA `ee8c36d09a90192cbf5220c10ec28b876852508c` com CI #40214317197 SUCCESS (**279 testes offline, compileall, 12 docs**). Parser OKX SWAP com volume contrato/base/quote, confirmação de candle, direitos/proveniência sempre fail-closed. Não houve GET, licença de mercado, Top50 real, candle canônico, troca de venue, trade ou deploy.

**WU23 #63 — CONCLUÍDA NO ESCOPO DE MANIFESTO:** run #40215045758/job #121234257255 SUCCESS, log original 2026-10-25T17:08:57Z confirma manifesto Vike BTC (fills/positions) schema correto e CC BY 4.0 **declarada**. SHA256 `9329c928aba6fc710a981ee9f985a75006af61147ac887bd960a544a6812ce7a`. Nenhum Parquet/rights upstream/Top50 verificado; issue #63 fechada, direitos externos #48 abertos.

**J2/PRE1 #66 — concluída como pré-trabalho offline, sem iniciar J2 operacional:** PR #67 merged SHA `cf1c4cacffa4f5b46475a73dcc6bc9f5631b2e5d`, CI #40216432146 SUCCESS (315 testes offline, compileall e 12 documentos). EMA/ATR/extremos prévios/volume/retorno calculados com Decimal somente em candles sintéticos; saída não sinalizadora e temporalidade verificada. J1 #2 e J2 #3 seguem abertas, sem fonte live, estratégia validada ou execução.

**WU24 #69 — concluída no escopo OFFLINE:** PR #70 merged SHA `49458f5db870651035d77c2470fe62386cfab652`, CI PR #40217228473 SUCCESS (**338 testes offline, compileall, 12 docs**). Contratos de metadados perp e candles nativos Hyperliquid com volumes brutos sem unidades atestadas, recusa de candles sem trades, gates de direitos/impossibilidade de usar em produção e Top50 sempre fail-closed. Nenhum HTTP real ou mudança de fonte. CoinGecko/CoinPaprika Free não cobrem uso comercial a R$0; Vike #63 continua sem prova do run.

**WU25 #72 — RUN REAL FALHOU EM SCHEMA:** job #121243633007/run #40218132668 FAILURE: 1 POST informativo /info, metadata hash `00e4595b1ba9e0dc718ee0f2ad38e6719a488588a1b100056dd97e56bb77e2c7`, status `invalid_provider_schema`; nenhum candleSnapshot executado. Não há corpo bruto persistido para identificar campo incompatível. Nenhuma unidade, rights ou Top50 liberados; issue #72 aberta para diagnóstico offline.

**WU26 #75 — AUDITORIA CONCLUÍDA:** PR #76 merged SHA `9d20a34404146f3ee7a8290542cd46d519dfb7c7`, CI #40219481048 SUCCESS (**378 testes offline**, compileall, 12 docs), auditoria GitHub Actions read-only #40219481021 SUCCESS. IDs e logs originais das sondagens anteriores recuperados sem repetição de chamadas de mercado, permissões write ou novos gastos. Issue #75 fechada.

**WU27 #78 — CONCLUÍDA OFFLINE:** PR #79 merged SHA `da62b41f69596c756d04cc5188b755bfaa97f862`, CI #40221224643 SUCCESS (**387 testes offline, compileall, 12 docs**). Parser valida BTC alvo com rigidez e preserva instrumentos não-alvo como dados inertes; agora oferece categorias de falha sanitizadas. Issue #78 encerrada. Falha histórica #72 permanece sem causa específica comprovada, nenhum novo POST, direitos/licença, Top50 ou produção liberados.

**J4/PRE1 #81 — CONCLUÍDA apenas como matemática sintética:** PR #82 merged SHA `c4f6b94fd5a89724185b9a486818a6c8fa84adf0`, CI #40223997038 SUCCESS (**414 testes offline, compileall, 12 docs**). Quantidades INITIAL/REMAINING e runner exato com propriedades live/order/fill não autorizadas; #81 encerrada.

**J4/PRE2 #83 — CONCLUÍDA como replay exclusivamente sintético:** PR #84 merged SHA `f051ab5c681bb9b4bd15e0384fb779a142330475`, CI #40224464764 SUCCESS (**443 testes offline, compileall, 12 docs**). Eventos de preenchimento fictício por tranche, deduplicação de ID/payload somente em memória, validação temporal, controle de overfill e conservação Decimal; nenhuma idempotência persistente, PnL, contratos reais ou ordem. Issue #83 fechada; J1 #2, J3 #4 e J4 #5 permanecem abertas. Unidade Kraken #36 e licenças #48 ainda não homologadas.

**J4/PRE3 #86 — CONCLUÍDA como domínio sintético:** PR #87 merged SHA `afb034d3435162402af673a8946bb2d747950326`, CI #40225049332 SUCCESS (**473 testes offline**, compileall, 12 docs). Configuração 50x para novas posições e leverage_at_open capturado, margem abstrata, vínculo de eventos PRE2 ao ID da posição fictícia; issue #86 encerrada. Não existe moeda, trade real, lot/step, PnL ou idempotência cross-session.

**J4/PRE4 #88 — CONCLUÍDA somente em aritmética SINTÉTICA:** PR #89 merged SHA `677f0c299cbfc1b0dc772f6d5d110a63c277dea9`, CI #40225440872 SUCCESS (**502 testes offline**, compileall, 12 docs). Passo Decimal/mínimo de tranche, fill individual e residual com regra hipotética e sem arredondamento. Issue #88 fechada; J4 #5, J3 #4 e J1 #2 não homologadas. Nada de lot/step real, USD/notional, order/trade ou idempotência persistente.

**J1/WU28 #91 — CONCLUÍDA como proteção de evidência documental:** PR #92 merged SHA `d3af3088088c7e7f638cb745ca5848ddbb2b9a43`, CI #40227134838 SUCCESS (**515 testes offline, compileall, 12 docs**), issue encerrada. Auditor recusa Kraken Spot/Derivatives US como prova de PF_ Futures; mantém etiquetas de insuficiência para volume, registro crypto-only e rights. Não libera Top50, OHLCV canônico, 50x real ou licença; issues #32/#36/#48 e J1 #2 abertas.

**J3/PRE1 #94 — CONCLUÍDA somente como observação SINTÉTICA:** PR #95 merged SHA `3a30150268d6ead7daabe16884827b655b5b1e7c`, CI #40229271296 SUCCESS (**548 testes offline, compileall, 12 docs**); reconhece gap e toques múltiplos sem ordem, nenhuma execução/liquidação real, PnL ou lucro. Issue encerrada, J3 #4 aberta.

**J3/PRE2 #96 — CONCLUÍDA apenas em matemática SINTÉTICA:** PR #97 merged SHA `ea13ea60c617eb57973a6b6e708b06fc325afc96`, CI PR #40229681278 SUCCESS (**577 testes offline, compileall, 12 docs**), issue fechada. Fees/slippage por perna e funding assinado em quote abstrata com precisão Decimal e dedup in-memory. Total de custo negativo não é lucro; flags de PnL/venue/FX/ordens permanecem false. J1 #2, J2 #3, J3 #4 e J4 #5 não homologadas.

**J1 #32/#36/#48 — diligência complementar registrada em issues:** padrão CAIP-19 identifica ativos por chain+namespace+reference, mas não atesta crypto-only/venue; SLIP-0044 é lista de derivação de wallets, não registro de perpétuos; CoinGecko Demo não inclui direitos comerciais; chart/analytics Kraken não provam unidade de volume. Sem feed real e mantendo gates abertos.

**J1/WU29 #99 — CONCLUÍDA como correção de integridade do seletor Kraken:** PR #100 merged SHA `2fcc768ea878ce1a78060fbb9abb5be7bbffb97a`, CI PR #40231112282 SUCCESS (**591 testes offline, compileall, 12 docs**); issue encerrada. Bloqueia `PF_AAPLXUSD` rotulado indevidamente como BTC, mesmo com categoria ausente; mantém alias oficial XBT/BTC e não libera registro real/Top50.

**J1/WU30 #101 — CONCLUÍDA como proteção de integridade do histórico crypto-only:** PR #102 merged SHA `e7f62a5fd56d1cc30ee84238cb313d18a029d9d1`, CI #40231467471 SUCCESS (**610 testes offline, compileall, 12 docs**); issue encerrada. Inserção no histórico revalida manifesto/sha/fonte/tempo inclusive dataclass direta, mas **não autentica a verdade de fontes externas**. Issues J1 #2/#32/#36/#48 ainda abertas.

**J1/WU31 #104 CONCLUÍDA apenas OFFLINE:** PR #105 merged squash SHA `7a97d5e239ab98fb61107dc60e3503a902146e98`, HEAD `f27d106edc0f7aa55148c6d245bad6f0d330975c`, CI PR #40233629730 SUCCESS (**613 testes offline, compileall, 12 docs**) e CI pós-merge #40233741828 SUCCESS. Issue #104 fechada; bloqueio de variantes textuais TradFi não valida identidades cripto. Sem feed real, unidade econômica de candle ou autorização comercial; J1 #2/#32/#36/#48 seguem abertas.

**J1/WU32 #107 — PR #108 integrada, prova live pendente:** merge `9b66a359d1fa1d7a3ce83f66e1e002aa825de354`, CI PR #40236541641 SUCCESS (626 testes), CI pós-merge #40236593184 SUCCESS. Primeiro owner-run #40236605217 FALHOU antes de qualquer GET com `ModuleNotFoundError` no entrypoint. Correção com execução como módulo e teste subprocess em `fix/j1-wu32-okx-entrypoint`; sem observação real OKX até reexecução controlada. Dados de mercado de uso pessoal, não publicação; nenhuma prova de identidade, histórico Top50 ou permissão comercial. Docs D57; issues J1 #2/#32/#36/#48 abertas.


**J1/WU33 #110 CONCLUÍDA no escopo BTC/ETH:** PR #111 merged SHA `9f364a244bedba42803ca9803585023777813bb1`, CI #40237458174 SUCCESS (**633 testes offline, compileall e 12 docs**); duas referências documentais independentes por ativo e proteção temporal. Uso interno; registro positivo real não é Top50.



**J1/WU34 #112 CONCLUÍDA como trilha price-only:** PR #113 merged `87b3f96653f97ef05798e918686b7fbe951622c2`, correção de URL inclusiva PR #114 merged `e7a5c21c639b14917216dc30df001daa083cfe0f`, CI PR #40237998812 SUCCESS (**652 testes offline, compileall, 12 docs**). Execução REAL #40238058772/job #121303793854 SUCCESS: 1 GET Kraken Futures PF_XBTUSD/1h, **3 candles fechados de preço guardados em SQLite TEMP**, qualidade `complete`; sem volume financeiro, retenção de mercado, Top50, ordem ou direito de publicação. Issue #112 encerrada.


**J1/WU35 #115 CONCLUÍDA como universo corrente REAL de até 2 bases:** PR #116 merged `7d54f5b13a1430d94cc9344781d8a63035bafbce`, CI PR #40238326403 SUCCESS (**663 testes offline, compileall, 12 docs**) e pós-merge #40238366580 SUCCESS. Owner-run #40238374774/job #121304703192 SUCCESS em 2026-10-25T22:03:34Z: 2 GETs instruments/tickers Kraken, **231 instrumentos observados, 2 elegíveis e 229 excluídos** sob registro BTC/ETH real, roundtrip SQLite TEMP; zero volume publicado ou armazenado permanentemente, sem ordens. Não equivale a Top50 histórico. Issue #115 fechada.

**J1/WU36 #117 CONCLUÍDA APENAS COMO IMPLEMENTAÇÃO LOCAL:** PR #118 merged squash SHA `4d6ba02ea61ceeb64fe65ae4ea04c37d0972ea6d`, HEAD revisado `6c286d302b92757bfe0339badfe5d5671cd10859`, review #5645586105, CI PR #40238785901 SUCCESS (**675 testes Python offline**, compileall, 12 docs), pós-merge #40238834784 SUCCESS. CLI privada reúne universo BTC/ETH + 3 candles BTC price-only em um SQLite local persistente, **sem deploy/execução na VPS**; diretório 0700/arquivo 0600, banco fora do Git público, duplo opt-in, 3 GETs no máximo e sem ordens. O comando combinado não tem run live próprio; as duas partes já tiveram smokes reais separados WU34/WU35. J1 #2/#32/#36/#48 ainda abertas.


**J1/WU37 #120 CONCLUÍDA COM 10 CONTRATOS REAIS NO UNIVERSO CORRENTE:** PR #121 merged `c967d244c4ce289387a8c381f331e51dcfaf292c`; CI #40241827002 SUCCESS (**685 testes offline**, compileall, 12 docs) e pós-merge #40241879286 SUCCESS. Owner-run #40241888934/job #121315259119 SUCCESS UTC 2026-10-25T22:48:27Z: **231 instrumentos Kraken examinados, 10 elegíveis e 221 excluídos**, 2 GETs e roundtrip SQLite TEMP. Registro v2 de dez bases revisadas com fontes externas de identidade e SHA256 verificável; nenhum dado bruto ou direito comercial. Não é Top50 histórico; issue #120 fechada.

**J1/WU38 #122 CONCLUÍDA COMO COLETA REAL MULTI-CRYPTO PRICE-ONLY:** PR #123 merged squash SHA `42887e8338bc45e65cc58f5f32cf0ccbf8034d6b`, review #5645766424 no HEAD `8ed058a27f230e80e142fa2c4721aab3de5e471f`, CI #40242225054 SUCCESS (**692 testes Python offline**, compileall, 12 docs), pós-merge #40242283400 SUCCESS. Run owner-only REAL #40242292478/job #121316477151 SUCCESS às 2026-10-25T22:53:58Z: 5 GETs Kraken, universo 10 elegíveis e 221 excluídos, **3 contratos coletados, 9 candles OHLC de 1h no MESMO SQLite TEMP**, qualidade completa; dados e DB do runner descartados. CLI local default BTC=1, opção 1..5 BTC+ranked crypto, nenhum volume base/quote canônico, direito de distribuição/ordens/Top50 histórico ou VPS liberados. Issue #122 FECHADA; J1 #2/#32/#36/#48 seguem abertas.

**J1/WU39 #125 CONCLUÍDA COMO CONTRATO OFFLINE DE UNIDADE DOCUMENTADA:** PR #126 merged squash SHA `bb3ecaf02f392bc8a1d06702a412d979b6ef1712`, HEAD revisado `dca9326df8d675ea857bcd284470db9cda0875f1`, review #5645815578, CI PR #40243415573 SUCCESS (**706 testes Python offline**, compileall e 12 docs), pós-merge #40243468762 SUCCESS. O parser Bybit V5 existente agora é encadeado a validação de `instruments-info` de linear perp USDT/USDC, status Trading, base/quote/settle, registro cripto com as-of e exclusões TradFi, sem inferir unidades ou alavancagem 50x. **ZERO GET Bybit, ZERO OHLCV real homologado, ZERO ClosedCandle/SQLite/VPS/ordens.** Direitos comerciais Bybit restringidos; documentação de outra exchange não soluciona volume Kraken #36. Issues J1 #2/#32/#36/#48 ABERTAS.

**J1/WU40 #128 ENCERRADA como diagnóstico de fonte ALTERNATIVA RESTRITA:** PR #129 merged squash `2119fd6cf37efec52d279313abed45af87ca60aa`, CI #40247354874 **722 testes offline**, pós-merge #40247418673 SUCCESS, review #5646077354. Run REAL proprietário #40247448362/job #121331921437: 2 GETs dYdX BTC-USD; metadata respondeu 200/status ACTIVE, candles bloqueados por `access_or_geographic_restriction` (HTTP/cabeçalho específico não preservado); **0 candles dYdX**, 0 volumes reais/market data armazenados. Não repetir nem contornar o bloqueio. BitMEX encerrada em 2026-09-23, descartada.

**J1/WU41 #130 CONCLUÍDA no escopo price-only:** PR #131 merged squash SHA `e2b7db5d30864ba57c5ab5b6c438049ae35dc488`, HEAD `ce228f3ac35c1394d9f277f16e27ba48fd4fb2cc`, review #5646098358; CI PR #40247855472 SUCCESS (**730 testes Python offline**, compileall, 12 docs), pós-merge #40247914420 SUCCESS. Owner-run REAL #40247946123/job #121333418424 SUCCESS em 2026-10-26T00:09:15Z: exatamente 3 GETs Kraken, **24 candles fechados de preço BTC 1h** com `price_window_complete=true` em SQLite TEMP descartado; 10 elegíveis e 221 excluídos no universo corrente de 10 bases. CLI permite janela 3..72h (default 3), **72h somente testadas offline**. Sem volume Kraken validado, Top50 histórico, direitos de mercado ou produção. J1 #2/#32/#36/#48 continuam abertas.



**J1/WU42 #133 CONCLUÍDA no escopo CÓDIGO OFFLINE:** PR #134 merged SHA `dcdaf90a07c36c5db044a31f041dd3ae2e08b2ea`, CI PR #40255910737 SUCCESS (**744 testes offline**, compileall e 12 docs), CI pós-merge #40255988914 SUCCESS. Candidato CandleFeed Free: volume BASE BTC + USD normalizado, somente 5 símbolos/30 dias/100 calls/dia, direitos §5.3 internos/§6 upstream; SEM conta, key, GET real, `ClosedCandle` ou backtest financeiro homologado.

**J1/WU43 #135 CONCLUÍDA na integridade do SQLite LOCAL:** PR #136 merged SHA `8e2a61d352bd4f0d40a4b1de86bfccf039cad4cb`, HEAD revisado `f55e2da431561a913bf34f6bb295ec135476637f`, review #5646590380, CI PR #40256399524 SUCCESS (**750 testes Python offline**, compileall e 12 docs), CI pós-merge #40256467576 SUCCESS. O coletor Kraken usa UMA transação para UniverseSnapshot+1..5 páginas price-only, rollback integral de conflito em banco EXISTENTE, replay idempotente; nenhum volume econômico ou rights liberado. Issues #133 e #135 fechadas, J1 #2/#32/#36/#48 seguem abertas.

**J1/WU44 #138 CONCLUÍDA como sonda Bybit BLOQUEADA:** PR #139 merged squash `61566e2d9377f7565579c1516d738f1f7748ecae`, review #5646635581, CI PR #40257293302 SUCCESS (**760 testes offline**, compileall 12 docs), CI pós-merge #40257371491 SUCCESS. Owner-run #40257405663/job #121362109826 (26/10/2026 02:06 UTC) fez **1 GET de instrumento BTCUSDT, 0 GET candles**; status `bybit_access_or_region_restricted_no_retry`, causa exata não registrada. Nenhum retry, mudança de domínio, dado financeiro ou ordem. Bybit base BTC/quote USDT documentada mas não validada com candle REAL neste ambiente. **J1 segue BLOQUEADA** por registro Top50 histórico #32, unidade de candle Kraken #36 e direitos públicos/comerciais #48. Fonte de verdade de candidatos: `docs/J1_SOURCE_GATES.md`.

## Riscos/pendências
A Binance respondeu HTTP451 no runner gratuito, sem candles. Kraken respondeu HTTP200 para instrumentos, tickers e 3 candles BTC (amostra pontual), com `volumeQuote` em USD, porém inclui instrumentos tokenizados não cripto (`PF_AAPLXUSD`). **213 prefixos PI_/PF_ não equivalem a 213 criptoativos elegíveis.** Falta classificação confiável, precisão das unidades, fechamento intrabar, cobertura histórica e homologação em ambiente operacional. J1 continua **ABERTA**, sem estratégias validadas, trades ou produção.

Restrições: custo R$0, repo público sem segredos, nenhum trade real, deploy, gasto ou migration sensível. Ler OPERATIONAL_STATE.md e verificar GitHub vivo antes de agir.


## J1/WU45 #141 — gate documental de matriz de fornecedores
A PR da WU45 reforça a proteção **offline** de `docs/J1_SOURCE_GATES.md`, agora incluída nos 13 documentos obrigatórios, com regressões para matriz ausente e marcadores críticos perdidos. Pesquisa oficial Kraken não encontrou definição explícita de unidade econômica de `trade candles.volume` PF_; minuta à Kraken na #36 permanece **não enviada**. Direitos #48 e Top50 point-in-time #32 continuam sem prova externa. Não confundir este incremento com homologação J1 #2 nem divulgar dados de mercado.


## J1/WU46 #143 — expansão causal das identidades sob revisão
O manifesto v3 propõe 13 identidades documentadas para **pesquisa interna**, acrescentando XMR/ETC/ZEC à base v2, preservando SHA/instante das dez anteriores. A variante `expanded-13` é opt-in; defaults existentes intactos. Sem GET de exchange, sem afirmação de 13 contratos Kraken, ranking Top50 ou histórico de listagens, sem direitos de redistribuição. Gate de volume #36, identidade histórica #32, rights #48 e J1 #2 continuam abertos.


## J1/WU47 — Binance/Bybit como candidatas de execução manual (26/10/2026 UTC)
O Product Owner informou que tem contas na Binance e na Bybit. **Isso não é evidência de acesso a futuros, habilitação regional de API, qualidade de OHLCV, alavancagem, ou autorização para usar credenciais.** Ambas são **candidatas**, nenhuma foi selecionada. O produto mantém execução **manual**, sem endpoints de ordens, chaves ou conexão à conta. Fonte de pesquisa não precisa coincidir com a venue de eventual execução, mas um sinal só poderá ser considerado executável após reconciliação de preço, símbolo, contrato, quote/settle, lot/step/min notional, funding, taxas, liquidez, limites de risco e disponibilidade na venue específica. Kraken price-only é pesquisa auxiliar e não certifica Binance/Bybit.
Binance USD-M já tem adaptador/fixtures offline, mas o run real anterior foi bloqueado HTTP451 (#19). Bybit linear V5 possui parser documentado de volume BASE/turnover QUOTE em USDT/USDC, porém o único run real foi restrito no primeiro GET (WU44, 0 candles). Não repetir nem contornar restrições. O relatório `scripts/j1_readiness_report.py` distingue as duas candidatas com flags `account_access_verified=false`, `live_signal_approved=false`, `manual_plan_approved=false`, `order_execution_enabled=false`. Essa enumeração não concede direitos de dados, não escolhe venue nem homologa J1 #2, #32, #36 ou #48. Custo adicional R$0; sem credenciais, dados de conta, ordens, deploy ou feed público.


## D77 / issue #147 — mudança no alvo do produto, 26/10/2026 UTC
**Requisito vigente:** entradas e saídas automáticas, incluindo parciais/trailing/runner, com Binance USD-M e Bybit V5 linear candidatas. A interpretação 'trading final manual' de WU47 foi substituída expressamente pelo Product Owner. O robô ainda **não foi implementado nem homologado**: estratégias J2, risco/backtest J3, ledger de execução J4, UI J5 e simulação contínua J6 dependem de integração e gates. A J1 segue com acesso Binance HTTP451, Bybit bloqueada no primeiro GET, Kraken price-only e sem Top50 histórico nem direitos públicos homologados. Nova `docs/AUTOMATED_EXECUTION_SPEC.md` descreve modo `offline_paper`, testnet condicionada e live proibido até autorização separada. A WU48 atualiza documentação e readiness; nenhuma operação/credencial/deploy.


## J4/AUTO1 #149 — base de ordens simuladas, não robô pronto
A implementação proposta adiciona `synthetic_order_lifecycle.py` e testes offline de estados e fills fictícios, como pré-requisito para controle automático de ordens. O estado nunca envia ordens nem cria PnL; lida com ACK vs FILL, timeout UNKNOWN, duplicações, parciais e REDUCE_ONLY puramente hipotético. Ausentes: estratégia J2 homologada, venue de execução selecionada, estado persistente/reconciliação REST+WS reais, stops, RiskGate global, licença de dados, controle regional e liberação live. #5 e #7 continuam abertos; nenhuma ordem real.


## J4/AUTO2 #151 — diário SQLite de ordens simuladas (em validação)
Incremento PAPER: intenções fictícias reservadas de forma durável, eventos hipotéticos de ACK/UNKNOWN/FILL/cancel e checkpoints reconstruíveis em transação SQLite atômica. Replays no mesmo arquivo não duplicam OPEN por sinal nem fills por IDs idênticos; corrupção e conflito interrompem o processamento. Ainda não há executor, integração privada Binance/Bybit, orçamento de risco, saldo agregado real, parciais coordenadas por posição, stops no livro da exchange ou PnL homologado. Nenhuma credencial/POST/ordem real, sem testnet, sem produção, sem seleção final de venue. A J4 #5 permanece aberta, além da J1 #2 e bloqueios de dados #19/#32/#36/#48.


## J4/AUTO2 concluída / AUTO3 em revisão (26/10/2026 UTC)
AUTO2 #151/PR #152 integrada SHA `47d51ac33142bcbd9672fbbe041f922948adca70`, CI pós-merge [#40279479428](https://github.com/leandrosilveiradepaula/crypto-intelligence-agent/actions/runs/40279479428) SUCCESS: **797 testes offline**, compileall e 14 docs; ordens continuam simuladas. AUTO3 #153 propõe preflight de risco para PAPER: cap de ordem, exposição, perdas, ordens incertas e kill-switch; não possui verdade de conta/venue, stops reais, estratégia validada nem habilitação de trading. J1/J4/J6 abertas, `live` desativado e R$0 adicional.


## J4/AUTO4 #155 — over-close agregado PAPER (em validação)
A branch `codex/issue-155-j4-auto4-paper-position-reservations` acrescenta um agregado SQLite exclusivo para posições fictícias, em que quantidade inicial vem de FILL, reservas REDUCE_ONLY e fills por tranche compartilham um único saldo e runner. Inclui replay/idempotência/crash concorrente e os casos 50%/60%/70% => 6% residual. **Não** é executora de exchange, nem migra DB AUTO2, confirma conta real ou homologa J4; aguardar PR/CI antes de afirmar integração. A J1 #2 segue aberta; ordens reais, chaves e deploy continuam não autorizados.


## J4/AUTO4 integrada; AUTO5 #157 — ciclo automático PAPER demonstrativo
AUTO4 issue #155/PR #156 integrada SHA `355c12c30f70a972721592be38f4393bbfa030b3`, [CI pós-merge #40297847492](https://github.com/leandrosilveiradepaula/crypto-intelligence-agent/actions/runs/40297847492) SUCCESS, **824 testes offline**, compileall e 14 documentos. AUTO4 contém saldo e reservas de saídas por posição, com passo de lote **fictício**; não há tick de preço, ordens reais ou reconciliação da corretora.
AUTO5 #157 propõe uma CLI de percurso automático **somente fixtures**, reunindo risco PAPER, OPEN, ACK/FILL, saídas parciais, runner e restart para os dois candidatos, sem desempenho validado. A PR/CI da AUTO5 ainda exigem comprovação. J1 #2 e J4/J6 permanecem não homologadas e `live` bloqueado.


## J4/AUTO5 integrada; AUTO6 #159 — pendências do journal no RiskGate PAPER
AUTO5 #157/PR #158 foi integrada SHA `2861207076aea3d2c5cd4f2a079e61825ef599ec`; [CI pós-merge #40298681391](https://github.com/leandrosilveiradepaula/crypto-intelligence-agent/actions/runs/40298681391) SUCCESS com **830 testes offline**, compileall e 14 docs. O comando `python3 -m scripts.demo_automated_paper_cycle` reproduz cenário sintético de entrada e saídas, sem financeiro real.
AUTO6 #159 acrescenta preflight/reserva OPEN numa única transação PAPER, calculando pendências/UNKNOWN dos registros locais, não confiando em zeros fornecidos pelo fixture, e atualiza o demo. A PR/CI AUTO6 ainda exigem revisão; J1/J4/J6 continuam abertas e nenhuma autorização live foi dada.


## J5/PRE1 #161 — tela em português offline, execução PAPER visualizada
A branch `codex/issue-161-j5-pre1-mobile-paper-demo` introduz `web/paper-demo.html` com prévia mobile e indicadores de fluxo J4 exclusivamente sintéticos, sem scripts/contas/rede/ordens. A PR/CI desta tela exigem validação antes de integração. Base confirmada: AUTO6 #159/PR #160 integrada SHA `830bdc6705458a7e3f9bb88623a22d8eaf1c1dab`, pós-merge [CI #40299720648](https://github.com/leandrosilveiradepaula/crypto-intelligence-agent/actions/runs/40299720648) SUCCESS **843 testes offline**, compileall e 14 docs. J1, J2, J3, J4, J5 e J6 ainda não aceitas para operação real; interface é uma amostra, não release.


## Checkpoint consolidado pós-J4/AUTO6 e J5/PRE1 — 26/10/2026 UTC (prevalece sobre notas "em revisão" acima)
- **GitHub `main`**: `c9ed28ca6c979895441807e2611d50a617d26939`; PRs abertas **zero** na verificação. [CI pós-merge #40300735438](https://github.com/leandrosilveiradepaula/crypto-intelligence-agent/actions/runs/40300735438): **SUCCESS, 848 testes offline, compileall, 14 documentos**.
- **AUTO4** issue #155 / PR #156: `355c12c30f70a972721592be38f4393bbfa030b3`, proteção conjunta de REDUCE_ONLY, rollback, recovery, lote fictício.
- **AUTO5** issue #157 / PR #158: `2861207076aea3d2c5cd4f2a079e61825ef599ec`, `python3 -m scripts.demo_automated_paper_cycle` para duas venues **somente em fixtures**, 50/30/14 e runner 6.
- **AUTO6** issue #159 / PR #160: `830bdc6705458a7e3f9bb88623a22d8eaf1c1dab`, pendências/UNKNOWN locais auditadas em transação única de gate/reserva OPEN PAPER.
- **J5/PRE1** issue #161 / PR #162: `c9ed28ca6c979895441807e2611d50a617d26939`, `web/paper-demo.html` standalone em PT-BR, responsivo, sem JS e sem controles de negociação; **QA visual física/abrangente ainda não realizada**.
- **Jornadas**: J0 concluída; J1 #2 continua **não homologada** (fontes/rights #19/#32/#36/#48); J2 #3 sinais reais não homologados; J3 #4 backtest financeiro real não homologado; J4 #5 tem componentes PAPER mas não é executor de exchange; J5 #6 tem protótipo estático, não UI operacional; J6 #7 sem homologação contínua; J7 #8 condicionado a resultado validado.
- **Próxima prioridade independente**: construir UI local consumindo snapshot PAPER versionado e testar visual/acessibilidade sem rede, enquanto J1 continua requerendo evidência primária de OHLCV econômico/licença e a futura escolha de venue. Nunca habilitar ordens/testnet/live ou deploy por default. Custo adicional R$0,00.


## J5/PRE2 #164 — renderização do replay no painel PAPER (em validação)
Em `codex/issue-164-j5-pre2-render-paper-snapshot`, a CLI `scripts/render_paper_dashboard.py` gera snapshot v1 de duas execuções J4/AUTO5 **inteiramente artificiais** e preenche a página `web/paper-demo.html` por marcadores seguros, sem JavaScript ou rede. Rejeita fontes/flags live, PnL, dados arbitrários e divergência de quantidades. Os arquivos HTML/JSON são exportados somente localmente com criação exclusiva; o HTML prévio continua válido. Esta WU ainda exige PR, CI, revisão de SHA e merge; não confundir com UI conectada, dados financeiros ou produto pronto. Base confirmada: `main=c7f6b2d8b19e45d132e37006e4137b507cb162b7`, zero PRs abertas antes da WU; J1 #2, J2 #3, J3 #4, J4 #5, J5 #6, J6 #7 permanecem abertas.


## J5/PRE3 #166 — prévia mobile acessível, auditoria em navegador em validação
Foi iniciada a branch `codex/issue-166-j5-pre3-mobile-a11y-browser-audit` a partir da `main=2f4d6303af66fc02e24ea17752b2ba86d7f748dc` (PRE2 PR #165 integrada, pós-merge CI #40307747119 SUCCESS, 860 testes offline, 14 docs). Melhoria: salto de teclado para main, scroll horizontal identificado/focável, rótulos que quebram em telas estreitas e validador HTML que recusa recursos externos. Auditoria Chrome/Playwright em seis viewports com screenshots/JSON sintéticos foi adicionada em workflow separado. **Não alegar QA visual aprovado até observar CI e evidências**, nem concluir J5; sem contas, APIs, ordens, produção ou custo.

**QA efetiva inicial da PR #167:** [Chrome run #40311401806](https://github.com/leandrosilveiradepaula/crypto-intelligence-agent/actions/runs/40311401806) SUCCESS sobre o primeiro HEAD da PR, com seis larguras, zero overflow global, zero elementos fora, navegação Tab/Enter e rolagem por setas. Contraste em amostras 9,43:1–12,7:1. Arquivo de 7 evidências no artifact `paper-mobile-qa-40311401806`; capturas 280/320/375/390/1280 foram examinadas e a densidade dos quatro cards em 375–390 motivou layout em coluna única até 420px. **A nova alteração exige CI/browser QA no SHA final**. Sem teste físico/leitor de tela completo, J5 permanece aberta.


## J5/PRE4 #168 — leitura de posição persistida PAPER (em validação)
Base real inicial: `main=e4c2e7daaf451971222b7567be8155d9431b35ac`, zero PRs abertas, J5 épica #6 ainda aberta. PRE3 issue #166/PR #167 integrada, CI pós-merge docs/Python #40312209141 SUCCESS (**861 testes offline**, 14 docs) e Chrome #40312209355 SUCCESS em seis larguras, sem rede/overflow. Branch PRE4: `codex/issue-168-j5-pre4-readonly-paper-position`. Entrega prevista/implementada na branch: leitor SQLite `mode=ro` de AUTO4 com cotejo OPEN opcional AUTO2, saída local JSON v1 e HTML responsivo individual com reservas UNKNOWN separadas dos fills, testes de corrupção/restart/RO, Chrome QA adicional via workflow existente. **Aguardam PR/CI/merge no SHA final**; J1 #2 e demais jornadas continuam sem homologação real, custo R$0.

**Evidência intermediária PR #169:** primeira CI Python #40319478992 falhou em quatro testes por duplicação do marcador UTC checkpoint no template; correção e regressão adicionadas. CI Python posterior #40319653489 SUCCESS: 875 testes offline e 14 docs. Chrome #40319653749 SUCCESS: seis viewports, zero overflow ou requisições externas, snapshot 100/20/30/50/80/6 com UNKNOWN preservado e rolagem por teclado. Artifact paper-mobile-qa-40319653749 contém 12 PNG e 2 JSON. Capturas da posição em 280/390/1280px foram inspecionadas; nenhum corte global, porém o rótulo técnico REMAINING_BALANCE foi traduzido no HTML. **Nova CI no HEAD pós-tradução ainda é necessária** antes de merge. J5 não homologada.


## J5/PRE4 homologada somente como pesquisa PAPER; J5/PRE5 #170 em validação
PRE4 issue #168/PR #169 integrada no squash SHA `3ab6f99c81f1a72336f5df90d2297ab8dbe3445b`. CI pós-merge [#40320499557](https://github.com/leandrosilveiradepaula/crypto-intelligence-agent/actions/runs/40320499557) SUCCESS (**875 testes offline**, compileall e 14 docs) e Chrome [#40320499417](https://github.com/leandrosilveiradepaula/crypto-intelligence-agent/actions/runs/40320499417) SUCCESS em seis larguras e sem rede. A PRE4 é leitura isolada de **uma** posição fictícia com fill/UNKNOWN/reserva. A nova PRE5 issue #170 / branch `codex/issue-170-j5-pre5-multi-paper-positions` amplia para consulta consistente de vários IDs explicitamente escolhidos de UM SQLite RO, JSON/HTML por posição e nenhum somatório financeiro; adicionou QA Chrome e testes de concorrência. **PR/CI PRE5 ainda precisam de evidência**, J1/J2/J3/J4/J5/J6 ainda não homologadas para operação real, R$ 0.



## J2/PRE2 #172 — hipótese de entrada estudável sem feeds/ordens

Foi iniciada a implementação do primeiro **avaliador matemático de entrada** (compressão ATR histórica, breakout estrito, filtro EMA/volume) com candles exclusivamente sintéticos e causalidade explícita. A engine J2/PRE1 fornece todos os indicadores, sem recálculo duplicado. Testes quantitativos de referência LONG/SHORT e adversariais foram adicionados. `ResearchCandidate` é hipótese e `approved_for_live_use=false`; não é sinal operacional, backtest, feed real ou rentabilidade. A J1 não está homologada e ainda não há dados históricos permitidos/representativos. A WU depende de CI e revisão no SHA da PR antes de integração, sem publicação ou ordem real.



## J3/PRE3 #174 — validade temporal antes de pesquisa de resultados

Implementação da estrutura offline de walk-forward: janelas de treino, gap e teste não sobreposto, fechamento confirmado antes de cada teste, regras de replay e recusa de períodos incompletos. J2/PRE2 #172/PR #173 integrada merge `d241dc8e025d88c98b7c5bc8cd7b366d63b25e14`, CI PR #40327807689 SUCCESS (**896 testes offline**, 14 docs), browser #40327807652 SUCCESS e ambas CI pós-merge #40327984929/#40327984911 SUCCESS. J5/PRE5 #170/PR #171 integrada merge `4c66aa7f9a3f4542396ff79a13e8f99b3d3a86de`, Python pós-merge #40326996341 e Chrome #40326996359 SUCCESS (**884 testes PR**). PRE3 aguarda CI própria; suas janelas ainda **NÃO** produzem resultados financeiros, ganhos, sinal autorizado ou PnL. J1–J6 não homologadas operacionalmente.


**J3/PRE4 issue #176 (em revisão, 26/10/2026):** após PRE3 PR #175 integrada SHA `b524da877ea6f3cf7b9c4f84f9f6f707a85b73f0` com CI pós-merge Python #40329036508 e Chrome #40329036488 SUCCESS, foi aberta unidade de purga de labels sintéticos em horizontes fixos. Branch `codex/issue-176-j3-pre4-purged-label-horizons`. PRE4 não executa backtest, não mede estratégia nem valida dados reais e permanece pendente de PR/CI/revisão/merge. J1/J3/J6 não homologadas, nenhuma ordem real.


**J3/PRE5 issue #178 (em revisão):** a base inicial é `main=6924f2545704954d695db66520ee71f2667d7235`, PR #177 PRE4 integrada, 915 testes offline/14 docs e CI Python/Chrome pós-merge SUCCESS. Branch `codex/issue-178-j3-pre5-causal-oos-replay` introduz integração J2→J3 com prefixos temporais e categorias ex-post de alteração de fechamento em dados 100% sintéticos, sem PnL/ordens/otimização de parâmetros. A nova PR e CI/merge ainda precisam ser comprovadas e revisadas. J1/J2/J3/J6 não homologadas.

## J3/PRE6 #180 — cenários financeiros condicionais offline, em revisão

A issue #180 adiciona branches financeiras sintéticas com premissas explícitas, custos PRE2 e ambiguidade PRE1. Não infere fill, não calcula liquidação de venue e não valida estratégia, lucro, backtest ou execução. Consultar GitHub para PR/CI/SHA antes de declarar integração; J1 #2, J2 #3 e J3 #4 continuam abertas.



**Revisão PR #181 / issue #180:** o primeiro SHA do Codex `f750712f9802e5a2212d7ca8cc8f451fa218db8c` teve CI Python Linux (929 testes/14 docs) e Chrome SUCCESS. A revisão financeira encontrou incompatibilidade possível entre preço×quantidade e nocionais de taxas, ausência de vínculo com o plano/barreira PRE1 e cobertura incompleta de níveis intrabar. Correção e testes adicionais foram incorporados **na mesma PR**, exigindo nova verificação no HEAD final antes de integrar. Não interpretar CI antiga como aceite dos commits posteriores.


**J1/WU48 issue #182 (em execução no checkpoint inicial, 26/10/2026):** `main=82aacf78bf8718846ab7530867353e3773331db7`, PR #181 J3/PRE6 integrada, CI pós-merge Python #40337579169 SUCCESS (934 testes, 14 docs) e Chrome #40337579002 SUCCESS. Nenhuma PR aberta ao iniciar. Nova branch `codex/issue-182-j1-wu48-offline-bybit-json-audit`: auditoria local pura de instrumento+kline JSON **fornecidos voluntariamente**, sem acesso externo; protege precisão/qualidade e não emite OHLCV canônico/ordens. PR/CI/merge da WU48 ainda sujeitos a verificação; J1 e direitos reais permanecem bloqueados. R$0 adicional.

## J3/PRE7 #184 — integração causal sintética, em revisão

A issue #184 integra J2/PRE2 e J3/PRE1–PRE6 com abstenção temporal e ramos condicionais explícitos. Não cria backtest, PnL agregado, ordem PAPER, feed real ou autorização live. Consultar a PR/CI antes de declarar integração.

**Revisão da PR #185:** SHA inicial `0f5a6d2bbc2293fdee6e9114d0e77dbbf215c3fa`, Python Linux #40343107820 SUCCESS (**948 testes**, 14 docs), Chrome #40343107890 SUCCESS. A revisão identificou consumo indevido de candles de outros folds/períodos posteriores ao horizonte por PRE7, contratos extras ignorados e necessidade de timestampar entradas hipotéticas no primeiro OPEN permitido. Adicionadas correções e regressões na mesma PR; obter novos SHA/CI antes de aceitar. Em ambiente Windows, o Codex relatou 23 erros e 3 falhas locais de casos dependentes de POSIX; não classificar essa execução como PASS ou alegar suporte Windows sem triagem específica.


**Qualidade/portabilidade issue #186 (em validação 26/10/2026):** base `main=260d101792c313a21c7455cf896aae28889842ea`; PR #185 J3/PRE7 merged, CI Python Linux #40346976828 (954 testes/14 docs), Chrome #40346976852 SUCCESS; PRs abertas zero no início. Criada branch `codex/issue-186-quality-windows-private-paths` para estabelecer fail-closed explícito no coletor Kraken quando Windows não fornece semântica POSIX de filesystem; testes de coleta privada POSIX continuam no Linux, enquanto validação de domínio e preflight permanecem cross-platform. Adicionada CI Windows offline em runner padrão do repositório público para diagnóstico real; **resultado Windows ainda não verificado neste checkpoint**. Não altera J1, trading, direitos ou execução real.


**Qualidade #186 — regressões Windows resolvidas no head provisório da PR #187:** execução GitHub Windows inicial [#40348787279](https://github.com/leandrosilveiradepaula/crypto-intelligence-agent/actions/runs/40348787279) revelou 16 erros de limpeza SQLite (`WinError 32`), não asserções financeiras. Corrigido fechamento de conexões no conjunto de testes via `contextlib.closing`, sem alterar semântica transacional. Novo run [#40349432290](https://github.com/leandrosilveiradepaula/crypto-intelligence-agent/actions/runs/40349432290) **Linux SUCCESS 958/958; Windows SUCCESS 958 testes, 35 skips POSIX**; Chrome [#40349432416](https://github.com/leandrosilveiradepaula/crypto-intelligence-agent/actions/runs/40349432416) SUCCESS, SHA provisório `b20fd346dc51df12e23a356167e096f773362b90`. PR permanece pendente de verificação final/merge, nenhum release/trade. O relato Windows do Codex 23 erros/3 falhas não foi reproduzido exatamente, pois código e suíte diferem.


**J4/AUTO7 issue #188 (entrega em revisão no checkpoint inicial, 26/10/2026):** base confirmada `main=895fc61c83d71fbc332305d4d99f76b768313290`, PR #187/issue #186 integradas, CI Linux+Windows pós-merge [#40350094916](https://github.com/leandrosilveiradepaula/crypto-intelligence-agent/actions/runs/40350094916) SUCCESS (**958 testes**, Windows 35 skips POSIX), Chrome [#40350094892](https://github.com/leandrosilveiradepaula/crypto-intelligence-agent/actions/runs/40350094892) SUCCESS, zero PR aberta na verificação. Branch `codex/issue-188-j4-auto7-causal-paper-intent` integra hipótese J2 no último candle causal ao preflight e reserva transacional PAPER AUTO6, sem PRE5/PRE7 ex-post, sem fill, sem dados de mercado ou ordens. **CI, SHA final e merge desta issue sujeitos a revisão**, não presumir aceitação J1/J2/J3/J4/J6.

**J4/AUTO8 issue #190 (em implementação/revisão):** adiciona saúde fail-closed de FILL PAPER antes da próxima OPEN causal. O auditor somente leitura relaciona AUTO2 e AUTO4, distingue `UNPROTECTED`, `UNKNOWN` e `PROTECTED_HYPOTHETICAL_ONLY`, e não chama um plano sintético de stop real. Enquanto houver FILL/posição a provar, novas OPEN são bloqueadas; REDUCE_ONLY não é cancelado. Evidências de branch, SHA e CI Linux/Windows devem ser registradas na PR antes de merge; nenhuma ordem, rede, conta, credential, deploy ou custo.


**Revisão de segurança da PR #191 (J4/AUTO8):** o HEAD enviado `1d5c556c5c901137da071f5a9311b813ee00eb74` tinha CI Linux/Windows e Chrome SUCCESS, mas foi identificado um intervalo TOCTOU: auditoria fora da transação podia ser seguida por FILL de outra thread antes de reservar OPEN. Corrigido pela operação guardada com auditoria/esquema dentro do `BEGIN IMMEDIATE` AUTO2, mantida auditoria AUTO4 somente leitura e nenhuma atomicidade cross-DB alegada. Testes adversariais novos verificam corrida de FILL, FILL parcial, mismatch de eventos e índice órfão. **Novos commits exigem CI no SHA final antes de merge.** J1/J2/J3/J4/J6 não homologadas, R$0.


**J4/AUTO9 issue #192 (revisão iniciada em 26/10/2026):** base verificada `main=25b4861d9b67916ef41a12644345684cca73fa5e` após merge #191; CI pós-merge Linux/Windows [#40356540982](https://github.com/leandrosilveiradepaula/crypto-intelligence-agent/actions/runs/40356540982) SUCCESS (980 testes, Windows 35 skips POSIX-only, 14 docs), Chrome [#40356541029](https://github.com/leandrosilveiradepaula/crypto-intelligence-agent/actions/runs/40356541029) SUCCESS. Branch `codex/issue-192-j4-auto9-paper-flat-reconciliation` implementa relatório de encerramento PAPER 100% por eventos explícitos, com relógio de decisão causal, sem proteger posição real. **PR, CI do SHA final e merge desta WU ainda devem ser verificados**. J1/J2/J3/J4/J6 não homologadas; nenhum endpoint, conta ou gasto adicional.


**J1/WU49 issue #194 (em revisão, 26/10/2026 UTC):** base confirmada `main=b7697ecedfb5e97dc0c91fb42462397db0cd07f9` após PR #193, CI Linux/Windows 991 testes (35 skips POSIX Windows), 14 docs e Chrome SUCCESS. Na pesquisa documental Bybit V5, `instruments-info` exige paginação quando há mais de 500 contratos. O ticker `turnover24h` não declara unidade explícita, diferentemente de `turnover` do endpoint de velas. A issue #194 e PR #195 documentam essa diferença, e a branch `codex/issue-194-j1-bybit-paginated-universe` verifica o encadeamento de cursores, contrato cripto registrado, filtro USDT e ordenação apenas do **valor bruto, sem unidade** do ticker, mantendo flags de direitos/volume/Top50/live falsas. CI final e merge desta PR ainda exigem verificação do SHA; J1 #2/#19/#32/#36/#48 bloqueadas. Nenhum GET/POST de mercado ou gasto.


**J1/WU50 issue #196 (diligência em revisão, 26/10/2026):** base GitHub confirmada `main=6401848d6b2e431a7ccc9c18fa07cbd1f2b20502` após PR #195 integrada (CI pós-merge Linux/Windows [#40365930592](https://github.com/leandrosilveiradepaula/crypto-intelligence-agent/actions/runs/40365930592) SUCCESS 1.007 testes, Windows 35 skips POSIX; Chrome [#40365930850](https://github.com/leandrosilveiradepaula/crypto-intelligence-agent/actions/runs/40365930850) SUCCESS). A pesquisa oficial Bybit mostrou **legendas de 24H Turnover(USDT)/24H Volume(BASE) na UI**, porém os campos REST `turnover24h`/`volume24h` não têm unidade explicitada no schema V5, e Kline e WebSocket não comprovam o endpoint REST. Branch `codex/issue-196-j1-bybit-ticker-unit-diligence` adiciona gate negativo `bybit_ticker_24h_units` ao relatório, testes e pergunta formal **NÃO enviada**. Não há novo GET/POST, conexão, contrato positivo, Top50 financeiro ou autorização de uso. PR/CI final/merge ainda requerem revisão. J1 #2/#19/#32/#36/#48 não homologadas; R$0.


**J6/PRE1 #198 (implementação em revisão, 26/10/2026 UTC):** base auditada `main=cffac3bc5dca30e64308618014e861f19265febe` após PR #197 integrada, CI pós-merge 1.008 testes Linux/Windows, QA Chrome e 14 documentos SUCCESS. A investigação J1 #36 do endpoint Kraken Futures charts confirmou que `volume` é tipado int64 mas unidade econômica não é declarada; documentos de ticker `volumeQuote` e interface BTC/USD não atestam a unidade da vela. Portanto J1 permanece bloqueada. Branch `codex/issue-198-j6-forward-only-paper-session` entrega replay **offline de candles artificiais**, limitado a um novo candle por passo, preservando prefixo, timestamp, risco AUTO6/8/9 e ausência de fill/ordens; checkpoint de sessão NÃO durável. **CI/PR/head/merge desta work unit ainda precisam de evidência exata.** J1 #2/#19/#32/#36/#48/#196, J2/J3/J4/J6 ainda não homologadas; custo extra R$0.


### J6/PRE2-A #200 — pré-requisito de integridade offline (26/10/2026 UTC)

Foi acrescentado contrato puro de selo determinístico SHA-256 para prefixos sintéticos completos e contexto versionado, com escala Decimal preservada e extensão de exatamente uma barra. É uma preparação verificável para recuperação futura, **não** checkpoint durável, transação conjunta com AUTO2, proteção de exchange, stream prospectivo ou homologação. A issue #200 permanece aberta: próximo passo é integrar cursor e reserva/no-signal na MESMA transação AUTO2, com crash tests e auditoria do schema RO, ou manter fail-closed se inviável. AUTO4 continua sem snapshot atômico cruzado. Nenhuma rede, ordem real, migration produtiva ou custo.


### J6/PRE2-B #200 — cursor transacional de fixture em AUTO2 (26/10/2026 UTC)

O módulo `offline_paper_durable_cursor.py` acrescenta API offline explícita com cursor SHA-256 e inventário de OPENs em metadado opcional do próprio banco AUTO2, sem migração de schema ou produção. Um único `BEGIN IMMEDIATE` verifica prefixo/versão, saúde AUTO8/AUTO9 e risco AUTO6, reserva intenção PENDING e atualiza cursor; no-signal e risco negado também registram progresso. A recuperação compara integralmente prefixo e contexto e rejeita replay, saltos, mudança de venue/quantidade/limites e OPEN legada sem cursor. AUTO4 continua arquivo independente, sem snapshot comum. `OfflinePaperForwardSession` PRE1 permanece in-memory. Nenhuma fonte de mercado real, rede, credencial, execução, deploy ou gasto. PR/CI e fault injection de processo ainda precisam ser validados; não declarar J6 homologada.


## Plano operacional aprovado — 26/10/2026 UTC

Fonte de execução por etapas: [`docs/EXECUTION_ROADMAP.md`](EXECUTION_ROADMAP.md). Prioridade: (1) finalizar revisão/CI/merge seguro da PR #202 J6/PRE2-B; (2) desbloquear por evidência legítima J1 #2/#19/#32/#36/#48/#196, sem novos probes restritos; (3) validar sinais e risco J2/J3 com dados reais; (4) implementar executor e UI J4/J5 após os gates; (5) homologar J6 com PAPER prospectivo e autorizações específicas de testnet/live. Sem cronograma ou porcentagem arbitrários. Nenhuma ordem real, deploy ou gasto extra autorizado.


### J6/PRE2-C #200 — fechamento de lacunas de teste de recuperação (26/10/2026 UTC)

Adicionada cobertura offline para encerramento real de processo **após commit** com OPEN e cursor persistidos, reenvio da mesma barra recusado, avanço para próxima barra sem nova OPEN, SQLite ocupado sem progresso, inventário de OPEN adulterado, metadado inesperado e arquivo SQLite corrompido. A cobertura anterior já testava interrupção real **antes do commit**. Estes testes são regressões de engenharia PAPER, não prova de durabilidade perante falha de hardware, corretora real ou snapshot AUTO2/AUTO4. PR e CI do SHA final ainda precisam de verificação; issue #200 permanece aberta até aceite. Próxima prioridade após aceite: J1, conforme docs/EXECUTION_ROADMAP.md.


## Checkpoint atual — transição J6/PRE2 para J1 (26/10/2026 UTC)

J6/PRE2 #200 encerrada como engenharia PAPER sintética: PRs #201/#202/#203 integradas, último merge SHA `5ee3312b362387a37bc3f403914741a5a33676ea`, CI pós-merge #40392712218 (Linux/Windows + 14 docs) e #40392711941 (Chrome) SUCCESS. J6 épica #7 e negociação real seguem bloqueadas.

Prioridade ativa: **J1 #2**. Matriz WU51 em `J1_SOURCE_GATES.md` diferencia provas e bloqueios por fonte e determina próximas ações sem burlar acesso: Kraken price-only/unidade chart #36 + direitos #48, Bybit acesso negado + ticker #196, Binance HTTP451 #19, registro crypto #32. Não foi homologado OHLCV financeiro, Top50, estratégia lucrativa ou venue real. R$0 extra.


## J1/AUTH1 #205 — autorização read-only do Product Owner (26/10/2026 UTC)

O usuário autorizou **somente conexão de leitura** de suas contas Binance e Bybit na VPS existente. Contrato e procedimento em `docs/PRIVATE_EXCHANGE_READONLY.md`; scripts e testes mockados na branch `work/issue-205-readonly-exchange-probe`, sem requisição autenticada real. Consulta ao plugin DigitalOcean retornou **zero droplets visíveis**; acesso à VPS/chaves não comprovado. Próximo gate é revisar CI Linux/Windows/QA, confirmar infraestrutura existente sem gasto, e executar diagnóstico somente em ambiente privado permitido com credenciais read-only. Nenhuma ordem, saldo divulgado, credential em chat, proxy, deploy ou alteração produtiva. J1 #2 e J6 #7 permanecem abertas.


### J1/AUTH1 — instalação offline real, autenticação pendente (26/10/2026 UTC)

O titular demonstrou as duas saídas `offline_network_disabled` na VPS Hostinger e checkout SHA `3dd2980eb8d1ddb93c8d8928a3336f8aac53c00b`. Próxima entrega na issue #205 é launcher seguro de credenciais `scripts/run_private_exchange_readonly_tty.py` para **uma GET autenticada por corretora** somente após verificação de chave exclusivamente de leitura; CI/PR sob avaliação. Nenhuma solicitação autenticada, ordem, saldo ou deploy.

## Checkpoint AUTH1 e J4 — 27/10/2026 UTC

**Bybit:** GET assinada privada HMAC com chave somente leitura foi autenticada na VPS do titular, retornando `authenticated_read_only_key_confirmed` e flags de ordens/saldo/trading negativas. **Binance:** titular criou chave HMAC de leitura com allowlist do IP da VPS e direitos de negociação desativados na interface; GET assinada retornou `access_or_region_restricted` (erro HTTP preciso **desconhecido**; a categoria inclui 401/403/418/451). Evidências sanitizadas: issue #205. Não repetir requisição negada ou transferir segredo/identificador ao GitHub.

**J1 #2 permanece BLOQUEADA:** não há GET público de candles validado nessa VPS, autorização de dados, volume canônico, universo Top50 histórico, feed operacional ou homologação financeira. Autenticação de chave Bybit ≠ validação do feed. O relatório offline J1 inclui observação de autenticação datada, sem concessão de negociação ou dados. Próximo caminho: evidência legítima de market data e direitos, mantendo regressões sintéticas independentes.

**J4/J3:** PR #211 de conservação do residual e duplicatas sintéticas integrada sem produção em `552aa5cb0b5a5c10e65ddcadade226e9ae67ac5e`, com CI da PR #40426971446/#40426971471 e CI pós-merge #40505375800/#40505375696 SUCCESS. Não há ordens, deploy ou custo adicional.

## J1/WU53 — observação pública Bybit real no ambiente-alvo (27/10/2026 UTC)

**Prova delimitada:** titular executou na VPS Hostinger uma sonda read-only pública sem credenciais: **2 GETs**, informações de perpétuo BTCUSDT + **3 candles 1H fechados validados**, `status=private_real_bybit_base_btc_quote_usdt_observed`, `observed_at_utc=2026-10-27T13:07:29+00:00`. `volume` em BTC (BASE) e `turnover` em USDT (QUOTE), conforme contrato de KLINE da Bybit. Identificadores SHA256 e flags `data_stored=false`, `orders_sent=false` constam na issue #213. O script já tinha revisão CI na PR #139 e o mesmo blob foi conferido no checkout da VPS e na main. O resultado não comprova direitos comerciais nem operação contínua.

**Distinção:** observação anterior de bloqueio no GitHub Actions continua verdadeira **naquele ambiente**; não era prova de bloqueio na VPS. A autenticação privada da Bybit (issue #205) é independente do GET público da WU53. A Binance permanece sem autenticação pública/privada de mercado nessa VPS.

**Permanece pendente:** J1 #2 para histórico persistido, qualidade multiativo, universo Top50 point-in-time, direitos de uso (#48), ticker 24h (#196), e validação J2/J3; flags de ordens, OHLCV canônico, redistribuição e release continuam desativadas. Próxima ação de engenharia: contrato offline de ingestão Bybit → armazenamento e testes sem novas chamadas ou dados financeiros reais no GitHub. R$0,00.

## J1/WU54 #215 — staging SQLite Bybit somente offline (27/10/2026 UTC)

Implementação proposta na branch `work/issue-215-j1-bybit-isolated-staging`: módulo `bybit_research_storage.py` com SQLite opt-in **distinto do banco canônico**, bytes JSON strict + manifesto WU48 validados pelo parser WU39 em cada commit, persistência Decimal BASE/QUOTE e idempotência, replay verificado, qualidade de lacunas e rollback por falhas/lock. Testes adversariais em `tests/test_bybit_research_storage.py` usam só fixtures; CI/PR e revisão de SHA pendentes neste checkpoint. Nenhuma integração de fonte real, cron, ordem, credencial, VPS ou deploy. O probe real #213 validou 3 candles, mas `data_stored=false`, e **não** forneceu esses corpos ao staging. J1 #2, licenciamento #48, universo #32 e ticker Bybit #196 continuam pendentes. R$0 adicional.

## J1/WU55 — diligência de direitos Bybit sem liberação de retenção (27/10/2026 UTC)

A WU54 #215 foi concluída por PR #216, main `5005de6a53b5b67a65c922dbd57587a9926c6354`, com staging SQLite de pesquisa **sintético/offline**, testes e CI aprovados; os 3 candles reais da WU53 não foram retidos. Na WU55 #217, a fonte oficial atualizada dos API Terms Bybit remete a conteúdo legal dinâmico que não pôde ser verificado integralmente. Referências oficiais anteriores restringem comercialização/redistribuição, mas não atestam retenção histórica local privada. **Gate de retenção permanece bloqueado**, `rights_authorized=false`. Preparar apenas contrato offline, sem consultar mercado, chaves, implantação, ordens, custos ou publicação. Fonte e restrições em `PROVIDER_RIGHTS.md`, decisão D108; J1 #2 não homologada.

## J1/WU55-B — ensaio offline de captura e staging (27/10/2026 UTC)

Branch `work/issue-217-j1-offline-capture-handoff-tests` acrescenta testes de integração simulando **duas respostas Bybit sintéticas** para `SQLiteBybitResearchStore` já implementado, com transporte fake estritamente limitado, replay e QA offline, proibição de endpoints errados e não-persistência após erro. O estudo documental de direitos da PR #218/D108 continua **sem licença de retenção privada comprovada**: não existe novo cliente live, GET, credencial, captura de candles reais ou alteração da VPS. PR/CI devem ser verificados antes de alegar aceite. J1 #2 e #217 abertas.

## J3/OFFLINE #208 — regressões de ambiguidade intrabar LONG/SHORT (27/10/2026 UTC)

Branch `work/issue-208-j3-intrabar-liquidation-order-regression`: cinco cenários de teste exclusivamente sintéticos sobre OHLC para STOP/TARGET/LIQUIDATION, incluindo toques múltiplos, gaps adversos e igualdade no nível. Nenhuma prioridade de fill ou precedência de liquidação é inferível de OHLC; testes mantêm flags de liquidação, fill e backtest falsas. **A issue #208 permanece aberta** para custos, risco e executabilidade real não modelados. Essa tarefa não altera J1 #2, gates de licença Bybit #217, trading, VPS ou dados reais; PR/CI e merge a verificar.

## J3/PRE6 #208 — base única de entrada nos cenários condicionais (27/10/2026 UTC)

Novo gate de engenharia no módulo existente `synthetic_financial_scenarios.py`: um conjunto de alternativas STOP/TARGET/LIQUIDATION **da mesma posição** deve conservar quantidade, moeda sintética, horário/notional e taxa/slippage de **entrada**, sem confundir risco entre branches. Permite diferenças explícitas de saída. Regressões LONG/SHORT e de liquidação em `test_synthetic_financial_scenarios.py`, decisão D109. Branch `work/issue-208-j3-shared-position-branch-invariants`, PR/CI/revisão pendentes nesta etapa; nenhuma nova estratégia, backtest financeiro validado, rede ou ordens. J3 #208 permanece aberta; J1 #217 continua sem autorização comprovada de retenção real.

## J3/OFFLINE #208 — calendário de funding pré-saída coerente (27/10/2026 UTC)

Branch `work/issue-208-j3-shared-funding-calendar`, base `2e9e5f4b3dbd12ca2169e9c82da0d921194375f7`: inspeção de PRE6 encontrou possibilidade de omitir/alterar um settlement já ocorrido antes da saída mais cedo entre alternativas de uma mesma posição sintética. Gate D111 compara ID/hora/taxa/fonte/moeda/sinal sem fixar nocional path-dependent; permite eventos após a primeira saída só em ramos ainda abertos. Regressões LONG/SHORT, STOP/TARGET, liquidação, mutações e fronteira; CI, revisão e merge ainda sujeitos a confirmação. PRs #222/#223 independentes permanecem abertas com checks aprovados e bloqueio anterior de merge; não presumir integração. J3 #208, J1 #217 e trading real continuam abertos/bloqueados. R$0 adicional.

## J3/OFFLINE #208 — ramificações únicas por barreira (D112, 27/10/2026 UTC)

Na revisão da PR #224 foi identificada cobertura de PRE6 baseada só em igualdade de conjuntos, admitindo duplicar um nível atingido com `scenario_id` diferente. A branch existente `work/issue-208-j3-shared-funding-calendar` recebeu gate de cardinalidade + igualdade de barreiras e regressões LONG/SHORT, inclusive liquidação hipotética. Reapurar HEAD/CI antes de revisão e merge; PRs #222/#223 permanecem abertas com CI anterior aprovada. A contagem de ramos não significa probabilidade e o motor não é homologado para PnL real ou trading.

## J3 #208 — reconciliação documental D113 e requisito D77 (27/10/2026 UTC)

Revisão de consistência na PR #224: `VALIDATION_PLAN.md` ainda continha um critério D113 de aceitar funding fora da ordem, apesar da correção de CI exigir cronologia estrita PRE2; substituído pelo contrato efetivo. `STRATEGY_SPEC.md` ainda dizia que o produto mantém execução manual como requisito, apesar da decisão D77 estabelecer execução automática como objetivo futuro; corrigido para separar alvo automático de bloqueio de live atual. Não altera motor, testes, gates financeiros ou habilita ordens. A PR #224 continua sem merge, com CI a ser revalidada no novo SHA.

## J3/OFFLINE #208 — first-hit e gaps adversariais (27/10/2026 UTC)

Regressões PRE1 LONG/SHORT: a primeira vela com nível observado permanece a primeira mesmo que uma vela posterior toque todas as barreiras; gap favorável no OPEN só prova TARGET no OPEN, não ordena STOP/liquidação atingidos depois dentro da mesma vela; gap adverso STOP+liquidação no OPEN preserva ausência de prioridade e de fill. Exigir close_safety_ms na fronteira exata também nesses gaps. Não criar motor financeiro paralelo nem derivar preço de liquidação, PnL, mark, execução ou prioridade intrabar. Testes offline no SHA final; CI Linux/Windows/docs/Chrome obrigatória antes de merge.

## J3 #208 — bateria metamórfica financeira offline (27/10/2026)

Regressões de custos PRE2: funding positivo/negativo e zero LONG/SHORT com notionals assimétricos, antissimetria de sinal, aumento monotônico de fee/slippage, replay idempotente de eventos duplicados. PRE6: perdas de liquidação explicitamente assumidas com taxas maiores reduzindo net condicional, rejeição de preço de saída inventado e precisão Decimal do chamador (2/4/28/200). Todos os resultados permanecem hipotéticos; nenhuma fórmula de margem/liquidação de venue, feed, fill ou retorno OOS foi homologado. CI Linux/docs, Windows e Chrome/PAPER exigida no SHA exato.

## J3 #208 — invariância à permutação dos ramos PRE6 (27/10/2026)

Para três barreiras sintéticas TARGET/STOP/LIQ LONG e SHORT, permutar a ordem dos ramos não pode alterar custos ou net condicional de cada barreira nem atribuir probabilidade, prioridade intrabar ou fill. Uma mutação de slippage na entrada de apenas um ramo deve falhar em ambas as permutações. Sem validação de venue, margem, funding real, residual, OOS ou lucro. CI Linux/docs, Windows e Chrome/PAPER no SHA exato é gate obrigatório.


## J3 #208 — custos líquidos, margem abstrata e runner residual (27/10/2026 UTC)

Testes de regressão sobre contratos existentes: PRE6 LONG/SHORT com TARGET atingido e gross positivo (+20 unidades sintéticas), porém taxas e slippage adversos declarados de 600/600 e 10/10 bps podem tornar o net condicional NEGATIVO; nenhuma classificação de TARGET equivale a lucro ou fill. PRE3/J4 exercita matriz LONG/SHORT × alavancagem de pesquisa 1x/50x/200x × margem abstrata 1/3/5, com replay de 50/30/14, duplicação exata e runner final 6 invariantes; 50x NÃO converte margem em notional ou preço de liquidação. PRE4 combina LONG/SHORT × leverage × margem com step 2, mínimo de saída 2 e residual mínimo de 6 (compatível) versus 7 (incompatível), sem arredondar/autorizar ordens. Não há integração financeira de moeda/collateral/preço entre J3 e J4 nem prova de viabilidade em Binance/Bybit, resultados OOS ou PnL real. Checks Linux/docs, Windows e Chrome/PAPER exigidos para integração.



## J1/HIST #229 — fonte oficial Binance Vision e arquivo mensal exclusivamente offline (27/10/2026 UTC)

Fonte primária: [Binance public data README](https://github.com/binance/binance-public-data/blob/master/README.md) declara USD-M futures klines por /fapi/v1/klines, 12 colunas, volume BASE e volume de cotação, ZIP mensal e CHECKSUM. [Vision Dataset Terms v1.0 26/08/2026](https://github.com/binance/binance-public-data/blob/master/TERMS_AND_CONDITIONS.md) §§3.1-3.4/4.1-4.5 aplica CC BY-NC-SA 4.0 e pesquisa/backtest estritamente pessoal, não produtivo; proíbe execução live com dataset e exploração comercial, com outras condições de acesso/território ainda sujeitas à avaliação. Não confundir licença MIT do código-ferramenta do repositório com licença dos DATASETS. Não baixar nem usar como feed live com base nesta análise. O contrato `offline_vision_month.py` somente recebe bytes ZIP sintéticos fornecidos pelo chamador: nome exato BTCUSDT/USDT 1h YYYY-MM, CRC/zip, 1 CSV 12 colunas, SHA256 esperado, mês inteiro fechado, timestamp contínuo, limites contra ZIP bomb, parser Binance existente, resultado de pesquisa separado de `ClosedCandle` e flags de direitos/trading todas falsas. Hash fornecido pelo chamador prova integridade relativa, NÃO autenticidade de fornecedor. J1 #2 e J3 #4 continuam bloqueadas para histórico real, universo point-in-time e validação OOS. Piloto real dependerá de revisão dos termos vigentes, elegibilidade territorial e permissão do titular, sem contornar HTTP451 via troca de host.



## J1/WU55 #217 — elo funcional offline arquivo -> SQLite Bybit (27/10/2026)

Prioridade modificada apos encerrar #208 sinteticamente: reduzir friccao ate obter historico real legal, em vez de infinitas microbaterias J3. scripts/import_private_bybit_research.py entrega importacao de manifest+instrument+kline local POSIX 0600 para SQLiteBybitResearchStore ja existente, com 3 opt-ins explicitos, permissao 0700, auditor WU48, commit atomico, replay/quality, falha sem I/O se falta consentimento, zero HTTP e nenhum arquivo real usado. Testes offline simulam ate tres candles e replay entre sessoes; resultados nunca promovem ClosedCandle/Top50/J2/J3/ordens. FAQ oficial Bybit agora traz referencia primaria de semantica generica turnover/volume e recomendacao de cache; legal/API Terms atual continua inconclusivo. **Nao alterar rights_authorized=false, nao coletar dados reais retentivos nem executar na VPS sem gate especifico.** Issue #217 continua aberta para autorizacao legal de retenção; #196 ticker 24h necessita confirmacao endpoint-specific/real; J1 #2 e J3 #4 abertas. Testar PR SHA exato com jobs docs/windows-offline/Chrome-PAPER e conferir merge/nonprod antes de considerar entrega concluida. Nenhum custo, ordem, rede market ou deploy.



## J4/J5/AUTO #232 — kill-switch PAPER duravel, sem acesso a corretora (27/10/2026 UTC)

Em resposta a necessidade concreta D77 de supervisao, o operador local pode persistir pausa de novas OPEN no journal AUTO2 SQLite existente. O modulo paper_operator_kill_switch.py grava somente chave opcional versionada paper_operator_kill_switch_v1 em paper_order_meta (sem tabelas novas), com estado active, sequence CAS, instante UTC-ms, acao pause/resume, JSON canonico e SHA256 de integridade. Ausencia de chave em banco antigo significa estado nao pausado legado; chave malformada/inesperada e bloqueada pelos leitores strict. Hash NAO autentica operador nem protege contra adversario que pode escrever no SQLite.

**Fio causal unico:** SQLitePaperOrderJournal._reserve_open_risk_locked combina (OR) a pausa persistida lida DENTRO de BEGIN IMMEDIATE com a flag do PaperRiskObservation; nenhuma fixture antiga com kill_switch_active=False pode ignorar pausa gravada. O caminho J6 step_durable_offline_paper usa o mesmo metodo e continua mantendo cursor de eventos no mesmo commit, inclusive em negacao de entrada. O metodo legado reserve tambem recusa OPEN enquanto pausado. REDUCE_ONLY PAPER hipotetico segue permitido; a chave nao cancela ordens pendentes, nao instala stops nativos, nao encerra posicoes, nao atua em qualquer exchange e nao autoriza negociacao real.

**Uso LOCAL futuro com arquivo POSIX 0600 em pasta 0700 ja existente** (nao executado na VPS): python3 -m scripts.control_paper_kill_switch --journal /arquivo/privado/orders.sqlite --action status; para pausar: --action pause --expected-sequence N; para retomar: --action resume --expected-sequence N --confirm-paper-resume. O status publica apenas sequence, UTC-ms e paused/not_paused, com flags live sempre falsas. Alteracao usa CAS e troca de estado sequencial, exige horario monotono e confirmacao de resume, nao permite escrever se o arquivo estiver ausente, com permissoes incorretas ou apontando a symlink/hardlink. Nenhum endpoint HTTP, chave ou rotina automatica de live e introduzido.

**Limites:** Gate PAPER local, nao kill-switch financeiro de producao; so protege caminhos de reserva de ordens de fixture no journal correspondente. Nenhuma autonomia de UI web sobre o estado sem autenticacao; nenhum deploy, VPS, testnet, ordem real ou custo novo. Tests adversariais incluem reinicio, corrida de duas instancias, metadado adulterado, OPEN legacy, risco com fixture stale, REDUCE_ONLY, cursor duravel, arquivos POSIX, CLI e reabilitacao explicita. CI docs, Windows offline e Chrome/PAPER no SHA final e obrigatoria; J4 #5/J5 #6/J6 #7 permanecem abertas e J1 historico permanece bloqueada.



## J6/PRE3 #234 — batch automatico FINITO de pesquisa PAPER, sem ordens reais (27/10/2026 UTC)

Entrega: `crypto_intelligence_agent/offline_paper_batch.py` reutiliza PRE2-B `step_durable_offline_paper` e `recover_durable_offline_paper` (mesmo SQLite AUTO2 e seus contratos), nao cria segundo ledger/cursor. Recebe candles ClosedCandle exclusivamente `quality=synthetic_fixture`, observacoes de risco PAPEL explicitamente ficticias e alinhadas por candle, configuracao J2/limites e journals existentes. Valida TODA a serie/identidade/horario antes do primeiro write, processa no maximo 64 candles novos por chamada, registra por passo resultado PENDING/recusa/no-signal sem produzir FILL, em `BEGIN IMMEDIATE` existente, e recupera restart comparando integralmente hash do prefixo, estrategia, venue, lot e inventario das OPENs. Novamente sobre dados totalmente processados = nenhuma nova escrita. Prefixo alterado, historico curto, risco com venue/tempo errado, metadata ou OPEN inconsistente: fail closed. Crash entre passos deixa somente commits completos, que sao retomados de maneira auditavel. O kill-switch PAPER D116 bloqueia novas OPENs sem esconder motivos de recusa nem retroemitir sinais antigos apos resume.

Comando demonstravel: `python3 -m scripts.demo_durable_offline_paper_batch` ou com `--demonstrar-pausa`. Ele cria candles inventados e sqlite TEMP, executa automaticamente uma sequencia de barras, simula reinicializacao do processo mediante reabertura do mesmo journal, completa o restante, verifica reexecucao sem duplicidade e remove os arquivos ao terminar. A saida e resumo em portugues de contagens/flags; nenhum dado bruto de mercado, chave, arquivo real ou ordem. Esta demonstracao NAO e daemon, fonte em tempo real, live feed, fluxo testnet, estrategia validada, resultado financeiro, exchange-native stop ou permissão de usar 50x. Nenhum job/cron/deploy foi ativado; custo adicional R$0.

Tests: primeiras 5 barras, abertura PAPER ficticia na sexta, checkpoint/OPEN pendente, reinicio, 0 duplicatas, pausa persistida, resume sem recuperar trade passado, limitacao de batch, validacao de todas observacoes, escala Decimal, alteracao retroativa de prefixo, falha entre passos, CLI e ausencia de rede. Aceite restrito a CI Linux/docs, Windows-offline, Chrome/PAPER no SHA exato de PR #235 (HEAD 9ae1097a71d0541c5dc56c04e04abaab76b0ddfb, integrada em e09ec9f5c9d9bb264def3c744303e929c8b5c2f8; CI pré/pós 3/3 SUCCESS), e revisao. J6 #7 permanece sem homologacao por falta de J1 canônico/licenciado, feed prospectivo verdadeiro, reconciliacao financeira, monitoramento continuo e seguranca de ordens reais; D77 destino automatico permanece.



## J5/UI #236 — tela local somente leitura com estado persistente PAPER (27/10/2026 UTC)

Problema: o dashboard de demonstração J5 mostrava apenas duas posicoes sinteticas fabricadas e NAO permitia ver se o kill-switch D116 e o cursor J6 PRE3 estavam de fato persistidos no journal em uso. Sem mudar o dashboard anterior, adicionar `crypto_intelligence_agent/paper_operator_status.py` e `scripts/render_paper_operator_status.py` com CLI `python3 -m scripts.render_paper_operator_status --journal /privado/orders.sqlite [--format html|json] [--output /caminho/novo.html]`. O leitor usa `_read_database` SQLite `mode=ro`/`PRAGMA query_only`, verifica esquema, meta keys, digest de cursor, identidade/inventario de OPENs, recupera pausa `paper_operator_kill_switch_v1` e compara o numero de OPENs pendentes/UNKNOWN pelo replay do journal. Falha fechada se houver corrupcao, chave desconhecida, caminho ausente, incongruencia de contagem ou dados de origem inesperada. So mostra estado deste arquivo AUTO2; NAO consulta conta, corretora nem posicoes AUTO4, e nao prova stop instalado. Nenhum endpoint HTTP ou credencial.

A pagina HTML offline em PT-BR apresenta um cabeçalho visivel 'SOMENTE SIMULACAO', estado de pausa de NOVAS OPENs PAPER, sequencia/horario UTC, contador de candles ficticios processados, quantidade de OPENs locais e UNKNOWN que precisa reconciliar. Layout responsivo sem overflow concebido para viewport 280..390px; CSS inline, sem script, rede, formulario ou botao que sugira dar ordens. CLI pode exibir JSON estrito ou HTML, opcionalmente criar arquivo novo com modo exclusivo sem sobrescrever. Leitura nao altera SQLite. O usuario que precisar alterar a pausa usa o controle local previamente homologado #232, nao a pagina. Nao mencionar 'robô ativo em producao' quando a pausa esta desligada: os outros gates financeiros seguem obrigatorios.

Testes: journal vazio, cursor com 6 candles e OPEN PENDING, restart, pausa/resume, UNKNOWN, checksum/meta corrompidos, arquivo ausente, HTML estatico/viewport/sem links de rede, sem leaks de caminhos/valores, JSON tipado, output exclusivo e no-network. J5 #6 continua sem produto online ou automacao de mercados; J1 #2 e J6 #7 ainda bloqueadas para dados reais/monitoramento. Nenhum release, migração, trading, acesso de conta, nova despesa nem VPS. Patch revisto; PR #237 (HEAD d38b7f6bd085e9e7cd668b72464d00743d237ac2) integrada em 4cdf6a8c51bd33a186a60a958bb3093a4280957f; CI pré e pós merge 3/3 SUCCESS no SHA exato. Nenhum review independente registrado.



## Checkpoint operacional verificado — J6/PRE3 e J5/UI (27/10/2026 UTC)

**Repo:** leandrosilveiradepaula/crypto-intelligence-agent; branch `main` conferida no commit `4cdf6a8c51bd33a186a60a958bb3093a4280957f`; nenhuma PR aberta no instante da verificação anterior ao checkpoint. **J6/PRE3 issue #234 (closed):** PR #235 merged squash, HEAD revisado `9ae1097a71d0541c5dc56c04e04abaab76b0ddfb`, main resultante `e09ec9f5c9d9bb264def3c744303e929c8b5c2f8`; CI pré e pós merge (docs/Linux unittest, windows-offline, Chrome/PAPER) 3/3 SUCCESS. Recuperação de cursor de fixtures, 1..64 passos de lote, pausa D116, pending paper e idempotência são funções realmente entregues, mas não há feed de mercado nem ordem real. Primeiro job Linux falhou exclusivamente porque um teste novo esperava DataValidationError para candle duplicado; teste corrigido para MarketDataError e CI reexecutada verde.

**J5/UI issue #236 (closed):** PR #237 merged squash, HEAD revisado `d38b7f6bd085e9e7cd668b72464d00743d237ac2`, merge/main `4cdf6a8c51bd33a186a60a958bb3093a4280957f`; docs/Linux, windows-offline e Chrome/PAPER pré/pós 3/3 SUCCESS. Leitor de journal read-only e HTML/JSON mobile PT-BR de status do cursor/pausa/OPEN pendentes/UNKNOWN foram entregues e testados; não controla exchange, não é rede, release ou produto hospedado.

**BLOQUEIOS REAIS:** J1 issue #2 ainda aberta: direitos de dados para uso histórico/produção (#217, #48), unidade/identidade/ticker e cobertura top50 histórica (#196, #32, #36, #19) não homologadas; J3 #4 segue sem backtest financeiro com dados reais; J4 #5 e J5 #6 sem execução/monitoramento de broker homologado; J6 #7 sem paper prospectivo de feed autorizado. Evidências sintéticas não provam lucro, custo, volume confiável, funding ou liquidação. D77 define ALVO de entradas e saídas automáticas, mas não concede chave, live/testnet/ordens ou deploy.

**Próximo passo seguro e autorizado:** priorizar diligência primária de direitos e acesso para J1, usando documentação e verificações sem credenciais nem market GET não aprovado, ou componentes internos PAPER/J5 independentes. Nenhum scraping para contornar HTTP451, nova coleta histórica real em SQLite, credencial, negociação/testnet, deploy, migration de produção ou gasto adicional sem gates pertinentes. Não abrir novas mini-PRs J3 apenas para repetir variações de cenários sintéticos. Orçamento R$0. Em nova sessão, verificar `main`, issues e CI antes de agir; nenhum executor assíncrono ficou ativo.



## J1/HIST #239 — série histórica multi-mês somente offline (27/10/2026 UTC)

`crypto_intelligence_agent/offline_vision_series.py` recebe **2..24** objetos `OfflineVisionMonth` já inspecionados por `inspect_offline_vision_month`, e monta uma série de pesquisa de 1h contígua em UTC, incluindo virada dezembro/janeiro, fevereiro de ano bissexto, mês integral, OHLCV Decimal e limite explícito de memória. Recusa arquivo reordenado/duplicado, mês ausente, identidade/símbolo alterado, dados de futuro, timestamps internos forjados, OHLC/volume inválidos, hash e nomes não canônicos. O hash do manifesto é somente uma soma de identidades dos ZIPs **alegadas pelo chamador**, não uma assinatura de Binance nem um hash de bytes reautenticado. Saída imutável `OfflineVisionResearchSeries` distinta de `ClosedCandle`; nenhum fornecedor, licença, feed, TOP50 histórico, desempenho, lucro ou ordem é homologado. Não existe fetch de ZIP/HTTP, cron, armazenamento de dataset nem execução de mercado. Os testes usam objetos totalmente sintéticos. Binance Vision Dataset Terms v1.0 (26/08/2026) autoriza estudos históricos estritamente pessoais não produtivos sob condições, NÃO autoriza usar arquivos no bot live, onde as fontes e direitos devem ser independentes. Nenhuma captura, download, uso de dados reais, ordem ou gasto. Esse avanço habilita montagem cronológica futura de dados legalmente obtidos, não constitui backtest financeiro J3 ou gate J1 liberado. Gates continuam `dataset_rights_authorized=false`, `canonical_ohlcv_approved=false`, `financial_backtest_approved=false`, `live_trading_authorized=false`. Issue #239 exige CI no SHA exato e merge não produtivo.


**J1/HIST #241 — auditor local multi-mês em desenvolvimento:** novo `scripts/audit_offline_vision_series.py` valida 2..24 ZIPs já disponíveis em diretório privado, hashes, meses e fechamento de candles, com JSON sanitizado. Tests sintéticos de cadeia completa e entrada hostil; nenhuma ingestão real, rede, licença, feed J2/J3, PnL ou ordem. Verificar PR, SHA e CI antes de concluir; J1 #2 e bloqueios de direitos persistem.


## J1/J3 #243 — diagnóstico mensal causal


Arquivos ZIP privados previamente obtidos sob termos aplicáveis podem ser inspecionados, sem rede, pelo comando `python3 -m scripts.audit_offline_vision_series --manifest /diretorio-privado/manifest.json --allow-personal-nonproduction-research --audit-directional-oos`. O módulo puro `vision_research_oos.py` reusa `assemble_offline_vision_months`, divide calendário em meses inteiros e seleciona **continuação ou reversão de retornos de fechamento** exclusivamente pelos resultados observados em meses ANTERIORES; a direção de referência majoritária também provém somente do treino. Para cada mês OOS retorna contagens de comparações ex-post do fechamento seguinte, sem preço, ativo ou informação de conta. Nenhum par cruza a fronteira de mês e retornos zero não geram acertos fictícios. Empates entre modelos produzem abstenção. Não há otimização dinâmica, simulação de entrada no fechamento, spread, fee, funding, liquidação, riscos de 50x, PnL ou desempenho financeiro aprovado.

A integridade estrutural e os hashes fornecidos pelo titular não autenticam provedor ou licença; o modo opcional não cria arquivos, não coleta mercados, não promove feed canônico ou execução, não calcula rentabilidade, não estabelece edge preditivo e não altera os bloqueios de direitos #217/#48, Top50 #2/#32 e J3 #4. `source_authenticated=false`, `dataset_rights_authorized=false`, `financial_backtest_approved=false`, `ready_for_trading=false`, `orders_sent=false`. Testes usam exclusivamente ZIPs sintéticos; CI Linux/Windows/Chrome e SHA exato exigidos para merge. Sem produção, custo, credenciais ou ordens.


## J1/WU56 #245 — contrato de inspeção offline

O módulo `bybit_research_series.py` lê um SQLite Bybit existente em `mode=ro` e `query_only`, verifica tabelas/metadados, hashes de páginas, integridade Decimal e continuidade UTC 1h, referência crypto-only declarada e base/quote consistente, retornando série congelada exclusivamente de pesquisa e hash determinístico de cabeçalhos. Dados não autenticados por hash continuam não autenticados. Não altera o banco, não coleta API, não entrega `ClosedCandle` canônico, ordens ou sinais. Uso somente em fixtures sintéticas até direitos e consentimento de retenção atestados. API Terms Bybit canônicos seguem insuficientemente verificáveis; recomendação de cache na FAQ não substitui licença de retenção/redistribuição. Rights #217/#48, Top50 #2/#32, ticker #196 e J3 #4 continuam bloqueados. Zero rede de mercado, credenciais, deploy, custo, migration ou trade. Testes Linux/Windows/Chrome/14 docs precisam passar no SHA exato para merge.


## D123 — Fonte de arquivos de trades públicos Bybit: pesquisa não significa licença live (28/10/2026 UTC)

Fonte identificada: Bybit official Docs https://bybit-exchange.github.io/docs/ encaminha histórico de market data e https://public.bybit.com/trading/BTCUSDT/ lista arquivos diários .csv.gz. Esses arquivos pertencem ao mercado Bybit, mas **não equivalem à API V5 candles** e trades não contêm por si só funding, mark/index, liquidação, contract point-in-time ou universo Top50. Uma tentativa de obter amostra oficial a partir deste ambiente falhou por DNS; portanto **não houve download real validado, cobertura real homologada nem schema CSV real verificado neste checkpoint**. O parser `bybit_public_trade_archive.py` é candidato estrito de esquema e somente testes sintéticos, não pode ser promovido a feed canônico. A documentação pública anuncia uso histórico para backtest, mas API Terms canônicos atuais e direitos de retenção/redistribuição/comercialização/live seguem não comprovados para o projeto; não presumir licença ampla. O uso permitido de pesquisa deve ser avaliado no escopo aplicável antes de baixar/armazenar. Não houve rede de mercado aprovada, arquivo persistido, dado privado, gasto, release ou ordem. J1 #2/#217, J3 #4 e #32 continuam abertas.


**Implementação de sonda one-shot:** `scripts/probe_bybit_public_trade_archive.py` só permite GET exato de `https://public.bybit.com/trading/BTCUSDT/BTCUSDT2020-03-25.csv.gz` quando flags `--allow-public-network --allow-one-public-archive-probe` estão ambas presentes. Limite 5 MB gzip/30 MB CSV, timeout 10s, nenhum redirect, proxy, retry, armazenamento ou credencial; relatório apenas contagens/UTC/digest, flags live/canonical/rights falsas. Workflow `bybit-public-archive-once.yml` **não executa em push/PR/cron**, apenas comentário exato de autor titular `/probe-bybit-archive-once-v1` na issue #247, main já integrada. CI usa transporte falso e gzip sintético. A fonte alternativa não muda as restrições jurídico-territoriais e o smoke pode falhar por formato, tamanho, licença ou rede; proibir tentativas de bypass. A descrição técnica de campos segue candidata, pendente de amostra oficial; este contrato falha fechado se surgirem colunas novas/arquivo real com outro esquema.


## D124 — J1/HIST #247 — primeiro arquivo de trades Bybit REAL verificado, sem retenção (28/10/2026 UTC)

**Execução comprovada:** workflow owner-only https://github.com/leandrosilveiradepaula/crypto-intelligence-agent/actions/runs/40613330522 (SUCCESS em 28/10/2026 01:09:47 UTC), proveniente da PR #248 integrada por squash na main `910a557f92a0aec15c5d82514a0f964d17d77bb8`. Foi realizada **uma única requisição GET** ao arquivo público da Bybit `https://public.bybit.com/trading/BTCUSDT/BTCUSDT2020-03-25.csv.gz`. O parser validou seu formato CSV gzip, 2.693 trades de BTCUSDT, 14 horas UTC distintas com negociações, primeiro timestamp `1585132572982`, último `1585180700064`, SHA-256 sobre o gzip obtido `cbca6933a8f0a11429661cfa93b04056055d776ee199209e8af9719ad2060a33`. Não há evidência de continuidade 24h neste primeiro dia parcial, nem cobertura de 50 ativos. O primeiro download tentado em outro ambiente falhara por DNS; esta execução no GitHub foi bem-sucedida. Bytes permaneceram em RAM transitória do runner, **nenhum dado bruto foi persistido ou publicado**. CI pré-merge Linux/docs/Windows #40612939369 SUCCESS, Chrome/PAPER #40612939237 SUCCESS. Nenhuma ordem, conta, segredo, deploy ou gasto.

**Limite de aceite:** isto comprova disponibilidade e esquema da amostra de 25/03/2020, não contrato/licença de retenção histórica ou redistribuição, dados comerciais, funding/mark/index/liquidação, histórico point-in-time Top50, viés sobrevivência ou resultados de estratégia. `dataset_rights_authorized_for_production=false`, `canonical_ohlcv_approved=false`, `historical_top50_approved=false`, `real_financial_backtest_approved=false`, `live_trading_authorized=false`. J1 #2 e Bybit rights #217 permanecem abertas. Próxima ação substantiva: separar direitos de pesquisa privada vs retenção longa/produção e validar série histórica contínua com origem, qualidade e custos correspondentes à venue. Nunca usar este smoke como autorização de trading real.


## D125 — J1/HIST #250 — continuidade estrita de sete arquivos diários (28/10/2026)

`bybit_archive_week.inspect_seven_daily_archives` reutiliza o parser offline Bybit validado por smoke real para aceitar **exatamente sete arquivos UTC diários consecutivos** BTCUSDT. O algoritmo exige dias sem duplicação/reordenação, valida cada CSV gzip sob limites preexistentes de bytes/linhas, soma trades e horas com transações, informa horas SEM transações separadamente e cria SHA-256 determinístico de recibos. Ausência de transações **não prova ausência de trades na venue**: horário sem trades fica lacuna de cobertura, nunca candle preenchido. O relatório não contém OHLC ou mercado bruto e não retém dados em disco. Testes são sintéticos; ainda não há semana real homologada. `rights_authorized=false`, `canonical_ohlcv_approved=false`, `financial_backtest_approved=false`, `live_trading_authorized=false`; nenhuma ordem, rede, implantação, migração ou custo. J1 #2 e direitos #217 continuam abertos. Próximo gate: amostra semanal efêmera e cobertura real com direitos vigentes verificados, depois OHLCV/custos/funding/mark antes de J3.


**Sondagem owner-only semanal preparada:** `scripts/probe_bybit_archive_week.py` realiza até 7 GETs sem credencial nem proxy/redirecionamento/retry de 2020-03-25 a 2020-03-31, todos de `https://public.bybit.com/trading/BTCUSDT/`, cada gzip limitado a 5 MB e 150 mil trades, com 10s de timeout, agregando somente contagens e digest; os bytes ficam somente em memória e não são enviados à UI, logs ou repo. A workflow `.github/workflows/bybit-public-archive-week.yml` requer comentário EXATO do owner na issue #250 e **não dispara em push, PR ou cron**. Um dia indisponível encerra sem buscar outro host. O recibo semanal é diagnóstico de dados reais, não licença, nem candles fechados, funding/mark, universo Top50, backtest ou ordem. Testes usam somente payload sintético/transport falso e gate permanece fechado. Executar apenas após CI/merge no SHA exato.


## D126 — Evidencia semanal real J1 #250

Execucao GitHub Actions `40620522744` SUCCESS, 28/10/2026 UTC: 7 GETs de BTCUSDT 25–31/03/2020; 54.677 trades, 158/168 horas com trades, 10 sem trades observados, um dia parcial; manifesto SHA256 `ffb13c6d46d539628b95ed645bd760fc4f8559604e0e2970ee3e3b5371e96b70`. Dados apenas em RAM efemera, sem persistencia ou ordens. Cobertura observada nao prova feed integral; direitos de retencao/live e backtest financeiro continuam nao aprovados. J1 #2 e rights #217 permanecem abertas.


**J1/HIST #253 — próximo contrato de pesquisa:** reconstrução trade-derived horária Decimal, microssegundos ordenados, 168 slots explícitos e flags de ambiguidades; relatório privado de qualidade sem preço, volume, símbolo nem retenção. Acesso real semanal D126 comprovado, porém backtest financeiro, licença de retenção e feed canônico continuam pendentes. PR e CI devem ser verificadas antes do aceite; dados de mercado reais não foram salvos e nenhuma negociação foi autorizada.


## D128 — J1/HIST #253 — reconstrução horária real efêmera (28/10/2026 UTC)

**Prova reproduzível:** [GitHub Actions #40624688974](https://github.com/leandrosilveiradepaula/crypto-intelligence-agent/actions/runs/40624688974), job `hourly-quality` SUCCESS em 28/10/2026 03:05:48 UTC, `main` na execução `1e7ee14270b2bfd04b2700b1d662029b957a6128`. Sete GETs fixos do arquivo público Bybit BTCUSDT 25–31/03/2020, **54.677 trades**, 158 horas 1h com negociações observadas, 10 sem negociações observadas, 1 dia parcial. Entre 158 horas com trades, **145 têm fronteiras open/close não ambíguas dentro dos trades observados** e **13 têm ao menos uma fronteira com múltiplos preços no mesmo timestamp**. O código não preenche as 10 horas, nem cria open/close arbitrário nas 13 horas ambíguas. SHA-256 do manifesto de arquivos (não assinatura da Bybit): `ffb13c6d46d539628b95ed645bd760fc4f8559604e0e2970ee3e3b5371e96b70`. Bytes brutos e OHLC/volume derivados somente em RAM transitória; stdout sanitizado inclui exclusivamente contagens, flags e digest, **não** preço, volume, arquivo privado, credencial ou símbolo. `data_stored=false`, `orders_sent=false`, 7 solicitações GET, nenhuma negociação/deploy.

**Escopo do aceite:** comprova algoritmo sobre amostra pública real e controle das fronteiras, NÃO completude de transações intra-hora, identidade econômica histórica de contratos, fidelidade ao candle da corretora, marcação de funding/mark/index/liquidação, histórico Top50, direitos de retenção/distribuição/uso comercial, rentabilidade ou prontidão de produção. `rights_authorized=false`, `source_authenticated=false`, `canonical_ohlcv_approved=false`, `historical_top50_approved=false`, `financial_backtest_approved=false`, `live_trading_authorized=false`. PR de código #254 (HEAD validado `c6067c06ce663cc82c1d86fee50ae14d80928b74`) integrada no SHA acima após CI pré-merge Linux/Windows/docs #40624482097 e Chrome/PAPER #40624482139, ambas SUCCESS. J1 #2 e direitos #217 permanecem abertas; próxima ação segura: investigação documental dos direitos e confronto com fontes independentes de OHLCV e metadados de contratos antes de validar backtests financeiros, sem ordens reais.


**J1/HIST #256 — validação contratual offline:** novo reconciliador de OHLC hourly trade-derived vs schema V5 linear e contagens de relações Decimal dos trades, com workflow owner-only de até sete GETs fixos. Comparação contra dados V5 reais ainda bloqueada por acesso/direitos e NÃO homologada. Sem armazenamento, ordens, custos adicionais ou promoção de sinais. Evidência de acesso semanal D126 e qualidade horária D128 preservadas; J1 #2 e rights #217 abertas.


## D130 — J1/HIST #256 — auditoria de relações numéricas em trades reais, sem promoção (28/10/2026 UTC)

**Execução comprovada**: [GitHub Actions #40629733622](https://github.com/leandrosilveiradepaula/crypto-intelligence-agent/actions/runs/40629733622), job `report-only` SUCCESS às **03:59:27 UTC**, SHA de código `04be5240db169344640e72bb313041e557171549` (PR #257). Uma única sondagem owner-only de **sete GETs** fixos ao arquivo público `trading/BTCUSDT` de **25 a 31/03/2020**: **54.677 negociações**, 158/168 horas com trades observados, 10 sem trades observados, 13 com fronteiras ambíguas, 1 dia parcial. O relatório observacional calculou `size == homeNotional` em **54.677/54.677** registros e `foreignNotional == price * homeNotional` em **54.677/54.677** registros; divergências numéricas observadas 0 em ambas relações. Reconciliado contra o mesmo manifesto SHA-256 `ffb13c6d46d539628b95ed645bd760fc4f8559604e0e2970ee3e3b5371e96b70` da D126/D128. **Dados e derivados apenas em RAM transitória**, `data_stored=false`, `orders_sent=false`, nenhum segredo, produção ou gasto.

**Limites:** estas duas igualdades aritméticas NÃO constituem validação de unidades econômicas históricas, especificação do contrato, fidelidade de execução, volume da API V5, direitos de retenção, top50 ou backtest. O reconciliador `bybit_trade_kline_reconciliation.py` foi aprovado em CI com **referência V5 sintética**; **não ocorreu comparação com um candle V5 real**, pois o endpoint anteriormente teve restrições e a licença vigente continua não comprovada. Proibido tentar contorno por proxy/host alternativo. `volume_units_verified=false`, `rights_authorized=false`, `source_authenticated=false`, `canonical_ohlcv_approved=false`, `historical_top50_approved=false`, `financial_backtest_approved=false`, `live_trading_authorized=false`. J1 #2 e direitos #217 permanecem abertos. Próxima ação: comprovação independente de direitos e acesso legítimo a referência histórica da mesma venue/contrato, verificação point-in-time de metadados, depois expansão e J3 financeira — sem ordens reais.


**J1 #259 — pipeline mensal offline Binance Vision:** adicionada conferência opcional de sidecars ZIP.CHECKSUM locais, reaproveitando parser/replay existentes; não é novo feed. Direitos já documentados D114, reconfirmados D131: datasets CC BY-NC-SA somente pesquisa não produtiva e proibição de trading live (§4.2). Sem download real, ordens, custos ou deploy. J1 #2 e rights #217 abertas até histórico licenciado e venue validada; testes e CI necessários para aceite.

## J1/D132 — evidencia primaria de direitos Bybit e alerta de identidade 2020 (28/10/2026)

Checkpoint sincronizado: PR #260 integrada, issue #259 encerrada e `main=390ce4a34100b87cbb0790c2363e8a19d18066e1` na abertura desta unidade. CI #40631665959/#40631665982 (HEAD pre-merge) e #40631860169/#40631860194 (HEAD pos-merge) verificadas SUCCESS; 0 PRs abertas nesse instante. Progresso documental: PDF oficial Bybit de 7 paginas efetivamente lido (regras para APIs e Service Data), mas a pagina canonica recente nao exibiu texto integral, e a aplicabilidade dos termos a arquivos publicos de trades nao foi comprovada. Exemplo de `launchTime` BTCUSDT de 30/03/2020 nao prova identidade historica dos trades reais observados desde 25/03/2020; exige registro point-in-time. Matriz de fontes oficiais para Kline/Mark/Index/Funding atualizada sem GET. Nenhum dado novo coletado, codigo alterado, ordem, custo ou release. J1 #2/#217 abertas; todos os gates de dados canônicos, direitos, backtest financeiro e live permanecem falsos. Detalhes D132 / PROVIDER_RIGHTS / J1_SOURCE_GATES.


## J6/PRE7 #266 — matriz de recuperacao PAPER com evidencia de replay (28/10/2026)

Unidade coesa: utilizar o replay duravel sintetico AUTO2 e o journal AUTO4 para cobrir sem cursor, cursor sem OPEN, OPEN pendente/UNKNOWN, FILL orfao, hipotese de posicao, REDUCE_ONLY parcial e total, runner residual, kill-switch e dados corrompidos. A API `inspect_local_paper_recovery_status` passa a comparar duas leituras read-only de cada diagnostico; qualquer divergencia observada retorna UNVERIFIED. A comparacao nao prova atomicidade entre bancos nem elimina races nao observadas. CLI preserva apenas JSON sanitizado e os gates `new_open_authorized=false`, `native_stop_verified=false`, `live_trading_authorized=false`. Issue #266; entrega sujeita a CI Linux/Windows/Chrome, revisao e merge no SHA exato. Sem ordens, mercado real, deploy ou dados autorizados de J1.


## J5/J6/PRE8 #268 — visualizacao estatica de recuperacao PAPER no celular (28/10/2026)

O diagnostico multi-journal PRE7 ganha opcao CLI HTML PT-BR com aviso de estado e gates de seguranca sempre negados, mantendo JSON anterior intacto. Documentos gerados apenas localmente: sem frontend remoto, autenticacao, servidor, JavaScript ou botao de negociacao. QA Chrome das seis dimensoes existentes para tres estados diagnosticos, testes de output exclusivo, sanitizacao e regressao de replay verdadeiro. Aceite sujeito a 3 checks de CI e merge SHA exato; o painel nao e produto pronto/live, backtest financeiro, venue ou dados legitimamente homologados.


## J5/J6/PRE9 #270 — painel de operador PAPER com posições explicitamente selecionadas (28/10/2026 UTC)

Base de código: `main=9e4a33e5961fdcd725237faccb5a028437364f92` antes da issue #270 (PR #269 integrada, CI pós-merge Linux/Windows/Chrome aprovada; zero PRs abertas). Unidade ativa `work/issue-270-j5-operator-overview`: composição read-only dos diagnósticos AUTO2/AUTO4 com posições AUTO4 apontadas via `--position-id` na CLI existente `scripts.inspect_paper_recovery`; nenhuma listagem automática ou soma entre símbolos, nenhum novo schema SQLite. O JSON sem seleção continua exatamente como PRE8; seleção gera objeto `paper_operator_overview_v1` e HTML insere cartões já suportados pelo renderizador de múltiplas posições, com aviso explícito de recorte parcial e sem autorização de ordens.

Aceite requerido: teste E2E de cursor, FILL hipotético, estado BLOCKED, runner, saída encerrada, mudança entre consultas, corrupção/IDs inválidos, CLI JSON/HTML sem vazamento de caminhos, export exclusivo e proibição de rede; QA Chrome da página unificada em seis larguras, além das três condições anteriores. Validar Python/docs Linux, Windows e browser Chrome, revisar SHA exato, integrar somente com CI verde e verificar pós-merge. Não autorizar negociações ou deploy; J1 #2/#217, J3 e J6 #7 continuam independentes e bloqueadas conforme seus aceites.


## J6/PRE10 #272 — alertas locais de mudança PAPER sem motor real (28/10/2026 UTC)

Checkpoint anterior verificado: PR #271/#270 encerradas, `main=a9c1412427db9791ff1a66417768ab5a4a73c3aa`; CI pós-merge Linux/docs/Windows e Chrome em SUCCESS. Próxima unidade autorizada #272 na branch `work/issue-272-j6-observer-alerts`: reusar inspectores PRE7/PRE9 e sua página estática para observar 1..16 amostras em sequência MANUAL, detectar mudança de estado e saldos de posições selecionadas sem divulgar saldos, e evitar alertas repetidos. Exigir saída sanitizada, alerta CRITICAL para UNVERIFIED, nenhum falso sinal de segurança/execução e no máximo 60s de atraso programado por execução. Nenhum daemon, cron, push, ordem, mercado real, PnL ou deploy. QA Chrome adiciona cenário de timeline às dimensões existentes, testes e CI com SHA exato; aceite e integração só após revisão e gates verdes. J1 #2/#217, J3 #4, J5 #6 e J6 #7 seguem abertas.


## J1/WU56 #274 — auditoria de integridade do armazenamento Bybit sob concorrência (28/10/2026 UTC)

A próxima correção da J1 foi escolhida por defeito concreto e reproduzível, não por novo protótipo de rede: `quality_report` no SQLite isolado Bybit contava candles e validava páginas em transações distintas e podia apresentar evidências misturadas sob escritor concorrente. WU56 centraliza todas as leituras de qualidade e replay em um único snapshot estritamente read-only (`mode=ro`), reutiliza o mesmo validador de página, verifica schema, origem, foreign keys, digest e valores econômicos exatos e mantém diagnóstico explícito de lacunas. Testes devem demonstrar que o escritor WAL não é bloqueado e o relatório antigo não incorpora página nova parcialmente. Não alterar SQLite canônico, ingestão real, sinais, negociação ou direitos.

**Documentos primários revisados:** o FAQ Bybit API recomenda cache/banco local por resiliência, mas isto não substitui os API Terms aplicáveis; PDF oficial hospedado pela Bybit restringe revenda/exploração comercial e não prova licença geral de arquivo histórico; página canônica não expôs texto integral atual. Logo `rights_authorized=false`, `source_authenticated=false`, `canonical_ohlcv_approved=false`, `historical_top50_approved=false`, `financial_backtest_approved=false`. J1 #2 e #217 não são homologadas. Issue #274 / branch `work/issue-274-j1-bybit-snapshot-quality`. Aceite exige CI Linux/docs, Windows e Chrome, revisão de diff/head SHA, merge sem produção e CI pós-merge com evidências vinculadas.


## J1/WU57 #276 — integridade uniforme do replay privado Bybit (28/10/2026 UTC)

Nova unidade após a WU56/PR #275, base `main=e9fd81ac98e4ebe9d36105188ac91ca4ca0d2b16`. O auditor de séries `bybit_research_series.inspect_existing_bybit_research_series` passa a reutilizar o mesmo validador estrito de páginas já empregado por `replay_page` e `quality_report`, dentro do próprio snapshot `mode=ro` existente. Também exige `PRAGMA foreign_key_check` para recusar dados órfãos; entradas com SHA de metadados sinteticamente falsificado não podem passar somente por contiguidade e hash dos headers. Testes de WAL concorrente, duas páginas, hash inválido e órfãos exigidos. Sem expansão de endpoints, ingestão de mercado, informações reais, canonização, ordens ou produção.

J1 #2 e direitos #217 continuam bloqueados; sucesso em fixture somente significa integridade técnica de pesquisa, não direitos, origem, funding, universo histórico Top50 ou retorno financeiro. Issue #276, branch `work/issue-276-j1-bybit-series-reuse`. Gate de aceite: CI Linux/docs, Windows e Chrome no SHA exato, revisão do diff, merge sem produção e checagens pós-merge documentadas.


## J4/J3/PRE11 #278 — pré-voo de margem e alavancagem PAPER somente offline (28/10/2026 UTC)

O contrato `paper_margin_preflight` conecta os existentes `PaperOrderIntent`, `SyntheticLeverageSettings`, `PaperRiskLimits` e `PaperRiskObservation` a uma fixture linear de Binance USD-M/Bybit V5. Inspeciona entrada OPEN apenas em simulação: igualdade exata de margem em quote × alavancagem com quantidade base × mark fictício, cap de alavancagem, step de quantidade, mínimo de quantidade/notional e teto de notional, validade temporal e precedência do kill-switch/UNKNOWN/RiskGate. Sem arredondamento silencioso ou conversão USDC/USDT/USD. Inclui regressões de margens exemplificativas 1/5 em 50x. O tick da fixture é metadado e não executa preço limite. Função não está conectada à reserva AUTO7, pois ainda faltam regras reais de venue, conta/mark e ledger de margem por posição.

**Não promove** dados J1, contrato da corretora, backtest financeiro ou operações reais. Issue #278, branch `work/issue-278-j4-margin-open-preflight`; gates: Linux/docs, Windows e Chrome verdes no SHA exato, revisar diff, squash merge sem deploy e confirmar CI pós-merge. J1 #2/#217, J3 #4, J4 #5 e J6 #7 abertas. Direitos de retenção histórica Bybit seguem pendentes de comprovação externa conforme comentário novo de #217; nenhum GET real ou custo adicional.


## J4/J6/PRE12 #280 — pré-voo de margem incorporado opcionalmente a OPEN causal PAPER (28/10/2026 UTC)

Depois da #278/PR #279 integrada (`main=022bbc1ea5e3ce65fad8bd3bbfe22ed3df0a79e0`, CI pós-merge Linux/Windows/Chrome verde), o mesmo preflight de margem 50x/lote/notional será acionável por `margin_preflight=PaperMarginPreflightRequest(...)` no fluxo `prepare_causal_paper_open` / `reserve_causal_paper_open`. Sem solicitação, comportamento anterior intacto e nenhuma aprovação implícita de margem. Com solicitação, negar incompatibilidades antes de transação AUTO2; quando compatível, ainda reexecutar health e RiskGate existentes sob lock. Snapshot `CausalPaperOpening.margin_assessment` é apenas em memória, não posição persistida; nenhuma nova OPEN real e nenhuma mudança REDUCE_ONLY. Regressões com journal SQLite sintético, 1/5 USDT, 50x/20x, kill-switch/UNKNOWN, pausa, double-open, contrato cruzado, no-signal e no-network.

**Gates:** CI Linux/docs/Windows/Chrome e revisão SHA; merge squash apenas se 3 checks verdes, verificar pós-merge e registrar issue #280. J1 #2/#217, J3 #4, J4 #5 e J6 #7 seguem abertas. Não implementar preço real, funding, stop, exposição de conta, deploy ou ordens.


## J4/AUTO9 #282 — recibo versionado de margem na mesma transação OPEN PAPER (28/10/2026 UTC)

`PaperMarginIntentReceipt` com versão `paper-margin-intent-v1` grava, opcionalmente, a configuração de margem quote/50x e notional hipotético no mesmo commit SQLite da OPEN AUTO2. Vincula a configuração ao SHA256 da intenção completa e preserva entrada PENDING sem inventar FILL. Novo leitor read-only `read_margin_receipt` realiza inspeção estrita de schema/meta, vínculo causal e dados exatos, com fail-closed de órfãos, duplicações/corrupção; retorno `None` para legacy sem opt-in significa **configuração não verificada**. Atualizar configuração global não reescreve recibos anteriores.

**Não** grava colateral ou alavancagem efetiva na posição AUTO4, não prova exchange, não homologa J1/J3/J4/J6 nem conecta API real. Issue #282, branch `work/issue-282-j4-atomic-margin-receipt`; próxima WU independente deverá vincular receipt à posição confirmada sem supor cross-file atomicity. Exigir CI Linux/docs, Windows, Chrome e pós-merge no SHA exato, revisão/merge seguro sem deploy. Bloqueio direitos históricos Bybit #217 inalterado; custo adicional R$ 0,00.


## J4/AUTO10 #284 — recibo 50x de OPEN incorporado à posição PAPER confirmada (28/10/2026 UTC)

Depois da PR #283/issue #282 (`main=b4aa10e178ca16d091be2f4b187b98831ba39d7f`, CI pós-merge verde), a criação opcional de posição AUTO4 com `opening_order_path` exige leitura RO do OPEN completo AUTO2 e importa seu recibo de margem/alavancagem somente se o replay terminal contiver **FILL positivo**. `PaperPositionBalance` expõe leverage/margem quote **solicitados**, não colateral real ou resultado. O payload antigo permanece imutável sem envelope; nenhuma migration. Auditoria cruzada `inspect_paper_position` e `paper_open_health` recusa receipt ausente num lado, falsificado ou inconsistente; saúde retorna UNKNOWN e bloqueia novas OPENs. O bundle de testes adversariais cobre reinício, parcial cancelada, saídas, no-network e corrupção re-hash.

**Issue #284**, branch `work/issue-284-j4-filled-position-margin-binding`. Aceite exige CI Linux/docs, Windows e Chrome verdes no SHA exato, revisão de diff, merge sem produção e pós-merge + evidências. Ainda faltam marcações reais de margem/alavancagem/funding/stop/fees/liquidação, J1 #2/rights #217 e J3 #4/J4 #5/J6 #7. Sem ordens, mercado real, credenciais, gasto ou deploy.


## J5/PRE13 #286 — exibição móvel conservadora de margem/leverage solicitados (28/10/2026 UTC)

Após #282/#284 e seus gates integrados, a leitura individual e múltipla de posições PAPER exibe os parâmetros solicitados presentes no recibo versionado, sem confundi-los com margem real aceita pela exchange. JSON v1 mantém `margin_intent_requested` allowlisted (ou `null` em posição legacy), e HTML mostra o valor 50x/5 USDT somente se registrado; “não registrada” caso contrário. Sem preço, notional, saldo, PnL, conversão entre moedas ou posição live. Testes Python e Chrome para seleção mista, ausência de rede, CSP e tamanhos mobile; revisão SHA/CI antes de merge. Issue #286, branch `work/issue-286-j5-paper-margin-mobile`. Homologações J1/J3/J4/J5/J6 ainda dependem de dados/venue/financeiro reais e gates humanos.


## J5/PRE13 #286 — configuração de margem/alavancagem solicitadas visível em telas PAPER (28/10/2026 UTC)

Após WU #284/PR #285 integrada (`main=106ebd5f14ed289238124ede56a30c232671d51a`, CI pré/pós-merge Linux/Windows/Chrome SUCCESS), a UI read-only PT-BR de posição individual e cartões de múltiplas posições passa a mostrar margem e leverage **solicitados** no recibo `opening_margin_intent_v1`, apenas de fixtures PAPER. Campos de JSON estritamente permitidos, flags de moeda e venue não verificadas; não exportar mark, PnL, saldo ou notional, não somar quotes, nem converter USD. Registros legados exibem “Não registrada”, não 50x por padrão. A visualização cross-file opcional só diz conferida se AUTO2/AUTO4 realmente comparados com D142; CSP bloqueia scripts/rede, layout responsivo e acesso por teclado mantidos.

Issue #286, branch `work/issue-286-j5-paper-margin-mobile`. Gate: testes offline de JSON/HTML, negativos/legado/CSP, Chrome nas seis larguras, CI Linux/docs, Windows, revisão do diff no SHA exato, squash merge sem produção e CI pós-merge. J1 #2/#217, J3 #4, J4 #5, J6 #7 abertas; nada autoriza mercado ou ordens reais.


## J5/J6/PRE14 #288 — seleção PAPER com crosscheck local opt-in (28/10/2026 UTC)

A PR #287/#286 foi integrada em `90830b2497e82a9a8c91e5660edbbffc05a690a6` com checks pré e pós-merge verdes. A branch `work/issue-288-j5-multi-paper-crosscheck` estende o leitor multiposição com conferência facultativa do AUTO2 e sinalização explícita de proveniência no mobile. Sem crosscheck o comportamento legado persiste. A conferência é all-or-nothing, estritamente local e sem atomicidade entre bancos; não autentica exchange. Aceite depende de CI Linux/docs/Windows/Chrome e SHA revisado antes do merge sem produção. J1 #2/#217, J3 #4, J4 #5, J5 #6 e J6 #7 permanecem abertas.


## J3/PRE15 #290 — faixa condicional de risco de margem em fixtures (28/10/2026 UTC)

Base `main=57eec4553af9df94f42469c0e31fa7ca87bd4bcb` após #288/#289 integrada e CI pós-merge verde, sem PRs abertas no início. Branch `work/issue-290-j3-adverse-margin-envelope`. Implementação de resultado condicional pior/melhor sobre margem fictícia em 50x e revalidação de aumento adverso de fees/slippage por PRE6, testes de precisão/ausência de FX e limites. Gatilho de possível perda acima da margem é APENAS cenário assumido, não equação de liquidação; não há backtest financeiro real ou ordem. Gates de CI Linux/Windows/Chrome e revisão SHA antes de merge sem deploy; J1 #2/#217, J3 #4, J4 #5, J6 #7 seguem abertas.


## J3/PRE15-B #290 — ligação de envelopes com PRE7/OOS (28/10/2026 UTC)

Após PR #291 integrada em `main=676ac1582493f97d1ec2ca4aa6578d053ccc2659`, branch `work/issue-290-j3-oos-margin-audit` acrescenta auditoria causal dos eventos com resultados condicionais: requer margem e choque por candidato e revalida PRE6 contra o resultado PRE7 exato. Eventos abstidos continuam sem resultado; nenhum lucro, perda financeira real ou liquidação de exchange. Exigir CI Linux/Windows/Chrome, revisão SHA, merge seguro e pós-merge. J3 #4 permanece não homologada.


## J3/PRE16 #293 — replay causal de mark/funding/manutenção (28/10/2026 UTC)

Verificado `main=4576ebcab57a6b7dce9f4b5fdbf44824ce298cce` após duas PRs #291/#292 integradas e CI verde; nenhuma PR aberta no começo. Issue #293 e branch `work/issue-293-j3-temporal-mark-replay`: motor financeiro sintético de posição única, mark/trade distintos, manutenção hipotética, funding e custos PRE2, precedência de liquidação, gatilhos de STOP/TARGET sem inferência de OHLC. Testes adversariais e D146/arquitetura/validação. Gate para integração: CI Linux/Windows/Chrome e revisão SHA exato, squash sem produção, pós-merge. Nenhuma ordem real; J1 #2/#217, J3 #4 e J6 #7 abertas.


## J3/PRE17 #295 — coestresse, exposição e concentração em carteiras fictícias (28/10/2026 UTC)

Base verificada `main=8127c77f3abfa353bb98d2346fe15856bffcc7f7` (issue #293/PR #294 integrada com CI pós-merge verde); nenhuma PR aberta antes deste bloco. Issue #295 e branch `work/issue-295-j3-portfolio-mark-risk`. Novo agregador de 2..16 posições de fixture em relógio comum que reutiliza PRE16, contém risco bruto/assinado, margem/equity/maintenance de buckets isolados, concentração e marks adversos simultâneos. Não produz PnL de carteira, correlação estatística nem fórmula de cross margin. Gates: CI pré-merge Linux/Windows/Chrome, SHA revisado, squash sem produção, CI pós-merge e evidência em issue; J1 #2/#217, J3 #4 e J6 #7 abertas.


## J1/HIST #297 — aquisição controlada do primeiro histórico privado (28/10/2026 UTC)

Fonte de verdade inicial `main=d96691aaff1ece7fec8f2d1fbae8e210be21f25f`, zero PRs abertas; issue #297 e branch `work/issue-297-j1-private-vision-capture`. Rota escolhida **para pesquisa, não trading**: termos Binance Vision CC BY-NC-SA v1.0/26-08-2026 concedem backtest pessoal não produtivo, vedam datasets para execução live. Entregue CLI owner-only para 2 meses contíguos BTCUSDT USDT-M 1h, com 4 GETs ao host fixo (ZIP+checksum), sem retry/redirect/proxy e sem dados de mercado em log, staging privado condicionado a 4 opt-ins. CI somente com fake transporte e ZIPs sintéticos; nenhum download real, aceite contratual, criação de arquivo em VPS ou alteração de release. J1 #2 e Bybit rights #217 abertas. Próxima ação após CI/merge: execução owner-only somente com aceite pessoal de termos, território e acesso a diretório privado; reportar contagem e checksum sanitizados. Dados nunca para live.


## J1/HIST #299 — aceite de termos e correção de segurança de captura (28/10/2026)

Titular manifestou 'Li e aceito' para termos Binance Vision de pesquisa pessoal não produtiva. O ambiente ChatGPT atual não oferece SSH/shell na VPS; não inventar arquivo retido ou origem real. PR de correção da captura #298: limpeza agora só remove diretório criado pela própria execução (protege concorrente). Manifesto last-write, sem alegar transação atômica. Ainda requer confirmação territorial/acesso e execução owner-only na VPS, nunca no GitHub Actions; nenhum dataset para live (Vision §4.2). J1 #2, Bybit #217 abertas.


## J1/HIST #301 — segurança da primeira retenção de histórico (28/10/2026)

Base `main=ef3893334c690e7f1025e6066bc6a8e2eca3e910` após #300 integrada e pós-merge Linux/Windows/Chrome aprovados, zero PRs abertas na abertura. Issue #301 / branch `work/issue-301-j1-vision-real-archive-readiness`: header Vision exato opcional; estágio privado temporário, reauditoria de disco e publicação Linux atômica sem substituição. Não há acesso SSH ao VPS nem coleta real verificada nesta sessão, embora licença para pesquisa pessoal não produtiva tenha sido aceita pelo titular. J1 #2 e Bybit #217 continuam abertas; dados não são autorizados para trading live, sem deploy ou custo.


## J1/HIST #303 — falha real de header Vision identificada em SSH (28/10/2026 UTC)

Main verificada em 1a73bf7e34bee89b182555bb0151e623dcf446eb antes da branch work/issue-303-j1-vision-observed-header, com zero PRs abertas. A execução SSH do titular localizou DataValidationError em VALIDACAO_CSV no ZIP de agosto, após GET e SHA: aliases nominais curtos, não dados inválidos comprovados. Issue #303 corrige o parser de headers exatos, com regressões sintéticas e fluxo de 1.464 candles via fake HTTP. Nenhuma captura real publicada. Gates CI Linux/docs, Windows e Chrome e revisão do SHA; merge seguro sem deploy. J1 #2 e Bybit #217 seguem abertas e trading live não está autorizado.


## J1/HIST — primeira captura privada real BTCUSDT 1h (28/10/2026 UTC) — bloqueio de primeira retenção superado

**Marco comprovado por duas saídas JSON de SSH fornecidas pelo titular:** código `46e394462b2e3141f675225c5bd1c682ec7384ec`, Binance Vision BTCUSDT USD-M 1h, agosto e setembro 2026, `archive_count=2`, `closed_candle_count=1464`, `data_stored_locally=true`, `network_requests=4`. Auditoria local read-only passou com os mesmos 1.464 candles, 2 sidecars e digest de manifesto `9f6a43b32573fe1aa5e80b2cf9d696d998e4d93850f9a02bcfd1397284af87a0` igual ao da captura. Intervalo [2026-08-01, 2026-10-01) UTC, sem lacunas pela validação mensal. Não foi executada verificação SSH direta pelas ferramentas do chat; são evidências produzidas pelo operador na VPS. O campo `data_stored=false` da **auditoria** significa que ela não gerou escrita adicional.

**Avanço:** primeira aquisição e retenção privada de histórico real de pesquisa **resolvida**; não voltar a alegar ausência completa de histórico local. **J1 #2 permanece aberta:** Top50 ponto-no-tempo, direitos de uso live, fonte canônica, qualidade multiativo/prospectiva e integração end-to-end não estão aceitos. `source_authenticated=false`, `canonical_ohlcv_approved=false`, `historical_top50_approved=false`, `financial_backtest_approved=false`, `live_trading_authorized=false`; nenhum trade, deploy ou gasto. Bybit rights #217 ainda aberta. Evidência operacional: issue #2.


## J1/PIT1 #306 — auditor multiativo e ranking temporal local (28/10/2026 UTC)

Base real conferida `main=f6520595d73927d458ae8662152d5e12b0e8eaa7`, zero PRs abertas. A primeira captura privada real BTCUSDT 1h de ago/set 2026 foi documentada por PR #305 e issue #2, com 1.464 candles, dois sidecars e digest de manifesto igual; não repetir download. Issue #306 / branch `work/issue-306-j1-vision-multiasset-pit`: módulo puro que ordena 2..50 séries alinhadas pela soma de 24h de volume quote USDT **até antes da decisão**, e CLI read-only que verifica manifestos locais de 1..50 ativos, com relatório agregado sem vazamento. Registro positivo de identidade/listagem retroativa, cobertura Top50 histórica, USD comparável, feed canônico e direitos live ainda não comprovados. Gates Linux/docs Windows Chrome no SHA, squash sem deploy, pós-merge e evidência; J1 #2, #32, #196, Bybit rights #217 continuam abertas.


## J1/EXIT #308 — reorientação para integração completa, sem bloqueio documental artificial

Product Owner exigiu J1 com fim definido e apontou que FAQ Bybit recomenda cache/banco local. Orientação oficial confirmada e aceita: desenvolver/validar coleta, armazenamento e replay privado, sem exigir prova de autorização de redistribuição comercial para testes offline. Gate de uso live e de acesso regional continua separado. Base `main=cb476487bb54a5e74f3c8b5cc2efbf36c51c8a5d`, zero PRs abertas ao iniciar. Issue #308 une instrumento paginado completo + ranking pelas últimas 24 velas fechadas com QUOTE USDT documentado + snapshots PIT imutáveis no SQLite privado já existente + teste E2E sintético com 720 velas por ativo/replay. A única captura REAL até este checkpoint continua BTCUSDT Vision 1464 velas 1h, permitida apenas pesquisa pessoal não produtiva. Bybit real 30d multiativo/Top50/aquisições horárias na VPS **ainda não comprovados**. Não encerrar #2 por testes sintéticos.


## J1 #310 — primeira prova VPS interrompida em validacao de instrumentos (29/10/2026 UTC)

Titular executou owner-only na VPS o codigo da PR #311, `main=b669dce6929326ee51d7e383c61db8cdbbd2bca8`. Saida sanitizada: `status=instrument_registry_or_pagination_rejected`, `partial_data_may_remain=true`, `marketwide_top50_verified=false`, `orders_sent=false`. A validacao falhou dentro do scan ANTES da chamada de criacao do banco, portanto nao ha evidencia de persistencia dessa tentativa; nao repetir a mesma coleta. Correcao de contrato/observabilidade em desenvolvimento: relogio por resposta, jitter de servidor limitado, exemplo oficial sem campos TradFi opcionais, categorias de erro sanitizadas e testes adversariais. Sem GET novo por esta revisao. J1 #2 ainda nao homologada.


## J1/EXIT #310 — resultado real após PRs #312/#313 e correção da filtragem (29/10/2026 UTC)

No SSH sob `cia-probe`, `main=b115a760859b50d1d2462b6bf90975815604829c`: 24 testes offline (5+4+15) aprovados. Resposta do coletor real: `instrument_scan_duplicate_instrument`, com `marketwide_top50_verified=false` e `orders_sent=false`. O scan não chega à criação do SQLite. O diagnóstico atual não distingue símbolo malformado de duplicado, pois a mensagem interna antiga agrupava ambas as causas. **Não presumir duplicata real da Bybit.**

Branch de correção de escopo contida na #310: permitir contratos lineares não elegíveis (futuros de vencimento, USDC, TradFi e bases desconhecidas) sem aplicar a eles o regex estrito dos perpétuos cripto, enquanto duplicata de perpétuo revisado ou identidade insegura continuam falhas. Adicionar testes regressivos, CI Linux/Windows/Chrome, revisão, merge e CI pós-merge antes da próxima captura. J1 #2 aberta; o histórico Bybit real de 30 dias, duas atualizações e universo Top50 continuam sem prova.


## J1/EXIT #310 — falha Bybit após longa execução e preservação do progresso privado (29/10/2026 UTC)

Em `main=ecc3b74707493a3114051aac155df81e57968945` o titular informou 30 testes locais aprovados (5 + 5 + 4 + 16). A captura foi iniciada por volta de 11h25 UTC, permaneceu em execução durante a espera horária e mais tarde retornou `status=provider_ret_code_failure_no_retry`, com `partial_data_may_remain=true`; o stdout não permite comprovar qual endpoint/retCode falhou, nem afirmar quantidade gravada. Como o script grava páginas e PIT antes de aguardar as horas, preservar banco privado e **auditar sem rede antes de qualquer repetição**.

Uma entrega coerente na issue #310 disponibiliza relatório estritamente read-only do SQLite (schema, digests, contiguidade, 720h, snapshots) e detecção controlada do erro de API. Próximo passo depois de CI/merge e um SSH de auditoria: decidir com evidência se deve aproveitar a base existente, corrigir parâmetro, respeitar limite ou refazer somente lacunas. Sem download ou ordem real nesta entrega. Universo real Top50 e homologação J1 #2 ainda não demonstrados.


## J1 #310 — amostra Bybit real 30d salva, próxima entrega é RETOMADA (29/10/2026 UTC)

**Evidência histórica concluída:** o titular rodou na VPS a auditoria read-only da PR #315 no SHA `008c810c800526bb302d9f2a5e8c30f612ae1787`. JSON confirmou 2 ativos elegíveis da amostra, 720 velas 1h fechadas por ativo, 1440 candles, 20 páginas, 1 snapshot PIT, SQLite íntegro, replay e cobertura completa. Decisão horária PIT inicial: 2026-10-29T11:00:00Z. Nenhuma atualização horária subsequente foi completada; Top50 mercado = false.

O próximo bloco de implementação J1 #310 cria `scripts.resume_private_bybit_j1` para preservar e estender essa mesma DB (sem re-fetch dos 30 dias), auditar antes da escrita, recuperar somente horas fechadas e acompanhar um novo snapshot atual e, se necessário, a próxima hora, até existirem pelo menos 2 atualizações PIT distintas verificadas além do snapshot inicial (sem exigir consecutividade artificial entre lacunas históricas). Se houver falha, guardar histórico/contadores e informar etapa/retCode sanitizado, sem repetir histórico. Critérios J1 #2: fonte real e retenção 30d **comprovados para 2 ativos**; Top50 completo e duas atualizações **ainda abertos**. Nenhum deploy, ordens reais ou custo.


## J1/EXIT #310 — primeira atualização PIT real e limite 10006 na segunda (29/10/2026 UTC)

Depois da PR #316 integrada, o titular executou na VPS o script de retomada; 5 testes OK e auditoria anterior de 1.440 candles/2 ativos/720h/PIT inicial íntegro. O processo reportou `phase=current_pit_verified`, `distinct_pit_updates_after_initial=1`, 26 GET, depois aguardou nova hora e falhou em `retCode=10006`, `last_request_stage=closed_kline_24h`, 42 GET no total, `existing_database_preserved=true`, `orders_sent=false`. Isso indica throttling da API, **não** comprova que a atualização adicional tenha passado por auditoria final. Não rebaixar os 30 dias já verificados nem reenviar o capturador original.

Correção #310: aplicar espaçamento conservador de 2s entre GETs reais, testes offline com relógio determinístico e fail-stop em 10006; publicar PR/CI verde e integrar somente com SHA exato. Na próxima execução owner-only, primeiro auditar SQLite privado e confirmar 2 PITs reais. Se houver apenas uma atualização após o inicial, retomar somente a hora fechada restante, sem recapturar 720h nem exigir duas viradas de hora adicionais. J1 #2 ainda aberta pelo Top50 de mercado e pela 2ª atualização pendente.


## J1/EXIT #310 — 1444 candles e 2 PITs confirmados, correção do relógio de lote em análise (29/10/2026 UTC)

Na VPS, a auditoria privada confirmou **2 ativos, 722 horas por ativo, 1.444 candles, 24 páginas, 2 snapshots PIT íntegros e 1 atualização real após o inicial**; todos os testes de retomada passaram. O ciclo seguinte falhou em `pit_review_page_capture_clock` após 18 GET de consulta de 24h, sem nova gravação confirmada, preservando o SQLite. A queda de velocidade dos GETs desde D159 expôs uma limitação do código: contratos recebidos no início do lote eram confrontados à hora final do ranking com idade rígida de 30s, enquanto o lote multiativo demora mais. A correção mantém a validade de cada página no seu instante de recebimento e permite lote limitado a 120s, sem afrouxar regras de fechamento UTC ou a idade padrão de 30s. PR e CI pendentes; não repetir o script anterior. J1 #2 continua aberta para a segunda atualização e Top50; nenhum sinal real ou deploy habilitado.


## J1 — vertical da amostra concluída; Top50 de mercado ainda pendente (29/10/2026 UTC)

**Aceite real na VPS:** `main=36b6b25895d133339ce3383af6b76b19f2d504aa`, 10 testes offline PASS, `private_j1_two_distinct_updates_verified_not_top50`, saída 0, auditoria independente posterior sem rede PASS. **2 ativos x 723 horas = 1.446 candles**, 26 páginas, 3 snapshots PIT imutáveis (inicial 11h + atualizações 13h/14h UTC), histórico inicial de 720h preservado, SQLite integrity/replay PASS, nenhuma ordem, `marketwide_top50_verified=false`. **Issue #310 fechada pelo escopo vertical de 2 ativos.** Não repetir coleta inicial, não apagar nem publicar dados privados.

**J1 #2 permanece ABERTA**: o cadastro revisado `expanded-13` contém somente 13 bases e o mercado Bybit linear inclui derivados não cripto. Issue #319 documenta o gate Top50 independente. Work unit inicial: censo owner-only do catálogo paginado Bybit sem OHLC ou escrita de banco, com números exatos de contratos revisados, candidatos ainda sem prova e excluídos TradFi/USDC/temporários; hash de fila de revisão, flags de Top50 e ranking 24h sempre falsos nesta etapa. Código offline não é evidência live. Sequência seguinte: ampliar registro com fontes verificadas, classificar/revisar novos ativos, homologar ranking sobre 24 candles fechados por candidato e 30d por selecionado, sem perder causalidade PIT. Nenhum trading live/testnet nem release.


## J1/TOP50 #319 — censo real aceito, priorização da revisão dos 348 candidatos (29/10/2026 UTC)

Censo real owner-only: 921 instrumentos em 5 páginas (5 GET), 13 cripto perpétuos revisados elegíveis, 348 candidatos ainda não revisados, 522 outras/exclusões e 38 bases conhecidas com contratos inelegíveis. `marketwide_top50_verified=false`. SQLite privado 1446 candles/2 ativos e 3 PIT reconfirmado intacto e auditado. O bloqueio de mercado inteiro já é medido; não precisa recapturar 30d.

Entrega #319 seguinte: classificar **prioridade de revisão de identidade** a partir de um ÚNICO ticker rolling 24h para os 361 contratos de aparência cripto da página completa, antes de pesquisar evidências independentes. O resultado não aprova Top50 nem combina ticker rolling com 24 candles UTC fechados. Por padrão relatório só agregado; identificadores públicos da fila no máximo 75 via flag de saída explícita, sem valores de mercado, dados privados ou commit desses identificadores. Testes offline e CI Linux/Windows/Chrome necessários antes do SSH proprietário; próxima fase será revisar candidatos selecionados e validar ranking verdadeiro por velas. J1 #2 aberta.


## J1 #319 — nova revisão observada de 52 bases, sem declarar Top50 (29/10/2026 UTC)

**Pesquisa externa:** a saída real do proprietário em `main=45e32d32...` aprovou 17 testes, consultou 921 contratos e 928 tickers (6 GET), classificou 361 candidatos com ticker positivo e 63 identificadores públicos prioritários ainda não revisados entre 75 primeiros; entre o Top50 *proxy rolling*, 38 identidades ainda não revisadas e 12 revisadas. O snapshot não valida ranking real por candles fechados nem autoriza trading. Histórico privado já confirmado: 2 ativos x723h = 1446 candles, 3 PIT e integridade/replay PASS.

**Entrega em curso:** nova versão opt-in `expanded-52` (13 identidades anteriores + 39 novas com referências CoinGecko e CoinMarketCap, além de documentação oficial para 9) com hash de integridade e observação de 29/10/2026. Preserva `expanded-13` para os PITs históricos e testes antigos. O marco **52 identidades no cadastro** não implica que as 52 tenham contratos elegíveis AGORA, histórico 30d nem que componham o Top50 por volume; auditar catálogo em tempo real com a versão explícita, depois coletar 24h de candles fechados para ranking global e histórico para selecionados. J1 #2/#319 seguem ABERTAS; nenhuma ordem/deploy.


## J1/TOP50 #319 — ranking de 24 candles FECHADOS para bases comprovadas (29/10/2026 UTC)

A revisão opt-in `expanded-52` (13 anteriores + 39 novas correspondências com duas fontes independentes) passou em CI Linux/Windows/Chrome e foi integrada pela PR #322 em `main=6232a85906e376f310917c785d9a26fe46acddd7`; **não toca SQLite proprietário**. Trabalho atual: API pública read-only para coletar 24 velas horárias fechadas por cada perpétuo USDT aprovado na revisão, validar TODOS os candles e turnover de cotação USDT, duplo censo paginado pré/pós sem deriva, gerar ranking exato de até 50 dos revisados, sem rede em testes e sem inserir os 348 candidatos ainda não revisados. Janela de captura até 360s em ritmo 2s/GET; sem trading, dados sensíveis ou deploy. Não confundir "50 de 52 bases revisadas" com "50 maiores do mercado"; J1 #2 e #319 ainda ABERTAS. A amostra já validada de 2 ativos/1446 candles/3 PIT permanece preservada na VPS.


## J1 #324 — diagnóstico de quota antes de repetir rank 52 (29/10/2026 UTC)

O proprietário confirmou ao vivo, após iniciar na janela correta, **52 contratos elegíveis** no cadastro `expanded-52` via 5 páginas de instrumentos Bybit. O segundo GET de kline 24h falhou com `retCode 10006` após 7 chamadas totais; o script parou sem retry. **Ranking de 24 candles fechados continua NÃO homologado**. SQLite owner-only continua íntegro: 1446 candles/2 ativos, 26 páginas, 3 PIT reais e replay PASS, nenhuma ordem. A documentação Bybit mostra limite API `10006` por segundo/UID com cabeçalhos de quota; ritmo já era conservador de 2s/GET, logo causa efetiva NÃO inferida de contagem isolada.

Work unit segura: instrumentar apenas headers numéricos sanitizados de rate-limit, sem novas requisições, e criar script proprietário de exatamente um GET fechado para diagnóstico controlado antes de qualquer nova coleta de 52. Novos testes offline de sucesso, 10006, 403, header inválido/ausente e opt-in negado. D165/docs versionadas e CI três plataformas. J1 #2/#319 continuam abertas: ainda faltam evidência de 24h FECHADAS global e 30d dos selecionados.


## J1 #326 — cache WS confirmado somente em fixtures (29/10/2026)

Implementação isolada: eventos sintéticos Bybit V5 `kline.60` confirmados, parser reuse de candle e contratos cripto revisados, journal SQLite exclusivo sem sobrescrever banco privado, auditoria RO que se abstém em lacunas e jamais afirma Top50 global. CLI `python3 -m scripts.probe_offline_bybit_closed_stream` e `--inject-disconnect` usam somente fixture temporária, sem GET/sockets/ordens. Testes `tests/test_j1_bybit_closed_stream_cache.py`; resultados locais iniciais 13/13 PASS em sandbox com stubs dos contratos (CI deve validar módulos reais). Isso não resolve quota anterior 10006 (um GET diagnóstico devolveu cabeçalhos ausentes), histórico de 30d de 50 elegíveis ou direitos live. #2/#319 continuam abertas; não coletar dado real por esta entrega.


## J1 #328 — observacao finita de kline publico (29/10/2026 UTC)

Adicionado observador read-only com `session_factory` injetavel, CLI `scripts.probe_bybit_public_ws_once` desativada sem opt-ins, no maximo 64 frames/90 segundos e limpeza de conexao, sem fallback REST. Testes de fake socket verificam ACK, close, open, duplicatas JSON, limites e erros; nenhuma conexao real nesta work unit. O binario opcional `websockets` nao faz parte de dependencies obrigatorias do projeto; sem biblioteca instalada, o diagnostico deve falhar de modo sanitizado. **J1 #2/#319 segue aberta**, 50 ativos e 30 dias de historico reais nao verificados. Sem ordens, deploy ou gasto.


## J1 WS2 #330 — integração multiativo de fixtures WS ao SQLite causal (29/10/2026)

Agregador de lote finito e injetado, sem rede, para ACK, eventos kline.60 abertos/fechados, replay idempotente e suspensão por gap. Reusa decoder de #328 e SQLite/auditoria de #326; testes de 24h/2 ativos, batch com ativo faltante, continuação explícita, replay, topic não revisado, ACK e JSON duplicado. A captura e o streaming reais não foram executados; quota 10006, cobertura de mercado e histórico 30d continuam pendentes. #2 e #319 permanecem abertos. Testes específicos locais inicialmente 7/7 PASS em ambiente com dependências simuladas; CI completa será a prova integrativa obrigatória.


## J1 WS3 #332 — ACK opcional, heartbeat e janela UTC (29/10/2026)

Correcao offline para aceitar `req_id` na ACK V5 documentada, heartbeat aplicativo a cada 20s apos ACK, pong estrito e sonda owner-only com janela de candle fechado, consentimento e timeout finito. Nao conecta em CI, nao guarda dados de mercado nem toca SQLite privado. Testes novos de compatibilidade, input malicioso e opt-in + regressao #328/#330. A execucao real owner-only, se desejada futuramente, depende de gate externo; #2/#319 permanecem abertas para 50 ativos e dados historicos reais.


## J1 WS4 #334 — primeiro frame real não reconhecido (29/10/2026)

A VPS executou com código `15187f34c66ab72a4b088e221ae9bc3dfc3dd910`, `websockets==15.0.1`, testes 10/10 e 7/7 PASS. A primeira sessão pública de `kline.60.BTCUSDT` recebeu 1 frame e retornou `ws_subscription_not_acknowledged`; a causa não é conhecida. Este patch adiciona diagnóstico por categorias sanitizadas, mantendo o tratamento fail-closed. Não houve candle confirmado nem escrita no banco privado; J1 #2/#319 abertas.


## J1 WS5 #336 — dado antecipado e ACK tardia (29/10/2026)

Última sonda owner-only na VPS sob SHA `4a6a28d5b6d528a437e6d6e9bb3239d9faa914fd`: 11/11 e 7/7 testes PASS, `frames_seen=1`, `status=ws_market_data_before_ack`, zero candles aprovados/ordens, dados locais preservados. Correção: kline pré-ACK estrita é apenas pendente e não dá sucesso até ACK válida; sem confirmação permanece recusada. #2/#319 seguem abertos.


## J1 WS6 #338 (30/10/2026 UTC)

Terceiro teste real na VPS: 16/16 + 7/7 testes offline PASS; ACK reconhecido, 19 frames, `ws_failed_closed`, 0 candles, 0 ordens/storage. Causa pendente; alteração offline elimina espera extra de 1000ms e reporta categoria de falha pós-ACK sem conteúdo do frame. J1 #2/#319 ainda ABERTAS por Top50 marketwide, 30d e direitos live.


## J1 WS7 #340 — envelope real ainda não validado (30/10/2026)

Owner executou um WS público real após 19+7 testes PASS, recebeu 21 frames com ACK positiva, mas `failure_category=kline_envelope`; nenhum candle validado. Implementação offline diferencia chaves raiz, tópico, tipo, rows e campos, reconhece variantes de controle público documentadas sem credenciais; nenhuma nova sonda real nesta entrega. J1 #319/#2 e direitos live permanecem abertos; não afirmar Top50 marketwide.


## J1 WS8 #342 — cardinalidade de linhas Kline (30/10/2026 UTC)

Sonda pública owner-only confirmou ACK e 19 frames, mas falhou `kline_rows` sem candle validado. A implementação offline deixa de exigir exatamente um registro em `data`, valida lotes limitados com rejeição total em caso de linha inválida e ignora lista vazia sem sucesso. A causa real ainda depende de uma única observação futura com SHA homologado. J1 #2/#319/#217 abertas.

## J1 WS8 — auditoria estrutural sem candles aprovados (30/10/2026)

A PR #343 incorpora uma sonda `--diagnostic-only` separada do observador fail-closed, sem persistência: em uma única conexão com orçamento máximo de 64 frames/90s mede somente histogramas de formato `data` (ausente, nulo, escalar, objeto, array 0/1/2..8/>8), itens objeto, `confirm` booleano, erros sanitizados e fase relativa à virada UTC. O modo diagnóstico não certifica nem armazena candles; continua após mensagem inválida apenas para investigar formas, mantendo ACK e o escopo do tópico, sem retransmissões ou novas conexões. O formato oficial V5 define `data` como array e o SDK pybit repassa Kline sem remodelar, porém NENHUMA ocorrência real de lote com 0 ou >1 linha foi ainda provada. Uma futura execução depende de CI/merge e opt-in e visa esclarecer o frame `kline_rows` de 19 mensagens. O pipeline offline e cache SQLite ainda exigem exatamente uma linha; não conectar o diagnóstico aos dois nem promover feed real antes de corrigir o contrato de ponta a ponta. J1 #2/#319 continuam abertas.


## J1 WS9 #344 — prova real de array múltiplo e integração offline (30/10/2026)

Owner VPS: 27/27 + 7/7 PASS, 64 frames, ACK=true, 61 eventos de mercado; `data_array_1=60`, `data_array_2_to_8=1`, um `confirm=true`, `first_validation_failure=kline_clock`, `strict_rejected_frames=1`, sem aprovar candles/ordens/storage. Corrigido ingresso do pipeline offline de array V5 e granularizadas causas de relógio no observador. Próxima evidência: CI e review no SHA da PR #344, sem sondagem repetitiva até necessário. J1 #319/#2 e direitos #217 abertas.


## J1/WS10 #346 — replay de controle e PIT histórico ainda pendente (30/10/2026)

Replay offline ignora somente pong Bybit já reconhecido no observador após ACK válido; pong não altera candle, DB ou ranking. Pong malformado, controle desconhecido ou pré-ACK aborta. Testes cobrem replay idempotente e fail-closed. **Não concluído:** auditoria 720h com múltiplos escopos point-in-time validados. O contrato atual usa um snapshot e limite de sete dias: nenhum sucesso de 30d, 50 ativos de mercado, licença de dados ou live pode ser afirmado nesta entrega. Sem rede, alteração de schema, ordens ou dados privados da VPS.


## J1 #346 — auditoria histórica PIT de 720h sintéticas (30/10/2026)

A API opcional `SQLiteOfflineClosedStreamJournal.audit(..., historical_scopes=(...))` preserva a auditoria legada de 24h. Exige no máximo 64 épocas ordenadas, com mesma identidade dos contratos, registro SHA e limites de relógio, associando cada evento à época mais recente conhecida no fechamento; rejeita retrodatação, deriva, escopo omitido, corrupção e gaps. Calcula cobertura 720h (720 velas fechadas por símbolo), slots ausentes, épocas e digest somente para janela integral de todos os símbolos. Mesmo em fixtures completas, `marketwide_top50_verified=false`, direitos e autenticidade false; sem rede, dados da VPS, migração ou ordens. Testes adversariais sintéticos novos em `tests/test_j1_bybit_ws_pit720.py`. Esta implementação não comprova que o mesmo registro de identidade permanece legalmente/temporalmente válido por 30 dias, nem reconstrói os 50 ativos reais; J1 #2/#319/#217 continuam abertas. Aceite somente com CI GitHub no SHA final e merge seguro.


## J1/EXIT #349 — corrigir o gargalo de páginas 72h (30/10/2026)

A API oficial V5 Kline admite até 1.000 candles 1h por chamada. A implementação adiciona modo opt-in `--history-page-hours 720` para uma janela exata de 30 dias (720 candles) sem mudar os defaults de 72h, e revisão `--registry-variant expanded-52`, sem presumir 50 membros efetivamente elegíveis. A camada local valida uma página inteira de 720, UTC, ordem, Decimal e limite de bytes; 73..719 e >720 são recusados no manifesto de pesquisa. Para dois ativos, a etapa histórica cai teoricamente de 40 GETs (10 metadados + 10 klines por ativo) para quatro (1+1 por ativo); três GETs extras de seleção/censo no exemplo sintético. Isto não garante ausência de 10006/HTTP restrito nem autentica origem, unidade de ticker ou direitos. Dados existentes da VPS (1446 velas/2 ativos/3 PIT) permanecem intactos. Ranking de 52 bases revisadas não prova Top50 do mercado enquanto o censo contiver candidatos sem revisão. Nenhuma ordem, migração, rede real no CI ou autorização live.


## J1 #351 — censo Bybit com limite oficial de 1000 por página (30/10/2026)

O cliente GET de instrumentos reduz o limite artificial de 200 para 1000 linhas por página, mantendo validação de cursor, limite de bytes, sem redirect, origem fixa e sem retries. Um censo de 921 linhas pode, em tese, caber numa única página, mas tamanho de resposta, disponibilidade da fonte e 10006 não estão comprovados por nova execução. Chamada por símbolo conserva limit=1. Teste adversarial rejeita limit=200/1001 injetados. A triagem de identidades sem atribuição indevida de Top50 permanece como etapa separada na issue #351; nada autoriza live ou prova ranking 24h fechado. Sem rede real ou alteração em dados privados.


## J1 #351 — triagem de identidades não revisadas por proxy móvel, offline (30/10/2026)

`bybit_top50_identity_priority.py` usa somente catálogo paginado completo já validado e um ticker público fornecido pelo chamador. Para cada candidato plausível sem identidade revisada exige ticker único, fresco, Decimal e valor/volume coerentes; qualquer falta/corrupção aborta a fila inteira. Ordena somente para priorizar revisão independente de identidade, inclusive símbolos potencialmente TradFi: **não concede classificação crypto**, não autentica fonte, unidade do ticker ou ranking de 24 horas FECHADAS. Relatório padrão contém contagens, digest e flags negativas; listagem de símbolos públicos somente com `include_public_symbols=True`. `marketwide_top50_verified=false` incondicional. Sem rede, SQLite, credencial, deploy ou ordens; #319/#2/#217 continuam bloqueadas até observação real autorizada e validação.


## D177 — desbloqueio de pesquisa independente do gate de trading real (30/10/2026)

**Decisão fechada:** Bybit continua candidata preferencial para feed prospectivo, usando WS/REST/cache local, sem considerar `10006` resolvido. Binance Vision previamente retido pelo titular fica restrito à pesquisa pessoal offline não produtiva, sem alimentação de sinais/live. J1 #319/#217 permanecem gates operacionais de dados/identidade/direitos. A execução automática permanece objetivo final (D77), mas nenhuma ordem live, testnet, deploy ou credencial foi ativada. J2/J3 podem pesquisar offline sem esperar homologação integral do Top50 de produção. Não exigir novo `prossiga` para tarefas seguras em sessão.

A biblioteca `vision_dynamic_replay.py` reutiliza candles já auditados por `offline_vision_month` e `offline_vision_series`, e gera replay determinístico de decisões com volume de cotação USDT em 24h FECHADAS para uma amostra de até 50 contratos, por prefixos, em até 720 decisões. Flags de Top50 de mercado, origem autenticada, direitos live, backtest financeiro aprovado e ordens continuam negativas. Testes de alinhamento, relógio, duplicata, determinismo, não-lookahead e recursos. **Não é autenticação de fonte ou universo histórico global.**


## #354 — CLI privada integrada à decisão D177 (30/10/2026)

`python -m scripts.replay_private_vision_dynamic --manifest /caminho/privado/asset1/manifest.json --manifest /caminho/privado/asset2/manifest.json --first-decision-ms UTC_MS --last-decision-ms UTC_MS --allow-personal-nonproduction-research` audita arquivos ZIP existentes, sidecars e manifests privados em leitura, sem novos downloads, e retorna somente números agregados e SHA do replay 24h de volume cotado na amostra. Sem a autorização de pesquisa pessoal não produtiva, falha antes de ler dados. Não habilita negociação, Top50 de mercado, sinais, feed canônico ou backtest financeiro. Não executar contra arquivos reais sem revisão local do titular; arquivos permanecem privados. Nenhum deploy está incluído.


## J2/J3 #357 — avaliação causal mensal de hipótese líquida, somente pesquisa (30/10/2026)

`vision_costed_oos.costed_vision_monthly_oos` reutiliza séries de meses Vision previamente inspecionadas, alinha múltiplos ativos e ranqueia pela soma das últimas 24h de volume cotado fechado. Regra fixa de tendência/contratendência é selecionada exclusivamente no histórico anterior, com alternativa de permanecer em caixa se não houver valor líquido hipotético positivo; o mês atual nunca treina sua própria escolha. Entrada hipotética no open do candle seguinte, saída no close, taxa/slippage hipotética agregada em bps por lado, benchmark buy-long e drawdown proxy. Não incorpora mark, funding, intrabar, slippage reais, liquidação, alavancagem, fills executáveis, custos de portfólio nem valida edge; `financial_backtest_approved=false` sempre. Não encaminhar a sinal real, ordens ou conta. Amostra restrita ao dataset local; sem autenticação de fonte, direitos de live ou Top50 de mercado. Sem downloads, storage, deploy ou novos gastos.


## J3/STRESS1 #359 — limites intrabar OHLC condicionais (30/10/2026)

`vision_intrabar_stress.py` introduz estresse matemático estritamente offline para uma barra Vision, com margem sintética, alavancagem fixa por avaliação, stop, target, limiar de liquidação proxy por equity e manutenção hipotética, funding assinado e custos Decimal por lado. Como OHLC não informa a ordem dos eventos, retorna **dois limites condicionais**: downside (liquidação/stop antes de target) e upside (target antes de stop), marcando ambiguidade e toques simultâneos. A marcação e a fórmula de liquidação reais da corretora NÃO são inferidas. Não há integração com execução nem estimativa de perda garantida. `financial_backtest_approved=false`, nenhuma ordem, rede, licença, dado canônico ou homologação Top50. Testes de 50x/1x, long/short, ambiguidade, taxa, funding e corrupção. A integração com seleção OOS mensal e CLI é **pendência da issue #359**, não alegar entrega completa.


## #359 — ligação de stress à seleção mensal OOS sem refitting (30/10/2026)

`vision_stress_oos.audit_costed_vision_intrabar_oos` chama o avaliador causal mensal de J2/J3 para congelar a regra exclusivamente treinada no mês anterior e, no mês OOS, estressa o candle selecionado com os limites condicionais OHLC adverso/favorável da etapa STRESS1. Retorna contagens agregadas de exposições, toques ambiguamente ordenados, condições de liquidação hipotética e resultados condicionais quote do modelo (sem garantia de perda executável). Não refaz ranking com futuro, não otimiza parâmetros no mês de teste, não publica OHLC/ativos ou preços. Não é backtest financeiramente homologado, execução, feed live, autenticação Binance nem validação Top50. A CLI privada ainda não publica a nova modalidade; issue #359 continua aberta até integração final e gates.


## #359 — acesso explícito ao stress OOS no auditor privado (30/10/2026)

A CLI `scripts.replay_private_vision_dynamic` recebeu opt-in `--audit-intrabar-stress` com os 9 parâmetros completos `--stress-margin-quote`, `--stress-leverage`, `--stress-stop-fraction`, `--stress-target-fraction`, `--stress-maintenance-bps`, `--stress-fee-bps`, `--stress-slippage-bps`, `--stress-funding-bps` e `--stress-selection-cost-bps`; recusa parâmetros parciais ou sem opt-in, só lê os manifest/ZIPs privados já existentes, valida antes de calcular, e emite unicamente agregados anonimizados de stress e digest. Alavancagem e margem são hipóteses, não aprovação da corretora; não autentica dados, não prova trajetória intrabar/mark/funding ou liquidação real. Nenhuma ordem, credencial, escrita, rede, deploy ou lucro validado. A CI é requisito antes de merge.


## J3/ROBUST1 #367 — pacote de robustez proposto (30/10/2026)

Após #363/PRs #364–#366 integradas, a nova issue #367 implementa comparação de quatro cenários condicionais em dados históricos Vision já privados, com choques explícitos de taxa, slippage, manutenção e funding, sem alteração do calendário OOS ou suposta liquidação real. Arquivos `crypto_intelligence_agent/vision_risk_sensitivity.py`, `tests/test_vision_risk_sensitivity.py`, CLI e docs/J3_ROBUST1.md em branch de revisão `work/j3-robust1-sensitivity`; **não afirmar aceite até teste/CI e merge**. Nenhuma conta, API, ordem, VPS, credencial, deploy ou gasto. J1 #2/#217/#319 e J3 #4 abertas.


## 30/10/2026 — J3/PRE17 #369 em implementação

Após #367/#368 integradas, pesquisa sintética continua sem dados reais de mark/funding. Issue #369 e branch `work/j3-pre17-risk-snapshot-pit` adicionam risco por tiers e snapshots PIT opcionais no replay mark/trade, com regras de dedução contínua, controle de staleness e intervalo de ticks. Regressões offline e documentação junto ao código. **Não afirmar merge, CI ou homologação da #369 até evidência real**. J1 #2/#217/#319, J2 #3 e J3 #4 abertas; orçamento R$0 e ordens live desabilitadas.


## 30/10/2026 — J3/PRE18 #371 em desenvolvimento

Após PR #370/issue #369 integradas em `cccca495b823c9fa4f7f465ca4ae5eb68e7c59d0`, a issue #371 acrescenta cobertura completa de horários de funding fictício no replay mark/trade. Arquivos `synthetic_funding_calendar.py`, extensão opt-in de `synthetic_mark_replay.py`, testes e `docs/J3_PRE18_FUNDING_CALENDAR.md`; nada habilita conta, Bybit real, ordens ou release. CI/merge desta issue dependem de resultados e SHA próprio, sem antecipar sucesso. J1 #2/#217/#319, J2 #3 e J3 #4 abertas.


## 30/10/2026 — J3/PRE19 #373 em implementação

Após PRs #370/#372 integradas em `cccca495b823c9fa4f7f465ca4ae5eb68e7c59d0` e `a69be5202ff2afe5f16202d4e2767e57458ec30a`, issue #373 e branch `work/j3-pre19-portfolio-replay` implementam agregador puro de carteira de pesquisa multi-posição, no mesmo UTC e quote `SYNTHETIC_USDT`, reusando marcação/custo/funding. Reporta exposição e drawdown prefixo e deixa PnL desconhecido após liquidação. Arquivos e critérios em `docs/J3_PRE19_PORTFOLIO_REPLAY.md`. **Integração depende de CI e merge ainda não alegados**. J1 #2/#217/#319, J2 #3 e J3 #4 permanecem abertas; R$0 adicional, sem ordens nem deploy.


## 30/10/2026 — J3/PRE20 #375 (não homologada)

Depois da PR #374/issue #373 integrada em `19d74c71a04d1bbef7015024bd0861ab9a34ec87`, iniciou-se work unit #375 na branch `work/j3-pre20-portfolio-risk-limits`. O bloco incorpora auditoria de risco global por margem, gross/net exposure, concentração, nocional individual por mark, drawdown causal e alavancagem por posição, com trava de incerteza pós-liquidação. Arquivos `synthetic_portfolio_risk_limits.py`, `test_synthetic_portfolio_risk_limits.py`, `docs/J3_PRE20_PORTFOLIO_RISK_LIMITS.md` e D182. Não afirmar CI/merge desta work unit antes de verificá-los. J1 #2/#217/#319, J2 #3, J3 #4 abertas; execução real desabilitada.


## J1/EXIT2 #377 — corrigindo o gargalo efetivo de 50 ativos (30/10/2026)

A captura anterior não conectava `expanded-52` ao validador de manifesto, e usava seleção PIT com orçamento de 120s, insuficiente a 52 consultas 24h sob intervalo de 2s por GET. A issue #377 cria helper compartilhado de ranking fechado com orçamento 6min e seleção tipada para 50, libera manifesto expandido com validação estrita e adiciona teste ponta a ponta de 36.000 velas com armazenamento 0600. Por exigência de uso pessoal, não apresentar direito de redistribuição comercial como bloqueio técnico do cache privado. Até CI/merge, a implementação está na branch `work/j1-exit2-top50-private-capture`, **não** declarada pronta. Banco de 2 ativos e PIT originais permanecem intocados; #2/#319 ainda exigem observação real owner-only para aceite de mercado.


## J1/EXIT3 #379 — conclusão de ciclo único 50×722, ainda requer owner-run

A PR #378 integrada corrigiu time budget de 6min e manifesto `expanded-52`, com 1.618 testes Linux PASS. O novo bloco #379 habilita `--two-hourly-updates` no modo 50×720h, mantendo cliente com cap 500 GET e falhas seguras; teste completo fake calcula 36.100 velas em novo SQLite privado e 3 PIT consecutivos. Não transformar o resultado fake em prova de Top50 real. O único owner-run na VPS deve ser realizado após CI/merge, em DB novo sob diretório 0700, sem tocar banco existente de 2 ativos ou habilitar ordens.


## J1/EXIT4 #381 — Top50 dinâmico em desenvolvimento, 30/10/2026

Após PRs #378 e #380 integradas em `main=667045a3d18e703f382e28a87fc45c0153e96ea2`, corrigir causa real adicional: seleção Top50 entre três PIT não deve exigir mesma composição, pois entrada/saída de um ativo é normal. Branch `work/j1-exit4-dynamic-top50-pit`: captura incremental por cursor, backfill somente de novo integrante, replay de retornante, auditor por PIT para até 52 históricos, testes adversariais e D185. Sem CI/merge desta issue até verificação; nenhum download real, acesso VPS, ordem ou gasto. #2/#319 continuam abertas até o owner-run comprovado.


## 30/10/2026 — J4/RUNNER1 #383 em implementação, independente da VPS

J1 EXIT4 (#381/PR #382) integrada em `main=c58c6845d5f1be97cf27ec1ffb50a54d4a9704ca`; execução owner-only de captura na VPS adiada pelo proprietário e registrada em #2/#319, sem solicitar ações repetidas. Jornada ativa J4 #5: issue #383 e branch `work/j4-runner1-offline-trailing` implementam observação de trailing para runner PAPER após fills confirmados, com estados e teste sem rede. `docs/J4_RUNNER1_PAPER_TRAILING.md` e D186 definem limitações: sem persistência de stop, fill, ordens ou lucro real. Testes, CI, merge e fechamento somente após verificação real do head SHA; R$0 extra.


## 30/10/2026 — J5/PRE14 #385, sem VPS

J4/RUNNER1 #383/PR #384 integrada na `main` em `08cae66c40779562fa15a07e5be77fce157d5c51` após CI docs/Linux, Windows e Chrome/PAPER verdes. Na J5 #6, issue #385 e branch `work/j5-pre14-paper-runner-state-mobile` mostram no cartão mobile e tabela o estado do runner obtido somente do ledger PAPER: aguardando parcial, reconciliar ordem incerta, sem runner ou runner confirmado sem stop verificado. Sem consultar marcação do mercado nem presumir trailing ativo. CI e merge desta nova work unit ainda sujeitos a confirmação. J1 #2/#319 continuam com execução owner-run na VPS explicitamente adiada; nenhuma nova solicitação ao proprietário.


## 30/10/2026 — J4/RUNNER2 #387, persistência offline sem VPS

Base confirmada `main=1f15409e09c9f3072cf4c526dd57edf90b085e80`, PRs abertas zero no início. Issue #387 e branch `work/j4-runner2-durable-paper-trailing` introduzem SQLite separado de eventos mark sintéticos, leitura RO do diário de posições e replay monotônico via RUNNER1. Os cenários de recuperação, corrupção, idempotência e staleness foram codificados em testes; CI/merge devem ser verificados. A coleta J1 #2/#319 segue pendente de ação externa quando possível, sem solicitar VPS agora. Nenhuma API financeira, ordem, credencial ou custo.


## J5/PRE15 #389 — recuperação de trailing PAPER no painel (30/10/2026)
Base confirmada: J4/RUNNER2 #387/PR #388 integrada em main SHA `125c5c8a30d20f6f3c479ca64bea654bd48a4051`, J5/PRE14 #385/PR #386 já integrada. Branch `work/j5-pre15-durable-runner-mobile` implementa visualização local RO opt-in dos estados hipotéticos recuperados RUNNER2, com policy completa, posição explicitamente selecionada, teste de drift e JSON/HTML aditivos. Nova issue #389, testes `test_paper_runner_recovery_mobile.py`. PR, CI e merge desta unidade exigem confirmação independente; nenhuma VPS, dados novos J1, stop nativo, ordem, lucro ou deploy. J1 #2/#319 permanecem pendentes de owner-run adiado por decisão do PO.


## J4/RUNNER3 #391 — fechamento da alocação runner PAPER, 30/10/2026
Base auditada: `main=2ec2025b2a2f0673024ee79ea0c0fec1b2048ad7`, PR #390 integrada e #389 fechada; nenhuma PR aberta ao iniciar. Issue #391, branch `work/j4-runner3-residual-paper-reduce-only`. Implementado saldo residual como passo zero de EXIT REDUCE_ONLY somente PAPER em AUTO4 com conservação e rollback, e preview puro após gatilho RUNNER2. `tests/test_paper_runner_close.py` inclui LONG/SHORT, parcial/UNKNOWN/cancel/overfill, restart e no-network. O código ainda exige PR, revisão e CI SHA final; não presumir merge ou homologação. J1 #2/#319 continua pendente do owner-run VPS adiado. Sem stop nativo, ordens, deploy, nova despesa ou promessa de lucro.


## J5/PRE16 #393 — visualização do fechamento runner PAPER, 30/10/2026
Confirmado `main=60f9ec4aaf41a05495b25c56085f6ac1d096054c` após squash merge de J4 RUNNER3 #391/PR #392, issue #391 encerrada com CI 41137713503 Linux/Windows e 41137713508 Chrome/PAPER SUCCESS, review #5719329610. Issue #393 e branch `work/j5-pre16-runner-exit-mobile-status` distinguem runner PAPER pendente, parcial, cancelado e encerrado na UI, mantendo status e flag de stop real falsos. Testes SQLite e docs D191 adicionados; PR/CI/merge desta etapa ainda precisam ser verificados. J1/Top50 VPS owner-run continua adiado pelo PO, sem credenciais, trades ou deploy.


## J6/PRE4 #395 — gatilho runner para reserva PAPER, 30/10/2026
Base verificada `main=cb10525a0c32a0fd89ee9b49153814ac4a8db514` após PR #394 integrada, CI 41138259201 Linux/docs/Windows e 41138259179 Chrome/PAPER SUCCESS, revisão #5719361203; issue #393 encerrada. J6 PRE4 issue #395 e branch `work/j6-pre4-durable-paper-runner-close` introduzem função explícita `step_durable_paper_runner_close` para reservar a saída residual PAPER após gatilho RUNNER2, sem FILL presumido e com recuperação via ledger AUTO4. Testes de restart/UNKNOWN/cancel/partial/corrupção/concorrência e D192; CI/PR/merge da nova unidade ainda não afirmados. J1 #2/#319 aguarda owner-run privado na VPS adiado pelo PO, sem trading real ou gasto.


## J6/PRE5 #397 — ciclo completo demonstrável sem rede, 30/10/2026
Confirmado J6/PRE4 #395/PR #396 integrada em `main=870bdfc2969af6a2c6fb87e91e4bb23f3a87e6ec`, CI 41138778211 Linux/docs/Windows e 41138778276 Chrome/PAPER SUCCESS, revisão #5719397733; #395 encerrada. Issue #397 e branch `work/j6-pre5-runner-e2e-demo` acrescentam `scripts.demo_paper_runner_close_flow`: 100→50→20→6, trailing fictício, reserva REDUCE_ONLY sem FILL, restart e preenchimento explicitamente sintético final. Teste de determinismo, no-network e limpeza temporária; D193 e documentação. PR/CI/merge desta etapa ainda não verificados. J1/VPS owner-run adiado, nenhum trade, stop nativo ou gasto.

## J6/PRE6 #399 — auditoria local de incidentes em preparação, 30/10/2026
Branch `codex/issue-399-j6-pre6-paper-incident-audit` parte de `main=7819e05c8d1913b15c220b0f0bd5531e5e0c87c7`. Implementa observador read-only de um AUTO4 selecionado e RUNNER2 explicitamente opt-in, com saída JSON sanitizada e estados estáveis para runner não protegido, trailing hipotético, reserva/UNKNOWN/parcial/cancelamento, encerramento PAPER, checkpoint RUNNER2 superado e journal inválido. A tela mobile PAPER existente ganhou cartão de incidente por seleção explícita, sem controles de trade. Ainda requer PR e CI do novo head; nenhum dado de corretora, VPS, credencial, ordem, stop nativo, testnet/live, deploy ou gasto foi usado.

## J6/PRE7 #401 — matriz offline em desenvolvimento, 30/10/2026

Branch `codex/issue-401-j6-pre7-paper-readiness-matrix` parte de `main=0959c86fc611a1a313514fde1ab728925ac333ea`. Acrescenta laboratório temporário com 11 cenários após revisão de integração e relatório `paper_incident_matrix_v1`, incluindo saúde/restart, UNKNOWN, parcial/cancelamento, concorrência, incompatibilidade e corrupção. D195 e contrato PRE7 registram que os resultados são evidência offline, não homologação financeira. PR/CI ainda pendentes.


## J6/PRE8 #403 — auditoria de uma carteira PAPER selecionada, 31/10/2026

Base verificada `main=6ab7b3558b44bf03bc6fbede62f6060f76d1a250`, PRs abertas=0 no início. PRE7 #401/PR #402 integrada com 11 cenários, SHA revisado `d400cb752cff605f5c71123c25241648b95298e9`, CI Linux/docs+Windows `41173066212` e Chrome/PAPER `41173066163` SUCCESS. Issue #403 e branch `work/j6-pre8-batched-paper-incident-readonly` implementam classificador puro PRE6 compartilhado e auditor de 1–128 posições PAPER no mesmo snapshot AUTO4, cutoff/idade, blocos de integridade sem publicação parcial e JSON/CLI sanitizados. Testes e decisão D196; PR/CI/merge dessa etapa permanecem pendentes até validação do SHA. J1 owner-run VPS adiado; sem exchange, ordens, deploy, migrations ou gasto.
