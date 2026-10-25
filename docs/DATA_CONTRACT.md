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

## Pesquisa independente WU6: Kraken Futures

- Probe `python3 scripts/probe_public_kraken.py --allow-public-network`, uma única consulta GET de instrumentos a host fixo `futures.kraken.com`, sem seguir redirects, sem salvar resposta bruta, sem credenciais nem comandos de trade. Execução normal sem flag recusa a rede.
- Limites: 8 segundos de timeout e 4 MiB de corpo. Saída JSON de prova usa UTC ISO, status HTTP, contagem de instrumentos, contagem **heurística** de símbolos `PI_`/`PF_` e até 5 símbolos de exemplo. Isso **não** comprova liquidez, volume USDT comparável, contratos lineares ou histórico contínuo.
- Workflow de issue #23 sob comando literal do proprietário `/probe-kraken-public-v1`; runner padrão público, 2 minutos, permissões somente leitura; nenhum agendamento ou CI online. Se houver erro por política do fornecedor ou DNS, parar sem retries, registrar evidência e não contornar restrições.
- Só projetar um adaptador Kraken e critérios de elegibilidade após observar que a API pública é efetivamente acessível e quais contratos/volumes ela oferece. Fonte oficial: https://docs.kraken.com/api/docs/futures-api/charts/candles .


## Conformance de metadados, tickers e candles Kraken — WU7
- A WU6 executou um GET real de instrumentos: run `40198042787`, HTTP200, 231 instrumentos, 213 prefixos PI_/PF_ (não 213 contratos cripto elegíveis).
- A probe WU7 é `python3 -m scripts.probe_kraken_market_schema --allow-public-network --allow-kraken-schema-probe`. Ambas flags são exigidas; nenhuma consulta acontece em testes automáticos.
- A probe usa caminhos fixos do **mesmo provedor independente** (`/derivatives/api/v3/instruments`, `/derivatives/api/v3/tickers` e `/api/charts/v1/trade/PF_XBTUSD/1h?count=3`), no máximo 3 GETs, sem redirects nem retries, até 8 segundos e 4MiB por request, sem chaves ou persistência da resposta. Retorna apenas campos allowlist/nomes de campos, status, UTC e contagens.
- Não interpretar um HTTP200 nem uma lista de símbolos PI_/PF_ como evidência de 50 criptoativos líquidos; `PF_AAPLXUSD` é exemplo de categoria não cripto que precisa ser excluída. Precisamos estudar tipo de instrumento, tickers/volume cotado e unidades de `contractSize` para seleção e ranking válidos.
- Campos de candles `time,open,high,low,close,volume` e `more_candles` são verificados estruturalmente, porém **não são tratados como velas fechadas validadas** sem regras de finalização e intervalos confirmados.
- Workflow owner-only exige comentário exato `/probe-kraken-market-v1` na issue #25. Um run real fornece evidência pontual de schema, não homologação do feed ou autorização de trading. Não tentar contornar políticas de Binance ou de Kraken.

## WU8 — Taxonomia crypto-only por metadados Kraken
- O probe original `scripts/probe_public_kraken.py` adiciona modo opcional `--inspect-taxonomy`, sem chamada extra: **um GET público** `/derivatives/api/v3/instruments`, sem redirect, retry, credenciais, armazenar payload bruto, ou acessar rede sem `--allow-public-network`.
- Saída segura informa contagens por categoria, distribuição booleana `tradfi`, e campos allowlist de PF_XBTUSD/PF_ETHUSD/PF_AAPLXUSD (base, quote, pair, category, tradfi, tags, type, tamanho do contrato, status). Strings só podem conter caracteres de token simples e até 40 caracteres; tags limitadas a 10.
- Workflow GitHub owner-only na issue #28, comentário literal `/probe-kraken-taxonomy-v1`, timeout 2 min, sem secrets e CI offline normal. Sem prova real da execução ainda; `taxonomy_validation_status=observed_values_only_no_crypto_only_filter_yet` impede promoção indevida de contagens para universo Top50.
- A validação futura precisa demonstrar que as categorias/flags diferenciam criptomoedas de instrumentos tokenizados e que `volumeQuote` USD equivale a volume financeiro comparável, com contrato linear e fechamento de candle confirmados. Não usar prefixo/tipo como filtro suficiente.

## WU9 — Universo de pesquisa Kraken fail-closed (sem selecionar ordens)

