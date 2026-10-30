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



## J3/PRE3 — fronteira de walk-forward offline

O planejador de folds `synthetic_walk_forward.py` tem responsabilidade EXCLUSIVA de dividir uma série `ClosedCandle` sintética validada em treino/gap/teste temporal com índices half-open, stride não sobrepondo os blocos OOS e tempo de disponibilidade do último candle de treino. Não contém otimizador, métricas de trade, fills ou estratégia J2 acoplada. Um fold futuro pode treinar com amostras que já foram OOS em fold anterior, porque chegaram a ser históricas depois; isso não permite usar OOS do próprio fold para ajustar configurações. A avaliação futura com labels de trades, horizon purging, custos/funding/liquidação e benchmark exige módulo separado e dados J1 homologados. NENHUM endpoint, conta, ordens ou live.

## J3/PRE6 — avaliação financeira condicional

`synthetic_financial_scenarios.py` compõe `SyntheticBarrierObservation` PRE1 com `SyntheticCostScenario` PRE2, sem reimplementar funding/taxas ou inferir fills de candles. Recebe branches de entrada/saída ou perda de liquidação explicitamente declarados, com fonte/moeda/sinal de funding, e devolve alternativas condicionais em `Decimal`. Não contém rede, persistência, ledger de exchange ou superfície de ordem; flags de validação financeira e live permanecem falsas.



**Contrato endurecido na revisão da PR #181:** o avaliador PRE6 exige `SyntheticBarrierPlan` original e `assumed_barrier` em cada ramo; reconcilia preço × quantidade com nocionais explícitos de custos, restringe o encerramento ao candle observado e recusa alternativas que omitam alguma das barreiras realmente atingidas. A perda de liquidação e seu notional de taxas permanecem independentes, hipotéticos. O resultado carrega a barreira presumida para auditoria, nunca uma ordem/fill real.

## J3/PRE7 — ciclo causal integrado

`synthetic_research_cycle.py` apenas orquestra J2/PRE2 e J3/PRE1–PRE6. Ele reconstrói folds/purge/OOS, reexecuta hipóteses por prefixos fechados e só observa barreiras a partir da primeira barra cuja abertura seja posterior à disponibilidade do candidato. Ramas financeiras são entradas externas explícitas; não há soma de alternativas, persistência PAPER, rede ou ordem.

**Limite de replay PRE7 revisado:** o corte efetivo de observação é `min(fold.test_end, outcome_index+1)`; apenas candles com `open_time_ms >= close_do_sinal + close_safety_ms` podem entrar na inspeção PRE1. PRE7 rejeita chaves não candidatas dos planos/cenários, inclusive bool, pressupostos não tipados e horários de entrada diferentes do OPEN da primeira barra permitida. A avaliação não observa outros folds, nem reaproveita períodos posteriores quando o horizonte terminou. Um evento registra número do fold e fim exclusivo da janela.


## J4/AUTO7 #188 — adaptador causal de hipótese J2 ao risk gate PAPER

`causal_paper_open.reserve_causal_paper_open` é camada fina, sem HTTP nem adaptador Binance/Bybit. Primeiro executa J2 somente no prefixo fechado à data de decisão; considera hipótese fresca exclusivamente se sua barra fechar no último índice. Sem sinal, devolve abstenção sem inserir intenção. Com sinal, cria `PaperOrderIntent` com ID estável do candle/estratégia e lado LONG/SHORT, sem usar PRE5/PRE7 ex-post ou preço do sinal como `mark_price`. A reserva chama o **único** `SQLitePaperOrderJournal.reserve_open_if_paper_risk`, que já possui o gate de risco e unicidade sob `BEGIN IMMEDIATE`. Resultado aprovado por risco representa apenas entrada PAPER pendente, não fill. Resultado negado preserva motivo e não escreve OPEN. Nenhuma nova tabela, migração, chave ou endpoint é acrescentado.

## J4/AUTO8 #190 — auditor de saúde OPEN PAPER entre journals independentes

Antes de uma nova reserva causal, `causal_paper_open` invoca `paper_open_health.audit_paper_open_health` sobre caminhos AUTO2/AUTO4 distintos e existentes, ambos em SQLite read-only. O auditor reutiliza os leitores canônicos, limita a varredura e falha em checksum, schema, cursor, payload, ID duplicado ou identidade de abertura inconsistente. Não existe snapshot atômico entre arquivos: o recibo declara isso e uma posição/FILL pendente de prova bloqueia, ao invés de presumir sincronismo. Mesmo o par OPEN+posição+plano exatamente correspondente é apenas `PROTECTED_HYPOTHETICAL_ONLY`, logo a causa explícita `paper_open_unverified_protection` impede outra OPEN. REDUCE_ONLY não passa por essa trava.


**Revisão AUTO8 (corrida TOCTOU):** uma auditoria read-only independente não autoriza uma abertura posterior. O adaptador AUTO7 chama exclusivamente a operação `SQLitePaperOrderJournal.reserve_open_if_paper_risk_with_health`; ela inicia `BEGIN IMMEDIATE` no arquivo AUTO2, valida esquema e todas as OPENs, lê AUTO4 em RO e só então, com o lock AUTO2 ainda retido, executa o preflight AUTO6 e a reserva. Eventos FILL AUTO2 concorrentes não podem aparecer entre a auditoria e o INSERT. As duas bases continuam distintas sem transação/snapshot compartilhado; o resultado expõe `cross_database_atomic_snapshot_available=false` e não representa proteção native STOP. `audit_paper_open_health` isolado é ferramenta de diagnóstico RO, não preflight suficiente.


