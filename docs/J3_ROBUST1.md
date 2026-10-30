# J3/ROBUST1 #367 — Sensibilidade adversa do risco OOS (30/10/2026)

Objetivo: analisar a fragilidade das hipóteses quantitativas diante de **custos, slippage, manutenção e funding alternativos**. Esta é pesquisa offline, não modelo validado de execução ou liquidação de Bybit/Binance.

## Contrato e cenários
- Reutilizar `costed_vision_monthly_oos` para congelar a seleção do mês de teste com dados anteriores, sem retreinamento no mês OOS.
- Reutilizar `audit_costed_vision_intrabar_oos`, que trabalha apenas com candles Vision já auditados de pesquisa pessoal não produtiva. O envelope é condicional a OHLC; não determina a ordem real dos eventos.
- Quatro hipóteses explícitas: base; aumento não negativo de fee de entrada/saída, slippage de entrada/saída e manutenção; mesmas taxas adversas com funding assinado aumentado; mesmas taxas adversas com funding assinado reduzido.
- Os choques são seis parâmetros `Decimal` em bps, tipados, finitos e limitados. O funding alternativo **não** é evento real de settlement: aplica uma hipótese por posição/candle. Taxa positiva é custo para LONG e crédito para SHORT neste modelo. Não supor monotonicidade de resultados para choques de funding em carteira LONG/SHORT mista.
- O cenário de custo/manutenção adverso, com funding constante, só é aceito se não melhorar resultados condicionais best/worst, para a estratégia e o benchmark, e se preservar a mesma seleção e exposição OOS. Uma inconsistência interrompe a auditoria.
- Métricas expostas: exposições, contagens de condições de liquidação proxy, worst/best, drawdown proxy, perda máxima por margem fictícia, digests e pior cenário entre as quatro hipóteses. Não apresentar retorno esperado, VaR probabilístico, trajetória executável, retorno ajustado ao risco real nem limite garantido de perda.

## CLI restrita
`scripts.replay_private_vision_dynamic` exige `--allow-personal-nonproduction-research` e manifests de ZIP existentes. O modo `--audit-stress-sensitivity` exige também `--audit-intrabar-stress`, os nove parâmetros de stress originais e **seis** parâmetros explícitos:

```
--risk-extra-entry-fee-bps 5
--risk-extra-exit-fee-bps 5
--risk-extra-entry-slippage-bps 5
--risk-extra-exit-slippage-bps 5
--risk-extra-maintenance-bps 5
--risk-funding-shock-bps 20
```

Valores acima são **fixtures ilustrativas** e não representam tarifas, juros de funding, limites ou instrumentos da exchange. Nenhuma chamada de rede, escrita, ordem, serviço, deploy, migração ou gasto adicional.

## Verificação e aceite
- Testes `test_vision_risk_sensitivity.py` e `test_replay_private_vision_dynamic.py`: custo adverso, LONG/SHORT implícitos na seleção, funding +/-, 50x vs 1x, ordenação de ativos, hashing sensível aos parâmetros, limites Decimal, CI POSIX/Windows e privacidade da CLI.
- Revisar efeito de cada hipótese na representação de liquidação conservadora criada na PR #366; não reutilizar preços de gatilho como fill real.
- CI docs/Linux, Windows/offline e Chrome/PAPER no SHA final; review técnico, merge seguro sem publicação em produção. Registrar PR e SHA da integração após ocorrer, sem antecipá-los.

## Gates permanentes
`financial_backtest_approved=false`, `marketwide_top50_verified=false`, `source_authenticated=false`, `funding_schedule_verified=false`, `liquidation_formula_verified=false`, `live_trading_authorized=false`, `orders_sent=false`. J1 #2/#217/#319, J2 #3 e J3 #4 permanecem abertas. D77: automatizar trading no produto final apenas após testes, aprovação e gates próprios.

Referências oficiais, sujeitas a confirmação de contrato/versão antes de qualquer uso operacional:
- https://bybit-exchange.github.io/docs/v5/market/mark-kline
- https://bybit-exchange.github.io/docs/v5/market/history-fund-rate
- https://bybit-exchange.github.io/docs/v5/market/risk-limit