- Módulo puro `crypto_intelligence_agent/kraken_eligibility.py` recebe instrumentos + tickers **observados no mesmo instante de pesquisa**, `observed_at_ms` UTC-ms, `verified_crypto_bases` (frozenset obrigatório injetado de registro externo confiável e versionado), `registry_version` e `max_symbols` (1 a 50). **Não existe registro fixo de 50 ativos no código**, nem chamada de rede, banco ou ordem.
- Dado empírico run `40199111677`: `PF_AAPLXUSD` tem `category=xStocks`, `tradfi=false`, `type=flexible_futures`; BTC/ETH têm `tradfi=false` e categoria ausente. Portanto nenhum desses três campos isoladamente comprova elegibilidade crypto-only.
- Para ser elegível, exigir símbolo linear PF_, `type=flexible_futures`, `tradeable=true`, `suspended=false`, não expirado, `tradfi=false`, `base` presente no registro versionado de criptomoedas, `quote=USD`, `pair=BASE:USD`, filtros contratuais positivos, ticker `tag=perpetual`, ticker ativo, `volumeQuote` Decimal positivo/finito. Excluir explicitamente categorias não cripto `xStocks/Equities/Forex/Commodities/Pre-IPO/Indices`. Casos ambíguos são rejeitados ou anotados como exclusões.
- Ordenar **apenas** contratos reconhecidos por `volumeQuote` USD desc com desempate por símbolo. Persistência/replay deve preservar versão de seleção e snapshot de observação genuína; ranking atual não reconstrói ranking histórico.
- Módulo de pesquisa não significa integração Kraken ao motor principal, não transforma `volumeQuote` de um único dia em prova de liquidez constante nem valida multiplier/stepSize/lot para ordens. Banco SQLite/backfill WU2 deve ser reutilizado quando houver adapter.

## WU10 — Origem e hash do registro crypto-only (somente pesquisa)
- `crypto_asset_registry.py` valida manifesto JSON versionado de uso `internal_research_only`, hash SHA256 canônico, `observed_at_ms`, `label`, base/canonical_id únicos e revisão identificada. Cada base demanda 2–6 referências independentes (publicador, asset_ref, URL HTTPS seguro, observed_at_ms anterior à revisão). Sem rede, dumps comerciais, credenciais ou ordem.
- `CryptoRegistryHistory` exige observações monotônicas, permite replay idêntico, rejeita conflitos e impede seleção com registro registrado **após o instante dos tickers**, inclusive em backtest. `select_at` também bloqueia observações futuras ou vencidas no momento da decisão. Limites de idade do mercado/registro são obrigatórios e configuráveis.
- Identidade de base certificada no manifesto é uma **afirmação de revisão** que ainda exige conferência humana real e licença adequada; digest só garante integridade de conteúdo. Módulo não acompanha API paga nem inclui assets pré-aprovados. Nome do snapshot de universo inclui SHA completo da versão do registro.
- A documentação detalhada do esquema, governança, fontes e limitações fica em `docs/CRYPTO_REGISTRY.md`. Não inferir 50 criptoativos da Kraken por sufixo, `tradfi=false`, volumeQuote ou categoria isoladamente.

## WU11 — Staging seguro de OHLC Kraken (sem unidade de volume inferida)
- `kraken_candle_validation.py`: parser puro, sem rede ou escrita, restrito às resoluções documentadas (`1m,5m,15m,30m,1h,4h,12h,1d,1w`). Entra `trade` candle com `time` integer UTC-ms, OHLC strings Decimal estritamente positivas, `volume` int64 não negativo e `more_candles` booleano.
- Requer janela de abertura `[start_open_ms,end_open_ms)` alinhada à grade UTC do intervalo, linhas ascendentemente contíguas e completas, limite configurável (1..500), sem candle futuro ou ainda aberto; `close_time_ms=open+duration-1` e `close_safety_ms` parametrizável. Não ordena/sintetiza silenciosamente lacunas. Sem fechamento confirmado => erro.
- `epoch_ms_window_to_kraken_seconds` converte datas alinhadas para argumentos do endpoint, mantendo visível a diferença entre ms das velas e segundos da query; sem assumir inclusividade dos limites do servidor antes de validar a resposta.
- `KrakenTradeCandleStaging` **não é** `ClosedCandle`: expõe apenas OHLC validado e `raw_trade_volume_unverified`, com `raw_volume_unit=unverified`. Não expõe `base_volume` nem `quote_volume`, não pode alimentar PnL/backtests/sinais como se tivesse volumes comparáveis. Nenhuma migração, persistência duplicada ou alteração de provedor principal.
- Referência oficial: https://docs.kraken.com/api/docs/futures-api/charts/candles. A unidade/multiplicador de volume ainda precisa de confirmação independente antes de criar um adaptador canônico Kraken. Gate atual: pesquisa offline, não homologação da J1.

