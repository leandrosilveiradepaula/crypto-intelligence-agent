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

## J3/PRE21 #407 — OOS mensal com estresse intrabar condicionado

A branch `codex/issue-407-j3-pre21-monthly-intrabar-oos` parte de `main=51df143e0a689b59f7874132d1fe1a328e787465`. Ela centraliza seleção/direção causal por barra em `causal_oos_bar_choice` para que o proxy legado e o auditor intrabar usem a mesma janela de 24h fechadas, e amplia os agregados do fold com abstenções e toques stop/alvo. `docs/J3_PRE21_MONTHLY_INTRABAR_OOS.md` e D198 delimitam os envelopes hipotéticos. A PR #408 teve o primeiro SHA `bb40654b71ba98231b9c47ff56d54422a7317263` aprovado em docs/Linux+Windows `41204360350` e Chrome/PAPER `41204360372`; o SHA documental posterior requer a mesma validação antes de revisão. Nenhum dado externo, VPS, credencial, ordem, testnet/live, deploy ou gasto foi usado.


## J6/PRE8 #403 — auditoria de uma carteira PAPER selecionada, 31/10/2026

Base verificada `main=6ab7b3558b44bf03bc6fbede62f6060f76d1a250`, PRs abertas=0 no início. PRE7 #401/PR #402 integrada com 11 cenários, SHA revisado `d400cb752cff605f5c71123c25241648b95298e9`, CI Linux/docs+Windows `41173066212` e Chrome/PAPER `41173066163` SUCCESS. Issue #403 e branch `work/j6-pre8-batched-paper-incident-readonly` implementam classificador puro PRE6 compartilhado e auditor de 1–128 posições PAPER no mesmo snapshot AUTO4, cutoff/idade, blocos de integridade sem publicação parcial e JSON/CLI sanitizados. Testes e decisão D196; PR/CI/merge dessa etapa permanecem pendentes até validação do SHA. J1 owner-run VPS adiado; sem exchange, ordens, deploy, migrations ou gasto.


## J6/PRE9 #405 — mesma intenção J2/RiskGate no ledger AUTO4, 31/10/2026

Base verificada `main=46975938ec727489647edcc8173bf98f2e7657a8`, após PR #404/J6 PRE8 integrada com CI 41174110832 Linux/docs+Windows e 41174110831 Chrome/PAPER SUCCESS, review 5721532250. Issue #405 e branch `work/j6-pre9-causal-open-to-runner-paper` implementam demonstração de cadeia J2→AUTO2→AUTO4→RUNNER2→PRE4→PRE8 com intenção OPEN recuperada do cursor real e FILL de fixture isolado, parciais/trailing/runner e relatório sanitizado. Testes e D197 adicionados; PR/CI/merge ainda não presumidos. J1 VPS owner-run adiado, nenhuma ordem/endpoint/gasto.



## J3/PRE22 #409 — grade de robustez de custos/alavancagem OOS, 31/10/2026

Base verificada `main=c852c4002b84b74be24b1dd986154c242971d09e`, zero PRs abertas ao iniciar. PRE21 #407/PR #408 integrada com seleção causal 24h fechado, envelope OHLC condicional, D198, CI final Linux/Windows/Chrome SUCCESS. PRE22 #409 na branch `work/j3-pre22-oos-sensitivity-grid` adiciona comparador read-only de 2–6 cenários `VisionStressAssumptions` sobre mesmos folds e contagens, com sumário de fragilidade sob custos, alavancagem e liquidação proxy, testes numéricos/fail-closed/privacidade e D199. PR, CI e merge permanecem sujeitos a verificação. Última evidência de J1 VPS: worker agendado para 31/10 15:00:15 UTC, não comprovou captura nem status final. Sem reiniciar/coletar, credencial, ordem, deploy ou novos gastos.


## J3/PRE23 #411 — CLI de pesquisa privada OOS 1x vs Nx (31/10/2026)

Base `main=8dccd85d7d33836577a82a681b32a0f77f6b60e6`, nenhuma PR aberta antes da branch `work/j3-pre23-private-oos-leverage-cli`. PRE22 #409/PR #410 integrou comparador de 2–6 hipóteses com CI verde, review `5723543953`, D199. PRE23 integra esse mesmo comparador à CLI privada Vision já auditada, sem recarregar arquivos, com opt-in explícito, comparação 1x/Nx e todos os termos declarados; testes POSIX com manifests fictícios, retorno sanitizado e D200. Gate PR/CI SHA final pendente até comprovação. J1 #319 worker VPS teve apenas agendamento confirmado para 15:00:15 UTC, status final desconhecido; nenhum novo processo/SSH/retry. Sem live/testnet, ordem, deploy, gasto ou dados reais usados nesta engenharia.


## J3/PRE24 #413 — integridade de decisões OOS, 31/10/2026

