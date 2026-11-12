# J1/D295 — systemd N50 preparado, DESLIGADO até gate de release

## Motivo

A prova real D289 incluiu dois fechamentos horários de 50 contratos e 1.250 velas. D290–D294 implementaram supervisão, recuperação de falhas intra-hora, lock global entre censo e writer e renovação causal de cohorts. Falta instalar um agendamento na VPS para coletar continuamente, mas o timer antigo N2 segue ativo e **não participa** da lease D293. Uma instalação N50 simultânea ao N2 poderia ultrapassar o orçamento agregado de GETs e interferir em um serviço que já funciona.

## Assets versionados OFF por padrão

- `deploy/systemd/cia-j1-n50-managed.service.template`: service oneshot com `User=@OWNER@` não-root, diretório de código, root privado de dados com `ReadWritePaths`, sandbox, UMask 0077, timeout 900s, sem restart automático, e ExecStart que chama **somente** `scripts.run_j1_n50_managed_once` (D294).
- `deploy/systemd/cia-j1-n50-managed.timer.template`: recurring UTC HH:01:05, `Persistent=false`, jitter zero, para permitir ~12m de censo dentro de HH:15. Este horário foi escolhido após prova real D287 21:01:05–21:13:28; não é garantia futura de deadline.
- `scripts.preflight_j1_n50_systemd_isolation`: **read-only** e fail-closed. Exige `ActiveState=inactive` em **ambos** `cia-j1-rest-hourly.timer` e `cia-j1-rest-hourly.service`, com `systemctl show` literal, timeout de 3s; erro/permissão/unknown/failed/active não passa. ExecStartPre é condição indispensável, mas não autoriza ativação por si.
- `scripts.render_j1_n50_managed_systemd`: só renderiza texto com validação de owner e paths seguros, **não instala, copia, habilita, inicia ou modifica** nenhuma unidade.

## Gate operacional separado

Nenhuma mudança systemd, migração, credencial, dado D256/D264 ou ordem é feita por esta PR. Um futuro **release de produção** requer autorização aplicável e execução controlada com rollback:
1. Confirmar HEAD SHA do GitHub, CI Linux/Windows/PAPER, owner da VPS, relógio UTC/NTP, root 0700 preparado com `lease/` e `epochs/`, Python/repositório corretos e histórico N2 íntegro.
2. Avaliar parada **reversível** do timer N2 no instante adequado antes de habilitar N50; não apagar N2 journal, preservar unidade e plano de restauração. O preflight N50 só permite execução quando N2 timer **e** serviço estão inativos, para evitar concorrência e quota.
3. Renderizar e revisar o diff exato do service/timer N50 com caminhos reais e proprietário não-root. Instalar somente sob gate, verificar timeout, recência, 50 contratos, exclusão global, logs sanitizados, recuperação e recorrência.
4. Acompanhar no mínimo 24 fechamentos UTC consecutivos e passagem de uma rotação >36h com nova coorte; preservar lacunas PIT quando existirem. Se ocorrer erro, bloquear coleta N50 e voltar ao estado anterior conforme rollback aprovado, sem ordenar trades.

**Limite:** nem CI verde nem template versionado demonstram serviço N50 24/7, identidade independente ou Top50 global elegível. Não sugerir ativar N50 com N2 ativo. Sem operações financeiras reais.


## D296 — cutover à prova de reboot: N2 deve estar DESABILITADO e INATIVO

Auditoria operacional read-only de 12/11/2026 (UTC): `cia-j1-rest-hourly.timer` apresentou `LoadState=loaded`, `ActiveState=active`, `UnitFileState=enabled`; `cia-j1-rest-hourly.service` apresentou `LoadState=loaded`, `ActiveState=inactive`, `UnitFileState=static`. A consulta ao timer N50 revelou `LoadState=not-found`; portanto **o novo serviço não foi instalado**. O N2 não foi interrompido e reportou último status de serviço com sucesso. Métricas sanitizadas mostraram 24/24 execuções esperadas do coletor N2. A auditoria SQLite read-only retornou `sqlite_owner_audit_blocked`; a causa e integridade completa do banco NÃO foram diagnosticadas por esse endpoint.

Falha de segurança corrigida: o gate D295 original verificava apenas `ActiveState=inactive`. Isso poderia permitir iniciar N50 se N2 timer estivesse **enabled porém parado**, reiniciando no próximo boot. D296 exige ainda `LoadState=loaded` em ambas as unidades e `UnitFileState=disabled` no timer N2; service N2 só pode ser `static` ou `disabled` e `inactive`. Saída ausente, duplicada, malformada, unidade ausente ou `active` bloqueia. Esse gate continua read-only e não executa `disable` nem `start`, tampouco equivale à autorização de produção. Um release posterior deve registrar o estado original, fazer parada reversível **apenas depois de autorização**, validar os três campos, instalar N50 sob gate e verificar o rollback (reativar N2 caso falhe).
