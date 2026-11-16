# J1 D384 — corrigir estado `failed` do systemd antes do coletor WS

## Falha observada em 16/11/2026, após recuperação D381

O Product Owner aplicou D381 com sucesso no SHA owner
`507e698bcf7ffbf55afd5b30bfa5a9f1e6ee900f` e habilitou
`cia-j1-n50-ws.timer` e rotação. **Às 13:59:30 UTC**, o `ExecStartPre`
de `cia-j1-n50-ws.service` retornou `status=blocked` e exit 65.
O OnFailure restaurou o timer REST N2 e desabilitou ambos os WS.
Não houve tentativa de coletar as 50 novas velas e não houve ordem.

**Causa específica comprovada:** o preflight D295 exige
`cia-j1-rest-hourly.service ActiveState=inactive`, enquanto D381
considerou `failed` (serviço já parado) aceitável para o próprio
cutover. O N2 tinha `ActiveState=failed`, `MainPID=0` e
`ControlPID=0`. A unidade antiga
`cia-j1-n50-managed.service` também estava `failed`, mas o
preflight D318 já admite `failed` nesse caso. Assim, D381 reabilitou
o WS sem limpar o estado `failed` do N2. O programa interrompeu a
coleta corretamente; **não é uma nova falha de candles nem prova de
replay conflitante**.

REST às 14:02 e 15:02 UTC continuou abstendo, com
`catchup_exceeds_48h_owner_review`, 0 GET, exit 65. Portanto a J1
histórica D360 continua aprovada para pesquisa, mas coleta recorrente
ainda não recuperada. Não refazer ranking/histórico ou relaxar guardas.

## Correção mínima D384 — código versionado, ainda não aplicado

`deploy/vps/recover_j1_n50_ws_d384_failed_state_once.sh`:
1. Preflight root host específico, NTP, SHA owner exato, checkout
   clean, units carregadas, timers e serviços nos estados esperados,
   sem processos em execução, e janela segura HH:+03 a HH:+58 UTC.
2. Com rollback armado, desabilitar N2.timer, executar
   `systemctl reset-failed` **somente** nas três units de serviço
   quiescentes (N2, N50 REST antigo e WS), exigir `inactive`/PID=0.
3. Executar o **preflight original não modificado** D318 com identidade
   `cia-probe` e exigir o relatório `old_collectors_quiesced_preflight_only`.
4. Reativar os timers WS e rotação existentes e verificar
   `active/enabled`; N2.timer permanece `inactive/disabled`.
5. Em qualquer falha, parar/recuperar o estado seguro REST N2 e
   registrar retorno. Nenhum checkout novo na VPS, nenhum journal
   mutado, nenhuma migration, nenhum processo J2/J3.

A auditoria read-only owner job
`e9e4959c6caa456dae58067894f6b68f` após a falha retornou
`active_n50_ws_epoch_revalidated` com exit code 0. Isso confirma
que o ponteiro da coorte está elegível; não comprova nova vela.

## Gates e critérios de encerramento

**A criação/merge desta PR não aciona sistema em produção.**
Antes de executar D384 no host: CI Linux/Windows/Chrome no SHA exato,
revisão de preflight e rollback e **gate de release de serviços
operacionais** com autorização correspondente. A autorização passada
para executar exatamente D381 não prova autorização automática de
qualquer outra implantação. Executar somente em janela segura.

Após aplicação: conferir owner HEAD, NTP, `systemctl show`, journal de
ExecStartPre e **um novo fechamento 50/50 realmente observado** com
`ws_owner_hour_50_observed_local_only`, `orders_sent=false` e
sem novo rollback. Um timer habilitado isoladamente não encerra #671.

A falha de fallback REST por catch-up >48h é limitação separada e não
deve ser escondida aumentando um limite de backfill.
