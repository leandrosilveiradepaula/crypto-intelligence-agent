# J1/OPS30 — Shadow WS finito para pesquisa causal (#480)

## Por que existe

OPS26 já observou, na VPS, 29 frames WS, um GET REST e seis campos coincidentes em um candle BTCUSDT do mesmo provedor; não demonstrou validade causal universal, Top50 nem 24/7. OPS27/D233 preservou `timestamp>end` em quarentena, e OPS28/D234 eliminou promoção retrospectiva pré-ACK. OPS29 simulou 30 horas sintéticas, não 30 horas reais. OPS30 mede exclusivamente como frames WS públicos se apresentam numa sessão finita sem gravar nenhum deles.

## Garantias e limites

- `crypto_intelligence_agent.j1_ws_shadow_observer.observe_shadow_once`: transporte WebSocket injetado; no máximo uma conexão, um subscribe correlacionado de 1..52 tópicos `kline.60.<SYMBOL>USDT`, sem retries ou reconexão. Até 128 envelopes estruturais pré-ACK são descartados; ACK inválido, duplicado ou ausente causa abstenção.
- Um frame pós-ACK passa por validação integral de todas as linhas, 1..8 rows, grade UTC 1h, `confirm`, preços/volume/turnover Decimal, `ts` vs recepção e hora de fechamento. A única exceção é permitir diagnosticar o excedente `timestamp>end` sem aprová-lo; `timestamp<start`, `timestamp>ts` e cronologias incoerentes não são aceitos nem para contagem.
- Por tópico, uma hora fechada é contada uma vez em memória. Replay idêntico conta como duplicata, nunca nova vela. As bandas de excedente (+1, +2..1000, +1001..5000 e >5000 ms) são agregadas para fechamentos e updates abertos. Não publica nomes de ativos, preços, datas absolutas, payload, hashes ou IDs.
- O JSON sanitizado mantém `source_authenticated=false`, `canonical_ohlcv_approved=false`, `marketwide_top50_verified=false`, `continuous_collector_authorized=false`, `live_trading_authorized=false`. `rest_gets=0`, `storage_writes=0`, `orders_sent=false`. Uma linha inválida termina a sessão em abstenção. Contadores positivos não homologam feed.
- CLI `scripts.observe_j1_ws_shadow_once`: sem flags não abre socket. Com opt-ins explícitos `--allow-public-network --allow-public-websocket --confirm-region-and-personal-research`, usuário não-root e tópicos opcionais `--topic kline.60.BTCUSDT` etc., executa uma sessão; default BTCUSDT + ETHUSDT, 90s e 256 frames. Não agenda, não salva estado, não roda serviço. **Este documento não autoriza execução no servidor.**

## Gates antes de experimento real

Verificar no terminal proprietário da VPS: user não-root, sha GitHub exato, NTP/UTC, código já validado por CI pré/pós merge, regime de rede/Bybit, ausência de sondas/coletores simultâneos, recursos/budgets e estado da registry (não confundir amostra com Top50 mercado). O experimento deverá ser uma chamada isolada, única e finita; no caso de erro, não repetir cegamente. Não instalar/ativar `cia-j1-ws-owner.service`, não tocar em SQLite REST EXIT5 nem reusar/alterar claims anteriores.

## Aceite técnico

`python -m unittest discover -s tests -p test_j1_ws_shadow_observer.py -q`, incluindo ACK, pré-ACK, tópicos múltiplos, multirow atômico, budget, clock e finanças inválidos, silêncio, duplicatas, histograma e relatório anonimizado. CI Linux/docs, Windows/offline, Chrome/PAPER e revisão SHA antes e após merge. Mesmo relatório positivo não encerra OPS1 #429, J1 #2 ou Top50 #319. A admissibilidade de velas permanece bloqueada pela D233 até validação causal apropriada.
