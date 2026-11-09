# J1 D269 — replay determinístico 98h de três épocas WS existentes

## Resultado de auditoria de código

A renovação básica de escopo WS em 48h **já estava implementada**, portanto não criar outro coletor nem substituir `_catalog_scope`, `_write_renewed_scope`, `_read_epoch_chain` ou `_audit_epoch_chain`. O código em `bybit_ws_owner_pilot.py` recolhe um catálogo bounded quando `now - observed_at > 48h`, escreve nova época imutável apenas se os contratos e especificações não mudaram, retém o PIT original, e falha fechado para `10006` e mudança de universo. `MAX_PIT_SCOPES=64` também existe. A documentação inicial de #525 subestimava esse suporte; atualizada via comentário verificado.

## D269 adiciona evidência de duração multi-epoch

Dois testes offline com fake clock em `test_j1_ws_owner_pilot.py`:
- T0, T+49h, T+72h, T+98h: duas renovações bem sucedidas, 3 épocas PIT no total, nenhuma nova consulta aos 72h (último snapshot com só 23h), no máximo 2 GETs públicos *sintéticos* por renovação, arquivo original e 1ª época preservados byte-a-byte; journal bytes não alterados na ausência de velas confirmadas; `_audit_epoch_chain` utiliza 1 época até T+49h, 2 desde a 1ª vela fechada pós-renovação, e 3 desde a 2ª, sem ranqueamento fictício.
- T+98h com catálogo negado por 10006: **um único GET sintético**, stop-on-denial; preserva todos os arquivos, histórico e snapshots e não inicia nova sessão WS.

As fixtures exercitam validação de identidade estável e ordenação causal existente. Não simulam recebimento de 52×24h de candles completos. `marketwide_top50_verified=false` e `local_two_hour_continuity=false` permanecem falsos.

## Próximos bloqueios não resolvidos

- Churn legítimo de universo exige **journal novo separado, com admissão aprovada e crosswalk independente**; `_write_renewed_scope` bloqueia mudanças e faz correto fail-stop. Não implementar troca automática sem política de identidade de #319.
- A VPS comprovou D267 `service_uninstalled`, `WS_JOURNAL_NOT_FOUND`; D268 `private_directory_requires_owner_provisioning`, 10 testes PASS, sem deploy/GET/ordens. O serviço 24/7 ainda não está instalado. Gate separado de preparação e ativação continua obrigatório (#429).
- Prova de 24 horas reais de fluxo, close UTC, gaps e recuperação não é substituída por CI de simulação.

Testar CI Linux/docs, Windows/offline e Chrome/PAPER no SHA da PR e merge sem deploy se verdes. Não executar nada na VPS para este teste puramente offline; nenhuma nova API paga, ordem, rede, migration ou alteração de banco privado.
