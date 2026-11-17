# J4 / D395 — trailing e residual no fluxo automático PAPER

## O que mudou

Antes de D395 o produto tinha: stop/targets intrahorários D389,
cotações tipadas D385/D391, o diário persistente de trailing RUNNER2
e o close de runner PRE4. Os componentes eram testados separadamente,
mas o fluxo de cada tick não chamava o trailing do residual.

`step_paper_intrahour_with_runner` conecta os componentes existentes
sem reimplementar cálculo nem criar outro ledger financeiro:

1. **STOP FIXO PRIMEIRO:** delega sempre ao coordenador D389. Se
   houve stop, dado stale, ordem UNKNOWN ou nova parcial, não inicia
   trailing nem cria outra reserva.
2. **ALVOS PARCIAIS:** o target D387 é avaliado pelo D389. O
   residual só fica elegível se todas as tranches têm preenchimentos
   PAPER registrados, não há reservas e o saldo confirmado equivale
   exatamente ao residual contratado.
3. **ATIVAÇÃO:** a primeira cotação válida após as parciais arma
   o RUNNER2 em um diário SQLite já existente, com marca e política
   imutáveis. Cotações posteriores atualizam ratchet LONG/SHORT
   segundo a política original de ativação e distância.
4. **SAÍDA DE RUNNER:** se RUNNER2 registrar gatilho hipotético,
   chama `step_durable_paper_runner_close` PRE4, que reserva
   **uma única ordem REDUCE_ONLY PAPER** via AUTO4. Repetições
   e reinício usam AUTO4 como estado de verdade.
5. **PENDENTE/UNKNOWN:** nenhuma nova ordem runner é emitida;
   o fluxo só retorna pendência, fechamento explicitamente
   registrado ou revisão manual. Não presume execução na Bybit.
6. **FALHA FECHADA:** gap na cronologia, snapshot do runner
   incompatível, política diferente, feed stale ou divergência
   de posição bloqueiam a mudança, sem rearmar diário paralelo.

A marca utilizada para o trailing é o `exchange_at_ms` da cotação
tipada, e o atraso de recebimento é controlado por orçamento de
frescor. O diário de RUNNER2 é independente do AUTO4 porque ele
**não armazena ordens nem saldos financeiros**: só guarda marcas
para replay causal já existente.

## Como validar

```bash
python -m unittest discover -s tests -p 'test_paper_intrahour_runner_bridge_d395.py' -v
```

Fixtures de mesma hora: entrada PAPER 100, saída parcial 30,
segunda saída parcial 20 (fills explicitamente simulados), residual
50. Depois da confirmação, o trailing LONG acompanha máxima,
aciona stop móvel numa correção e reserva REDUCE_ONLY de 50; sem
a confirmação posterior de FILL, permanece pendente. Em SHORT
a lógica de ratchet é invertida. Um stop fixo que cruza primeiro
anula o trailing; se uma parcial anterior estiver UNKNOWN,
o diário não é armado. Reinício preserva o estado do runner.

## Limites importantes

Esta entrega é somente código offline PAPER. O estado de
trailing **não é stop nativo instalado na corretora**. Não abre
socket público, não envia ordens, não cria fill, não modela
liquidação 50x, não substitui stop emergencial nem garante
proteção após queda de conexão. O feed contínuo público de J2
e o reconciliador privado de ordens ainda não foram homologados.

Um processo de produto deverá configurar uma rota persistente
para cada posição habilitada ao trailing, preservar o diário entre
reinícios e incorporar a ponte ao roteador de cotações J4/D391,
sob teste prospectivo. **Não foi feita instalação na VPS**.

Próximos gates: integrar esta ponte ao roteador D391, testar
ciclo completo D394 de fills hipotéticos e replay com lacuna
e liquidação, expor decisões no painel J5 e homologar
stream contínuo J2/J6 com dados públicos reais.
