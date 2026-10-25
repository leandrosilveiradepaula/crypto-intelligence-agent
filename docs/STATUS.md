# Status — Crypto Intelligence Agent

## J0 — Fundação documental concluída
Issues e documentos oficiais estão versionados. Issue #1 encerrada; PRs #10 e #11 integradas.

## J1 — Dados (épica #2, EM ANDAMENTO)
- **WU1 — #9/PR #12 concluída:** adaptador público read-only, contratos Decimal/UTC-ms, candles fechados e fixtures; merge `c9bf70c3f8429b1474a9b68cc1aeb0a3cd209193`.
- **WU2 — #13/PR #14 concluída:** armazenamento SQLite de referência, backfill paginado, checkpoints transacionais e relatório de qualidade; merge `f3567eb063f0b7cfeffe40169ba0b8e9fce1da96`. CI pós-merge 42 testes offline.
- **WU3 — #15/PR #16 concluída:** CLI offline por padrão, transporte sintético sem rede, pipeline de múltiplos símbolos e auditoria de endpoints/status no SQLite; merge `9631e4445678bc4c7067964b537da924b5b89a0b`. CI pós-merge run 40188838338 SUCCESS, 58 testes offline.
- **WU4 — #17/PR #18 concluída:** consulta pública de relógio de servidor, validação de desvio e incerteza por RTT antes da coleta, teste de clock recuando; merge `8fc2f75460e93ef898ae14e3c48ef0348692c857`. CI pós-merge run 40189235249 SUCCESS, 65 testes offline, compilação e 10 documentos.
- **WU5 — #19 em implementação direta:** branch `feat/j1-wu5-public-api-conformance`, com classification de erros 403/418, proteção 429/Retry-After e regressões de payloads públicos offline. Revisão/CI/merge ainda dependem de validação do SHA exato; evidência de feed live continua PENDENTE.

## Não comprovado
API live funcionando no ambiente final, histórico de universo ponto-no-tempo profundo, retenção/backups, serviço contínuo em VPS, estratégias rentáveis, UI e ordens reais. **J1 não está homologada.**

## Restrições
Custo adicional R$0; repositório público sem credenciais/dados privados, sem trades automáticos, sem implantação ou migration de produção. Para próximo passo: docs/OPERATIONAL_STATE.md. Confirmar HEAD e CI vivos no GitHub.
