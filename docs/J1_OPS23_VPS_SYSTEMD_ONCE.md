# J1/OPS23 — VPS systemd one-shot sem repetir sondagens

Status: **código e unidades desativados por padrão**; nenhum deploy ou ativação na VPS.
Implementação ligada à issue #466, investigação OPS22 #464 e coletor contínuo OPS1 #429.

## Decisão e por quê

A janela UTC para uma vela fechada deve ser supervisionada pelo sistema operacional da VPS, não pela conversa ou por comentários GitHub Actions. O GitHub permanece responsável por código, CI e revisão. O timer systemd é de **uma data UTC exata**, não cron horário: a pessoa responsável por liberar uma prova seleciona o fechamento futuro e o SHA aprovado.

Este bloco implementa apenas a prova limitada OPS22: BTCUSDT WebSocket público (90 segundos/256 frames) e **até um GET** REST histórico da mesma Bybit. Acordo de seis campos não homologa o feed nem permite gravar candles, acionar sinal ou negociar. Não instala nem habilita o coletor J1 24/7 existente.

## Guardas do lançador

1. Timer absoluto 15 minutos antes do fechamento UTC; \`AccuracySec=1s\`, \`RandomizedDelaySec=0\`, \`Persistent=false\` e \`Restart=no\`. Se o servidor voltar depois, não recuperar janela.
2. Lançador só funciona nos primeiros 15 segundos após o horário programado, exige \`timedatectl ... NTPSynchronized=yes\`, processo POSIX não-root, checkout no SHA exato e \`git status --porcelain\` vazio.
3. Diretório de estado **pré-criado** pelo proprietário, fora do checkout, modo \`0700\`, sem symlinks. Arquivo \`ops22-one-shot-attempt.claim\` nasce com criação atômica exclusiva \`O_EXCL\`, modo \`0600\`, e sincronização em disco **antes** de qualquer conexão. Serviço iniciado outra vez abstém sem recriar conexão.
4. O wait interno existente só aceita início a 30 segundos do fechamento UTC com tolerância de 5 segundos e limite de espera de 20 minutos. Verificação adicional de NTP imediatamente antes da prova.
5. A sonda OPS22 mantém limites de uma assinatura WS, no máximo um GET, timeout REST 8 s / corpo 32 KiB, sem retry, sem credenciais/ordens, sem persistência e com relatório sanitizado. O wrapper não imprime stdout/stderr do filho, nem caminhos/valores/segredos, mesmo se ele falhar.
6. Se a hora passar, NTP falhar, SHA/árvore divergirem, diretório faltar, marker existir, a espera falhar, WS/REST abster-se ou JSON final não for seguro, o resultado é abstenção. **Nenhum retry automático**. O marker não é apagado após falha; uma tentativa futura precisa de novo fluxo revisado e novo estado isolado.
7. A prova é experimental e **não** é o serviço contínuo. O serviço já esboçado em \`cia-j1-ws-owner.service.template\` segue OFF por padrão. Não operar simultaneamente até verificar exclusão de escritores.

## Preparação offline para conferência (não instala nada)

Após merge da PR e revisão independente do SHA, um operador autorizado pode gerar apenas texto com:

\`\`\`sh
python3 -m scripts.render_j1_ops23_timer \
  --owner cia-probe \
  --target-utc 2026-11-04T16:00:00Z \
  --expected-sha <SHA40_CONFERIDO> \
  --repo-root /home/cia-probe/agent/repo \
  --python-bin /home/cia-probe/agent/ws-venv/bin/python \
  --state-dir /home/cia-probe/agent/ops23-claims
\`\`\`

O alvo acima é **exemplo**, não agendamento ativo; o \`SHA40_CONFERIDO\` é placeholder inválido até ser substituído por commit real aprovado. A saída contém \`cia-j1-ops22-once.service\` e \`cia-j1-ops22-once.timer\` como duas seções textuais. Nunca canalizar essa saída diretamente para um caminho de serviço; revisar e salvar as unidades separadamente.

Antes de eventual deploy (gate separado) verificar: identidade da VPS, serviço legado ativo, disponibilidade do venv e libs, \`git rev-parse HEAD\`, árvore limpa, relógio UTC/NTP, espaço, quota Bybit, permissões da pasta 0700, ausência de marker prévio, cronologia do alvo e risco de duplicidade com workflows GitHub. Não alterar/limpar SQLite anterior nem executar como root.

## Homologação futura na VPS — exige gate de ativação

Somente após autorização aplicável, preparar usuário owner e pasta privada fora do checkout, instalar unidades revisadas em local apropriado, \`systemd-analyze verify\` nos dois arquivos renderizados, \`systemd-analyze calendar\` na data exata, \`systemctl daemon-reload\` e habilitar **apenas o timer único**. Verificar \`systemctl list-timers\`, depois \`systemctl status cia-j1-ops22-once.service\`, \`journalctl -u cia-j1-ops22-once.service\` e conteúdo do marker sem divulgar dados financeiros. Não usar \`systemctl start\` manual fora da janela; falhas são terminais. O timer deve ser desativado após o teste. Nenhuma dessas ações foi executada nesta implementação.

## Evidência de teste

Testes \`tests/test_j1_ops23_once_timer.py\` cobrem data UTC absoluta, calendário inválido, atraso de janela, NTP antes/depois da espera, SHA/árvore, permissão, symlink, execução concorrente/duplicada via \`O_EXCL\`, espera falha, JSON inseguro, resultado que abstém, paths maliciosos e não recorrência do template. Testes POSIX são ignorados no Windows; os testes puros rodam nas duas plataformas. GitHub CI precisa executar Linux/docs, Windows/offline, Chrome/PAPER no SHA exato, com nova verificação pós-merge.

**Limites:** code/CI verde não prova VPS operacional, uptime, fonte autenticada, Top50 marketwide, 24h, rentabilidade ou segurança em 50x. O experimento ainda depende de uma execução real na rede da VPS, mediante gate distinto.
