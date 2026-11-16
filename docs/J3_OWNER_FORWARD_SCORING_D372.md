# J3/OPS-FORWARD1 #667 — candidato de avaliação horária 1/4/8h

## Objetivo verificável

A primeira captura real da J2 D364 (03:00 UTC 16/11/2026) registrou uma
decisão com **zero oportunidades**. Um score 1h único está pré-agendado no
job VPS `b8671bba364948c385e129d0009f38d3`; esta PR não o executa
novamente nem declara resultado antecipadamente.

A J2 #663 já possui **código de captura horária**, mas o agendamento
não foi liberado nem instalado. Para usar esse eventual histórico, a J3
precisa avaliar de forma causal, sem escolher retrospectivamente trades que
deram certo e sem preencher horas faltantes com zero de lucro.

## Código proposto, exclusivamente offline

- `scripts/run_j3_ws_owner_forward_tick_once.py`: uma avaliação de
  pesquisa por hora do relógio **real**, como UID POSIX não root, janela
  UTC HH:17..HH:24 exclusiva. Requer três opt-ins de leitura e plano
  explícito de `ForwardCostAssumptions` existente, sem API externa.
  Faz preflight privado N50 50×24 sobre a epoch ativa, depois chama
  `score_owner_ws_decision_once` já existente para **1, 4 e 8 horas**
  a partir do fechamento *atual* (um único snapshot temporal por tick).
  O motor owner valida registro ex-ante, hash local, coorte, barras fechadas,
  custos e fonte; não gera sinais, posições, fills ou ordens. A cada prazo,
  devolve `reference_marks_scored_hypothetical_only`,
  `no_observations_selected` ou `abstained`, sempre **sanitizado**
  e sem nomes/preços. O validador usa um conjunto **exato** de campos para cada relatório de score; campos extras (inclusive possíveis símbolos/segredos) invalidam a avaliação, não são expostos. Se alguma decisão estiver ausente ou a coorte
  tiver girado, não há retorno inventado. Se o relógio mudar durante
  os três scorers, descarta todos os resultados do tick.
- `scripts/render_j3_ws_forward_score_timer_once.py`: só imprime
  candidatos de unit `cia-j3-owner-forward.service/.timer` para SHA40
  já validado. *Não instala, não executa, não habilita*. Janela proposta
  `OnCalendar=*-*-* *:17:00 UTC`, `Persistent=false`,
  `User=cia-probe`, `ProtectSystem=strict`,
  `ProtectHome=read-only`, `PrivateNetwork=yes` e **nenhum**
  `ReadWritePaths`. Exemplo **hipotético** de notional e bps
  para research: 100 unidades cotadas; fee 4/6, slip adverso 2/3.
  NÃO são custos comprovados da exchange. O plano é configurável na
  CLI por parâmetros validados, e eventual unit precisa de nova decisão.

## Gate operacional separado

O Product Owner aprovou somente **uma** instalação/captura prospectiva
D364 em 15/11/2026, não timers recorrentes de score. Antes de qualquer
release: CI 3/3, code review, `systemd-analyze verify` de arquivos
candidatos em fixture e auditoria do owner sandbox; NTP=sim,
N50+rotação ativos, coorte auditada, DAC preservado e rollback desabilitando
somente units J2/J3 novas. Sem migrar banco, abrir porta, criar ordem
real/testnet, declarar vantagem estatística ou publicar scores privados.
R$0 adicional.

## Critérios de validação

`python -m unittest discover -s tests -p test_j3_ws_owner_forward_tick.py -v`.
Testar 1/4/8h, abstenção por ausência de arquivo, meta/coorte alterados,
resultados artificiais, marca futura, flags de negociação true, hora fora
de janela, drift, zero candidatos (nenhum PnL), taxas/NaN, UID root,
nenhuma reexecução/backfill e output count-only. A PR não comprova
amostra OOS, liquidação, spread nem rentabilidade.
