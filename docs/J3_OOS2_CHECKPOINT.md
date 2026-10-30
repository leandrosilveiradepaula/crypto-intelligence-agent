# J3/OOS2 — linha de base OOS com opt-in privado

Issue #363, 30/10/2026. Esta entrega parcial adiciona `--costed-oos --oos-cost-bps 5` à CLI `scripts.replay_private_vision_dynamic` já existente; o valor 5 é apenas um exemplo sintético, não tarifa de corretora. Reutiliza exclusivamente os manifests e ZIPs privados já auditados e `costed_vision_monthly_oos`; o relatório `hypothetical_costed_oos` publica somente agregados sem símbolos, preços ou caminhos. A execução não cria dados e não chama a rede.

Sem a flag, o comportamento legado permanece inalterado. O custo explícito não pode ser fornecido sem a flag, nem a flag sem o custo. Com `--audit-intrabar-stress` a saída inclui seções distintas de pesquisa; não somar os resultados como operações independentes.

A issue #363 permanece aberta para os próximos blocos: fold por período com benchmark LONG sob as mesmas barras, downside/upside e drawdown proxy para cada ramo, testes de monotonicidade e privacidade. Esta PR não os declara entregues.

**Gates:** `financial_backtest_approved=false`; `marketwide_top50_verified=false`; `live_trading_authorized=false`; `orders_sent=false`. J1 #2/#217/#319, J2 #3 e J3 #4 abertas. Pesquisa pessoal histórica não produtiva; sem downloads, ordens, releases, migrations, segredos ou gastos adicionais. Testes de regressão em `tests/test_replay_private_vision_dynamic.py`; exigir CI Linux/Windows/Chrome no SHA final antes do merge.
