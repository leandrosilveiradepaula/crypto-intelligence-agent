# J2/OPS-RECURRENT1 #663 — candidato de monitoramento prospectivo horário

## Código preparado — NÃO instalado nem habilitado na VPS

A J1/N50 continua coletando 50 perpétuos e girando epochs de forma independente. A J2 já registrou a **primeira decisão prospectiva real** (D364) em 16/11/2026 03:00 UTC com **zero candidatos**. O job posterior de score 1h `b8671bba364948c385e129d0009f38d3` foi agendado como one-shot; não é coleta recorrente.

Para construir um histórico de oportunidades verdadeiramente observadas *antes* dos resultados, o projeto acrescenta dois componentes offline, dependentes de novo gate de release:

1. `scripts/run_j2_ws_owner_recurring_once.py`: uma tentativa única por disparo do timer — nunca um loop. Exige POSIX usuário não root, UID/GID real=efetivo, **três opt-ins explícitos** de pesquisa, janela UTC **HH:07:00 inclusivo até HH:13:00 exclusivo**; chama preflight J2 de mesma epoch 50×24, e só se pronto invoca a função owner de captura já existente. O ledger tem não sobrescrita de hora e grava 0600 em diretório 0700. Reexecução da mesma hora retorna `owner_hour_idempotent_no_new_record` sem novo registro. Ausência de dados, rotação, clock drift ou falha retorna abstenção e nunca tenta outra hora.
2. `scripts/render_j2_ws_prospective_timer_once.py`: produz por stdout o candidato `cia-j2-owner-prospective.service` ou `.timer` de um SHA40 **já mergeado**. É um renderer puramente offline, não grava units, não cria timers. O plano utiliza `OnCalendar=*-*-* *:07:00 UTC`, `Persistent=false`, `User=cia-probe`, checkout isolado pinado `.../j2-owner-prospective-d362-<sha12>/code`, `PrivateNetwork=yes`, `NoNewPrivileges=yes`, `ProtectSystem=strict`, `ProtectHome=read-only`, `ReadWritePaths` apenas no ledger J2, timeout 180s. Diretório private ledger deverá existir antes de instalar a unit, com owner 0700 e sem symlink. A pré-instalação deverá verificar execução real do preflight no contexto sandboxed; não remover proteção de rede para corrigir erro de DAC. Serviços N50/rotação existentes intocados.

## Gates para operação futura

Uma **autorização específica** será necessária para instalar/ativar esse novo agendamento. A autorização anterior cobriu uma instalação e uma captura, **não** futuras capturas ou timers. Antes de qualquer release: CI 3/3 no head exato, revisão de unit com `systemd-analyze verify` em fixture e teste owner em sandbox isolado, timer N50+rotação intactos, NTP `yes`, sem operações concorrentes e rollback do novo timer. Sem replicar SQL de coleta; não criar GET, ordens, acesso a corretora ou armazenamento externo.

Após liberação, cada tick poderá resultar em 0–10 candidatos, inclusive zero: isso é observação legítima, não lucro. O score 1/4/8h necessita mecanismo separado de observação futura, cuja política deve evitar lacunas e censura de coorte; este PR **não** o instala. Métricas OOS e vantagens estatísticas requerem amostra suficientemente longa e custos verificáveis. Em qualquer falha, **abster e preservar** o ledger. Nenhuma promessa de retorno ou habilitação de sinais.

## Testes

`python -m unittest discover -s tests -p test_j2_ws_owner_recurring.py -v`; regressões `test_j2_ws_owner_preflight.py`, `test_j2_ws_prospective_ledger.py`, `test_j2_ws_owner_pilot_d362.py`; CI Linux/docs, Windows/offline e Chrome/PAPER. Testar rejeição de produção indevida, relógio, duplicação, coorte, flags e saída sanitizada sem símbolos/preços.
