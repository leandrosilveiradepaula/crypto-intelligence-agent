# J1/D278 — pesquisa de 9 concorrentes ao corte Top50 em um único lote

Diligência retrospectiva: **11/11/2026 UTC**. Issues #319 e #517. Fontes públicas abaixo foram pesquisadas **depois** da janela congelada em 06/11/2026. Nenhum dado privado, token, volume, ordem ou chave sai do host owner.

## Resultado da pesquisa

O ranking D256 + filtro contemporâneo D264 tem 50 candidatos de pesquisa e substitutos imediatamente abaixo do corte; D276 mostrou que excluir XAUT desloca LYN, e excluir também LIT/ARIA/BIRB/CLANKER desloca LYN, DOT, ICNT, ELSA e AERO. O módulo D278 documenta os **9** símbolos distintos, sem classificá-los como ativos elegíveis:

| Símbolo | Evidência primária | Situação de pesquisa |
|---|---|---|
| LYNUSDT | [Bybit, listing de perpétuo 06/10/2025](https://announcements.bybit.com/en/article/new-listing-lynusdt-perpetual-contract-with-up-to-50x-leverage-blteec52ce3c263c923/) e [Binance, 06/10/2025](https://www.binance.com/fr/support/announcement/detail/f4077219b5a441b5bf39413c603c5a7b) identifica **Everlyn AI (LYN)** | Hipótese nominal corroborada entre venues; sem mint da Bybit |
| DOTUSDT | Sem segunda fonte primária contemporânea de vínculo exato documentada neste lote | Identidade permanece não comprovada |
| ICNTUSDT | [Binance Futures, 03/07/2025](https://www.binance.com/en/support/announcement/detail/baaa3a53a66840d087e845fb44872dc8) identifica **Impossible Cloud Network** | Falta anúncio de perpétuo Bybit exato; spot não substitui prova |
| ELSAUSDT | [Bybit, listing de perpétuo 22/01/2026](https://announcements.bybit.com/en/article/new-listing-elsausdt-perpetual-contract-in-innovation-zone-with-up-to-20x-leverage-blt41fbabdeb9208666/) e [Binance Futures, 22/01/2026](https://www.binance.com/en/support/announcement/detail/4afa6aa807234762b141920847b4fe0b) identifica **HeyElsa (ELSA)** | Hipótese nominal corroborada entre venues; sem mint Bybit |
| AEROUSDT | [Bybit, migração do token spot 26/10/2026](https://announcements.bybit.com/en/article/bybit-will-support-the-aerodrome-aero-token-migration--art01f028b44dd4/) | **Atenção:** o anúncio NÃO autentica o perpétuo AEROUSDT; contrato Base mudou e há cronologia |
| LITUSDT | [Bybit, listing de perpétuo 30/12/2025](https://announcements.bybit.com/en/article/new-listing-litusdt-perpetual-contract-with-up-to-25x-leverage-blt0bf35ec2cd5047d8/) e [Binance Futures, 23/12/2025](https://www.binance.com/en/support/announcement/detail/6a33be00231c4539b3a4a625538e4d1e) identifica **Lighter Protocol (LIT)** | Boa hipótese nominal; a colisão prévia com Litentry continua não aprovada historicamente |
| ARIAUSDT | Sem fontes primárias suficientes para resolver a colisão `aria-ai` / `aria` | Colisão permanece |
| BIRBUSDT | Sem fontes primárias suficientes para resolver `moonbirds` / `birb` | Colisão permanece |
| CLANKERUSDT | Já possui D274: Bybit Learn e Binance, hipótese **tokenbot (CLANKER)** | Pesquisa de duas fontes, colisão histórica preservada |

**AERO, risco material:** Bybit publicou o endereço Base antigo `0x940181a94A35A4569E4529A3CDfB74e38FD98631` e novo `0x3f5bF3EdAc59d650D8fDf9657a71F2f904A3a4Ee`; depósitos/retiradas tiveram interrupção. A comunicação é **spot/migração** e inclui delist de **VELODROMEUSDT**, não autentica um perpétuo **AEROUSDT** ou seu índice naquele instante. Nunca deduzir o mint de perpétuos a partir da migração spot.

## Implementação

`crypto_intelligence_agent.j1_cutoff_primary_batch_d278` versiona 9 dossiês nominais, fonte Bybit/perp, Binance/perp e Bybit spot-migração em classes **distintas**, publicações e revisão. Dois domínios não certificam identidade on-chain; simples URL/documento não autentica a captura do catálogo nem timestamp PIT.

`scripts.j1_d264_private_metadata_snapshot.replay_private_snapshot` agora incorpora `cutoff_primary_batch_research` usando os mesmos dados de ranking já auditados: fronteira de 50 e os dez próximos concorrentes depois do filtro negativo. Nenhuma consulta HTTP/SQL adicional além do replay existente, nenhum coletor novo. A saída padrão contém **somente contagem agregada, categorias e digest**. Nomes/links são impressos somente no console owner com `--include-private-symbols`, já existente. Zero permissão alterada.

## Gates e próxima ação

CI Linux/docs, Windows/offline e Chrome/PAPER no head final, revisão e merge sem produção. Reexecutar no host `cia-probe` após merge, conferindo digest e classes; corrigir eventuais divergências sem inventar aprovação.

Nenhuma decisão nova sobre XAUT. LIT, ARIA, BIRB e CLANKER continuam `ticker_collision_unresolved` na camada histórica D261; D278 é prova adicional tardia, não mutação de identidade PIT. `marketwide_top50_verified=false`, `trading_enabled=false` e `eligible_crypto_approved=false` são invariantes. O Top50 global só poderá ser certificado depois de identidade contratual independente, PIT verificável e exclusões comprovadas.
