# D413 — diagnóstico real de 129 frames pré-ACK no WebSocket N50

## Evidência observada em 17/11/2026, 21h38 UTC

O operador, na VPS `srv1319424`, executou o probe D406 a partir de um tarball GitHub SHA `d295138a88b409f04a5c645433da7bd26e3016ad`, validando dois blobs Git conhecidos, sob UID `cia-probe` e **sem modificar o checkout owner da J1**. Relatório sanitizado real:

- `network_attempted=true`, `data_mode=real_public_websocket`, `sessions_attempted=1`;
- `requested_contracts=50`, `frames_seen=129`, `elapsed_seconds=3.657`;
- `subscription_acks=0`, `market_frames_accepted=0`, `received_distinct_contracts=0`;
- `failure_category=invalid_market_data`, `status=public_market_frames_not_verified`;
- `orders_sent=false`, `private_state_modified=false`, `quotes_persisted=false`;
- CLI `BYBIT_PUBLIC_WS_PROBE_EXIT=2`.

Esse número **129** coincide exatamente com a condição `preack_session > MAX_PREACK_FRAMES` do supervisor D386, cujo limite era **128**. Antes de alcançar o ACK, o supervisor descartou frames de ticker e disparou `ticker_ws_preack_budget_exceeded`, mas a tabela de causas não reconhecia essa exceção específica e a mascarava como `invalid_market_data`.

**Diagnóstico fundamentado:** a causa imediata da interrupção da sessão anterior é o teto pré-ACK fixo, incompatível com o volume inicial de 50 tópicos. **Ainda não foi demonstrado** se o servidor enviaria um ACK válido depois desses frames, nem se haveria snapshot fresco após ele. Não confundir sucesso de TLS/WebSocket e recepção de frames com cotações homologadas.

## Correção

- D386 mantém o descarte incondicional de todo ticker pré-ACK, sem cache, journal, callback PAPER ou aparente preço válido.
- O limite de frames ignorados antes do ACK passa a ser calculado por escopo: `min(4096, max(128, 64 * len(topics)))`. Assim 50 tópicos podem gerar até 3.200 frames pré-ACK sem encerrar prematuramente a única sessão de 20 segundos; o número total de frames e a duração continuam finitos.
- **Sem ACK reconhecido:** nenhuma cotação é aceita. O resultado do lease permanece falha `no_subscription_ack` por tempo esgotado ou `preack_limit_reached_before_ack` se atingir o novo teto. Não foi relaxado ACK, schema, clock, ordem ou autorização financeira.
- Falha de ACK malformado passa a ter categoria própria `invalid_subscription_ack`, sem ecoar dados, símbolos ou conexão. O relatório D405 inclui `preack_frames_discarded` como contagem, sem raw frames.
- Tests offline reproduzem 129 ticks pré-ACK com 50 + posição externa, ACK tardio seguido de snapshot aceito; sem ACK, zero quotes/ordens; com dois tópicos, o limite menor permanece ativo. A prova D405 não permite tratar socket injetado como mercado real.

## Próxima operação real

Executar **uma nova sessão finita** com código pinado no SHA integrado e o mesmo fluxo temporário sob UID owner, preferivelmente primeiro com apenas `BTCUSDT` (D405) e depois com os 50 da J1 (D406), mostrando explicitamente ACKs, pre-ACK descartados, quantidade de quadros aceitos, cobertura e causa da falha. Não alterar serviço/timer/banco J1, não instalar daemon, não enviar ordens.

Se o ACK for recebido mas faltar snapshot pós-ACK, a próxima correção deverá preservar a política fail-closed sem aceitar preço de mensagem não confirmada. Se o ACK não chegar, revisar formato/sessão junto aos exemplos oficiais da Bybit. Não ativar PAPER, não afirmar suporte 24x7 sem evidência.

Fontes públicas de protocolo: https://bybit-exchange.github.io/docs/v5/ws/connect e https://bybit-exchange.github.io/docs/v5/websocket/public/ticker

Custo R$ 0,00, nenhuma ordem real.
