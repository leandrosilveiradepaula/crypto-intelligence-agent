# J1/D312 — recuperação do HALT 10006 da epoch ativa, não da antiga

## Incidente verificado e limite

Na VPS em 12/11/2026 16:01 UTC (13:01 BRT), N50 da coorte `epoch-1794492000000` foi interrompido após 4 GETs, 3 candles parciais e categoria exata `provider_rate_limit_no_retry`, exit65. `OnFailure` desativou N50 e restaurou N2 timer ativo com execução 16:02 UTC success0. Nenhum recibo PIT pode ser atribuído ao fechamento interrompido. O código D311 de GET com cadência 8s foi integrado na GitHub main `bfc114e6de6fd869586876aea2df0f6d21a7c961` **mas não está instalado**: o serviço aponta para o worktree owner anterior `/home/cia-probe/agent/j1-n50-d306-main-code`. O módulo D306 de release estava deliberadamente fixado ao HALT histórico `epoch-1794456000000` com 3 checkpoints e 6 parciais; não pode ser reutilizado para este incidente.

## Entregas D312

- `scripts.audit_j1_n50_recovery_candidate_once` é somente leitura, fixo à raiz privada D296 e à epoch corrente esperada `epoch-1794492000000`. Exige `--allow-private-readonly-audit`; sem opt-in nem lê journal. Usa o ponteiro ativo real D294 + auditor D304 (SQL `mode=ro`, `query_only=ON`, checksum e recibos). Valida que a parada foi por `provider_denied_owner_review`, sem gaps de publicação e com **1 a 49 candles parciais**, 1 a 72 checkpoints anteriores e digests imutáveis. Não fixa 3/6 como no evento anterior, nem vaza tickers/turnover, e jamais limpa HALT. Se o evento observado por root tiver divergido dos dados owner, retorna blocked.
- `scripts.release_j1_n50_recovery_10006_once` é candidato **OFF por padrão**. Exige root+host, hora sincronizada, worktree separado com origem GitHub+SHA exato e owner 0700, unit service N50 sha256 instalado `41db7486...`, timer `477ac621...`, fallback `bc6c0c...`, dois N2 units Git blob pinados e estado de failback N2 ON/N50 OFF. Repete auditoria real do N2 (gaps registrados sem preencher) e a prova privada da **epoch ativa atual**. Apenas em preflight reporta `preflight_pass_no_changes` sem systemd/rede/escrita.
- As duas flags separadas `--confirm-recovery-cutover --allow-systemd-modifications` **não são autorização derivada do merge**; elas exigem autorização própria de release de produção e só podem iniciar em HH:01:05–HH:01:50 UTC. Sob gate, desabilita N2 com verificação de isolamento, chama o owner recovery D306 para **censo público único em nova epoch** (até 372 GETs, sem retry para 10006) e compara SHA256 do SQLite+scope HALT antes/depois. Só após sucesso reponta **exclusivamente** `WorkingDirectory` da unidade N50 para worktree Git pinado/limpo, reinicia daemon, confere hash, habilita timer N50 e valida N2 OFF/N50 ON. Não altera timer/fallback/módulo financeiro/ordens.
- Falha antes/durante censo restaura N2. Falha depois de mudar unit tenta restaurar texto original e N2. Saída positiva `rolled_back_to_n2` só quando o rollback confirmou o contrato; caso contrário `CRITICAL_rollback_unverified` e intervenção manual obrigatória. O HALT da epoch antiga continua preservado mesmo se uma nova epoch for selada e o timer falhar.

## Pré-condições e fronteiras

**Sem implantação nesta PR.** O conector MCP permite `systemctl show` e `journalctl`, mas recusa acesso owner `git -C /home/cia-probe/agent/j1-n50-d306-main-code` e execução de `runuser` (DAC). Não contornar proteções. A atualização do worktree owner e o lançamento root da ferramenta exigem executor com permissões operacionais e aprovação do gate de produção aplicável. Nenhum script foi executado nesta sessão.

**Uma recuperação bem-sucedida não fecha a J1**: exige em separado 24 PITs fechados reais, rotação de coorte >=36h, elegibilidade de cripto independente #319, limites reais do provedor e ausência de ordens. O pacing 8s não garante inexistência futura de 10006; fallback N2 permanece.

## Testes/aceite

`tests/test_j1_n50_recovery_10006_d312.py`: opt-in nega leitura owner; proof válida e inválida, pointer antigo rejeitado, SHA digests e partial count arbitrários, N2 rollback após 10006, erro crítico de rollback, root preflight sem escrita, janela UTC. Regressões D304/D306/D311/D299 e suíte Linux/docs Windows/offline Chrome/PAPER no SHA exato; revisão SHA e merge **sem** deploy.

Custo adicional: R$0,00. Sem credenciais/POST, SQL write sobre HALT, trading ou estratégia nova.
