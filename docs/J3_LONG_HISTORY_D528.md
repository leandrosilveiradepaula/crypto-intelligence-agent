# D528 — histórico longo, retomável e separado do residente

Prioridade PO 24/11/2026: aumentar a amostra substancialmente. Base de 90 dias primeiro, 365 e até 730 dias, independente do horizonte de cada operação. 50x e RSI exclusivamente confirmação; dimensionamento D527 adiado. D526 real: 140 cenários, 83 positivos, 43 negativos, 14 sem dados, mesma janela curta de 24h/4h; não repetir. Ver issue #4 e recibo #752. D525 integrado sem publicação (main 64863220c7b7c2182a03fa3e7b95f0a6c6fc3044); não alterar J1.

## Primeira entrega útil

- Congelar uma coorte D451 atual de 50 perpétuos USDT provisórios, com BTC, launchTime e impressão digital do snapshot. **Amostra de sobreviventes**, não Top50 histórico de mercado; deslistados e universo completo pendentes. Nunca fingir snapshots D461 históricos. Essa primeira coorte serve à pesquisa inicial de indicadores; próxima expansão deve abranger catálogo independente e deslistados quando disponíveis.
- Página REST explicitamente opt-in de 1h/5m até 1000 velas; reaproveita transporte fixo Bybit, parser, HistoricalBackfill e SQLiteMarketDataStore. Default e limites residentes inalterados. Requisições em série com espaçamento mínimo 2s, até 400 GETs de velas por lote, mais captura inicial D451, sem retry automático em erros de acesso/rede/quota; preservar páginas confirmadas. Lote até 30min, manter 1GiB livre, sem custo. Coordenar horário com coleta residente; não parar J1.
- Plano imutável com cutoff de dia UTC fechado, shards de 30 dias, recorte no primeiro candle inteiro após lançamento. Estender 90→365→730 reutiliza todos os shards anteriores; 365 arredonda para 390 dias planejados, 730 limitado ao máximo. Usar mesmo diretório e plano para 1h e 5m. Não preencher lacunas. Falha de página de um ativo não apaga os demais; cobertura por ativo e shard, novos GETs contabilizados. Mesmo plano pode ser retomado por até 30 dias após snapshot; prazo evita fingir metadados atuais, não prazo de retenção dos dados. A coleta não inclui mark/funding nem histórico de mudanças de contrato.
- Leitura offline exata de janelas entre shards sem criar banco e função de rank causal por turnover das 24h anteriores dentro da coorte congelada. Se faltar qualquer ativo elegível, não fabricar ranking. Ainda não integra o replay longo D526: próximos trabalhos são adaptador de pesquisa causal, horizontes 24/48/72h, métricas por mês/regime e holdout cronológico, universo mais amplo. Não alterar D512 para falsificar arquivos contemporâneos.
- Código/fixtures novos, nenhuma coleta real ou resultado financeiro até execução owner. D528 não instala timers, não acessa conta ou perfil, não envia ordens. Até 2/2,5% a 50x permanecem contrafactuais enquanto liquidação não modelada.

## Execução em checkout exato aprovado (owner não root)

Criar diretório privado novo 0700, nome iniciando d528-history, com disco suficiente. Confirmar direitos de uso pessoal privado e elegibilidade regional antes da coleta. Não distribuir dados. Primeiro comando, apenas após aceite do código:
```bash
python -m scripts.run_j3_long_history_d528 \
  --directory "$HISTORY" --init --days 90 --interval 1h --low-priority \
  --allow-public-network --confirm-personal-readonly-research \
  --confirm-region-eligible --confirm-public-data-rights
```
Retomar com os mesmos argumentos sem --init. Para estender, mudar --days para 365 e 730; para 5m usar --interval 5m. Um lote parcial não é aceite integral. O relatório JSON contém expected/saved/missing e número de GETs. Estimativa 365 dias 50 ativos continuamente: 438000 velas horárias, 5256000 de 5m; launch e cobertura efetiva variam. Primeiro 1h em 90 dias, depois 5m por lotes, sem rebaixar a ambição de histórico longo. Não executar sem autorização aplicável nem contornar bloqueios de acesso. Docs oficiais: https://bybit-exchange.github.io/docs/v5/market/kline e https://bybit-exchange.github.io/docs/v5/market/instrument.
