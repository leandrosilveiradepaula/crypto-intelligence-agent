# J1/D335 — folga para auditoria de hora WS dentro de D313

## Observação
Na janela real de 13/11/2026, 16:59:30–17:02:00 UTC, o serviço capturou 50 eventos fechados, `accepted_postclose_trade_clock=50`, `closed_events_appended_to_ws_journal=50`, `subscription_acks=1` e zero GET/ordens. Ainda assim `ws_owner_hour_audit_abstain`, `confirmed_contracts=0`, exit65. O OnFailure desativou WS/rotação e restabeleceu N2 REST (ver #619 e #585). **Não** é prova de 50/50 na segunda hora.

## Diagnóstico e hipótese explícita
O gate D313 rejeita `observed_at_ms > close+120000`. O `j1_n50_ws_cached_runner` permitia um budget nominal até `close+119000`, deixando só ~1s para término da sessão + auditoria. O fim registrado em 17:02:00 UTC é compatível com expiração de prazo por milissegundos, mas não há timestamp exato da chamada audit; a causalidade exclusiva não foi atestada.

## Correção focal D335
O budget passa a terminar nominalmente até `close+105000`: **15 segundos de folga** antes do limite estrito de 120s, sem mexer no auditor, no parser de WS, no journal SQLite, na validade de cada candle, no epoch N50 ou em serviços. Prova sintética adicional injeta 10s de atraso antes do auditor após sessão prolongada e exige 50/50 real no SQLite fixture; 49/50 permanece incompleto. Nenhum retry ou REST GET, nem apagamento de dados.

## Gates
Rodar regressões D313/D315/D317/D323/D325/D333, o novo teste de borda, compilação e CI Linux/docs, Windows/offline e PAPER/mobile no HEAD. Merge seguro **sem deploy** se gates verdes. Um novo processo de recuperação root pinado no SHA realmente instalado ainda será necessário, com N2 rollback, antes de reativar WS. Não executar D333 novamente (OLD_SHA incompatível); não alegar J1 completa, 24h, 36h ou Top50 marketwide. Nenhuma ordem ou custo adicional.
