# J1 / D281 — cruzamento automático retrospectivo de Bybit USDT com D256/D264

Data: 2026-11-11. Relacionado a #319 e #2. Continuação de D279/D280.

## Evidência operacional de D280, na VPS existente

- Repo VPS \`/home/cia-probe/agent/repo\` atualizado em fast-forward, checkout limpo de \`eca44e212d2cc85597d5affdc13d6800f68b46f1\` até \`72f6ec7cfab1ad7f343ee37d850bb4fb7e1417e0\`; 15 testes unitários \`test_j1_auto_*.py\` OK.
- Um GET público GET-only Bybit em 11/11/2026, \`scripts.scan_j1_auto_usdt_perps_once\`, retornou \`status=automatic_usdt_perpetual_research_candidates_only\`, 930 linhas, 1 página, **370 candidatos provisórios**, exclusões: 108 outros produtos, 388 marcadores TradFi, 25 negativos documentados, 39 ambíguos/malformados, 0 nomes TradFi adicionais. Hash público do conjunto \`115eb222184de24706f585143d343d9064d52f2d2e0e329de45730e37c231c96\`, observado \`1794406882373\` ms. \`requests_attempted=1\`, sem writes, credenciais ou ordens. Não confundir \`network_requests=0\` do **classificador puro** com o 1 GET do wrapper.
- Banco D256 \`j1-marketwide-closed24h.sqlite\` e snapshot privado D264 já presentes, arquivos owner 0600, diretório owner 0700; **não** foram alterados nem reiniciados. O censo REST N=2 24/24 é outro banco, diferente do D256.
- Catálogo de 11/11 não é snapshot PIT de 06/11 nem 370 identidades positivas de cripto. Top50 de mercado não homologado.

## Implementação D281

A função \`reconcile_auto_pool_with_private_census(pool, directory, ...)\` é **read-only**, owner-only POSIX e opt-in. Reutiliza bloqueio compartilhado flock, SQLite \`mode=ro\`, \`PRAGMA query_only\`, \`PRAGMA integrity_check\`, replay byte/linha D256 \`_replay\` e validação imutável D264 \`_load_private\`. Não constrói outro coletor ou registro manual.

- Aplica negativa conhecida do snapshot D264 ao **pool atual** de pesquisa, mesmo se o provider tiver removido depois o marcador.
- Cruza os candidatos com o escopo congelado D256 e as 24h de turnovers USDT já auditadas; séries ausentes ou curtas são incompletas, não recebem zero. Reusa \`rank_auto_candidates_closed24h_offline\` D279 e hash determinístico.
- Expõe contagens e digests por padrão: candidatos atuais, interseção histórica, ausentes, veto D264 e quantidade de Top50 retrospectivo.
- Em qualquer falha de integridade, opt-in ou clock, abstém e não despeja símbolos, valores, caminhos ou corpos de respostas.
- Nenhum ranking é apresentado como mercado **atual**, PIT retroativo, identidade cripto verificada, sinal operacional ou permissão para trade.

A CLI existente \`scripts.scan_j1_auto_usdt_perps_once\` ganha parâmetros opcionais \`--private-directory\` e \`--allow-private-readonly-audit\`. Se fornecidos, executa a junção em memória no mesmo **único** GET de catálogo, sem criar snapshot ou escrever no banco. Caso a junção falhe, o resultado externo é \`abstain\`.

## Gates de aceite

CI Linux, Windows/offline e Chrome/PAPER no SHA final da PR, revisão do conjunto de arquivos, squash merge seguro sem deploy. Depois, atualizar VPS com SHA exato, executar testes específicos, verificar modo owner/lock e fazer **uma** prova GET-only/read-only da junção. O número de 50 ranqueados é um resultado retrospectivo de candidatos técnicos, **nunca** confirmação de que os 50 contratos são criptos ou que o histórico foi coletado continuamente.
