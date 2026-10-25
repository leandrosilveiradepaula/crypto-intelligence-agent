# Arquitetura candidata para a J0

A tecnologia específica será escolhida por adequação, licenças e limites reais da VPS, não por preferência de framework.

## Módulos previstos
1. Adaptadores de futuros perpétuos: fontes públicas REST/WebSocket, metadados de contrato, OHLCV, mark price, funding, open interest quando disponível.
2. Pipeline de dados: ingestão, histórico, UTC, candles fechados, controles de lacuna/duplicação e histórico de composição do universo.
3. Feature Engine: indicadores determinísticos sem acesso a dados futuros.
4. Strategy & Regime Engine: contexto BTC, tendências, rompimentos, compressão, correções, força relativa, liquidez e ranking.
5. Position Ledger & Risk: margem e alavancagem de abertura, PnL realizado/não realizado, custos, funding, exposição e correlação.
6. Winner Management: alvos, saídas parciais, trailing e posições residuais.
7. Research: backtesting com mesma semântica de sinais da operação prospectiva, liquidação intrabar e walk-forward.
8. API/UI: acesso protegido às posições do usuário; interface PT-BR mobile e alertas idempotentes.
9. ML/LLM: extensões opcionais submetidas a validação independente.

## Candidatos gratuitos
Python, bibliotecas científicas, FastAPI, PostgreSQL, DuckDB/Parquet, CCXT, Freqtrade quando compatível e n8n existente, se útil. Nenhum deles é obrigatório antes de uma decisão de arquitetura registrada.

## Fronteiras
Serviços de mercado são read-only. Não implementar endpoints de ordens reais nesta fase. Nunca guardar segredos no GitHub público. Estados e cálculos financeiros devem ter precisão, idempotência e testes independentes.