## WU12 — Diagnóstico real pontual de unidade de volume, sem promoção canônica
- Script `scripts/probe_kraken_volume_units.py` bloqueia qualquer rede sem as DUAS flags `--allow-public-network --allow-volume-diagnostic`. Executa no máximo dois GETs públicos fixos, sem redirects/retries/segredos e timeout de 8 segundos por chamada, resposta limitada a 4 MiB. Não grava corpos brutos nem banco.
- `GET /api/charts/v1/trade/PF_XBTUSD/1h?count=27`: resume apenas a soma do `volume` **inteiro bruto** de 24 barras de hora completamente fechadas, contíguas e em UTC. Não aceita data futura, timestamp fora da grade, valor negativo/float ou linha incompleta. O `volume` do chart permanece com unidade **desconhecida**.
- `GET /derivatives/api/v3/tickers`: resume `vol24h` e `volumeQuote` publicados para o ticker `PF_XBTUSD` identificado como `perpetual`; sem classificação automática de unidade. As janelas de 24 horas corridas e de 24 velas fechadas **não coincidem exatamente**; qualquer comparação é heurística insuficiente para garantir conversão.
- Workflow `issue_comment` da issue #36 somente para comando literal proprietário `/probe-kraken-volume-v1`, prazo 2 min, permissão leitura e runner gratuito sem execução em PR/push/cron. Resposta diz `unit_proof=false` mesmo sob HTTP200. Nenhum `ClosedCandle`, volume financeiro inventado, execução real ou homologação de J1 resulta deste probe.

## Primeiro resultado WU12 e observabilidade sanitizada
- Smoke run https://github.com/leandrosilveiradepaula/crypto-intelligence-agent/actions/runs/40201172859 em 2026-10-25 14:12:51 UTC, SHA `b607e2f32c5df8144790e58471133fb4fb9559a0`. GET chart BTC horário HTTP200; rejeição `invalid_chart_or_insufficient_data` após **1 GET**; nenhum ticker lido, nenhum candle validado para comparação de unidade.
- A próxima versão do probe relata somente `chart_row_count`, `more_candles` booleano, distribuição de **TIPOS** da coluna volume em até 28 linhas, quantidade de timestamps alinhados/fechados e primeira/última abertura válida. Não imprime o conteúdo de volume, OHLC ou corpos da API. Continua sem prova de unidade financeira.
- O status HTTP200 e uma estrutura parcialmente compatível não justificam inferir base_volume/quote_volume, contornar políticas da fonte, superar limites públicos ou preencher lacunas históricas. WU12 permanece bloqueada na parte de unidade até evidência adicional.

## Evidência de schema de volume Kraken — WU13
- Run owner-only https://github.com/leandrosilveiradepaula/crypto-intelligence-agent/actions/runs/40201488833 (2026-10-25T14:16:56Z, SHA `af0e431e5fba56e6fb5eb09c9c2e4e3418b93d1c`): `GET /api/charts/v1/trade/PF_XBTUSD/1h?count=27` HTTP200, 27 linhas, 26 horárias fechadas, `more_candles=false`. Todos 27 campos `volume` são **strings de número decimal**, não inteiros. O parser WU12 abortou com erro de schema após 1 GET e não leu ticker.
- Kraken documenta `volume` como `number<int64>`, mas o formato real observado exige aceitar strings decimal fixas sem perder precisão. O parser único `kraken_candle_validation._raw_trade_volume` retorna `Decimal` não negativo para int64 ou string de precisão limitada (sem float/NaN/expoente/bool). Respeitar teto int64; deixar significado financeiro **explicitamente não verificado**.
- WU11 staging `KrakenTradeCandleStaging.raw_trade_volume_unverified` passa a ser `Decimal`, não valores de base/quote. WU12 agrega Decimal exato de 24 barras fechadas, sem inferência de unidade ou alinhamento exato da janela rolling ticker. NENHUM `ClosedCandle`, volume financeiro em sinais/backtests, autorização de trade ou banco paralelo.

