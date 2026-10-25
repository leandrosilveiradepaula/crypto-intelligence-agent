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

**J1/WU32 #107 — ferramenta integrada, acesso OKX bloqueado:** merge `9b66a359d1fa1d7a3ce83f66e1e002aa825de354`, CI PR #40236541641 SUCCESS (626 testes), CI pós-merge #40236593184 SUCCESS. Primeiro owner-run #40236605217 FALHOU antes de qualquer GET com `ModuleNotFoundError` no entrypoint. Correção PR #109 integrada; segundo run real #40236734900 encontrou acesso/rate restriction após 1 GET, sem candles; não repetir nem contornar. Dados de mercado de uso pessoal, não publicação; nenhuma prova de identidade, histórico Top50 ou permissão comercial. Docs D57; issues J1 #2/#32/#36/#48 abertas.

**J1/WU32 #107 — probe executado, acesso OKX BLOQUEADO:** PR #109 integrada `2a7b3de97e1af1224cc78168f7b8e782067f420b`, CI #40236692028 SUCCESS (**627 testes offline**). Segundo owner-run #40236734900/job #121299805518 tentou 1 GET de instrumentos, retornou `access_or_rate_restricted`, não executou GET de candles; 0 candles, 0 ordens, direitos/Top50 false. **Sem retentativa ou contorno**.
**J1/WU33 #110 — registro BTC/ETH real de pesquisa em validação:** duas referências externas de identidade por ativo, revisão técnica assistida por IA, hash SHA256 e vigência point-in-time; ainda **não** há Top50 real, feeds canônicos, autorização comercial nem J1 homologada.

## Riscos/pendências
A Binance respondeu HTTP451 no runner gratuito, sem candles. Kraken respondeu HTTP200 para instrumentos, tickers e 3 candles BTC (amostra pontual), com `volumeQuote` em USD, porém inclui instrumentos tokenizados não cripto (`PF_AAPLXUSD`). **213 prefixos PI_/PF_ não equivalem a 213 criptoativos elegíveis.** Falta classificação confiável, precisão das unidades, fechamento intrabar, cobertura histórica e homologação em ambiente operacional. J1 continua **ABERTA**, sem estratégias validadas, trades ou produção.

Restrições: custo R$0, repo público sem segredos, nenhum trade real, deploy, gasto ou migration sensível. Ler OPERATIONAL_STATE.md e verificar GitHub vivo antes de agir.
