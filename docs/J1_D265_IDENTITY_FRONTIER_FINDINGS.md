# J1 D265 — diligência dos dez símbolos não resolvidos na D264

## Prova real privada de entrada

O usuário executou replay local owner-only D264 (08/11/2026 02:14 UTC), **sem GET**, exibindo somente símbolos públicos e ordem de pesquisa: #30 `BZUSDT`, #33 `WLFIUSDT`, #36 `CAPUSDT`, #38 `CYBERUSDT`, #40 `CLANKERUSDT`, #43 `XPLUSDT`, #44 `FARTCOINUSDT`, #47 `DGAIUSDT`, #48 `PONSUSDT`, #49 `ASTERUSDT`. Essa é a lista observada ANTES da negativa BZ D265; não publicar nem recriar arquivo D264, nem assumir que as mesmas posições persistem após nova versão da classificação.

## Descoberta negativa crítica

O anúncio oficial da Bybit de **13/05/2026** identifica `BZUSDT` como perpétuo referenciado a **Brent Oil** e não como base cripto, embora o contrato não tivesse sido marcado entre os 297 atuais por `marketRegion`/`underlyingTicker`. Fonte primária: https://announcements.bybit.com/en/article/new-listing-bzusdt-perpetual-contract-with-up-to-10x-leverage-blt847e7209dd33a69a/. **Conclusão:** campos vazios de metadados contemporâneos não constituem prova cripto e negativas oficiais por símbolo exato precisam prevalecer. D265 adiciona BZ ao catálogo D259, de 24 para 25 exemplos; nenhum campo histórico ou arquivo privado é alterado. O digest do catálogo muda; o ranking de 819 velas brutas continua intocado. A exclusão ocorre somente na fronteira de pesquisa (que poderá trocar o 50º selecionado).

## Nove identidades restantes — hipóteses NÃO aprovadas

| Contrato | Pista de pesquisa externa | Política |
|---|---|---|
| WLFIUSDT | World Liberty Financial, CoinGecko ID `world-liberty-financial` | candidato não autenticado para venue/PIT |
| CAPUSDT | Cap, `cap` | candidato; exigir chain/mint/contrato |
| CYBERUSDT | Cyber/CyberConnect, `cyberconnect` | candidato; exigir venue/PIT |
| CLANKERUSDT | **colisão:** tokenbot/Base `tokenbot-2` ≠ outro token Solana `clanker` | `ticker_collision_unresolved`, veto até ID real |
| XPLUSDT | Plasma `plasma` | candidato, sem autorização |
| FARTCOINUSDT | Fartcoin `fartcoin` | candidato, sem autorização |
| DGAIUSDT | nenhuma atribuição canônica confiável obtida | `identity_unresolved`, sem inventar referência |
| PONSUSDT | Pons `pons` | candidato; vincular endereço de contrato/venue e data |
| ASTERUSDT | Aster `aster-2`, migração histórica APX→ASTER | candidato; conferir migração/chain e PIT |

Fontes externas de pesquisa:
- https://www.coingecko.com/en/coins/world-liberty-financial
- https://www.coingecko.com/en/coins/cap
- https://www.coingecko.com/en/coins/cyberconnect
- https://www.coingecko.com/en/coins/tokenbot-2
- https://www.coingecko.com/en/coins/clanker
- https://www.coingecko.com/en/coins/plasma
- https://www.coingecko.com/en/coins/fartcoin
- https://www.coingecko.com/en/coins/pons
- https://www.coingecko.com/en/coins/aster-2

**Importante:** lista externa da CoinGecko é uma origem agregadora, não duas fontes independentes para comprovação. A presença de par Bybit em um agregador não autentica o contrato de futuros nem o instante de 06/11 13h UTC. `DGAIUSDT` permanece explicitamente desconhecido. `CLANKERUSDT` não é aprovado por ticker. Candidatos não são números positivos da allowlist.

## Mudanças técnicas

`bybit_identity_research_leads_d265.py` contém nove registros exatos e digest canônico, sem credenciais ou valores de mercado. Integra `research_category`/`research_details` sem mudar as dez hipóteses D261 anteriores. A negativa BZ precede qualquer referência antiga. D264 replay já usa `NEGATIVE_EVIDENCE` e `research_category`; ao executar novamente no mesmo snapshot privado, ele deve (a) excluir BZ, (b) preservar digest bruto e SHA do snapshot, (c) recalcular uma fronteira de 50 **de pesquisa**, (d) manter flags `marketwide_top50_verified=false`, `crypto_identity_independently_verified=false`, `metadata_pit_valid_for_frozen_window=false`. Valores e hashes novos são **pendentes da prova VPS**; não afirmar posição/contagem nova antes do log.

Testar fontes, validação de aliases/colisões, negativa BZ, ausência de sinal D263, DGAI sem ID, tampering e regressões de censo. Validar CI Linux/docs, Windows/offline e Chrome/PAPER no HEAD final, revisão SHA e merge sem deploy; depois **apenas replay offline**, nenhum GET novo. #517 e #319 seguem abertas para duas origens independentes e crosswalk canônico de todos os 50; #429 para continuidade; #2 J1. Nenhum trading, release, migration, serviço, gasto ou refetch dos 822 candles.
