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


## WU25 — Sondagem read-only e output agregado, fora da CI
O novo módulo de diagnóstico fica isolado em `scripts/probe_hyperliquid_native_info.py`. Reutiliza o parser puro WU24, não contém cliente de /exchange, não faz retry, não grava candles e bloqueia todo tráfego por padrão até receber duas flags CLI. O único gatilho GitHub Actions é `issue_comment` do titular na issue #72 após integração e revisão, sem `issues:write`, cron, push/PR trigger de rede, tokens persistidos ou secrets. CI comum só executa mocks. A evidência de um eventual runner real precisa de identificação e log verificável; o próprio comentário não é prova de execução. Sem confirmação do direito de dados, este componente não alimenta ranking, sinais, J3, produto ou release.


## WU26 — Ponte read-only entre runs issue_comment e inspeção de logs
`scripts/audit_j1_issue_comment_runs.py` e `.github/workflows/j1-evidence-run-audit.yml` são uma ferramenta operacional restrita, sem dependência da arquitetura de dados. A API REST oficial GitHub permite listar runs e jobs por workflow com permissão read-only `actions:read`; o conector existente permite ler os logs uma vez conhecido o job ID. Um job de PR específico do titular publica somente os IDs e status de dois diagnósticos passados, sem pedir `issues:write`, sem escrever em branch, sem agendar, sem S3, e sem qualquer endpoint de exchange. O workflow de auditoria não substitui a CI de testes, não habilita mais sondagens e não cria um serviço de monitoramento contínuo.

## J1/WU27 — Separação de validação estrutural global e prova do perp BTC
A função pura `_native_perp_context` conserva a checagem posicional de `metaAndAssetCtxs`; apenas o instrumento solicitado tem todos os campos de negociação validados. Tickers não-alvo são identificadores inertes (com limites de comprimento/charset e proibição de namespaces spot/HIP-3) e podem ter contextos ausentes por inatividade sem impedir um BTC validado. Uma subclasse `NativeMetadataSchemaError` tipa a etapa/motivo da recusa para produzir diagnóstico sanitizado, sem capturar ou logar o payload de resposta. `probe_hyperliquid_native_info.py` mantém a mesma política de máximo dois POSTs *somente em execução manual pré-autorizada*, sem reexecução nesta jornada. Nenhuma mudança no gate de direitos, fontes, universo crypto-only, persistência ou provedor escolhido.


## Pré-trabalho matemático J4/PRE1 — percentual de saída sem venue
`synthetic_partial_exits.py` é **domínio puro independente** de dados OHLCV e da infraestrutura de ordens (que não existe). Só recebe quantidades abstratas sintéticas, bases `INITIAL_POSITION`/`REMAINING_BALANCE`, percentuais Decimal e piso opcional da posição inicial, e retorna fatias imutáveis e conservação de quantidade. Não lê/salva posições, não chama brokers, não calcula PnL/fee/funding e não infere limites/ticks de contratos. Um contrato futuro de posições e execução **manual** deverá aplicar bounds reais, registrar fills idempotentes, alavancagem at_open imutável, custos e gatilhos sob backtest validado antes de permitir uso financeiro. J1 #2, J3 #4 e J4 #5 continuam sem aceite operacional.


## J4/PRE2 — Replay puro de eventos de fixture, antes de um ledger persistente
`synthetic_manual_exit_replay.py` usa o plano de alocação matemática PRE1 já integrado e processa um `tuple` imutável de eventos `SyntheticManualExitEvent` **fictícios**, sem conexão com `SQLiteMarketDataStore`, exchange, cliente HTTP, posição real ou executor de ordens. Deduplica exclusivamente IDs e payloads idênticos durante a **mesma função de replay**, falha fechado em conflitos, eventos posteriores ao corte, alterações cronológicas ou overfill de tranche, mantendo conservação Decimal e runner floor. Resultado imutável com progresso por tranche não dá autorização live, não gera ordens e declara não possuir idempotência persistente nem lot-size real. A J4 futura dependerá de store próprio/ledger de posições e fills, idempotência transacional cross-session, contratos reais, custos, funding, critérios de trailing e aceite J1/J3.


