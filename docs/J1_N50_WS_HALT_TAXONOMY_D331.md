# J1/D331 — razões confiáveis do halt WS N50 após 42 candles

## Problema real, não hipótese

Em **13/11/2026 13:59:31–14:00:01 UTC**, o primeiro lease depois do recovery D329 recebeu ACK=1 e 673 frames, e o ingestor registrou **42** eventos `confirm=true` com compatibilidade de timestamp pós-fechamento (`accepted_postclose_trade_clock=42`, `closed_events_appended_to_ws_journal=42`). A execução terminou `exit 65` com `failure_category=invalid_or_gapped_market_data`, sem chegar ao atestador D313 (`confirmed_contracts=0` e `missing_contracts=50` são campos iniciais nesse ramo, **não** contagem real de membros ausentes). `http_gets=0` e `orders_sent=false`.

A contingência `cia-j1-n50-ws-fallback.service` concluiu às **14:00:04 UTC**, desabilitou ambos timers WS e restaurou N2. O serviço REST N2 terminou **14:02:04 UTC** em success0. Dados imutáveis WS podem estar no journal; nunca removê-los sem auditoria.

A categoria genérica era causada pela lista incompleta de literais internos do `bybit_ws_supervisor._safe_ws_failure_class`. **Não sabemos** qual erro efetivo interrompeu a 43ª tentativa (ou outro frame). Não há payload privado gravado nem prova de oito símbolos especificamente falhos. A documentação oficial Bybit distingue `confirm`, `start/end`, `ts` e `timestamp`; a mudança D329 resolveu parte da incompatibilidade e continua sem autorização para sinais. Referência: https://bybit-exchange.github.io/docs/v5/websocket/public/kline .

## Mudança D331 — diagnóstico preciso sem relaxar qualidade

A classificação de falhas do supervisor ganha somente **mensagens exatas de erros do nosso código**. Os grupos agregados são:

| Classe | O que evidencia no próximo lease |
| --- | --- |
| `ws_journal_closed_replay_conflict` | mesma chave símbolo/hora com bytes divergentes; não sobrescrever |
| `ws_journal_backfill_or_registry_drift`, `ws_journal_gap_limit` | evento regressivo ou lacuna além do limite explícito |
| `ws_journal_predecessor_corrupt`, `ws_journal_payload_integrity_invalid` | journal/recibo anterior não íntegro |
| `ws_journal_schema_invalid`, `ws_journal_write_invalid`, `ws_journal_row_limit` | esquema, SQLite ou orçamento |
| `ws_closed_ohlcv_invalid`, `ws_closed_ohlcv_type_invalid` | financeiro inválido ou preço/OHLC incoerente |
| `ws_scope_member_invalid`, `ws_scope_metadata_stale`, `ws_closed_window_invalid` | identidade/escopo/janela causal |
| `invalid_or_gapped_market_data` | erro não previsto; **não inventar** subcausa |

O mapeamento exige correspondência **exata**; nunca serializa `str(error)` ou traceback e não usa prefixo genérico. Não contém símbolos, horários de frames, preços, paths, chaves nem credenciais. A nova classificação **não altera** assinatura do journal, `append`, tolerância de timestamp, lock, limites de frames, requerimento 50/50, onFailure N2 ou decisão de negociação. A regra para JSON/candle inválido continua fail-closed.

## Evidência e regressões

`tests/test_j1_n50_ws_halt_taxonomy_d331.py` usa a fonte de fixtures D329 e supervisor de 50 tópicos:

- 42 mensagens válidas seguidas por um **replay divergente**: 42 linhas preservadas, saída fail-closed, motivo distinto, sem vazamento;
- 42 mensagens válidas seguidas por OHLC inconsistente: motivo diferente, sem gravação da inválida;
- 50 mensagens íntegras: 50/50 local, sem autorização de ordem/sinal ou de 24h;
- mensagens adversariais contendo símbolos/segredos em texto **não allowlisted** retornam apenas a categoria genérica;
- parser offline estrito permanece inalterado.

`tests/test_j1_n50_ws_recovery_release_d331.py` verifica shell, SHA antigo, preflight, cinco suites locais e rollback N2. Exigir CI Linux/docs, Windows/offline e PAPER/mobile no HEAD revisado com regressões D313–D329, depois merge sem deploy.

## Gate VPS (separado; não executado nesta PR)

`deploy/vps/recover_j1_n50_ws_d331_once.sh` é **apenas preparado**, exige root SSH explícito no host aprovado, `OLD_SHA=a2fa30ad499e97f3cb836c5a7fd66eb9f43ae1b1` instalado e checkout limpo, serviço WS failed, timers WS/rotação disabled, N2 active/enabled, NTP e ponteiro D321/cache íntegros. Busca **um** SHA novo revisado, roda testes offline no Python real da VPS **antes** de desligar N2, reutiliza unidades existentes com rollback. Não faz bootstrap D322, novos 372 GET, manipulação REST, migração SQLite, investigação de símbolos ou ordem financeira.

**Próxima prova:** após um único futuro lease real de D331, ler somente status/failure_category/contadores sanitizados; discriminar conflito de replay, lacuna, financeiro ou escopo e corrigir a causa real em um bloco, não conjecturas. Se 50/50, preservar estado e seguir D323 24 horas, rotação real >=36h e #319. Caso contrário N2 deve permanecer ativo. Nenhum sinal ou ordem autorizado.
