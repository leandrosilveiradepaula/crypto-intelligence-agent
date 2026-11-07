# J1 D257 — triagem PIT da identidade sobre o censo fechado (sem rede)

## Fato de partida e objetivo
Prova D256 na VPS em 06/11/2026 19:02 UTC: `basic_survey_integrity_pass_incomplete_unverified`, 822 membros técnicos do catálogo, 819 séries de 24 candles 1h fechados (19.656 velas), 3 séries com 0..23 velas (6 observadas), zero pendências, digest Top50 **apenas entre séries completas** `b4e4884d28e4a4b385c94ea521201006242d449828d575a56f01cb2b70b8faaa`. Auditoria local read-only confirmou integridade, mas não origem HTTP por invocação, identidade crypto-only ou operação 24/7.

O módulo `scripts/triage_j1_marketwide_identity.py` aproveita o banco owner-only e as verificações de `audit_j1_marketwide_checkpoint._replay`; **não** executa GET, não migra SQLite nem grava candle. Ordena novamente os 819 completos por soma Decimal exata de `quote_turnover` em 24h e compara somente **sobreposição de referência histórica** com o manifesto versionado `registries/crypto-bases-52-20261029-v4.json`. Não consulta ticker de 24h móvel nem imputa turnover zero aos três contratos curtos. Disponibiliza digest de prioridade entre contratos sem base no registro anterior, sem imprimir símbolos/valores privados.

## Separações que não podem ser suprimidas
- **O arquivo de 52 bases foi observado em 29/10/2026** e está vencido para o corte de 06/11 13:00 UTC sob a política de sete dias; seu conteúdo pode ajudar a priorizar nova revisão, **não** demonstra elegibilidade atual. O auditor exige hash/estrutura/evidência do manifesto existente e comprova a data com `CryptoRegistryHistory.as_of(..., max_age_ms=7d)`; **não** retrodata outra revisão.
- `historical_registry_overlap_complete_count` e `historical_registry_overlap_top50_subset_count` significam sobreposição histórica de nomes, não certificação das identidades nem ranking de todos os elegíveis.
- `identity_review_priority_count` e digest cobrem membros completos sem referência no manifesto antigo, na ordem do turnover fechado observável. São itens para **revisão externa independente**, não sinais de trade.
- Nenhum contrato 24h incompleto é promovido ou recebe volume sintético. Uma base no registro não substitui a falta de candles nem valida listagem recente.
- `current_eligible_contracts_verified=0`, `crypto_identity_independently_verified=false`, `marketwide_top50_verified=false`, `closed_24h_rank_promoted=false`, `live_identity_approved=false` e `continuous_collector_verified=false` invariantes. Mesmo um registro válido em fixture não é comprovação de fonte real/contrato/identidade externa nem licença para operar.

## Execução owner-only depois de CI e merge
Na VPS `srv1319424`, checkout clean e FF-only para SHA aprovado, em `/home/cia-probe/agent/repo`, sob usuário `cia-probe`:
```bash
/home/cia-probe/agent/ws-venv/bin/python -m scripts.triage_j1_marketwide_identity \
  --directory /home/cia-probe/agent/j1-global-closed24h-private/run
```
Saída limitada a contagens, flags e hashes; acesso apenas ao mesmo SQLite privado 0600, pasta owner 0700 e lock compartilhado não bloqueante, `mode=ro/query_only`. Esperar status `identity_review_queue_stale_registry_no_go` se o arquivo antigo mantiver a idade original. **Não registrar dados/símbolos privados no GitHub.**

## Gates subsequentes
1. Confrontar contagens e digest com a prova D256; não aprovar universo só pelo resultado numérico.
2. Efetuar revisão de identidade nova com duas fontes públicas realmente independentes, timestamps verdadeiros, qualidade de contrato e histórico point-in-time; decisão de expansão requer comprovação, sem editar/rejuvenecer manifesto antigo.
3. Planejar ranking causal posterior com todos os elegíveis contemporâneos e serviço de 24 horas supervisionado; nenhum serviço/ordem real fica autorizado por esta auditoria.
4. Validar testes adversariais offline e CI Linux/docs, Windows/offline e Chrome/PAPER sobre SHA final; PR e merge sem deploy sob gates.

J1 #319, #502, #429 e #2 permanecem abertas.


## D258 — apresentação opcional de IDs públicos no terminal privado

