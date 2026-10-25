# Status — Crypto Intelligence Agent

## J0 — Fundação documental
- Issue #1 encerrada. PRs #10 e #11 integradas, com CI documental aprovada.
- Decisões, arquitetura candidata, regras de autonomia, jornadas, critérios de aceite e contrato de dados versionados.

## J1 — Dados, EM ANDAMENTO
- WU1 (#9) concluída pela PR #12 e integrada no commit `c9bf70c3f8429b1474a9b68cc1aeb0a3cd209193`.
- CI antes do merge: SUCCESS, run 40159360299 no SHA `d477388d26a9859544f1e7c24206855b23c95b04`: 17 testes offline, compileall e 10 documentos.
- CI pós-merge: SUCCESS, run 40159403768 no SHA integrado.
- Entregue: adaptador de futuros público somente leitura, contratos tipados, validação temporal, OHLC, volume e fixtures.
- WU2 (#13) em revisão na PR #14: SQLite local desacoplado, backfill paginado, continuidade verificada dos checkpoints, rollback atômico, replay e relatório de qualidade offline. Integração e CI final dependem de conferência do SHA atual.
- Ainda NÃO entregue: operação contínua, fonte histórica ponto-no-tempo independente, sinais, pesquisa financeira ou implantação. A J1 não está concluída.

## Restrições
Custo adicional R$0. Repositório público por decisão do Product Owner. Sem negociação real, credenciais de ordens, APIs pagas ou deploy nesta fase.

Fonte operacional mais específica: docs/OPERATIONAL_STATE.md. Conferir GitHub vivo antes de qualquer ação.
