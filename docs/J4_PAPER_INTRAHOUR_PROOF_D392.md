# D392 — prova executável integrada de negociação PAPER intrahorária

**Objetivo:** evitar confundir quantidade de PRs com demonstração funcional. Esta entrega fornece um comando CLI reproduzível que realmente executa o decoder de ticker D385, o roteador D391, o coordenador stop-first D389 e o journal SQLite AUTO4 com uma posição fictícia Bybit, **sem acesso à rede, conta ou serviços da VPS**.

## Executar (CI/offline)

```bash
python -m scripts.run_paper_intrahour_proof_d392 --side LONG
python -m scripts.run_paper_intrahour_proof_d392 --side SHORT
python -m scripts.run_paper_intrahour_proof_d392 --side LONG --scenario unknown_blocks_stop
python -m unittest discover -s tests -p 'test_paper_intrahour_proof_d392.py' -v
```

Os relatórios JSON têm o schema `cia-paper-intrahour-proof-d392-v1`, digest SHA256 dos campos canônicos, estados das reservas, saldo confirmado e flags de qualidade. O SQLite é criado num diretório temporário e descartado após a auditoria; nenhum dado de J1/produção é escrito.

## Cenários reproduzíveis

| UTC, dentro da MESMA hora 10h | Ação e estado |
| --- | --- |
| 10h05 | `OPEN` PAPER de 100 unidades com um evento de fill **explicitamente injetado**. A estratégia não identificou nem abriu posição real |
| 10h12 | Snapshot ticker sintético com alvo 1: reservar `REDUCE_ONLY` 30; saldo permanece 100 até evento de preenchimento fictício separado |
| 10h12 + 1ms | Evento fictício `FILL` de 30, informado pelo teste. Não é inferido do toque de preço |
| 10h19 | Delta ticker sintético com alvo 2: reservar `REDUCE_ONLY` 20; depois registrar outro `FILL` fictício separado |
| Antes de 10h27 | Reiniciar a sessão simulada de ticker e o roteador; exigir novo snapshot, preservando saldo e intenções no SQLite original |
| 10h27 | Snapshot com mark cruzando stop: reservar `REDUCE_ONLY` de **apenas 50** restantes; depois registrar `FILL` fictício separado |
| Fim | Posição PAPER: 100 unidades de saída ficticiamente preenchidas, saldo 0, três intenções; sem preço real, taxa, PnL ou risco verificado |

A configuração de saídas contém duas tranches INITIAL_POSITION (30% e 20%) e residual inicial de 50%. O stop final sacrifica esse residual para testar proteção; **não é uma demonstração de trailing de runner**.

O cenário `unknown_blocks_stop` injeta `UNKNOWN` após reservar a primeira parcial: o alvo seguinte e o stop **não podem gerar reservas concorrentes**. Resultado esperado: posição com 100 unidades confirmadas, 30 reservadas/pendentes, nenhuma unidade preenchida de saída, necessidade explícita de conciliação. Há variantes LONG e SHORT.

## O que esta prova comprova / não comprova

**Comprova sob fixtures:** encadeamento executável entre módulos integrados, dois alvos e um stop na mesma hora, prioridade do stop, atualização efetiva de SQLite AUTO4, persistência entre instâncias, deduplicação/validação de ticker por D385 e gate UNKNOWN sem falsa confirmação de fill.

**Não comprova:** oportunidade de entrada quantitativa, preços reais da Bybit, disponibilidade de WebSocket 24×7, execução real de ordens ou stops nativos, aderência ao livro/lot/minNotional, taxas, funding, slippage, liquidação, alavancagem instalada de 50x, margem real, PnL, segurança financeira, capacidade multi-posição/live ou rentabilidade. O relógio, mercado e fills são sintéticos. `orders_sent=false` e `approved_for_live_use=false` em todos os relatórios.

## Próximas provas que mudam o status do produto

1. Capturar eventos públicos Bybit continuamente sob gate adequado, testar queda/reconnect e medir perdas de frames, latência e orçamento da VPS.
2. Substituir os `FILL` explícitos sintéticos por um **simulador separado e validado** de execução com bid/ask, taxas, slippage, latência, funding e liquidação, que mostre hipóteses e falhas; não inventar execução pelo toque no alvo.
3. Completar gerenciamento automático trailing e runner, exposição e risco de carteira; demonstrar PAPER prospectivo por período significativo, com auditoria reproduzível.
4. Somente depois, contrato REST de ordens + WS privado e homologação testnet sob autorização específica; live separadamente bloqueado.

Referências: D77, D382, D383, #676, #677 e `docs/BYBIT_V5_ARCHITECTURE_D383.md`.
