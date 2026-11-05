# J1/OPS27 — auditor causal de rollover WS em quarentena (issue #474)

## Fatos, hipótese e decisão

A prova real owner-only na VPS em 04/11/2026, das 03:45 às 04:00:01 UTC, entregou `29` frames WebSocket e **um** GET REST público da Bybit, com `fields_compared=6`, `fields_equal=6`, `probe_completed_unverified`. Não houve ordens, gravação de candles nem autenticação independente. O timer foi desativado e os três markers de uso único foram preservados. Este único candle corrobora **valores do mesmo provedor**, não liberação da ingestão de mercado inteira.

Contrato Bybit V5 público: https://bybit-exchange.github.io/docs/v5/websocket/public/kline . `start` é abertura do intervalo, `end` é o último milissegundo desse intervalo, `timestamp` é o horário do último negócio, `ts` é horário de geração da mensagem WebSocket, e `confirm` indica fechamento. A documentação não afirma que se pode remapear livremente `timestamp>end` ou usar `ts` como horário do negócio. A observação OPS18/20 de `timestamp>end` (50 frames 2..1000ms, 2 frames 1001..5000ms) e o 6/6 de OPS26 são fatos **distintos**; o relatório de OPS26 não transporta os valores ou clocks brutos. Não inferir equivalência temporal ou autorização a partir deles.

**D233 — proposta técnica conservadora:** até comprovar causalidade de cada linha e proveniência sob contrato revisado, `timestamp>end` permanece **em quarentena** e o parser persistente `parse_offline_confirmed_kline` continua estrito. O status `causal_gate_same_venue_match_quarantined` nunca implica `canonical_ohlcv_approved`, `ws_candle_approved`, `source_authenticated`, `marketwide_top50_verified` ou `continuous_collector_authorized`. Abrir a admissibilidade canônica exige decisão versionada específica, teste causal fora da amostra e gate de produto aplicável; o código OPS27 não altera o comportamento de produção.

## Implementação offline

`crypto_intelligence_agent/j1_ws_close_causal_gate.py` expõe `audit_causal_rollover_offline(events, expected_topic, ack_verified, reference)`. É uma função determinística que consome **somente** tuplas de frames/horários já fornecidos: até 64 frames, de 1 a 8 linhas por frame, um tópico fixo `kline.60.*USDT`, e afirmação explícita do caller de ACK previamente validado. *O próprio parâmetro ACK não certifica um handshake de rede.* A auditoria valida grid de 1h UTC, receipt/server, `confirm` booleano, campos Decimais, OHLC, intervalo temporal, tópico e ordem de recepção para **todas** as linhas. Não admite seleção parcial de frame: qualquer anomalia invalida todo relatório, com contagens zeradas. Não permite segundo close nem replay da mesma janela.

Para linhas estruturalmente válidas, a função classifica `timestamp-end` por 5 bandas disjuntas, separadas entre `confirm=true` e `confirm=false`: dentro do intervalo, +1ms, +2..1000ms, +1001..5000ms, e acima de 5000ms. Nenhum símbolo, data/hora absoluta, OHLCV, caminho, dado de rede ou objeto original aparece em `sanitized_report()`. A unidade somente conta excedentes; não normaliza timestamps.

Opcionalmente, um único close anômalo pode ser comparado com página REST de pesquisa já validada em esquema usando o auditor OPS21 (se fornecida pelo chamador), sem network. Concordância 6/6 é **quarentena não autorizadora**; divergência e referência inválida continuam bloqueadas. A função não abre SQLite, não emite requests nem altera o estado persistente. O status `causal_gate_strict_stamp_observed_unverified` também não autoriza coleta 24/7.

## Gates OPS1 #429 — próximos passos operacionais

1. **Offline:** rodar `test_j1_ws_close_causal_gate.py`, `test_j1_ws_rest_offline_corroboration.py`, `test_j1_bybit_ws_offline_pipeline.py`, `test_j1_ws_supervisor.py` e `test_j1_ws_service.py`; CI Linux/docs, Windows/offline e Chrome/PAPER antes e após merge. A prova WS×REST única já cumpriu sua finalidade; não a repetir.
2. **Pré-voo VPS read-only:** verificar checkout SHA exato, NTP, região, limites, quotas, estado do diretório de pesquisa separado e ausência de escritores duplicados. Não ativar serviço de coleta contínua durante a OPS27.
3. **Piloto finito de múltiplos contratos:** exigir gate explícito do proprietário e confirmação do registro revisado vigente; observar assinaturas, ACK, `confirm=true`, clocks, integridade, renovação de escopo e saúde sem promover candles em quarentena. Falha de integridade deve interromper sem restart automático.
4. **Apenas após decisão de admissibilidade e critérios de cobertura:** considerar serviço supervisionado por 24h, com aquisição de 24 fechamentos reais por membro, auditoria de continuidade, gaps e ausência de lookahead. O template `cia-j1-ws-owner.service` continua OFF; retorno 66 de integridade não deve acionar loop de restart.
5. **Universo #319:** verificar escopo marketwide elegível independentemente antes de alegar Top50; um registry de 52 candidatos e ranking amostral não satisfazem esse gate.

## Evidência e lacunas

O histórico real de 6/6 está registrado nas issues #464/#468/#429; a biblioteca OPS27 utiliza fixtures sintéticas e não preserva WS/REST reais. Portanto o relatório não demonstra rentabilidade, marketwide, direitos, origem autenticada, recuperação de lacunas, serviço ativo nem coleta contínua. Nenhuma instalação, ordem ou nova execução de rede foi autorizada por esta implementação.


## Evolução D238 — OPS32 (05/11/2026)

A OPS31 #482 confirmou na VPS 2/2 fechamentos únicos com `timestamp>end` (229 frames) e encerrou o timer sem retries, sem REST ou escritos. O diagnóstico D233 continua sendo um **veto** à ingestão WS Bybit, não um incentivo a normalizar o relógio. A OPS32 #484 adicionou a matriz de fontes/selector offline `j1_causal_source_decision.py` e testes Bybit/Binance em `docs/J1_OPS32_CAUSAL_SOURCE_DECISION.md`. Nenhuma admissibilidade do parser persistente foi alterada, e o Top50/24h permanece bloqueado.
