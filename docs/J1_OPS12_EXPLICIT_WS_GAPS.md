# J1/OPS12 — Retomada após lacunas WS sem candles fictícios

Issue #442, dependências #429/#319/#2, base main `98eba1dbae5b7dbd3a27e0087f6df68fb1594fa3`.

## Problema concreto

O journal WS exige `next.open_ms = previous.open_ms + 3600000` e rejeita dados reais posteriores se um evento `confirm=true` se perder após desconexão. O código também rejeita qualquer lacuna histórica na auditoria. Sem correção, a coleta deixa de registrar velas desse símbolo indefinidamente, ainda que o transporte se recupere. Repetir toda a captura REST não é opção: EXIT5 terminou em Bybit `retCode=10006`, preservando 37.470 candles/2 PIT.

## Solução OPS12

- O journal WS continua sendo o **mesmo SQLite privado separado** da coleta REST; nenhuma alteração de tabelas, nova migração ou backfill.
- `append` permanece estrito por padrão. Apenas o piloto owner-only, sob os opt-ins originais de rede/armazenamento, chama o supervisor com `allow_declared_gaps=True`. A pipeline offline existente conserva o padrão `False`.
- Um salto adiante de 1..168 horas ausentes é permitido somente se houver candle confirmado real válido no destino; sua própria transação `BEGIN IMMEDIATE` grava um marcador na `meta` preexistente e o evento autêntico de WS. A lacuna registra ausência, **não** um candle interpolado ou um novo PIT.
- O audit read-only exige correspondência exata entre cada salto real e o marcador, rejeitando órfãos, marcadores perdidos, adulterações, conflitos e saltos excessivos. Horas faltantes continuam faltando: a grade 24h e o ranking exigem 24 velas fechadas consecutivas para cada candidato revisado. Depois de 24h limpas é possível recuperar *apenas o ranking local da amostra*; `marketwide_top50_verified=false` permanece.
- A proveniência continua de WS não autenticado para fins de certificação; nenhum REST GET, ordem ou sinal financeiro é gerado. Um `ACK` não é entrega de dados.

## Aceite

`python -m unittest discover -s tests -p test_j1_ws_explicit_gap_recovery.py -v`
`python -m unittest discover -s tests -p test_j1_bybit_closed_stream_cache.py -v`
`python -m unittest discover -s tests -p test_j1_ws_supervisor.py -v`
`python -m unittest discover -s tests -p test_j1_ws_owner_pilot.py -v`

CI Linux/docs, Windows/offline, Chrome/PAPER, revisão de compatibilidade, SHA do HEAD, merge sem deploy, evidências pós-merge se consultáveis. O serviço systemd permanece off-by-default.

## Limites relevantes

Não existe reconciliação REST de candles ausentes nesta OPS. A antiga lacuna continua explicitamente registrada, sem preencher o OHLC. O limite de 168 horas exige nova intervenção técnica controlada se ultrapassado; não contornar com zero/reset. O teto de 100.000 linhas permanece e requer política de retenção futura. J1 #2/#319/#429 continuam abertas até cobertura real e homologação VPS. Nenhuma ordem real, credencial, deploy ou gasto.

## Observabilidade privada

O auditor publica somente `declared_gap_markers` agregado, sem símbolos, OHLC ou turnover. O relatório do piloto owner-only propaga o contador e o leitor de health valida intervalo 0..100000; mesmo fresco, esse último JSON informa `worker_running_verified=false`, `realtime_stream_verified=false` e `marketwide_top50_verified=false`. Nenhum contador de lacunas permite inferir saúde do processo ou substituir a grade 24h.

O digest antigo do diário sem lacunas é preservado byte a byte. Apenas um diário com marcador explícito inclui marcadores no hash, para não invalidar fingerprints anteriores sem necessidade.
