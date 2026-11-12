# J1/D322 — instalação única do N50 WS com rotação automática de 36h

## Objetivo: eliminar uma segunda intervenção SSH

A implantação D320/PR #593 era de uma coorte estática. D321/PR #594
introduziu ponteiro imutável e renovação a partir de 36h, mas o instalador
corrigido `prepare_install_j1_n50_ws_d321_once.sh` ainda montaria um
serviço com caminhos fixos. D322 integra as duas partes em **uma única
instalação root**: bootstrap com D321, instalação WS D318 às 59:30 e
timer rotativo às 01:15. Não faz deploy automático por merge nem executa
ordens.

## Caminho de execução (código, não realizado na VPS)

`deploy/vps/prepare_install_j1_n50_ws_rotating_d322_once.sh <SHA40>`
requer SSH root no host `srv1319424`, NTP sincronizado e N2 timer
ativo. Cria novo checkout GitHub no SHA exato como `cia-probe` (0700),
sem alterar o trabalho antigo. Cria root privado dedicado
`/home/cia-probe/agent/j1-n50-ws-epochs` (0700) e subdir `active`.

Espera a janela **HH:01:15–HH:01:30 UTC** (exigida por D286:
início HH:01:00–HH:02:00), verifica N2 service inactive, e executa
`scripts.rotate_j1_n50_ws_epoch_once` para capturar a coorte D287
fresca, obter metadata D314 em cache privado D316, validar 50 e
escrever o ponteiro ativo SHA256 de forma atômica. Qualquer `10006`,
falha de GET, horário errado, não-censo, falta de permissão ou cache
inconsistente encerra **antes de alterar systemd ou o N2**. Claim
imutável impede retry de provedor naquela epoch.

O módulo root `scripts.release_j1_n50_ws_rotating_once` é OFF por padrão
e exige as **duas flags explícitas** `--confirm-rotating-ws-cutover` e
`--allow-systemd-modifications`. Primeiro verifica snapshot ativo
D321 owner, diretórios 0700, cache D316 revalidado pelo owner, SHA exato
do checkout e Git origin, NTP, cinco hashes de units N2/N50 REST
instaladas (auditoria real do broker 12/11/2026 UTC), estado
`N2 active/enabled`, N50 REST `inactive/disabled` e cinco unidades
novas ausentes.

Somente depois do PASS cria cinco units novas via O_EXCL com 0644,
`daemon-reload`, valida carregamento, desabilita N2 reversivelmente
e habilita os dois timers WS. São elas:

1. `cia-j1-n50-ws.service`: **entrada WS via ponteiro ativo**, D317,
   abre socket público só sob owner flags e com 50 contratos confirmados.
   Não usa caminhos estáticos D320.
2. `cia-j1-n50-ws.timer`: HH:59:30 UTC, 30s antes de cada fechamento.
3. `cia-j1-n50-ws-fallback.service`: desabilita ambos os timers WS
   e restaura N2, sem restaurar o velho N50 REST.
4. `cia-j1-n50-ws-rotate.service`: owner D321, só tenta renovar após
   >=36h, com claim único antes de qualquer GET, nova coorte/journal
   isolados, troca atômica, sem restart/retry.
5. `cia-j1-n50-ws-rotate.timer`: HH:01:15 UTC, verifica elegibilidade
   a cada hora, sem GET se não estiver na hora de trocar.

Caso qualquer etapa **após começar a desabilitar N2** falhe, root
desabilita os dois timers WS e reabilita N2; `OnFailure` do WS faz
o mesmo. Os journals antigos permanecem intactos, incluindo os
1.203 candles/1 PIT/3 parciais preservados da epoch REST HALT.

## Fronteira de aceitação e segurança

- Nenhum dos scripts é executado por GitHub CI ou pelo broker VPS; o
  broker atual **não tem DAC/systemd nem pode `runuser`**.
- Criar unit e enfileirar timer não é coleta homologada: primeira prova
  de 50/50 vem do fechamento real subsequente; 24 fechamentos e rotação
  depois de 36h só podem ser atestados na VPS.
- A rotação de D321 tem exatamente uma tentativa por coorte; falha
  de provedor mantém a antiga coorte até 48h, quando fail-close + N2
  são as condições corretas. NÃO repetir GET até novo gate.
- REST para lacunas com quota/proveniência separado; #319
  elegibilidade crypto-only global pendente. Sem ordens reais, custo
  adicional R$0.
- **Substitui os comandos root antigos D320 (HH02:15 incorreto) e D321
  (instala WS estático)**; publicar nova URL SHA fixo e checksum
  somente após CI/review/merge D322. Não executar nenhum dos anteriores.

## Testes e evidência de código

`tests/test_j1_n50_ws_rotating_release_d322.py` cobre default
inócuo, preflight privado fail-closed, cinco units novas, sequência
reversível N2→WS→rotação, restauração N2 após falha parcial do disable
N2 ou enable de qualquer timer, fallback que desativa os dois timers,
horário D286/D318, isolamentos, sem ordens e sintaxe Bash. Exigir
Linux/docs, Windows/offline, Chrome/PAPER verdes no HEAD final exato
e revisão/merge seguro sem deploy.

O estado operacional deve manter explícito que **a VPS não foi alterada**
nesta PR. O comando único fora do broker só será solicitado quando
o operador estiver com SSH disponível.
