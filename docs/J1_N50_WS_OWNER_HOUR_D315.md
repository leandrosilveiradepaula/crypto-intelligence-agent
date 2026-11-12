# J1/D315 — lease owner N50 WS com comprovante causal 50/50

Referências: #585 (WS-first), #429 (supervisão), #319 (identidade).

## Entrega e contrato

O módulo `crypto_intelligence_agent.j1_n50_ws_owner_hour` liga três
componentes **já testados** em um fluxo único:

1. `DynamicN50WSAdmission` (D314) vincula exatamente os 50 contratos do
   manifesto D287 ao escopo de metadados, sem usar o registro local fixo de 52.
   Valida hashes, tipos, timestamps, membro exato e pré-existência do escopo
   antes da hora-alvo fechada.
2. `exclusive_owner_ws_writer` (OPS3) verifica DAC POSIX 0700/0600,
   journal SQLite isolado e flock não bloqueante **antes** de solicitar
   `session_factory`. Recusa root, flags ausentes, caminho inseguro ou lock
   já ocupado; nenhum socket é criado pelo próprio módulo.
3. `supervise_ws_research` (OPS3) faz uma assinatura única de 50
   `kline.60.*`, ACK completo e controle bounded de tempo/frames/heartbeat/
   desconexões. Sua ingestão reaproveita o parser `confirm=true` e o
   SQLite WS fechado, deduplicado, com recibos UTC e digests.
4. Só uma lease íntegra e encerrada por budget, com ACK, chama a auditoria
   D313 no mesmo escopo e journal: `attest_n50_ws_hour_once` atesta uma
   hora UTC com **50/50** candles fechados e timestamp de recepção causal.
   49/50 mantém linhas parciais e emite `rest_gap_reconciliation_required`,
   **sem** fabricar PIT, preencher zero ou disparar REST. ACK ausente, limite
   de frames, clock/identidade inválidos e lock contendido absterão.

## Limites operacionais deliberados

- A função é uma **composição owner opt-in por lease**, não um daemon nem um
  gerenciador de service. Requer `allow_private_ws_writer=True` e
  `allow_injected_public_ws=True`, `session_factory` explicitamente
  fornecido pelo executor autorizado, `journal` WS já separado e
  `WSRunBudget`. Não há código que crie socket HTTP/WS neste módulo,
  consulte Bybit, reinicie systemd ou publique ordens.
- A fonte do evento persistido é o pipeline público de `confirm=true`
  `bybit_public_ws_confirmed`, não `bybit_rest_closed_kline`. O relatório
  contém somente contagens/hashes/flags; nenhum ticker, preço, payload,
  URL, segredo ou stack trace. Há `closed_events_appended_to_ws_journal`,
  portanto não alegar **zero writes** no journal WS; somente
  `rest_database_modified=false` e `http_gets=0`.
- Um `ws_owner_hour_50_observed_local_only` prova a observação local de
  uma hora **em fixture/sessão fornecida**; não autentica o provedor, não
  certifica Top50 global, não equivale a PIT REST e não aprova sinais,
  24h/36h contínuas, lucro, sistema instalado ou trading real.
- Se houver gaps, o planejamento de REST em #585 requer quota, provenance
  separada, lock e fail-stop 10006. **D315 não executa backfill**.
- O HALT da epoch REST `epoch-1794492000000` (1.203 candles, 1 PIT,
  3 parciais) deve permanecer imutável. O serviço N50 segue disabled/failed,
  N2 ativo: nenhum release/cutover autorizado por este merge.

## Aceite e evidências

Teste `tests/test_j1_n50_ws_owner_hour_d315.py` com POSIX owner temporário,
jornal SQLite real isolado e sessão injetada sem rede: 50/50, 49/50 +
complementação, `confirm=false`, frame anterior ao ACK, ACK forjado, limite
de quadros, manifesto futuro, metadado forjado, flags ausentes, lock concorrente,
contagens/sanitização e ausência de GET. Suite completa Linux/Windows/offline
e Chrome/PAPER no SHA final + revisão, merge sem implantação. Positivos POSIX
são skipped explicitamente em Windows, não confundidos com falha.

## Próximo gate da #585

1. Integrar `load_private_ranked_scope` e `capture_n50_dynamic_ws_metadata_once`
   a uma **nova** epoch privada D314 com escopo/journal exclusivo,
   versão controlada, budget de metadados e lock completo. Não reusar o
   SQLite da epoch REST HALT.
2. Empacotar watcher owner WS com lease pré-fechamento, recibos e falhas
   observáveis; REST somente para gaps corroborados, sem retry 10006.
3. CI, smoke root em preflight OFF, revisão dos units N2/N50/fallback e
   autorização própria de release; 24 fechamentos reais e rotação >=36h
   documentados separadamente, além da #319 crypto-only.

Custo adicional: R$0; sem ordens.
