# J1/OPS2 — Readiness de retomada REST somente leitura

Contexto: [issue #540](https://github.com/leandrosilveiradepaula/crypto-intelligence-agent/issues/540). Janela finita aprovada: 24/24 sucessos, 100 velas e 26 checkpoints para DOIS contratos de pesquisa. O timer na VPS está elapsed, sem próxima execução. Isso não prova Top50 elegível, dados para sinais, nem operação 24/7.

## Entrega

O módulo `crypto_intelligence_agent/j1_rest_resume_readiness.py` inspeciona somente o banco REST privado existente `j1-rest-hourly-research.sqlite` via SQLite mode=ro/query_only. Reusa `_strict_owner` e `_validate_cursor` do M1 para validar owner, integridade, cursores e digests dos candles armazenados. Inspeciona scope, número de contratos, checkpoints consecutivos REALMENTE publicados, horários de observação +1m..+15m e latch. A primeira publicação pode ser no fechamento inicial ou no fechamento seguinte; nenhuma hora ausente é inventada. O total esperado de candles depende do cursor e do escopo inicial, não da mera contagem de checkpoints.

Os estados são `no_gap` (delta entre 0 e 1h), `catchup_with_unobserved_hours_requires_review` (delta de 2..48h), `catchup_exceeds_48h_blocked` (49h ou mais), `halted_owner_review`, `clock_before_last_publication` e `journal_unavailable_or_integrity_blocked`. A saída nunca afirma fonte autenticada, Top50, continuidade ou permissão de ordens. Em todos os cenários, `activation_authorized=false`, `continuous_collector_verified=false`, `orders_sent=false`, `network_requests=0` e `database_mutation_statements=0`. Um status no_gap NÃO libera a coleta e não significa que esteja dentro da janela de publicação.

## Execução somente diagnóstica sob gate separado

A execução opcional requer checkout SHA conferido, usuário não root `cia-probe`, diretório existente 0700 e arquivo 0600. Não está exposta pela API MCP financeira, que permanece limitada às três auditorias fixas das 24 rodadas. Não há reinício, timer enable, novos GETs, escrita ou troca de SQLite.

```bash
cd /home/cia-probe/agent/repo
/home/cia-probe/agent/ws-venv/bin/python -m scripts.audit_j1_rest_resume_readiness --output-directory /home/cia-probe/agent/j1-rest-m3-20261109/canary --allow-private-readonly-audit
```

**Bloqueios remanescentes:** a coleta permanente #429 necessita política para gaps, renovação causal e serviço supervisionado; o universo de 50 elegíveis e identidade cripto #319 ainda não foi comprovado. Não ampliar o limite de 48h, reinstalar timer, recriar banco ou liberar operação real. Este bloco é diagnóstico offline com testes, não implantação.

## Validação

Fixtures com 100 candles e 26 checkpoints para dois contratos, alternativa de 98 candles, delta 1/6/48/49h, fronteiras UTC HH:01/HH:15, dados alterados, halt, symlinks, owner e nenhuma rede. CI Linux/docs, Windows/offline e Chrome/PAPER em SHA revisado.

## Correção de causalidade: publicação ausente no catch-up inicial
A prova real J1 #429 registra primeiro timer em 19:02 UTC com quatro candles novos após o canário: o worker cobriu as horas 18:00 e 19:00 para cada um dos dois contratos, mas publicou somente o checkpoint da rodada 19:00. O journal possui 100 candles íntegros e 26 publicações, entre as quais existe uma hora intermediária sem `published_hour`. **Isso não é gap em candles e não pode ser corrigido inventando uma publicação retroativa.** A auditoria aceita sequência monotônica de checkpoints efetivos, conta separadamente `historical_unpublished_hours` e marca `historical_checkpoint_gaps_present=true`. Se o histórico é íntegro e não existe atraso atual, devolve `historical_checkpoint_gaps_require_review`, nunca `no_gap`. Mesmo com candles completos, uma ausência de PIT histórico exige revisão de operações e impede qualquer ativação automática.
