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

**WU5 / issue #19 permanece ABERTA**: código e regressões offline concluídos; smoke com dados reais da API pública, disponibilidade por ambiente/região e evidência de cobertura ainda não foram verificados. J1 **não está homologada**.

## Não implementado/não comprovado
Estratégias validadas, backtest de retorno líquido, gestão de posições real, interface PT-BR, feed live homologado, histórico ponto-no-tempo profundo, serviço contínuo VPS, backup de dados ou operações reais.

## Limites
Custo adicional autorizado R$ 0, repositório PÚBLICO sem segredos; nenhuma API paga, ordem real, release ou migration sensível. Consultar docs/OPERATIONAL_STATE.md e GitHub ao vivo antes da próxima ação.
