# J1/D297 — substituição operacional N2→N50 com rollback e owner audit

## Escopo / autorização e gates

Preparação autorizada pela continuidade da J1; a aplicação é uma **operação de release operacional**, nunca executada automaticamente por CI ou merge. CLI `python -m scripts.install_j1_n50_cutover_once` exige usuário root no host `srv1319424`, SHA exato do worktree dedicado, origem oficial e árvore limpa, NTP sincronizado, arquivos das duas unidades N2 com Git blobs pinados, timer N2 `loaded/active/enabled`, serviço N2 `loaded/inactive/static`, nenhuma unidade N50 instalada, diretório privado N50 0700 de propriedade de cia-probe com `lease/` e `epochs/` vazios. Executa auditoria SQLite owner-only de N2 como `cia-probe` via `runuser`, exigindo integridade real, 2 contratos, recibos no máximo 2h antigos, zero trading e manutenção explícita das 21 horas históricas sem checkpoint.

## Duas etapas e falha fechada

A chamada **sem flags de aplicação** faz preflight, renderiza service/timer em memória e retorna `preflight_pass_no_changes`, sem criar unidades e sem tocar N2. A aplicação exige **ambas** `--confirm-controlled-cutover --allow-systemd-modifications`. Escreve as unidades N50 como root 0644 de forma atômica, verifica configuração com `systemd-analyze verify` e carrega unidades. Somente então desabilita e para o timer N2, confirma service N2 inativo e chama o preflight D296 (N2 timer precisa estar `loaded/inactive/disabled`, serviço N2 `loaded/inactive/static|disabled`). Habilita e inicia **apenas o timer N50**, nunca o worker fora da janela UTC; confere o estado final de ambas as unidades. Em qualquer falha após início da mudança, desabilita N50, remove novas unidades, recarrega systemd e restaura N2 ativo/habilitado. Unidades e SQLite N2 são preservados, e nenhuma ordem real é habilitada. Falha no rollback é evidência crítica, nunca informada como PASS.

Os arquivos `deploy/systemd/cia-j1-n50-managed.*.template` são os já integrados D295/D296; esta mudança acrescenta o **executor operacional revisável** em `scripts/install_j1_n50_cutover_once.py`. Exemplo de preflight (somente leitura):

```bash
/usr/bin/python3 -m scripts.install_j1_n50_cutover_once \
  --source /home/cia-probe/agent/j1-n50-managed-d297-code \
  --root /home/cia-probe/agent/j1-n50-managed-d296-private \
  --python /home/cia-probe/agent/ws-venv/bin/python \
  --expected-sha <SHA-EXATO-DE-MAIN>
```

A aplicação é feita só após validação dos gates, mesmos parâmetros e flags finais: `--confirm-controlled-cutover --allow-systemd-modifications`.

## Evidências reais anteriores ao release

- Github CIA `main` em D296: `4f39658ea7537143ad3f70c26d2ba1642cadf139`; worktree separado D296 na VPS criado sem alterar o HEAD D287 do coletor N2; 45 testes N50 no worktree da VPS: PASS.
- Owner-only N2 REST SQLite audit via `cia-probe`: `journal_integrity_verified=true`, `stored_candles=166`, `published_hours=39`, `historical_unpublished_hours=21`, `historical_checkpoint_gaps_present=true`. O gateway MCP atualmente instalado usa auditor antigo e por isso retorna `sqlite_owner_audit_blocked`; não confundir com corrupção.
- N2 continua ativo, timer N50 estava not-found, root privado N50 preparado sem ativação. Não declarar N50 24/7, soak 24h ou rotação real antes de evidência posterior independente.

## Evidência obrigatória pós-ativação

1. Confirmar N2 timer `loaded/inactive/disabled`, N2 service inativo e N50 timer `loaded/active/enabled`, além da unidade N50 instalada e do SHA do worktree.
2. Observar primeiro fechamento N50 após censo no próprio timer, validar 50 contratos, 1.200 candles na primeira hora de writer, +50 por hora seguinte, checkpoints UTC, 0700/0600, 0 ordens e no máximo 50 GETs/h nas horas ordinárias.
3. Acompanhar ≥24 fechamentos e pelo menos uma rotação real >36h, com novo journal e scope e preservação do antigo. Confirmar execução sem terminal, watchdog, recuperação/rollback e auditoria.
4. Sem execução financeira real. CI verde demonstra código, não lucratividade nem disponibilidade contínua.

### Failback automático durante a execução

A unidade N50 instalada por D297 aponta `OnFailure=cia-j1-n50-fallback.service`. A unidade root-only versionada em `deploy/systemd/cia-j1-n50-fallback.service.template` não lê dados, não chama exchange nem habilita trading: desativa o timer N50 e reabilita o timer legado N2 se o worker N50 falhar. O instalador inclui essa terceira unidade no preflight/`systemd-analyze verify` e remove todas no rollback de instalação. Esse mecanismo cobre falha do *serviço* N50, mas **não** é um watchdog de ausência de execuções ou falhas silenciosas com exit 0; o soak 24h continua obrigatório.

### Backup privado antes do cutover

O comando opt-in `python -m scripts.backup_j1_n2_before_cutover --allow-owner-readonly-backup` é executado como **cia-probe** e usa a API SQLite backup com origem exclusivamente `mode=ro` e `query_only=ON`. Grava uma cópia consistente em `/home/cia-probe/agent/j1-n50-managed-d296-private/n2-before-cutover.sqlite`, 0600, somente se o alvo estiver ausente; valida `PRAGMA integrity_check`, contagem de candles/publicações e SHA256, sem imprimir símbolos, valores, SQL ou credenciais. Nunca substitui a cópia existente; arquivos temporários são removidos em caso de falha. Esse backup protege a recuperação, mas é distinto da auditoria causal owner (que continuará sendo gate obrigatório). O cutover não executa backup automaticamente: antes de `--confirm-controlled-cutover`, conferir `backup_verified` e armazenar o digest SHA256 na evidência da issue.

**Fail-closed de janela UTC:** a CLI do timer `scripts.run_j1_n50_managed_once` não trata mais `deferred` como sucesso: retorna exit 65. Assim uma execução tardia de HH:01..HH:15 produz falha do serviço e aciona `OnFailure` restaurando N2; `epoch_started`, `epoch_rotated` e `research_hour_persisted` seguem exit 0. Testes offline `test_j1_n50_managed_cli_failback_d297.py` cobrem esse contrato.


## D298 — correção do preflight observada na VPS

A primeira chamada D297, **sem flags de aplicação**, retornou `status=blocked`, `systemd_modified=false` antes de qualquer tentativa de instalação. Dois detalhes reais foram identificados: venv `bin/python` é symlink para Python 3.12 oficial, e `git -C` executado como root falha pela proteção `safe.directory` em checkout de outro usuário. D298 aprova **apenas** o entrypoint esperado `/home/cia-probe/agent/ws-venv/bin/python` quando resolve estritamente para `/usr/bin/python3.12`, e executa `git rev-parse/status/remote` como `cia-probe` via `runuser`. Não adiciona `safe.directory`, não altera a pasta privada nem desativa proteção. Backup privado do N2 foi criado e verificado antes do preflight, com SHA256 `8eb5d7f82dc9d0fd6ba5d0e26ded37e4b743476f8bc0708e3bb3befaa32cb8a7`, 166 velas e 39 checkpoints; continuar exigindo contagens iguais no momento do cutover. Qualquer drift de horário deve bloquear sem contornar gate.
