# J1/WU10 — Registro auditável de identidade de criptoativos (somente pesquisa)

## Por que existe

A Kraken Futures retornou GET HTTP200 de metadados, tickers e candles (run
[40198745112](https://github.com/leandrosilveiradepaula/crypto-intelligence-agent/actions/runs/40198745112)).
Sua taxonomia mostrou `PF_AAPLXUSD` com `category=xStocks` e `tradfi=false`,
como BTC/ETH em relação ao valor `tradfi=false` (run
[40199111677](https://github.com/leandrosilveiradepaula/crypto-intelligence-agent/actions/runs/40199111677)).
Prefixo `PF_`, `type=flexible_futures`, `tradfi=false` e até um registro comunitário
de tokens NÃO provam identidade cripto legítima nem elegibilidade para futuros.

O módulo `crypto_intelligence_agent/crypto_asset_registry.py` é **offline e de
pesquisa**. Ele não inclui uma lista real "aprovada", não chama APIs, não
distribui dados de terceiros, não conecta ordens e não substitui o provedor
principal. Um hash comprova somente integridade relativa aos bytes revisados
— **não** comprova identidade, qualidade, autorização de uso ou assinatura de
um mantenedor.

## Política de aprovação (manual e documentada)

1. Registrar `base` normalizada, `canonical_id` distinto e identificável;
   revisar ambiguidade de tickers, ativos clonados, tokenização de ações e
   versões de contratos por rede. O mesmo ticker pode identificar ativos
   diferentes; o símbolo é somente um rótulo, não uma prova criptográfica.
2. Exigir **ao menos duas referências independentes**, com publicadores,
   domínios, IDs por fonte, links públicos HTTPS sem credenciais e timestamps
   genuínos em UTC-ms. Validar manualmente se ambas realmente se referem ao
   *mesmo* criptoativo, não apenas se o formato passou no teste.
3. Registrar `reviewed_by`, `reviewed_at_ms`, `observed_at_ms` de inclusão e
   `label` imutável. Revisões e referências precisam existir até a captura
   do registro. Quando um ativo perde a aprovação, publicar snapshot NOVO
   omitindo-o, nunca reescrever snapshots passados.
4. Manter revisão de direitos/licenças por fonte antes de consumir dados na
   aplicação pública. O contrato WU10 exige
   `usage_policy=internal_research_only`; uma mudança de uso exige
   decisão/avaliação própria. O código NÃO assegura direitos sobre fontes
   apenas porque contém seus URLs.
5. Capturar `sha256` do JSON canônico (**ordenar chaves, sem espaços, ASCII,
   excluindo a própria chave sha256**). O digest é verificado antes de
   aceitar o snapshot; seu histórico de revisão deve permanecer em PR/commit
   do GitHub. Dois arquivos diferentes nunca podem ter o mesmo
   `observed_at_ms` ou reutilizar `label` com nova captura.

## Esquema versão 1 — exemplo SINTÉTICO (NÃO apto a operar)

O exemplo abaixo omite propositalmente `sha256` e utiliza domínios reservados
de teste: não é um registro homologado. Usar
`registry_sha256(unsigned_manifest)` apenas depois da revisão das referências
reais, acrescentar o campo ao manifesto e invocar
`load_registry_json(...)`.

```json
{
  "schema_version": 1,
  "observed_at_ms": 1800000000000,
  "label": "reviewed-fixture-v1",
  "usage_policy": "internal_research_only",
  "assets": [{
    "base": "BTC",
    "canonical_id": "bitcoin-mainnet",
    "reviewed_by": "internal-reviewer-fixture",
    "reviewed_at_ms": 1799999990000,
    "evidence": [
      {
        "publisher": "example-project",
        "asset_ref": "btc-mainnet",
        "url": "https://project.example.org/asset/btc",
        "observed_at_ms": 1799999989000
      },
      {
        "publisher": "example-catalog",
        "asset_ref": "bitcoin",
        "url": "https://catalog.test.net/coins/bitcoin",
        "observed_at_ms": 1799999989000
      }
    ]
  }]
}
```

Toda entrada externa é conferida: versão e campos exatos, tempos inteiros,
identificadores, fontes/domínios independentes, 1–2000 ativos, limite JSON de
1 MiB, base/canonical_id únicos, hash hexadecimal completo SHA-256 e rejeição
de chaves JSON duplicadas/NaN. A validação **sintática** não substitui
due diligence de identidade e compliance.

## Histórico, replay e integração ao seletor WU9

`CryptoRegistryHistory.append` exige ordem por instante de captura e rejeita
conflitos; repetição idêntica é idempotente. `as_of(market_observed_at_ms,
max_age_ms=...)` escolhe somente um registro já existente **no instante
da amostra de mercado**, nunca o snapshot de amanhã para um backtest de ontem.
Rejeita ausência e obsolescência conforme limite informado pelo chamador. Esta proteção contra **look-ahead** não pode ser contornada pelo replay de snapshots capturados em data posterior.

`select_at(..., market_observed_at_ms=..., decision_at_ms=...,
max_market_age_ms=..., max_registry_age_ms=...)` verifica também que
`market_observed_at_ms <= decision_at_ms` e que o mercado não ficou obsoleto
na decisão. O `UniverseSnapshot.selection_rule_version` incorpora o
SHA-256 completo do registro selecionado. Os preços/tickers e seus timestamps
precisam VIR da auditoria real de coleta; o módulo não tem como comprovar
se a hora fornecida pelo chamador foi inventada.

O seletor existente `select_kraken_research_universe` continua exigindo:
ticker `tag=perpetual`, contrato PF_ linear USD, status válido, exclusões
de `xStocks/Equities/Forex/Commodities/Pre-IPO/Indices`, precificação
Decimal e volumeQuote USD contemporâneo. Ranking Top-N (até 50) só é
informativo no momento da observação. Sem uma fonte licenciada de registry
e persistência genuína de snapshots NÃO temos universo Top50 real.

## Pesquisa de fontes e direitos — 25/10/2026

- [CoinGecko API](https://support.coingecko.com/articles/1043089972-what-are-the-differences-between-commercial-and-custom-licenses):
  plano gratuito/Demo sem direitos comerciais. Planos comerciais são pagos
  e redistribuição tem direitos adicionais; **não integrar** automaticamente
  sob orçamento R$0.
- [CoinPaprika API](https://coinpaprika.com/api) e
  [Termos](https://coinpaprika.com/api-terms-of-use/):
  plano gratuito sem key para uso pessoal, **não comercial**, com atribuição;
  **não importar** como fonte comercial embutida sem licença.
- [Trust Wallet Assets](https://github.com/trustwallet/assets):
  repositório comunitário de identidade e metadados de tokens. Scripts e
  documentação declarados MIT; isso **não prova** que dados/imagens de terceiros
  sejam livres para qualquer uso nem que todo token listado seja um perpétuo
  cripto elegível. Revisar direitos específicos antes de copiar dados.
- [Uniswap Token Lists](https://github.com/Uniswap/token-lists):
  especificação MIT de metadados de tokens ERC-20, **não** uma certificação
  financeira de identidade ou lista de futuros perpétuos. Não aceitar
  presença em uma token list como prova suficiente.

**Decisão operacional:** primeiro entregar o mecanismo de validação,
integridade e antiviés temporal, com fixtures somente sintéticas. Identificar
fonte real e compatibilidade de licença é pendência explícita. Nenhuma
compra ou ativação paga está autorizada.

## Testes e gates

Executar localmente/CI, sem GET e sem segredos:
`python3 -m unittest discover -s tests -v`,
`python3 -m compileall -q crypto_intelligence_agent tests`,
`python3 scripts/check_docs.py`.

Testar hash alterado, timestamps futuros, referências conflitantes,
identidade duplicada, URL não segura, licença inadequada, chaves
duplicadas, registro revogado em snapshot posterior, replay historicamente
estável e rejeição de dados do futuro. Aprovação de código não é aprovação
de um registro concreto nem homologação de qualidade do feed.

Jornada J1 (#2), WU10 (#32). A próxima entrega é a avaliação real
e versionada de fontes de identidade e o adaptador Kraken read-only, sempre
com reutilização dos contratos e storage existentes e sem ordens reais.


## Observação de taxonomia de instrumento publicada pela Kraken (WU22)
A página regulatória https://support.mtf.kraken.com/hc/en-us/articles/25499987607837-Linear-Contract-Specifications separa seções "Perpetual Contract Specifications - Crypto" e "- xStocks", mas a seção nominal "Crypto" também apresenta identificadores como `PF_COINXUSD` (Coinbase/COINx) e `PF_METAXUSD` (Meta/METAx). Além disso, o artigo é específico de Kraken MTF, **não prova equivalência de todos os símbolos** à API de Kraken Futures pesquisada. Portanto, não converter suas listas nem prefixos em registro positivo de identidade, não importar os dados na árvore pública do projeto sem revisar direitos. Taxonomia do fornecedor é uma pista, não duas referências independentes nem prova de ativo crypto-only. Issue #32 segue aberta.


## Vike Hyperliquid — cuidado com identidades e contagem de negócios (WU23)
O catálogo [Vike Hyperliquid](https://vike.io/data/hyperliquid) oferece candles de perpétuos, incluindo HIP-3 DEXs que também podem negociar ativos tokenizados ou derivados de ações/índices. O ticker `BTC` da amostra pública não constrói um registro crypto-only positivo para o **universo dinâmico** nem identifica contratos Kraken/OKX; mapear venue, contrato, base e símbolo ponto-no-tempo continua obrigatório. O [manifesto público](https://data.vike.io/archive/hl-samples/manifest.json) informa fills por carteira: ambos os lados de um mesmo `trade_id` podem aparecer, de modo que somar `size_usd` ou `n_trades` por linha sem desduplicação potencialmente dobra o volume. O esquema registra preços/quantidades `Float64` e não atesta precisão original exata, funding, liquidação, top 50 ou continuidade histórica. Licença CC BY declarada pela Vike não autentica identidade de ativos nem direitos upstream. Issue #32 segue aberta.


## Hyperliquid native e HIP-3 (J1/WU24)
O documento oficial https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint/perpetuals descreve universo nativo (`dex=""`) e DEXes HIP-3 separados. HIP-3 pode listar ativos tokenizados e sintéticos de ações/índices; a distinção de namespace não constitui por si só identidade crypto-only de um `BTC`, `COIN` ou outro símbolo. A informação atual de `metaAndAssetCtxs` também não reconstrói adições, exclusões, liquidez e elegibilidade no passado. O candidato nativo fica fora do registro positivo até atender revisões independentes e direitos da issue #32. Não importar listas de terceiros no repositório público.


## J1/WU28 — Catálogo oficial de perp não é registro independente crypto-only
Fonte oficial de **Kraken Futures linear Multi-M perp**: https://support.kraken.com/articles/4844359082772-linear-multi-collateral-derivatives-contract-specifications, consultada em 25/10/2026. O catálogo contém `PF_AAPLXUSD` (Apple, ativo tokenizado), além de contratos cripto como `PF_1INCHUSD`. `PF_1INCHUSD` aparece como classe E (10x) e `PF_AAVEUSD` classe B (50x), indicando limitações diversas; esses valores são exemplos do documento corrente, sujeitos a instrumento, nível de risco, data e jurisdição, e NÃO são mapeados como parâmetros ativos. Isso confirma que prefixo PF_, nome de instrumento ou tabela de base da própria Kraken **não provam por si mesmos** cripto-only e jamais substituem as duas referências independentes previstas no contrato versionado `crypto_asset_registry.py`.

A mudança WU28 `readiness_evidence.py` classifica esse link, quando empregado na issue #32, como `instrument_list_includes_non_crypto_no_positive_registry_proof`; hash de claim não equivale a revisão independente nem a direitos sobre a fonte. Para uma aprovação real, comprovar identidade de cada base fora da exchange, resolver XBT/BTC e ativos tokenizados, registrar referência temporal e licença, e manter elegibilidade histórica point-in-time. **Não foi criado** um catálogo permanente de Top50 nem seleção live nesta work unit; issue #32 aberta.


## J1/WU29 — Evitar empréstimo indevido da identidade de outro ativo
A validação `CryptoRegistryHistory.select_at` reutiliza o seletor Kraken WU9 que antes aceitava `PF_AAPLXUSD` **falsamente declarado** em uma fixture como `base=BTC`, `pair=BTC:USD`, `category=None` mesmo com registro BTC e `tradfi=false`. O numerador do símbolo não era conferido. Após WU29, o seletor recusa tais inconsistências (`symbol_base_mismatch`) antes de ranquear `ticker.volumeQuote`. O comparador entende apenas o alias oficial `XBT → BTC` da API Kraken (https://support.kraken.com/br/articles/360001206766-bitcoin-currency-code-xbt-vs-btc) e não cria um segundo ativo `XBT` no registro canônico. Assim `PF_XBTUSD`/BTC continua funcional com documentação explícita, sem troca de provedor.

É uma **barreira contra metadados contraditórios**, não um registro positivo real nem verificação de 2 fontes independentes. `PF_AAPLXUSD` com `base=AAPLX` e `category` indevidamente ausente ainda dependeria da classificação crypto-only confiável; não se declara resolvida a issue #32 ou os direitos. Os exemplos da regressão são sintéticos, não observações da corretora, e não autorizam Top50 histórico/live.


## J1/WU30 — Impedir bypass do manifesto ao inserir registro em memória
`CryptoRegistryHistory.append` revalida a integridade estrutural de `CryptoRegistrySnapshot` **mesmo quando o chamador usa seu construtor público** em vez de `load_registry_json/from_manifest`. O histórico reconstitui o manifesto v1 a partir de `VerifiedAsset` e `IdentityEvidence` e reutiliza o validador único, exigindo SHA256 canônico, 2–6 referências por ativo, independência de domínio/publicador, campos/timestamps válidos, unicidade e política de uso privado. Compara a instância recebida à reconstrução para recusar um campo derivado `publisher_root` alterado sem mudar o hash.

Antes, uma fixture `CryptoRegistrySnapshot(..., sha256_digest="0"*64, assets=(...))` podia entrar em `CryptoRegistryHistory` e ser usada para `verified_crypto_bases` sem passar na prova de integridade. Agora ela é recusada na inserção; inserir um snapshot legítimo e repetir idempotentemente continua funcionando. Um manifesto deliberadamente criado com URLs `example.org` e SHA válido é **apenas sintaticamente consistente**, não registro real, direito de uso nem fonte verificada. Mesmo com a integridade preservada em memória, a classificação crypto-only continua bloqueada por revisão externa da issue #32; dados/Top50 live não foram autorizados.

## Alternativa J1/WU32 — identidade aberta não é certificado (25/10/2026)
A [política de licenciamento Wikidata](https://www.wikidata.org/wiki/Wikidata:Licensing) coloca os registros estruturados sob CC0, podendo fornecer referência independente reutilizável para um crosswalk `venue_symbol -> canonical_id`. Contudo uma afirmação editável no Wikidata não comprova crypto-only, projeto ativo, contrato perp da mesma base ou histórico da venue; por ativo, reter revisão humana e outra fonte realmente independente com direitos. A [precificação atual CoinMarketCap](https://coinmarketcap.com/api/pricing/) oferece Basic gratuito com licença comercial limitada, mas páginas antigas e contratos pessoais/comerciais exigem verificar qual adesão/termos foram efetivamente aceitos. A [API keyless](https://coinmarketcap.com/api/keyless/) é direcionada a avaliação/protótipo, não licença de redistribuição. Nenhuma API de identidade foi chamada, nenhum registro aprovado em tempo real, e #32 segue aberta.

## J1/WU33 — primeiro registro REAL, BTC e ETH, revisado para pesquisa interna (25/10/2026)
Arquivo imutável: `registries/crypto-btc-eth-20261025-v1.json`, digest SHA-256 `ad860bf8f69a76352a839f269f1337b33db20c51c2d1ff8750ec12c0fc05e301`, `observed_at_ms=1792964997555` UTC. **Não é fixture de identidade inventada:** somente os dois ativos de identidade conhecida foram examinados como links públicos, sem copiar valores de mercado, sem chamar API de terceiros e sem chaves.

- **BTC / bitcoin-mainnet:** [Bitcoin.org FAQ](https://bitcoin.org/en/faq) identifica Bitcoin como criptomoeda; [Banco Central Europeu](https://www.ecb.europa.eu/ecb-and-you/explainers/tell-me/html/what-is-bitcoin.en.html) o identifica independentemente como criptoativo. Dois publicadores distintos.
- **ETH / ethereum-native-ether:** [Ethereum.org](https://ethereum.org/pt-br/what-is-ether/) identifica ETH como ativo nativo; [CoinGecko, página pública de Ethereum](https://www.coingecko.com/en/coins/ethereum) confirma o par de identidade Ethereum/ETH de fonte independente. **A referência à página não implica licença para copiar seu feed ou usar a API comercialmente.**
- `reviewed_by=assistant-technical-review` é revisão documental **por assistente**, não auditoria jurídica, assinatura humana ou aprovação de cada ativo para trading. `observed_at_ms` fixa a primeira data de conhecimento; dados anteriores NÃO podem receber esse registro por retroação. A revisão de versão/hash do manifesto permanece em GitHub.

Uso: carregar via `load_registry_json`, anexar a `CryptoRegistryHistory` e chamar `select_at` somente para capturas de mercado ocorridas após este registro; a filtragem WU29/WU31 segue excluindo tokens de ações, base/símbolo incoerente e inativos. No máximo 2 bases podem ser positivamente reconhecidas; o limite **N até 50 não significa 50 ativos disponíveis**. Nenhum dado de exchange foi consultado ou armazenado nesta entrega. Sem renovação temporal automática: um registro antigo deve expirar conforme idade definida pelo chamador.

**Não aprova:** licenças de mercado, direitos comerciais, elegibilidade regional, nomenclatura real do contrato (especialmente XBT/BTC), unidade de volume Kraken #36, retroatividade de listagens ou cobertura de Top50. Issues #2/#32/#36/#48 abertas. Pesquisa interna somente, sem publicação de dados.

## J1/WU37 — Manifesto v2 com dez identidades cripto, sem retroagir nem inferir Top50 (25/10/2026)
A issue #120 cria `registries/crypto-bases-10-20261025-v2.json` com **10 bases documentadas**: BTC, ETH, SOL, XRP, ADA, DOGE, LTC, AVAX, LINK, DOT; digest SHA256 canônico `a95179a342289833f3b14f0c2442163acdcb32f1ca0c9569fa01adeaa3534746`; `observed_at_ms=1792968148000` (UTC, 2026-10-25T22:42:28Z). O manifesto v1 BTC/ETH permanece inalterado com suas evidências/tempos originais; v2 só é consultável a partir de sua própria data. `reviewed_by=assistant-technical-review` descreve **revisão documental por assistente**, não parecer jurídico, certificação humana ou atestado de listagem em perp.

Fontes PRIMÁRIAS e referências INDEPENDENTES, apenas LINKS e identidade, sem copiar preço, dados de mercado ou consumir API:
- SOL: [Solana — SOL nativo](https://solana.com/learn/introduction-to-solana-tokens) + [CoinGecko SOL](https://www.coingecko.com/en/coins/solana)
- XRP: [Ripple — XRP nativo XRP Ledger](https://ripple.com/xrp/) + [CoinGecko XRP](https://www.coingecko.com/en/coins/xrp)
- ADA: [Cardano — ADA moeda nativa](https://docs.cardano.org/about-cardano/new-to-cardano/what-is-a-cryptocurrency) + [CoinGecko ADA](https://www.coingecko.com/en/coins/cardano)
- DOGE: [Dogecoin — criptomoeda](https://dogecoin.com/) + [CoinGecko DOGE](https://www.coingecko.com/en/coins/dogecoin)
- LTC: [Litecoin — moeda digital](https://litecoin.org/) + [CoinGecko LTC](https://www.coingecko.com/en/coins/litecoin)
- AVAX: [Avalanche — AVAX nativo](https://docs.avax.network/docs/primary-network/avax-token) + [CoinGecko AVAX](https://www.coingecko.com/en/coins/avalanche)
- LINK: [Chainlink — token LINK](https://chain.link/economics) + [CoinGecko LINK](https://www.coingecko.com/en/coins/chainlink)
- DOT: [Polkadot — DOT nativo](https://wiki.polkadot.com/learn/learn-dot/) + [CoinGecko DOT](https://www.coingecko.com/en/coins/polkadot)

A versão é explicitamente escolhida no código/CLI por `--registry btc-eth` (v1, default reprodutível) ou `--registry expanded-10` (v2). O `CryptoRegistryHistory` revalida SHA/manifesto de ambas. Não usar identidade v2 para qualquer amostra anterior a `1792968148000`, nem carregar preço CoinGecko. Um ativo no registro **não garante** par Kraken PF_ existente, status tradeable, liquidez USD ou permissão de negociação; `select_at` aplica todos os filtros da venue e `max_symbols=min(50, len(registry.assets))`. Dez identidades não significam dez mercados, 50 contratos elegíveis ou os 50 maiores históricos; registrar a quantidade efetiva observada. Sem direitos comerciais/redistribuição de dados de exchange, sem `ClosedCandle` canônico, base/quote volume de candle ou trading. J1 #2/#32/#36/#48 ABERTAS.
