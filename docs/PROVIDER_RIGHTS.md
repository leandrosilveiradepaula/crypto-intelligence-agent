# Governança de direitos de dados de mercado — J1/WU17

## Descoberta documental verificada em 25/10/2026

A Kraken informa em seu guia oficial de APIs que **determinados usos requerem permissão prévia**, incluindo usos **comerciais não pessoais** de dados obtidos em endpoints publicamente acessíveis. O guia abrange REST e WebSocket, Spot e Futures.

- Fonte primária, seção **Notices**: https://docs-legacy.kraken.com/api/docs/guides/global-intro/#notices
- Introdução Derivatives (acessibilidade pública, sem key): https://support.kraken.com/articles/360022635512-introduction-derivatives
- Contato **indicado pela própria Kraken** para solicitar permissão de uso dos dados: `marketdata@kraken.com`.
- O fato de a API responder HTTP200 sem credenciais **não concede** automaticamente licença comercial, direito de redistribuição ou acesso ilimitado.
- Esta análise é um gate técnico/documental, **não parecer jurídico** nem interpretação definitiva dos termos aplicáveis a um usuário, entidade ou jurisdição. Termos podem mudar; verificar versão e direitos antes de qualquer lançamento.

## Matriz de cenários e gates

| Cenário previsto | Estado da evidência | Gate |
| --- | --- | --- |
| Código aberto no GitHub, sem dumps nem chaves | Código separado de dados; nenhum dado bruto de terceiros versionado | Permitido como desenvolvimento de software, observadas licenças do próprio código |
| Pesquisa pessoal/interna, sem redistribuição | Endpoints públicos tecnicamente acessíveis; sujeitos aos termos da Kraken | Prosseguir apenas em escopo de pesquisa conforme termos aplicáveis, sem tratar acesso como licença comercial |
| Painel privado autenticado para uso próprio | Não foi confirmada licença específica; modo de uso e modalidade ainda dependem da finalidade real | Não presumir direitos de exibição ou exploração comercial; avaliar termos e região antes de release |
| Painel para terceiros, com dados ou alertas derivados da Kraken | Nenhuma autorização comercial ou redistribuição verificada | **BLOQUEADO** até revisão do uso pretendido e direitos expressos para essa modalidade |
| API pública, retransmissão de preços, venda de dados, serviço comercial ou monetizado | Guia oficial cita exigência de permissão prévia para usos comerciais não pessoais | **BLOQUEADO** sem comprovação de permissão/licença apropriada |
| Divulgação de histórico bruto em repositório público | Não há direito de redistribuição comprovado | **BLOQUEADO** |

A tabela diferencia **código público** de **dados de mercado públicos**: disponibilizar o cliente de software em repositório público não é o mesmo que republicar candles/volumes/dados da exchange. A licença de software livre não transfere direitos sobre dados fornecidos por terceiros.

## Estado específico dos fornecedores