## J4/AUTO9 #192 — gate conservador para posição PAPER encerrada

O auditor AUTO8 reutiliza o `_balance` canônico de AUTO4 e somente classifica `CLOSED_FLAT_HYPOTHETICAL_ONLY` quando há eventos de FILL REDUCE_ONLY explícitos que levam exatamente a zero, com estados de saída terminais e sem runner/reservas. A transação `BEGIN IMMEDIATE` do journal AUTO2 retém o lock na verificação de saúde, risco e reserva; o `decision_at_ms` é passado ao replay para recusar checkpoints futuros de ambos os arquivos SQLite. AUTO4 continua lido separadamente sem atomicidade cross-DB. Diagnóstico read-only isolado não substitui o gate transacional nem a validação real de proteção.


## J6/PRE1 #198 — invólucro in-memory de decisão incremental PAPER

`crypto_intelligence_agent.offline_paper_forward_session.OfflinePaperForwardSession` é camada fina sobre `synthetic_feature_engine._checked_candles` e `causal_paper_open.reserve_causal_paper_open`. Cada chamada com prefixo fechado verifica continuidade, identidade, integridade de todos os registros previamente aceitos e instante exato de decisão. Somente após o gate AUTO7/8/9 devolver resposta válida avança o estado da instância. Sinal atual pode produzir intenção OPEN `PENDING` com zero fills; no-signal ou risk-denial não inventa evento. Sessão usa lock local e limite de memória, sem checkpoint persistente, fila, worker, webhook, app, socket ou fonte de dados real. A garantia da transação de ordens continua restrita ao arquivo AUTO2; AUTO4 é banco independente. Exigir reconciliação externa na inicialização futura de fluxo real.


### J6/PRE2-A #200 — pré-requisito de integridade offline (26/10/2026 UTC)

Foi acrescentado contrato puro de selo determinístico SHA-256 para prefixos sintéticos completos e contexto versionado, com escala Decimal preservada e extensão de exatamente uma barra. É uma preparação verificável para recuperação futura, **não** checkpoint durável, transação conjunta com AUTO2, proteção de exchange, stream prospectivo ou homologação. A issue #200 permanece aberta: próximo passo é integrar cursor e reserva/no-signal na MESMA transação AUTO2, com crash tests e auditoria do schema RO, ou manter fail-closed se inviável. AUTO4 continua sem snapshot atômico cruzado. Nenhuma rede, ordem real, migration produtiva ou custo.


### J6/PRE2-B #200 — cursor transacional de fixture em AUTO2 (26/10/2026 UTC)

O módulo `offline_paper_durable_cursor.py` acrescenta API offline explícita com cursor SHA-256 e inventário de OPENs em metadado opcional do próprio banco AUTO2, sem migração de schema ou produção. Um único `BEGIN IMMEDIATE` verifica prefixo/versão, saúde AUTO8/AUTO9 e risco AUTO6, reserva intenção PENDING e atualiza cursor; no-signal e risco negado também registram progresso. A recuperação compara integralmente prefixo e contexto e rejeita replay, saltos, mudança de venue/quantidade/limites e OPEN legada sem cursor. AUTO4 continua arquivo independente, sem snapshot comum. `OfflinePaperForwardSession` PRE1 permanece in-memory. Nenhuma fonte de mercado real, rede, credencial, execução, deploy ou gasto. PR/CI e fault injection de processo ainda precisam ser validados; não declarar J6 homologada.

## J1/WU54 #215 — banco de staging Bybit offline e isolado (27/10/2026 UTC)

`crypto_intelligence_agent.bybit_research_storage.SQLiteBybitResearchStore` encapsula SQLite da stdlib em arquivo de laboratório criado explicitamente pelo chamador, com tabelas próprias `bybit_research_meta`, `bybit_research_pages`, `bybit_research_candles`. Rejeita banco existente com tabelas canônicas `candles`, `checkpoints`, `contract_specs`, `universe_snapshots` ou `collection_events`; não altera `storage.SQLiteMarketDataStore`. Uma única transação `BEGIN IMMEDIATE` envolve página e candles, com FKs, rollback por falha e lock sem espera/retry.

Fluxo **exclusivamente offline**: bytes JSON estritos + `LocalBybitCaptureManifest` datado **autodeclarado** → `decode_public_market_json_exact` → parser WU39 `stage_bybit_documented_linear_pair` (metadados/identidade/candle/UTC/Decimal/BASE e QUOTE) → SQLite de pesquisa → `replay_page` / `quality_report`. O contrato não aceita uma instância de `ClosedCandle` nem chama o commit canônico; replay retorna `BybitResearchStoredCandle`. Janelas futuras contíguas podem ser anexadas somente para o mesmo símbolo/intervalo/revisão/ambiente e com bytes/metadata imutáveis em replay. A origem de fixtures **não é certificada** por SHA ou `capture_environment`; não existe tomada de decisão real, serviço, thread ou coletor nessa camada.

