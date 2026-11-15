# D362 — execução isolada do piloto prospectivo J2/J3 (#658)

**Estado:** ferramenta de operação preparada para revisão de código, NÃO instalada nem executada na VPS. Este procedimento não autoriza um release de produção: exige gate próprio e aprovação explícita do Product Owner para a primeira instalação/captura.

## Por que usar executor one-shot

O broker MCP atual tem o serviço *owner sidecar* de J1 e validação do N50, mas **não anuncia uma operação J2**. Tentar ler diretamente o caminho privado do `cia-probe` pelo gateway retorna Permission denied; isso é correto. O piloto seguirá o padrão D359 já auditado: processo de administração da VPS autorizado apenas na fase de release, com `runuser -u cia-probe` para todo acesso privado. A fonte N50 e seus timers continuam independentes.

Script versionado: `deploy/vps/j2_ws_prospective_owner_pilot_d362_once.sh`. Recebe um **SHA40 exato já integrado na main**, hostname `srv1319424`, root real para controle da operação, NTP sincronizado, WS N50/rotador active+enabled, timers REST antigos inativos, Python owner existente. Bloqueia shell arbitrário, timestamps fornecidos para a decisão, parâmetros fora do contrato, symlinks e checkout incompleto/alterado. Todos os subprocessos privados usam UID `cia-probe`. Nenhuma porta aberta, chave de exchange ou operação de trading.

## Operações separadas e gates

- `--preflight-os SHA40`: **somente leitura** do host, unidades, clock e acesso básico do owner. Não cria o checkout de pesquisa e não demonstra ainda a prontidão da epoch 50×24. Pode ser executado pelo broker já autorizado, desde que o operador tenha aprovado o código que irá invocar.
- `--confirm-owner-capture SHA40`: **requer autorização de implantação/captura**, cria uma cópia independente 0700 em `/home/cia-probe/agent/j2-owner-prospective-d362-<sha12>/code` via clone público **pinado**, ou valida a cópia já existente, executa três suítes offline como owner; só então chama o preflight J2 real `preflight` e, se passar, **uma** captura `capture` na janela HH:03–HH:59 UTC. A decisão é armazenada pelo módulo já existente `j2_ws_prospective_ledger.py`, no diretório privado 0700/arquivo 0600, sem sobrescrever registro da mesma hora. Não grava nem altera SQLite N50.
- `--score-once SHA40 H NOTIONAL FEE_IN FEE_OUT SLIP_IN SLIP_OUT`: **com gate apropriado**, usa apenas o checkout pinado e **registro já criado**; verifica epoch e somente avalia velas posteriores fechadas 1/4/8h. Passa explicitamente os cinco custos de pesquisa em unidades cotadas/bps. Todos são **hipotéticos**; não são preços de execução, custos certificados ou PnL realizado. 24h entre coortes não é suportado.

Cada operação emite somente linhas `D362_...` após validação de um JSON privado com allowlist; o corpo original nunca é ecoado. Abstenções não provocam retry automático ou novo GET. A execução de `--score-once` na janela errada **não recupera outro horizonte retrospectivamente**: o motor associa a decisão exatamente ao fechamento `end-atual - H` para não procurar oportunisticamente um acerto favorável.


As linhas de score exibem também **somas agregadas** em bps brutos, após custos *assumidos* e relativo ao BTC, além do total hipotético de custos em quote. Essas somas não são médias por posição nem retornos realizados; só devem ser interpretadas junto do número de observações e da posterior avaliação OOS. O parser rejeita chaves duplicadas e constantes JSON não finitas antes de emitir qualquer resultado.

**Sem autoagendamento nesta entrega**. Após o primeiro piloto e sua avaliação, uma decisão separada poderá autorizar agendamento owner idempotente para coleta recorrente; não criar um segundo coletor nem alterar o WS atual.

## Evidência obrigatória antes de qualquer release

1. Pull request, revisão de diff/cálculo, tests/CI Linux/docs + Windows/offline + Chrome/PAPER verdes no HEAD exato, merge sem produção e SHA integrado registrado.
2. Pré-release: confirmar que não existe outra captura ativa, que os timers N50 e rotação permanecem intactos e que o script aprovado pertence ao SHA pinado. Conferir hora UTC e host. O download do script aprovado deve usar a URL raw GitHub com **commit completo fixo** e verificação sintática `bash -n`, como no padrão D359; não executar `main` mutável sem pin.
3. Autorização explícita de **uma instalação owner isolada + uma captura prospectiva** antes do primeiro `--confirm-owner-capture`. Se houver dúvidas sobre DAC, checkout, NTP, gaps, timer, coorte ou outras operações, abster. Nenhuma necessidade de licença de API paga, autorização de ordens ou migração.
4. Registrar job ID, UTC, SHA, resultado sanitizado de preflight/capture, número de observações e evidência de zero ordens. Só após maturação executar `--score-once` na hora exata; registrar resultados e perdas, sem contaminar pesquisa com conhecimento de futuro.

**Rollback:** não tocar nos timers N50. Não há daemon novo para desabilitar; interromper novas invocações do runner se houver falha e preservar o ledger original/arquivos para auditoria, sem limpar ou retrodatá-los. Se checkout isolado apresentar erro, bloquear execução, preservar provas e preparar correção em nova PR.

**Flag de pesquisa:** J1 D360 = aprovada para seleção técnica e coleta; `prospective_registration_independently_verified=false`, `out_of_sample_results_validated=false`, `financial_backtest_approved=false`, `approved_for_signals=false`, `live_trading_authorized=false`, `marketwide_top50_verified=false`. O SHA local e relógio NTP do host não são testemunha externa do instante de registro.

## Testes offline

`python -m unittest discover -s tests -p test_j2_ws_owner_pilot_d362.py -v`
e regressões `test_j2_ws_owner_preflight.py`, `test_j2_ws_prospective_ledger.py` e `test_j2_n50_ws_private_screen.py`. CI GitHub comprova o contrato de código, não a instalação nem a captura.
