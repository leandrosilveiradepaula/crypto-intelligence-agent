# D441 — piloto público Bybit de BTCUSDT isolado da J1

Esta entrega substitui o piloto D438 e o gate J1 do operador D439. **J1 permanece aceita para pesquisa no escopo D360 e não será reiniciada, auditada ou alterada para testar o canal público J2.**

## Fluxo autorizado para pesquisa, sem ordens

1. No host root real `srv1319424`, executar o operador versionado `deploy/vps/j2_public_kline_owner_d439_once.sh --preflight SHA40`: exige host, relógio NTP, `runuser` do owner `cia-probe`, Python e `websockets.sync.client`. Nenhuma leitura J1, REST, WSS, instalação ou escrita no preflight.
2. Verificar pessoalmente elegibilidade regional, termos de dados e pesquisa read-only. Somente depois preencher quatro confirmações operacionais para `--capture`: `CIA_D439_CONFIRM_PERSONAL_RESEARCH=YES`, `CIA_D439_CONFIRM_REGION_ELIGIBLE=YES`, `CIA_D439_CONFIRM_DATA_RIGHTS=YES`, `CIA_D439_CONFIRM_PUBLIC_WS=YES`.
3. O operador cria **um diretório novo** com owner 0700 em `/home/cia-probe/agent/j2-d439-public-XXXXXXXX`, baixa o SHA fixado em checkout separado e valida o HEAD. Não altera `/home/cia-probe/agent/repo` nem o estado privado J1.
4. O launcher D437 confere owner, opt-ins, diretório de pesquisa privado e orçamento; faz **um único GET público HTTPS** à API Bybit `instruments-info?category=linear&symbol=BTCUSDT&limit=1`, reutilizando `BoundedBybitPublicClient` para TLS, redirecionamentos, cotas e limite de resposta. O contrato BTCUSDT deve ser `LinearPerpetual`, `Trading`, USDT/USDT, base BTC explicitamente para este piloto BTCUSDT, timestamps atuais, sem pré-listagem ou TradFi. O fingerprint da sessão **não é** um registro independente de identidade cripto.
5. Somente depois do REST válido, inicia um WebSocket público `linear` `kline.60.BTCUSDT`, uma sessão por 240s/24.000 frames, journal SQLite isolado e projeção local terminal. ACK, atualização aberta, close confirmado e falha são reportados separadamente. **Uma janela de quatro minutos pode não alcançar o close horário: ACK/open já são evidências limitadas, nunca inventar close.**

## Limites e interpretações

- Nenhuma leitura ou escrita na J1, nenhum Top50, nenhum ranking N50 novo, nenhuma alteração de timers/systemd, nenhuma credencial ou ordem real.
- O escopo é **apenas BTCUSDT**, não o feed de 50 ativos. A prova pública é um marco de transporte, não prova de cobertura de mercado ou desempenho, nem fonte autenticada, direitos de uso ou operação PAPER.
- `--state-directory`, `--scope-file` e `--allow-private-pointer-read` são parâmetros legados recusados antes de rede. O parser de manifesto D437 só existe para testes offline, nunca para construir a sessão real.
- `D439_BLOCKED=...` encerra o processo sem execução pública. Qualquer erro REST ou clock gera abstenção, não fallback para arquivo J1 nem fixture.
- O conector VPS limitado não consegue trocar usuário (`runuser: cannot set groups`); o preflight deve ser feito no shell root do host real. O teste anterior que dependia de J1 **não deve ser repetido**.
- A transição futura para feed contínuo N50 e PAPER exige avaliação própria; não substituir a J1 por um piloto nem publicar dados financeiros.

Veja o runbook `docs/J2_D439_OWNER_PILOT_RUNBOOK.md`, as decisões D383/D436/D437/D441 e issue #677.
