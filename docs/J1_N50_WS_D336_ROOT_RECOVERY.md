# J1/D336 — recuperação do N50 WS após correção D335 (operador root, reversível)

## Estado verificado — 13/11/2026
O D333 produziu a primeira hora real N50 50/50 às 16:01:58 UTC. A segunda sessão 16:59:30–17:02:00 UTC gravou 50 eventos fechados, mas terminou `ws_owner_hour_audit_abstain` com 0 contratos atestados, exit65. `OnFailure` restaurou REST N2 `active/enabled`; WS e rotação ficaram `inactive/disabled`. Zero ordens e zero GET nessa sessão; não afirmar duas horas homologadas.

O código D335 (PR #620, commit `b20758c91fa94881ddcba9ec130d91bdf508076a`) limita budget nominal de sessão a +105s pósclose, preservando 15s antes do limite D313 de +120s. É hipótese focal para o problema de deadline; o instante exato do auditor na falha não foi conservado e causalidade exclusiva segue não demonstrada.

## Solução D336
`deploy/vps/recover_j1_n50_ws_d336_once.sh` é novo entrypoint de recuperação root, **não reexecutar D333**. Reutiliza a transação e compensação D333 sem criar nova coorte, modificar journal SQLite, alterar systemd units, autenticar conta, consultar exchanges ou enviar ordens.

Pré-condições checadas no host:
- root no `srv1319424`, NTP sincronizado, Python owner existente, checkout owner-only regular e limpo dentro do path D322 esperado;
- checkout atual **exatamente D333** `76ba09735b46e19e1e0af718c420d6a60cdd0067`; origem HTTPS esperada;
- N2 timer active/enabled, WS/rotação inactive/disabled, serviço WS inativo/falho e owned por `cia-probe`, serviços de fallback e REST antigo no estado seguro;
- execução fora de minutos UTC 00:00–02:59 e 58:00–59:59 (janela de fechamento/rotação), checada **antes do fetch** e imediatamente antes do cutover;
- SHA novo completo, revisado e existente em `origin/main`; revalidar endereço dos arquivos, margem D335 literal, regressões owner/local D326–D332 e D313/D315/D317, e ponteiro privado D321 com TTL.

A auditoria D332 de *mismatch* de base USDT de 1 caractere não é refeita: já foi o gate causal do D333; repetição não diagnostica o deadline D335. Revalidação privada do ponteiro e dos contratos permanece, sem imprimir símbolos.

## Operação e retorno
Código só muda via `git checkout --detach` do SHA revisado, com trap registrado **antes** da primeira alteração. N2 continua ativo durante checkout, regressões e auditoria do ponteiro. Somente depois dos gates, quiesce N2 e habilita timers WS+rotação. Se qualquer etapa falhar antes da conclusão, o trap devolve o HEAD anterior; em erro de cutover, desabilita WS/rotação e para serviço WS antes de reabilitar N2. Confirma estado esperado; falha de compensação retorna 75 e exige operador. Não remover nem sobrescrever journal, pasta HALT ou manifests.

**Gate de publicação em VPS:** PR revisada, CI Linux/docs, Windows/offline e PAPER/mobile no SHA final, merge seguro sem deploy, então a execução root de um script pinado ao commit exato da `main` é ato operacional separado. Não usar broker MCP com permissões insuficientes para contornar isolamento privado. A execução root só deve reportar marcadores e estados sanitizados. Checar após a próxima hora `confirmed_contracts=50`, `missing_contracts=0` e digest real; até isso acontecer, D335 não é sucesso operacional.

Mesmo com próxima hora positiva, continuam pendentes D323 24h de 50/50, rotação >=36h, crypto-only #319 e J1 #2. Custo R$ 0,00.
