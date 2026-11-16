# D393 — auditoria de custos condicional vinculada aos preenchimentos PAPER

A J4 D392 provou que as intenções de parciais e stop são gravadas num mesmo
SQLite AUTO4. A J3 já mantém `evaluate_synthetic_costs`, com aritmética
decimal exata para taxas, slippage e funding. **D393 conecta as duas provas
sem construir novo motor financeiro ou fabricar preenchimentos por toque de
preço.**

## Entrega executável

```bash
python -m scripts.run_paper_cost_audit_d393 --scenario closed
python -m scripts.run_paper_cost_audit_d393 --scenario unknown
python -m unittest discover -s tests -p 'test_paper_closed_cost_audit_d393.py' -v
```

`crypto_intelligence_agent/paper_closed_cost_audit_d393.py` lê por meio de
`inspect_paper_position`, em `SQLite mode=ro`, os eventos `FILL`
já persistidos em AUTO4. Para calcular o resultado condicional, exige
**uma referência de preço declarada para cada evento FILL**
(`intent_id`, `event_id`, UTC-ms). Qualquer referência ausente,
sobrando, duplicada ou com horário divergente aborta, assim como
funding com notional incompatível com o saldo fictício ainda aberto.
Usa a função J3/PRE2 `evaluate_synthetic_costs` para as taxas, o
slippage e o funding, com sinal dependente de LONG/SHORT.

**Sem todos os fills explicitamente reconciliados e posição zerada,
NÃO existe PnL numérico, nem sequer condicional.** Reservas, UNKNOWN,
ACK, cancelamentos ou saldo residual aberto nunca são convertidos
silenciosamente em lucro. A auditoria nunca envia ordens ou grava em
SQLite; as referências de fill permanecem fixtures fornecidas pelo
chamador e não são validação de preço da corretora.

## Cenário controlado LONG

Valores em **unidades de cotação fictícias**, sem afirmação de USDT
efetivo ou margem. A posição é de 100 unidades no preço de entrada
hipotético 100, com D392: 30 unidades a 101, 20 a 103 e 50
no stop a 98, todos com recibos de fill *explicitamente sintéticos*.
Premissas: entrada/saída 10 bps de taxa e 5 bps de slippage adverso
em cada ponta. Funding fictício positivo de 2 bps sobre
7.000 unidades de notional remanescente após a primeira saída.

| Componente | Referência condicional |
| --- | ---: |
| Variação bruta dos recibos fictícios | -10 |
| Taxa de entrada | 10 |
| Taxas de saída | 9,99 |
| Slippage de entrada | 5 |
| Slippage de saída | 4,995 |
| Funding sintético com sinal LONG | 1,4 |
| **Resultado líquido condicional** | **-41,385** |

Esse saldo **não é PnL real, backtest validado ou retorno sobre margem**.
Não foi verificado o calendário completo de funding, fees Bybit,
tempo de fila, execução passiva/agressiva, liquidation price,
regras de risco nem a disponibilidade financeira de 50x. Uma
conta com 50x pode liquidar antes de o stop fictício disparar.

O cenário `unknown` retém reserva de 30, saldo confirmado de
100, zero saída preenchida e campo
`conditional_net_after_supplied_costs_quote=null`, inclusive
quando existem marcas ou alvos favoráveis.

## Evidências e limites

Testes offline verificam ledger fechado, cronologia de funding,
resultados numéricos exatos, impacto de juros negativos, replay
duplicado, correspondência bijetiva de fills, ausência de recibos,
saldo ainda aberto, UNKNOWN e execução de CLI real em subprocesso.

A integração é **somente leitura**, base de dados temporária e
sem WS/REST reais, timers, contas, chaves, ordens, fundos ou custo
adicional. Relatórios sanitizados não divulgam IDs ou preços.
`net_pnl_verified=false`, `funding_calendar_complete=false`,
`liquidation_risk_verified=false` e
`approved_for_live_use=false` são imutáveis.

Próximo gate de produto: simulador de execução para eventos reais com
hipóteses explícitas de latência, spreads e parcialidade, fonte pública
contínua da Bybit homologada e replay de liquidação com risco
de 50x. Manter D384 J1 como pendência operacional separada.