## Resultado live WU13 e permanência de gate financeiro
- Run https://github.com/leandrosilveiradepaula/crypto-intelligence-agent/actions/runs/40201868577, UTC `2026-10-25T14:21:50Z`, SHA `e9b3b52b252b9319790ea188633392d13178b38f`. Ambos os GET públicos Kraken (chart BTC PF_XBTUSD e tickers) HTTP200; 27 barras de chart, 24 totalmente fechadas/contíguas, soma Decimal de `volume` bruto `4122.747600000000`; ticker reporta `vol24h=3928.2499`, `volumeQuote=314801204.5661`. Nenhum dump bruto, credencial, ordem ou DB persistente.
- WU13 #39/PR #40 corrigiu erro de schema observado em #40201488833 (27 valores `volume` decimal-string): `KrakenTradeCandleStaging.raw_trade_volume_unverified` é `Decimal` exato; testes offline 169 e documentação 11 aprovados. Volume bruto não é automaticamente volume-base/cotado.
- WU12 #36 ainda **ABERTA**: documentos chart não estabelecem fatores e unidades para mapear base_volume/quote_volume do contrato canônico; janelas ticker rolling24h e 24 candles UTC fechados não coincidem. Não transformar o êxito de duas consultas em aprovação de estratégia, história integral, volume monetário ou Top50 negociável.

## WU14 — Compatibilidade de alavancagem de pesquisa com tiers Kraken (sem execução)
- `crypto_intelligence_agent/venue_leverage_gate.py`: contrato puro `VenueLeverageSchedule` com venue Kraken, PF_ USD, URL HTTPS pública sem credenciais, `source_version`, `observed_at_ms` e tiers ordenados `[min_notional_usd,max_notional_usd)` com último `max=None`. Cada tier contém `maximum_leverage` Decimal. Exigir cobertura integral desde zero, intervalos adjacentes, e teto monotônico não crescente. Uma URL/versionamento são metadados de proveniência **declarada**, não atestado de conferência de fonte.
- `assess_new_research_position` recebe alavancagem global solicitada para a **nova posição**, valor notional adicional, notional EXISTENTE no mesmo instrumento, instante UTC da decisão, limite de idade de fonte. Usa a exposição **agregada final**, inclusive se atravessar exatamente um limite de bracket; recusa schedule futuro/obsoleto, dados inválidos, floats, NaN, Infinity e gaps de tier.
- Resultado imutável `NewPositionLeverageAssessment` apresenta permitido/recusado, requested leverage sem mudança automática, cap por tier, valores da exposição e versão do snapshot. `guaranteed_exchange_acceptance=false`, `adjusts_existing_positions=false`, `sends_orders=false`. É um gate **de pesquisa**, não motor de margem real/liquidação nem verificação de jurisdição ou saldo.
- A configuração global D02 de 50x é preservada no produto. **Não** pressupor que 50x seja válido para PF_1INCHUSD (classe E 10x citada na documentação) ou contratos de classes inferiores. Um ativo tokenizado não se torna elegível por passar no gate. Nenhuma tabela de venue atual é hardcoded, apenas fixtures offline sintéticas.
- Referências: https://support.kraken.com/br/articles/360022632452-derivatives-margin-schedule-maximum-leverage e https://support.kraken.com/br/articles/4844359082772-linear-multi-collateral-derivatives-contract-specifications .

## WU15 — Número JSON financeiro de ponta a ponta sem ponto flutuante binário
- `crypto_intelligence_agent/decimal_json.py` oferece `decode_public_market_json_exact`: lê somente objeto JSON UTF-8 limitado (até 4 MiB), `parse_float=Decimal` com precisão finita limitada, `parse_int` limitado, sem `NaN/Infinity`, raízes de outros tipos ou chaves JSON repetidas. Sem rede, segredo, banco ou ordens. Para análise de provedores, o timestamp e a origem precisam continuar atestados pelo chamador.
- `positive_market_decimal` aceita exclusivamente `Decimal`, `int` ou string decimal fixa positiva/finita e com limites explícitos; **recusa float** que já teve seus dígitos arredondados. O seletor Kraken `kraken_eligibility.py` utiliza este validador para `tickSize`, `contractSize` e `ticker.volumeQuote`, preservando ranking dos ativos elegíveis inclusive por diferenças inferiores à precisão IEEE-754.
- O probe read-only `scripts/probe_kraken_volume_units.py` decodifica números numéricos JSON pelo mesmo decoder antes de resumir `ticker.vol24h` e `ticker.volumeQuote`. Relatório mantém `unit_proof=false`, 2 GETs owner-only no máximo e janelas UTC vs rolling24h explicitamente incompatíveis. Não reconstrói moeda/unidade de candles nem promove `ClosedCandle`.
- Uma fonte externa que já devolveu Python `float` deve ser reintegrada desde os bytes JSON; não basta converter `float` com `str` ou `Decimal(float)`. Essa validação não confere a identidade/licença cripto de WU10 #32 nem a unidade financeira em WU12 #36.

