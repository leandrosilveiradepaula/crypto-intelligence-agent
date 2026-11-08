# J1/D266 — dossiê causal de identidade, sem allowlist automática

## Evidência e objetivo

Prova owner D265: 30/30 testes aprovados; 819 históricos completos, 298 vetos de **pesquisa retrospectiva** (297 metadados TradFi atuais + BZ Brent Oil documental), 50 candidatos = 30 referências antigas vencidas, 18 hipóteses e 2 ainda desconhecidos. Hash raw preservado b4e4884d28e4a4b385c94ea521201006242d449828d575a56f01cb2b70b8faaa; SHA sidecar 0b1bde685b053a6036b71cf350cb1cf32cda463b43b2df5251b10f35ffcecf3a; hash fronteira 30e4fcd7d10c38cdb6a7c3f437f73efc1d5ab58fc5df92ea60da7406500a994a. Nenhuma requisição de rede, escrita ou ordem.

D266 fornece **validador puro e offline de alegações**, para organizar futuras evidências de cada contrato sem confundir URLs, hashes ou manifests com autenticidade. `crypto_intelligence_agent/bybit_identity_dossier_guard.py` recebe um dossiê de pesquisa com símbolo de venue, ID de ativo proposto, classe, ID de contrato venue, contrato/mint de rede (opcional), clock de observação/validade, revisão e evidências de URLs públicas (publisher e IDs declarados). Exige esquema estrito, UTF8/JSON canônico SHA256, links públicos HTTPS sem credenciais, publishers/roots distintos e cronologia consistente. Reutiliza o parser de URLs do registro existente, sem fazer GET ou capturar páginas externas.

**Política de precedência**: negativa documentada (ex. BZ) ou indicador atual da Bybit; veto de colisão de ticker (LIT/ARIA/BIRB/CLANKER) ou tokenização commodity (XAUT); prova fora da janela `decision_at_ms`; fontes de mesma origem ou únicas; classe não cripto; revisão manual do contrato/mint; hipótese de pesquisa. Todos os estados retornam **`identity_approved=false`, `eligible_top50=false`, `marketwide_top50_verified=false`, `orders_sent=false`**, sem possibilidade de promoção automática. Uma declaração de duas fontes com IDs de ativo e timestamps escolhidos pelo usuário **NÃO** autentica a venue Bybit nem prova que o token está na rede ou que a data é real. A revisão exigirá conferir fontes primárias e token contract/mint fora do validator.

## Testes e limites

Fixtures adversariais: BZ Brent oil com dossiê falsamente cripto, metadado atual negativo, XAUT RWA, CLANKER/LIT/ARIA/BIRB, aliases 1000PEPE e PUMPFUN sem promoção, duas URLs de mesmo publisher, uma única origem, relógio posterior ao corte 06/11 13h UTC, validade expirada, duplicatas de chave JSON, tampering SHA, URL HTTP, URL com credenciais, localhost e consulta com token. A saída por padrão não inclui símbolo, URL nem payload; classifica apenas razão e digests, para não publicar dado privado.

Esses testes não simulam a autenticidade real de fontes; nenhum ativo da lista de 50 está aprovado. Nenhuma mudança no SQLite privado, snapshot D264, universo dinâmico, fonte da Bybit ou coleta contínua. CI Linux/docs, Windows/offline, Chrome/PAPER e revisão SHA exigidos antes do merge. Seguir #517/#319 para dossiês reais e #429 para supervisor, sem ordens ou deploy.
