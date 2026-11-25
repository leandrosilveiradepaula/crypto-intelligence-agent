# D531 — comparação de saídas e winner management

## D531 — saídas parciais e proteção em pesquisa (25/11/2026 UTC)

D530 integrado em dbf9d03678da8c9617c065dbfa16126dd17989d5, CI 45521088598/45521088705 SUCCESS, review 6049890764. D530 399 cenários ainda não executados; D529 real 420/420 negativos na ordenação adversa 1h. D531 acrescenta matriz JSON opt-in de saídas: perfil owner de referência e até 5 variantes de alvos/tranches/runner, proteção do preço de entrada após parcial e trailing após alvo escolhido, ambos efetivos apenas na barra seguinte e monotônicos. Não altera perfil nem comportamento padrão D517/D529. Compara as mesmas entradas e trajetórias, ambas as ordenações, custos, payoff médio e profit factor líquido pré-funding; não presume que stop no preço de entrada zere custos. Runner marcado ao fim do horizonte. Preset com 4 variantes; 19 estratégias x 3 stops x 1 horizonte x 5 saídas = 285 cenários numa triagem focalizada; grade completa opcional até 3000. Primeiro executar D530 no desenvolvimento; não repetir D529 nem consumir holdout. Coleta 5m continua bloqueada por erro não identificado, diagnóstico D530 aprovado; MCP sem UID owner. Sem ordens reais, sizing, custo, J1 ou publicação. Ver docs/J3_EXIT_RESEARCH_D531.md. Código candidato, CI/revisão e execução real pendentes.

## Hipóteses editáveis

- Referência: política de saída já lida do perfil owner, taxas e slippage preservados.
- 1/2/3% no preço: 25% da posição inicial em cada parcial, 25% residual.
- Mesmas parciais, stop do saldo no preço de entrada após TP1.
- Mesmas parciais, proteção após TP1 e trailing de 150 bps após TP2.
- 1,5/3/5%: 25% inicial em cada parcial, 25% residual.
- JSON também admite percentuais sobre saldo restante, alvos ordenados e piso do residual; validar conservação antes do replay.

Stop dinâmico usa somente extremo favorável de barra concluída em trajetória sobrevivente. Ativa na próxima barra, não melhora fills intrabar retroativamente e não afrouxa stop. Gap cruza stop pelo preço de abertura observado. Avaliar adverse-first e favorable-first separadamente. Preço de entrada não é breakeven líquido. Não modela mark/liquidação/funding/execução real. A 50x stops >=200bps são contrafactuais; não alterar sizing. Ganhos/perdas médios e profit factor são calculados por trajetória (líquidos pré-funding), não carteira ou previsão.

## Execução depois de CI/revisão e resultados D530

    python -m scripts.run_j3_long_replay_d529 --directory "$HISTORY" \
      --policy-file "$POLICY" --days 90 --partition development \
      --matrix-file docs/examples/d530_entry_controls_matrix.json \
      --entry-experiments-file docs/examples/d530_entry_experiments.json \
      --exit-experiments-file docs/examples/d531_exit_experiments.json \
      --horizon-hours 48 --stop-grid-bps 100 150 250 \
      --resolution 5m --low-priority > "$REPORT"

Exemplo focalizado, não escolha de vencedor. O arquivo de saídas é opcional; omiti-lo preserva D530. Ampliar para sete stops e três horizontes somente conforme custo computacional e evidências. Controle de cobertura e grade causal compartilhada; selecionar hipóteses apenas no desenvolvimento e congelar para teste posterior.