A amostra real WU53 #213 provou 3 candles fechados na VPS, mas `data_stored=false`: ela **não** está nem pode aparecer magicamente neste banco. Gates J1/J6 e permissões comerciais permanecem independentes.



## J4/J5/AUTO #232 — kill-switch PAPER duravel, sem acesso a corretora (27/10/2026 UTC)

Em resposta a necessidade concreta D77 de supervisao, o operador local pode persistir pausa de novas OPEN no journal AUTO2 SQLite existente. O modulo paper_operator_kill_switch.py grava somente chave opcional versionada paper_operator_kill_switch_v1 em paper_order_meta (sem tabelas novas), com estado active, sequence CAS, instante UTC-ms, acao pause/resume, JSON canonico e SHA256 de integridade. Ausencia de chave em banco antigo significa estado nao pausado legado; chave malformada/inesperada e bloqueada pelos leitores strict. Hash NAO autentica operador nem protege contra adversario que pode escrever no SQLite.

**Fio causal unico:** SQLitePaperOrderJournal._reserve_open_risk_locked combina (OR) a pausa persistida lida DENTRO de BEGIN IMMEDIATE com a flag do PaperRiskObservation; nenhuma fixture antiga com kill_switch_active=False pode ignorar pausa gravada. O caminho J6 step_durable_offline_paper usa o mesmo metodo e continua mantendo cursor de eventos no mesmo commit, inclusive em negacao de entrada. O metodo legado reserve tambem recusa OPEN enquanto pausado. REDUCE_ONLY PAPER hipotetico segue permitido; a chave nao cancela ordens pendentes, nao instala stops nativos, nao encerra posicoes, nao atua em qualquer exchange e nao autoriza negociacao real.

**Uso LOCAL futuro com arquivo POSIX 0600 em pasta 0700 ja existente** (nao executado na VPS): python3 -m scripts.control_paper_kill_switch --journal /arquivo/privado/orders.sqlite --action status; para pausar: --action pause --expected-sequence N; para retomar: --action resume --expected-sequence N --confirm-paper-resume. O status publica apenas sequence, UTC-ms e paused/not_paused, com flags live sempre falsas. Alteracao usa CAS e troca de estado sequencial, exige horario monotono e confirmacao de resume, nao permite escrever se o arquivo estiver ausente, com permissoes incorretas ou apontando a symlink/hardlink. Nenhum endpoint HTTP, chave ou rotina automatica de live e introduzido.

**Limites:** Gate PAPER local, nao kill-switch financeiro de producao; so protege caminhos de reserva de ordens de fixture no journal correspondente. Nenhuma autonomia de UI web sobre o estado sem autenticacao; nenhum deploy, VPS, testnet, ordem real ou custo novo. Tests adversariais incluem reinicio, corrida de duas instancias, metadado adulterado, OPEN legacy, risco com fixture stale, REDUCE_ONLY, cursor duravel, arquivos POSIX, CLI e reabilitacao explicita. CI docs, Windows offline e Chrome/PAPER no SHA final e obrigatoria; J4 #5/J5 #6/J6 #7 permanecem abertas e J1 historico permanece bloqueada.



## J6/PRE3 #234 — batch automatico FINITO de pesquisa PAPER, sem ordens reais (27/10/2026 UTC)

Entrega: `crypto_intelligence_agent/offline_paper_batch.py` reutiliza PRE2-B `step_durable_offline_paper` e `recover_durable_offline_paper` (mesmo SQLite AUTO2 e seus contratos), nao cria segundo ledger/cursor. Recebe candles ClosedCandle exclusivamente `quality=synthetic_fixture`, observacoes de risco PAPEL explicitamente ficticias e alinhadas por candle, configuracao J2/limites e journals existentes. Valida TODA a serie/identidade/horario antes do primeiro write, processa no maximo 64 candles novos por chamada, registra por passo resultado PENDING/recusa/no-signal sem produzir FILL, em `BEGIN IMMEDIATE` existente, e recupera restart comparando integralmente hash do prefixo, estrategia, venue, lot e inventario das OPENs. Novamente sobre dados totalmente processados = nenhuma nova escrita. Prefixo alterado, historico curto, risco com venue/tempo errado, metadata ou OPEN inconsistente: fail closed. Crash entre passos deixa somente commits completos, que sao retomados de maneira auditavel. O kill-switch PAPER D116 bloqueia novas OPENs sem esconder motivos de recusa nem retroemitir sinais antigos apos resume.

Comando demonstravel: `python3 -m scripts.demo_durable_offline_paper_batch` ou com `--demonstrar-pausa`. Ele cria candles inventados e sqlite TEMP, executa automaticamente uma sequencia de barras, simula reinicializacao do processo mediante reabertura do mesmo journal, completa o restante, verifica reexecucao sem duplicidade e remove os arquivos ao terminar. A saida e resumo em portugues de contagens/flags; nenhum dado bruto de mercado, chave, arquivo real ou ordem. Esta demonstracao NAO e daemon, fonte em tempo real, live feed, fluxo testnet, estrategia validada, resultado financeiro, exchange-native stop ou permissão de usar 50x. Nenhum job/cron/deploy foi ativado; custo adicional R$0.

