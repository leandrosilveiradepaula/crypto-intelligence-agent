# J1/D321 — renovação segura de coorte N50 WS após 36 horas

## Problema e resultado

O instalador D320 (PR #593, main `1089fe2cea6471cad4bfb43386bddb10f3067516`) inicia o N50 WS com um **único** manifesto D287 e cache D316 em caminhos fixos. Ambos têm prazo máximo de 48h e o serviço falha de forma segura quando vencem. Sem renovação, o WS cairia de volta para N2 após dois dias, mesmo sem falhas de rede.

D321 introduz um epoch manager independente para uma próxima versão do serviço, mas **não é aplicado automaticamente à unidade D320 já publicada ou à VPS**.

## Contrato de código

- `j1_n50_ws_epoch_rotation.py`: arquivo privado `active-n50-ws-epoch.json` 0600, estado owner em diretório 0700, no prefixo específico `/home/cia-probe/agent/j1-n50-ws-epochs`. JSON canônico contém apenas caminhos locais, digest de scope, digest de metadata e UTC de ativação, autenticados com SHA-256. Nunca símbolo/vela/payload. Leitura verifica owner/inode/hardlink/symlink, JSON sem duplicados, digest e replay D287+D316 50/50 do **mesmo** epoch, relógio e validade. Escrita usa `flock` owner não bloqueante e `O_EXCL` de temporário 0600, `fsync`, `os.replace` atômico e `fsync` do diretório; nunca sobrepõe arquivos antigos.
- Troca só depois de 36h da última ativação, com NOVOS diretórios owner de manifesto/cache/journal. Sem sobrescrever, reindexar ou migrar o journal WS anterior ou o SQLite REST HALT. Arquivo anterior permanece legível até a troca atômica. Não publica PIT retroativo.
- `scripts.rotate_j1_n50_ws_epoch_once`: execução owner com cinco flags explícitas, cron UTC `HH:02:15`, cheque de idade **antes de qualquer GET**. Se ainda não venceu, retorna `not_due_no_get`. Se venceu, cria claim imutável por epoch **antes** do censo D287; no máximo uma tentativa completa nessa epoch. Captura escopo D287 causal e metadata D314→D316 em diretórios novos; `10006` ou erro de integridade encerra SEM retry e SEM troca de ponteiro, com histórico e N2/serviços intocados. Falha não transforma parcial em coorte ativa.
- `scripts.run_j1_n50_ws_owner_active_once`: nova entrada owner para o timer `HH:59:30`. Resolve e revalida o ponteiro ATIVO antes de abrir factory WS, então chama D317 no journal/escopo apontados. Mantém a API antiga do D320, sem alterar seu `ExecStart` ou seu SHA.
- Templates OFF por padrão: `cia-j1-n50-ws-rotating.service.template` é possível substituto futuro da unit WS estática (mantém nome do serviço somente quando migrada por root gate), `cia-j1-n50-ws-rotate.timer.template` roda HH:02:15, `cia-j1-n50-ws-rotate.service.template` faz o refresh owner. Renderer inerte `render_j1_n50_ws_rotating_systemd.py` valida o prefixo isolado, flags e nomes. `ReadWritePaths` só admite root dedicado de epochs WS, não a raiz REST HALT.

## Limites operacionais

Este bloco NÃO instala nem habilita novas unidades, não modifica D320 ou N2, não se conecta à Bybit durante CI e não executa ordens. **É necessária uma migração root separada com rollback** depois do disparo autorizado D320: criar epoch root 0700 e active pointer owner, migrar service WS fixo para CLI por ponteiro sem perda do journal vigente, instalar timer de rotação e verificar falha segura. Não executar diretamente o template rotativo por cima do D320 de produção.

A coorte D287 ainda requer o censo de 24h fechado e metadados públicos reais, que podem receber `10006`; a rotina não assume que a renovação deu certo sem prova. Com falha persistente, antigo scope vence em 48h, D317 falha e `OnFailure` devolve N2. Renovação automática ainda **não foi homologada** na VPS.

## Aceite de código e evidência

`tests/test_j1_n50_ws_epoch_rotation_d321.py`: arquivos reais 0700/0600, bootstrap ativo 50/50, troca atômica a 36h, recusa a 35h, histórico intacto e digest alterado somente após aprovação, cache adulterado, symlink/ponteiro adulterado, quota D287 sem retry e sem metadata GET, runner que escolhe nova coorte após troca, CLI opt-in ausente bloqueando antes de WS.

`tests/test_j1_n50_ws_rotating_systemd_d321.py`: timer renovação HH:02:15, serviço coleta WS HH:59:30 preservado, nenhum install/systemctl implícito, sem REST antigo, root/path injetado proibido.

Executar Linux/docs, Windows/offline e Chrome/PAPER no SHA final, revisar e integrar sem deploy se verde. Validação 24 fechamentos reais, mudança do universo após >=36h, gaps REST limitados, identidade #319 e primeiro root install D320 permanecem **pendentes e separados**.

Custo adicional R$0,00. Ordens reais zero.
