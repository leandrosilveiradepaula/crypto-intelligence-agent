# Crypto Intelligence Agent

Plataforma em desenvolvimento de inteligência quantitativa para futuros perpétuos de criptomoedas: identificação de oportunidades, pesquisa estatística e futuras saídas parciais de vencedores. **Sem execução automática real e sem promessa de lucro.**

## Situação
- J0 documental concluída.
- J1 Dados em andamento: WU1 (#12), WU2 (#14), WU3 (#16) e WU4 (#18) integradas; parte offline da WU5 (#20) integrada. [Issue #19](https://github.com/leandrosilveiradepaula/crypto-intelligence-agent/issues/19) continua aberta aguardando evidência real de API pública.
- CI pós-WU5: **78 testes Python offline**, compilação e dez documentos aprovados. Não equivale a feed live homologado.

## Documentação
[Regras para agentes](AGENTS.md) · [Produto](docs/PRODUCT_SPEC.md) · [Arquitetura](docs/ARCHITECTURE.md) · [Decisões](docs/DECISIONS.md) · [Contrato de dados](docs/DATA_CONTRACT.md) · [Estratégias](docs/STRATEGY_SPEC.md) · [Validação](docs/VALIDATION_PLAN.md) · [Jornadas](docs/JOURNEYS.md) · [Status](docs/STATUS.md) · [Estado operacional](docs/OPERATIONAL_STATE.md)

## Demonstração offline — fixtures sintéticas, nenhuma rede
```bash
python -m crypto_intelligence_agent
python -m crypto_intelligence_agent --max-symbols 2 --interval 1h --candles 3
python -m crypto_intelligence_agent --database /tmp/crypto-market-demo.sqlite3 --symbols BTCUSDT
```

O banco SQLite é temporário por padrão; `--database` cria armazenamento local explicitamente indicado. O JSON registra fontes, timestamps, endereços de endpoints, resultados, status de coleta e cobertura. **Os dados offline são sintéticos e não servem para medir rentabilidade.**

O modo live é estritamente read-only e precisa das duas opções `--mode live --allow-public-network`. Uma verificação limitada, quando houver executor autorizado com rede, usa `--max-symbols 1 --candles 3`. HTTP 403/418 não é retentado automaticamente, HTTP 429 respeita espera limitada, e desvio de relógio excessivo bloqueia a captura. Nenhuma consulta live foi comprovada nesta etapa.

## Testes de engenharia
```bash
python -m unittest discover -s tests -v
python scripts/check_docs.py
python -m compileall -q crypto_intelligence_agent tests
```

CI roda somente testes offline com fixtures e sem chaves. O volume atual de 24h não é fonte de universo histórico retrospectivo. SQLite é backend local de referência, não decisão de banco de produção.

**Custo adicional autorizado: R$0.** Repositório público: nunca versionar segredos, chaves, credenciais, dados pessoais ou bancos capturados.

## Verificação read-only via GitHub sob comando do proprietário

A validação **live** não é executada em CI automática. O workflow `.github/workflows/public-feed-smoke.yml` aceita apenas um comando explícito `/run-readonly-smoke-v1` publicado pelo dono do repositório na [issue #19](https://github.com/leandrosilveiradepaula/crypto-intelligence-agent/issues/19). É restrito a 1 símbolo, 3 candles, GET público e três minutos num runner padrão de repositório público; sem secrets, ordens, gastos adicionais, deploy ou agendamento. O job gera logs sanitizados, mas um sucesso pontual não substitui a homologação completa da J1.

## Smoke real de GET público — restrição observada

O [run 40197499250](https://github.com/leandrosilveiradepaula/crypto-intelligence-agent/actions/runs/40197499250) foi acionado explicitamente na issue #19 em 25/10/2026 e recebeu HTTP **451** na primeira consulta ao serviço público USD-M da Binance. **Zero candles reais coletados.** Não repetir nem contornar a restrição. A causa geográfica/legal específica não foi comprovada, e a J1 continua aguardando uma fonte pública independente e verificável. Testes offline verdes não mudam esse status.

## Pesquisa de fonte independente

A [issue #23](https://github.com/leandrosilveiradepaula/crypto-intelligence-agent/issues/23) investiga a API pública de instrumentos da Kraken Futures, que é **outro fornecedor**, não um proxy para a Binance. O teste de viabilidade usa uma única requisição GET e retorna apenas um resumo sanitizado:
`python3 scripts/probe_public_kraken.py --allow-public-network`. Sem essa flag, o script não acessa a rede. Resultado positivo de conectividade ainda não prova elegibilidade dos contratos, qualidade ou continuidade de histórico.


## Kraken Futures: resultado de pesquisa independente
- [WU6 #23](https://github.com/leandrosilveiradepaula/crypto-intelligence-agent/issues/23) concluída: [run 40198042787](https://github.com/leandrosilveiradepaula/crypto-intelligence-agent/actions/runs/40198042787) HTTP200, 231 instrumentos, 213 candidatos heurísticos PI_/PF_. A lista inclui ativo tokenizado (`PF_AAPLXUSD`): não é um universo validado de perpétuos de criptomoedas.
- [WU7 #25](https://github.com/leandrosilveiradepaula/crypto-intelligence-agent/issues/25) valida schema real de instrumentos, ticker e candles BTC sob até três GETs públicos fixos, sem contas, credenciais ou trades. Probe offline por padrão: `python3 -m scripts.probe_kraken_market_schema` **recusa rede**; flags duplas necessárias para o smoke owner-only. Sem troca automática de provedor.

## WU8 — Segurança na seleção do universo
Um GET real de Kraken mostrou que BTC e ações tokenizadas podem compartilhar `type=flexible_futures`. A [issue #28](https://github.com/leandrosilveiradepaula/crypto-intelligence-agent/issues/28) investiga `category`, `tradfi` e `tags` usando `python3 scripts/probe_public_kraken.py --allow-public-network --inspect-taxonomy` (exige autorização explícita e usa apenas GET público). O resultado será um resumo sanitizado, não universo de negociação nem prova de retorno. O teste inicial de três endpoints (run 40198745112) passou com HTTP200.


## Triagem conservadora de instrumentos Kraken (WU9)
A taxonomia real da [WU8](https://github.com/leandrosilveiradepaula/crypto-intelligence-agent/issues/28), run [40199111677](https://github.com/leandrosilveiradepaula/crypto-intelligence-agent/actions/runs/40199111677), provou que xStocks podem ter `tradfi=false`. O módulo de pesquisa `crypto_intelligence_agent/kraken_eligibility.py` só ranqueia contratos Kraken quando recebe um **registro externo/versionado de bases cripto verificadas**, além de critérios ativos de quote USD, ticker perpetual e volumeQuote Decimal. Sem tal registro, falha em vez de incluir instrumentos não cripto; ainda não integra sinais ou operações, nem comprova Top50.

## Estado da triagem Kraken (WU9/WU10)
A [PR #31](https://github.com/leandrosilveiradepaula/crypto-intelligence-agent/pull/31) integrou seletor puro que evita incluir ações tokenizadas por prefixo/flag, exigindo um **registro externo e versionado de bases criptográficas verificadas**. CI pós-merge: 115 testes offline. A [issue #32](https://github.com/leandrosilveiradepaula/crypto-intelligence-agent/issues/32) trata de estabelecer esse registro com evidência ponto-no-tempo. Ainda não foi gerado um Top50 real, não houve alteração de fornecedor principal nem operação financeira.


## Registro cripto com histórico verificável — WU10
O módulo `crypto_intelligence_agent/crypto_asset_registry.py` valida manifestos **internos de pesquisa** (SHA256, revisão identificada, duas fontes independentes, tempos UTC), rejeita revisões posteriores à observação e inclui a versão integral do registro no `UniverseSnapshot`. A [issue #32](https://github.com/leandrosilveiradepaula/crypto-intelligence-agent/issues/32) rastreia a WU10. O esquema, direitos de uso e riscos ficam em [docs/CRYPTO_REGISTRY.md](docs/CRYPTO_REGISTRY.md). Não há lista real homologada de moedas nem integração comercial com APIs pagas; todos os testes usam fixtures sintéticas e não enviam ordens.


## Kraken: candles de pesquisa e limite de volume
A [issue #34](https://github.com/leandrosilveiradepaula/crypto-intelligence-agent/issues/34) valida OHLC temporalmente fechado com preços Decimal e timestamps UTC no parser `crypto_intelligence_agent/kraken_candle_validation.py`. A coluna `volume` da API é armazenada somente como **`raw_trade_volume_unverified`** em memória; sem unidades verificadas, ela **não** se torna `base_volume`/`quote_volume` nem alimenta o backtest. Referência: https://docs.kraken.com/api/docs/futures-api/charts/candles. Nenhum GET extra, chaves, ordens reais ou deploy.


## Pesquisa da unidade de volume Kraken (WU12)
A [issue #36](https://github.com/leandrosilveiradepaula/crypto-intelligence-agent/issues/36) propõe um diagnóstico opcional de **dois GETs públicos** de BTC, sem credenciais nem ordens. Exige flags `--allow-public-network --allow-volume-diagnostic`, publica apenas soma de 24 candles UTC totalmente fechados e volume reportado pelo ticker 24h. O próprio relatório define `unit_proof=false`: semântica da unidade e janelas de 24h não são automaticamente comparáveis, portanto nenhum dado é convertido a `ClosedCandle` por essa pesquisa. CI segue offline e R$0.


O primeiro run real da WU12, [40201172859](https://github.com/leandrosilveiradepaula/crypto-intelligence-agent/actions/runs/40201172859), recebeu HTTP200 no chart, mas rejeitou a estrutura ou quantidade de candles e não consultou o ticker. Nenhum volume foi homologado. A correção da issue #36 introduz apenas diagnóstico sanitizado de tipos/contagens e não relaxa as exigências do feed.


## Compatibilidade real do volume Kraken (WU13)
O run [40201488833](https://github.com/leandrosilveiradepaula/crypto-intelligence-agent/actions/runs/40201488833) provou que 27 candles retornaram `volume` como **string decimal**, divergindo do tipo int64 descrito em documentação. A [issue #39](https://github.com/leandrosilveiradepaula/crypto-intelligence-agent/issues/39) normaliza esse número como `Decimal` bruto, sem afirmar unidade financeira, sem criar `ClosedCandle` ou converter para volume cotado. Os testes offline continuam sendo o gate obrigatório.


## WU13 concluída — volume Kraken preservado sem inferência
A [PR #40](https://github.com/leandrosilveiradepaula/crypto-intelligence-agent/pull/40) corrigiu o formato decimal-string observado dos candles Kraken. O [run #40201868577](https://github.com/leandrosilveiradepaula/crypto-intelligence-agent/actions/runs/40201868577) confirmou 2 GET HTTP200 e 24 candles fechados com `volume` bruto acumulado; ainda `unit_proof=false`. O número de volume bruto do chart **não** é volume financeiro comparável sem conhecer unidade/multiplicadores e sem alinhar janelas. A [issue #36](https://github.com/leandrosilveiradepaula/crypto-intelligence-agent/issues/36) continua aberta; nenhuma negociação real foi executada.


## Gate conservador de alavancagem por instrumento (WU14)
A [issue #42](https://github.com/leandrosilveiradepaula/crypto-intelligence-agent/issues/42) rastreia um módulo **somente de pesquisa** que compara a alavancagem global solicitada (50x padrão) a uma tabela externa/versionada de limites Kraken conforme exposição agregada em USD. Se o contrato/tier permitir apenas 10x, 50x é **recusado**, não reduzido silenciosamente. Fixtures são sintéticas: não equivalem à margem real, liquidação ou permissão de operar. A fonte documental é a [tabela oficial de níveis e alavancagem](https://support.kraken.com/br/articles/360022632452-derivatives-margin-schedule-maximum-leverage). Sem ordens ou custo extra.


## Precisão dos números JSON de mercado (WU15)
A [issue #44](https://github.com/leandrosilveiradepaula/crypto-intelligence-agent/issues/44) previne perda silenciosa de casas decimais: `decimal_json.py` decodifica frações numéricas diretamente em `Decimal` e rejeita floats Python já arredondados nos campos financeiros usados para ranquear Kraken. Inclui testes com volumes praticamente iguais, evitando erro de ordenação. A correção mantém `unit_proof=false`, não estabelece volume de candle em base/quote nem ativa negociação.


## Cliente de pesquisa Kraken público, sem ordens (WU16)
A [issue #46](https://github.com/leandrosilveiradepaula/crypto-intelligence-agent/issues/46) agrega as peças validadas em `KrakenPublicReadOnlyResearch`: modo sem rede por padrão, opt-in explícito para GET público de instruments/tickers e candles trade, JSON financeiro Decimal exato, sanitização allowlist e janela UTC de observação. O retorno de velas é apenas `KrakenStagedCandlePage` com volume bruto **sem unidade financeira atestada**, nunca `ClosedCandle`, sinal ou operação real. CI inteiramente offline com transporte simulado.


## Direitos e licenças dos dados públicos Kraken (WU17)
O [guia oficial da Kraken](https://docs-legacy.kraken.com/api/docs/guides/global-intro/#notices) informa que usos comerciais não pessoais de dados dos endpoints públicos podem exigir autorização prévia. A [issue #48](https://github.com/leandrosilveiradepaula/crypto-intelligence-agent/issues/48) e [docs/PROVIDER_RIGHTS.md](docs/PROVIDER_RIGHTS.md) separam pesquisa/código público de redistribuição de dados e publicação comercial. O cliente Kraken continua rede-off por padrão; **nenhum direito comercial ou lançamento público foi aprovado**. Nenhuma despesa, autorização de trading ou mudança de finalidade foi inferida.


## Pesquisa de alternativa com unidades OHLCV documentadas (WU18)
A [issue #50](https://github.com/leandrosilveiradepaula/crypto-intelligence-agent/issues/50) avalia **somente em testes offline** o schema de candles lineares Bybit V5. Sua [documentação oficial](https://bybit-exchange.github.io/docs/v5/market/kline) distingue volume em moeda-base e turnover em USDT/USDC, ao contrário da ambiguidade Kraken. Este estudo NÃO conecta Bybit, não aprova licença comercial nem troca a fonte de dados atual; `docs/PROVIDER_RIGHTS.md` registra a restrição dos termos da API. Nenhum backtest financeiro, dados live, ordem ou serviço pago é habilitado.


## Gate técnico de direitos por finalidade (WU19)
A [issue #52](https://github.com/leandrosilveiradepaula/crypto-intelligence-agent/issues/52) acrescenta avaliação puramente offline de origem, finalidade e versão de alegações de licença. Um campo `grant_confirmed=true` **não** autoriza publicação/revenda de dados: todos os usos externos continuam recusados e sujeitos a verificação contratual e gate humano. O módulo não publica dados, não envia mensagens e não negocia.


## Auditoria offline de proveniência — WU21
A J1 ainda não tem registro real Top50, unidade financeira dos candles Kraken homologada nem direitos de distribuição. `python scripts/j1_readiness_report.py` mantém o snapshot conservador da WU20. Opcionalmente, `python scripts/j1_readiness_report.py --evidence-json caminho-local.json --decision-at-ms UTC_MS` analisa **apenas a sintaxe/integridade do envelope de alegações** (sem rede e sem dados privados no repositório). O hash é verificável contra os bytes do claim, não contra a autenticidade de terceiros; datas, revisão e licença afirmadas pelo chamador não são comprovação. O relatório nunca libera Top50 real, OHLCV canônico ou exposição externa. Contrato em `docs/DATA_CONTRACT.md` (WU21), testes offline em `tests/test_readiness_evidence.py`.


## Pesquisa offline de esquema OKX V5 SWAP — WU22
O módulo `crypto_intelligence_agent/okx_swap_candle_research.py` valida somente fixtures sintéticas de candles históricos de swaps lineares. Campos documentados `vol` (contratos), `volCcy` (moeda-base), `volCcyQuote` (USDT/USDC) e `confirm=1` são conservados com Decimal exato; não há conversão para USD, feed live, autorização de licença, mudança de fornecedor, armazenamento ou negociação. A API Agreement OKX 9.4 restringe usos de mercado a fins pessoais não comerciais, com direitos de redistribuição não demonstrados. Ver D40, DATA_CONTRACT e PROVIDER_RIGHTS.


## Vike/Hyperliquid — diligência de fonte gratuita, sem ativação (WU23)
A Vike declara CC BY 4.0 com atribuição para os arquivos de dados e permite manifesto público keyless de amostras BTC: `https://data.vike.io/archive/hl-samples/manifest.json`. O projeto valida **apenas os metadados publicados** (`scripts/probe_vike_public_manifest.py`) em testes offline e disponibiliza um único diagnóstico GET owner-only (issue #63, comando literal) sem conta, chave ou dados de carteiras nos logs. Não foram atestadas licença upstream, identidade crypto-only, precisão Decimal de Float64, conteúdo dos Parquets ou prontidão live. J1 permanece aberta. Mais em `docs/PROVIDER_RIGHTS.md` e `docs/VALIDATION_PLAN.md`.


## Pré-cálculo de indicadores J2 (exclusivamente offline e sintético)
`synthetic_feature_engine.py` calcula EMA(close), TR/ATR Wilder, extremos N barras anteriores, razão de volume cotado contra média anterior e retorno simples, usando `Decimal`, períodos explícitos e apenas `ClosedCandle.quality=synthetic_fixture` contíguos e fechados antes da decisão. Nenhum sinal de compra, posição, resultado de backtest, API de mercado ou ordem é produzido. A J1 permanece não homologada; ver D42 e `docs/STRATEGY_SPEC.md`.


## WU24 — Hyperliquid nativa apenas como esquema de pesquisa
O endpoint público Hyperliquid `POST /info` é informativo, distinto do `/exchange` de execução de ordens. `hyperliquid_native_research.py` valida somente fixtures de metaAndAssetCtxs e candleSnapshot, sem enviar POST, acessar contas, armazenar dados ou aprovar licença. Candles incluem contagem real **alegada** de trades, preço exato Decimal e volume `v` sem unidade financeira homologada; nenhuma conversão USD/USDC ou geração de `ClosedCandle` ocorre. O histórico nativo informado é limitado aos 5.000 candles mais recentes por intervalo. Ver D43 e `docs/DATA_CONTRACT.md`; Top50 e direitos seguem pendentes.


## WU25 — Diagnóstico pontual Hyperliquid nativa
`python3 -m scripts.probe_hyperliquid_native_info` é offline por padrão. Mesmo com flags explícitas, só pode fazer dois POSTs informativos ao endpoint público `https://api.hyperliquid.xyz/info`: metadata perp nativa BTC e três candles BTC 1h fechados. No CI comum, todas as respostas são mockadas. O comando owner-only exige comentário exato na issue #72, após merge, e nunca chama o endpoint `/exchange`, cria ordens, grava preços/candles ou transforma volume sem unidade em `ClosedCandle`. Relatórios expõem apenas contagens, hashes e status, deixando `ready_for_*` false e direitos externos não verificados. Instruções de segurança e evidências em D44 e `docs/VALIDATION_PLAN.md`.


## Auditoria pontual de runs GitHub Actions — WU26
A rotina `scripts/audit_j1_issue_comment_runs.py` permite consultar *somente* os metadados do próprio GitHub (sem mercado) para descobrir os IDs dos jobs das sondagens já acionadas nas issues #63 e #72. O workflow `.github/workflows/j1-evidence-run-audit.yml` roda excepcionalmente em uma PR do titular, branch exata `audit/j1-run-evidence`, com leitura `actions:read` e `contents:read`. Não pede permissão write ou tokens privados, não dispara novas sondagens, não lê corpos de logs brutos e não confere licenças ou qualidade live; os IDs são usados para inspeção posterior de logs. Testes desta rotina são offline, e flags de Top50/aceite permanecem false.

## WU27 — Estrutura global vs prova BTC no contexto Hyperliquid
A rotina offline de `metaAndAssetCtxs` valida a posição de BTC nos arrays, mas não exige que todos os símbolos **não-alvo** tenham a mesma forma do ticker BTC. Contextos opcionais ou inativos de outros contratos não autorizam nem desautorizam BTC. O alvo deve estar ativo e possuir contexto financeiro válido. Para futuros diagnósticos (somente com autorização de execução), a recusa pode emitir uma categoria fixa e sanitizada, sem dados brutos. A falha real do run #40218132668 não pode ser reconstruída a partir do hash e não houve novo POST. Sem liberação de Top50/dados canônicos/licença.


## J4/PRE1 — Fatias sintéticas para saídas parciais
`synthetic_partial_exits.py` calcula percentuais de realizações sobre posição inicial ou saldo restante, com piso residual configurável e conservação exata via `Decimal`. Exemplo 50%, 60% e 70% do restante deixa 6% da posição. É um **planejador matemático sem corretora**, não possui preço, PnL, ordem, fills, lote real ou trailing; não habilita sinais/live/50x. J4 #5 e J1 #2 permanecem abertas. Veja D47 em `docs/DECISIONS.md` e o plano de validação.


## J4/PRE2 — Replay in-memory de preenchimentos parciais SINTÉTICOS
`synthetic_manual_exit_replay.py` recebe o plano matemático PRE1 e eventos fictícios explícitos, em sequência UTC, para reconstruir quantitativos de saídas parciais sem precificar ordens. IDs idênticos/payload igual contam uma vez; reutilização conflitante é erro, mas IDs diferentes do mesmo fill econômico **não** são detectados sem fonte de verdade externa. Nenhum mercado, conta, persistência, taxa, trailing, PnL ou envio de ordem é integrado. J4 #5 e J1 #2 permanecem abertos; confira D48 e `docs/STRATEGY_SPEC.md`.


## J4/PRE3 — Estado imutável de posição SINTÉTICA
`synthetic_position_state.py` define uma posição de fixture, não financeira: ID `fixture_*`, LONG/SHORT, plano PRE1, margem Decimal abstrata e `leverage_at_open` capturado de uma configuração imutável de pesquisa (50x inicial, configurável apenas para **novas** posições). Eventos PRE2 são vinculados ao ID antes do replay, sem cross-position fill. Não existe exchange, moeda de margem comprovada, preço, multiplicador, lot/step de contrato, liquidação, taxas, PnL, sinal, ledger persistente ou ordem; todos os gates de uso live permanecem falsos. Veja D49 e `docs/STRATEGY_SPEC.md`.


## J4/PRE4 — Lotes hipotéticos, sem arrendondamento ou autorização de ordens
`synthetic_lot_feasibility.py` avalia aritmeticamente tranches PRE1 e fills PRE2 de posições PRE3 usando apenas limites `Decimal` **de fixture** (passo de tamanho, mínimo por saída e mínimo de saldo residual). Cada fill individual deve ser múltiplo exato e atingir seu mínimo; não basta que a soma dos fills passe no step. Duplicatas de ID verificadas pelo replay contam uma vez, mas idempotência persistente não é comprovada. Nenhuma quantização, real venue lot-size, min notional, preço, PnL, conta, ordem ou aprovação live é produzida. Veja D50 e `docs/STRATEGY_SPEC.md`.


## J1/WU28 — Fontes oficiais precisam pertencer ao MESMO produto
O auditor OFFLINE `readiness_evidence.py` diferencia documentação Kraken Futures (`PF_`, candles `/api/charts/v1/`) dos arquivos OHLCVT Spot/Kraken Pro e dos contratos Kraken Derivatives US CME/Bitnomial. Citar uma URL oficial de outro produto NÃO comprova a unidade de volume, identidade de criptoativos, lot/step ou direitos dos nossos perpétuos. A tabela PF_ da Kraken inclui Apple/AAPLx e alavancagens diversas: 50x global é configuração de pesquisa, não executabilidade. O auditor registra `source_applicability` insuficiente, mantém gates live e release falsos e não consulta sites durante os testes. Veja D51, `docs/DATA_CONTRACT.md`, `CRYPTO_REGISTRY.md` e `PROVIDER_RIGHTS.md`.


## J3/PRE1 — Toque intrabar em OHLC sintético, sem afirmar vitória
`synthetic_intrabar_barriers.py` recebe candles fechados **sintéticos** e um plano de referência LONG/SHORT com stop, target e liquidação HIPOTÉTICA opcional. Reutiliza a validação temporal J2. Reporta o primeiro candle com níveis observados, distinguindo aberturas já além do limite de toques na faixa high/low; **dois ou mais toques no mesmo candle têm ordem desconhecida**, mesmo se o fechamento favorece o alvo. Não calcula fill, execução ao limite, retorno, taxa, funding, slippage, liquidação real ou PnL e mantém flags live/backtest false. J1 #2, J2 #3 e J3 #4 continuam sem homologação; veja D52 e `docs/STRATEGY_SPEC.md`.


## J3/PRE2 — Custos assinados de cenário SINTÉTICO, não PnL
`synthetic_cost_scenarios.py` calcula custos hipotéticos de taxa e slippage adverso por perna e funding com sinal LONG/SHORT sobre notionals em unidades **abstratas** fornecidas pelo teste, sem inferir preço, mercado, moeda, leverage real ou preenchimento de ordem. Usa `Decimal` preciso, eventos fictícios com IDs `fixture_funding_*` e idempotência **somente em memória**, recusa conflito ou cronologia suspeita. O total pode ser NEGATIVO por um crédito hipotético de funding — **isso não é lucro ou resultado financeiro comprovado**. J3 #4 e J1 #2 não estão homologadas, nenhuma ordem é enviada. Veja D53 e `docs/STRATEGY_SPEC.md`.


## J1/WU29 — PF_ símbolo e base precisam representar o mesmo ativo
A seleção de pesquisa Kraken agora recusa metadados contraditórios: o numerador de `PF_<base>USD` deve ser coerente com `instrument.base`, `instrument.pair` e `ticker.pair` se presente. O alias documentado `XBT`→`BTC` é explicitamente aceito para a API Futures; outros multiplicadores/aliases não são presumidos. Isso impede a fixture `PF_AAPLXUSD/base=BTC` de usar a identidade BTC caso sua categoria xStocks esteja ausente. O cheque NÃO comprova identidade crypto-only, licença, candlestick volume unit, Top50 real, risco ou autorização de ordens; veja D54 e `docs/CRYPTO_REGISTRY.md`.


## J1/WU30 — Histórico cripto não aceita manifesto adulterado via construtor
O histórico `CryptoRegistryHistory.append` também revalida instâncias Python de `CryptoRegistrySnapshot` construídas diretamente: SHA256 do manifesto v1, evidências independentes declaradas, tipos, timestamps e `publisher_root` derivado. Uma dataclass `frozen=True` não comprova integridade; sem essa defesa, um objeto com SHA inventado poderia alimentar o seletor offline. Revalidação de bytes/forma não autentica o publicador, a identidade do ativo, a licença ou dados reais. Questões J1 #32/#36/#48 seguem abertas; veja D55 e `docs/CRYPTO_REGISTRY.md`.


J1/WU31: o seletor de pesquisa Kraken também exclui formas textuais comuns de `xStocks`, equities, forex, commodities, índices e pré-IPO, inclusive com separadores/espaços; isso apenas reforça o filtro negativo e não substitui a prova independente de crypto-only nem os direitos de dados.

## J1/WU33 — Registro de identidade inicial de BTC/ETH (pesquisa interna)
O manifesto `registries/crypto-btc-eth-20261025-v1.json` referencia duas páginas públicas independentes para cada base e limita a seleção `CryptoRegistryHistory.select_at` a BTC/ETH em coletas futuras. É o primeiro registro com referências reais em vez de fixtures de teste, revisão técnica assistida por IA e hash versionado, **não** prova de cobertura dos 50 ativos, licença, candles `ClosedCandle` ou aptidão para ordens. Não reproduz feeds de preço e não usa APIs pagas; detalhes em `docs/CRYPTO_REGISTRY.md` e D58.

## J1/WU34 — Preços históricos de pesquisa, sem inventar volume
A extensão `SQLiteKrakenPriceOnlyArchive` reaproveita o SQLite local e o adaptador público Kraken existente para guardar páginas exatas de OHLC fechado como **price-only**, com Decimal, as-of/replay/qualidade e sem base/quote volume ou checkpoint `ClosedCandle`. O script `scripts.probe_kraken_price_archive` é um diagnóstico opcional e owner-only de um GET, banco temporário e sem dados financeiros no log. Não prova Top50, elegibilidade real dos 50 ativos, permissão comercial, sinais, execução ou rentabilidade. Ver `docs/DATA_CONTRACT.md` e D59.

## J1/WU35 — UniverseSnapshot corrente com registro BTC/ETH
Para testar a seleção real sem fabricar um Top50, a sonda privada WU35 usa o registro BTC/ETH datado, obtém instrumentos e tickers Kraken em duas chamadas públicas GET, aplica o seletor fail-closed e valida roundtrip em SQLite temporário. O limite é **até 2 ativos** e a conclusão não afeta `ClosedCandle`, licenças, histórico de ranking, 50x real ou ordens. A execução ao vivo depende de acionamento owner-only; detalhes D61 e `docs/DATA_CONTRACT.md`.

## J1/WU36 — Coleta pessoal persistente, opcional e somente leitura
O fluxo `scripts.collect_private_kraken_research` reúne o seletor Kraken BTC/ETH real e três candles fechados de **preço apenas** em um SQLite local, sem ordens nem execução automática. Exige dois opt-ins e caminho absoluto em diretório privado fora do GitHub; não faz rede na CI. A estratégia e os backtests financeiros não podem usar candles sem volume canônico comprovado; a licença comercial e o Top50 continuam bloqueados. Documentação de escopo e operação futura: `docs/J1_PRIVATE_RESEARCH.md`.

## J1/WU37 — Registro real opt-in de 10 identidades
O registro v2 `registries/crypto-bases-10-20261025-v2.json` documenta BTC/ETH/SOL/XRP/ADA/DOGE/LTC/AVAX/LINK/DOT com uma fonte oficial e outra independente por ativo, SHA256/UTC point-in-time e `internal_research_only`. O seletor Kraken de pesquisa WU35 e a CLI privada persistente WU36 aceitam `--registry expanded-10` (sem alterar o default `btc-eth`), mas só escolhem ativos que realmente passarem os filtros de contrato/ticker em cada captura. Isso não fornece Top50 histórico, licença comercial, volume econômico de candles, sinais ou negociação. Ver D63 e `docs/CRYPTO_REGISTRY.md`.

## J1/WU38 — Pesquisa local de até 5 perps sem volume canônico
A CLI já existente `python3 -m scripts.collect_private_kraken_research` oferece `--max-price-symbols 1..5` (default 1) e mantém `--registry expanded-10` como opt-in. O seletor Kraken corrente define os contratos elegíveis; o coletor captura BTC primeiro mais até N-1 perps crypto por ranking USD, com 3 barras 1h price-only cada, no máximo 2+N GETs e SQLite privado fora do Git. Não inventa contratos ou `base_volume/quote_volume`, nem atribui direito comercial, Top50 histórico, PnL ou execução. Ver `docs/J1_PRIVATE_RESEARCH.md` e D64.