## WU16 — Cliente público Kraken de pesquisa integrado
- `KrakenPublicReadOnlyResearch` aceita `allow_public_network=False` por padrão; método `current_market_snapshot` exige True para realizar exatamente **dois GETs públicos fixos** de `/derivatives/api/v3/instruments` e `/derivatives/api/v3/tickers`. Transport e clock injetáveis; response limitada a 4 MiB por GET, timeout até 10s, sem redirect/retry/auth/POST/ordem. Classificar 403/418/451 como bloqueio terminal sem contornar a origem.
- `KrakenCurrentResearchSnapshot` registra `captured_start_ms`, `captured_end_ms` e `observed_at_ms=end` do relógio local, intervalo máximo 30s, sem afirmar relógio verificado da exchange. Retorna somente tuplas de mapas read-only allowlist de metadados/tickers, com valores financeiros `Decimal` exatos desde JSON. Duplicatas divergentes falham e ordem é determinística. Snapshots atuais nunca reconstroem elegibilidade passada.
- `staged_closed_candles` realiza 1 GET trade chart por símbolo PF_ USD e intervalo documentado, com janela explícita `[start_open_ms,end_open_ms)` UTC e query `from/to` em epoch segundos. Sempre passa por `stage_kraken_trade_candles`, rejeitando gaps/abertos/schema/volume inválido. O retorno `KrakenCapturedCandleResearchPage` conserva `observed_at_ms` e staging de preços; **NUNCA** `ClosedCandle`, `base_volume`, `quote_volume`, `MarketDataCheckpoint` ou gravação de backfill.
- Esse client não contém token de API, credenciais, métodos de ordens, componentes de estratégia ou acesso contínuo. Transport mock nos testes CI; ausência de fonte cripto positiva ou unidade de candle impede ativação de universo/estratégia real. A execução de sondagens públicas já foi demonstrada pelas runs WU7/#40201868577; não duplicar requisições sem hipótese de pesquisa nova.

## WU18 — Bybit V5 linear USDT/USDC como candidato de estudo de unidades de volume (OFFLINE)
- `bybit_linear_candle_research.py` recebe objeto sintético do `GET /v5/market/kline` (`category=linear`, símbolo `...USDT` ou `...USDC`, `retCode=0`). Cada item precisa ter **7 strings**: abertura UTC-ms, OHLC, `volume` base coin e `turnover` quote coin. Dados entram em ordem newest-first, mas são entregues cronologicamente ASC após validação de ordem descendente, continuidade e fechamento.
- A especificação oficial é explícita: USDT/USDC linear `volume` em **base** e `turnover` em **quote**, não `USD` indiferenciado. Não inferir conversão USD via fechamento de candle, não supor que rolling ticker equivale ao período. Guardar `documented_base_volume`, `documented_quote_turnover`, `quote_currency` e `unit_basis=documented_bybit_linear_kline_schema_not_live_verified`.
- Exigir input de metadados de contrato `LinearPerpetual` e status `Trading`, instante de observação de contrato não futuro/nem obsoleto, janela UTC half-open alinhada e vela inteiramente fechada com safety parametrizado; falhar em gaps, duplicatas, reverse order inválida, OHLC inconsistente, NaN, strings fora do padrão ou página incompleta. O chamador ainda precisa **comprovar metadados reais**, não basta afirmar valores em argumentos.
- Nenhum GET live, transporte, data lake, contrato `ClosedCandle`, storage, trade ou mudança de fornecedor. O resultado é estágio de pesquisa com **fixtures sintéticas** e sem direito comercial/licença atestada. Fontes: https://bybit-exchange.github.io/docs/v5/market/kline e https://www.bybit.com/en/help-center/article/API-Terms .


## WU19 — Decisão de finalidade de uso de dados sem distribuição
- `provider_usage_gate.py`: `UsagePurpose` enum de pesquisa interna, painel privado, display público, API pública e comercial; `Dataset` instruments/candles/tickers/funding/derived_alerts; provedor Kraken/Bybit/Binance explícito.
- `RightsGrantEvidence` é **declaração fornecida pelo chamador** de provedor/dataset/finalidade, revisor, versão, instante e vencimento UTC-ms e URL HTTPS pública, e NÃO assinatura nem licença autentificada. Campos inválidos, tempo futuro/vencido e escopo cruzado não se propagam entre modalidades.
- `assess_provider_usage` é puramente informativa, fail-closed e sempre `allowed=false` para usos privados/públicos/comerciais, inclusive quando o chamador injeta `grant_confirmed=true` ou flag de release. Pesquisa interna retorna `needs_terms_review`, não permissão automática. Não exporta dados, não habilita produção e não representa parecer legal.
