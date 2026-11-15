# J5/PAPER-BACKUP1 — exportar e restaurar cenários PAPER locais (#648)

## Problema corrigido
O app `web/app/index.html` já exportava `cia-j5-paper-local-export-v1` com `simulation_only=true`, `orders_sent=false`, `exported_at` UTC e `state` v1, mas o leitor de JSON só aceitava relatórios N50/J2. Um backup não recuperável não resolve perda/troca de navegador. A restauração agora usa o **mesmo importador local**, sem backend, cookies, storage compartilhado ou troca de schema da posição.

## Contrato de importação fail-closed
1. Máximo **1 MiB**, JSON parseado no navegador. Um backup deve ter **exatamente** `schema_version`, `simulation_only`, `orders_sent`, `exported_at`, `state`.
2. Schema exatamente `cia-j5-paper-local-export-v1`; `simulation_only === true` e `orders_sent === false`. Data UTC ISO canônica com milissegundos e sufixo Z, superior a 2020-01-01 e não mais de cinco minutos no futuro. Não aceita clock injetado do usuário como autorização de mercado.
3. `CIAEngine.validateState` é a verificação numérica/contábil original: conserva quantidades após eventos, alavancagem de abertura imutável, saldos de runner, limites de config e estado apenas PAPER. Chaves extras em state/config/positions/events são recusadas para não transportar segredos, flags de execução ou payloads inesperados ao storage.
4. O contador `nextId` deve ser **maior** que todos os IDs de posições importadas, para impedir reutilização de `SIM-*` na abertura seguinte.
5. O importador faz **validação antes** do diálogo de confirmação. Após validação, o navegador pergunta expressamente se substitui **todos os cenários PAPER locais**. Cancelar/arquivo inválido não modifica `state` nem `localStorage`.
6. Confirmado: substitui o estado em memória sem fazer merge silencioso de posições/eventos, salva com o mesmo `save()`, renderiza; se storage for indisponível, informa que resta apenas a sessão e orienta exportar novamente antes de sair.
7. N50/J2 permanecem apenas na sessão, separados de `state.positions`. Não migra sqlite, não lê DB privado, não cria API, credencial ou ordem. Restore não reativa bot, testnet ou negociação real; `config.paused` restaurada segue apenas a trava de cenário PAPER.

## QA
- No Chromium real em 390px: criar duas posições, alterar alavancagem, pausar/despausar, exportar ZIP? **Não**: arquivo `crypto-intelligence-paper.json` do botão original. Resetar localmente com confirmação, tentar restaurar cancelando (estado permanece vazio), aceitar o backup (duas posições retornam), recarregar e confirmar persistência.
- Forjar `orders_sent=true` e introduzir `unexpected_credentials` em posição: rejeitar sem substituir estado. Contrato de horário, schema e conservação permanece sob teste Python/Node.
- Preço de mark de J5/#646 não entra no backup e volta ao preço fictício de entrada após reload, sem tratar dados de mercado como atuais.
- Executar `tests/test_j5_product_app_mvp.py`, `scripts.audit_j5_product_app_browser`, suite offline e CI 3 jobs (Linux/docs, Windows/offline, PAPER/Chrome) no SHA exato.

## Limites e permissões
Ação de recuperação de um backup de simulação no **próprio navegador do usuário**, condicionada à confirmação individual. Nenhuma perda remota de dados, upload, ordem, exchange, VPS ou migração de produção. O aplicativo continua inteiramente `offline_paper`; a decisão D77 de automação futura continua pendente de J1/J3/J4/J6 e de gates humanos para execução real. Custo adicional R$0.
