# J3/OOS2 — linha de base OOS com opt-in privado

Issue #363, 30/10/2026. Esta entrega parcial adiciona `--costed-oos --oos-cost-bps 5` à CLI `scripts.replay_private_vision_dynamic` já existente; o valor 5 é apenas um exemplo sintético, não tarifa de corretora. Reutiliza exclusivamente os manifests e ZIPs privados já auditados e `costed_vision_monthly_oos`; o relatório `hypothetical_costed_oos` publica somente agregados sem símbolos, preços ou caminhos. A execução não cria dados e não chama a rede.

Sem a flag, o comportamento legado permanece inalterado. O custo explícito não pode ser fornecido sem a flag, nem a flag sem o custo. Com `--audit-intrabar-stress` a saída inclui seções distintas de pesquisa; não somar os resultados como operações independentes.

A issue #363 permanece aberta para os próximos blocos: fold por período com benchmark LONG sob as mesmas barras, downside/upside e drawdown proxy para cada ramo, testes de monotonicidade e privacidade. Esta PR não os declara entregues.

**Gates:** `financial_backtest_approved=false`; `marketwide_top50_verified=false`; `live_trading_authorized=false`; `orders_sent=false`. J1 #2/#217/#319, J2 #3 e J3 #4 abertas. Pesquisa pessoal histórica não produtiva; sem downloads, ordens, releases, migrations, segredos ou gastos adicionais. Testes de regressão em `tests/test_replay_private_vision_dynamic.py`; exigir CI Linux/Windows/Chrome no SHA final antes do merge.

## Segunda entrega #363 — auditoria de benchmark e drawdown condicional

A avaliação mensal `vision_stress_oos` registra, sem abrir posição, as barras pontuadas e as exposições/ambiguidades por fold OOS. O benchmark LONG é avaliado no mesmo ativo selecionado causalmente a cada barra do teste inclusive quando a estratégia abstém; resultados downside/upside são calculados sob condições intrabar mutuamente exclusivas. Drawdown é somente proxy de soma de resultados hipotéticos quote em cada ramo, sem capital, cronologia intrabar comprovada, preço mark, fórmula de liquidação real ou gestão de risco da corretora. O resultado de benchmark não é retorno financeiro observado. A diferença de exposição entre benchmark e estratégia impede comparação econômica direta sem normalização posterior.

Gates de #2/#217/#319/#3/#4 e toda proibição de ordens ou release continuam inalterados. Após CI e merge seguro, manter #363 aberta até aferir riscos e limitações em testes adversariais adicionais; não declarar validação financeira real.

## Revisão final da issue #363

PR #364 integrada em `1a6bf869fafafb7c4e180b263a1db89917033303`, PR #365 em `744e4f263c3a5f5e0530619476d3202f479b51b5` após CI Linux/docs, Windows offline e Chrome/PAPER verde no head. A auditoria permanece matemática condicional e a magnitude por margem não representa VaR/probabilidade nem liquidacão oficial. Esta revisão adiciona regressões específicas de aumento de taxas, digest dependente de pressupostos, privacidade da saída e invariância do calendário OOS sob alteração de volume posterior. Testes e CI no head da revisão final devem ser verificados antes de fechar a issue.

## Falha CI e correção financeira conservadora (30/10/2026)

A CI da PR #366 identificou uma regressão verificável: no caso de liquidação hipotética, aumentar taxas de 0 para 10 bps tornava a perda agregada menos negativa (`-1440` para `-1438.7040`), porque a fórmula anterior assumia saída executável precisamente no preço de gatilho de liquidação, que se deslocava com a taxa. Isso não é defensável como piso de risco. A correção em `vision_intrabar_stress.py` não credita execução nesse preço: quando há toque de liquidação proxy no ramo adverso, considera exaustão da margem solicitada, custos adversos explícitos calculados no nocional de entrada e financiamento pago positivo. É uma convenção *hipotética conservadora*, não fórmula da exchange, garantia de perda máxima nem PnL. Testes long/short verificam monotonicidade e gates. Não relaxar o teste que detectou o defeito; novo head e todas as CI devem passar antes de merge.
