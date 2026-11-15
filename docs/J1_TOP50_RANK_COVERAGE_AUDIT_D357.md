# J1/D357 — auditoria de cobertura do ranking Top50 de pesquisa (15/11/2026)

## Por que esta auditoria

O Product Owner confirmou D279/D356: o filtro automático de perpétuos lineares USDT **já resolveu a triagem para pesquisa**. Não voltar a consultas de Instagram, duas fontes por token ou dossiês manuais. O trabalho solicitado é auditar a integridade da **ordenação dinâmica** da pool técnica no instante da seleção, sem alterar o produto, ampliar direitos ou reiniciar o coletor WS.

A auditoria está dividida em observações **comprovadas** e uma lacuna **não comprovada**. Não transformar ausência de prova em defeito presumido.

## Provas reais disponíveis na VPS

- Rotação ativa de 14/11/2026 ~15:13 UTC: `journalctl -u cia-j1-n50-ws-rotate.service` retornou `n50_ws_epoch_rotation_complete`, `rank_network_requests=372`, `metadata_network_requests=1`, `rotation_due=true`, `new_epoch_activated=true`, `old_epoch_preserved=true`, sem writes/ordens. SHA de scope: `4b81c74306c930561856ebb09db8e195b6b50383df0636ee71d018230717041e`.
- D323 owner executada e aprovada no dia 15/11: `ws_24h_local_evidence_verified`, mesma SHA de scope, metadados `24ee84514e180a374a1a48940a7f0af9f188f5ba895d28dca2a8c66ba2ff7cfd`, 24 horas × 50 contratos, `persisted_ws_rows=1200`, replay SQLite e digest verificados, nenhuma ordem. Isso comprova **integridade dos dados dos 50 escolhidos**, não qualificação de todos os candidatos antes da escolha.
- D280 (11/11): catálogo de 930 instrumentos, 370 candidatos provisórios; D281 verificou 370/370 em janela histórica anterior. Não projetar o histórico D281 para o PIT da rotação de 14/11.
- Uma consulta `runuser -u cia-probe` no broker administrativo atual falhou com `cannot set groups: Operation not permitted`. O broker **não** fornece acesso owner arbitrário; não contornar DAC nem mudar permissões. O sidecar D323 preexistente avalia **jornal WS**, não o relatório completo de ranking D286.

## Lacuna encontrada em revisão de código

`research_current_closed24h_once` D286 obtém o catálogo antes e depois de coletar candidatos; `rank_auto_candidates_closed24h_offline` rejeita candidatas sem 24 barras para o ranking, sem imputar zeros, e fornece `complete_closed24h_candidates`, `insufficient_closed24h_candidates`, `zero_closed24h_turnover_candidates`. No entanto, o status de pesquisa `current_closed24h_provisional_perpetual_rank_research_only` é possível quando há **pelo menos 50 contratos completos**, mesmo se **outros candidatos estão incompletos**.

Isso é aceitável para um ranking **provisório da subamostra completa**, mas não certifica que é o Top50 do conjunto integral naquele PIT: um candidato sem observações completas poderia ultrapassar o 50º. O manifesto D287 selado registra o digest da pool, digest do rank e a lista de 50, mas não preserva as contagens de incompletude. O relatório sanitizado de rotação D321 publicado em 14/11 também só contém os GETs e digests, não as contagens. **Logo, não é possível provar retrospectivamente a cobertura integral da pool a partir desses logs.** Isso não é evidência de erro no ranking atual.

## Mudança aditiva de código (sem deploy)

- `sanitized_rank_coverage_receipt` verifica a soma `complete_positive + complete_zero_turnover + incomplete == pool_total`, tipos exatos, timestamps PIT, digests SHA, dois catálogos estáveis e status exclusivamente de pesquisa. Recusa contagens contraditórias/adulteradas; sem símbolos nem preços.
- `capture_and_seal_current_rank_once` usa a auditoria **antes de selar** o D287 e expõe no recibo somente contagens, digest e flag `rank_all_candidate_windows_complete24h`.
- `rotate_n50_ws_owner_epoch_once` propaga esses campos ao relatório sanitizado da rotação, permitindo cruzar o digest do ranking/da pool com a SHA da coorte que D323 observa posteriormente.
- Uma captura com 50 completos e um incompleto **continua apta a pesquisa N50 provisória**, mas emite flag de **cobertura integral falsa**. Não impor uma mudança de regra que possa bloquear a rotação por listagem recente, não editar contrato do manifesto v1 ou histórico D323, não ligar sinal/ordem e não alterar os serviços existentes.
- Zero novos GETs/tempo de captura, SQL, arquivos persistidos, segredos, dependências ou APIs. O código integrado **não atualiza o executável da VPS** sem gate de release; logs históricos de 14/11 não ganham contagens retroativas.

## Critérios de aceite desta melhoria

1. Unit tests D286: 51 contratos, 50 com 24 candles, um com 23; resultado research-only sem declarar full pool.
2. Unit tests D287: recibo de 370/370 completo, 369+1 incompleto, inconsistência de soma, flag forjada, hash malformado; falha antes de gravar manifesto.
3. D321: propagação de contagens/digests sem símbolos, preservação do no-retry/claim por epoch e de `orders_sent=false`.
4. CI Linux/docs, Windows/offline e Chrome/PAPER no HEAD final, revisão e merge seguro sem publicação/produção.

## Gate futuro e limite de J1

Um relatório **real de rotação que já contenha a nova telemetria**, obtido pelo canal owner autorizado depois do gate de implantação, permitirá verificar PIT, composição da pool, 24h completas, ausência de candidatos sem dados e os digests correspondentes. Se houver incompletos, a pesquisa N50 não será descartada, mas o selo "Top50 integral da pool" permanece negado. Também é preciso tratar o que foi explicitamente excluído/ambíguo pelo filtro (D279) sem exigir classificação manual token a token.

D323/50×24 já PASS; o subgate Top50 integral da pool e o fechamento formal #319/#2 **ainda não possuem essa prova**. Mantenha `marketwide_top50_verified=false`, `crypto_identity_independently_verified=false`, `approved_for_signals=false`, `orders_sent=false`; esses campos têm escopo de negociação/autenticação além da pesquisa. A entrega aqui é **auditabilidade**, não autorização de mercado, estratégia ou release. Custo R$0.
