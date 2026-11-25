# D536 — dados de funding e mark price para posições longas

## Evidência e prioridade

D535 concluído no owner: 365d/1h, 240 cenários, 276395 slots pareados, 11/240 positivos antes de funding (2/7/30/60/90d: 0/0/3/2/6). Melhor 90d w04_v15 wide protegido após TP1, 150bps: 289 caminhos, 142 positivos com marks, 9 abertos, +26,3211 USDT, 18,22bps, PF1,2207; realizado -41,6806, não realizado bruto +68,1065. TP4 10% sem proteção extra: +0,60239375 totalmente realizado, 52/289 TP4, PF1,0042. D535 integrado 17575948eeb1d1c8babe38e7e7b74a2eca52abcc, árvore 9cb8dfca3af26d5978d03288a8899c76d7a311a0, CI 45646814867/45646814822 SUCCESS, revisão 6060609070. Não repetir anual 1h nem 90d 5m. A coleta anual 5m foi interrompida por retCode10006; quantidade atual desconhecida. Manter 365/730d, 50x, stops, sizing adiado, 36d reservados.

## Contrato de aquisição

Reutiliza plano D528, coorte congelada, lock owner e transporte HTTPS fixo sem retry. Rotas opt-in D536:
- https://bybit-exchange.github.io/docs/v5/market/history-fund-rate — fundingRate é fração decimal; janelas de 30d, limite 200; subdividir somente páginas saturadas, em intervalos disjuntos, sem tratar a página truncada como calendário completo.
- https://bybit-exchange.github.io/docs/v5/market/mark-kline — mark-price 1h/5m, até 1000 OHLC por página; não fabricar volume ou tratar como preço de negócio.
- https://www.bybit.com/en/help-center/article/UTA-Trading-Rules-Liquidation-Process — liquidação usa mark e manutenção; tiers históricos, modos de margem, funding deduzido, taxas e política de liberação de margem ainda precisam de modelagem e evidência.

Páginas normalizadas owner-only imutáveis, hash do corpo bruto e identidade/sha256 do conteúdo normalizado, modo 0600, fsync. Checkpoints independentes dos candles; sem redownload de páginas guardadas, inclusive saturadas. Uma página vazia ou não saturada prova apenas resposta à consulta, NÃO calendário de liquidação do funding. Mark parcial fica identificado, nunca interpolado. Relatório de cobertura sem rede por padrão; trade-1h/5m mede janela EXATA, não o arredondamento de shards D528. D536 usa janelas ancoradas de 30d (relatório distingue solicitado/planejado), limite 100 GET por execução e 10..12s de espaçamento. Não repetir automaticamente 10006 nem usar outra rota para contornar quota; executar coleta separadamente da coleta de trade candles. Sem J1, PAPER, perfil, release, ordens, custo. Não há dados D536 reais ainda.

## Cálculo de funding

FundingExposure registra taxa observada e intervalo de quantidade remanescente/mark no instante de cobrança. funding_cost_bounds usa LONG paga taxa positiva, SHORT recebe; taxas negativas invertem sinal. Exige sequência de timestamps fornecida explicitamente e não transforma falta de evento em zero. Limites de quantidade e mark representam ambiguidade de parciais e candles; não declara saldo real nem prova cobertura histórica. É primitiva testada por fixtures, ainda NÃO conectada ao D529: faltam trilha de exposição de cada caminho, calendário efetivo histórico e mark, política de margem pós-parcial, tiers e reconciliação com ambos cenários intrabar. Não reutilizar tiers atuais como históricos. Sem escolha financeira, OOS, carteira ou ordens.

## Execução owner após CI

python -m scripts.run_j3_derivatives_history_d536 --directory <D528> --days 365 --dataset trade-5m --low-priority (sem GET, mede progresso).
Para funding, mark-1h, mark-5m, trocar dataset; sem --collect é leitura. Para coletar, --collect --max-gets 100 --request-spacing-seconds 10 --allow-public-network --confirm-personal-readonly-research --confirm-region-eligible --confirm-public-data-rights. Não executar em paralelo com D528 e não insistir se quota bloqueada. Priorizar funding e mark-1h depois de restabelecimento autorizado; mark-5m complementa trade-5m. Após coleta, integração de ledger temporal de exposição/rates e estudo de manutenção, sem reotimização sobre holdout. 730d após cobertura anual. CI e execução real pendentes.
