# J1 D268 — preparação para instalação supervisionada do WS, sem ativação

## Diagnóstico comprovado

A VPS `srv1319424` executou D267 em 09/11/2026: 9/9 testes PASS, `WS_JOURNAL_NOT_FOUND` na árvore pesquisada do agente (repo e venv excluídos), `service_load_state=not-found`, `service_active_state=inactive`, `operational_blocker=service_uninstalled`, `ws_private_status=unavailable`. **Não existe evidência de unidade instalada ou 24h de journal WS real nessa árvore.** Os 819 históricos 24h D265 são de **REST** e não substituem o banco WS. Nenhuma operação nova em mercado, escrita ou trade foi executada pelo diagnóstico. A issue #521 foi encerrada; #429, #319 e #2 permanecem abertas.

O produto ainda não tem Top50 crypto-only PIT autenticado; o coletor WS codificado atualmente opera um escopo revisado de até 52 bases históricas, expira o escopo aos 48h e não possui prova de renovação segura contínua. Portanto **não instalar 24/7 como serviço "pronto" sem resolver a renovação de identidade/epoch**. O template systemd versionado é OFF por default.

## Pré-voo D268: somente leitura

`scripts.preflight_j1_ws_installation` aceita:
- `--private-directory` caminho futuro de um journal WS separado do REST/repo/venv;
- `--expected-sha` commit imutável validado;
- `--allow-readonly-preflight` flag explicitamente exigida.

Gates: UID=EUID POSIX não-root; caminho absoluto sob `/home/cia-probe/agent/`, sem `..`, symlinks nos ancestrais verificáveis, writer isolado; diretório existente precisa ser proprietário do operador e 0700, ausente é pendência de provisionamento, **não cria diretório**. Só leitura do interpreter, repo, SHA local limpo por `git rev-parse HEAD` e `git status --porcelain`, template renderizado em memória via `render_j1_ws_service` e unidade fixa do `systemctl show` (até 3 s). Contrato de sandbox: `NoNewPrivileges=true`, `ProtectSystem=strict`, `ReadWritePaths` isolado, `UMask=0077`, `RestartPreventExitStatus=64 65 66 77 130`, teto do service; proíbe comandos adicionais de sistema. Apenas um resumo de flags e bloqueador é impresso, sem caminhos, PID, símbolos, payloads, credenciais ou dados financeiros.

Resultados possíveis: `existing_service_requires_review`, `repo_not_at_expected_sha`, `private_directory_requires_owner_provisioning`, `separate_activation_gate_required` ou `abstain` para entrada/ambiente inválido. **Mesmo o último estado NÃO autoriza a instalação**, apenas indica que o checklist local está pronto para a decisão operacional separada. `deployment_authorized=false`, `service_activated=false`, `continuous_collector_verified=false`, `marketwide_top50_verified=false`, `network_requests=0`, `orders_sent=false` em todos os cenários.

## Limites reais antes de operação contínua

1. Obter escopo crypto-only causal atual e crosswalk de identidade versionado com prova independente (#319). O histórico de 52 não é allowlist de mercado.
2. Revisar renovação de escopo a cada 48h, compatibilidade de epochs e garantia de não perder velas durante transições; `Restart=always` apenas reinicia leases transitórios e não prova isso.
3. Manter quota do provedor fail-stop em `10006`, 403, 429 e integridade; validar limites de restart e quarentena.
4. Definir diretório WS real, propriedade, journaling, uso de disco, backups, reversão de unidade, rede pública, despesas R$0 e supervisão/alertas. Esses passos podem exigir gate de implantação e execução pelo operador na VPS.
5. Somente depois considerar a instalação/ativação *deliberada* sob autorização explícita; teste software e renderização não implicam deploy.

## Validação e uso

Testes `tests/test_j1_ws_installation_preflight.py` simulam unit instalada/ausente, path dentro de repo/venv, hash incorreto, working tree suja, missing dir, modo preparado, alterações maliciosas do template, no-optin (nenhum I/O). Windows exercita validação pura sem acesso à VPS; Linux cobre o pré-voo do proprietário em fixtures. CI Linux/docs Windows/offline Chrome/PAPER no head final antes de merge sem deploy.

Após merge sem deploy, com SHA real e checkout `main` limpo, um operador poderá executar SOMENTE o diagnóstico (não a ativação), usando o diretório WS ainda não criado como caminho planejado:

```bash
/home/cia-probe/agent/ws-venv/bin/python -m scripts.preflight_j1_ws_installation \
  --private-directory /home/cia-probe/agent/ws-owner-private \
  --expected-sha SHA_MERGE_EXATO \
  --allow-readonly-preflight
```

**Nenhum** `mkdir`, `systemctl daemon-reload`, `systemctl start/enable`, WS/REST GET, migration, ordens, chaves ou custo está embutido. Se `abstain`, não contornar com flags novas. A falta de journal e serviço é um diagnóstico legítimo e não deve ser mascarada.
