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
