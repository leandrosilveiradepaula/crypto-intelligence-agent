# D518 — Refinamento de saídas em 5 minutos

## Entrega
Refina a simulação D517 com velas públicas de cinco minutos e compara os mesmos sinais, perfil e horizonte com uma referência de 1h sobre a amostra comum. O usuário escolhe a resolução e o horizonte de 1 a 12h. Sem alteração da estratégia operacional.

## Dados e limites
- Bybit V5 GET /v5/market/kline, interval=5, consulta pública documentada em https://bybit-exchange.github.io/docs/v5/market/kline; sem credenciais. O modo de transporte é opt-in e default J1 permanece exclusivamente horário. Janela de até 36 horas, 432 velas por símbolo, união limitada a 80 símbolos e 80 GETs, pacing existente, sem retries.
- Âncora em membros de arquivos REST originais consecutivos; nenhuma recomposição retroativa do ranking. Suplemento privado imutável com digest e data real de recuperação, separado de D461/D516 e do journal PAPER.
- Só avaliar trajetória completa quando toda hora original é reproduzida pelos 12 OHLC de 5m; preços de avaliação futuros não modificam as entradas. Sem substituição silenciosa por 1h se faltar o dado de 5m.
- Dentro de cada vela de 5m, extremos ainda não têm ordem conhecida. Cenários adverso/favorável não são limites garantidos, e a soma de hipóteses não é resultado de carteira. Sem mark price, funding, liquidação ou execução comprovados. Não alegar backtest financeiro validado nem resultado OOS.

## Uso após integração
O CLI owner existente aceita:
```bash
python -m scripts.run_j3_retrospective_warmup_d516 \
  --historical-directory "$HISTORY" --policy-file "$POLICY" \
  --history-hours 122 --ema-periods 10 30 60 --horizon-hours 4 \
  --resolution 5m --allow-public-network --confirm-personal-readonly-research \
  --confirm-region-eligible --confirm-public-data-rights
```
Os períodos e horizonte são exemplos. Captura D516 e D518 na mesma execução isolada; `--reuse` usa os suplementos sem GET externo. A rota privada aceita `&horizon=4&resolution=5m` (opcionalmente `&retro=1` antes de horizon). Se faltar suplemento, resposta explícita de indisponibilidade. Nenhum acesso à rede via rota HTTP do painel.

## Aceite
Testar forma/limites do GET e rejeição no transporte default, digest e relógio, 12 barras por hora, conflito OHLC, preservação das hipóteses, ordem observável entre velas, comparação de amostra comum e ausência de futuro. CI/revisão antes de merge; nenhuma coleta real ou deploy D518 nesta entrega. Sem custo ou ordem.
