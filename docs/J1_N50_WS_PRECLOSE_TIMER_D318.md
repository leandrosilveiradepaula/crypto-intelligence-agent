# J1/D318 — N50 WebSocket antes da virada UTC (HH:59:30)

## Decisão e mudança pontual

O timer N50 atualmente **instalado** (`cia-j1-n50-managed.timer`) é
REST-only, inicia em `HH:01:05 UTC` e chama
`scripts.run_j1_n50_managed_once`. **Não** antecipá-lo para `HH:59:30`:
isso dispararia REST antes do fechamento, contrariando o contrato de vela
fechada e sem resolver o retCode `10006`.

O D317 `run_cached_n50_ws_owner_window` já exige iniciar entre 10 e 60
segundos ANTES do fechamento da próxima hora. D318 cria o timer
**específico do N50 WS** com `OnCalendar=*-*-* *:59:30 UTC`, 30 segundos
antes da virada, `AccuracySec=1s`, `RandomizedDelaySec=0`,
`Persistent=false` e `Unit=cia-j1-n50-ws.service`.
O agendamento foi validado na VPS pelo comando read-only
`systemd-analyze calendar '*-*-* *:59:30 UTC'`, que normalizou a forma
e informou próxima execução às 19:59:30 UTC de 12/11/2026.

## Serviço conectado ao WebSocket correto

`cia-j1-n50-ws.service.template` chama **somente**
`scripts.run_j1_n50_ws_owner_cached_once` com diretórios parametrizados:
código revisado, manifesto privado D287 existente e cache/journal WS privado
D316/D317 em pasta NOVA 0700 do owner `cia-probe`. A unidade é oneshot
sem restart, timeout 210s, sandbox read-only no home e escrita APENAS no
diretório WS. Nunca aponta ao journal REST HALT D296, nunca compra APIs,
executa ordens ou habilita negociação.

A etapa `scripts.preflight_j1_n50_ws_systemd` lê `systemctl show` e
recusa iniciar WS se o timer/serviço N2 não estão quiescidos, ou se o
antigo timer N50 REST está habilitado/rodando (aceita unit REST service
failed depois do HALT, mas não running). Não executa `systemctl` de
escrita. A recuperação `cia-j1-n50-ws-fallback.service.template`
desabilita o novo timer WS e restaura o timer N2 se a lease WS falhar;
não apaga histórico nem reativa REST N50.

## Realidade da implantação

Os três templates e o renderer são **código sem instalação**:
`scripts.render_j1_n50_ws_systemd.render_n50_ws_systemd` valida o
owner, caminhos, separação do diretório REST HALT, conteúdo/horário do
timer, pontos de invocação e fallback, sem tocar na VPS. A unit REST N50
antiga conserva `HH:01:05`, porém continua disabled. O N2 ativo não
pode ser automaticamente desligado por CI/merge.

A **ativação do novo timer WS** somente faz sentido depois que:
- novo checkout owner no SHA exato D318 estiver instalado sem tocar no
  checkout antigo REST HALT;
- manifesto D287 corrente e metadados D314 já forem capturados e
  cacheados em WS D316 com permissões 0700/0600, coorte de 50 intacta;
- preflight confirmar timer N2 disabled, serviço N2 parado e N50 REST
  antigo disabled; release root e rollback estiverem pinados e aprovados.

Instalação/enable do sistema, quiescer N2 e abrir a sessão WebSocket
pública de forma recorrente são operações de produção separadas deste
merge. **Não habilitar o novo timer hoje usando o checkout REST antigo**.
Nenhum timer foi alterado na VPS nesta entrega. No último estado lido,
N2 active/waiting/success e N50 REST inactive/disabled.

## Qualidade e encerramento do bloqueio

`tests/test_j1_n50_ws_preclose_timer_d318.py` confirma calendar WS,
separação do REST às HH:01:05, ExecStart WS verdadeiro, a recuperação
N2, renderização inerte, root/paths inseguros rejeitados, N2 ativo e
old N50 enabled negados por preflight, stdout sanitizado.
Executar Linux/docs, Windows/offline, Chrome/PAPER SHA final + revisão
antes do merge. Isso não demonstra 24h reais de coleta, 36h de rotação,
recuperação por REST em lacunas ou ranking marketwide independente
(issue #319). Essas evidências requerem operar o serviço real depois
do gate e manter o N2 como fallback. Custo extra R$0; ordens zero.
