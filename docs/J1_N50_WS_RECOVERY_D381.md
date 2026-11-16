# J1 / D381 — recuperação transacional do N50 WS após replay D380

## Por que existe
A J1 foi aprovada para **pesquisa histórica** em D360. No dia 16/11/2026,
às 08:00 UTC o novo escopo WS tinha 50/50 fechamentos; às 09:00 UTC os
50 eventos foram persistidos, e um replay posterior gerou
`ws_journal_closed_replay_conflict`. O `OnFailure` desligou
`cia-j1-n50-ws.timer` e `cia-j1-n50-ws-rotate.timer` e reativou o
REST N2; porém o REST retorna `catchup_exceeds_48h_owner_review` sem GET.

A auditoria proprietária somente leitura, sem alterar DAC, confirmou
`EPOCH_VALID=True`, `INTEGRITY_OK=True`, **5 horas com 50 contratos
distintos por hora**, 250 linhas e zero marcadores de lacuna. A mensagem
recusada não foi retida, portanto a sua diferença concreta permanece
desconhecida. D380 melhora o tratamento **somente** de replays econômicos
idênticos com relógios monotônicos, preservando a primeira gravação.

## Executor preparado (NÃO executar sem gate de release)
`deploy/vps/recover_j1_n50_ws_d381_once.sh <SHA40-main-revisado>`
é root-only e falha fechado fora do host `srv1319424`, sem NTP, com
timer/mode inesperado, código antigo alterado ou SHA não presente em
`origin/main`. Requer checkout owner atual `61aead8870166ddbc0b3a4c27d8924e320c477b1`
em diretório pinado D322, unit existente, J2/J3 ainda `not-found`.
Janela de cutover é UTC HH:+03 até HH:+58 (exclusiva).

Antes de tocar timers, o executor faz checkout pinado do novo SHA,
executa regressões com o Python já instalado do owner, revalida a epoch,
executa `scripts.audit_j1_n50_ws_replay_count_d379_once` sobre a
janela real 08h/09h (count-only, `mode=ro`, 50/50 e 0 gap), e valida
as três units com `systemd-analyze verify`. Em falha de testes/preflight,
reverte o checkout. Em falha de cutover, desliga novos timers, para o
serviço WS e restaura REST e checkout antigo. Não cria novas units,
não modifica SQLite, não repete seleção Top50/GET nem envia ordens.

**Prazo da auditoria:** o próprio preflight D379 recusa hora com mais de
48h; após 18/11/2026 09:00 UTC será necessário reavaliar o gate,
nunca relaxar silenciosamente essa janela.

## Evidências a registrar no release autorizado
- Aprovação expressa de release de pesquisa e SHA exato, CI Linux/Windows/Chrome e revisão do script
- Resultado da execução com `D381_OWNER_SQLITE_READONLY_08_09_50_OF_50_PASS` e `D381_RECOVERY_TIMERS_ENABLED_NO_ORDERS`
- Timers N50 WS e rotação `active/enabled`, REST N2 `inactive/disabled`, NTP yes, código owner no SHA aprovado
- Primeiro fechamento futuro `ws_owner_hour_50_observed_local_only` com 50/50 no **novo horário**; se a falha persistir, observar o fallback e não fingir continuidade
- REST fallback original não é prova de recuperação enquanto `catchup_exceeds_48h_owner_review` persistir

## Limites
A ativação recorrente J2/J3 continua um release **distinto**; código J2/J3
não é instalado por este script. Nenhum sistema de ordens reais, live
ou testnet, migração, API paga, mudança de exposição ou ROI autorizado.
Não classificar replay sem diferença econômica como fato retrospectivo:
o frame recusado da hora 09:00 não foi armazenado.
