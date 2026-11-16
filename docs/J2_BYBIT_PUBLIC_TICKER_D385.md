# J2 / D385 — estado de ticker público Bybit V5 em tempo intrahorário

## Objetivo

A D383 selecionou Bybit V5 `linear` como venue única. A issue #677
implementa um feed público de mercado contínuo. D385 entrega sua **primeira
camada de dados, totalmente offline e desacoplada de sockets reais**:
`crypto_intelligence_agent/bybit_public_ticker_state_d385.py`.

O coletor N50 WS de janela curta da J1 permanece intacto. Este componente
NÃO inicia conexão pública 24×7, não coleta novos dados na VPS e não abre
ordens. Ele é um decodificador/estado causal a ser utilizado por um supervisor
WebSocket persistente em uma próxima integração revisável.

## Contrato de entrada

O chamador injeta uma coorte de até 50 contratos previamente admitidos
pelo pipeline PIT da J1/REST Bybit e a lista atual de contratos com posições
(estes são monitorados mesmo fora do N50), totalizando até 100. O módulo
não comprova que símbolos sejam criptomoedas ou estejam habilitados na Bybit;
`USDT` é só a gramática de entrada.

O chamador deve confirmar assinatura/ACK de `tickers.{symbol}` no
WebSocket público `wss://stream.bybit.com/v5/public/linear` **antes** de
iniciar a sessão. `begin_acknowledged_session` limpa os estados de
sessões anteriores. Após desconexão, `mark_disconnected` invalida TODOS
os preços; próximo acesso requer novo snapshot após nova inscrição.
Assinaturas dinâmicas são planejadas por `rotate_membership`, sem enviar
uma mensagem pelo próprio componente. Após novo ACK validado pelo chamador,
`acknowledge_added_topics` libera **somente** os tópicos novos admitidos;
quadros que chegarem antes do ACK são rejeitados e invalidam a sessão.
Uma atualização de universo com tempo no futuro não autoriza usar seus dados
antes do instante de observação PIT.

Quadro `snapshot` inicial precisa conter preços last, mark, index,
bid1/ask1 e respectivas quantidades. `delta` atualiza somente os campos
presentes: ausência significa **valor não alterado**, e não zero. Sem
snapshot prévio, o delta é recusado. Cross-sequence regressiva, timestamp
invertido/futuro, idade de rede acima do limite, BBO cruzado, duplicata
com mesmo sequence e payload divergente, dados financeiros malformados,
símbolo não admitido e JSON com chaves duplicadas provocam desconexão
lógica e abstenção. Duplicata idêntica mantém a primeira recepção
imutável, sem renovar artificialmente a idade.

**Separação financeira:** `lastPrice` ≠ `markPrice` ≠ bid/ask; nenhum
deles prova preço de execução. A função `current` devolve `None`
para ausência, book sem profundidade, desconexão ou quote obsoleta
(default 3000 ms), jamais uma ordem ou fill. Recepção e tempo do
servidor são armazenados separadamente.

`sanitized_report` contém **apenas contagens** e flags
`order_submission_enabled=false, orders_sent=false,
live_trading_authorized=false`; não expõe preços nem símbolos.
O módulo usa validação decimal exata já existente e rejeita JSON
numérico com float no campo financeiro, para evitar erros de precisão.

## Próxima implementação dentro de #677

- Supervisor de conexão pública persistente, com autenticação **não
  necessária**, ACK por lote, `ping/pong`, reconexão com backoff,
  reset de snapshots e limite de sessões/frames/memória.
- Persistência de dados intrahorários causalmente reproduzíveis, com
  retenção/limites de volume medidos na VPS; controle de timestamps,
  atrasos p95/p99, mensagens perdidas e backpressure.
- Composição com sinais J2 e motor de saídas PAPER #676, protegendo
  posições e bloqueando entradas quando feed staleness/UNKNOWN.
- Piloto isolado read-only na VPS somente após release/gate próprio;
  manter J1 WS de 1h e seu SQLite proprietário sem dois escritores.

## Testes

`python -m unittest discover -s tests -p test_bybit_public_ticker_state_d385.py -v`

As fixtures cobrem snapshot/delta, precisão de Decimal, campos omitidos,
funding negativo, duplicata idêntica e conflitante, monotonicidade de
sequence/clock, stale, bid/ask inválidos, zero liquidity, JSON com
chaves duplicadas, 50 símbolos com posições fora do ranking, rotação e
reconnect sem reusar estado. Nenhum teste abre rede ou conta.

Fontes oficiais:
- https://bybit-exchange.github.io/docs/v5/websocket/public/ticker
- https://bybit-exchange.github.io/docs/v5/ws/connect
- https://bybit-exchange.github.io/docs/v5/websocket/public/kline

Nenhuma testnet, API privada ou ordem financeira está autorizada.
