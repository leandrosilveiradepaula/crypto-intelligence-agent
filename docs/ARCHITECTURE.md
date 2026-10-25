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


## Registro de identidade Kraken — módulo somente pesquisa (J1/WU10)
A arquitetura conserva um seletor de Kraken isolado, **sem alterar** adaptador Binance atual, banco de dados ou ordens. O novo `crypto_asset_registry.py` recebe manifestos locais de ativos revisados e versionados; consulta um histórico em memória e só fornece `verified_crypto_bases` ao seletor `kraken_eligibility.py` quando o registro existia na data de mercado. A ligação usa o hash SHA256 completo para reprodutibilidade. Não faz GET/POST, não armazena payloads de terceiros nem cria tabelas/migrations paralelas. A futura integração de fonte pública deve reutilizar `ClosedCandle`, `UniverseSnapshot`, `SQLiteMarketDataStore` e `HistoricalBackfill`, após validação da unidade financeira, licença e cobertura. Política/schema: `docs/CRYPTO_REGISTRY.md`.


## Staging OHLC Kraken sem falsear volume (J1/WU11)
`kraken_candle_validation.py` verifica resposta pública de trade candles em memória, com grades UTC, Decimal, volume Decimal bruto sem unidade atestada (int64 documentado, string decimal observada), e janela de velas estritamente fechadas. Esta estrutura transitória NÃO é `ClosedCandle` nem `MarketDataStore`; não persiste, não fornece volume financeiro para estratégias e não cria pipeline paralelo. O adaptador canônico só será permitido após especificação confiável de base_volume, quote_volume, mínimos contratuais e universo cripto revisado, aproveitando os contratos e backfill já existentes.


## Gate de alavancagem referenciado a venue (J1/WU14)
`venue_leverage_gate.py` é um módulo de avaliação de pesquisa independente de UI, posições e corretora. Recebe tiers e metadados **injetados**, proveniência/tempo e exposição agregada em USD; apenas decide se uma nova hipótese de posição com alavancagem configurada extrapola o teto da faixa aplicável, sem reduzir a configuração global e sem modificar posições anteriores. Não contém tabela de alavancagens real hardcoded, ordens, APIs privadas ou persistência paralela. Não valida classes de criptomoedas (WU10), volume de candles (WU12), disponibilidade regional, garantias, taxas, margem de manutenção ou liquidação — esses cálculos pertencem a J3.


## Proteção decimal na fronteira de dados públicos (J1/WU15)
`decimal_json.py` decodifica objetos JSON de mercado público Kraken diretamente para `Decimal` nos números fracionários, recusando números fora da precisão suportada, chaves duplicadas e valores não finitos. `kraken_eligibility.py` e o probe WU12 não aceitam números já arredondados por Python `float` como entrada de notional/volume. Esta é uma proteção numérica independente da fonte de verdade temporal, contrato linear, unidade de volume, licenciamento de ativos ou permissão de negociação: não cria dados históricos nem altera a arquitetura de armazenamento.


## Cliente público Kraken somente leitura (J1/WU16)
`kraken_public_readonly.py` conecta endpoints Kraken públicos previamente pesquisados a `decimal_json.py`, `kraken_eligibility.py` (seletor de pesquisa consumidor opcional) e `kraken_candle_validation.py`, com transporte GET/clock injetáveis e modo offline por padrão. As respostas expõem campos allowlist e intervalo de captura; não há autenticação, redirects, retries automáticos, armazenamento ou ordens. O chart retorna OHLC somente no formato de **staging com volume bruto não interpretado**, pois `ClosedCandle` exige base/quote units comprovadas. Uma integração futura ao storage/backfill de WU2 deve aguardar prova de unidades, identidade/licença e cobertura histórica. Apenas o mecanismo de coleta/validação read-only é acrescentado, sem venue swap.
