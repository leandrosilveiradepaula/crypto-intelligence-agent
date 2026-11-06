# J3/PRE28 — gate causal de co-perda por correlação sintética (D248)

## Contexto e decisão
O replay PRE19 calcula correlações descritivas entre marcas do caminho inteiro, mas essa métrica não pode liberar uma posição num checkpoint passado: seria olhar o futuro. O PRE20 controla risco de carteira por margem, nocional bruto/líquido, concentração e drawdown, sem gate de pares potencialmente co-perdedores. A issue #500 cria uma camada **opt-in**, independente e apenas de pesquisa para preencher essa lacuna sem modificar o comportamento legado.

## Contrato
- Módulo `synthetic_portfolio_correlation_gate.py`: chama **antes de tudo** o gate PRE20 `audit_synthetic_portfolio_risk`, preservando seus testes de horários, funding, liquidação, custos e risco PIT. Não reimplementa o limite financeiro ou simula ordens.
- `SyntheticCorrelationGate(max_positive_signed_return_correlation: Decimal, minimum_return_samples: int)` exige limite em [0, 1] com representação Decimal finita e amostra mínima de 3 a 128 retornos. Máximo de 16 posições e 256 ticks para orçamento CPU de correlação por prefixo.
- Retornos de preço de marcação são calculados por tick, `mark[t]/mark[t-1]-1`, e assinados por direção de PnL: LONG positivo, SHORT negativo. Correlação positiva de duas pernas com o mesmo lado representa co-movimento adverso potencial; LONG/SHORT com a mesma série resulta em correlação negativa, mas **não** comprova hedge real.
- Pearson incremental guarda somente estatísticas acumuladas de cada par, sem acessar dados de ticks futuros. Um par só é considerado enquanto ambas as pernas estiverem no estado `OPEN_UNRESOLVED` nos ticks consecutivos. Par com preço constante, histórico curto ou variância nula produz `insufficient_or_flat_pair_history_abstain`, jamais segurança presumida.
- Qualquer correlação que **ultrapasse** o limite explícito marca `positive_correlation_limit_exceeded` de forma conservadora durante todo o restante do replay; violações do PRE20 e liquidação desconhecida também impedem elegibilidade. Sem par aberto, o estado `no_open_pair` herda o veto/aceite do PRE20.
- `new_position_research_allowed` é **somente** indicador retrospectivo da hipótese sintética; não é autorização para criar ordem, chamada REST/WS, testnet ou trading real.
- Relatório apresenta apenas códigos, contagens e correlação agregada Decimal por checkpoint e digest determinístico. Nenhum símbolo, fixture-ID, preço, endereço privado, segredo ou ordem. `financial_backtest_approved`, `net_pnl_verified`, `live_trading_authorized` e `orders_sent` sempre false.

## Validação
`python -m unittest discover -s tests -p test_synthetic_portfolio_correlation_gate.py -q` e regressões `test_synthetic_portfolio_replay.py`, `test_synthetic_portfolio_risk_limits.py`, `test_synthetic_mark_replay.py`. Fixture LONG/LONG correlacionada, LONG/SHORT anticorrelacionada por lado, SHORT/SHORT, preços constantes, veto PRE20, liquidação, fechamento de perna, alteração apenas do último tick sem mudar prefixos, precision Decimal, ordem de entrada de pernas e limite 256. CI Linux/docs, Windows/offline e Chrome/PAPER em SHA exato.

## Limites
Não estima diversificação estrutural nem risco de liquidação real, correlação condicional por regime, lucro líquido real, custo de execução ou permissões de corretora. A janela de apenas 3 a 128 retornos em pesquisa é parâmetro configurável, não quantidade universal suficiente para inferência estatística. Não substitui o teste OOS/walk-forward nem resolve J1 #2/#319/#429.
