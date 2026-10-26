# Arquitetura candidata para a J0

A tecnologia específica será escolhida por adequação, licenças e limites reais da VPS, não por preferência de framework.

## Módulos previstos
1. Adaptadores de futuros perpétuos: fontes públicas REST/WebSocket, metadados de contrato, OHLCV, mark price, funding, open interest quando disponível.
2. Pipeline de dados: ingestão, histórico, UTC, candles fechados, controles de lacuna/duplicação e histórico de composição do universo.
3. Feature Engine: indicadores determinísticos sem acesso a dados futuros.
4. Strategy & Regime Engine: contexto BTC, tendências, rompimentos, compressão, correções, força relativa, liquidez e ranking.
5. Position/Order Ledger & Risk: intenção de ordem, fills e estado reconciliado, margem e alavancagem de abertura, PnL realizado/não realizado, custos, funding, exposição e correlação.
6. Winner Management: alvos, saídas parciais, trailing e posições residuais.
7. Research: backtesting com mesma semântica de sinais da operação prospectiva, liquidação intrabar e walk-forward.
8. API/UI: acesso protegido às posições e ordens; interface PT-BR mobile, estado do robô, alertas idempotentes e kill-switch.
9. ML/LLM: extensões opcionais submetidas a validação independente.
10. AutoExecutionEngine: cadeia signal -> risk -> intent persistida -> adapter venue -> ack/fills reconciliados -> saídas; implementação simulada primeiro e live somente após gate.

## Candidatos gratuitos
Python, bibliotecas científicas, FastAPI, PostgreSQL, DuckDB/Parquet, CCXT, Freqtrade quando compatível e n8n existente, se útil. Nenhum deles é obrigatório antes de uma decisão de arquitetura registrada.

## Fronteiras
Adaptadores de DADOS continuam read-only. O executor de ORDENS é componente separado, iniciado com `offline_paper` e travado para produção; projetar contratos offline sem abrir endpoints reais nesta fase. Nunca guardar segredos no GitHub público. Estados e cálculos financeiros devem ter precisão, idempotência e testes independentes.


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


## J1/WU29 — Crosscheck de metadados de identidade de contratos Kraken
No estágio de seleção `kraken_eligibility._why_ineligible`, antes de usar `volumeQuote` e ordenar `UniverseSnapshot`, há conferência estrutural do numerador do símbolo `PF_<base>USD` com `instrument.base`, `instrument.pair` e `ticker.pair` (quando informado). O comparador canônico conhece apenas `XBT`→`BTC`, alias documentado da API Futures, e **não aceita** multiplicadores/símbolos de mercado sintetizados por conversão de string arbitrária. `CryptoRegistryHistory.select_at` herda a proteção sem alterar persistência, histórico ou integridade SHA dos manifestos. O resultado excluído recebe motivo estável `symbol_base_mismatch`, preservando demais filtros e ordenação Decimal. Continuidade dos gates J1 #32/#36/#48 é externa, com direitos e autenticidade não autoafirmáveis.


## J1/WU30 — Validação canônica no `CryptoRegistryHistory.append`
O histórico de identidade não confia mais no tipo da dataclass como marcador de revisão: `_revalidate_snapshot_for_history` exige `CryptoRegistrySnapshot` exato e tuples imutáveis de `VerifiedAsset`/ `IdentityEvidence` exatos, reconstrói o manifesto `schema_version=1, usage_policy=internal_research_only` com dados fornecidos e invoca **o mesmo `from_manifest` existente**. A igualdade final verifica `publisher_root` derivado, que não participa diretamente do hash JSON. Mantém API, timestamps, seleção e persistência inalterados; não adiciona banco, rede nem schema de produção. SHA íntegro não autentica identidade ou licença, e o histórico não permite que fixture diretamente construída com hash arbitrário vire seleção de mercado.


