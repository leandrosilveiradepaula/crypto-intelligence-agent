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


## Gate de licenciamento de dados de mercado (J1/WU17)
Kraken `KrakenPublicReadOnlyResearch` permanece isolado de API/UI de distribuição e desligado por padrão. A licença dos dados de mercado **não decorre** da licença do código-fonte; o guia oficial Kraken requer permissão prévia para certos usos comerciais não pessoais de dados públicos. `docs/PROVIDER_RIGHTS.md` estabelece matriz de uso e gate humano de release. Até que finalidade concreta e direitos aplicáveis sejam registrados, **não integrar os candles/tickers da Kraken em serviço público, exportação aberta ou monetização**. Testes offline/sintéticos continuam independentes do licenciador, sem gastos ou ordens.


## Estudo de schema Bybit com unidades documentadas (J1/WU18)
`bybit_linear_candle_research.py` é isolado e **puramente offline**, sem endpoint ou autenticação, para analisar o schema do candidato Bybit V5 linear: OHLC em ordem descendente, `volume` moeda-base e `turnover` na moeda de cotação USDT/USDC conforme API oficial. Exige metadados injetados de `LinearPerpetual`/`Trading`, validação temporal, string Decimal e candles fechados. Não migra storage, não cria contratos `ClosedCandle` canônicos nem libera seleção Top50 ou estratégia. Mudança de provedor ou licença comercial exigiria evidência e gate separado; `docs/PROVIDER_RIGHTS.md` inclui Bybit.


## Direitos de dados segregados da ingestão (J1/WU19)
`provider_usage_gate.py` é um módulo offline de classificação de finalidade de uso, separado dos clientes públicos, storage e UI. Escopos são por dataset/provedor/finalidade e exigem revisão temporal, mas nenhuma declaração introduzida pelo chamador pode liberar distribuição comercial/pública ou sinalizar release. Auditoria jurídica/contratual de licença e autorização da finalidade real permanecem gates humanos e externos, conforme `docs/PROVIDER_RIGHTS.md`.


## Candidato adicional OKX V5 SWAP (J1/WU22)
O staging de histórico em `okx_swap_candle_research.py` é intencionalmente separado dos adaptadores operacionais e reutiliza somente os validadores de tempo/erro existentes. Não há mais um sistema de armazenamento, fonte principal ou processo de rede. O esquema documentado traz volume em contratos, base e quote separados, além do flag de fechamento. Isso permite **testes de conformidade offline**, não backtest real nem direitos sobre o feed. O registro de identidade positivo crypto-only e o gate de licença são dependências independentes. Nenhuma integração à UI ou `ClosedCandle` foi autorizada.


## Pré-trabalho de features sintéticas sem J1 homologada — J2/PRE1 (#66)
`synthetic_feature_engine.py` depende do contrato único `ClosedCandle` e das funções UTC já implementadas no J1. Não aceita staging dos fornecedores Kraken/Bybit/OKX nem qualidade não sintética, e não introduz outro banco ou engine de ordens. Seu resultado é apenas uma sequência imutável de números causais (EMA, ATR, máximos/mínimos passados, razão de volume e retornos); a política de trading e os sinais serão um componente separado depois da homologação de J1/J2, com a mesma semântica no J3. Nenhum indicador vira gatilho operacional pela existência do valor.


## Contrato de venue alternativo sem rede — Hyperliquid nativa (J1/WU24)
A rota `hyperliquid_native_research.py` valida somente payloads injetados em memória do `/info` (POST informativo) e usa as funções de intervalo UTC/erros já existentes. Não acrescenta adaptador operacional, banco, cliente HTTP nem faz POST de ordens para `/exchange`. Metadados de mercado são reportados, não autenticados, e a série de candles conserva o volume `v` como unidade não verificada; nenhuma saída é convertida em `ClosedCandle` ou alimenta o `synthetic_feature_engine.py`. Sem chamada real, a disponibilidade e a licença permanecem desconhecidas. Se a opção avançar, a próxima unidade deverá revisar termos e coletar prova mínima autorizada, com validação de conteúdo/retention e sem burlar gates J1.
