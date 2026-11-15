# J5/N50 #636 — progresso na mesma coorte sem falsas reinicializações

## Problema observado

Em `srv1319424`, os 24 relatórios WS N50 entre 13/11/2026 18:00 UTC e 14/11/2026 17:00 UTC confirmaram 50/50 em cada hora, mas os primeiros 22 tinham uma coorte e os dois últimos, outra. A rotação real ocorreu em 14/11 às 15:13:39 UTC, preservando a epoch anterior segundo o log. **24 relatórios de serviço 50/50 não são 24 candles dos mesmos 50 contratos nem replay SQLite.**

Na leitura de 15/11, observamos 18 relatórios 50/50 consecutivos de uma única coorte, entre 14/11 16:00 e 15/11 09:00 UTC, todos com `hour_evidence_sha256` presente. Esta leitura não executou D323 e não certifica os dados privados.

## Contrato aditivo do relatório `j5-n50-ws-log-progress-v1`

O projetor `project_n50_ws_log_progress` mantém os campos, contratos e 24 `slots` anteriores. Acrescenta somente:

- `same_scope_recent_50_of_50_hours` — sequência **recente**, contígua e limitada a 24, de fechamentos 50/50 com o mesmo par sintaticamente válido `ranked_scope_sha256` e `ws_metadata_sha256` do último fechamento elegível; um novo par reinicia *apenas esta métrica de interface*, não a coleta nem a auditoria.
- `scope_evidence_available` — `true` apenas quando o último fechamento OK fornece o par completo de digests; no legado sem digests a métrica aparece indisponível, nunca inferida.
- `scope_changed_in_window` — dois ou mais pares distintos de digests aparecem em registros OK da janela móvel; é mudança observada em logs, **não falha** de coleta e não atesta execução válida da rotação de 36 horas.

**Segurança:** as strings dos digests só existem na memória transitória do projetor, passam por validação hexadecimal de 64 caracteres e nunca são devolvidas no JSON sanitizado, HTML estático ou DOM. Símbolos, preços e outros campos do relatório bruto continuam não expostos. Falhas, duplicatas, dados sem digest e horas ausentes não entram na contagem de coorte. Contratos REST e J2 não são alterados. O importador do painel aceita relatórios v1 legados sem esses novos campos e não inventa continuidade.

A interface mobile exibe as duas medidas separadas: horas 50/50 da janela e horas recentes da mesma coorte identificada nos logs. O alerta explica mudanças legítimas de coorte. Continua mostrando `owner_d323_24h_audit_verified=false`, `approved_for_signals=false`, `orders_sent=false`, sem ordens nem tráfego novo.

## Critérios de aceite e continuidade

- 22 registros OK da coorte A + 2 da B: 24 horas 50/50, sequência recente de serviço 24 e sequência da coorte B **2**.
- 24 OK com o mesmo par de digests: métricas 24 e 24, sem marcar D323 `PASS`.
- Sem digests: contagem legada de serviço preservada, sequência de coorte **0/indisponível**.
- Digests inválidos/parciais no relatório OK: abstém na projeção. Falhas não precisam expor hashes.
- Segurança da página `CSP`, localhost, zero requests externos e PAPER preservada. CI Linux/Windows/PAPER necessária antes de merge sem deploy.

**Decisão:** seguir com J2/J3/J4/J5 em paralelo. Para concluir o gate de integridade WS J1, executar D323 uma vez na primeira janela de 24 horas da coorte efetivamente ativa, sem criar novos ciclos de espera artificial; caso haja abstenção, investigar seu motivo preciso. Homologação de cobertura marketwide Top50 (#319) segue separada, sem promover a coorte provisória a sinal aprovado.