Tests: primeiras 5 barras, abertura PAPER ficticia na sexta, checkpoint/OPEN pendente, reinicio, 0 duplicatas, pausa persistida, resume sem recuperar trade passado, limitacao de batch, validacao de todas observacoes, escala Decimal, alteracao retroativa de prefixo, falha entre passos, CLI e ausencia de rede. Aceite restrito a CI Linux/docs, Windows-offline, Chrome/PAPER no SHA exato de PR #235 (HEAD 9ae1097a71d0541c5dc56c04e04abaab76b0ddfb, integrada em e09ec9f5c9d9bb264def3c744303e929c8b5c2f8; CI pré/pós 3/3 SUCCESS), e revisao. J6 #7 permanece sem homologacao por falta de J1 canônico/licenciado, feed prospectivo verdadeiro, reconciliacao financeira, monitoramento continuo e seguranca de ordens reais; D77 destino automatico permanece.



## J5/UI #236 — tela local somente leitura com estado persistente PAPER (27/10/2026 UTC)

Problema: o dashboard de demonstração J5 mostrava apenas duas posicoes sinteticas fabricadas e NAO permitia ver se o kill-switch D116 e o cursor J6 PRE3 estavam de fato persistidos no journal em uso. Sem mudar o dashboard anterior, adicionar `crypto_intelligence_agent/paper_operator_status.py` e `scripts/render_paper_operator_status.py` com CLI `python3 -m scripts.render_paper_operator_status --journal /privado/orders.sqlite [--format html|json] [--output /caminho/novo.html]`. O leitor usa `_read_database` SQLite `mode=ro`/`PRAGMA query_only`, verifica esquema, meta keys, digest de cursor, identidade/inventario de OPENs, recupera pausa `paper_operator_kill_switch_v1` e compara o numero de OPENs pendentes/UNKNOWN pelo replay do journal. Falha fechada se houver corrupcao, chave desconhecida, caminho ausente, incongruencia de contagem ou dados de origem inesperada. So mostra estado deste arquivo AUTO2; NAO consulta conta, corretora nem posicoes AUTO4, e nao prova stop instalado. Nenhum endpoint HTTP ou credencial.

A pagina HTML offline em PT-BR apresenta um cabeçalho visivel 'SOMENTE SIMULACAO', estado de pausa de NOVAS OPENs PAPER, sequencia/horario UTC, contador de candles ficticios processados, quantidade de OPENs locais e UNKNOWN que precisa reconciliar. Layout responsivo sem overflow concebido para viewport 280..390px; CSS inline, sem script, rede, formulario ou botao que sugira dar ordens. CLI pode exibir JSON estrito ou HTML, opcionalmente criar arquivo novo com modo exclusivo sem sobrescrever. Leitura nao altera SQLite. O usuario que precisar alterar a pausa usa o controle local previamente homologado #232, nao a pagina. Nao mencionar 'robô ativo em producao' quando a pausa esta desligada: os outros gates financeiros seguem obrigatorios.

Testes: journal vazio, cursor com 6 candles e OPEN PENDING, restart, pausa/resume, UNKNOWN, checksum/meta corrompidos, arquivo ausente, HTML estatico/viewport/sem links de rede, sem leaks de caminhos/valores, JSON tipado, output exclusivo e no-network. J5 #6 continua sem produto online ou automacao de mercados; J1 #2 e J6 #7 ainda bloqueadas para dados reais/monitoramento. Nenhum release, migração, trading, acesso de conta, nova despesa nem VPS. Patch revisto; PR #237 (HEAD d38b7f6bd085e9e7cd668b72464d00743d237ac2) integrada em 4cdf6a8c51bd33a186a60a958bb3093a4280957f; CI pré e pós merge 3/3 SUCCESS no SHA exato. Nenhum review independente registrado.



## J1/HIST #239 — série histórica multi-mês somente offline (27/10/2026 UTC)

`crypto_intelligence_agent/offline_vision_series.py` recebe **2..24** objetos `OfflineVisionMonth` já inspecionados por `inspect_offline_vision_month`, e monta uma série de pesquisa de 1h contígua em UTC, incluindo virada dezembro/janeiro, fevereiro de ano bissexto, mês integral, OHLCV Decimal e limite explícito de memória. Recusa arquivo reordenado/duplicado, mês ausente, identidade/símbolo alterado, dados de futuro, timestamps internos forjados, OHLC/volume inválidos, hash e nomes não canônicos. O hash do manifesto é somente uma soma de identidades dos ZIPs **alegadas pelo chamador**, não uma assinatura de Binance nem um hash de bytes reautenticado. Saída imutável `OfflineVisionResearchSeries` distinta de `ClosedCandle`; nenhum fornecedor, licença, feed, TOP50 histórico, desempenho, lucro ou ordem é homologado. Não existe fetch de ZIP/HTTP, cron, armazenamento de dataset nem execução de mercado. Os testes usam objetos totalmente sintéticos. Binance Vision Dataset Terms v1.0 (26/08/2026) autoriza estudos históricos estritamente pessoais não produtivos sob condições, NÃO autoriza usar arquivos no bot live, onde as fontes e direitos devem ser independentes. Nenhuma captura, download, uso de dados reais, ordem ou gasto. Esse avanço habilita montagem cronológica futura de dados legalmente obtidos, não constitui backtest financeiro J3 ou gate J1 liberado. Gates continuam `dataset_rights_authorized=false`, `canonical_ohlcv_approved=false`, `financial_backtest_approved=false`, `live_trading_authorized=false`. Issue #239 exige CI no SHA exato e merge não produtivo.


