# J1/D313 — ponte de evidência causal N50 por WebSocket, 50/50 (offline)

## Por que

O N50 REST incremental falhou com retCode `10006` após 4 GETs às 16:01 UTC de 12/11/2026; o fallback N2 foi correto, mas coleta 2 contratos. A correção D311 usa intervalos de 8s somente para o writer N50, sem garantir quota. A rota estrutural #585 é obter os fechamentos `kline.60` confirmados de WebSocket público e reduzir REST à captura de universo/lacunas, **sem confundir dados WS com respostas REST**.

## Primeira unidade integrável: prova de fechamento pontual 50/50

- `SQLiteOfflineClosedStreamJournal.audit` passa a aceitar `hour_evidence_symbols` **opcional** e estritamente `tuple` ordenada com 50 membros distintos já presentes no escopo validado. O contrato normal da auditoria WS 24h/720h continua compatível e inalterado. A auditoria original continua lendo **uma transação SQLite BEGIN read-only** e validando SHA dos payloads, identidade, gap markers, UTC e cronologia de cada candle, sem confiar apenas em ACK ou contagem do provider.
- Nessa **mesma transação** é calculado o número de recibos reais do último candle fechado (`decision_at_ms - 1h`) entre os 50 selecionados, antes de `as_of_ms`. Só 50/50 libera digest `hour_evidence_sha256`; 49/50 = contagem parcial e digest ausente. Campos sanitizados reportam contagens/digest, nunca símbolos ou valores de OHLC.
- `j1_n50_ws_hourly_attestation.attest_n50_ws_hour_once` exige coorte D287 **já selada** e imutável (50 membros, hash/UTC/TTL D287), verificação de identidade no escopo WS pré-existente com 50–52 membros (não substitui o ranking), e decisão UTC com recebimento limitado a 1–120s após o fechamento. Não há conexão, GET, arquivo gerado, liberação de ordem, escrita SQLite ou systemd. A prova contém hashes vinculando digest da coorte D287, journal WS, versão do catálogo WS e eventos da hora; **`published_rest_pit=false`** mesmo com 50/50.
- **Não produzir prova positiva se a coorte N50 não couber no escopo WS revisado**: isso é um bloqueio explícito, não autorização para criar uma lista sintética nem derivar elegibilidade de `USDT`. O atual piloto WS de 50–52 instrumentos é um catálogo limitado/revisado; alcançar os 50 dinâmicos de D287 requer adaptação da cadeia de metadados ou novo escopo WS do mesmo censo, com testes e gate separados.
- Fonte de candles: `bybit_public_ws_confirmed_fixture` e `source_authenticated=false`; não autentica exchange real nem garante condições de uso. Nunca armazenar WS como REST e não preencher hora passada retroativamente.

## Testes e etapas restantes da issue #585

`test_j1_n50_ws_hourly_attestation_d313.py`: 50×1 `confirm=true` sintéticos no SQLite real e result 50/50; 49/50 e último evento depois do cutoff não geram digest; `confirm=false`, membro estranho, drift, digest adversarial, voto de epoch antigo, timestamps inválidos, replay idempotente e alteração monetária de replay reprovada. `test_j1_bybit_closed_stream_cache.py` e testes do WS supervisor/pilot devem seguir passando. CI Linux/docs, Windows/offline e Chrome/PAPER no SHA final.

**Ainda necessário antes de J1 pronta:**

1. No WS owner: admitir a coorte dinâmica completa de 50 nomes do censo D287 com metadados de instrumento válidos e hash, sem dependência do catálogo fixo de 52, sem serviços pagos.
2. Operacionalizar assinatura WS para os 50 (`bybit_ws_supervisor` já possui ACK/heartbeat/reconnect/budget), registrar os 50 candles confirmados por hora com journaling e lock owner; publicar recibo no journal WS dedicado somente depois de 50/50 e garantir idempotência/integridade de épocas.
3. Reparar gaps via REST dentro de quota, sem retry de 10006, em fonte explicitamente separada. Não reiniciar N50 REST travado antes da auditoria do HALT atual e gate root.
4. Validar 24 fechamentos reais consecutivos e rotação da coorte >=36h, além da identidade crypto-only independente #319. Nenhum lucro/trading implícito.

**D313:** uma hora de 50 eventos WS comprovados pela trilha WS é uma observação local, **não** recibo do SQLite REST legado, evidência de continuidade de 24h, provedor autenticado, cobertura Top50 global nem sinal de compra. Merge de código não implanta serviços.
