# J2 / D386 — supervisor de WebSocket público Bybit com reconexão

## Entrega

`crypto_intelligence_agent/bybit_public_ticker_supervisor_d386.py`
implementa uma **lease finita de eventos intrahorários** usando conexão
WebSocket pública Bybit injetada. Integra-se diretamente à estrutura D385
`BybitPublicTickerBook` e pode distribuir `BybitTickerQuote` a um
consumidor PAPER fornecido pelo chamador, sem importar API de ordens.

Este módulo **não** abre sockets por conta própria, não instala systemd,
não modifica SQLite owner da J1 e não envia qualquer ordem. Seu contrato é
compatível com um processo permanente após teste e gate específico,
mas **ainda não há serviço público 24×7 rodando na VPS**.

## Contrato de operação

- Assina até 100 tópicos de `tickers.{symbol}` em **uma única requisição**,
  para eliminar ambiguidade de ACK quando a Bybit devolve `req_id` vazio
  ou o omite. Orçamento de 21.000 caracteres JSON e estado independente
  de universo previamente admitido. Não faz ranking/crypto classification.
- Antes da confirmação de inscrição, descarta eventos de mercado sem
  transformá-los em preços; limite de 128 eventos antecipados por sessão.
- Após ACK válido, recebe ticks e deltas através do D385 (Decimal,
  last/mark/index, bid/ask, relógios, sequência e freshness). Eventos
  não admitidos, contraditórios, futuros, fora de ordem ou sem snapshot
  após reconexão invalidam o estado e **interrompem a lease**.
- `ping` nominal a cada 20s e prazo de `pong` de 45s.
  Uma desconexão de transporte permite reconexão com espera e limites
  configuráveis; **o estado de preços é sempre invalidado** entre sessões,
  exigindo novo ACK e snapshots. Mensagem inválida não gera loop de retry.
- Limita sessões (default 3, máximo 4), quadros (default 50.000,
  máximo 5 milhões) e duração (default 180s, máximo 3.600s).
  O processamento de quote é síncrono e não mantém fila ilimitada.
  Ao atingir limite de quadros, devolve abstenção explícita, nunca
  certifica continuidade do feed.
- Callback opcional `on_quote` recebe somente a cotação tipada e validada.
  Não é contrato de trade, e eventual conexão a um gerenciador de posições
  depende de J4 #676 e de gating. Não há suposição de preço executável.
- Relatório count-only (número de sessões, frames, ACK, ping/pong,
  reconexões, quotes recebidas, contagem fresca ao final e buckets de
  atraso), sem símbolo, preço, frame ou credenciais. `orders_sent=false`.

## Teste de falhas

`python -m unittest discover -s tests -p test_bybit_public_ticker_supervisor_d386.py -v`

Fixtures de sessão, sem rede: ACK único para 51 tópicos, ACK vazio,
frames antes do ACK, ACK conflitante/extra, preço inválido, event sourcing
após desconexão, retry com snapshot novo, `ping/pong` e prazo de heartbeat,
limites de recursos, prova de que nenhum frame anterior ao ACK chega ao
callback, nenhuma tentativa de ordem.

## Próximos incrementos dentro da #677

1. Conector público real e supervisionado que injete `StreamSession`
   com websocket transport e desligamento gracioso; benchmark/profiling
   50+contratos, drop-rate, p95/p99 de atraso e bytes/s. Confirmar
   comportamento do handshake e limites atualizados na Bybit.
2. Integração de rotação de N50/posições com subscribe/unsubscribe
   confirmado, política de reaquisição de snapshots e watchlist
   atualizada por REST; sem abandonar posição aberta.
3. Replay/persistência de ticks e eventos úteis para J3 com custos
   e orçamento de disco. Inserir em sistema J2/J4 PAPER após testes.
4. Piloto read-only isolado na VPS somente após gate de release;
   não desligar o coletor J1 WS horário, não abrir segundo escritor
   sobre seu SQLite.

Fontes primárias: [Bybit WS connect](https://bybit-exchange.github.io/docs/v5/ws/connect),
[Bybit public ticker](https://bybit-exchange.github.io/docs/v5/websocket/public/ticker).
