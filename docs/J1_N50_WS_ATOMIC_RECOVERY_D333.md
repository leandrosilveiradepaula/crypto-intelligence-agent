# J1/D333 — recuperação transacional do WS N50 e compensação de código

## Incidente e bloqueio corrigido

Após D331 13/11/2026 14:59:31–15:00:03 UTC, o WS encerrou `exit65` após 42 fechamentos, com `failure_category=ws_scope_member_invalid`. O fallback N2 foi bem-sucedido, e a VPS permaneceu com D331 pinada em `c1fbd4cd46bba108be14859b9a04bb4184c3e91f`, timers WS/rotação desativados e N2 ativo. A D332 em `main=de26e3afb43fe4813ca66cc6dbf08c541e19526d` corrigiu gramática de base USDT curta no parser e no SQLite e acrescentou um auditor owner-only da coorte privada que veta ativação quando a hipótese não for confirmada. **D332 foi integrada ao GitHub, mas nunca implantada na VPS nesse checkpoint.**

Uma falha no fluxo D332, anterior ao corte para WS, deixaria o checkout em `NEW_SHA` e o N2 ativo; o próximo recovery ainda exigiria `OLD_SHA`, criando bloqueio operacional secundário. O problema é **consistência de release e reentrância**, não alegação de que os 42 candles eram inválidos.

## Solução D333

`deploy/vps/recover_j1_n50_ws_d333_once.sh` substitui o entrypoint root D332 **sem duplicar instalações**. O `OLD_SHA` permanece o D331 realmente instalado. O novo SHA deve ser o commit revisado e integrado à `main`. O código de D332, sete suítes e auditor de gramática são reutilizados, sem mudança em dados financeiros, cadeia N50, ranking, parser, SQLite, indicadores ou cron.

A transação contém três flags internas:

- `PIN_CHANGED`: ajustada **antes** de tentar o `git checkout --detach NEW_SHA`, para cobrir até falha parcial. Em saída não finalizada, o trap restaura `OLD_SHA` e verifica tanto o SHA quanto a árvore limpa.
- `CUTOVER_STARTED`: ativada antes de mudar qualquer estado de serviço. Se a operação falhar, o N2 é reabilitado, os timers WS e rotação são desabilitados e esses estados são conferidos; só depois o pin antigo é restaurado.
- `RECOVERY_FINALIZED`: marcada **somente após** sucesso do cutover e verificação do estado esperado. Nesse único caso, preserva `NEW_SHA` e WS/rotação ativos com N2 disabled.

O trap `EXIT` é instalado **antes** do primeiro comando de `git fetch/checkout`, preserva o código de saída original quando a compensação tem êxito e retorna **75 com marcador `D333_RECOVERY_COMPENSATION_REQUIRES_OPERATOR`** se não puder confirmar o retorno seguro. `HUP`, `INT` e `TERM` acionam a mesma compensação. Nunca imprimir OHLC, símbolos da coorte, paths owner privados ou segredos no relatório do auditor.

## Critérios e regressões

`tests/test_j1_n50_ws_atomic_recovery_d333.py` verifica o pin antigo, o conjunto de sete suítes D332/D331/D329–D326 e o preflight owner D321/D316 **antes de desabilitar N2**; testa com subprocesso Bash isolado e mocks (nenhum systemctl, runuser ou git real) os cenários:

| Cenário sintético | Resultado exigido |
| --- | --- |
| owner audit D332 abstém após checkout | pin antigo verificado, N2 intacto, exit65 |
| cutover parcial falha | N2 restaurado, timers WS/rot desativados, pin antigo restaurado, exit65 |
| sucesso completo | pin novo mantido, sem compensação, exit0 |
| checkout antigo não recuperável | sinalização operador, exit75 |
| restauração N2 não verificada | sinalização operador, exit75 |
| erro antes do primeiro checkout | sem alteração de pin, retorno do erro original |

O script segue exigindo root somente na VPS `srv1319424`, Git limpo e pinado, N2 active/enabled, WS/rotação disabled, NTP sincronizado, auditor privado com opt-ins, **zero novo bootstrap D322/372 GET**, nenhuma migration SQLite, ordem real, preço ou derivativo enviado a exchange. O rollback de pin não remove linhas dos journals WS, que permanecem intactas.

**Gates:** CI Linux/docs e Windows/offline, Chrome/PAPER no HEAD exato, revisão e merge sem deploy. Só depois execução root em gate operacional específico, sem driblar a restrição do broker remoto. Em caso de `legacy_mismatch_not_established_abstain`, parar com N2 e pin antigo restaurados: a hipótese sobre o frame privado não foi provada. Em caso de preflight verdadeiro e sucesso de cutover, acompanhar primeiro lease para 50/50; J1 D323 24h, rotação 36h, identidade #319 e J1 #2 permanecem pendentes. R$ 0,00 adicional.
