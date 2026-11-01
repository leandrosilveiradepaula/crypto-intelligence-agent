# J1/OPS3 — Controlador WebSocket limitado, multiativo e owner-only

## Problema comprovado e objetivo

A retomada real do owner na VPS em 01/11/2026 encerrou com `retCode=10006` após 168 GET, no estágio `closed_kline_24h`. A auditoria independente confirmou 37.470 candles, 51 ativos históricos, 50 no último PIT, 2 PITs íntegros e cobertura inicial de 720h. Faltou um terceiro PIT real. Não há motivo para repetir 720h. O plano é receber candles novos via WS e atualizar o ranking de 24 horas localmente, sem reeditar a SQLite REST atual.

A OPS2 já fornece os validadores de candles `confirm=true`, journal SQLite offline e ranking de amostra revisada. Esta OPS3 adiciona um **controlador finito** que aceita somente `session_factory` injetado e reusa o pipeline existente. Não há `systemd`, serviço 24/7 instalado, conector real habilitado, backfill por REST, ordens ou credenciais nesta entrega. As evidências de execução são de fixtures locais; isto não autentica feed live e não prova Top50 do mercado.

## Protocolo finito

1. Exigir escopo `OfflineReviewedStreamScope` válido, de até 52 símbolos elegíveis já revisados, não apenas os 50 selecionados; isso evita ranking enviesado pelos candidatos que não são mais observados.
2. Produzir tópicos `kline.60.<symbol>` e enviar assinaturas em lotes conservadores de até 10 tópicos por vez. **Nunca mais de uma solicitação pendente por conexão**. A Bybit documenta múltiplos tópicos no mesmo WS, limite total de args e heartbeat. No caso multi-lote, **exigir `req_id` ecoado exatamente**: sem correlação, ACK duplicado poderia aprovar falsamente outro lote. O comportamento real de correlação ainda precisa de uma prova owner-only específica, sem relaxar este gate por suposição.
3. Antes de todas as assinaturas confirmadas, frames de mercado ficam numa quarentena em memória de no máximo 128 frames. Só após os ACKs correlacionados podem passar pelo mesmo validador rigoroso; desconexão anterior descarta a quarentena sem gravar.
4. Após os ACKs, validar frames com `ingest_offline_ws_batch(require_ack=False)` — somente ali, depois do gate de ACK externo. Velas abertas são examinadas, mas nunca armazenadas; `confirm=true` com timestamps, Decimal, identidade e 1h fechada é exigido no parser já versionado.
5. Enviar ping JSON a cada 20s sem comunicação de heartbeat, aceitar somente pong estruturado, considerar conexão degradada após 45s sem pong. Conexões e tempo de observação são finitos, com até 4 sessões/20.000 frames/3600s por invocação; por padrão até 3 sessões/4096 frames/180s. Reconexão somente após falha de transporte, com espera de 5s, 10s, 20s, etc., limitada pelo orçamento. Erro de esquema, ACK, vela, conflito ou lacuna **não é retry automático**.
6. Nunca preencher lacunas silenciosamente, nem reconstruir PIT de horários perdidos. O journal separado rejeita saltos horários e replay econômico divergente. Se 24 candles de qualquer candidato revisado faltarem, a OPS2 se abstém. Reconciliador REST ficará para implementação posterior, com quota/fail-stop `10006`.
7. Retornar **apenas contadores e categorias fixas**, sem símbolos, valores financeiros, URLs, paths, provider payload ou credenciais. `http_gets=0`, `orders_sent=false`, `marketwide_top50_verified=false`, `source_authenticated=false` e `live_trading_authorized=false` sempre.

## Exclusão mútua owner-only (POSIX)

`exclusive_owner_ws_writer` exige opt-in explícito e journal **separado** da SQLite REST em diretório 0700 do mesmo usuário e arquivo SQLite 0600 sem hardlink/symlink. Cria (se necessário) lock persistente `.ws-writer.lock` 0600 com `O_NOFOLLOW`, confere proprietário/inodes e toma `flock(LOCK_EX|LOCK_NB)`. Outra instância falha imediatamente. **Nunca apagar o arquivo de lock**, pois isso permitiria escritores diferentes segurarem inodes diferentes. Windows não tenta executar esse contrato POSIX. O serviço real deverá manter o lock por toda a vida do processo.

O controlador injetado isolado não ativa o lock por conta própria: testes determinísticos e UI offline podem chamá-lo. **Toda futura integração owner-only com rede real deve envolver `exclusive_owner_ws_writer` e gates regionais/escopo**, além de supervisor de processo. Este documento não fornece uma autorização de deploy ou comando para iniciar nova conexão na VPS.

## Evidências e limites

Testes offline em `tests/test_j1_ws_supervisor.py`: ACK/correlação, 52 tópicos e 6 lotes, vela aberta/fechada, quarentena preACK, replay de janela 24h existente, desconexão/reconexão, gap, heartbeat/pong, limites de execução e ausência de GET/ordens. `tests/test_j1_ws_owner_lock.py`: concorrência com lock, liberação, opt-in ausente, modos POSIX inseguros, hardlink e symlink.

Executar Python `compileall`, testes unitários Linux/Windows, `scripts/check_docs.py`, QA Chrome/PAPER, revisão diff, CI SHA de PR e CI pós-merge. No Windows os testes POSIX devem pular explicitamente. Nenhuma suite offline equivale a disponibilidade do WebSocket real na VPS ou autoriza trading.

## Próxima etapa, mantendo a issue #429 aberta

Integrar escopo real verificado PIT com o controlador sem fabricar metadados; preparar adaptação read-only do SQLite REST legado para warm-start causal sem misturar proveniência; reconciliador somente para lacunas dentro de orçamento com fail-stop em 10006; endpoint/painel PT-BR de saúde; definir e homologar `systemd` antes da ativação na VPS. J1 #319 também exige comparar todos os candidatos crypto-only do mercado — 52 revisados não são prova suficiente de Top50 marketwide.

## Fontes técnicas

- [Bybit WebSocket V5 Connect](https://bybit-exchange.github.io/docs/v5/ws/connect): endpoint linear, multi-topic subscribe, ACK, heartbeat 20s, limites de conexão.
- [Bybit WebSocket V5 Kline](https://bybit-exchange.github.io/docs/v5/websocket/public/kline): `kline.60`, `confirm` e timestamps de candles 1h.