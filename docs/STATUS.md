# STATUS — Crypto Intelligence Agent

## J0 — Fundação documental concluída
Issue #1 fechada, PRs #10 e #11 integradas; requisitos, decisões, arquitetura, jornadas e autonomia versionados.

## J1 — Dados (épica #2 ABERTA)
| Work unit | Issue / PR | SHA de integração | Evidência |
| --- | --- | --- | --- |
| WU1 — adaptador público read-only e contratos | #9 / #12 | `c9bf70c3f8429b1474a9b68cc1aeb0a3cd209193` | testes e CI aprovados |
| WU2 — backfill/SQLite/checkpoints | #13 / #14 | `f3567eb063f0b7cfeffe40169ba0b8e9fce1da96` | 42 testes offline |
| WU3 — pipeline offline/CLI/auditoria | #15 / #16 | `9631e4445678bc4c7067964b537da924b5b89a0b` | run 40188838338 SUCCESS, 58 testes |
| WU4 — relógio remoto/gate temporal | #17 / #18 | `8fc2f75460e93ef898ae14e3c48ef0348692c857` | run 40189235249 SUCCESS, 65 testes |
| WU5 — conformance HTTP e Retry-After (PARCIAL) | #19 / #20 | `cddfc2535aac7c3b7ae9bc04fea160419344ee7f` | run 40189603458 SUCCESS, 78 testes |

**WU5 / issue #19 permanece ABERTA:** a PR #21 integrou o workflow owner-only de smoke GET (commit `09617e0197c250e3b13c7486a60067791ed41a52`, 81 testes offline). O único smoke real, run [40197499250](https://github.com/leandrosilveiradepaula/crypto-intelligence-agent/actions/runs/40197499250), recebeu HTTP **451** na rota inicial de horário público da Binance. Zero candles reais capturados; causa exata não confirmada. A correção HTTP 451 foi integrada pela PR #22 no commit `32c63d0beccdf4734cf06d0f37d04f9ae833fc1f`, CI pós-merge SUCCESS com 81 testes offline. J1 **não homologada**.

## Não implementado/não comprovado
Estratégias validadas, backtest de retorno líquido, gestão de posições real, interface PT-BR, feed live homologado, histórico ponto-no-tempo profundo, serviço contínuo VPS, backup de dados ou operações reais.

## Limites
Custo adicional autorizado R$ 0, repositório PÚBLICO sem segredos; nenhuma API paga, ordem real, release ou migration sensível. Consultar docs/OPERATIONAL_STATE.md e GitHub ao vivo antes da próxima ação.


- **WU6 — issue #23, concluída:** PR #24 integrada, SHA `76490ac8790138642f34de710c5f2e4bb2cf3d09`; GitHub run [40198042787](https://github.com/leandrosilveiradepaula/crypto-intelligence-agent/actions/runs/40198042787) em 25/10/2026 13:32:08Z retornou **HTTP 200**, 231 instrumentos, 213 candidatos PI_/PF_ por heurística; há ativos tokenizados não cripto (ex. PF_AAPLXUSD), portanto nenhum Top50 cripto foi confirmado.
- **WU7 — issue #25, EM DESENVOLVIMENTO:** branch `research/j1-kraken-market-conformance`, até três GET públicos independentes para esquema de instrumentos, tickers/volume e candles de BTC. Não presumir PR/CI/run ou elegibilidade final antes das respectivas evidências.

- WU7 primeira execução de conformance: [run 40198556326](https://github.com/leandrosilveiradepaula/crypto-intelligence-agent/actions/runs/40198556326) falhou na importação do script `ModuleNotFoundError`, antes de qualquer GET. Correção de entrypoint preparada em branch `fix/j1-kraken-probe-module-entry`, sem presumir CI/merge ainda.
