# D520 — Bateria exploratória de estratégias combinadas

## Objetivo
Comparar grupos de indicadores, especialmente SMA 20/50 + força relativa ao BTC + Pivot Point SuperTrend, usando o mesmo motor e amostra já observada, sem salvar um perfil operacional. Matriz de pesquisa independente e editável (`--matrix-file`), com 15 combinações novas e os dois controles anteriores. Pode conter 1..24 combinações distintas. O arquivo de exemplo versionado fixa as hipóteses, incluindo ablação do Pivot, ajuste de parâmetros, EMA/SMA híbridas e força relativa mais exigente; não é uma recomendação.

## Contrato
- Usar o mesmo conjunto de arquivos D461 e suplementos D516/D518, carregados uma única vez, congelados por `--as-of-ms`; cada perfil recebe o mesmo aquecimento causal máximo, mesmos filtros de volume e cooldown. Força relativa: retorno open-to-close de 24h do ativo menos o retorno de 24h do BTC; LONG exige FR acima do limiar, SHORT abaixo do negativo. Limiar 0 conserva a regra anterior. FR 50/100 bps significa diferença de 0,5/1 ponto percentual. A transição D513 determina o momento da hipótese; os filtros de FR atuam nesse instante, não abrem posição mais tarde por si.
- Resolução 5m, horizonte editável 1..12h, entradas de 1h, mesmos parâmetros econômicos e parciais do perfil salvo, sem alterá-lo. Sem dados suficientes, cobertura explícita. Comparação de 5m apenas com OHLC corroborado; ordem dentro de cada vela continua ambígua. Nenhum GET externo.
- Relatório: oportunidades comuns e cobertas, hipóteses LONG/SHORT, cobertas, taxa de positivos, stops, parciais, residual, perda >= margem solicitada, ambas somas e médias pré-funding, custos e exemplos dos dois primeiros sinais cobertos (cronológicos, nunca escolhidos por ganho). Compara também resultado por ativo-hora coberto comum, não capital investido. Lista todas as hipóteses ordenadas por filtro descritivo de amostra e média após custos no cenário adverso. Limiar padrão 20 completos e 70% de cobertura ajustável; não significa significância nem aprovação de trade. Referência LONG permanece no relatório completo, não ranqueada como estratégia.
- Recibo D518 já conhecido; como a matriz foi definida depois de ver a amostra, qualquer resultado é exploratório e não OOS. Não otimizar no mesmo dia e declarar vencedor. Teste futuro com regras congeladas, amostra temporal independente, funding/mark/liquidação e exposição é indispensável. Sem execução, carteira ou ordens reais.

## Execução owner em checkout isolado aprovado
```bash
python -m scripts.run_j3_combination_research_d520 \
  --historical-directory "$HISTORY" --policy-file "$POLICY" \
  --as-of-ms 1795547640289 --horizon-hours 4
```
O cutoff fixa a recuperação D518 já executada e evita mover a janela durante a bateria. O relatório contém hash da matriz e dos suplementos; `--full-json` preserva também todos os hashes dos arquivos e as métricas completas. Sem gravação de perfil, ledger ou dados de mercado; não precisa instalar o laboratório novo nem baixar novamente velas. A política econômica lida é a salva na hora da execução; se alterada, os resultados não são diretamente comparáveis ao recibo anterior. CI, testes e revisão devem preceder merge; execução real requer UID owner. Não alegar resultados novos antes do recibo.

