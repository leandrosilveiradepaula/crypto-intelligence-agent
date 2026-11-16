# J4 / D391 — eventos de ticker público alimentam gestão PAPER

## Entrega

`PaperIntrahourQuoteRouter` em
`crypto_intelligence_agent/paper_intrahour_quote_router_d391.py`
conecta o callback tipado `on_quote` do supervisor público
Bybit D386 ao coordenador de saídas automáticas D389
(stop antes de alvo) e **ao journal AUTO4 existente**.
Isso fornece um caminho completo para experimentar
`ticker -> decisão -> reserva de ordem hipotética`, sem
precisar de nova vela de 1h ou clique por operação.

Não é um executor de corretora; não abre conexão, não
coloca ordens, não gera ACK/fill, não coleta dados para
pesquisa, não modifica J1 nem demonstra rentabilidade.
O supervisor D386 continua injetado/finito e seu adaptador
D390 exige opt-in público. Nenhum serviço opera 24×7 na VPS.

## Invariantes

- Cada rota declara `position_id`, regra de stop e política
  de alvos com idade compatível. Inicialização consulta a
  posição no SQLite AUTO4 em modo somente leitura,
  comprova venue Bybit, plano e identidade do ativo.
- **Uma posição por símbolo nesta ponte PAPER** para
  evitar representar várias posições independentes
  em um contrato one-way de exposição líquida da
  Bybit. Não é limite global de quantidade de posições.
- Eventos da assinatura não vinculados a uma posição
  são ignorados. O callback rejeita transporte com
  atraso superior ao orçamento (padrão 3 segundos),
  sequência/relógio retroativo e mesmo `cross_sequence`
  com conteúdo diferente. Duplicata idêntica não
  dispara nova reserva; o D385 também protege o replay.
- A decisão propriamente dita é D389: stop primeiro,
  depois parcial somente quando stop não disparou,
  respeitando UNKNOWN e saldos confirmados/reservados
  no AUTO4. Nenhuma gravação financeira paralela.
- Limites de 100 rotas e 100.000 eventos por instância.
  As métricas retornam **contagens sem preços, símbolos
  ou IDs**, e as flags `orders_sent`,
  `order_submission_enabled` e
  `approved_for_live_use` são falsas.
- O cursor na memória não substitui reconciliação
  persistente após restart: um novo supervisor precisa
  revalidar ACK e snapshots; o journal PAPER continua
  com estado de reservas, mas NÃO é estado de conta real.

## Testes

`python -m unittest discover -s tests -p 'test_paper_intrahour_quote_router_d391.py' -v`

Os testes usam posição AUTO4 e ticks Bybit sintéticos:
alvo parcial, stop concorrente bloqueado durante ordem
pendente, fill fictício explícito para liberar saldo,
stop após fill, stop simultâneo ao alvo, duplicação,
sequência conflitante, atraso, escopo inválido e
callback completo D386 com ACK e snapshot injetado.
**Não há dados de corretora nem simulação de fills
automáticos por toque de preço**.

## Próximo gate

- Ampliar cobertura J4 a trailing/residual,
  preservando STOP FIRST e idempotência.
- Revisar integração de preço mark vs bid/ask,
  reconexão e custos sob J3/J6 antes de
  simulação prospectiva da conta.
- Implantar feed público 24×7 na VPS somente com
  gate de release e evidência de estabilidade; J1
  D384 segue bloqueada independentemente.