Para uma revisão orientada a fontes independentes sem voltar à Bybit, o comando pode receber `--include-public-symbols`. O default continua sem qualquer símbolo; com opt-in explícito, a saída JSON acrescenta `public_top50_complete_subset_review_only` (rank, símbolo público e presença/ausência de **referência no registro histórico**, jamais aprovação) e `public_short_history_contracts_review_only` (IDs de históricos incompletos, fora do Top50). Não contém preços, turnovers ou detalhes dos candles. A lista só deve circular no terminal privado do owner para pesquisa, não ser copiada automaticamente para issues, CI ou arquivos públicos. O Top50 é de **819 completos**, não o mercado crypto-only integral. O manifesto 52 está expirado no PIT: qualquer informação sobre status atual depende de prova externa nova, sem retrodatar identidade.


## D259 — documentos oficiais como evidência NEGATIVA retroativa

A prova D258 do proprietário revelou uma mistura de classes: 21 contratos identificados por comunicados oficiais da Bybit como TradFi dentro do Top50 bruto das 819 séries completas e 3 contratos short de ações TradFi recém-listadas em 06/11 às 11h UTC (até 13h, no máximo 2 velas fechadas). D259 adiciona catálogo estático versionado de **24 contratos documentados**, com URLs de anúncios, datas declaradas e digest determinístico em `crypto_intelligence_agent/bybit_tradfi_negative_evidence.py`. Fontes: [INS Loans TradFi, 26/08/2026](https://announcements.bybit.com/en/article/ins-loans-tradfi-perpetual-contracts-leverage-adjustments--art9f80e1dca25d/), [Incentivos TradFi, 19/10/2026](https://announcements.bybit.com/en/article/tradfi-liquidity-incentive-program-weight-adjustments--arte82775610db0/), [DUOL 06/11 11h](https://announcements.bybit.com/en/article/new-listing-listing-of-duolusdt-on-bybit-tradfi-perpetual-on-nov-6-2026-11-00am-utc--artde830783f6d5/), [FISV](https://announcements.bybit.com/en/article/new-listing-listing-of-fisvusdt-on-bybit-tradfi-perpetual-on-nov-6-2026-11-00am-utc--art5e5431016814/) e [FN](https://announcements.bybit.com/en/article/new-listing-listing-of-fnusdt-on-bybit-tradfi-perpetual-on-nov-6-2026-11-00am-utc--artff454659fb47/).

O resultado default informa somente contagens e hashes; o opt-in `--include-public-symbols` inclui etiqueta `bybit_tradfi_documented_retrospective` e link primário para revisão manual, separando `archived_crypto_reference_only` de `identity_unresolved`. NÃO remova esses 21 do banco nem construa Top50 cripto a partir dos 29 restantes: faltam identidade atual, cobertura dos 822 e prova temporal, e quaisquer contratos não documentados continuam ambíguos. A data impressa num anúncio não autentica que a publicação era acessível antes da janela PIT: somente classificação retrospectiva, não prova de mercado histórico ou direitos de negociação. Continuar sem ordens/rede/serviço/SQL write.


## D261 — crosswalk hipotético e fila ampliada além dos 50 brutos

`crypto_intelligence_agent/bybit_identity_crosswalk_research.py` define **10 hipóteses de pesquisa**: `1000PEPEUSDT` (multiplicador 1000), `PUMPFUNUSDT` (alias PUMP a comprovar), `TRUMPUSDT`, `AKEUSDT`, `JCTUSDT`, `UAIUSDT` (candidatos com ID externo ainda não autenticado), `LITUSDT`, `ARIAUSDT`, `BIRBUSDT` (colisões de ticker) e `XAUTUSDT` (tokenizado ouro, gate de produto distinto de `XAUUSDT` TradFi). URLs, IDs e data de compilação são referências de pesquisa, não duas fontes independentes autenticadas, não snapshots históricos e não certificação cripto. O catálogo D259 negativo prevalece sobre qualquer hipótese positiva.

O CLI D257, que já revalida todo SQLite em read-only, agora relata contagens/digest da fronteira **de pesquisa**, composta pelos primeiros até 50 contratos com 24 velas válidas entre os 819 completos **após ignorar apenas os 24 símbolos TradFi negativos documentados**. A fronteira é tirada de todo o ranking bruto, não só dos 50 de maior volume bruto. Mas faltam negativas de mercado além do catálogo, identidade independente e temporalidade verdadeira; portanto `closed_research_frontier_not_eligible_top50=true`, `candidate_research_pit_authenticated=false`, `marketwide_top50_verified=false`, `current_eligible_contracts_verified=0`. Sob `--include-public-symbols`, acrescenta `public_research_frontier_review_only` com ID público, posição de pesquisa, hipótese de ID canônico e links; sem preços/turnover/candles. Default apenas contagens e hashes. Nada é exportado/publicado automaticamente, nem salvo no SQLite. Para confirmar contratos de execução é necessário crosswalk autenticado da venue e duas fontes de identidade realmente independentes, sem reescrever o instante 06/11 13h UTC.
