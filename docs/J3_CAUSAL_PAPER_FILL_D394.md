# D394 — simulação causal de fills PAPER com latência e profundidade

## Problema resolvido

Até D393, as decisões intrahorárias D389 geravam intenções
`REDUCE_ONLY`, mas o preenchimento seguia exigindo fixtures
`FILL` explícitas. Para diferenciar intenção de um preenchimento
hipotético sob dados de mercado, D394 implementa uma **hipótese
de fill posterior ao sinal**, lendo uma cotação tipada D385 e
atualizando **somente** o journal PAPER AUTO4 existente.

Isto não é um agente de execução real ou modelo de fila.
Uma cotação pública de primeiro nível **não prova** que
houve preenchimento de ordem na corretora.

## Contrato

`apply_causal_paper_fill_assumption` exige:

1. Uma posição PAPER Bybit com intenção de saída
   já persistida e vinculada ao mesmo símbolo.
2. `enable_synthetic_ledger_fills=True` explícito;
   caso contrário, `offline_paper_optin_required`
   e nenhum write.
3. Uma cotação independente de ticker Bybit posterior
   ao instante da criação da intenção **mais o atraso
   mínimo configurado** (padrão 150 ms). A cotação
   disparadora do alvo/stop **não é um fill**.
4. Timestamp de exchange/recepção causal, orçamento de
   frescor (padrão 3 s), prazo máximo de espera da
   intenção (padrão 60 s) e spread BBO aceitável
   (padrão 30 bps), todos configuráveis dentro de limites.
5. Quantidade do fill sintético limitada pelo saldo
   pendente da intenção, por `bid1Size` quando a
   posição vende ou `ask1Size` quando compra, e
   participação máxima assumida (padrão 25% do topo
   observado); arredondar **para baixo** no lote PAPER.
6. `UNKNOWN`, `CANCELLED`, `REJECTED` e
   `FILLED` não geram novo fill; spread alto,
   profundidade insuficiente, atraso, latência
   insuficiente e dados stale geram abstenção.
7. O mesmo evento (posição, intenção, timestamp
   de exchange, sequência) tem ID determinístico;
   replay da cotação não cria evento adicional.
   O journal AUTO4 é o **único** mecanismo de
   contabilidade, com transação já existente.
8. Um preenchimento hipotético gera evento explícito
   `PaperOrderEvent(kind=FILL)` e
   `PaperDeclaredFillReference` com o preço BBO
   observado no lado correto. A referência
   destina-se à auditoria D393, que ainda precisa
   de todos os fills e de posição encerrada para
   calcular resultado condicional.

**Importante:** o preço BBO é apenas referência do
modelo. Não aplica um slippage oculto; D393 permanece
responsável pelo custo de slippage configurado. Não
existe sinal de corretora privada nem autenticação,
probabilidade de fila, impacto de mercado, ordens
reais, risco de liquidação comprovado ou PnL validado.

## Teste offline

```bash
python -m unittest discover -s tests -p 'test_paper_causal_fill_d394.py' -v
```

Testes com ticker Bybit tipado sintético e SQLite AUTO4:
- opt-in ausente não grava;
- a cotação que dispara target não pode preencher;
- evento posterior válido preenche somente parte
  do saldo com profundidade limitada;
- novo evento pode preencher restante, mas replay
  do anterior não aumenta unidades;
- LONG usa bid/size para vender e SHORT usa
  ask/size para comprar;
- UNKNOWN, spread alto, profundidade pequena,
  timestamps futuros/obsoletos e timeout abstêm-se;
- lote arredondado para baixo.

## Lacunas do modelo

Uma estimativa de fill baseada em uma única cotação
de ticker **pode ser otimista**: bid/ask e tamanho
de primeiro nível não atestam volume que de fato
seria executável após o atraso, nem prioridade na fila.
O modelo tampouco resolve o risco de liquidação 50x,
funding real, lot/notional mínimo da Bybit,
gaps entre observações, custos por nível de book,
preço de liquidação ou execução de ordens.

D394 permanece pesquisa offline. Para J6, exigir
cenários pessimistas e teste fora da amostra em
trajetórias reais públicas, confrontados com
latência e disponibilidade de dados observada.
**Sem gate de liberação financeira**, conta,
WebSocket privado, ordens ou mudanças na VPS.
