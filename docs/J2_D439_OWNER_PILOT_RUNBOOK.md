# D439 revisado pela D441 — execução host de pesquisa BTCUSDT independente da J1

**O operador anterior que exigia `OWNER_J1_EPOCH_REVALIDATION` foi substituído. Não repetir o preflight antigo nem diagnosticar o ponteiro da J1.**

## Pré-verificação sem rede e sem escrita

Em terminal root real de `srv1319424`, verificar SHA completo da branch PR draft #734 no GitHub; baixar `deploy/vps/j2_public_kline_owner_d439_once.sh` por URL raw pinada no SHA e conferir o SHA-256 do conteúdo conferido pelo revisor. Executar `bash -n` e `bash SCRIPT --preflight SHA40`. O script valida host, owner `cia-probe` não-root, NTP, Python e biblioteca WebSocket. Não toca em J1 e não abre REST/WS.

Esperado: `D439_HOST_PREFLIGHT=PASS_NO_NETWORK_NO_WRITES` e `D439_PUBLIC_WS=NOT_STARTED`. Qualquer `D439_BLOCKED=` significa **parar** até resolver o gate concreto de host. Evitar compartilhar dados privados no chat.

## Captura finita opt-in

Somente depois do preflight e de confirmar pessoalmente os termos, direitos dos dados e elegibilidade regional para pesquisa, preencher quatro variáveis de ambiente (`CIA_D439_CONFIRM_PERSONAL_RESEARCH`, `CIA_D439_CONFIRM_REGION_ELIGIBLE`, `CIA_D439_CONFIRM_DATA_RIGHTS`, `CIA_D439_CONFIRM_PUBLIC_WS`) com `YES`, e rodar `bash SCRIPT --capture SHA40` no host root. Não presumir elegibilidade nem contornar controles geográficos.

O operador executa o Python de rede como `cia-probe` com checkout SHA pinado em um diretório owner novo. Um único GET HTTPS público consulta BTCUSDT instrumento/perpétuo; após validação, uma única sessão WS linear finita subscreve `kline.60.BTCUSDT`. Journal separado e só saída sanitizada (ACK/open/closed/abstenção). Sem side effects J1, serviço, timer, autenticação, PAPER ou ordem.

Um fechamento confirmado só pode ser declarado se realmente observado. Se terminar antes da virada de hora, pode reportar apenas ACK/atualizações abertas. Não confundir protocolo funcionando com produto N50 contínuo ou estratégia homologada.

## Estado e próximo passo

Pré-verificação D439 anterior falhou em leitura J1 por dependência introduzida indevidamente; esta falha **não prova defeito da J1**. A versão revisada remove totalmente o gate. A execução pública revisada ainda exige validação CI do SHA exato e preflight no host. O diagnóstico D440 anterior não é requisito de execução e foi retirado da branch (histórico preservado no Git).
