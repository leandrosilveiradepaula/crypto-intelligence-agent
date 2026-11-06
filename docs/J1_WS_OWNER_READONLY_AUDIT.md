# J1/OPS1 D247 - auditoria somente leitura do journal WebSocket privado

## Problema
As PRs #497/#498 inspecionam o SQLite de candles historicos com esquema `candles`, `checkpoints` e `universe_snapshots`. O piloto WebSocket usa um **segundo** SQLite, `ws-confirmed.sqlite`, com `confirmed` e `meta`, e snapshots independentes `ws-reviewed-scope.json`/`ws-reviewed-epochs`. Portanto o CLI `j1_local_health.py` nao deve ser aplicado ao journal WS e seu estado nunca foi um atestado de continuidade desse canal.

## Implementacao
`crypto_intelligence_agent/j1_ws_owner_readonly.py` reusa `_safe_stat`, `_read_epoch_chain`, `_audit_epoch_chain` e `SQLiteOfflineClosedStreamJournal.audit`. Exige usuario POSIX nao-root, diretório 0700 e arquivos 0600, escolha explicita `allow_private_readonly_audit=True`, UTC de decisao alinhado 1h e observacao de 1..60 segundos apos o fechamento. So observa estado existente, nao instancia writer, nao abre rede nem cria arquivos.

A cadeia PIT é validada com as mesmas regras do coletor; apenas revisoes conhecidas ate a decisao podem participar da auditoria. Sem snapshot anterior ou snapshot obsoleto (>48h), falha. A auditoria SQLite `mode=ro` rejeita corrupcao, schema adulterado, digest falso, OHLCV, horas faltantes, timestamps, alteracao de membership e marcadores de lacuna inconsistentes. O novo relatório devolve somente contagens, hashes e categorias estaticas, nunca simbolos, precos, URL ou credenciais. Um arquivo `ws-pilot-health.json` nao substitui auditoria da base.

`scripts/audit_j1_ws_owner_readonly.py` oferece CLI apenas de consulta com parametros UTC explicitos. Exit 0 significa **somente** amostra WS local com 24h fechadas estruturalmente completas e identidade PIT interna consistente; exit 2 significa abstencao ou incompletude. Nao indica processo ativo nem autentica proveniencia real.

## Comando ilustrativo, nao executar na VPS sem gate
```bash
python scripts/audit_j1_ws_owner_readonly.py --directory /caminho/privado/ja-existente --decision-at-ms UTC_FECHAMENTO_1H --observed-at-ms UTC_OBSERVACAO_ATE_60S --allow-private-readonly-audit
```
Valores UTC devem ser inteiros em milissegundos. Nenhum timer/daemon é criado ou ativado.

## Validacao
`python -m unittest discover -s tests -p test_j1_ws_owner_readonly.py -q`, regressao `test_j1_bybit_closed_stream_cache.py`, `test_j1_ws_owner_pilot.py`, `test_j1_ws_multihour_soak.py`; CI Linux/docs, Windows/offline e Chrome/PAPER. Testes POSIX owner-only ficam skipped no Windows. Cenarios: opt-in, root, clocks, diretorio ausente/alterado, snapshot PIT invalido/symlink, journal ausente, adulteracao digest, warmup incompleto, 24h completas de 52 ativos sinteticos e zero escrita/rede do observador. CI verde valida o **codigo**, nao homologacao operacional.

## Limites
`worker_running_verified=false`, `source_authenticated=false`, `marketwide_top50_verified=false`, `canonical_ohlcv_approved=false`, `live_trading_authorized=false`. Nao converter `timestamp>end` de Bybit em candle canonico. Nao contornar #319, #429 ou #2.
