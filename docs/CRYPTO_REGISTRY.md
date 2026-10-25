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
Rejeita ausência e obsolescência conforme limite informado pelo chamador.

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
