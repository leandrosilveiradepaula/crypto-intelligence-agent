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