## J4/PRE3 — Contrato de abertura da posição de fixture sobre PRE1/PRE2
`synthetic_position_state.py` é uma camada **pura e offline**: `SyntheticLeverageSettings` imutável controla apenas novas aberturas; `SyntheticPosition` captura `leverage_at_open`, plano PRE1 imutável e margem Decimal abstrata. `SyntheticPositionExitFill` exige `fixture_position_id` válido e `replay_synthetic_position` usa diretamente PRE2, sem implementar outro ledger, event store ou driver de corretora. `SyntheticPositionSnapshot` mantém apenas quantidades sintéticas; não contém preço, mercado, moeda de colateral comprovada, PnL, fees ou execução. Posições e snapshots têm flags de live, identidade de lote, direitos de market data e idempotência persistente sempre falsas. Lotes e incrementos mínimos reais, permissões regionais, material de rede e dados da J1 não participam do contrato. J4 operacional #5 continua bloqueada por contratos de posições reais/J3/J1.


## J4/PRE4 — Auditoria sintética independente de step/minimum
`synthetic_lot_feasibility.py` constrói uma auditoria imutável de múltiplos exatos de `Decimal`, sem quantização, I/O ou dependência de exchange. Recebe `SyntheticPosition` PRE3 com `SyntheticExitPlan` PRE1 e um `tuple` opcional de `SyntheticPositionExitFill`. Invoca o replay PRE3/PRE2 **antes** da análise para reusar suas regras de data/ID/tranche/conservação. Os limites de `SyntheticLotFixture` são parâmetros de teste, não evidência de fonte; cada tranche e cada fill único são validados separadamente, sem converter ordem ou preço. Residual zero é tratado como posição fechada apenas dentro da fixture matemática. Saída revela flags de fonte, lot step e trading **sempre falsas** mesmo quando compatibilidade de múltiplos exatos é verdadeira. J1/J3/J4 operacionais seguem bloqueadas.


## J3/PRE1 — Detector puro de barreiras em candles sintéticos sem caminho/fill
`synthetic_intrabar_barriers.py` consome `ClosedCandle` de `quality=synthetic_fixture` e usa os wrappers públicos `validate_synthetic_closed_candles` e `validate_synthetic_research_price` de `synthetic_feature_engine.py`, que reutilizam a validação J2 já integrada: identidade, UTC, fechamento, Decimal e OHLC. Não há adaptador novo, storage, rede, conta ou execução. `SyntheticBarrierPlan` define níveis hipotéticos antes da série; `observe_synthetic_intrabar_barriers` valida a série INTEIRA antes da pesquisa e retorna apenas a primeira observação. Distingue abertura já fora do intervalo de toque apenas pela faixa; dois+ toques na mesma vela são `MULTIPLE_LEVELS_UNORDERED`. Não supõe trajetória high/low, fill, preço de execução, taxas, funding ou fórmula de liquidação da exchange. Saída imutável com flags live, backtest financeiro, lucro e path sempre false. J3 #4 continua aberta até motor financeiro reproduzível sobre dados aceitos.


## J3/PRE2 — Contabilidade de custo isolada de execução e de OHLC
O novo `synthetic_cost_scenarios.py` é camada aritmética pura dependente apenas de `DataValidationError` e do enum de direção de pesquisa J3/PRE1. Recebe `SyntheticCostScenario` com notionals hipotéticos **de quote abstrata**, taxas/impacto adverse em bps, janela temporal e `tuple` opcional de `SyntheticFundingEvent` com IDs prefixados `fixture_funding_*`. O cálculo em `Decimal` local de alta precisão não usa preço, margin, alavancagem, contrato, lucro, preenchimento, base/quote de exchange, storage, rede, posição real ou ordem. Funding assinado usa convenção explícita sintética, com identidade somente no replay em memória e timestamps estritamente crescentes, rejeitando duplicata de instante com IDs diferentes para reduzir contagem duvidosa. Resultado imutável separa fee, slippage e signed funding; `total_signed_cost_units` pode ser negativo e não é PnL. Todos os gates reais de venue, licença/moeda e trading são invariavelmente falsos. J3 #4 não homologada.