## J3/PRE16 #293 — replay sintético de mark e preço negociado

`crypto_intelligence_agent/synthetic_mark_replay.py` é camada pura, independente de venue e SQLite; recebe `SyntheticMarkReplayPlan`, caminho `SyntheticMarkTick` e eventos `SyntheticFundingEvent` tipados com UTC-ms. Reutiliza PRE15 `SyntheticMarginBasis`, PRE2 `evaluate_synthetic_costs` e validadores de preço. A cada tick: custo de entrada e funding ocorrido -> equity e manutenção por MARK -> condição de manutenção (precedência) -> gatilho STOP/TARGET no TRADE -> custo de saída PRE2 somente em ramo condicional. Não consome OHLC para reconstruir caminho e não reconcilia fills. Não é cliente de exchange, carteira, executor ou backtest homologado. Sem network, DDL, implantação ou integração de ordens.


## J3/PRE17 #295 — observatório temporal de risco de portfólio fictício

`synthetic_portfolio_risk.py` agrega 2..16 trilhas sintéticas com horário de entrada, moeda quote e relógio UTC idênticos. Cada trilha usa `replay_synthetic_mark_path` PRE16, que detém cálculo local de funding, equity e manutenção. A camada de portfólio apenas recorta observações até o primeiro instante terminal e descreve notional bruto/assinado, equity e manutenção de buckets isolados, concentração por símbolo e marks adversos sincronizados. Não há snapshots de ativos reais, preço/ordem compartilhados, netting de margem, posição consolidada, liquidação de corretora ou correlação estimada. Segurança, feed J1 e J3 financeira permanecem bloqueados.


## J1/HIST #297 — captura de arquivo oficial para pesquisa isolada

O caminho `scripts/capture_private_vision_months.py` é uma camada owner-only para adquirir arquivos históricos em dois meses contíguos usando domínio fixo Binance Vision; reutiliza `vision_checksum_sidecar.py`, `offline_vision_month.py` e `offline_vision_series.py` e gera diretório local privado 0700/0600 + manifesto para `audit_offline_vision_series.py`. Não conecta `ClosedCandle`, storage canônico, J2/J3 ou motor de ordens; não há daemon, cron, chave, banco produtivo, host alternativo ou coleta em CI. Separação por construção: histórico de pesquisa não produtivo nunca é feed de trading. A licença do dataset limita finalidade, não é substituída pela licença MIT do código.


## J1/HIST #301 — retenção de histórico Vision em estágio privado

O capturador recebe bytes fixos do host Vision somente após quatro opt-ins; primeiro os valida em memória com ZIP SHA-256 + parser estrito (com possível cabeçalho conhecido), depois grava estágio 0700 e arquivos 0600, roda `audit_private_vision_archives` nos bytes relidos, sincroniza e publica o diretório pronto via `renameat2(RENAME_NOREPLACE)` Linux. O manifesto é marcador de conteúdo completo dentro do estágio, não um sinal live. Não sobrescreve diretórios nem envia bytes a GitHub, e permanece separado dos feeds canônicos/ordens.


## J1/PIT1 #306 — observatório multiativo privado (somente pesquisa)

`vision_multiasset_research.py` recebe grupos de meses `OfflineVisionMonth` já conferidos, reexecuta a validação temporal/financeira `assemble_offline_vision_months` e calcula um ranking descritivo de volume quote USDT de 24 horas **fechadas antes** de um timestamp UTC de decisão. É função pura, em memória, sem API/executor. `scripts/audit_private_vision_multiasset.py` é a porta separada de leitura owner-only de 1..50 diretórios existentes na VPS, reusando `audit_private_vision_archives` com CHECKSUMs obrigatórios e `_read_private_file` (O_NOFOLLOW, fstat, 0600). Confere janelas e duplicidade, mas não carrega preços para stdout nem gera sinais. Ambos os contratos mantêm tipos de pesquisa não canônicos; não convertem USDT/USD, não certificam listagem na época, fonte ou direitos live. Não criar rede, cron, migrations, posição ou sistema paralelo de OHLC.


## J1/EXIT #308 — fluxo vertical de dados de pesquisa Bybit

`bybit_paginated_universe_research.scan_bybit_linear_instruments_offline` extrai todos os instrumentos de uma cadeia de cursores completa, aplica contrato perp Trading/USDT e identidade cripto local datada, e retorna o conjunto **revisado**, não toda a exchange. `bybit_pit_research.select_bybit_reviewed_sample_pit` exige 24h de `stage_bybit_linear_kline` estritamente fechadas para cada candidato com pelo menos 24h de listagem. Desempate lexical, Decimal preciso e UTC/observação temporal; rank apenas da amostra. `SQLiteBybitResearchStore.commit_pit_research_snapshot` grava claim imutável na tabela separada `bybit_research_pit_snapshots` dentro do SQLite de pesquisa; `replay_pit_research_snapshot` valida SHA+conteúdo sem redes. O armazenamento histórico de 30d usa os métodos existentes `commit_raw_pair`, `quality_report` e `inspect_existing_bybit_research_series`: páginas no máximo 72 candles, 10 páginas por ativo para 720h. Nenhuma escrita nas tabelas canônicas, entradas J2, ordens ou serviços produtivos. A nova tabela é aditiva em arquivo de **pesquisa somente**, retrocompatível com arquivos de 3 tabelas antigos; arquivos de pesquisa novos contêm 4 tabelas.


