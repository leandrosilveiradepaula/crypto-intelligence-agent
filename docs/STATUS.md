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

**WU12 #36 aberta, diagnóstico parcialmente executado:** PR #37 integrada no SHA `b607e2f32c5df8144790e58471133fb4fb9559a0`; CI pós-merge run 40201054020 SUCCESS (**163 testes offline + 11 docs**). Primeiro owner-run [40201172859](https://github.com/leandrosilveiradepaula/crypto-intelligence-agent/actions/runs/40201172859) em 25/10/2026 14:12:51 UTC: chart GET HTTP200 (~144ms), porém `invalid_chart_or_insufficient_data`; **somente 1 GET** realizado, sem ticker nem sumário financeiro. `unit_proof=false`. Branch de correção `fix/j1-volume-probe-structural-diagnostics` amplia somente o resumo estrutural sanitizado para discernir incompatibilidade sem salvar dados brutos. Nova execução live ainda não comprovada.

## Riscos/pendências
A Binance respondeu HTTP451 no runner gratuito, sem candles. Kraken respondeu HTTP200 para instrumentos, tickers e 3 candles BTC (amostra pontual), com `volumeQuote` em USD, porém inclui instrumentos tokenizados não cripto (`PF_AAPLXUSD`). **213 prefixos PI_/PF_ não equivalem a 213 criptoativos elegíveis.** Falta classificação confiável, precisão das unidades, fechamento intrabar, cobertura histórica e homologação em ambiente operacional. J1 continua **ABERTA**, sem estratégias validadas, trades ou produção.

Restrições: custo R$0, repo público sem segredos, nenhum trade real, deploy, gasto ou migration sensível. Ler OPERATIONAL_STATE.md e verificar GitHub vivo antes de agir.
