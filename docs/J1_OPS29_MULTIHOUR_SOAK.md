# J1/OPS29 — prova offline de continuidade WS em 30 horas (#478)

## Escopo e limites

A OPS29 complementa a OPS10 e a OPS28: em vez de declarar continuidade com dois checkpoints isolados, exige uma cadeia **transitiva** de pelo menos sete fechamentos de hora, com os mesmos contratos PIT, uma auditoria 24h completa a cada decisão, uma lease finita e ACK por hora e sem lacunas. Tudo é executado com fake clocks e sessões de WebSocket **injetadas**, usando apenas um novo SQLite sintético em diretório temporário nos testes. Nenhuma rede Bybit, REST GET, daemon, migração, ordem real ou dado de usuário é acessado.

A referência de teste percorre 30 horas fechadas para dois membros da fixture revisada: as primeiras 24 aquecem a janela 24h e as sete decisões de horas 24..30 criam sete checkpoints consecutivos. Cada checkpoint deriva da auditoria real do journal de fixture com digest, PIT, ranking causal e verificação de 24 horários fechados por membro. A auditoria adicional `j1_ws_multihour_soak.audit_ws_multihour_soak` verifica **todos** os elos com `compare_closed_hours`, cardinalidade/identidade de escopo, cronologia, ACK da sessão, estado de conclusão do supervisor e exatamente um evento novo por membro na hora. Replay idempotente jamais equivale a uma hora nova.

## Cenários adversariais obrigatórios

- Rollover normal com 2 membros x 30h de confirmação, 60 candles sintéticos, 7 checkpoints;
- Desconexão de transporte seguida de reconexão delimitada e ACK independente da nova sessão;
- Descarte de frame `confirm=true` antes do ACK; o candle ausente permanece ausente sem retro-promoção;
- Missing hour ou missing member, falha de integridade, `timestamp>end`, ACK incorreto, frame malformado;
- Replay idempotente sem acrescentar horas e conflito OHLCV do mesmo candle;
- Mudança PIT de fingerprint, salto/reversão UTC, digest ausente, número errado de contratos, uso de input não tipado e excedente do orçamento de 72 checkpoints.

Cada caso inválido retorna `local_multihour_soak_abstain` **com contagens zeradas**, sem divulgar prefixos parcialmente aprovados. Apenas a cadeia integral retorna `local_multihour_soak_consistent_unverified`: isso significa que **a fixture** é autoconsistente, não que o WebSocket real entregou 30h na VPS.

## Proteções invariantes

O auditor é puro e não grava SQLite; quem grava é apenas o pipeline de fixture testado, em arquivo temporário. O relatório exporta apenas contagens agregadas e estados fixos, nunca símbolos, timestamps absolutos, valores ou paths privados. Os flags `source_authenticated`, `marketwide_top50_verified`, `continuous_collector_authorized`, `worker_running_verified`, `canonical_ohlcv_approved`, `live_trading_authorized` permanecem sempre falsos.

A D235 **não** altera a D233 (stamp post-end em quarentena), D234 (não promover pré-ACK), nem o parser da ingestão real, a SQLite REST EXIT5, o estado de systemd e a elegibilidade Top50 #319. Os critérios reais da OPS1 #429 ainda exigem piloto finito live com controle de recursos, decisões PIT e validação causal de candles antes de ativar 24h; nenhuma CI substitui esse gate.

## Evidências versionadas

Comando de regressão focal: `python -m unittest discover -s tests -p test_j1_ws_multihour_soak.py -q`. Executar também `test_j1_ws_supervisor.py`, `test_j1_ws_hourly_continuity.py`, `test_j1_bybit_ws_offline_pipeline.py`, `test_j1_ws_close_causal_gate.py` e `test_j1_ws_service.py`; CI Linux/docs, Windows/offline, Chrome/PAPER no SHA head e pós-merge. Não registrar essas evidências como concluídas até execução efetiva. Uma PR verde não prova conexão viva, 24h reais, lucro, cobertura 50 global ou autorização para envio de ordens.
