# D526 — RSI 14 como veto de um sinal original

D524 confirmou 40 variantes de RSI no gatilho com dados, todas negativas; SMA20/50 passou de 22 para 66 sinais. Não é ablação de um filtro. Hipótese D526: usar o mesmo RSI Wilder e a mesma FR BTC, mas o RSI só é avaliado depois que o gatilho original, volume e FR aprovam o sinal. Ele pode rejeitar, nunca antecipar, atrasar ou criar uma entrada. A regra é exclusivamente de pesquisa; o perfil ativo e a confluência D523 permanecem intactos.

Matriz 20 estratégias: controles sem RSI e pares RSI 50–70/55–75, incluindo rompimento + veto (119 caminhos cobertos no controle D524). `rsi_filter` tipado independente de `rsi` (proibido combinar ambos); trigger opcional breakout somente quando todos indicadores de gatilho estão desligados e existe veto. Todos compartilham o mesmo warmup e caminhos, e cada linha filtrada reporta sinais originais, vetados e respectivas coberturas. A seleção com veto é subconjunto do gatilho/FR original na mesma janela, não comparação de sinais diferentes por transições do RSI. O preset privado `rsi_filter` e a CLI permitem a grade 50/75/100/125/150 bps, 100 cenários. Comparar médias, frequência, stops antes de TP1, MAE/MFE, custo e cobertura; não escolher vencedor pelo total bruto. O perfil operacional não é modificado.

Após revisão/CI, experimento isolado:
```bash
python -m scripts.run_j3_combination_research_d520 \
 --historical-directory "$HISTORY" --policy-file "$POLICY" \
 --matrix-file docs/examples/d526_rsi_filter_research_matrix.json \
 --as-of-ms 1795547640289 --horizon-hours 4 \
 --research-stop-grid-bps 50 75 100 125 150
```
Este mesmo corte é uma comparação exploratória, não OOS. Próximo: retomada de tendência após correção com regras causais de pullback e amostra de vários dias, funding/mark/liquidação. Sem ordens reais, alteração J1, custo ou publicação. D525 permanece pinado ao produto D524 aprovado; D526 não substitui uma versão publicada sem gate.
