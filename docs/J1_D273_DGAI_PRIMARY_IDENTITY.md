# J1/D273 — DGAIUSDT: duas fontes primárias, sem promoção histórica

Data da diligência: **11/11/2026 UTC**. Issue #517 / #319.

## Descoberta verificável

- [Bybit, 04/09/2026](https://announcements.bybit.com/en/article/new-listing-dgaiusdt-perpetual-contract-in-innovation-zone-with-up-to-20x-leverage--art151aff198a7e/): anúncio oficial do perpétuo **DGAIUSDT**, subjacente **DGrid AI (DGAI)**, liquidação **USDT**, zona Innovation, até **20x**. É vínculo nominal do símbolo ao subjacente publicado pela própria venue.
- [Gate, 23/08/2026](https://www.gate.com/pt-br/announcements/article/101292): anúncio independente da listagem spot **DGrid AI (DGAI)**, site do projeto e endereço do token BNB Chain **0x10D4183389e99233db3cc981c43443Ebd28Ebd5e**. É vínculo entre nome, ticker e contrato do token publicado por outra empresa.

Duas fontes primárias de origens diferentes são mais fortes que uma sugestão de ticker CoinGecko. O endereço on-chain foi **publicado pela Gate**, não autenticado por consulta on-chain independente. A hipótese canônica `coingecko:dgrid-ai` continua referência de pesquisa, não identidade aprovada. O limite de 20x anunciado é propriedade do contrato, não mudança da alavancagem global de pesquisa do produto.

## Limites de inferência

As fontes são publicadas antes da janela histórica de **06/11/2026**, mas foram **revisadas nesta diligência em 11/11/2026**. Data de publicação não equivale a evidência coletada/autenticada pelo agente em 06/11. Portanto o registro D273 preserva `identity_pit_authenticated=false`, `identity_approved=false`, `eligible_top50=false`, `marketwide_top50_verified=false` e nenhuma ordem. Tampouco prova volume suficiente para o corte dos 50, disponibilidade da conta/região ou estado Trading no instante do censo.

O registro `bybit_primary_identity_research.py` guarda URLs primárias, datas, token publicado e revisão retrospectiva, com digest determinístico. `primary_research_details` rejeita timestamps inválidos, separa publicação de revisão e nunca autoriza trade. Testes D273 cobrem precedência temporal, duas fontes, símbolos negativos, URLs maliciosas e não promoção. O catálogo antigo D265 permanece imutável como fotografia anterior de pesquisa; D273 é **evidência adicional posterior**, não reescrita retroativa do registro.

## Próxima etapa concreta

Cruzar D273 com a **fila real** gerada pelo bridge privado da PR #542, apenas no owner da VPS. Se DGAI estiver entre os rivais relevantes, anexar dossiê revisado com vínculo de contrato da venue e revisão PIT efetiva para novas janelas; caso contrário, priorizar os rivais acima do 50º. Não rebaixar requisitos de #319 para fechar a J1 artificialmente. Sem rede nova de mercado, migração, custo, release ou ordens nesta entrega.