### J1/EXIT #308 — fechamento da ligação entre módulos (sem rede)

`bybit_research_cycle.stage_offline_bybit_research_cycle` aceita bytes JSON por símbolo e página **já disponíveis localmente**, preflights todo o universo, exige intervalos contíguos de 1..72h até 720h por símbolo e unidades USDT, usa diretamente `SQLiteBybitResearchStore.commit_raw_pair` com replay/idempotência, executa `quality_report` independente e somente depois salva o snapshot PIT. Erro em qualquer página impede o resultado de ciclo completo. As páginas previamente validadas podem permanecer em SQLite após erro de gravação intermediária; não alegar atomicidade entre todos os símbolos. `append_offline_bybit_hourly_update` permite 1 candle fechado após 720h com o **mesmo conjunto de símbolos**, audita a série inteira (721h) e grava PIT da segunda hora. Se mudar composição do universo, precisa primeiro backfill/revisão dos entrantes, jamais reusar o histórico de outro ativo. `LocalBybitCaptureManifest` agora aceita de 1 a 72h, mantendo todos os demais gates de tempo/volume; o antigo mínimo de 3h impedia atualização a cada hora. Ambos recebem transporte já capturado, **não executam GET** ou usam credenciais.


## D177 — desbloqueio de pesquisa independente do gate de trading real (30/10/2026)

**Decisão fechada:** Bybit continua candidata preferencial para feed prospectivo, usando WS/REST/cache local, sem considerar `10006` resolvido. Binance Vision previamente retido pelo titular fica restrito à pesquisa pessoal offline não produtiva, sem alimentação de sinais/live. J1 #319/#217 permanecem gates operacionais de dados/identidade/direitos. A execução automática permanece objetivo final (D77), mas nenhuma ordem live, testnet, deploy ou credencial foi ativada. J2/J3 podem pesquisar offline sem esperar homologação integral do Top50 de produção. Não exigir novo `prossiga` para tarefas seguras em sessão.

A biblioteca `vision_dynamic_replay.py` reutiliza candles já auditados por `offline_vision_month` e `offline_vision_series`, e gera replay determinístico de decisões com volume de cotação USDT em 24h FECHADAS para uma amostra de até 50 contratos, por prefixos, em até 720 decisões. Flags de Top50 de mercado, origem autenticada, direitos live, backtest financeiro aprovado e ordens continuam negativas. Testes de alinhamento, relógio, duplicata, determinismo, não-lookahead e recursos. **Não é autenticação de fonte ou universo histórico global.**


## J2/J3 #357 — avaliação causal mensal de hipótese líquida, somente pesquisa (30/10/2026)

`vision_costed_oos.costed_vision_monthly_oos` reutiliza séries de meses Vision previamente inspecionadas, alinha múltiplos ativos e ranqueia pela soma das últimas 24h de volume cotado fechado. Regra fixa de tendência/contratendência é selecionada exclusivamente no histórico anterior, com alternativa de permanecer em caixa se não houver valor líquido hipotético positivo; o mês atual nunca treina sua própria escolha. Entrada hipotética no open do candle seguinte, saída no close, taxa/slippage hipotética agregada em bps por lado, benchmark buy-long e drawdown proxy. Não incorpora mark, funding, intrabar, slippage reais, liquidação, alavancagem, fills executáveis, custos de portfólio nem valida edge; `financial_backtest_approved=false` sempre. Não encaminhar a sinal real, ordens ou conta. Amostra restrita ao dataset local; sem autenticação de fonte, direitos de live ou Top50 de mercado. Sem downloads, storage, deploy ou novos gastos.


## J3/STRESS1 #359 — limites intrabar OHLC condicionais (30/10/2026)

`vision_intrabar_stress.py` introduz estresse matemático estritamente offline para uma barra Vision, com margem sintética, alavancagem fixa por avaliação, stop, target, limiar de liquidação proxy por equity e manutenção hipotética, funding assinado e custos Decimal por lado. Como OHLC não informa a ordem dos eventos, retorna **dois limites condicionais**: downside (liquidação/stop antes de target) e upside (target antes de stop), marcando ambiguidade e toques simultâneos. A marcação e a fórmula de liquidação reais da corretora NÃO são inferidas. Não há integração com execução nem estimativa de perda garantida. `financial_backtest_approved=false`, nenhuma ordem, rede, licença, dado canônico ou homologação Top50. Testes de 50x/1x, long/short, ambiguidade, taxa, funding e corrupção. A integração com seleção OOS mensal e CLI é **pendência da issue #359**, não alegar entrega completa.


## Pesquisa J3/ROBUST1 — isolamento dos cenários adversos

