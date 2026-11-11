# J1 / D283 — substituir agendamento finito por timer REST recorrente

Data da auditoria: **11/11/2026, 14:47–14:49 UTC**. Issues #429, #319, #2. Objetivo: remover a causa do timer sem próximo disparo **sem criar coletor, banco ou serviço novo**.

## Diagnóstico comprovado no host

No servidor VPS existente, somente leitura:

- \`systemctl show cia-j1-rest-hourly.timer\`: \`LoadState=loaded\`, \`ActiveState=active\`, \`SubState=elapsed\`, \`UnitFileState=enabled\`, \`NextElapseUSecRealtime\` vazio, \`LastTriggerUSec=2026-11-10 18:02:00 UTC\`. A aparência **active/enabled** não significa agenda futura.
- O arquivo real \`/etc/systemd/system/cia-j1-rest-hourly.timer\` contém **24 linhas fixas** \`OnCalendar=...\`, de 2026-11-09 19:02 UTC até 2026-11-10 18:02 UTC. Depois da 24ª execução, não existe mais agendamento. Não é falha do cursor REST.
- O arquivo *já versionado* \`deploy/systemd/cia-j1-rest-hourly.timer.template\` contém **uma linha recorrente**: \`OnCalendar=*-*-* *:02:00 UTC\`, \`AccuracySec=1s\`, \`RandomizedDelaySec=0\`, \`Persistent=false\`, mesmo \`Unit=cia-j1-rest-hourly.service\`. \`systemd-analyze calendar\` confirmou normalização, sem ambiguidade.
- O serviço instalado é o M1 existente, \`oneshot\`, \`User=cia-probe\`, \`max-assets=2\`, \`ProtectSystem=strict\`, \`ReadWritePaths\` só do journal \`/home/cia-probe/agent/j1-rest-m3-20261109/canary\`. Não converter estes 2 contratos de pesquisa para Top50 sem gate de produto e evidências.
- O ensaio finito 24/24 OK e SQLite íntegro com 100 candles e 26 publicações foram confirmados por auditoria MCP fixa; nenhuma nova execução, serviço ou timer foi iniciada durante o diagnóstico.
- \`python -m scripts.audit_j1_rest_resume_readiness --output-directory /home/cia-probe/agent/j1-rest-m3-20261109/canary --allow-private-readonly-audit\`, pelo owner \`cia-probe\`, confirmou \`status=catchup_with_unobserved_hours_requires_review\`, \`catchup_hours=21\`, \`unobserved_closed_hours=20\`, \`historical_unpublished_hours=1\`, \`journal_integrity_verified=true\`, \`catchup_within_worker_limit=true\`, \`activation_authorized=false\`. Os tempos são do instante da auditoria: **revalidar antes de qualquer ação**.
- NTP host = \`yes\`; checkout privado no SHA \`1633d6596fd5ab6df0ec11fdaa237ba409ee2025\` após merge D282, 20 testes J1 automáticos OK. Nenhuma ordem ou gasto.

## Entrega de código

\`crypto_intelligence_agent/j1_rest_recurring_plan.py\` verifica **exatamente** as 24 datas horárias UTC consecutivas HH:02 do timer finito instalado, que estejam encerradas. Compara todas as demais diretivas do timer contra o modelo versionado. O serviço instalado tem de coincidir integralmente com a renderização \`scripts.render_j1_rest_hourly_timer.render\`. Reusa auditoria owner-only \`j1_rest_resume_readiness\` e reconstrói o cálculo UTC da próxima decisão, horas de catch-up e histórico não publicado. FALHA se houver qualquer drift de unit, relógio/cursor, latch, >48h, dado inválido ou identidade de serviço diferente. Não acessa rede ou banco por escrita.

\`scripts.audit_j1_rest_recurring_timer\` é CLI **somente leitura**, inativa sem \`--allow-private-readonly-audit\`. Nunca executa \`systemctl\`, modifica \`/etc/systemd\`, habilita timer, inicia serviço, faz GET ou escreve no SQLite. Saída privada sanitizada: resultado \`recurring_unit_verified_pending_operational_gate\` significa que somente o **diff** e o **preflight** são válidos, **não** autoriza instalar. Campos \`activation_authorized=false\`, \`timer_activated=false\` e \`marketwide_top50_verified=false\` permanentes.

Os testes \`tests/test_j1_rest_recurring_timer.py\` incluem 24 datas, duas datas repetidas, data inválida HH:03, opção de serviço alterada, \`Persistent=true\`, comando de execução alterado, leitura sem opt-in, 21/49 horas de catch-up, estado halted, mismatch do relógio e ausência de ativação.

## Sem automatismo de produção: sequência proposta, somente após gate

Esta PR **não** executa estes comandos nem os disponibiliza por CI. O operador de produção autorizado precisa estabelecer gate explícito de ativação da coleta recorrente, com revisão do estado do journal no instante de execução e decisão sobre as 20 horas não observadas. Revalidar SHA da \`main\`, CI, checkout limpo, NTP, usuário/owner, arquivo unit e SQLite; **não** iniciar se \`catchup_hours > 48\`, SQLite corrompido, provider latch ou versão do serviço diferente. Se o gap ultrapassar 48h, resolver a recuperação por fluxo separado, nunca zerar o DB, inventar PIT ou ampliar o limite do worker.

Após gate e preflight repetidos, a mudança mínima é substituir **apenas** o arquivo \`/etc/systemd/system/cia-j1-rest-hourly.timer\` pelo conteúdo **exato** de \`deploy/systemd/cia-j1-rest-hourly.timer.template\` do SHA aprovado; preservar backup 0600/owner root do timer finito fora do unit search path. Não mudar \`.service\`, \`ExecStart\`, \`max-assets\`, \`ReadWritePaths\`, SQLite, secrets ou qualquer arquivo de fonte. Recarregar apenas o gerenciador de unidades \`systemctl daemon-reload\` e reiniciar **só** o \`.timer\`, não disparar manualmente o \`.service\`. Revalidar \`SubState=waiting\`, \`NextElapseUSecRealtime\` futuro, \`UnitFileState=enabled\`, depois acompanhar dois ou mais fechamentos reais e auditoria do journal/cursor. Em falha, restaurar backup e \`daemon-reload\`; não apagar candles gravados.

O M1 pode buscar candles fechados faltantes (<=48h) na janela HH:01–HH:15, mas **não** cria publicações PIT dos horários perdidos. Preservar \`historical_unpublished_hours=1\` como evidência explícita; o resultado de um único catch-up não é prova de 24/7. Falhas provider permanentes são latched; outras falhas ficam visíveis como service failure, sem retry imediato. \`Persistent=false\` evita disparos extras fora da janela após reboot.

## Próximo gate e evidência necessária

1. CI do SHA head da PR: Linux/docs, Windows/offline, Chrome/PAPER, revisão e merge seguro **sem deploy**.
2. Prova owner da nova CLI read-only na VPS com SHA final; usar saída sanitizada, zero GET/SQLite writes.
3. **Somente após gate de instalação de produção** e verificação fresh (<48h), fazer a substituição recorrente controlada, sem alterar o worker/DB; auditar os próximos fechamentos. Se o período necessário para autorização estourar 48h, reavaliar plano de catch-up.
4. Questão separada: ampliar universo de 2 contratos de pesquisa para 370 candidatos/Top50 **corrente** com elegibilidade/PIT. Isso não se resolve simplesmente instalando timer e não é uma permissão de trading.


### Regressão adicional de recuperação realista

`tests/test_j1_rest_incremental_owner.py` agora cobre explicitamente 21h de atraso entre dois `published_hour`: 42 velas adicionais para 2 contratos, apenas **um** checkpoint novo na retomada (não 20 checkpoints fictícios), 0 GET na repetição do mesmo fechamento e preservação da integridade SQLite. Um gap de 49h falha **antes de qualquer GET**, preservando as velas e publicações anteriores. São fixtures offline e não autorizam colocar em produção.
