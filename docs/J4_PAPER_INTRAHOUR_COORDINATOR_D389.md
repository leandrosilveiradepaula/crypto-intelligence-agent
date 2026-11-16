# J4 / D389 — coordenador PAPER de stop e saídas parciais

## Necessidade concreta

D387 implementou reservas automáticas de targets de saída; D388 implementou
reserva de stop emergencial pelo mark da Bybit, inclusive antes do primeiro
alvo. Ambos reutilizam o journal AUTO4, mas **não havia uma chamada única**
que garantisse que a proteção fosse avaliada antes de uma realização quando
uma única atualização de mercado satisfazisse os dois critérios.

D389 entrega `step_paper_intrahour_coordinated` em
`crypto_intelligence_agent/paper_intrahour_coordinator_d389.py`, uma
composição explícita de D388 e D387 com **stop sempre prioritário**.

## Semântica

1. Exigir políticas tipadas explícitas, relógios compatíveis e
   `BybitTickerQuote` tipado; diferenças no orçamento de idade impedem
   qualquer reserva antes de tocar o journal.
2. Executar D388 **primeiro**. Apenas `mark_stop_not_triggered_paper_only`
   (`HOLD`) permite consultar D387. Todas as outras respostas de stop
   encerram a avaliação do evento sem criar nova parcial:
   `RESERVED`, `PENDING`, `CLOSED`, `STALE`,
   `OLDER_ORDER_UNRESOLVED` e `MANUAL_RECONCILIATION`.
3. Um único tick em que mark cruza stop e bid/ask satisfaz um target
   gera **somente reserva PAPER do stop**, nunca duas reservas. É
   obrigação do AUTO4 garantir idempotência/quantidade em transação SQLite.
4. Se parcial anterior aguarda ACK/UNKNOWN/fill, stop não disputa a
   quantidade. O resultado expõe **posição sem proteção comprovada** e
   exige reconciliação, não promete que foi protegida na Bybit.
5. Se a parcial anterior recebeu fill explícito, o stop pode reservar o
   **saldo confirmado restante**, e não o tamanho original. Repetições
   concorrentes do mesmo evento não duplicam a reserva.
6. D387 somente pode rodar se o stop estiver comprovadamente avaliado
   como não disparado e com dados frescos. Feed stale ou BBO sem
   profundidade causa abstenção completa, mesmo que o último preço
   pareça lucrativo.
7. Resultados são tipados e relatórios são sanitizados; não guardam
   símbolos/preços/IDs, não geram evento `FILL` ou PnL, não enviam
   ordem e nunca certificam stop nativo ou autorização live.

## Evidência offline

`python -m unittest discover -s tests -p 'test_paper_intrahour_coordinator_d389.py' -v`

Cenários: stop e alvo simultâneos, parcial e stop depois de fill
confirmado, pendência de reconciliação impedindo alvo, stop totalmente
preenchido explicitamente, dados stale ou livro zerado, HOLD sem
ordens, política incompatível, símbolo errado, concorrência e SHORT.

## Próximas tarefas na issue #676

- Trailing stop e residual com estado persistente, sem novo journal;
- Consumo da mesma cotação emitida por supervisor público #677;
- Replay intrabar com eventos ordenados, taxas/funding/slippage/
  latência/liquidação em J3 e J6, sem supor fill no toque;
- Adaptador REST/WS privado Bybit em offline e testnet sob gates
  separados, sem ativar conta ou negociar capital nesta entrega.

**Gate de J1 permanece separado:** nada neste módulo modifica o
WebSocket horário, SQLite owner, timers ou release da VPS.