Partindo de main 97a990c2f62fa6888e80c1c509df1ab453da7d8d (PRE23/PR #412 integrada, zero PRs abertas), PRE24 corrige a insuficiência de comparações por contagem: fingerprints de decisões OOS por fold e global permitem detectar seleção diferente com exposição igual; PRE22 falha fechado quando houver discrepância. Relatório aditivo inclui drawdown e perda máxima por margem, preservando digest financeiro PRE21. Branch work/j3-pre24-oos-decision-fingerprint-risk; issue #413. Testes/CI/revisão/merge dependem de evidência de execução, sem alegação antecipada. J1 #2/#319: worker agendado às 15:00:15 UTC, conclusão não verificável pelo GitHub, sem reiniciar. Sem dados reais, VPS, ordens, credenciais, deploy ou custo.


## J3/PRE25 #415 — benchmark LONG pareado por exposição, 31/10/2026

Base `main=fea791dfd6dfb565a5254e4bb6dbb137cc2762ca` com PRE24 #413/PR #414 integradas, todos gates pre/postmerge verdes. PRE25 adiciona LONG contrafactual nos **mesmos** ativos/barras de exposição da estratégia, reutilizando envelope LONG já calculado, sem substituir LONG integral, sem retreinar regra OOS, alterar fingerprints PRE24 ou digest financeiro legado PRE21. O relatório por fold/agregado e em PRE22/PRE23 inclui exposições, ambiguidade, toques stop/alvo/liquidação proxy, riscos condicionais e deltas adverso/favorável; não confundir deltas com alpha, fills, retorno composto ou vantagem comprovada. Testes de tendências sintéticas, LONG, reversão SHORT, abstenção, custo 1x/50x, privacidade. Issue #415 e branch `work/j3-pre25-exposure-matched-oos-benchmark`. CI/revisão/merge sujeitos a comprovação; J1 #319 worker VPS continua sem resultado verificado, sem coleta ou acesso remoto novo. Sem ordens, contas, testnet/live, deploy ou gasto adicional.


## J6/PRE10 #417 — matriz integrada de interrupção causal PAPER (31/10/2026)

Base confirmada `main=87f6221c82c4f38a6307a2daaf023ed26aeb21e8`, zero PRs abertas antes da tarefa. A demo existente `scripts.demo_full_offline_paper_lifecycle` agora usa auditoria AUTO8 e PRE8, operador AUTO6 e ramo AUTO4 descartável com FILL divergente para afirmar bloqueio nas fronteiras J2/AUTO2/AUTO4/REDUCE_ONLY/runner sem alterar caminho de sucesso. Sete checkpoints sanitizados `interruption_checks`; testes de determinismo, contadores, travas de native stop/live e auditor adulterado. Issue #417; branch `work/j6-pre10-causal-interruption-matrix`. CI, PR, revisão e merge somente após evidências no SHA exato, sem promessas antecipadas. J1 #319: worker VPS agendado no último registro mas sem resultado privado verificado, não reiniciar/coletar. Sem conta, rede, ordens, deploy ou gastos.


## J6/PRE11 #419 — cutoff causal e recuperação em PAPER, 31/10/2026

Base verificada `main=97840c8f4245ed7692b372d06ed68b611c50cbab` (J6 PRE10/PR #418 integrada, CI pós-merge verde, zero PRs abertas). PRE11 implementa fail-closed em snapshot futuro AUTO2 cursor/pause no status de operador e recuperação; runner-close PENDING/FILLED com cutoff antigo; classificação de incidente RUNNER2 com AUTO4 posterior ao cutoff. Testes adversariais de instante anterior/igual, recusa de leitura retrocausal e imutabilidade do diário. Issue #419 branch `work/j6-pre11-causal-recovery-cutoff`. CI, revisão e merge dependem de evidência verificável. J1 #319 permanece sem resultado auditado da tentativa VPS; sem novo GET, restart, trade, credenciais, release, deploy ou gasto.


## J6/PRE12 #421 — sanidade temporal completa de eventos AUTO2, 31/10/2026

Base real `main=386e364eeebfb70583b7f38bedac87444a71829d` com PRE11 #419/PR #420 integrada, testes Linux/Windows/Chrome verdes e zero PRs abertas no início. PRE12 fecha lacuna em `paper_operator_status`: cursor e pausa estavam limitados pelo cutoff, mas o scan de OPEN/REDUCE_ONLY ainda aceitava snapshots de FILL/eventos futuros. O scan agora valida `created_at_ms` e `snapshot.as_of_ms` de **todas** as intenções AUTO2 sob a mesma transação read-only, antes de calcular pendência. O modo sem cutoff permanece compatível. Recuperação anterior usa o novo bloqueio e a demonstração PAPER acrescenta dois checkpoints de impossibilidade retrocausal (abertura e runner). Testes com SQLite, abstinência de rede, sem writes e saídas sanitizadas. Issue #421 e branch `work/j6-pre12-auto2-event-causal-cutoff`. CI e merge ainda exigem evidências; nenhuma VPS, coleta J1, conta, ordem, testnet/live, release, migration ou gasto.


## J3/PRE26 #423 — diagnóstico adversarial OOS/risco multicenário, 31/10/2026

Base observada `main=bdb7fcdd7474a842e46eeb2c71249ec933b1bf95`, zero PRs abertas; J6 PRE12/PR #422 integrada e CI pós-merge verde. PRE26 introduz política tipada com limites de amostra, liquidação proxy, ambiguidade, perda por barra, drawdown e ramo adverso por fold **para cada cenário** PRE22, sem aceitação por média ou cenário melhor. Verificações de integridade cruzam contagens OOS, matched LONG e fingerprints. CLI privada reutiliza grid 1x/Nx já calculada, com opt-in e limites obrigatórios; sem novo acesso a arquivos privados. Testes para 1x/50x, tendencia sintética, flat/zero exposição, taxas, permutação, falsificação de fingerprint, limites inválidos e privacidade. Issue #423, branch `work/j3-pre26-robustness-oos-screen`. CI, revisão e merge não presumidos; J1 #319 sem resultado verificável VPS. Sem mercado, ordem, testnet/live, migration, release, deploy ou gasto.


## J3/PRE27 + J6/PRE13 — caminhos intrabar e stop ausente (#425), 01/11/2026

Base verificada `main=5c59103fa0718ed80e8e4bcb29daa40c6825eee1`, 0 PRs abertas; PRE26 #423/PR #424 integrado, Linux/Windows/Chrome verdes. PRE27 adiciona simulação determinística e explicitamente condicional em dois caminhos intrabar e dois estados hipotéticos de STOP, com custos, margem, funding e limiar de liquidação proxy PRE21. Agrega por fold/scenario nas decisões causalmente congeladas PRE22 (fingerprint e contagens validados), mede diferença frente ao pior envelope PRE21, sem trocar estratégia. Novo opt-in no replay privado `--audit-oos-path-outage` só com par 1x/Nx, sem novos arquivos. J6/PRE13 adiciona contrafactual isolado à demo PAPER sem injetar ordens/fills de execução. Testes LONG/SHORT, ambiguidade, piora por outage, 1x/50x, custos, permutação e integridade OOS. Issue #425 e branch `work/j3-pre27-stop-outage-intrabar-paper`. Aguardar CI e revisão SHA antes de merge; J1 #2/#319 permanece sem evidência privada de execução VPS, nunca reiniciar. Nenhum GET de mercado, trading real, testnet/live, credenciais, deploy, migração ou gasto.


## J1/EXIT5 #427 — recuperação da prova VPS de 50 ativos (01/11/2026)

Fatos comprovados: o usuário rodou diagnóstico read-only na VPS; `capture_exit_code=1`, `audit_exit_code=0`, 50 ativos, 36.000 candles 1h, 720h cada, 50 páginas, PIT único `2026-10-31 15:00 UTC`, `sqlite_integrity_passed=true`, `private_page_replay_passed=true`. Erro factual: `provider_rate_limit_no_retry`, retCode `10006`, etapa `closed_kline_24h`, após 157 GETs, captura já encerrada. A VPS estava no checkout `c852c4002b84b74be24b1dd986154c242971d09e`. Nenhuma mutação/GET foi executada nesta sessão pelo assistente. O caminho antigo `resume_private_bybit_j1` suporta apenas 13 ativos, então EXIT5 amplia para 50 dentro de `expanded-52` e catch-up de janelas 1..72h, preservando 720h iniciais. Dados existentes, ranking, flags live, e PIT atual não são presumidos marketwide. Issue #427, branch `work/j1-exit5-resume50-bounded`. CI e revisão obrigatórias antes do merge, sem deploy automático remoto. J1 #319 ainda aberta até 2 PIT posteriores reais confirmados pelo auditor VPS.


## J1/OPS1 #429 — observabilidade do EXIT5 (01/11/2026)

Titular VPS: pré-auditoria 50 ativos/36.000 candles/1 PIT, backup e SHA `c3e199487e9ac807d8cc2a26b78529dcbb641b7a`, quatro testes PASS. O worker owner-only PID 905841 reportou `current_pit_verified` com 156 GETs e `waiting_for_next_closed_hour` às ~06:18 UTC. Não há auditoria final no checkpoint de engenharia; **não declarar 3 PITs comprovados**. Issue #429: novo leitor local de relatório `scripts.observe_private_j1_exit5` com 28 testes POSIX offline PASS, sem rede nem SQLite, e contrato `docs/J1_OPS1_STATUS.md`. Coletor 24/7 ainda não existe em produção. J1 #2/#319 abertas.


## J1/OPS2 #429 — ranking por janela local WebSocket offline (01/11/2026)

A execução EXIT5 da VPS terminou com `resume_exit_code=1`, Bybit `retCode=10006` após 168 GETs; auditoria `audit_exit_code=0` atestou 37.470 candles, 51 ativos históricos, 50 no último PIT, 2 snapshots, cobertura inicial 720h e replay/SQLite íntegros. **Ainda faltam prova de 3 PITs e Top50 mercado** (#319/#2 abertas). A próxima implementação #429/OPS2 calcula ranking local causal por 24 velas fechadas usando journal WebSocket offline; abstenção se qualquer candidato revisado faltar, sem repetir GET em fixture. Nenhum serviço 24/7 ou conexão real ativado.


## J1/OPS3 #429 — controlador WebSocket finito (01/11/2026)

Entrega proposta no ramo work/issue-429-ops3-ws-ack-supervisor-lock, base main=8b4a358a3e6f96dd7b0cce1a388ab2dbaa5116e3. Implementa protocolo de subscribe/ACK com até 52 tópicos, heartbeat/pong, conexão/reconexão sob orçamento, lock exclusivo POSIX e relatórios sanitizados, usando journal WS já existente. EXIT5 owner-only terminou com 10006 após 168 GETs; auditoria íntegra 37.470 candles, 51 históricos, 50 seleção, 2 PIT, faltando terceiro PIT. Não há serviço WebSocket real ativado nem acesso remoto VPS; J1 #2 e Top50 #319 continuam abertos.


## J1/OPS4 #429 — piloto finito WS sem ranking REST repetitivo (01/11/2026)

Entrega de engenharia no ramo work/issue-429-ops4-owner-ws-catalog-pilot, sobre main=2756b583c82235bf41ebebc37f3933543b99ebd0 (OPS3 integrado e CI pós-merge verde). Contrato privado owner-only coleta no máximo quatro páginas de catálogo na primeira sessão, valida o escopo revisado de 50 a 52 contratos, persiste metadados em 0600, reutiliza sem GETs posteriores e recusa metadata expirada. Piloto invoca controlador WS OPS3 sob lock de escritor, audita janela de 24h de candles confirmados em journal distinto da SQLite REST, grava último status sanitizado. Não instala serviço 24/7 nem prova feed público ou Top50 global. Evidência VPS preservada: 37.470 candles, 2 PIT, 51 ativos históricos, 10006 em 168 GETs. J1 #2/#319 abertas.


## J1/OPS5 #429 — renovação causal de escopo WS (01/11/2026)

Branch `work/issue-429-ops5-causal-catalog-renewal` derivada da main `3828fefa02b8ee00f145f357423e03ea95381d20`. O piloto passa a renovar catálogo `instruments-info` só ao expirar (48h), com máximo quatro GETs, sem refazer ranking 24h por REST e sem retry 10006. Escopo compatível é acrescentado como epoch PIT privado imutável e journal WS é auditado causalmente; churn bloqueia. Falta serviço 24/7 instalado e homologação WS live. VPS EXIT5 original permanece 37.470 candles, 2 PIT, 51 históricos, 10006 após 168 GETs. J1 #2/#319 seguem abertas. Evidências da PR/CI precisam ser verificadas antes de registrar integração.


## J1/OPS6 #429 — blueprint de serviço off-by-default (01/11/2026)

Prepara pacote de supervisão operacional no branch `work/issue-429-ops6-ws-systemd-service-health`, base `main=cb6455bc7ae630856f5cdb5232b360662e7c8caa`: adaptador de lease 3300s, classes de exit para impedir restart em 10006, template systemd com isolamento, renderizador sem install/enable e leitor seguro de último health owner-only. Testes POSIX locais 17 PASS e compileall PASS, unit `systemd-analyze verify` local PASS; CI/revisão/merge ainda devem ser conferidos. Não instalado na VPS, nenhum mercado ou ordem ativados. Banco REST antigo permanece 37.470 candles, 2 PIT e última falha 10006 após 168 GET. #429 e #319 seguem abertas.


## J1/OPS7 #429 — compatibilidade do ACK WS linear (01/11/2026)

A implantação real segue pendente: OPS7 troca os seis `subscribe` por uma solicitação única de todos os 52 candidatos revisados, permitindo `req_id` ausente/vazio conforme formato Bybit linear sem ambiguidade entre lotes. Testes offline cobrem assinatura única, ACK duplicado/errado, pré-ACK e ausência de ordens. Branch `work/issue-429-ops7-linear-single-ack` derivada de `main=896f5bde924dfe5135faad42172c4744d8c798d7`; confirmar CI/merge SHA antes de declarar integrado. O serviço supervisonado OPS6 continua desativado na VPS. Coleta REST EXIT5: 37.470 candles, 2 PIT, 51 históricos, 10006 após 168 GET. J1 #2/#319 abertas.


## J1/OPS8 #429 — sonda isolada de handshake linear (01/11/2026)

Base main `b46424485e911dd4daebed8c35729ec0161b4ed7`; branch `work/issue-429-ops8-live-linear-52-handshake-proof`. Sonda POSIX owner-only com 52 tópicos candidatos revisados numa inscrição, janela finita <=90s/<=1024 frames, sem persistir, sem REST/ordens, ACK explícito e contadores sanitizados distinguindo assinatura/frames/candle fechado. Documentação D216 e `docs/J1_OPS8_LINEAR_HANDSHAKE_PROOF.md`; confirmar CI e revisão antes de merge. Piloto de persistência e systemd continuam **não homologados** na VPS. Histórico EXIT5 anterior 37.470 candles, 2 PIT, 51 históricos, erro 10006 após 168 GET permanece intocado; #319 marketwide e J1 #2 abertas.


## J1/OPS9 #429 — envelope de frames proporcional ao lease (01/11/2026)

Branch `work/issue-429-ops9-hourly-frame-budget` baseada em `main=7dd4224fb9a854e31d4f9c2d92ee3868ac38d704`, engenharia sem deploy. Serviço OPS6 configurava 3.300 segundos mas usava orçamento implícito de 4.096 frames; OPS9 explicita até 175.696 frames para os 52 tópicos e transforma esgotamento precoce em abstenção / exit 66 sem reinício automático. Default da sonda curta mantido. CI/revisão/merge ainda a comprovar. Prova real VPS 37.470 candles/2 PIT EXIT5 permanece; J1 #2, #319 e OPS1 #429 abertas. Detecção de gaps, retenção, homologação VPS e Top50 global ainda não concluídas.


## J1/OPS11 #440 — rotação segura ao fechamento UTC (02/11/2026)

Branch `work/issue-440-j1-ops11-utc-lease-rotation`, base main `0e7125693037b04c184396529d5ea9c6e80f906f`: política offline de duração adaptativa do serviço WS para encerrar 3 a ~8m após candle UTC, teste exaustivo 3600 fases, template systemd continua desligado. Código de engenharia, não homologação VPS nem prova marketwide. Aguardam-se PR/CI/revisão/merge no SHA. Histórico EXIT5 intocado; J1 #2/#319 e OPS #429 abertas.


## J1/OPS12 #442 — retomada de WS após lacunas (02/11/2026)

Base main `98eba1dbae5b7dbd3a27e0087f6df68fb1594fa3`, branch `work/issue-442-j1-ops12-ws-explicit-gaps`. Modificação offline do journal separado WS: marcadores privados de gap atômicos com candle real, default estrito, opt-in owner pilot; auditoria valida salto e rejeita órfãos, ranking 24h continua abstendo até janela limpa. Testes e docs em revisão/CI; não afirmar PASS/merge sem resultado. Sem SSH/VPS, GET, ordem, custo, deploy ou mudança na SQLite REST EXIT5. J1 #2/#319/#429 permanecem abertas.


## OPS13 #444 — diagnóstico WS privado de 24h e capacidade (02/11/2026)

Branch `work/issue-444-j1-ops13-private-readiness`, base `main=8e37e0e4e7bf78831f15cf9ba08ad92d6e755329`. Implementado auditor read-only owner-only com integridade do journal WS, escopo PIT, grade 24h, gaps, contagem de linhas e projeção de dias; testes POSIX offline e documentação, CI/merge ainda a validar. Sem rede/SQLite REST, ordens ou deploy. J1 #2/#319/#429 ainda abertas, VPS não homologada.


## J1/OPS14 — corrigir teto do probe WS real (02/11/2026)

Base GitHub `cf35e2acefe05f47be2fabed09b066976f0243b6`, branch `work/issue-429-ops14-live-probe-frame-budget`: a OPS8 mantém prova única read-only de 52 tópicos, mas sobe cap de 1024 para 8192 frames (52×90s) e diferencia saturação antecipada como abstenção. Testes adversariais e CLI/documentação atualizados. CI, revisão SHA e merge ainda pendentes. A VPS não foi acessada, #429/#319/#2 seguem abertas.


## J1/OPS15 — prova GitHub-only WS52, isolada da VPS (02/11/2026)

Base main `85c87d5c36ba12b1a3dc04cd816f166e0642c3c2`, branch `work/issue-429-ops8-github-ws52-one-shot`. Workflow owner-only por comentário exato em #429 prepara uma única sonda pública de 45s com até 8192 frames no runner efêmero e logs sanitizados. Testes estáticos, decisão D222 e contrato OPS8 alterados. PR/CI/revisão/merge e execução real ainda por comprovar; VPS e SQLite REST não foram acessados. Validade do registro encerra em 05/11/2026 15:27:39 UTC. J1 #2, universo #319, OPS #429 abertas.


## J1/OPS15 — protocolo público WS52 comprovado no GitHub, VPS pendente (02/11/2026)

Workflow owner-only #41492753422 SUCCESS no `main=ed1f3235445741e82a82b68e7cb3f43aec5e0797`: 52 tópicos solicitados, ACK=1, frames totais=1.069, frames válidos pós-ACK=1.014, 52 tópicos distintos observados, 0 velas fechadas durante 45s. Fonte rede do runner GitHub, não VPS; sem SQLite/REST/ordens/credenciais. `all_topics_delivered_verified=false` e `marketwide_top50_verified=false`; Top50 #319/J1 #2/OPS #429 continuam abertas. A sonda pública não precisa ser repetida para a mesma prova de protocolo. CI pré-merge PR #447 verde; pós-merge validar SHA/run. Próximo gate real: homologar em VPS owner-only sem recomeçar EXIT5; registrar ACK, closes UTC, integridade 24h e soak controlado.


## J1/OPS16 — prova de candle fechado ao cruzar UTC (02/11/2026)

A prova pública GitHub WS52 anterior 41492753422 confirmou ACK e frames pós-ACK de 52 candidatos, mas nenhuma vela `confirm=true` em 45s. OPS16 branch `work/issue-429-ops16-hour-close-proof` prepara uma execução **única**, comentário exato owner-only #429, espera UTC limitada 20min, inicia 30s antes do próximo fechamento, recebe 90s/8192 frames e reporta somente contagens sanitizadas. Nenhum serviço contínuo, credencial, REST, persistência, ordem ou uso da VPS. CI/merge e execução real ainda pendentes até evidência. Top50 #319 e J1 #2 permanecem abertas.


## J1/OPS17 — diagnóstico de validação no fechamento real (02/11/2026)

OPS16 PR #449 integrada em main `145d9074a365f8ba75e8809dd7828bfebe82eb2d`; prova real GitHub runner `41505630514` cruzou janela UTC com sucesso (start 18:59:30Z) e falhou em 19:00:00.429Z: `ws_frame_invalid_abstain` categoria genérica `validate`, 1 ACK, 52 tópicos, 448 frames e 393 válidos após ACK, sem candle fechado comprovado. É erro de validação, **não** prova de incompatibilidade da Bybit nem de falha da VPS. Issue #450/OPS17 branch `work/issue-450-j1-ops17-close-frame-categories` instrumenta apenas categorias allowlist sem dados sensíveis, com testes adversariais. CI/revisão/merge ainda dependem do SHA. Sem repetição de probe, GET REST, dados armazenados ou ordens.


## J1/OPS18 — diagnóstico causal do timestamp no rollover (02/11/2026)

Prova real #41514590636 em SHA `bb58414a032fa9848ef9f439e05e29b1e7e01814`: ACK 1, 52/52 tópicos, 702 frames válidos, 0 closes, `clock_trade_stamp` no fechamento 20:00 UTC. Não sabemos se `timestamp` ficou antes de `start` ou depois de `end`, nem se era vela aberta ou fechada. Issue #452/branch `work/issue-452-j1-ops18-close-stamp-diagnostics`: categorias fixas before/after/open/closed, contagem atômica de fechamentos e modo de quarentena observacional opt-in na **mesma** sonda owner-only. O coletor/SQLite mantêm gates originais; testes/CI/merge pendentes de evidência. Não houve execução live OPS18, acesso VPS, ordens ou alteração do histórico REST.


## J1/OPS19 — endurecer diagnóstico sem perder outras anomalias (02/11/2026)

Revisão em OPS18 mostrou que um `break` após timestamp inválido poderia impedir validação das linhas posteriores e esconder OHLC/confirm inválidos no mesmo row. Issue #456/branch `work/issue-456-j1-ops19-full-frame-quarantine` elimina esse atalho, exige a validação integral das demais regras e só registra quarentena de frame após examinar todas as linhas. O modo normal segue estrito; SQLite, REST e execução real não mudaram. Testes adversariais e D226 adicionados. A prova anterior OPS18 `41521829843` já está em andamento no commit `cd256e13` e não deve ser repetida ou confundida com esta correção. PR/CI/revisão pendentes no momento deste registro.


## J1/OPS20 — medir deslocamento temporal para decisão fundamentada (02/11/2026)

A prova observacional real `41521829843` no runner GitHub (20:59:30–21:01:00 UTC, checkout OPS18 `cd256e13`) terminou SUCCESS, mas `status=ws_timestamp_diagnostic_unverified`: 1 ACK, 52/52 tópicos, 1.931 frames, 1.820 válidos, 52 frames confirm=true e 2 open em quarentena, 54 com `timestamp>end`, zero com timestamp antes do início, zero closes aprovados. O excesso não foi mensurado. OPS19 #456/PR #459 integrada em `main=b0701af94d8c014f6ca5b5a62d7d7792bb75b068` para validar todas as linhas; CI pós-merge ainda a confirmar. OPS20 #460 mede somente excesso em bandas anônimas fixas, sem relaxar parsers. PR/CI e nova prova ainda não concluídos. VPS/Top50/24h continuam pendentes.

OPS20 — Regra de agregação revisada na PR #461: em frames com múltiplas linhas, registrar **somente a banda de maior excedente por categoria open/closed, uma vez por frame**, após validação integral das linhas. A soma das quatro bandas por categoria não pode exceder o número de frames em quarentena dessa categoria. Isso evita dupla contagem e não aprova eventos confirmados.


## J1/OPS21 — auditoria OHLCV puramente offline para anomalia de timestamp (03/11/2026)

Prova GitHub runner [#41569434229](https://github.com/leandrosilveiradepaula/crypto-intelligence-agent/actions/runs/41569434229), 02:59:30–03:01:00 UTC, 52 tópicos; 52 frames confirm=true com `timestamp>end`, sendo 50 na banda 2..1000ms e 2 na 1001..5000ms. Zero closes validados, zero dados gravados/GET/ordens. OPS20 #460/PR #461 integrada `main=bd453bb65ee0b0b9cc6f67f3d2580a5435c34038`; CI pós-merge Linux+Windows `41525893334` e Chrome `41525893272` SUCCESS. A documentação Bybit descreve `timestamp` como último negócio da vela, sem exceção de rollover; os dados não permitem pressupor correção automática. OPS21 issue #462/branch `work/j1-ops21-ws-rest-offline-corroboration`: comparação apenas entre entradas sintéticas/previamente validadas por esquema, com hora, símbolo, clocks, confirm e todos os seis decimais exatos coerentes, retornando relatório sanitizado e **sempre** `ws_candle_approved=false`. Falta CI/revisão/PR/merge; nenhuma validação real REST independente executada. J1 #2/Top50 #319/OPS #429 e contrato de ingestão estrito permanecem abertos.


## J1/OPS22 — corroborar um fechamento real WS×REST sem persistência (03/11/2026)

J1/OPS18–21 confirmaram 52 frames `confirm=true` em quarentena com `timestamp>end` na rede GitHub; a prova 03/11/2026 03:01Z separou 50 excedentes 2..1000ms e 2 excedentes 1001..5000ms, nenhum candle aprovado. OPS21 compara seis campos apenas de entradas sintéticas offline (não comprova proveniência real). Issue #464, branch `work/issue-464-j1-ops22-ws-rest-one-candle`, base main `090780470927bed9a0cd4b16e60763c1c5a7cbf2`: planeja uma prova owner-only de 1 tópico BTCUSDT, uma conexão WS, no máximo um GET REST público após UTC close +1s, comparação OHLCV6 usando auditor OPS21 non-authorizing, com resposta sanitizada e sem armazenamento, ordenação ou ordens. Padrão temporal do auditor e parser persistente permanecem estritos; flag só de comparação com WS cedo não altera journal/ingestão. Código/testes/CI/PR e evidência real pendentes no checkpoint; não declarar proveniência independente, Top50 ou VPS. #2/#319/#429 abertas.


## J1/OPS23 — temporização de coleta pela VPS, desativada por padrão (03/11/2026)

Issue #466; branch `work/j1-ops23-systemd-once-timer` baseada em `main=0c180200189271b91f0e0f001cabb2d465e189f5` e OPS22 PR #465 integrada/CI verde. O disparo por automações ChatGPT falhou repetidamente (registro `requires_user_action=true` e zero comentário-gatilho da OPS22), enquanto a prova WS52 OPS20 precisou de chamada direta no GitHub. O novo design usa `systemd.timer` com data UTC absoluta e uma execução única, que verifica NTP, SHA/árvore, horário, conta POSIX não-root, diretório privado e marker atômico `O_EXCL` antes de aguardar UTC; sem recuperação após atraso. Templates NÃO estão instalados, habilitados ou rodando. Testes adversariais em `tests/test_j1_ops23_once_timer.py`, especificação em `docs/J1_OPS23_VPS_SYSTEMD_ONCE.md`, decisão D230. PR/CI/merge devem ser confirmados antes de liberar deploy. Mesmo após CI o bloqueio de J1 #2, Top50 #319, OPS #429 e prova real OPS22 #464 continua; nenhuma vela confirmada aprovada, trade, REST/WS nem alteração de banco neste bloco.


## J1/OPS25 — problema de frame pré-ACK no teste VPS de 03/11/2026

A VPS comprovou início do timer `22:45:00Z` e tentativa finita até `22:59:32Z`, mas primeiro frame WS antes da confirmação de subscribe causou `ws_preack_abstain` (`ws_frames=1`, `rest_gets=0`, `fields_compared=0`). O claim de uso único permanece presente. Issue #469/branch `work/issue-469-j1-ops25-preack-bound` implementa descarte bounded de até oito envelopes de mercado antes do ACK e exige ACK válido + frame **posterior** para qualquer comparação. Nenhuma leitura REST, coleta histórica, ordem, reinício ou instalação foi executada nesta correção de código; teste real de WS×REST e homologação de Top50/J1 continuam pendentes. CI/revisão/merge devem ser provados antes de marcar integrado.


## J1/OPS26 — teste VPS 2 e correção estrutural (04/11/2026)

A segunda sonda de candle na VPS foi de fato executada pela janela UTC: 26 frames WS, `ws_envelope_abstain`, 0 GET REST, 0 campos comparados, tentativa isolada consumida. Hipótese plausível, não confirmada, é incompatibilidade com formato multirow; a saída sanitizada não identifica o motivo exato. Issue #472 implementa diagnóstico por categorias fixas, tratamento de até oito linhas pós-ACK com validação completa e seleção única de candle fechado apenas para auditor não autorizador, sem mudar ingestão. Código/CI/merge e nova homologação da VPS devem ser evidenciados separadamente; cron antigo não deve ser reexecutado. J1 e Top50 continuam abertos.


## J1/OPS27 #474 — gate de timestamp WebSocket antes de 24h (04/11/2026)

OPS26 comprovou timer one-shot e igualdade 6/6 WS×REST de um único candle BTCUSDT do mesmo provedor na VPS (29 frames, 1 GET, 0 ordens/armazenamento); três markers preservados, timers desabilitados, sem 24h ativado. A anomalia `timestamp>end` observada em OPS18–20 permanece incompatível com o parser estrito da coleta: coincidência de valores de mercado não certifica causalidade. OPS27 prepara auditor offline por bandas de excedente e confirmação, testes de referência/duplicata/multirow/clock adversariais, e critérios de no-go em `docs/J1_OPS27_CAUSAL_ROLLOVER_GATE.md`; código da ingestão não é afrouxado. J1 #2/Top50 #319/OPS1 #429 ainda abertas e sem prova de serviço 24/7. CI/merge específicos devem ser confirmados.


## J1/OPS28 #476 — política causal pré-ACK para supervisor (04/11/2026)

A revisão da OPS1 detectou que o supervisor multiativo `bybit_ws_supervisor.py` permitia replay de frames de mercado guardados antes da confirmação de assinatura, divergindo do probe OPS22/decisão D231. A OPS28 altera somente supervisor/testes: pré-ACK estrutural do tópico esperado é contado e descartado sob limite 128; ACK só libera quadros **novos**; frames inesperados ou acima do limite falham fechados sem escrita. `early_frames_buffered=0` e `preack_frames_discarded` tornam comportamento observável de forma sanitizada. Parser temporal estrito e quarentena D233 não são alterados. Branch/CI/merge devem ser verificados; serviço 24h e Top50 marketwide não estão homologados.


## J1/OPS29 #478 — simulação de continuidade trans-horária (04/11/2026)

A correção OPS28 foi integrada em `main=87f135a50bb4f40a1b7b205c0874ec37c73a0232` e 3/3 CI pós-merge aprovadas; nenhuma PR aberta na revisão inicial. A OPS29 adiciona `j1_ws_multihour_soak.py` e regressões para 30 horas sintéticas de 2 membros, uma sessão limitada a cada hora, 24h de warm-up e 7 decisões fechadas sucessivas, incluindo reconexão e descarte pré-ACK. O contrato exige auditoria SQLite real da fixture a cada fechamento, ACK e o mesmo fingerprint PIT, abstenção em gap, replay, conflito, clock inválido ou falha de integridade; sem legitimidade de feed real. Branch `work/issue-478-j1-ops29-multihour-soak`, CI/merge devem ser provados. VPS, sistema operacional e dados financeiros permanecem intocados. J1 #2, OPS1 #429 e Top50 #319 abertas.


## J1/OPS30 — observação WS shadow sem gravação (04/11/2026)

Após simulação offline OPS29 de 30 horas e a prova real OPS26 de igualdade 6/6 em um candle BTCUSDT, a admissibilidade causal `timestamp>end` ainda bloqueia a promoção automática do feed ao journal 24/7. A issue #480 acrescenta observador independente de uma sessão WS finita, somente contadores anônimos por tópico/fechamento e bandas de timestamp (inclusive fora de end), preservando todas as validações de row exceto o predicado de pesquisa D233. Nenhum candle, símbolo, preço ou horário de negociação é armazenado/logado. CLI owner-only requer opt-ins de rede/WS/região; padrão não conecta. CI/merge e qualquer ativação VPS são etapas separadas. J1 #2, OPS1 #429 e Top50 #319 abertas.


## J1/OPS31 #482 — preparo do piloto shadow owner-only na VPS (04/11/2026)

OPS30 #480/PR #481 integrada, CI pré e pós-merge 3/3 SUCCESS em `main=6bf647aa354abfe5228a34be0a84a5ff687ca0f3`. Issue #482, branch `work/issue-482-j1-ops31-shadow-one-shot`: novo launcher de timer absoluto, claim privado, render-only systemd, validação de retorno/histogramas e regressões adversariais; D237 e `J1_OPS31_SHADOW_ONESHOT.md`. Código aprovado não equivale a coleta real. VPS ainda no SHA observado `229969952c3c0bcd06b35f7b828eac21c9bd1498`, três claims intactos, serviço contínuo off. PR/CI/merge do OPS31 exigem provas separadas; #429 OPS1, #319 Top50 e #2 J1 abertas.


## J1/OPS32 #484 — decisão causal offline (05/11/2026)

OPS31 #482 está concluída com evidência real da VPS: 229 frames, 2 fechamentos únicos, ambos com `timestamp>end`, sem REST/writes/ordens, serviço SUCCESS, timer desabilitado e 4 claims preservados. D238 declara NO-GO para promoção dos candles Bybit WS e para coletor 24h. Branch `work/issue-484-j1-ops32-causal-source-decision` desenvolve avaliador offline Bybit V5/Binance USD-M WS/REST com fechamento explícito, clocks, anti-lookahead, OHLCV Decimal, unidade de volume e quarentena; 15 testes focais executados localmente e PASS. **PR/CI/merge ainda precisam de confirmação independente**; código offline não prova feed live nem escolhe venue final. Próxima gate: CI, review e merge sem deploy se verde. J1 #2/OPS1 #429/Top50 #319 continuam abertas.


## J1/OPS33 #486 — preparação da alternativa causal Binance (05/11/2026)

OPS32 #484/PR #485 integrada em `main=ccbb62406c8af46b1a3e23cedab7db0e327450f9`, CI pré e pós-merge 3/3 verde. OPS33 branch `work/issue-486-j1-ops33-binance-shadow-once`: implementação offline de 2 tópicos públicos Binance com `k.x` e gate OPS32, clock/ACK, contador sanitizado, opt-in non-root, lançador isolado one-claim e templates `systemd` sem instalação; 20 testes locais PASS sob shims de dependência para unidade focal (não prova integração completa). CI/PR/merge exigem gates reais SHA. Ainda NO-GO para serviço 24h e Top50. VPS OPS31 teve 2/2 closes Bybit em quarentena; timer desativado e claims preservados.


## J1/OPS34 #488 — auditoria de contrato e Top50 Binance offline (05/11/2026)

OPS33 #486 fechada: VPS Binance 178 frames, dois closes causais, timer disabled, cinco claims preservados, nenhuma gravação/ordem. Branch `work/issue-488-j1-ops34-binance-pit-top50` a partir de `main=7964fa4d149eca64ddfe82df7851470b1b5c7a3a`, sem PR aberta na inspeção inicial. `j1_binance_top50_pit.py` e regressões adversariais (26 testes locais via shims compatíveis, **CI integrada ainda gate separado**) + guia D240. `marketwide_top50_verified=false` e `usdm_contract_verified=false` sem autenticação/censo/24h reais de todo o mercado. Próximo: review, CI PR Linux/Windows/Chrome, merge sem deploy se verde e CI pós-merge. Não repetir sondas OPS31/33, nem iniciar 24h/ordens.


## J1/OPS35 #490 — preparação de auditoria Binance metadata-only (05/11/2026)

OPS34 #488/PR #489 integrada em main `1dffc83277aacd73c29207fc942674a9ce2ec253`, CI 3/3 pré e pós verde. OPS35 branch `work/issue-490-j1-ops35-binance-metadata-once` desenvolve GET-only exchangeInfo via cliente limitado (2 GETs, 2MiB, 8s, sem retry e sem credenciais), catálogo pre/post, registry PIT as-of, saída sanitizada e zero escrita/ordem. 16 testes locais PASS com shims; CI e merge ainda precisam ser verificados separadamente. Região, quota e registros atuais não foram testados na VPS. Top50 marketwide, contrato autenticado e coletor 24/7 continuam NO-GO.


## OPS35 D242 — separação de censo e identidade (05/11/2026)

Branch `work/issue-490-ops35-catalog-only-observation` preparada a partir de `main=b3c4473cd7d961642a6ccd9813aada1c5db36e9e`; implementa modo catalog-only explícito para metadata Binance sem registro PIT, flags sempre false, e reforça expiração do modo de identidade durante a janela de dois GETs. 26 testes locais do probe + 26 do ranking OPS34 em ambiente de shims PASS; integração GitHub/CI/merge requer comprovação independente neste checkpoint. Nenhum acesso real de mercado, deploy ou alteração SQLite/ordens. #490 permanece aberta até prova owner-only de metadados. J1 #2, #319 e #429 abertas.


## J1/OPS36 #493 — replay Binance WS 24h offline (05/11/2026)

O titular não tem acesso à VPS; OPS35 #490 execução real fica pendente. Na main `ad0022e3cd94c8672013183eb7e5079a40f5a8c5` foi iniciado módulo offline `j1_binance_ws_24h_replay.py` + testes adversariais e guia D243, sem rede, SQLite, timer ou trading. Contratos OPS32/34 reutilizados para 24 fechamentos de cada ativo de amostra revisada, quote turnover determinístico. É pesquisa sintética não homologada e não prova Top50. PR/CI/merge devem ser comprovadas antes de declarar prontidão. J1 #2, OPS1 #429, Top50 #319 e OPS35 #490 abertas.

J1/OPS37 #495: VPS OPS35 #490 atualizou main ad7b8f03e8ae1ccbec2d43b25513b5d4ff5e7de5, passou 52 testes, criou claim unico, teve requests_attempted=1/responses_validated=0/status=metadata_transport_or_validation_abstain, 0 writes/ordens. A causa nao foi observada. OPS37 prepara status de estagio e categorias fixas, testes e D244, sem repetir a captura; CI/merge exigem comprovacao. J1 #2, Top50 #319, OPS1 #429, OPS35 #490 abertas.


## J1/OPS1 D245 — observador de saude local (06/11/2026)

Primeiro bloco seguro sem VPS da #429: auditor `j1_local_health.py` sobre SQLite existente em modo somente leitura, 24 candles 1h fechados, checkpoint e PIT de amostra. CLI isolada sem rede, writes, ordens ou agendamento. Testes locais em fixture: 15 PASS no desenvolvimento focal; CI integrada na PR e pos-merge sao evidencias separadas. Nunca classificar amostra 50 como Top50 marketwide; #319/#429/#2 continuam abertas. Ver docs/J1_LOCAL_HEALTH_READONLY.md.


## J1/OPS1 D246 — observador SQLite v2 (06/11/2026)

Inspecionada main `4023aae65f7eea4a291e2ad55878350870b91adf` (#497), issue #429 e supervisor WS preexistente. Escolhido corrigir falsa sensação de saúde do observador D245: a v1 lia apenas timestamps/quality e nao verificava os preços/volumes, permitindo linha malformada em amostra estruturalmente completa. Branch `work/issue-429-j1-ohlcv-health-integrity` adiciona verificação integral dos OHLCV Decimal, schema e unicidade dos checkpoints + testes adversariais. Resultado local e CI ainda precisam ser comprovados; zero acesso VPS, rede, SQLite real ou trades. Top50 e J1 permanecem abertas.


## J1/OPS1 D247 - leitura isolada de WS owner research (06/11/2026)

Main de base verificada `115cd8f38f6f135702d3dcf2a530d67b0ad021d2`; #429 aberta e nenhuma PR aberta no preflight. Branch `work/issue-429-j1-ws-owner-readonly-audit` prepara auditor offline do SQLite `ws-confirmed.sqlite`, que nao tem as mesmas tabelas do SQLite historico de D246. Reusa validadores reais do journal e PIT, nao cria segundo supervisor. Prova offline e CI no SHA da PR pendentes neste registro inicial; nenhum deploy, GET, VPS ou ordem. Top50 segue nao homologada.


## J3/PRE28 #500 — risco causal de correlação (06/11/2026)

Verificada main `22abacd43307346cba658f180f04d224c6a3dfae`, sem PR aberta, J1 #2/#319/#429 bloqueada por provas operacionais reais. Issue #500 criada; branch `work/issue-500-j3-pre28-causal-correlation-gate` desenvolve política opt-in de correlação por pares e check de risco PRE20 por prefixo de marcação (sem olhar futuro). Limites e limitações em D248 e docs/J3_PRE28_CAUSAL_CORRELATION_GATE.md. CI, SHA da PR e merge exigem comprovação independente; nada foi executado na VPS, exchange, testnet ou live.


## J1/TOP50 D249 — prova real e censo integral preparado (06/11/2026)

Prova owner VPS `srv1319424`: re-auditoria SQLite exit0, 37470 candles reais em 51 series/50 selecionados, 2 PITs (0 consecutivos no final), último PIT 01/11 06:00 UTC; Bybit catálogo real 930, filtros basicos 822, ticker 822; 50 candidatos ticker consultados com 1200 klines fechadas UTC de 24h, 52 GET, 10/10 Top10 coincidente só na amostra, 0 writes/ordens. Falta cobertura dos outros 772 e identidade independente. Issue #502 e branch `work/issue-502-j1-basic-marketwide-24h-replay` preparam recenseamento offline TDD e replay de lote com DB separado, sem rede no CI; CI e prova real global ainda pendentes neste checkpoint. D249, docs/J1_TOP50_CLOSED24H_MARKET_CENSUS.md.


## J1/TOP50 D250 — falha real e correção de diagnóstico (06/11/2026)

Titular VPS executou D249 #503 com SHA `ec8a7d15e30252fea2e585945dd8ceaf0462e136` e recebeu `status=abstain`, `failure_stage=kline`, `requests_attempted=6`, `completed_contracts=4`, `validated_closed_1h_rows=96`, `remaining_contracts=818`; `provider_ret_code=null`. Nova leitura **sem rede** confirmou 822 escopo, 4 concluídos, 96 velas, 0 parciais, SQLite íntegro, UTC window 06/11 13:00. Resposta do quinto GET não está em cache, causa exata não é recuperável. Branch `work/j1-502-abstain-classification` desenvolve status/failure_code allowlisted e regressão, sem novos GET/ordens/deploy. #502/#319/J1 abertas; somente CI e nova prova real poderão promover o estado.


## J1/TOP50 D251 — correção de parser após prova real (06/11/2026)

VPS realizou re-prova D250 (1 catálogo + 1 kline): 822 contratos técnicos, 4 concluídos, 96 velas, 818 pendentes, janela 06/11/2026 13:00 UTC, `status=abstain`, `failure_code=invalid_candle_decimal`, `failure_category=candle_integrity_or_time`. Sem comprovante do campo e lexical do valor; somente rejeição decimal foi demonstrada. Branch `work/issue-502-j1-census-bounded-decimal-lexemes` passa a aceitar notação científica Decimal finita/limitada e disponibiliza campo inválido como enum seguro; sem trocar janela, pular ativo, remover contrato, rede ou ordens. Evidência de CI/merge e nova observação VPS continuam gates separados.


## J1/TOP50 D252 — 20 contratos reais, incompatibilidade de símbolo (06/11/2026)

VPS executou lote sequencial no SHA `8fa321ef04a8cabeaead88b2c4ba61e4f94caa47`, encerrou `abstain` em `kline/invalid_kline_window` depois de 16 GETs, com 20/822 contratos completos, 480 candles e 802 pendentes, sem writes ao histórico legado nem ordens. Comparação do código revelou `_catalog` aceitando até 32 caracteres e transporte limitando `[A-Z0-9]{2,24}USDT`; rejeição local anterior ao GET é compatível com divergência, mas símbolo exato não foi registrado. Branch `work/issue-502-j1-symbol-shape-contract` alinha forma técnica base 1..28 + USDT e testes de fronteiras. Integração e nova prova VPS ainda requerem CI e SHA. Preserve janela original 2026-11-06 13:00Z, sem reset, retry ou skip silencioso.


## J1/TOP50 D253 — 247 completos, curto histórico observado (06/11/2026)

VPS owner com SHA `a82bd25b48951984d18e6d55ae7c326305513025`: 5 testes de forma + 16 de censo OK, lotes: 21/504 (2 GET), 141/3384 (121 GET), 247/5928 (108 GET) e `abstain/kline_not_24_closed_hours` em 822 candidatos técnicos, 575 pendentes. Nenhuma ordem, histórico original intacto. Causa curta ainda SEM prova de listagem recente. Branch `work/issue-502-j1-incomplete-24h-survey` D253 implementa observações incompletas persistentes 0..23 com replay/hash e survey completo com abstenções, preservando janela UTC e posição no catálogo. Ranking marketwide segue não verificado se um membro for curto; CI/PR/merge/prova VPS necessários separadamente.


## D256 — auditor de censo somente leitura (06/11/2026)

Prova D255 owner no SHA `cdc2a125bb224b143010044675facdbe4f8be89e`: 822/822 contratos básicos inspecionados; 819 completos, 3 short, 19.656 candles completos + 6 observações short, 0 pendentes. Digest apenas do Top50 entre completos `b4e4884d28e4a4b385c94ea521201006242d449828d575a56f01cb2b70b8faaa`. Top50 global, crypto-only e continuidade continuam não validados. D256 implementa auditor independente, offline e owner-only de replay do SQLite privado e identifica que entre os 715 inspecionados da D254 e 822 da D255 há 107 novos, mas a última execução informou somente 48 GETs. Se as provas forem adjacentes, mínimo de 60 inspeções carecem de proveniência por sessão observada; não inferir ausência de coleta, nem afirmar causa. Script, teste e guia em `scripts/audit_j1_marketwide_checkpoint.py`, `tests/test_j1_marketwide_checkpoint_audit.py`, `docs/J1_D256_MARKETWIDE_READONLY_AUDIT.md`. PR/CI/merge não comprovados neste checkpoint inicial. #502/#319/#429/#2 permanecem abertas até os critérios faltantes.


## J1 D257 — fila de identidade com censo já auditado, sem GET (06/11/2026)

Ponto de partida real D256 na VPS: 10 testes PASS; 822/822 contratos técnicos inspecionados, 819 históricos 24h completos, 3 short (6 velas), 19.656 candles validados, zero GET/write/ordens, hash do Top50 subset `b4e4884d28e4a4b385c94ea521201006242d449828d575a56f01cb2b70b8faaa`. A próxima revisão não consulta Bybit novamente. Nova `scripts/triage_j1_marketwide_identity.py`, teste adversarial e documento D257 com reuso de D256 e `CryptoRegistryHistory`, auditam sobreposição e fila de revisão com registro de 52 bases vencido para 06/11. Ainda não é elegibilidade contemporânea. CI/merge/prova de VPS específicas D257 são gates separados, não foram comprovados nesta nota inicial. J1 #319/#502/#429/#2 abertas.


## J1 D258 — identificadores de prioridade somente com opt-in local (07/11/2026)

VPS D257 owner: 8 testes PASS; 822 técnicos inspecionados, 819 completos, 3 curtos, 52 bases com referência histórica dentre completos, 19/50 no Top50 completo-subset e 31/50 sem referência; 767 completos ausentes do registro. Manifesto histórico com idade `682341000ms` (>7d), portanto **não elegível temporalmente**. D258 adiciona opção local `--include-public-symbols` ao CLI de triagem, desativada por padrão, para mostrar identificadores públicos e sinal de referência histórica das 50 linhas prioritárias e dos short separados, sem divulgar valores financeiros nem liberar negociação. PR/CI/merge e prova real D258 devem ser registrados separadamente. #319/#502/#429/#2 abertas.


## J1 D259 — TradFi misturado no Top50 bruto identificado (07/11/2026)

D258 owner VPS confirmou 819 completos/3 curtos, 11 testes PASS, top50 19 referências de registro vencido e 31 sem referência. Evidência oficial Bybit data de 26/08 e 19/10 permite identificar 21 dos 50 como contratos TradFi; os 3 short `DUOLUSDT/FISVUSDT/FNUSDT` foram listados em 06/11 às 11h UTC como TradFi, duas horas antes do corte 13h. D259 registra evidências negativas versionadas, marca 21 como `bybit_tradfi_documented_retrospective`, mantém 19 como `archived_crypto_reference_only` e 10 como `identity_unresolved` na amostra REAL, mas estas contagens ainda dependem de execução de código D259 na VPS. Todos estão bloqueados para operações. Não presumir que 21 sejam a totalidade TradFi entre 822, nem que 19 sejam crypto-only no PIT atual. Próximos gates: CI/PR/merge sem deploy, depois prova VPS read-only. #319/#502/#429/#2 abertas.


## J1 D261 — fronteira offline de revisão de identidade (07/11/2026)

Prova VPS real D259: 14 testes OK, 822 inspecionados, 819 séries 24h, 3 short, Top50 bruto 21 TradFi/19 registros antigos/10 não resolvidos, zero GET/ordem/escrita e digest `b4e4884d28e4a4b385c94ea521201006242d449828d575a56f01cb2b70b8faaa`. D261 cria catálogo hipotético de identidade (10 símbolos) com colisões, aliases, metais tokenizados e URLs de pesquisa, sem afirmar verificação. Triagem D257 reusa o SQLite existente para preparar uma **fronteira pesquisável, não negociável**, de até 50 séries completas fora do conjunto de negativos documentados, que não é exaustivo. Contagem e digest sanitizados; rank e nomes só sob opt-in. Nenhum reset de censo ou mudanças de sistema. Head/CI/PR/merge D261 exigem prova específica, não inferir de commits antes da verificação. J1 #319/#502/#429/#2 continuam abertas.


## J1 D262 — regressão de contrato de símbolo diagnosticada (07/11/2026)

Prova D261 na VPS: 6 testes de crosswalk e 16 de triagem PASS, mas CLI real `abstain/sqlite_replay/registry_or_storage_validation_invalid` com 0 GET, 0 DB write e 0 ordens. O problema provável é divergência entre contrato de base unitária D256 e regex D261, não corrupção comprovada dos dados. D262 corrige regra da fronteira (base 1..28, sufixo USDT) e adiciona testes SQLite completos para `XUSDT` fora do Top50, limites 32 total e sanitização de falha. **Nenhuma evidência nova da VPS ainda**: manter D261 sem aceite operacional até rerun. PR/CI/merge sujeitos a gates; #319/#502/#429/#2 permanecem abertas.


## D263 — triagem negativa de metadados atuais, com J1 ainda aberta (08/11/2026 UTC)

#502 encerrada como **survey básico + auditoria** com provas owner de 822/822 inspecionados, 819 completos e 3 short documentados, 19.656 velas completas e 25 testes D262 PASS na VPS; não homologou Top50. Issues #319/#429/#2 continuam abertas. Nova auditoria D263 read-only compara catálogo contemporâneo Bybit de instrumentos lineares com membros do SQLite congelado, classifica apenas indícios TradFi atuais de `marketRegion`/`underlyingTicker`, 1 GET owner opt-in sem rebaixar freios de rede, logs só contagens e timestamps. Qualquer falta de campos, paginação ou temporalidade não autentica identidade cripto; CI e prova owner D263 são gates separados, ainda não comprovados no momento deste registro.


## D264 — sidecar de indicadores contemporâneos sem rebaixar gates (08/11/2026 UTC)

D263 owner PASS (8/8): 297/822 com indicadores atuais TradFi, 525 sem indicação e **não cripto aprovados**, 24 negativos D259 documentados (3 sem indicação). D264 acrescenta opção privada explícita para persistir apenas a lista atual dos indicadores em artefato imutável, novo GET owner-only se autorizado, com replay offline read-only do censo 819 completos e pesquisa de 50 após overlays contemporâneos. A execução real D264 e classificação independente PIT não estão provadas nesta nota; CI/PR/merge separados. #502 CLOSED somente censo técnico; #319/#429/#2 OPEN. Detalhes em `docs/J1_D264_PRIVATE_CURRENT_NEGATIVE_SNAPSHOT.md`.


## J1/D265 — descoberta de Brent Oil e revisão de dez nomes (08/11/2026 UTC)

Owner D264 repetiu replay offline exibindo 10 símbolos públicos, não valores de candles: BZ, WLFI, CAP, CYBER, CLANKER, XPL, FARTCOIN, DGAI, PONS, ASTER. D265 encontrou anúncio oficial da Bybit `BZUSDT` como Brent Oil, mesmo sem sinal `marketRegion`/`underlyingTicker` na captura D264. Filtro negativo documental cresce para 25; sete pistas de token, um caso CLANKER colidido e DGAI sem ID. A classificação segue `research-only`, não Top50 elegível; #517/#319/#429/#2 continuam abertas. O código/CI/merge e replay privado D265 exigem provas distintas.


## J1/D266 — validador offline de evidências sem promoção (08/11/2026 UTC)

D265 VPS operacional: 30 testes PASS; 297 vetos TradFi atuais + BZ Brent Oil documental = 298 dos 819 completos excluídos somente da pesquisa; fronteira 50 = 30 referências antigas, 18 hipóteses, 2 desconhecidas, raw digest e snapshot D264 inalterados. D266 fornece verificador offline de dossiês de contratos, com checks causais de URLs independentes, segurança, SHA256 e vetos; `identity_approved=false`, `eligible_top50=false` invariantes. Testes, docs e PR têm gates próprios; sem evidências reais adicionais de token/mint, nenhum dos 50 foi certificado, nem coleta 24/7 homologada.


## J1 OPS/D267 — pré-voo read-only do serviço WS (#521)

D265 owner aprovado com 30 testes, 819 históricos, 298 vetos de pesquisa, 50 fronteira (30 referências antigas + 18 hipóteses + 2 desconhecidos). D266 PR #520 já merged/CI completa no SHA `203758c563ac59b51ad484b5e6533daae6ee8491`, entrega validador offline de dossiês. D267 #521 é bloco paralelo em #429: diagnóstico único do status systemd, janela privada WS e último health, sem ativação ou GET. Main preflight SHA `203758c563ac59b51ad484b5e6533daae6ee8491`; validar PR/CI/merge e VPS antes de afirmar qualquer continuidade. #319/#429/#2 abertas. Nenhum sistema contínuo ativado por esta mudança.


## D268 — pré-voo de instalação WS sem deploy (09/11/2026)

Prova D267 VPS: 9 PASS, unidade `cia-j1-ws-owner.service` not-found/inactive, nenhum `ws-confirmed.sqlite` na árvore pesquisada, 0 requests/ordens/DB modified; #521 CLOSED, #429 OPEN. D268 cria ferramenta de validação POSIX owner-only do template/off-by-default e da pasta privada planejada, sem instalar unidade, criar banco/diretório ou emitir WS/GET. Faltam gate de implantação, refresh causal de escopo <=48h, identidade crypto-only #319 e prova de 24h contínuas. CI/PR/merge e avaliação VPS D268 exigem evidência própria.


## D269 — replay multi-epoch do escopo WS existente (09/11/2026)

D268 owner VPS **10 testes PASS** em `be6af1747436a990e7a1720adfe93896e24aa591`: `private_directory_requires_owner_provisioning`, template válido, serviço ausente, checkout limpo, 0 rede/writes/ordens. Issue #523 CLOSED apenas para pré-voo. Revisão de #525 identificou renovação de 48h existente e testes de expiração/quota/churn. D269 adiciona testes de 98h/3 épocas e rejeição tardia sem perda silenciosa; CI/PR/merge ainda exigem prova separada. #429 ainda serviço WS não instalado, #319 identidade crypto-only e #2 J1 abertas.


## J1/M1 — primeiro writer REST incremental hourly, sem instalação (09/11/2026)

Preflight `main=68d9d72677fd6dc11a8848d7f2b0b7c0c6cbba0e`, zero PRs abertas. Após uma sequência de auditores offline sem serviço instalado, M1 implementa `j1_rest_incremental_owner.py` (janela fechada UTC, novo SQLite, cursor+digest por contrato, no overlap com censo D264, fail-stop provider), CLI, modelos systemd oneshot+timer OFF e testes de persistência/retomada. Não afirmar CI, merge ou prova VPS antes de conferi-los. #429/#319/#517/#2 permanecem abertas; nenhum deploy, envio de ordens ou acesso financeiro.


## J1/M2 — hardening do writer REST (09/11/2026)

Issue #528; branch `work/issue-528-j1-m2-hourly-rest-safety`. Inspeção do M1 integrado detectou que o check da janela UTC no começo aceitava resposta lenta após HH:15 dentro da mesma hora. M2 adiciona guard após GET e antes de publicação, e latch de quota/integridade sob flock do escritor, com regressões de tempo fake. Este registro documenta somente código proposto; CI, revisão, merge e provas da VPS precisam ser confirmados separadamente. #429/#319/#2 abertas; não há autorização de serviço/ordens/marketwide.


## J1/M3 — canário REST de duas horas preparado (09/11/2026)

Preflight main `01bffb798737d7da8eeef1659f18f6ddc3bb8b30`, PRs abertas=0. Issue #530: orquestrador novo `scripts/run_j1_rest_twohour_canary.py`, testes fake-clock `tests/test_j1_rest_twohour_canary.py` e runbook `docs/J1_M3_REST_TWOHOUR_CANARY.md`. Duas horas UTC consecutivas N=2, base D264 somente leitura, saída separada e auditoria SQLite independente (50 velas, 2 publicações, digests e cursores); sem timer, sem GET no CI. Evidências CI, revisão e merge exigem verificação; VPS não acessada/acionada. #429/#319/#2 abertas.


## J1 — Top 50: fila de rivais por dominância matemática (11/11/2026)

A questão prioritária é identidade de ativos cripto, não funcionamento do worker incremental. O censo histórico já fornece 819 séries completas de 24h, com negativas TradFi atuais/documentais que não constituem classificação cripto positiva nem são retrospectivamente PIT. O redutor puro da branch `work/issue-319-top50-proof-by-dominance` calcula a fila mínima de concorrentes desconhecidos acima do corte do 50º positivamente revisado; qualquer volume faltante bloqueia certificação. Estado inicial de implementação em branch, sem prova de CI/merge neste registro; `marketwide_top50_verified=false`. A coleta contínua #429 e ativação do timer recorrente são frente independente. Ver `docs/J1_TOP50_RANK_PRESSURE.md`.


## J1/D273 — diligência primária DGAIUSDT (11/11/2026)

Dois anúncios primários distintos Bybit/Gate sustentam a hipótese de DGrid AI para DGAIUSDT e identificam o token BNB Chain publicado pela Gate. Implementação de lead versionado e testes adversariais na branch `work/issue-517-d273-dgai-primary-identity`; **sem CI/merge comprovados neste checkpoint**. Fontes foram revisadas depois do censo de 06/11, logo não aprovam identidade PIT, não garantem Top50 nem habilitam trading. Ver `docs/J1_D273_DGAI_PRIMARY_IDENTITY.md`.


## J1/D274 — segunda identidade com fontes primárias (11/11/2026)

CLANKERUSDT: fonte Bybit Learn sobre tokenbot (CLANKER) e listagem perpétua; fonte Binance Futures sobre tokenbot e endereço Base 0x1bc0c42215582d5a085795f4badbac3ff36d1bcb. Branch `work/issue-517-d274-primary-clanker-crosswalk` agrega evidências de pesquisa e regressões; validação e merge devem ser conferidos à parte. Sem reabrir coleta, sem aprovação PIT ou Top50. Ver `docs/J1_D274_CLANKER_PRIMARY_CROSSWALK.md`.


## J1/D275 — frente de identidade Top50 em lote (11/11/2026)

Branch `work/issue-319-d275-frontier-review-batch`: módulo puro para anexar ao replay D264 existente a fila de pesquisa de todos os 50, combinando referências arquivadas e evidências primárias D273/D274 sem promover aprovação. Saída padrão somente contagem/digest, opt-in owner para nomes; testes unitários e SQLite. **Este checkpoint de branch não é CI/merge nem prova owner real.** O conector VPS não consegue executar como `cia-probe` por permissão; não relaxar isolamento. Ver `docs/J1_D275_FRONTIER_BATCH_REVIEW.md`.


## J1/D276 — cenários do corte Top50 no banco real (11/11/2026)

Replay real owner somente leitura em 819 séries completas e 3 incompletas revelou substitutos LYN (sem XAUT) e LYN/DOT/ICNT/ELSA/AERO (sem XAUT + 4 colisões). Nenhum desses cenários aprova ativos ou resolve retrospectivamente PIT. Branch `work/issue-319-d276-top50-cutoff-sensitivity` integra relatório determinístico ao D264 e testes. **CI/merge não confirmados neste checkpoint**, verificar head final. Ver `docs/J1_D276_TOP50_CUTOFF_SENSITIVITY.md`.


## J1/D277 — shorts incompletos com fontes primárias (11/11/2026)

Prova owner real 822 catalogados = 819 completos + DUOLUSDT/FISVUSDT/FNUSDT com 2 candles cada, e os três com indicadores negativos TradFi D264. Bybit publica anúncios oficiais de perpétuos TradFi de Duolingo, Fiserv, Fabrinet às 11h UTC 06/11. Branch `work/issue-319-d277-short-tradfi-primary-proof` implementa anotação read-only no replay D264 e testes; CI/merge ainda não estão comprovados neste checkpoint. Ver `docs/J1_D277_SHORT_TRADFI_EVIDENCE.md`.


## J1/D278 — nove rivais pesquisados em lote (11/11/2026)

Branch `work/issue-517-d278-batch-cutoff-primary-crosswalk`: matriz de 9 símbolos da fronteira D276 (LYN, DOT, ICNT, ELSA, AERO, LIT, ARIA, BIRB, CLANKER), fontes oficiais por tipo venue perp/independente perp/migração spot, tests e integração no replay D264 sem rede. LYN/ELSA/LIT têm duas fontes nominais, ICNT só uma independente e AERO migração spot que não comprova perpétuo. Todas identidades ainda research-only, D261/PIT sem promoção. Este checkpoint de branch não prova CI/merge. Ver `docs/J1_D278_CUTOFF_PRIMARY_BATCH.md`.


## J1 — seleção automática de candidatos USDT perpétuos (11/11/2026)

Nova branch `work/issue-319-j1-auto-usdt-perp-research-filter` separa pesquisa automática de contratos USDT lineares perpétuos de autorização de negociação. Filtro puro, sem registro positivo individual para **pesquisa**, exclui TradFi documentado e marcadores de metadados, reconhece desconhecidos e ranqueia somente 24 candles 1h fechados com turnover USDT positivo. Não substitui registro de identidade para trading, não promove Top50 marketwide e não realiza GET, VPS, ordens ou alteração do banco. Este checkpoint não prova CI, PR ou merge; verificar SHA/gates 3/3. Detalhes em `docs/J1_AUTOMATIC_CRYPTO_USDT_RESEARCH.md`.


## J1/D280 — observação atual do universo com seletor automático (11/11/2026)

PR #551/D279 integrada SHA `ca174b8dc4b98b95bce7fa967ba3ab3668bb34bf`, Linux 2374, Windows e PAPER sucesso. Novo `scripts.scan_j1_auto_usdt_perps_once` na branch `work/issue-319-j1-auto-usdt-catalog-readonly-cli` permite uma consulta pública GET-only por páginas, explicitamente opt-in e sem armazenamento para aplicar o filtro automático, sem revisar moeda por moeda. Pesquisa não equivale a universo Top50 comprovado, nem operação real; nenhuma VPS acessada para a nova rotina. Evidências CI/merge D280 ainda pendentes neste checkpoint.


## J1/D281 — prova real de filtro automático e união com histórico sem recaptura (11/11/2026)

VPS owner `cia-probe` atualizada via fast-forward até `72f6ec7cfab1ad7f343ee37d850bb4fb7e1417e0`, 15 testes J1 auto aprovados; GET-only real Bybit D280 em 11/11 com 930 linhas/1 página e 370 candidatos provisórios (388 marcadores TradFi, 25 negativos documentados, 108 outros produtos, 39 ambíguos; 1 GET). Sem ordens, gravação ou serviço. D281 na branch `work/issue-319-j1-auto-vps-readonly-reconcile` conecta esses candidatos ao D256 histórico e snapshot D264 já existentes, reutilizando replay SQLite em read-only e explicitando que cruzamento posterior não é Top50 PIT/mercado homologado. Ver `docs/J1_AUTO_USDT_PRIVATE_RECONCILIATION.md`. Gates CI/merge D281 não alegados neste checkpoint.


## J1/D281 — prova real do classificador e ranking fechado retrospectivo (11/11/2026)

**Concluído:** PR #553 integrada, SHA `d4b8afb9b8623a488227d515cf5c2abc7743a602`; CI Linux 2387, Windows e PAPER verdes. VPS owner atualizado no SHA, 20 testes específicos OK. Novo classificador consultou Bybit (1 GET, 930 instrumentos), identificou 370 candidatos técnicos USDT após exclusões; cruzamento read-only com D256/overlay D264 comprovou 370/370 séries de 24 velas históricas, 0 incompletas, ranking retrospectivo Top50 digest `173688c7b6fd8fde0f49ef970b797757e57a1b655f60a7b457adada`. Sem SQL writes, nova coleta histórica, deployment, timer ou ordens. **Não é Top50 atual, PIT de 06/11, nem certificação positiva de cripto.** Uma discrepância de telemetria (classificador puro 0 GET vs wrapper 1 GET) é corrigida no branch `work/issue-319-j1-auto-real-proof-and-get-accounting`, CI pendente. #319/#429 abertas por continuidade atual de dados; #517 encerrada como diligência manual abandonada.


## J1/D283 — agendamento REST finito identificado; substituição recorrente isolada em PR (11/11/2026)

Confirmado diretamente na VPS: timer `cia-j1-rest-hourly.timer` `active/elapsed/enabled`, `NextElapse` vazio, 24 calendários explícitos até 10/11 18:02Z. Template do repo **já** possui agendamento periódico `*-*-* *:02:00 UTC` com serviço M1 idêntico. Journal SQLite owner íntegro: 2 amostras, 100 candles, 26 publicações, 21h de catch-up até próximo UTC, 20 horas sem observação e uma publicação histórica ausente; não extrapolar PIT. Branch `work/issue-429-j1-recurring-rest-timer-preflight` acrescenta auditoria de diff exato + integridade read-only, testes e runbook de rollback para gate de produção; **nenhum timer foi alterado/ativado, nenhum GET ou escrita foi feito**. CI/PR/merge não alegados até evidências. #429 coleta contínua e #319 Top50 atual seguem abertas.


## J1/D284 — coleta REST recorrente efetivamente ativada, primeiro fechamento comprovado (11/11/2026)

**Gargalo 'timer finito sem próxima execução' solucionado na VPS.** PR #555 MERGED SHA `20757b7ca48d11fdacbce0ce5c597b419c8607cb`, Linux/docs **2.397 testes** + Windows/offline SUCCESS (run `43043024350`), PAPER SUCCESS (run `43043024364`). VPS `cia-probe` sincronizada nesse SHA, testes específicos 8+13+10=31 OK. Timer unit alterada **apenas** para `OnCalendar=*-*-* *:02:00 UTC`, serviço M1 `max-assets=2` idêntico, backup privado root preservado. `systemctl`: timer active/waiting/enabled, disparou em 11/11 15:02 UTC, serviço sucesso/exit 0 com **2 GETs, 42 candles novos**, banco agora **142 candles e 27 publicações** (antes 100/26), íntegro. Próxima execução real agendada 16:02 UTC. `historical_unpublished_hours=21` documentado, sem criar PIT retroativo. Sem ordens, custos, novo banco ou mudança de universo Top50; `continuous_collector_verified=false` até múltiplas horas de soak, `marketwide_top50_verified=false`. #429 e #319 abertas; próximo passo operacional: evidência de mais fechamentos consecutivos por auditoria somente leitura, sem novo comando de coleta.


## J2 — hipótese causal de retomada após correção (11/11/2026)

A PR #550 `work/j2-trend-pullback-causal-paper` entrega estratégia B de pesquisa PAPER long/short por tendência EMA medida **antes** da correção, confirmação de rompimento no candle fechado, ATR/volume/cooldown; testes e `docs/J2_TREND_PULLBACK.md`. Correção CI mede a inclinação pré-pullback (o candle de correção invertia o sinal EMA). Esta nota registra escopo, NÃO alega lucro, live trading ou merge; validar CI Linux/Windows/PAPER no head exato, revisar e integrar sem deploy. Próximo: avaliação por replay com custos e OOS de A vs B.


## J1/D285 — capacidade de prova 50 contratos sem modificar coleta recorrente (11/11/2026)

Branch `work/issue-429-j1-rest-fifty-cohort-readonly-audit`: auditor owner-only read-only M1 agora aceita de 1 a 50 membros, preservando default 2, com revalidação completa de SQLite 0700/0600, digest/cursor e cálculo digest-only de ranking de turnover USDT por 24 candles fechados em cada membro. Inclui testes com SQLite real 50×50=2500 velas, sem output de símbolos. A implantação recorrente N2 D284 **continua intocada**. Futura prova N50 será somente uma amostra de pesquisa no novo journal, ainda distinta da pool automática D279/N370 e do Top50 corrente de #319; nenhum efeito em ordens. PR, CI e prova VPS ainda dependem de gates.


## J1/D286 — ranking corrente por 24 candles fechados da pool automática (11/11/2026)

PR #559 em validação: scripts/run_j1_auto_closed24h_rank_once.py consulta todos os candidatos D279 atuais (VPS: 370), 24h fechadas por ativo com Bybit V5 público, scanner de catálogo ANTES e DEPOIS, janela HH:01..HH:15 e GET budget <=450 a 2s de intervalo, sem retries em 10006. Um GET separado mostrou que 44/50 ativos D264 históricos permanecem na pool atual; portanto não reutilizar o frontier antigo para N50. Ranking determinístico Decimal de turnover USDT 24h, somente contagens/digest (nomes públicos sob opt-in) e flags de pesquisa, sem storage/ordens. CI e execução real ainda dependem de gates. Coleta REST N2 em produção permanece intocada; projeto ainda não alega Top50 atual marketwide ou identidade cripto certificada.


## J1/D287 — handoff entre ranking D286 atual e persistência M1 por epoch (11/11/2026)

Branch `work/issue-429-j1-auto-current-ranked-epoch-journal`: fluxo de manifest research-only privado (N50 atual D286, SHA binding de lista ordenada e horários, 48h expiração, sem overwrite), novo runner explícito que injeta seleção ao writer M1 EXISTENTE sem alterar worker, timer e journal N2, e testes de 50×24=1.200 candles +50 incrementais, rotação rejeitada no mesmo DB e zero GET sem opt-in. Relatório D286 para manifesto exige opt-in de símbolos públicos e armazenamento 0600, distinto do job de captura 16:01 UTC agendado sem saída de símbolos. Nenhum deploy ou N50 real confirmado nessa branch; CI/PR/merge ainda sujeitos a evidência. Sem ordens ou Top50 certificado.


D287 acrescenta ainda o subcomando `capture-seal`: captura o ranking corrente D286 e sela a coorte N50 numa única operação owner-only, sem nomes de símbolos no stdout, sem arquivo intermediário obrigatório e sem alterar o serviço REST N2. O job D286 anterior, agendado para 16:01 UTC, segue independente; nenhum manifesto ou journal N50 foi instalado nesta PR.


## J2/J3 — D288 A/B custo-OOS sobre calendário igual (11/11/2026)

Em branch `work/j3-synthetic-a-b-costed-oos-same-folds`, entregue módulo offline de comparação A (compressão/rompimento) versus B (EMA-pullback-retomada) nos **mesmos índices OOS purgados**, sinais sobre prefixos fechados, marks futuros somente depois da decisão e custos hipotéticos parametrizados (fee/slippage/funding) via motor J3 existente. Testes adversariais, explicação de limitações e documentação `docs/J3_AB_COSTED_OOS_D288.md`. **Não declarar CI ou merge até verificação**, nem rentabilidade/backtest real. Coleta N50 owner D287 segue independente na VPS e não é requisito de testes sintéticos; nenhuma ordem, rede ou SQLite novo na D288.


## J1/D289 — N50 real: duas rodadas consecutivas na VPS (11/11/2026)

O job owner de captura/selagem D287 `08212abda5374f658db32b95c25aafff` terminou `exit=0` (21:01–21:13 UTC): catálogo + 24 candles fechados da pool automática, 372 GETs, manifesto privado selado com 50 contratos provisórios atuais, `scope_digest=b022c1211b230e0be4503bed52858954c7deb68c60a03976e5cd74243f1335cb`, sem escrita no SQLite N2. O job isolado `5d207d7d4dd9463594a67abb3958308f` terminou `exit=0`: primeira rodada 22:03 UTC = 50 GETs/1.200 candles; segunda 23:03 UTC = 50 GETs/**50** candles novos, sem refazer 24h. Auditoria SQLite owner read-only: **50 contratos, 1.250 candles, 2 checkpoints UTC consecutivos, PASS**, sem ordens. É **piloto N50 de 2 horas**, não um coletor N50 24/7 instalado nem Top50 elegível certificado. O timer N2 anterior continua independente. Próxima etapa de #429: execução supervisionada e renovação de coorte antes dos 48h, com epochs/journals imutáveis e gate operacional próprio para instalação de serviço permanente.

## J1/D290 — plano de supervisão N50 e renovação em epoch (11/11/2026)

D289 real concluiu 50 contratos/1.250 candles/2 horas consecutivas. D290 adiciona decisão pura `j1_n50_supervision.plan_n50_supervision`, com bloqueios de gaps, falsa PIT, identidade, scope drift, relógio, contagens, replays sem comprovação e reexecução duplicada. Aos 36h exige transição controlada e serializada para novo manifesto/journal (limite D287 de 48h), sem instalar serviço nem sobrepor censo e GETs do coletor. Auditor owner precisa expor binding scope de forma independente antes de habilitar operação real. Ver docs/J1_N50_SUPERVISION_D290.md. PR/CI/merge exigem prova separada.

## J1/D291 — runner seguro da hora N50 (12/11/2026 UTC)

D290 PR #563 merge SHA `a678d0dccb96c390bc0cf1071976b5fff2e63288`; D291 adiciona execução única owner de coleta N50 baseada na decisão read-only D290, seis opt-ins, journal existente auditado ou novo output 0700 vazio, janela UTC e renovação fail-closed antes de 48h. Usa **o mesmo writer D287/M1** em vez de duplicar REST, SQLite ou lock. Branch `work/issue-429-j1-n50-supervised-hourly-runner`; sem timer/release/ordens. PR/CI/merge D291 exigem evidências próprias.


## J1/D292 — correção de retomada após parada parcial (12/11/2026 UTC)

Após o piloto D289 e merge D291, D292 adiciona ao auditor read-only N50 (opt-in, N2 inalterado) reconhecimento de bootstrap e incremento incompletos, permitindo retomar pelo próprio M1 apenas dentro da mesma janela horária e sem fabricação de checkpoints. Adversariais de SQLite/cursor/digest e CI ainda exigidos; nenhum timer, produção, ordem ou ativação introduzidos.

## J1/D293 — lease compartilhada para censo e writer N50 (12/11/2026 UTC)

Implementados ponto de entrada coordenado, flock global, claim owner-only imutável por fechamento e testes adversariais: não executar censo D286/D287 e writer D291/D292 na mesma janela nem trocar destino por retry, manter recuperação D292 de ação idêntica. Escopo OFF por padrão, sem serviço permanente/deploy; o coletor N2 continua independente. J1 #429 exige ainda rotação automática, instalação supervisionada e soak 24h; #319 exige validação de Top50/identidade para negociação.

## J1/D294 — ciclo N50 gerenciado com renovação por epochs (12/11/2026 UTC)

D294 adiciona `managed_n50_tick_once` e CLI owner OFF por padrão: primeira seleção/selagem, atualização incremental horária no manifesto corrente e troca causal para epoch novo a partir de 36h, protegendo a transição com lock/claim D293 e ponteiro owner-only atômico. Testes offline de crash/conflito/retomada/idade e preservação de journals. **Não é N50 24/7 instalado**; nenhum serviço, timer, ordem ou migration. CI/revisão/merge exigidos; J1 #429 precisa ativação operacional com soak real e #319 ainda qualificação independente.

## J1/D295 — pacote de implantação N50 ainda OFF (12/11/2026 UTC)

Após D294 (PR #567 integrada, SHA a verificar no gate), adicionados service/timer systemd N50 inertes com entrada única no gerenciador D294, renderer de owner/paths e preflight que **recusa N50 enquanto N2 timer ou worker estiver ativo**. Não houve instalação ou mudança na VPS. Próximo gate: CI/revisão/merge sem deploy, preparação owner/root/rollback de produção e autorização de release antes de substituir agendamento, seguido de soak real >=24h e rotação causal. Sem ordens reais.


## J1/D296 — validação read-only e correção do gate N2→N50 (12/11/2026 UTC)

Consulta real ao systemd VPS confirmou N2 timer `loaded/active/enabled`, N2 service `loaded/inactive/static`, N50 timer `not-found/inactive`. Corrigido gate D295 para exigir N2 timer tanto `inactive` quanto `disabled` antes de qualquer start N50 (evita dupla execução após reboot); também exige `LoadState=loaded` e service N2 `inactive/static|disabled`. Novos testes adversariais de resultados systemctl. Nada foi instalado, parado, iniciado ou negociado. Status real do N50 24/7 permanece falso.


## J1/D297 — caminho de cutover N2→N50 sem operar manualmente cada hora (12/11/2026 UTC)

VPS N2 auditado pelo proprietário `cia-probe`: SQLite íntegro, 166 velas, 39 checkpoints e 21 horas históricas sem publicações (não fabricar PIT). Worktree N50 separado D296 SHA verificado e 45 testes N50 PASS; raiz 0700 criada sem ativar N50. D297 agrega instalador one-shot de release com preflight N2 owner, pin SHA, escrita de unidades N50, parada reversível de N2 e rollback automático se falha; só aplica com flags explícitas. J1 #429 em aberto até soak real de 24h/renovação, #319 identidade ainda não certificada. Nenhuma operação financeira.

**Aprimoramento D297:** falha explícita do serviço N50 aciona unidade `OnFailure` que desabilita N50 e reabilita N2 sem ordens nem escrita no banco. Ainda falta monitorar falhas silenciosas/ausência de execução para declarar supervisão 24/7.


## J1/D298 — impedimento real de release corrigido em código (12/11/2026 UTC)

D297 PR #570 integrada, backup N2 SQLite owner 0600 verificado, 166 candles/39 publicações. Preflight N50 real foi bloqueado sem alterar systemd: venv Python é symlink oficial e Git root recusa checkout owner. D298 endurece liberação para aceitar somente symlink Python pinado resolvendo para `/usr/bin/python3.12` e faz revisão Git sob `cia-probe`, sem relaxar proteção Git. Gate ainda requer CI/merge, preflight root PASS e rollout reversível; não declarar N50 24/7.


## J1/D299 — coleta N50 agora agendada na VPS; observabilidade sem fabricar PIT (12/11/2026 UTC)

D297/D298 realizaram cutover autorizado com rollback: N50 timer active/enabled, N2 timer inativo/disabled e backup íntegro preservado, zero ordens. D299 adiciona auditor read-only owner de epochs D294, scope D287 e journals M1/D290, retornando contagens reais, lacunas e cobertura dos 24 fechamentos. Código/testes offline não instalam nada. N50 24/7 e rotação continuam **não verificados** até observações reais; #429/#319 abertas.


## J2/D300 — análise descritiva de dados privados N50 (12/11/2026 UTC)

Criada ponte para a primeira observação de mercado real de 24 candles 1h por cada um dos 50 ativos N50, com replay integral da J1, last published checkpoint, manifest/provenance, digests por candle e métricas Decimal: retorno observado, volatilidade/true range, turnover, último rompimento e comparação BTC quando BTC estiver na coorte. Não gera sinais nem ordens, não reutiliza fixtures sintéticas para dados reais. Testes POSIX locais na VPS: 10 PASS no candidato D300; só executar CLI real após primeiro writer N50. Primeira captura automática N50 de 04:01–04:13 UTC consumiu 372 GETs e criou o epoch, sem candles ainda. Monitor de continuidade segue ativo; J1 não encerrada.

D300 QA adicional: 11 testes de tela de pesquisa N50 PASS na VPS após adicionar fixtures numéricas determinísticas de alta/baixa; 2.509 testes completos PASS no worktree anterior sem mudanças de lógica além de testes. Fonte N50 real: 50 membros USDT, BTC referência presente, identidade externa ainda não certificada; primeira publicação horária futura precisa de evidência independente, sem trading.


## J5/D301 — panorama privado mobile para N50 (12/11/2026 UTC)

A partir da ponte J2/D300 (PR #573 integrada, squash SHA `95edb62a52ba2fd0619457371281db3b02df2fd0`), D301 entrega HTML único PT-BR com CSP fechada, cards e tabela responsiva, somente dados de pesquisa N50 auditados, data UTC, contexto BTC e avisos de não-trading. CLI opt-in tríplice pode salvar relatório local owner 0600, nunca publicar. Testes de privacidade, acessibilidade, injeção e modo somente leitura: 10 PASS na VPS candidata. Não é produto web online, não libera ordens e não atesta 24h coletadas.


## J3/D302 — primeira avaliação observacional de 2 horas N50 (12/11/2026 UTC)

Concluída a implementação do estudo owner-only J3 com 50×25 candles consecutivos de uma mesma coorte, seleção fixada apenas por retornos anteriores, marcação posterior t+1h e custos explícitos hipotéticos. **10 testes PASSED** no worktree VPS candidato ca7f513d157673575e6e4b1156afd6d1bc6d4e73. Não é PnL, backtest OOS validado, fill ou sinal. Dados reais precisam de duas publicações; primeiro censo N50 já ocorreu, mas não antecipar outcome.

## J1/D303 — falha do provedor observada no N50; fallback N2 comprovado (12/11/2026 UTC)

Primeiro N50 owner checkpoint: 1.200 candles de 50 contratos, seguido por 3 checkpoints reais até 07 UTC. Às 08:01 UTC, 7 GETs e 6 candles avançados, com `provider_denied_owner_review` no SQLite; `PRAGMA quick_check=ok`, 50 cursores e 1.306 candles no total. N50 terminou exit 65 e acionou OnFailure, deixando timer N50 disabled/inactive e N2 enabled/active. Subtipo exato da resposta do provedor não é reconstituível dos logs já registrados. D303 adiciona telemetria de `failure_category` whitelist M1→D291→D293→D294 para futuras falhas, sem relançar provedor e sem mexer no banco. Homologação 24h e renovação >36h seguem pendentes; #429 continua aberta.


## J1/D304 — forense da falha N50 e preservação dos checkpoints (12/11/2026 UTC)

N50 completou 3 publicações horárias; a quarta falhou após 7 GETs e 6 candles parciais com HALT `provider_denied_owner_review`. Fallback N2 foi confirmado ativo, N50 timer inativo. D304 acrescenta auditor owner-only de journal halted, validando SQLite/cursors/manifesto/PIT sem qualquer GET nem liberação de retomada. Nenhuma conclusão de 24h, continuidade Top50, causa específica HTTP ou rentabilidade.

## J3/D305 — primeira comparação histórica real após HALT (12/11/2026 UTC)

Implementado modo J3 de estudo ex post do arquivo HALT (opt-in e D304 obrigatório), sem recolher dados ou limpar latch. Amostra real de 50 contratos, 25 candles cada e um único horizonte t+1h: marcações líquidas de referência hipotéticas para top5 LONG +US$ 24,72, bottom5 SHORT −US$ 5,19 e todos50 LONG +US$ 13,00 sob 18 bps de custos supostos (US$100 de referência por ativo). **Não é PnL nem backtest OOS**, não comprova trading, liquidação ou previsão; J1 N50 continua parado após fallback N2. Testes CI e merge sem deploy exigidos.

## J1/D306 — resolver N50 diretamente, sem desvio para J2–J5 (12/11/2026 UTC)

Primeiro N50 chegou a 3 horas reais, mas parou em 08:01 UTC (7 GETs, 6 candles). Identificado o 7º contrato HYPEUSDT e comprovado com 2 GETs distintos de diagnóstico que o contrato segue ativo e uma vela fechada pode ser obtida hoje. O erro remoto das 08:01 não foi registrado em subtipo; não atribuir causa sem prova. D306 implementa nova coorte de coleta com D304 forensic gate, mantém antiga SQLite intacta, exige N2 quiescido, altera unit N50 só com release root duplo e preserva rollback N2. Preflight N2 considera 25 lacunas históricas reais após failback em vez de 21 do piloto. J1 permanece aberta até CI/cutover, 24 horas consecutivas e rotação real. Ordens zero.

## J4/D307 — pesquisa de parciais e runner com custos hipotéticos (12/11/2026 UTC)

Sem interromper a observação N50 J1, adicionado módulo puro de marcação financeira sintética de exits parciais, runner e funding assinado, compatível com PRE1–PRE3 e custos J3/PRE2; inclui dedup de fills e controle de causalidade/marca obsoleta. Apenas fixtures, sem rede/ordens/fills reais ou alteração de serviço. J4 #5 segue aberta, sem backtest financeiro aprovado. Evidência: `docs/J4_PARTIAL_COSTED_REPLAY_D307.md`.

## J2/D308 — watchlist descritiva privada de 50 contratos, sem sinais (12/11/2026 UTC)

Composição causal e offline da leitura auditada D300: rompimento do fechamento acima/abaixo dos 23 candles anteriores, retorno relativo ao BTC e intensidade do turnover da barra fechada, com ordenação determinística e no máximo cinco observações por direção. Dados insuficientes/corrompidos recusados, lista de símbolos OFF por padrão e nenhuma ordem, GET, alteração de SQLite ou systemd. Testes adversariais em `tests/test_j2_n50_descriptive_watchlist.py`, contrato em `docs/J2_N50_DESCRIPTIVE_WATCHLIST_D308.md`. CI/revisão/merge a validar; não declarar estratégia validada, alpha, Top50 global nem homologação J1. N50 D306 supervisionado, com 24h/rotação ainda pendentes.

## J1/D309 — testemunho de 24h N50 somente leitura (12/11/2026 UTC)

D309 adiciona `j1_n50_24h_witness.py`, CLI owner-only e testes adversariais: compõe o replay privado D299 (todas as epochs, incluindo HALT forense) com estado read-only de quatro unidades systemd para distinguir 24 PITs fechados reais, janela ainda incompleta, failback N2, serviço falho e falta da última publicação. Nunca declara `continuous_collector_verified=true` apenas por contar 24 candles, nem converte 24h em prova de rotação após 36h ou Top50 crypto-only global. Sem deploy, ordens, GET, mudança de banco/systemd ou credenciais. Contrato em `docs/J1_N50_CLOSED24H_WITNESS_D309.md`; testes e CI/PR a validar antes de merge.

## J5/D310 — apresentação móvel da watchlist D308 (12/11/2026 UTC)

Extensão da página HTML privada J5/D301 para exibir observações determinísticas D308 com BTC/turnover/rompimento, contagens e limite de cinco por sentido. A interface usa a função pura D308 existente, abstém se o relatório não passa no mesmo audit/digest e não mostra lista sem BTC; símbolos privados apenas no HTML salvo com as três flags pré-existentes. Testes regressivos próprios e contrato em `docs/J5_N50_D308_WATCHLIST_MOBILE_D310.md`; CI/revisão/merge a validar. Sem deploy, ordens, serviços novos, banco ou alteração de pesquisa de mercado. J1 #429/#319 seguem abertas.

## J1/D311 — limite Bybit 10006 no writer N50, fallback N2 real (12/11/2026 16:11 UTC)

Incidente confirmado pelo journald: N50 falhou 16:01:12 UTC, exit65, `provider_rate_limit_no_retry`, 4 GETs, 3 candles parciais sem recibo da hora; N50 timer disabled e N2 active/enabled pelo OnFailure. N2 concluiu 16:02:04 UTC em success0 com 2 GETs e 6 candles, coorte de apenas 2 contratos. A janela de 24h N50 e rotação permanecem NÃO homologadas. D311 acrescenta cadência opcional entre GETs reais de 2–12s e usa 8s somente no writer incremental N50, preservando captura de universo N50 e N2 em 2s e **sem retry no 10006**. Correção é apenas código/CI, sem nova recuperação VPS; auditoria forense e gate root necessários antes de qualquer cutover. Detalhes e critérios em `docs/J1_N50_RATE_LIMIT_MITIGATION_D311.md`.

## J1/D312 — preparação de recuperação da nova epoch HALT 10006 (12/11/2026)

Com N50 timer inactive/disabled e N2 active/enabled após o incidente real 16:01 UTC (10006, 4 GETs, 3 parciais), o script D306 anterior (fixo a epoch antiga com 3 PITs/6 parciais) não pode ser reaproveitado. D312 introduz auditoria owner-only da epoch ativa `epoch-1794492000000` via forense D304 e um release root OFF por padrão, SHA e units pinadas, com dupla confirmação apenas após gate produção, novo censo/epoch, preservação do HALT e rollback para N2. Não é deploy, homologação 24h ou permissão de trading. Contrato e testes em `docs/J1_N50_RATE_LIMIT_RECOVERY_D312.md`. Em paralelo, #585 é a rota WS-first para deixar de requisitar ~50 candles REST por hora.

## J1/D314 — escopo dinâmico D287→WebSocket sem lista fixa (12/11/2026 UTC)

Integração pura offline de 50 símbolos USDT perpétuos do manifesto D287 com metadados V5 atuais de catálogo paginado, e ingress GET público opt-in não-root de 1–4 páginas com 10006 sem retry, em um `OfflineReviewedStreamScope` estritamente **provisório** para uso por `bybit_ws_supervisor`, cache e auditoria D313. Valida paginação completa, campos contra TradFi, timestamps, tipo perpétuo, precisão financeira, hashes e todos os 50 membros. Teste ponta a ponta offline gera 50/50 no journal WS e falha fechado em caso incompleto. Código, testes e `docs/J1_N50_WS_DYNAMIC_ADMISSION_D314.md` ainda sujeitos a CI/revisão. Não executado na VPS; N50 continua disabled e fallback N2 ativo, com #585/#429/#319 abertas.

## J1/D315 — ponte N50 WS owner por hora (12/11/2026 UTC, candidato sem release)
A partir de main `d503da20a059be7284ba3b40fa430233ea2c8d91`, branch `work/issue-585-j1-d315-n50-ws-owner-lease` liga admissão de 50 perpétuos D314 ao supervisor WS existente, ao lock owner e à auditoria D313 de 50/50, sem REST/cutover. Testes em fixtures com journal SQLite, ACK, 49/50, drift, lock e controles de tráfego em `tests/test_j1_n50_ws_owner_hour_d315.py`. **Candidato para CI/revisão; não declarar teste final ou merge antes de evidência.** Evidência VPS owner D304 atual: HEAD instalado `75b93b2dc2a0ace537927b55e94292a73466a27f`, stored=1203, published=1, partial=3, integrity=true, sem gaps, sem GET, ordens ou writes pela auditoria. N50 REST failed/disabled; N2 active/enabled. J1 #429/#319 e WS-first #585 abertas; 24h/36h e identity não verificados. Contrato `docs/J1_N50_WS_OWNER_HOUR_D315.md`.

## J1/D316 — cache owner do escopo dinâmico WS (12/11/2026, candidato)
Branch `work/issue-585-j1-d316-ws-dynamic-owner-cache` dependente de D315/PR #589. O D316 grava de forma imutável um único recibo owner 0700/0600 do manifesto D287 mais páginas completas D314, cursor e relógio, com limite 8 MiB, SHA e replay independente do mesmo validador; leitura posterior não faz GET por hora e exige digest da coorte ativa, TTL 48h e hash correto. Testes adversariais de tamper, symlink, DAC, expiração, drift e 50/50 sintético. **Código/PR/CI não equivalem a deploy, feed 24h, N50 global ou ordens.** N50 REST continua OFF após 10006 e N2 ativo até novo gate. Contrato `docs/J1_N50_WS_PRIVATE_CACHE_D316.md`.
