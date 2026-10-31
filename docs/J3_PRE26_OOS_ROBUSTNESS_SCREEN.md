# J3/PRE26 — Triagem robusta de pesquisa OOS (sem aprovação financeira)

## Objetivo
`audit_oos_robustness` recebe `VisionStressSensitivity` existente e `OOSRobustnessPolicy` explícita. Retorna diagnóstico **por fold e cenário** com uma única condição agregada de pesquisa sintética; se qualquer caso for reprovado, `all_synthetic_conditions_met=false`. Não classifica cenários, não recomenda alavancagem e não aprova ordens reais.

## Política configurável
`min_test_folds` inteiro 1–24, `min_exposures_per_fold` inteiro 1–100000, `max_liquidation_proxy_fraction` e `max_intrabar_ambiguity_fraction` Decimal 0..1, `max_single_bar_loss_over_margin` Decimal 0..1000, `max_worst_drawdown_quote` Decimal 0..1e12 e `require_nonnegative_adverse_fold` bool. Limiar e requisito são fornecidos pelo pesquisador, **não** descobertos ou otimizados sobre o mesmo OOS. Rejeita float, NaN/Infinity, expoente excessivo, boolean mascarando inteiro, thresholds ausentes, folds inconsistentes, fingerprint alterado e divergência de exposições LONG pareadas.

Os motivos por fold são `insufficient_exposures_per_fold`, `liquidation_proxy_fraction_exceeded`, `intrabar_ambiguity_fraction_exceeded`, `single_bar_margin_loss_exceeded`, `adverse_drawdown_exceeded` e `negative_adverse_fold`; por cenário, inclui `insufficient_oos_folds` e `no_oos_exposure` se aplicáveis. Custos/drawdown são envelopes de um trade por barra com margem fixa, **não** retorno de carteira sincronizada, resultado líquido real ou forecast. O histórico OOS treinado é congelado antes dos cenários; não escolher policy ex-post como se fosse validação estatística.

## CLI privada, somente pesquisa
Executar a CLI existente `scripts.replay_private_vision_dynamic` no ambiente privado do titular somente com dados previamente auditados, opt-ins `--audit-intrabar-stress --audit-oos-leverage-pair --audit-oos-robustness`, todos termos de stress e os seis argumentos `--robust-min-folds`, `--robust-min-exposures-per-fold`, `--robust-max-liquidation-fraction`, `--robust-max-ambiguity-fraction`, `--robust-max-single-loss-over-margin`, `--robust-max-drawdown-quote`. A flag `--robust-require-nonnegative-adverse` ativa o requisito do pior ramo não negativo em cada fold. Falhas de input são sanitizadas e não acionam trading, GET ou extra leitura de manifesto. O resultado é campo aditivo `hypothetical_oos_robustness`; sem opt-in, formato legado preservado.

## Evidência e limites
Testes offline para 1x/50x, amostra sem entradas, custos adicionais, regra de qualquer fold/cenário, identidade causal, determinismo sob permutação, privacidade, CLI owner-only e não rede. CI Linux/docs+Windows/offline+Chrome/PAPER no SHA revisado. Mesmo `all_synthetic_conditions_met=true` NÃO representa `financial_backtest_approved`, `net_pnl_verified`, `liquidation_formula_verified` ou `live_trading_authorized`, todos falsos. J1 #2/#319 continuam aguardando captura VPS privada verificável; nenhuma coleta nova, credencial, ordem, deploy ou custo.
