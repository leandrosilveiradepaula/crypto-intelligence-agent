# J4 / D388 — stop de emergência PAPER antes das parciais

## Problema concreto

A J4 tinha planos PRE1 de percentuais e runner, mais a reserva AUTO4
de saídas planejadas. Ela **não admitia fechar toda a posição antes da
primeira parcial**. Com alavancagem de pesquisa de 50x, esperar completar
as metas antes de um stop seria especialmente errado, mesmo em simulação.

## Implementação

Esta entrega estende o **journal AUTO4 já existente** com um tipo especial
de saída PAPER `tranche_step=-1` para emergência. **Não cria segundo
ledger, tabela ou migration** e preserva a compatibilidade dos registros
anteriores com tranches positivas (parciais) e zero (runner).

`paper_intrahour_emergency_stop_d388.py` consome cotação tipada
Bybit D385 e a posição PAPER confirmada. LONG dispara quando
`mark_price <= stop_mark_price`, SHORT quando
`mark_price >= stop_mark_price`. Os níveis são `Decimal` validados,
tempo UTC causal e quote dentro da idade declarada. BBO sem profundidade
ou feed obsoleto provoca abstenção; não inferir um fill de uma oscilação
de mark. O stop **deve ser avaliado antes** dos alvos do D387 por
um coordenador, que ainda precisa ser implementado.

Quando disparado, o módulo chama `SQLitePaperPositionJournal.reserve_exit`
com o **saldo confirmado total** de `REDUCE_ONLY`, mesmo se as metas
parciais nunca foram atingidas. O journal verifica em transação única:
- ausência de reservas ou ordens anteriores sem reconciliação;
- quantidade inteira ainda aberta, lot-step sintético, mesmo símbolo,
  lado, plano/posição, venue Bybit e ordem causal;
- nenhum runner já emitido e nenhum stop anterior (rejeitado/cancelado
  não é reenviado cegamente);
- nenhuma tranche/runner pode ser registrada **após** a emergência;
- `UNKNOWN` e fill parcial mantêm saldo reservado até confirmação;
- evento `FILL` precisa ser adicionado explicitamente via
  `append_exit_events` para reduzir quantidade. ACK ≠ FILL.
- replays/checkpoints anteriores continuam válidos; validação de
  replay exige que o stop seja de **todo saldo residual**, não uma
  redução arbitrária disfarçada.

Em caso de parcial anterior pendente/UNKNOWN, a resposta
`older_exit_unresolved_no_new_stop_paper_only` expõe que o saldo
não pode ser reservado duas vezes: a proteção não está comprovada.
Esse caso é um **bloqueio de homologação para capital real**, não
uma falsa promessa de que um stop já está na Bybit.

O relatório é sanitizado e indica sempre
`native_stop_verified=false`, `orders_sent=false`,
`approved_for_live_use=false`. A ordem é **apenas uma reserva PAPER**;
nenhuma API autenticada, depósito, liquidação ou preço de execução é
simulado por este módulo.

## Evidências / testes offline

`python -m unittest discover -s tests -p test_paper_intrahour_emergency_stop_d388.py -v`

Cenários: stop LONG antes de qualquer alvo, SHORT por mark (não Last),
saldo restante após primeira tranche confirmada, UNKNOWN/pending
de outra saída impedindo dupla reserva, cancelamento seguido de
reconciliação, stop UNKNOWN/cancelado sem retry, concorrência de
dois eventos, stale/sem book, mismatched ticker/clock, ausência de
fill fabricado e bloqueio de tranche depois de emergência.

Regressões da suíte AUTO4 original são executadas pela CI completa.

## Pendências para fechar #676

- Coordenador de um evento intrahorário executa **stop primeiro**,
  depois alvo parcial D387 e, somente com as parciais concluídas,
  runner/trailing existente. Testar stop e alvo simultâneos sem
  emitir duas ordens e reconciliar stop em presença de ordem
  anterior ainda pendente.
- Estender contratos de proteção real via REST Bybit
  `/v5/position/trading-stop` e fills por WS privado;
  `positionIdx`, modo one-way, regras Full/Partial, taxas,
  slippage, liquidação e native stop verificado são gates
  separados em testnet e live **não autorizados aqui**.
- Testes replay/stress intrabar com mercado, eventos reordenados
  e estratégias J2/J3, sem inventar trajetória ausente.

Referências:
- `docs/J4_INTRAHOUR_AUTO_TARGET_D387.md`
- `docs/BYBIT_V5_ARCHITECTURE_D383.md`
- https://bybit-exchange.github.io/docs/v5/position/trading-stop
