# J1/OPS37 - diagnostico sanitizado de rejeicao metadata-only

## Evidencia

A VPS OPS35 de 06/11/2026 reportou uma tentativa GET, zero resposta validada e metadata_transport_or_validation_abstain. Nao armazenou payload bruto, codigo HTTP ou campo culpado. A causa especifica permanece desconhecida. Claim original ops35-metadata-one-shot-attempt.claim CONSUMIDO e imutavel.

## Contrato de observabilidade

MetadataProbeReport agrega failure_stage e failure_category como rotulos estaticos. Os estagios sao none/preflight/fetch/response_clock/json/catalog/compare. As categorias cobrem HTTP access/transport, fetch-unclassified, clock, JSON, catalog root/missing field/invalid-or-duplicate/digest/sidecar e drift, sem nomes de ativos, corpo/URL de resposta, exception text ou campo especifico. Uma categoria apenas identifica o ponto de veto e NAO autentica a fonte.

O validador estrito _catalog OPS34 permanece obrigatorio. Nenhuma correcao sintetica, excecao de schema, migracao, backfill, gravacao, order ou relaxation de PIT. Flags usdm_contract_verified, marketwide_top50_verified, canonical_ohlcv_approved e continuous_collector_authorized continuam false.

## Gates

Testes OPS35 novos + OPS34/36 e CI Linux/docs, Windows/offline, Chrome/PAPER no SHA head e main pos merge. Nenhum acesso de mercado nesta issue. Nova prova futura exige autorizacao owner-only regional, claim totalmente novo e protocolo separado, sem reexecutar OPS35.
