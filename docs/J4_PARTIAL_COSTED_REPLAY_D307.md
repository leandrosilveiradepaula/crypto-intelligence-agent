# J4/D307 — parciais, runner e custos por hipótese, sem ordens

## Objetivo e isolamento

A J4 já dispõe de planos `INITIAL_POSITION`/`REMAINING_BALANCE` (PRE1), replay idempotente *in-memory* de fills de fixture (PRE2), snapshot de margem/alavancagem imutável (PRE3) e reservas duráveis PAPER (AUTO4). O que faltava para pesquisar gestão de vencedores era juntar quantidades preenchidas, valor de referência do residual, taxas, slippage adverso e funding **sem fingir que isso seja PnL executado**.

`synthetic_partial_costed_replay.py` reutiliza `replay_synthetic_position` para a matemática de saídas e `evaluate_synthetic_costs` da J3 para cada saída marcada. Todos os preços, taxas, eventos de funding e observações são fornecidos em fixtures `Decimal`, com limite de tempo e precisão. Não acessa Bybit, Binance, SQLite, credenciais, APIs nem systemd. Nunca cria ordem, stop, autoexecução ou posição financeira.

## Contrato matemático

- As tranches respeitam os dois modos da PRE1; 50%, depois 60%, depois 70% **do restante** sobre 100 unidades dão saídas 50/30/14 e runner 6. Cada evento confirmado vincula ID da posição, tranche, quantidade, instante e preço sintético; repetição de ID/payload/preço exatamente igual é contada uma vez, e conflitos são rejeitados.
- `gross_realized_reference = soma_lado((preço_referência_saida − entrada_referência) × quantidade)`; `gross_runner_reference = lado × (último_mark_referência − entrada_referência) × quantidade_ainda_aberta`. LONG usa sinal +, SHORT sinal −.
- Taxas e slippage de entrada são aplicadas **à posição inicial inteira**, mesmo com runner aberto. Custos de saída só incidem sobre tranches declaradas efetivamente preenchidas; não criar uma liquidação implícita do runner. Todos os quatro bps são declarados e não comprovam tabela real da venue.
- Funding é uma hipótese explícita, assinada: taxa positiva LONG paga e SHORT recebe. Para prevenir dupla contagem sobre partes já vendidas, o notional sintético de cada evento precisa igualar `quantidade_restantante_no_instante × preço_referência_de_entrada`. O preço de entrada é usado **deliberadamente** como referência fixa; não simula marcação de funding real. Eventos na mesma marca temporal de um exit são ambíguos e bloqueados, assim como eventos futuros, IDs conflitantes ou notional que ignore parciais.
- Resultado total descritivo: `realized_gross + residual_gross − entry_costs − exit_costs − signed_funding_cost`, sem arredondamento de lote e sem dividir por margem de moeda não homologada. `leverage_at_open` é carregada mas **não** usada como multiplicador de PnL; mudar alavancagem global afeta apenas novas posições.

## Proteções e limites

Todas as marcas devem ser conhecidas até `as_of_ms`; `mark_observed_at_ms` precisa suceder abertura e preenchimentos e respeitar `max_mark_age_ms` (até sete dias). A rotina falha em saldo excedido, tranche fora de ordem, preços inválidos/float/NaN, funding inconsistente, IDs e payloads repetidos com divergência, ou cotação que chegaria após o instante de pesquisa. Trabalha exclusivamente em memória e com `Decimal` independente do contexto global.

A saída `sanitized_report()` contém apenas agregados financeiros **sintéticos** e quantidades, sem tickers, identificadores de ordens, preços individuais ou dados de conta. Todas as flags de `financial_backtest_approved`, `realized_pnl_verified`, `liquidation_risk_verified`, `actual_margin_return_available`, `approved_for_live_use` e `orders_sent` permanecem `false`.

## Caso de referência

Fixture LONG com entrada 100 quote/unidade, posição inicial 100 unidades, tranches 50@110, 30@120, 14@90, runner 6 marcado a 130, taxas entrada/saída de 10bps e slippage adverso entrada/saída de 5bps, funding LONG 2bps sobre notional sintético residual 5.000 depois da primeira tranche:

| Termo | Valor quote hipotético |
| --- | ---: |
| Ganho bruto das parciais | +960,00 |
| Marca bruta do runner | +180,00 |
| Custo total de entrada | −15,00 |
| Custo total de saída das 94 unidades | −15,54 |
| Funding assinado | −1,00 |
| Marca líquida sintética total | **+1.108,46** |

Os valores são exagerados propositalmente para facilitar conferência aritmética e **não são** recomendação de mercado, retorno de 50x, backtest OOS ou PnL realizado. Falta homologação de fills, mark, contrato, fee tier, funding real, liquidação, trajetória intrabar, spread, lot size e risco agregado.

## Aceite

`tests/test_synthetic_partial_costed_replay.py` valida LONG/SHORT, 50/60/70, runner não vendido, abertura sem saídas (custo de entrada presente), preenchimento parcial, funding pós-saída, dedup exato e colisão ID/preço, relógio/mark obsoleto, precisão Decimal e snapshot 50x imutável após alteração global para 20x. CI Linux/Windows/PAPER e suíte VPS antes do merge. Nenhuma publicação de código em serviço de produção; J4 #5 permanece aberta até estudos prospectivos e ledger real homologado.
