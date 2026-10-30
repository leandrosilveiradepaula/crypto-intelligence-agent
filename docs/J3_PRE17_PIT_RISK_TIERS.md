# J3/PRE17 #369 — maintenance em faixas com snapshots point-in-time

Em 30/10/2026, o replay de ticks sintéticos `synthetic_mark_replay.py` passou a aceitar **opcionalmente** `risk_snapshots`, `max_risk_snapshot_age_ms` e `max_tick_gap_ms`. O caminho legado sem snapshots permanece válido e usa taxa de manutenção fixa do plano. Esta não é uma migração de dados, integração real ou simulação de liquidação autenticada.

## Contrato
- `SyntheticMaintenanceTier`: intervalo semiaberto de nocional **mark** `[lower, upper)`, última faixa sem limite, `maintenance_bps` em `Decimal` e dedução por faixa em unidades sintéticas de quote.
- Faixas contíguas, taxa não decrescente e dedução matematicamente contínua no limite. A primeira começa em zero com dedução zero; nunca extrapolar tiers de Kraken para Bybit.
- `SyntheticRiskSnapshot`: `fixture_...` por instrumento e versão, timestamps UTC `observed_at_ms <= effective_at_ms`. Uma versão futura não pode ser aplicada retroativamente. O snapshot inicial deve estar disponível até o instante de abertura; todos os snapshots fornecidos seguem ordem, identidade única e corte temporal.
- Cada tick usa **mark_price × quantity_base** para selecionar a faixa vigente e calcular maintenance = `mark_notional × bps / 10000 - deduction + close_reserve`. Funding sintético já liquidado antes do tick afeta equity, não o preço de trade. Stop/target usam **trade_price**. Caso a margem hipotética seja insuficiente, a saída é apenas `LIQUIDATION_CONDITION`, sem supor preço/ordem de preenchimento ou PnL.
- Com snapshots, um limite explícito para idade do snapshot evita uso de tabelas obsoletas. `max_tick_gap_ms` limita a distância de entrada ao primeiro tick e entre observações, mas **não comprova ausência de excursão intrabar**.
- Reutiliza `SyntheticFundingEvent` e os limites de 64 eventos, sem modificar regras de ordenação ou deduplicação.

## Aceite e limites
Regressões em `tests/test_synthetic_risk_tiers.py` cobrem continuidade numérica, bordas, versões futuras, mudança de risco entre ticks, mark divergir de trade, LONG/SHORT, funding, stale, gaps, Decimal e comportamento legado. Suites em Linux/docs, Windows offline, Chrome/PAPER no SHA final antes de merge. J1 #2/#217/#319, J2 #3 e J3 #4 continuam abertas. Nenhuma evidência de fonte real, venue tiers, margem cross, mark venue, cálculo de liquidação do provedor, executabilidade, alavancagem liberada ou lucro validado.

Referências documentais para contratos separados: Bybit V5 mark-price-kline, funding/history e risk-limit. São inspiração para cenários explicitamente fictícios; não foram adquiridos novos dados.