Novo adaptador puro `vision_risk_sensitivity.py` consome a pesquisa mensal `vision_stress_oos` e `VisionStressAssumptions` existentes. Não cria downloader, banco de dados, motor de ordens, provider real de mark/funding ou outra seleção. Reutiliza o mesmo histórico privativo auditado e os mesmos folds por mês; emite agregados e SHA, fail-closed se um cenário de custos melhora o envelope ou muda as exposições. A CLI só acessa o modo com opt-in explícito. Conservar `source_authenticated=false` e `financial_backtest_approved=false` invariantes. Detalhes em `docs/J3_ROBUST1.md`.


## J3/PRE17 — contrato isolado de faixas PIT para manutenção

O módulo puro `synthetic_risk_tiers.py` contém tipos imutáveis de faixa e snapshot, validações de continuidade e cálculo de manutenção por nocional mark. `synthetic_mark_replay.py` aceita snapshots opcionais e limite explícito de intervalo entre ticks, sem I/O e sem feed do provedor. Eventos de funding e ordem de gatilhos permanecem no replay atual. Não há alteração no ledger ou execução de ordens; ver `docs/J3_PRE17_PIT_RISK_TIERS.md`.


## J3/PRE18 — calendário sintético separado da aritmética de funding

`synthetic_funding_calendar.py` contém somente grade temporal tipada e checagem de cobertura; não calcula taxas, não obtém calendário da exchange nem persiste. `synthetic_mark_replay.py` exige a grade apenas quando `funding_calendar` é informado. Dedução e sinais LONG/SHORT permanecem na calculadora `synthetic_cost_scenarios.py`, sem duplicação de motor ou acoplamento à J1. Contrato completo em `docs/J3_PRE18_FUNDING_CALENDAR.md`.


## J3/PRE19 — agregação isolada de carteira sintética

`synthetic_portfolio_replay.py` recebe legs imutáveis com um relógio UTC comum e reutiliza `replay_synthetic_mark_path` (incluindo tiers PIT e calendário opcional de funding). Não duplica motor de custo ou execução. Expõe equity, drawdown prefixo, exposição assinada/bruta, concentração e correlação descritiva de retornos mark; global PnL fica nulo após qualquer liquidação proxy sem saída verificável. Sem armazenamento, troca de moeda, cross-margin ou dados live. Ver `docs/J3_PRE19_PORTFOLIO_REPLAY.md`.


## J3/PRE20 — guardrail de risco global, somente avaliação offline

`synthetic_portfolio_risk_limits.py` é avaliador read-only sobre `synthetic_portfolio_replay.py`, sem duplicar custos, marcação, funding ou execução. `SyntheticPortfolioRiskLimits` recebe parâmetros tipados exact-Decimal; `SyntheticPortfolioCheckpoint.max_open_notional_quote` usa o maior nocional mark das legs abertas (nulo após liquidação proxy sem fill). A auditoria aplica limites de margem de entrada, bruto/net de exposição, concentração e drawdown causal com trava após incerteza. Não modifica ledger, posição, ordem, dados ou deploy. Contrato `docs/J3_PRE20_PORTFOLIO_RISK_LIMITS.md`.


## J1/EXIT2 — seleção compartilhada 52→50 e histórico 720h em DB novo privado

`observe_reviewed_closed_24h_rank` é helper interno extraído do owner probe: pré e pós censo V5 íntegros, 24 velas fechadas por elegível revisado, orçamento de 6 minutos e seleção causal. `capture_private_bybit_j1._observe_large` reaproveita o objeto tipado `BybitReviewedClosedRanking` para construir `BybitPITResearchSelection` (até 50) sem ticker rolling, evitando a antiga janela impossível de 120s para 52 ativos. O restante do capturador reutiliza `LocalBybitCaptureManifest`, o parser de kline 720h e `SQLiteBybitResearchStore` com replay e controle 0600, sem segundo storage. A coleta do modo 52 só aceita uma página exata de 720h por ativo e um **novo** banco, preservando integralmente a base privada antiga com 2 símbolos. Sem migração/deploy. Issue #377.


## J1/EXIT4 — membros dinâmicos sem rebaixar 720h

`_append_dynamic_research_hour` mantém cursores de fechamento por símbolo durante um único owner-run de 3 PIT; `cursors.get(symbol,start)` distingue entrantes inéditos, retornantes e ativos contínuos. Cada par de páginas V5 tem metadados próprios, janela exata UTC e preflight de schema. `SQLiteBybitResearchStore.commit_raw_pair` continua idempotente e exige continuidade contígua; o PIT só é gravado após garantir todos os históricos ativos. Ex-membros permanecem no SQLite. O auditor `audit_private_bybit_j1_progress` verifica até 52 símbolos armazenados para SHA do registro expandido, união dos membros PIT igual aos persistidos, 720h de base e cobertura até a decisão em cada PIT. Não transforma este ledger privado no motor de ordens nem altera schema.


## J4/RUNNER1 — observação conservadora do runner PAPER

`paper_runner_trailing.py` depende de `PaperPositionBalance` de AUTO4 e eventos de preços mark tipados, sem acoplamento a REST/WS, banco de mercado J1 ou adaptadores de ordens. O monitor é funcional, limita 256 ticks por janela, valida cronologia/staleness e emite estado/digest sanitizado. Nenhuma transação, endpoint, persistência do stop ou ordens. Não confundir gatilho do replay com instalação de stop nativo. Issue #383, docs/J4_RUNNER1_PAPER_TRAILING.md.


