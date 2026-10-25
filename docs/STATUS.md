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

**WU8 — issue #28 em desenvolvimento** na branch `research/j1-kraken-asset-taxonomy`. Reutiliza probe de 1 GET para medir categorias/flags `tradfi`/tags, com workflow sob comentário do proprietário. Nenhum resultado WU8 live/PR/CI/merge deve ser presumido antes de verificá-los.

## Riscos/pendências
A Binance respondeu HTTP451 no runner gratuito, sem candles. Kraken respondeu HTTP200 para instrumentos, tickers e 3 candles BTC (amostra pontual), com `volumeQuote` em USD, porém inclui instrumentos tokenizados não cripto (`PF_AAPLXUSD`). **213 prefixos PI_/PF_ não equivalem a 213 criptoativos elegíveis.** Falta classificação confiável, precisão das unidades, fechamento intrabar, cobertura histórica e homologação em ambiente operacional. J1 continua **ABERTA**, sem estratégias validadas, trades ou produção.

Restrições: custo R$0, repo público sem segredos, nenhum trade real, deploy, gasto ou migration sensível. Ler OPERATIONAL_STATE.md e verificar GitHub vivo antes de agir.
