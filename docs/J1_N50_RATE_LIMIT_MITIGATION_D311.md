# J1/D311 — incidente de quota N50 e mitigação de cadência, sem nova execução

## Evidência real (12/11/2026, 16:01 UTC / 13:01 BRT)

Observação **somente leitura**, diretamente no `systemd show` e no `journalctl` sanitizado da VPS `srv1319424`, às 16:11 UTC:

- N50 `cia-j1-n50-managed.service` iniciou às 16:01:06 UTC, terminou 16:01:12 UTC em `Result=exit-code`, `ExecMainStatus=65`.
- Mensagem já sanitizada de `j1-n50-managed-tick-v1`: `operation=hourly_writer`, `status=blocked`, `failure_category=provider_rate_limit_no_retry`, `requests_attempted=4`, `new_closed_candles=3`, `epoch_id=epoch-1794492000000`, `pointer_updated=false`, `claims_created=1`, `orders_sent=false`. **Não foi publicado PIT horário com 3/50 candles**. Os 3 candles parciais podem existir no SQLite; sua integridade exata exige auditoria owner read-only e não foi inferida de sucesso do journal.
- `OnFailure` ativou N2: N50 timer agora `inactive/disabled`, N2 timer `active/enabled` desde 16:01:14. N2 serviço rodou 16:02:00–16:02:04 `Result=success, ExecMainStatus=0`, `research_sample_closed_hour_persisted`, `contracts_at_decision=2`, `requests_attempted=2`, `new_closed_candles=6`, `orders_sent=false`. Próxima janela N2 17:02 UTC. Isso representa **apenas fallback de pesquisa em 2 contratos**, não continuidade Top50.
- A biblioteca atual `bybit_public_j1_transport.classify_provider_retcode(10006)` mapeia para `provider_rate_limit_no_retry`. Os logs comprovam essa categoria, mas não provam que outras aplicações/IP consumiram a quota nem identificam o ativo da quarta requisição. Não inferir nem publicar símbolo/URL.

## Correção de código D311 — controlada e reversível

Um cliente Bybit real inicia hoje GETs com espaçamento **2 segundos** e não repete a requisição que falhou. A classe `BoundedBybitPublicClient` passa a aceitar somente `min_interval_seconds` numérico finito dentro de **2 a 12 segundos**; padrão 2s inalterado. No componente `j1_n50_supervised_once`, **após** opt-ins, owner, integridade do journal e plano UTC aprovados, o writer N50 usa cliente real de **8 segundos** entre GETs quando nenhum cliente foi injetado. Para 50 requisições, isso significa cerca de 392–400 segundos só de espaçamento, dentro da janela limite de 15 minutos; monitorar latências/clock e falhar fechado se o limite expirar. Esse ritmo **não garante** que o provedor concederá quota, sobretudo quando houver tráfego concorrente.

O censo de renovação de universo N50 (até 372 GETs), os coletores N2, os transportes injetados de testes, os controles por hora e a emissão de ordens permanecem **inalterados**. O error `10006` **continua sem retry**; o writer preserva status de erro e dados parciais auditáveis, saída 65 e fallback N2 pelo serviço atual, sem publicação de checkpoint incompleto.

## Validação e limites operacionais

- `tests/test_j1_n50_rate_limit_pacing_d311.py`: relógio monotônico simulado, quatro GETs e 10006 sem retry/símbolos vazados, 8s entre cada GET no boundary real simulado, valor de cadência malicioso/NaN/infinitos rejeitado, opt-ins e auditoria antecedem construção do cliente, cliente injetado não é substituído, falha preserva quatro tentativas e três candles parciais com zero aprovação/ordens. Executar regressões M1/D291/D293/D294, transporte, falha D303, D306, auditor D309 e suíte completa Linux/Windows/Chrome no SHA final.
- **Não é recuperação operacional:** a coorte N50 recém-interrompida ainda exige auditoria forense do `halted_reason`, recibos, último cursor e ponteiro; não reutilizar o script de release D306 pinado ao incidente anterior de 3 checkpoints + 6 parciais. Essa condição NÃO autoriza apagar o novo HALT, reutilizar o claim desta hora, retentar requisição 10006 ou reativar N50 com N2 ativo.
- A PR só deve ser integrada sem deploy após CI e revisão; sua entrada em serviço exige **outro gate root/systemd**, verificação atual de hashes, operador/owner, segurança do journal e rollback para N2. Não realizar nessa PR, nem afirmar que a J1 foi concluída.
- A estratégia definitiva para eliminar a dependência de ~50 GETs REST/h pode usar WebSocket público de candles confirmados + REST incremental para lacunas, já previsto em J1 #429, mas requer testes de reconexão, contiguidade, heartbeat, quorum e replay. É trabalho futuro independente desta mitigação, não uma justificativa para ativar ordens reais.

**D311:** reduzir pressão de quota por requisição somente na coleta N50 incremental, sem alterar contratos financeiros, autorização, persistência ou política de falha segura; classificar sucesso somente por dados realmente observados.
