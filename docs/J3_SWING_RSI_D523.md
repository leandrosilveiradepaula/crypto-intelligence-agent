# D523 — qualidade de entradas, RSI do ativo e stop de pesquisa

Pedido explícito PO 24/11/2026: orientar pesquisa a swing trade, aumentar distância de stop nos experimentos e incluir RSI 14 próprio do ativo, sem substituir FR contra BTC. D521: 119 caminhos completos do rompimento + FR, 90 stops, 75 negativos, 44 positivos; pelo menos 15 positivos com stop. Não é prova de reversão imediata.

RSI de Wilder: N diferenças de fechamentos, semente média aritmética dos ganhos e perdas, suavização (N−1)/N, RSI = 100 × ganho/(ganho+perda), flat = 50. Campo opcional e configurável: enabled, period 2..120, long_min 50..99, long_max maior que long_min até 100. LONG se long_min < RSI <= long_max, SHORT por espelhamento; 50 neutro. Só velas fechadas, warmup N+2 para transição; a inicialização depende do prefixo causal disponível. RSI participa da confluência D513 e pode mudar o instante da transição, não é só ablação de um filtro pós-sinal. A FR BTC continua sendo filtro separado. Perfis sem RSI continuam aceitos; não alterar perfil ativo.

Matriz D523 independente, 16 hipóteses adicionais (7 controles pareados sem RSI, 7 versões RSI 14 50–70 e 2 versões 55–75) e 2 controles históricos. Não altera a matriz D521 de 25. API local D522 admite preset original/swing e stop_bps inteiro de 1..1000, exclusivamente pesquisa, ou matriz customizada sem preset. CLI aceita --research-stop-bps. Valores para comparação inicial: 50, 75, 100, 125, 150 bps, com mesmo cutoff, matriz, perfil, horizonte e saídas. A UI permite executar cada variante; comparar por nome, número de candidatos e cobertura, não por posição no ranking. A 50x, 100 bps implica perda bruta de 50% da margem, 150 bps 75%; nenhum cenário comprova sobrevivência à liquidação (mark, margem de manutenção, custos e gaps). Não mudar leverage ou stop PAPER salvo. Sem ordens reais.

Métricas novas: stop sem TP1, stop sem TP1 na primeira hora, stop sem TP1 seguido por toque de TP1 em barra estritamente posterior, positivos com stop, MAE e MFE médios de toda trajetória (inclusive depois de uma saída hipotética). Não pressupõem recuperação dentro de uma vela, fill ou liquidação. São descritivas e usam apenas caminhos completos corroborados. Preserva contagem de ambiguidade econômica. Um stop mais largo não melhora necessariamente a expectativa.

Primeiro experimento reproduzível em checkout aprovado, UID owner, suplementos D518 salvos, sem rede:
```bash
for STOP in 50 75 100 125 150; do
  python -m scripts.run_j3_combination_research_d520 \
    --historical-directory "$HISTORY" --policy-file "$POLICY" \
    --matrix-file docs/examples/d523_swing_rsi_research_matrix.json \
    --as-of-ms 1795547640289 --horizon-hours 4 --research-stop-bps "$STOP"
done
```
Mesmo perfil deve ser mantido durante toda bateria; conferir revisões e manifestos dos relatórios. D518 só tem 36h de suplementos e D512 seleciona até 24 pares, replay 1..12h; **não é backtest swing de vários dias**. Próxima frente: amostra histórica PIT mais extensa, 24/48/72h com cobertura causal e funding/mark/liquidação, múltiplas condições de mercado, holdout cronológico. Não reconstruir N50 usando ranking atual retroativo. Nenhuma decisão de estratégia vencedora.