## J5/PRE14 — status do runner na leitura RO mobile

`scripts.inspect_paper_positions.multi_paper_snapshot` acrescenta status por posição usando o `PaperPositionBalance` já lido via `mode=ro` e replay validado, sem novos acessos ao SQLite. O renderizador HTML compartilha o cartão com a tela de recuperação e fornece label controlada em PT-BR e coluna na tabela; não injeta marcação/fills/stop. O esquema JSON v1 recebe campos aditivos sem mudar contratos anteriores e mantém flags live falsas. `tests/test_paper_runner_mobile.py` e Chrome/PAPER testam resultado sem rede.


## J4/RUNNER2 — persistência isolada do replay de trailing PAPER

`crypto_intelligence_agent/paper_runner_journal.py` adiciona somente arquivo SQLite de pesquisa novo e separado. `start_paper_runner_journal` fixa fingerprint do saldo, evento/versão e política de `PaperPositionBalance` lida RO e grava o primeiro mark. `append_paper_runner_mark` faz transação de um agregado, replay completo antes de persistir, trata duplicação exata e recusa status hipotético já disparado. `load_paper_runner_journal` usa URI mode=ro e `query_only`, confere schema/metadados/hash, reabre posição RO e executa RUNNER1. Não depende de envio nem reconciliação exchange; cruzamento entre arquivos é observacional, não atômico.


### RUNNER3 — encerramento de posição residual exclusivamente sintética
AUTO4 preserva o ledger existente e usa `tranche_step=0` para a parcela residual de um plano completamente reconciliado, com `runner_filled_units`, `runner_reserved_unfilled_units` e `runner_unallocated_units` distintos das tranches de 1..n. `paper_runner_close_preview` é um componente funcional que consulta RUNNER2 e AUTO4 em leitura RO, exigindo gatilho hipotético e checkpoint estável, sem inserir reservas. Uma reserva posterior é explicitamente PAPER e verificada sob lock do AUTO4. A vinculação de journals distintos não fornece atomicidade cruzada. Sem stop exchange, executor live ou migração; ver `docs/J4_RUNNER3_RESIDUAL_PAPER_CLOSE.md`.


### J5/PRE16 — leitura de status do residual de posições PAPER
A interface `scripts.inspect_paper_positions` consome somente `PaperPositionBalance` já validado por SQLite AUTO4 RO. O novo passo zero do runner define estados PENDING/UNKNOWN, cancelado, parcialmente preenchido e encerrado a partir do ledger; nunca tenta deduzir stop nativo ou proteção financeira por flags do RUNNER2. Campos aditivos em `paper_positions_snapshot_v1` são quantidades por instrumento, sem consolidação/FX. Ver `docs/J5_PRE16_RUNNER_EXIT_MOBILE.md`.


### J6/PRE4 — primeira orquestração PAPER do fechamento residual
`step_durable_paper_runner_close` coordena, sob opt-in da chamada local, um preview RUNNER2 read-only e uma reserva AUTO4 `tranche_step=0` no mesmo SQLite de posições, mantendo a idempotência de intent ID e `BEGIN IMMEDIATE` já existentes. Em restart, um estado runner pré-existente em AUTO4 substitui a leitura do diário de marks anterior. Não usa transportes, FILL sintético adicional, stop native ou testnet. Não existe transação atômica cruzada entre journals. Ver `docs/J6_PRE4_PAPER_RUNNER_CLOSE_STEP.md`.


### J6/PRE5 — laboratório local executável do ciclo runner
O CLI `scripts.demo_paper_runner_close_flow` usa os módulos de produção já auditados de AUTO4, RUNNER2, J6/PRE4 e leitura J5 dentro de um diretório temporário. O cenário injeta eventos FILL **somente de fixture**, demonstra restart e idempotência sem gateway externo, e remove arquivos após terminar. O JSON público tem apenas estágios e flags negativas para live/ordens. Contrato `docs/J6_PRE5_PAPER_RUNNER_E2E_DEMO.md`.

### J6/PRE6 — observador de incidentes PAPER
`paper_runner_incident_audit.py` compõe apenas inspeção AUTO4 e, por opt-in completo, replay RUNNER2 para uma posição escolhida. Ele devolve um DTO JSON sanitizado e determinístico; não abre writer, não cria banco, não agrega posições nem faz acesso externo. Após qualquer reserva RUNNER3, a fonte para pendência é AUTO4 e o fingerprint RUNNER2 anterior é tratado como checkpoint superado, nunca rearmado. Os SQLite independentes permanecem sem atomicidade distribuída; falha de leitura, schema, hash ou evidência bloqueia o relatório operacional.

### J6/PRE7 — laboratório de evidência finita
`paper_incident_matrix.py` orquestra fixtures descartáveis pelas APIs AUTO4/RUNNER2/PRE4 e obtém a classificação pelo PRE6. O DTO da matriz não contém identificadores do journal e distingue `PASS`, `BLOCKED_EXPECTED` e `FAIL`; a concorrência trata preview stale como perdedor seguro, exigindo uma reserva única no agregado AUTO4. É prova de contrato local, não monitor contínuo ou reconciliador distribuído.