- **Kraken Futures:** contrato de cliente somente GET no módulo `KrakenPublicReadOnlyResearch`, rede desligada por padrão; a fonte de direitos para publicação/uso comercial não foi validada. Não publicar market data em UI pública nem exportar feeds comerciais sem autorização.
- **Bybit V5 (candidato puramente OFFLINE):** documentos oficiais distinguem `volume` base coin e `turnover` quote coin para linear USDT/USDC: https://bybit-exchange.github.io/docs/v5/market/kline . Os termos da API restringem exploração comercial/revenda de dados: https://www.bybit.com/en/help-center/article/API-Terms . Até avaliação de direitos/geografia/uso e fonte real, não consultar a exchange nesta work unit, não integrar para serviço público, nem supor licença geral.
- **Binance Futures:** a primeira consulta pública foi bloqueada HTTP451 no runner (issue #19). Não contornar a restrição, nem confundir acesso físico com direitos de uso.
- **CoinGecko Demo e CoinPaprika Free:** avaliações na `docs/CRYPTO_REGISTRY.md` indicaram limites para uso comercial gratuito; não incorporar feeds/asset registry ao produto sob a premissa de direitos ilimitados.
- **Trust Wallet Assets / Uniswap Token Lists:** bibliotecas ou listas abertas não certificam identidade do ativo futuro Kraken nem direitos de redistribuição de todos os dados e imagens. Não derivar licença de um logo ou licença MIT apenas do repositório de código.

## Política operacional: antes de dados em produção

1. Confirmar com o Product Owner a **modalidade efetiva de uso** (pessoal interno, painel privado para titular, painel público para usuários ou monetização) somente quando for necessário para decidir um release/material produto. Não fazer alterações materiais de finalidade implicitamente.
2. Mapear, por provedor e conjunto de dados (instrumentos, OHLC, volume, funding, derivados), quais dados serão lidos, armazenados, mostrados, transmitidos ou exportados. Dados agregados e alertas derivados também podem ter restrições; não presumir que transformação elimine direitos.
3. Obter **evidência explícita de licença ou autorização aplicável** para uso previsto; registrar texto, data, URL/canal, titular, abrangência e prazo no GitHub em referência sanitizada (nunca credenciais, e-mails privados ou documentos confidenciais no repositório público).
4. Manter estado `commercial_or_public_distribution_authorized = false` **como declaração de produto/documentação**, não como flag ou credencial de permissão implementada. Só alterar decisão com base comprovada e gate humano de release; na ausência de evidência, bloquear disponibilização pública/comercial.
5. Nunca converter a confirmação de read-only/HTTP200 em autorização para trading; validar separadamente elegibilidade legal/regional, margens, risco, liquidação e termos.
6. Custo adicional = **R$0,00**; não contratar serviço pago, disparar e-mail em nome do titular, solicitar licença paga ou liberar produção sem autorização apropriada.
7. Continuar **em modo offline e com fixtures sintéticas** nas work units que dependem de dados cuja licença ainda é incerta. Reutilizar apenas os endpoints públicos para pesquisa privada quando permitido pelos termos aplicáveis.

## Relação com as pendências técnicas

- **J1 #2**: ainda aberta. CI verde valida software, não direitos de uso, qualidade do mercado, estratégia, backtest ou produto.
- **WU10 #32**: identidade crypto-only positiva ainda exige base verificável e licença compatível; os metadados Kraken têm categoria `xStocks` com `tradfi=false`.
- **WU12 #36**: o campo `trade candles.volume` Kraken segue com unidade financeira não demonstrada; `unit_proof=false`.
- **WU16 #46 / PR #47**: cliente GET-only integrado SHA `6d5b37aba154b0fb6a950fbffa4ba3e18d01410e`, CI pós-merge #40203821568 SUCCESS (213 testes offline + 11 docs), sem novo acesso live nem serviço em produção.
- **WU17 #48**: esta política documenta riscos de licença/redistribuição. A questão externa de autorização comercial, se aplicável, continua **não resolvida**, mesmo depois de a documentação técnica passar na CI.

Próximos passos: conservar as evidências de licenciamento e arquitetura aqui, evitar novas sondagens live não necessárias, e avançar na validação independente de fontes/identidades sem inventar direitos de uso. Antes do release, reavaliar a modalidade de produto e os termos vigentes, com gate humano aplicável.


## WU19 — Gate de finalidade em código, sempre conservador (issue #52)
O módulo puro `crypto_intelligence_agent/provider_usage_gate.py` tipa os provedores Kraken/Bybit/Binance, datasets (instrumentos, candles, tickers, funding, alertas derivados) e finalidades distintas (pesquisa interna, painel privado, exibição pública, API pública e comercial). Aceita `RightsGrantEvidence` com revisão identificada, período de vigência, URL HTTPS, versão e declaração explícita do escopo, **mas não comprova autenticidade da licença nem substitui revisão jurídica/humana**. O resultado atual permanece `allowed=false` para todas as modalidades até existir processo externo real de confirmação e release: mesmo `grant_confirmed=true` e `externally_reviewed_release_gate=true` inseridos pelo chamador não autorizam distribuição. `INTERNAL_RESEARCH` retorna estado informativo `internal_research_subject_to_current_terms_review`, não licença automática. Ausência/obsolescência/futuro/escopo incompatível são recusados, e nenhuma resposta divulga dados comerciais. Não conectar esse gate diretamente a produção/UI: o release humano precisa validar a modalidade real do produto, território, contrato de licença e fornecedor. Fixtures de testes **sintéticas**, nunca autorização.


## OKX V5 — candidato de esquema offline WU22 (issue #60)
Em 25/10/2026, a documentação de API https://app.okx.com/docs-v5/en/ mostra GET público de histórico OHLCV para SWAP e unidades volume/contratos/base/quote explicitamente distintas. Porém o **OKX API Agreement seção 9.4** em https://www.okx.com/en-us/help/okx-api-agreement limita Market Data a utilização pessoal não comercial e restringe exposição a terceiros, redistribuição e construção de produto concorrente, mesmo em endpoints sem autenticação. O escopo final/região precisará de revisão aplicável antes de qualquer GET ou release. O `provider_usage_gate.py` passa a conhecer `okx_v5` como candidato, mas continua retornando `allowed=false` para todas as finalidades, inclusive com `grant_confirmed=true` sintético. Não consultar, copiar, distribuir ou monetizar market data OKX nesta work unit. Pesquisa de software com dados sintéticos não equivale a licença de dados da exchange. A pesquisa WU22 #60/PR #61 foi integrada SHA `ee8c36d09a90192cbf5220c10ec28b876852508c` com CI #40214317197 SUCCESS; **isso não altera autorização externa/comercial = false**.


## WU23 — Vike Data/Hyperliquid: licença publicada não é prova de cadeia de direitos

A [página de licenciamento da Vike](https://vike.io/data/licensing) distingue o código da plataforma (FSL) dos dados. Declara todos os arquivos Parquet de `https://data.vike.io/archive` como **CC BY 4.0**, com possibilidade de reutilização inclusive comercial mediante atribuição. Para respostas REST/MCP, a página promete a mesma obrigação de atribuição, mas sujeita o acesso aos termos de chave e controle de uso. Esta é a **declaração do publicador**; ainda não existe comprovação jurídica independente da cadeia de direitos de dados de origem Hyperliquid/HL HIP-3, nem aceite da modalidade final de produto.

O manifesto público sem chave `https://data.vike.io/archive/hl-samples/manifest.json` foi inspecionado documentalmente em 25/10/2026: informa `generated_at=2026-10-22T12:56:48Z`, BTC de 21/10/2026, arquivos `fills-sample.parquet` (uma hora) e `positions-sample.parquet` (um instante), além de `license.name=CC BY 4.0`, esquema tipado e cobertura alegada. O manifesto **não é uma licença assinada pelo originador**, tampouco prova de conteúdo ou completude dos arquivos; nenhum Parquet foi descarregado e auditado nesta fase. As colunas incluem `wallet` e métricas financeiras `Float64`; não versionar valores por carteira, preços, dados brutos ou dumps no GitHub público.

O serviço [Vike Data API](https://vike.io/data/api) anuncia 20 mil chamadas/hora e custo zero, porém acesso REST a candles exige criação de conta e chave própria. Não criar conta, pedir chaves ou consultar REST em nome do titular sem permissão; o único endpoint novo permitido na WU23 é o **manifesto público keyless**, com coleta explícita, limitada e auditável. Também não assumir que `volume_usd` ou `Float64` sirvam automaticamente como volume decimal financeiro para backtest. Fills de compradores/vendedores podem compartilhar `trade_id`: contagem ingênua duplicaria negociação. HIP-3 pode incluir ações/índices, de modo que não constitui registro positivo crypto-only. Usos de dados em UI pública/comercial permanecem BLOQUEADOS até confirmação dos direitos, do escopo e gate humano apropriado.

O script `scripts/probe_vike_public_manifest.py` requer duas flags de pesquisa para um GET sem chave; job owner-only na issue #63 por comando exato `/probe-vike-keyless-manifest-v1`, sem repetição automática. Saída sanitizada registra somente hash SHA-256, datas, nomes de datasets e *claim* de licença; explicitamente `sample_rows_inspected=false`, `upstream_rights_independently_verified=false` e `authorized_for_public_release=false`. Isso **não** modifica a recusa de uso externo no `provider_usage_gate.py`, que não integra Vike ao feed operacional. A implementação WU23 foi integrada na PR #64 SHA `c4cb8b1e7f31c3bde917e78185aeceb0a6a6733c` (CI #40214978748 SUCCESS, 293 testes offline). O comentário owner #6400604063 foi rastreado por auditoria WU26 a run #40215045758/job #121234257255 SUCCESS; o log sanitizado confirma o GET único e validação estrutural do manifesto Vike, SHA256 `9329c928aba6fc710a981ee9f985a75006af61147ac887bd960a544a6812ce7a` (2026-10-25). Issue #63 encerrada **somente** como diligência de manifesto: nenhum Parquet, origem de licença, cobertura histórica ou direito comercial foram independentemente verificados.


## J1/WU24 — Comparação gratuita de identidade e dados (sem concessão automática)
- **Hyperliquid nativa:** https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint e https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/rate-limits-and-user-limits documentam acesso público informativo via POST /info, sem chave de negociação, com limites de peso 1.200/min por IP (info normalmente 20 + adicional por candles). O caráter aberto de consulta **não substitui autorização explícita para publicar, revender ou retransmitir dados**; a documentação de endpoint consultada não concede licença de redistribuição. Gate externo fechado; consultar termos e jurisdição antes de uso operacional.
- **Vike Hyperliquid:** declara arquivos CC BY 4.0 com atribuição https://vike.io/data/licensing, mas é alegação do publicador e não comprova a cadeia de direitos upstream. Manifesto BTC keyless limitado a fills de uma hora e snapshot de posições, não OHLCV histórico de Top50; run #40215045758 confirma manifesto keyless, mas não direitos upstream nem Top50.
- **CoinGecko Demo/free:** o artigo oficial atualizado em 19/10/2026 https://support.coingecko.com/articles/1043089972-what-are-the-differences-between-commercial-and-custom-licenses informa que o plano gratuito **não inclui licença comercial** e exibição pública comercial exige plano pago. Não usar como base licenciada de produto a R$0.
- **CoinPaprika keyless/free:** https://coinpaprika.com/api e https://coinpaprika.com/api/licensing restringem Free a uso pessoal, planos comerciais pagos e redistribuição negociada. Não tratar lista pública como registro crypto-only com direitos comerciais gratuitos.
- **Kraken/OKX/Bybit/Binance:** políticas e evidências independentes já documentadas aqui; Vike ou Hyperliquid não fecham automaticamente bloqueios #19/#32/#36/#48. O financiamento de alavancagem, a margem de manutenção e a disponibilidade na região também não decorrem do schema público.
- `provider_usage_gate.py` adiciona `hyperliquid_native` exclusivamente como escopo de pesquisa conservador. Mesmo licença sintética ou flag de revisão não cria permissão nem release. **R$0 adicional**, sem novas contas, chaves, GET/POST live ou API de ordens nesta WU.


## WU25 — Hyperliquid /info com diagnóstico mínimo owner-only
A fonte primária https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint/perpetuals permite consultar `metaAndAssetCtxs` nativo e candles por POST informativo, com limite de peso https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/rate-limits-and-user-limits (1.200/min agregado por IP; informações normais peso 20, candles acrescentam por 60 itens). Uma execução pontual por owner-only, caso comprovada, pode registrar somente conectividade e shape BTC de 3 velas fechadas; **não** outorga licença comercial, redistribuição, publicação de feed ou coleta persistente de dados. Todas as flags de direitos permanecem false. O diagnóstico não usa /exchange nem contas ou credenciais de trading, não mede risco, slippage ou margem. Em caso de HTTP403/418/451/429, encerrar sem retry e não contornar restrições. A versão do teste não valida o produto operacional; issues #2/#32/#36/#48 seguem bloqueios. Implementação WU25 PR #73 merged SHA `11e9d840f53701c1a8fb2bb38c5dae61098c0905` com CI #40218027418 SUCCESS (361 testes offline). Comentário proprietário #6401021095 registrado na issue #72; sem ID/log verificável da execução de issue_comment, **nenhuma conclusão live ou licença foi atestada**; não repetir automaticamente a sondagem.


## Resultado comprovado do diagnóstico Hyperliquid — 2026-10-25
O run `40218132668`/job `121243633007` fez exatamente UM POST read-only em `/info` e registrou `status=invalid_provider_schema` após hash SHA256 da resposta de metadata `00e4595b1ba9e0dc718ee0f2ad38e6719a488588a1b100056dd97e56bb77e2c7`. O segundo POST de candles não ocorreu. Isso NÃO prova indisponibilidade de API, unidades financeiras, ausência de direito ou falsidade do schema oficial; a validação local pode ser mais estrita que o universo real. O corpo bruto foi descartado intencionalmente. Sem novo probe autorizado e sem corrigir falhas às cegas, manter WU25 issue #72 aberta, gate de direitos externo e critérios de homologação desativados.