## J1/WU47 — Binance/Bybit como candidatas de execução manual (26/10/2026 UTC)
O Product Owner informou que tem contas na Binance e na Bybit. **Isso não é evidência de acesso a futuros, habilitação regional de API, qualidade de OHLCV, alavancagem, ou autorização para usar credenciais.** Ambas são **candidatas**, nenhuma foi selecionada. O produto mantém execução **manual**, sem endpoints de ordens, chaves ou conexão à conta. Fonte de pesquisa não precisa coincidir com a venue de eventual execução, mas um sinal só poderá ser considerado executável após reconciliação de preço, símbolo, contrato, quote/settle, lot/step/min notional, funding, taxas, liquidez, limites de risco e disponibilidade na venue específica. Kraken price-only é pesquisa auxiliar e não certifica Binance/Bybit.
Binance USD-M já tem adaptador/fixtures offline, mas o run real anterior foi bloqueado HTTP451 (#19). Bybit linear V5 possui parser documentado de volume BASE/turnover QUOTE em USDT/USDC, porém o único run real foi restrito no primeiro GET (WU44, 0 candles). Não repetir nem contornar restrições. O relatório `scripts/j1_readiness_report.py` distingue as duas candidatas com flags `account_access_verified=false`, `live_signal_approved=false`, `manual_plan_approved=false`, `order_execution_enabled=false`. Essa enumeração não concede direitos de dados, não escolhe venue nem homologa J1 #2, #32, #36 ou #48. Custo adicional R$0; sem credenciais, dados de conta, ordens, deploy ou feed público.


## D77 — engine de entradas e saídas automáticas (destino final)
O usuário **não precisa confirmar cada operação**: após futura autorização do modo live, o motor tomará decisões quantitativas, abrirá e gerenciará posições automaticamente na venue selecionada, inclusive saídas fracionadas e residuais. O estado `live` não é autorizável pela mera seleção de Binance ou Bybit no relatório: exige gates técnicos e de release. Separar `StrategySignal`, `RiskApproval`, `OrderIntent`, `ExecutionAdapter`, `Fill/OrderLedger` e `EmergencyStop`. Fluxo idempotente com ordem cliente determinística, eventos persistidos, reconciliação após timeout/restart, exits reduce-only onde válidos, stops nativos e telemetria de estado. Nenhum código de dados públicos pode ser reaproveitado para transmitir uma ordem sem novo contrato específico da venue e revisão de permissões. Fonte: `docs/AUTOMATED_EXECUTION_SPEC.md`.


## J4/AUTO1 #149 — ciclo de ordens exclusivamente PAPER
`synthetic_order_lifecycle.py` acrescenta um contrato tipado de `PaperOrderIntent`, `PaperOrderEvent`, `PaperOrderSnapshot` e `replay_paper_order`. Ele **não** acessa contas, APIs ou credenciais, não contém transporte, signer, cliente REST/WS ou envio de ordens. Reutiliza `SyntheticSide` e validadores de quantidades/tempo dos módulos J4 já existentes. Uma ordem hipotética possui quantidade, lado, efeito OPEN ou REDUCE_ONLY, tempo UTC, venue candidata e evento sintético. ACK não cria fill; UNKNOWN impede inferir falha; duplicatas exatas são idempotentes apenas no replay em memória; fills parciais preservam quantidade; efeitos e limites de redução evitam inversão inadvertida em fixtures. Isto é uma **pré-condição técnica** para o futuro executor e reconciliação persistente, não implementação nem aceite do robô automático.


## J4/AUTO2 — persistência PAPER separada dos candles
`SQLitePaperOrderJournal` é um componente local de referência independente de `SQLiteMarketDataStore`, sem usar suas tabelas, sem migration, e sem I/O de rede. Reutiliza `PaperOrderIntent`, `PaperOrderEvent`, `replay_paper_order` e os validadores Decimal/UTC existentes. `reserve` toma reserva OPEN por `fixture_signal_id`, `append_events` reaplica o reducer antes de gravar eventos e checkpoint na mesma transação, e `load` confere hashes, ordem, cursor e replay. Simula recuperação de estado após restart, mas não substitui Order/FillLedger real nem uma política de risco por posição. Bancos de pesquisa devem ficar locais e fora do GitHub público; live/trading continua desabilitado.


## J4/AUTO3 — revisão pura de risco simulado
`paper_risk_gate.py` é um módulo sem I/O. Distingue `PaperRiskLimits` explícitos, `PaperRiskObservation` fictícia e `PaperRiskDecision` imutável; calcula notional em moeda de cotação usando Decimal, rejeita snapshots futuros/obsoletos e nega novos OPEN com kill-switch/perda/limites ou OPEN incerto. Ordens `REDUCE_ONLY` permanecem apenas planos hipotéticos quando o kill switch pausa entrada. Nenhuma política de risco real é hardcoded: cap de ordem, exposição, perda, pendências e idade máxima são parâmetros, sujeitos aos testes da J3. Não conecta `PaperRiskObservation` à verdade da exchange ou à lista persistida de intenções J4/AUTO2, logo não é gate live nem substitui reconciliação real.


## J4/AUTO4 #155 — posição PAPER como agregado transacional
`SQLitePaperPositionJournal` mantém abertura confirmada por `PaperOrderEvent(FILL)`, `SyntheticExitPlan`, intents `REDUCE_ONLY`, eventos e checkpoint em **uma única linha SQLite versionada**, atualizada sob `BEGIN IMMEDIATE` com índice global de ID de ordem. Um único arquivo independente previne divergência entre saldos e reservas em atualizações concorrentes, rollback e restart; replays `PaperOrderIntent`/eventos usam `replay_paper_order` de AUTO1 e percentuais usam `plan_synthetic_partial_exits` da PRE1, sem duplicar as fórmulas. A API anterior `SQLitePaperOrderJournal` permanece v1 para pesquisas de ordens isoladas e não se torna silenciosamente uma fonte de saldos; bancos v1 não são migrados para o schema de posições. Um futuro integrador J4 deve consolidar contas/estratégias, posições efetivamente reconciliadas e risco da venue antes de habilitar conectores de ordens.


## J4/AUTO5 — fluxo de integração demonstrativo sem conectores
`scripts/demo_automated_paper_cycle.py` demonstra um único percurso com funções e SQLite PAPER preexistentes; não cria nova engine, provedor ou gerador de sinais. A integração entre `SQLitePaperOrderJournal` e `SQLitePaperPositionJournal` usa **dois bancos temporários sem transação entre arquivos**: a abertura confirmada no primeiro é materializada de forma idempotente no segundo por eventos explicitamente simulados. Isso não garante exactly-once de rede nem reconciliação real; são necessários contratos e infraestrutura próprios antes de testnet/live. A apresentação JSON foi desenhada para permitir inspeção do ciclo sem alegar mercado financeiro ou resultados verdadeiros.


## J4/AUTO6 — gate PAPER dentro do journal
`reserve_open_if_paper_risk` reutiliza `_reserve_on_connection` (mesma inserção que `reserve` legado), `_checked_entry` e `evaluate_paper_risk` dentro de **uma única transação SQLite**. Lê todas as ordens locais, valida inclusive REDUCE_ONLY para detectar índice adulterado, conta apenas OPEN não terminais, combina suas pendências com alegações externas por máximo/OR e aplica os limites antes de gravar nova OPEN. Isto elimina a janela de corrida entre calcular pendências e inserir a ordem PAPER; não confundir com atomicidade de exchanges ou dos dois bancos temporários do demo. Script AUTO5 foi atualizado para consumir o novo recibo de preflight/reserva.


## J5/PRE1 #161 — UI isolada e segura para demonstração PAPER
`web/paper-demo.html` é um arquivo local independente, com HTML semântico, CSS embutido e layout responsivo, `lang=pt-BR` e CSP que desabilita rede, scripts, formulários e iframes. Não carrega market data ou dados privados, não tem endpoint/botão para ordens, nem conecta a stores SQLite. Os valores visíveis são uma fotografia estática **do cenário fictício** de `scripts/demo_automated_paper_cycle.py`; `tests/test_paper_dashboard_contract.py` compara esses números com a execução de ambos os candidatos em cada CI. A futura interface J5 terá contrato de dados/autenticação/estado próprio, após gates J1/J4/J6; esta página não substitui essa integração.


## J5/PRE2 #164 — fronteira PAPER para exportação local versionada
`scripts/render_paper_dashboard.py` invoca exclusivamente `simulate_automatic_paper_cycle` (AUTO5) em processo, valida envelope de versão `paper_dashboard_snapshot_v1` e campo por campo dos dois cenários, rejeita chaves extras/credenciais, `live`, PnL, fonte não fictícia e divergências de tranches. Valida os alvos 50/60/70 usando o planejador PRE1 (não recalcula alocação no renderizador). Elementos identificados por `data-metric` e `data-snapshot-key` em `web/paper-demo.html` são preenchidos com texto numérico escapado; ausência/duplicação de marcador falha sem produzir página. O arquivo original continua prévia estática; HTML novo é apenas um artefato local sem JavaScript, conexão, autenticação ou fluxo de mercado. CLI exporta HTML (padrão) ou JSON de fixture gerada internamente; escrita em arquivo **somente por criação exclusiva** (não sobrescreve). Não existe endpoint HTTP ou caminho de importação de JSON arbitrário. Nenhuma evidência de renderização em browser/dispositivo ou auditoria WCAG completa deve ser alegada a partir desses testes.


## J5/PRE3 #166 — auditoria de browser isolada de mercado
`scripts/audit_paper_dashboard_browser.py` chama o renderer J5/PRE2 diretamente sobre fixtures internas J4/AUTO5 e fornece HTML em memória a Chromium via Playwright `set_content`, interceptando/abortando qualquer requisição externa. Não consome JSON/HTML por argumento, API, credenciais ou dados privados; não executa browser com contas autenticadas. O script mede DOM e foco em 6 larguras, verifica overflow fora da região horizontal de tabela e contraste de alguns textos; imagens e relatório JSON são **somente evidências temporárias e sintéticas**. Workflow `.github/workflows/paper-mobile-browser-qa.yml` roda em runner Ubuntu público e pode anexar screenshots de PAPER, sem publicar market data. `render_paper_dashboard` audita tags e atributos HTML, permitindo um único `href="#conteudo-principal"` para skip-link e rejeitando URLs/recursos/scripts/handlers. Auditoria browser não substitui avaliação manual WCAG ou release.


## J5/PRE4 #168 — fronteira estritamente read-only para snapshot de posições
`crypto_intelligence_agent/paper_position_inspection.py` oferece `inspect_paper_position` e abre **somente arquivos SQLite regulares já existentes**, via URI criada por `Path.as_uri() + '?mode=ro'`, `uri=True`, `PRAGMA query_only=ON` e transação de leitura. Nunca instancia o construtor gravador AUTO4/AUTO2, que inicializa tabelas e usa `BEGIN IMMEDIATE`. Recusa banco ausente/URI direta/symlink, schema/table/version estranhos, corrupção, posição desconhecida, índice/sha/checkpoint ou evento com replay inconsistente. Reaproveita `SQLitePaperPositionJournal._read`, `_balance` e, quando se fornece o segundo arquivo explicitamente, `SQLitePaperOrderJournal._checked_entry` para comparar OPEN intent e eventos. Os bancos são lidos em momentos distintos: **não há transação ou reconciliação exactly-once entre dois arquivos**, e digest SHA256 é somente integridade local, não autenticação de exchange.

`scripts/inspect_paper_position.py` renderiza snapshot allowlisted `paper_position_snapshot_v1` ou HTML `web/paper-position-template.html`, em português, somente leitura, sem JS/HTTP, com tabela focável e legenda de UNKNOWN. Utiliza política HTML conservadora J5/PRE3, substitui marcadores fixos por valores com escape de HTML e exige escolha de uma identidade de posição. Exportação só cria arquivo novo (ou stdout), não lê JSON arbitrário, não expõe conta, chaves ou retorno financeiro. A workflow `paper-mobile-browser-qa.yml` usa Chrome sobre uma fixture SQLite temporária para conferir layout/teclado sem market feed; nenhuma homepage/live API é criada.


## J5/PRE5 #170 — snapshot consistente multi-posição, sem totalização financeira
`inspect_paper_positions(path, position_ids)` estende o adaptador PRE4 `mode=ro`: exige tupla de IDs únicos `fixture_...`, no máximo 128 por chamada como limite de recurso, abre **um único arquivo** AUTO4, verifica schema/version e lê TODOS os agregados sob a mesma transação `BEGIN`. Reusa `SQLitePaperPositionJournal._read` e `_balance` para hash, cursor e replay causal, sem construir escritor/DDL. Em falha de qualquer ID não retorna snapshot parcial. Suporta posições em venues/símbolos diferentes apenas por seleção consciente, sem namespaces de contas ou somatório de unidades heterogêneas. O exporter `scripts/inspect_paper_positions.py` e `web/paper-positions-template.html` criam JSON `paper_positions_snapshot_v1` ou HTML PT-BR sem JS/rede, usando política de template PRE3, escape de texto e saída exclusiva. Auditoria real `scripts/audit_multi_paper_positions_browser.py` exercita Chrome em seis larguras e estados UNKNOWN atribuídos à posição correta, com fixture SQLite temporária. Não é carteira de corretora, stream, monitoramento 24/7 ou controle de ordens.
