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
