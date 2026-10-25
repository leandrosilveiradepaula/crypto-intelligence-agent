# J1 — Contrato canônico de dados (proposta versionada)

Este documento delimita a primeira work unit do Codex (issue #9), sob a jornada #2. Não implica implementação nem integração real com a exchange.

## Mercado e universo
- Mercado-alvo inicial: contratos futuros perpétuos lineares cotados em USDT; adaptador de fonte configurável, sem acoplar o domínio a um provedor.
- Universo inicial: até 50 contratos elegíveis por volume de negociação, calculado no momento da decisão, não uma lista fixa de símbolos.
- Preferir volume cotado (quote volume) comparável para ordenar; validar tipo, status de contrato, liquidez, idade mínima configurável e eventuais exclusões. Registrar versão e snapshot do conjunto elegível.
- Em estudos históricos, reconstruir elegibilidade e ranking com informação disponível naquela data; nunca usar listagem atual como universo retroativo sem advertência de viés de sobrevivência.

## Objetos de domínio
- ContractSpec: exchange, market, symbol, base_asset, quote_asset, contract_type, status, onboard_time, tick_size, step_size, min_qty, min_notional quando disponível, timestamps de observação e fonte.
- ClosedCandle: exchange, market, symbol, interval, open_time_ms, close_time_ms, open, high, low, close, base_volume, quote_volume e qualidade da amostra.
- UniverseSnapshot: observed_at_ms, selection_rule_version, símbolos elegíveis, posição no ranking, fonte e motivo de exclusões.
- MarketDataCheckpoint: tipo de dado, exchange, símbolo, intervalo, início/fim confirmados, fonte, versão e integridade.
- Futuramente, MarkPriceSample e FundingEvent serão objetos próprios: não confundir preços negociados com preços de marcação.

## Regras temporais e numéricas
- Todas as datas de mercado em UTC, timestamps de API em milissegundos.
- Nunca utilizar candle ainda em formação para sinal de fechamento: validar close_time e disponibilidade efetiva, com margem conservadora de segurança quando necessário.
- Histórico ordenado crescentemente por open_time. Identidade idempotente: (exchange, market, symbol, interval, open_time_ms).
- Valores financeiros mantidos com precisão decimal apropriada; não converter silenciosamente valores monetários/quantidades em floats imprecisos.
- Timeframe 4h para pesquisa inicial de entradas e 1h para confirmação são hipóteses de configuração; granularidade intrabar mais fina será exigida posteriormente para backtest de liquidação.

## Erros e limites
- Dados ausentes, lacunas, duplicatas, mudança de especificação, contrato não elegível, throttling, timeout e erro HTTP devem ser explícitos, registrados e testáveis.
- Respeitar limites públicos de API, com backoff limitado e retries idempotentes.
- Fixtures offline como base da CI; testes online opcionais e sem credenciais de trading.
- Dados gratuitos podem ter cobertura ou histórico limitados; registrar essas limitações, nunca completar lacunas com valores fictícios.

## Critérios de aceite da primeira work unit
1. Esquemas e adaptação read-only implementados com fixtures offline.
2. Testes para UTC, candle fechado, deduplicação, ordering, timeout/rate limit e símbolo inválido.
3. Evidências de execuções locais/CI no SHA da PR e documentação de decisões.
4. Nenhum envio de ordens reais, segredo ou chamada paga.
5. Não declarar a jornada J1 concluída apenas pela primeira work unit.

Referência: issues #2 e #9, docs/PRODUCT_SPEC.md, DECISIONS.md e VALIDATION_PLAN.md.

## Integridade de dados implementada na WU1

- `contracts()` e `universe()` consultam endpoints **atuais**, não séries históricas. A hora declarada de observação precisa ser recente em relação ao relógio injetável (`max_snapshot_age_ms`, padrão 300000); snapshots históricos exigem registros realmente persistidos na época e não podem ser sintetizados por uma consulta atual.
- `closed_candles()` recusa uma observação futura em relação ao relógio do adaptador. Apenas candles com `close_time_ms + close_safety_ms <= observed_at_ms` são admitidos.
- Timestamps devem ser inteiros não negativos sem truncamento implícito; intervalos fixos aceitos são enumerados no adaptador. `1M` é propositalmente não suportado nesta work unit, por ter duração variável.
- Candle aceito deve ter duração exata do intervalo, OHLC estritamente positivo e volumes não negativos. Metadados de contrato exigem filtros de preço/quantidade positivos. Tickers com duplicatas divergentes falham explicitamente.
- O snapshot de universo é um retrato aproximado de coleta do ticker público de volume móvel de 24 horas; não equivale a reconstrução histórica ponto-no-tempo e não garante simultaneidade exata das duas chamadas REST. A J1 posterior deverá persistir snapshots e suas evidências de coleta.
- CI deve executar `unittest`, compilação Python e validação documental com fixtures offline; nenhum teste aciona ordens ou depende de API externa.

## Persistência e backfill implementados na WU2

- `SQLiteMarketDataStore` é a referência local gratuita, isolada atrás de `MarketDataStore`; não é uma decisão de banco de produção. Preços, quantidades e volumes são gravados como texto decimal canônico, e nunca como `REAL`/`float`.
- O backfill recebe uma janela explícita `[start_open_ms, end_open_ms)`, alinhada ao intervalo UTC, e só aceita cobertura exata de cada página. Falta, duplicata, candle fora da janela ou identidade divergente falham sem gerar candles sintéticos.
- Cada página confirmada e seu `MarketDataCheckpoint` são gravados na mesma transação SQLite. Uma falha de API ou validação da página não avança o checkpoint; uma nova execução recomeça em `confirmed_end_ms + 1` e é idempotente.
- Contratos e `UniverseSnapshot` persistem o timestamp e a fonte efetivamente recebidos. O armazenamento não fabrica snapshots históricos: a fonte pública atual continua sendo recusada pela WU1 quando rotulada como observação antiga.
- `quality_report()` expõe cobertura esperada/persistida, timestamps ausentes e último checkpoint. Conflitos rejeitados não são registrados como eventos persistidos: `conflicting_duplicates=None` significa **não medido**, nunca zero comprovado. `complete` requer cobertura e checkpoint íntegro cobrindo a janela.


## Proteções adicionais da revisão WU2
- Checkpoint é uma afirmação de histórico **contínuo** desde o início original. Antes de reutilizá-lo, o backfill reconfere a presença e a ordem de todos os candles do prefixo, rejeitando lacunas/corrupção, fontes ou versões divergentes, retrodatação anterior ao início ou janelas não contíguas. Não pula automaticamente histórico ausente só porque existe um watermark mais recente.
- Avanço de checkpoint só pode ser adjacente à última página válida. Gravação direta de páginas valida toda a sequência, identidade, intervalos, `Decimal` finitos, OHLC e volumes, e falha fechada com rollback.
- Metadados de contratos de mesma identidade e timestamp são imutáveis. Um replay igual é idempotente; versão conflitante é rejeitada sem substituir valores e sem commits parciais de lotes.
- Janelas semanais respeitam o calendário da exchange: abertura de candle `1w` na segunda-feira UTC, não no offset zero do Unix. `SQLiteMarketDataStore(":memory:")` é rejeitado porque o backend de referência usa conexões independentes por transação.
- A revalidação integral do prefixo em cada retomada é conservadora e tem custo O(N); otimizações futuras exigem provas de integridade equivalentes. O store não é um serviço operacional de retenção/backup auditado. O modelo atual de checkpoint só suporta uma linhagem ativa por exchange/símbolo/intervalo, devendo rejeitar janelas históricas desconexas.

## WU3 — Orquestração e proveniência (em revisão)

- `python -m crypto_intelligence_agent` é um fluxo de engenharia **offline por padrão**. Usa `OfflineFixtureTransport` exclusivamente local, reaproveita as classes WU1 e o backfill/SQLite WU2. Os candles de demonstração são sintéticos, marcados `quality=synthetic_fixture` e `source=synthetic_fixture`; **não** constituem histórico para backtest.
- `--mode live --allow-public-network` é o único caminho para chamadas públicas reais de leitura. Não há autenticação, envio de ordens ou execução pela CI. Rede live requer autorização explícita do operador via flags de CLI; ela não está homologada e não valida cobertura, retenção, volume histórico ou rentabilidade.
- O pipeline captura metadados e universo com timestamps UTC-ms observados ao **terminar** cada resposta; os endpoints de origem ficam registrados como `GET /fapi/v1/exchangeInfo`, `GET /fapi/v1/ticker/24hr` e `GET /fapi/v1/klines`. São consultas sequenciais, **não atômicas**. O universo atual jamais é rotulado como universo ponto-no-tempo histórico.
- Eventos por endpoint/símbolo, status e resultado são persistidos na tabela local aditiva `collection_events`; o recibo de execução também é emitido como JSON na saída. Não armazenar tokens/URLs com credenciais. Falhas de dados são explicitamente auditadas sem avançar páginas inválidas.
- Seleção de universo suporta `--max-symbols` de 1 até 50, sem hardcode de símbolos no modo live; `--symbols` opcional limita-se aos contratos ranqueados/eligíveis. Janelas `[start-ms, end-ms)`, intervalo, page size e idade mínima são configuráveis.
- CLI sem `--database` cria banco temporário e o remove ao sair. Para inspeção/replay, usar caminho explícito **fora do GitHub público**, sem publicar `*.sqlite*`. Modo offline suporta fixture horária ilustrativa BTC/ETH; não extrapolar cobertura dessa fixture.
- Relatórios de qualidade incluem candles esperados/gravados, lacunas, checkpoint, status e proveniência. `None` na contagem de conflitos significa **não medido**. Sem sinais de negociação, backtest, ML, deploy ou homologação de feed real.

## WU4 — Conformidade temporal com relógio da exchange

- `BinanceFuturesPublicAdapter.server_time_ms()` realiza somente `GET /fapi/v1/time`, sem credenciais, e exige `{"serverTime": <inteiro UTC-ms não negativo>}`. Respostas inválidas, HTTP 429/5xx ou timeout falham explicitamente.
- Antes de coletar metadados, universo ou candles, o pipeline mede horário local antes/depois da resposta. Estima o deslocamento do relógio da exchange em relação ao ponto médio local, além da incerteza por latência (metade do RTT, conservadoramente arredondado). Bloqueia a coleta se `abs(offset_ms) + ceil(RTT/2) > max_clock_skew_ms`.
- O limite padrão é `5000 ms`, configurável com `--max-clock-skew-ms` (não negativo). Falha é registrada como evento `GET /fapi/v1/time` com status `failure` e não gera snapshots/candles, evitando falsa integridade temporal.
- O relatório JSON exibe `server_time_ms`, `clock_offset_ms`, `clock_round_trip_ms`; o evento de sucesso grava os valores estimados. Uma amostra não comprova sincronização permanente nem elimina atraso de publicação da exchange.
- O transporte de fixtures responde a `/fapi/v1/time` com valor **sintético**, sem rede. O modo live exige consentimento explícito para GETs públicos e não participa dos testes CI. Documentação de referência: https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data .

## WU5 — Conformidade de endpoints públicos e rate limits (código offline)

- O adaptador distingue HTTP 403 (acesso negado) e HTTP 418 (bloqueio/banimento de IP) de falhas gerais, por `ExchangeAccessError`; não deduz automaticamente a causa (geografia, WAF, rede ou política de IP). Nenhuma dessas respostas deve ser repetida automaticamente.
- HTTP 429 pode incluir `Retry-After`; quando fornecido em segundos numéricos finitos, o cliente respeita o maior entre esse intervalo e o backoff exponencial local. Um atraso maior que `max_retry_wait_seconds` (padrão 10 s) resulta em `RateLimitError` sem nova tentativa, para evitar piorar bloqueios de IP. Cabeçalhos inválidos falham de modo explícito, não são ignorados.
- `HttpResponse.headers` guarda **apenas** `retry-after` e `x-mbx-used-weight-1m` extraídos da resposta; nenhum header de autenticação, cookie ou dado privado é persistido. O modo de teste usa `sleep_fn` injetável e fixtures de HTTP para executar sem sleeps nem rede.
- Respostas HTTP fora de 2xx não são aceitas como JSON de mercado; payloads incorretos de `serverTime`, `exchangeInfo`, `ticker/24hr` ou `klines` devem falhar explícita e seguramente.
- A CLI já aceita `--mode live --allow-public-network` e limita a demonstração por `--max-symbols`, `--candles`, `--page-size`; sua execução real é **opcional e NÃO foi realizada** nesta WU5. CI permanece somente offline. Se o ambiente não acessar endpoints públicos, registrar bloqueio de execução e não declarar cobertura live homologada.
- Documentação oficial: https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data .

## Smoke público sob comando explícito (J1/WU5)

- O workflow `.github/workflows/public-feed-smoke.yml` só aceita um evento `issue_comment.created` com texto literal `/run-readonly-smoke-v1` na issue #19, publicado pelo proprietário `leandrosilveiradepaula` e conferido também por `github.actor`. **Não** é executado em pushes, PRs, cron ou CI automática.
- Runner padrão `ubuntu-latest`, limite de três minutos, somente `contents: read`; checkout sem credenciais persistidas. Repositório público: runner padrão não exige gasto adicional. O workflow não recebe segredos, chaves nem variáveis de ordem.
- Executa a CLI já validada, com dupla permissão explícita `--mode live --allow-public-network`, no máximo 1 símbolo, 3 candles 1h e uma página de 3 candles. Consulta exclusivamente endpoints públicos GET USD-M; sem execução de ordens ou armazenamento de banco persistente. Resultado e erros ficam nos logs do job, públicos e sem credenciais.
- Um resultado GitHub Actions `success` comprova execução dessa amostra naquele runner, instante e IP — não comprova cobertura ampla, dados ponto-no-tempo históricos ou execução em VPS. `failure` por DNS, 403/418, 429, clock ou payload é evidência de bloqueio/incompatibilidade, não licença para contornar políticas regionais.
- A única execução live autorizada por este caminho depende do comando explícito do proprietário (registrado na issue); testes normais `docs.yml` continuam **100% offline**. Os testes `tests/test_public_smoke_workflow.py` verificam a presença desse gate no workflow.

## Evidência live pontual — HTTP 451

- Run: https://github.com/leandrosilveiradepaula/crypto-intelligence-agent/actions/runs/40197499250, execução de 25/10/2026 às 13:24:57 UTC, commit `09617e0197c250e3b13c7486a60067791ed41a52`.
- Workflow `issue_comment` iniciado explicitamente pelo proprietário na issue #19. A CLI começou em modo `live` e falhou na primeira rota GET pública de horário da Binance, retornando `HttpResponseError` HTTP **451**; saída sem dados.
- **Resultado:** conectividade HTTP alcançou uma resposta de restrição, sem evidência de candles, elegibilidade ou dados reais válidos. Não presume indisponibilidade universal do provedor, não prova qual legislação/território causou o retorno e não autoriza contorno de bloqueios.
- O adaptador agora considera HTTP 451 como `ExchangeAccessError` sem novas tentativas, junto com 403/418, com regressão offline. Nunca usar esse runner para repetidas consultas ao endpoint que rejeita acesso. A issue #19 continua aberta; avaliar outras fontes públicas independentes sob termos legais próprios.
