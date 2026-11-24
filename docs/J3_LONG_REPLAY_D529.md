# D529 — replay de base longa

D528 integrado em 7ae59574b1b21e6a132e083fe729df0def874f52; CI 45510118117/45510118137 SUCCESS. Coleta real pendente, host_status confirmou 38,6 GB livres no volume global. D526 real 140 cenários em recorte curto, não repetir.

D529 reutiliza D513/D526 para hipóteses, D517 para saídas/custos, D518 para corroborar OHLC 5m vs 1h e D528 para dados privados. Modo exclusivamente REST retrospectivo calcula todos os eventos causais em cada sequência contígua numa passagem por configuração distinta. Estado contínuo de EMA/ATR/Pivot/RSI, não idêntico ao reseed de prefixo móvel D526. Lacunas interrompem sequência e exigem novo warmup. Não fabricar D461/WS ou mudar default J2/J4. Cap explícito 730 dias de candles 1h e 72h de trajetórias 1h/5m; D517 default 12h. Reusa saídas por direção/horizonte/stop, RSI somente veto; FR BTC 24h. Coorte sobrevivente atual, não Top50 histórico.

Partições UTC fixas 60% desenvolvimento / 20% validação / 20% holdout. Lê somente até o fim da partição solicitada, usa prefixo anterior para indicadores. Exclui decisões finais pelo horizonte máximo para garantir mesma grade e não cruzar partição. Holdout exige confirmação de hipóteses congeladas, não comprova independência. Relatório por mês e regime BTC 24h +/-1%, cobertura comum por horizonte, manifesto SHA256 dos dados lidos, matriz, perfil, métricas D517. OHLC 1h triagem preliminar, 5m refinamento. Sem funding, liquidação, caminho intrabar ou carteira verificados. Stops 2/2,5% contrafactuais a 50x. Não escolher vencedor; não alterar perfil ou serviços.

CLI após coleta e aceite:

    python -m scripts.run_j3_long_replay_d529 --directory "$HISTORY" \
      --policy-file "$POLICY" --days 90 --partition development \
      --horizon-hours 24 48 72 --stop-grid-bps 50 75 100 125 150 200 250 \
      --resolution 1h --low-priority > "$REPORT"

Matriz D526: 20 estratégias x 7 stops x 3 horizontes = 420 cenários por partição. Rodar 5m quando cobertura disponível, comparar caminhos correspondentes. Validação e holdout separados. Depois ampliar universo, 365/730d, pullback e compressão. Nenhuma ordem real ou custo.
