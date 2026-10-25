# Status — Crypto Intelligence Agent

## J0 — Fundação documental concluída
- Issue #1 encerrada; PRs #10 e #11 integradas. Regras de autonomia, arquitetura, produto, validação, jornadas e contratos versionados.

## J1 — Dados, EM ANDAMENTO
- WU1, issue #9: PR #12 integrada, commit `c9bf70c3f8429b1474a9b68cc1aeb0a3cd209193`. Adaptador público read-only, contratos de dados, validação temporal e fixtures. CI pós-merge aprovada.
- WU2, issue #13: PR #14 integrada, commit `f3567eb063f0b7cfeffe40169ba0b8e9fce1da96`. Backfill paginado, SQLite local transacional, checkpoints contínuos verificáveis, imutabilidade de contratos, replays, snapshots, qualidade, testes de falha e documentação.
- CI da PR #14: run 40168249829 SUCCESS, HEAD `9ac750ff3f92d56189ce55a670391292d3716ec2`, com 42 testes offline, compileall e 10 documentos.
- CI pós-merge PR #14: run 40168285079 SUCCESS no commit `f3567eb063f0b7cfeffe40169ba0b8e9fce1da96`; 42 testes offline.
- J1/WU3, issue #15: PR #16 integrada no commit `9631e4445678bc4c7067964b537da924b5b89a0b`. CLI offline por padrão, fixtures sintéticas, auditoria SQLite e testes ponta a ponta. CI pós-merge run 40188838338 SUCCESS: 58 testes offline e 10 documentos.
- J1 ainda NÃO validada em operação contínua. Cobertura histórica externa/ponto-no-tempo, retenção, monitoramento, riscos de exchange e desempenho de sistema continuam pendentes.

## Restrições permanentes
Custo adicional autorizado: R$0. GitHub público; sem segredos ou bancos de dados capturados no repositório. Nenhum deploy, ordem real, backtest validado ou alegação de lucro.
Fonte operacional: docs/OPERATIONAL_STATE.md. Verificar GitHub vivo antes de agir.

- J1/WU4, issue #17: verificação de relógio UTC público e gate fail-closed iniciados diretamente na branch `feat/j1-wu4-exchange-clock`. Não declarar CI/PR/merge concluídos até checagem em GitHub. Dados de produção, retenção e homologação de exchange permanecem pendentes.
