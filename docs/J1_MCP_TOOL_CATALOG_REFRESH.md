# J1 — Ativação das ações MCP no ChatGPT (após instalação aprovada)

Checkpoint comprovado: 10/11/2026 22:59 UTC. Issue de integração: [#532](https://github.com/leandrosilveiradepaula/crypto-intelligence-agent/issues/532). Issue operacional do gateway: [agente-sql-langgraph#224](https://github.com/leandrosilveiradepaula/agente-sql-langgraph/issues/224), fechada após homologação do sidecar.

## Estado observado e escopo

- **VPS/serviços — APROVADO.** Upgrade root-only e versionado de [PR gateway #225](https://github.com/leandrosilveiradepaula/agente-sql-langgraph/pull/225), merge `df56cf2ca22befccfadbe042eb80d41143219ec0`, instalado por operador no host correto. Retornos literais: `CIA_J1_OWNER_UPGRADE=PASS`, `OWNER_SQLITE_AUDIT=PASS`, `FINANCIAL_MODULE_UNCHANGED=true`, `MCP_TUNNEL_ACTIVE=true`, `CIA_COLLECTOR_SQLITE_TIMER_UNCHANGED=true`. Os quatro serviços owner-socket/owner-service/finance-broker/finance-tunnel estavam `active`.
- **Coleta REST — 24/24 APROVADO, somente amostra N=2.** Auditoria independente em 10/11/2026 22:37 UTC: 24 execuções horárias, zero falhas, 48 GETs, 50 candles novos; SQLite `integrity_check=ok`, 100 candles totais, 26 checkpoints, cursores e digests válidos. Apenas dois contratos congelados para pesquisa; não Top50, cobertura 24/7 perpétua, estratégia rentável ou autorização para ordens.
- **ChatGPT — CATALOGO PENDENTE.** Após o upgrade, `mcp_health` do plugin Agente Financeiro VPS respondeu `ok`, `real_sql_execution=false`; `host_status` respondeu normalmente. Porém o catálogo de ferramentas desta sessão ainda só oferece as 11 ações financeiras antigas, sem `cia_j1_rest_timer_status`, `cia_j1_rest_journal_summary` e `cia_j1_rest_sqlite_audit`. Logo o teste ponta a ponta *pelo modelo* ainda não foi realizado. Não é falha de código/DB e não justifica reiniciar a VPS.

## Única ação externa pendente: atualizar lista de ferramentas autorizadas

O ChatGPT pode usar um snapshot previamente aprovado de ações de apps MCP personalizados. Atualizações no servidor **não** atualizam automaticamente as ações autorizadas. Para apps gerenciados em espaços Business/Enterprise/Edu, a documentação oficial orienta o administrador ou proprietário com direito de gestão a:

1. Abrir o **ChatGPT na web**, no espaço de trabalho correto, e acessar **Configurações do espaço de trabalho > Apps** (algumas versões apresentam **Plugins** ou **Console de administração**).
2. Localizar **Agente Financeiro VPS** e abrir o menu **••• > Controle de ações** (ou **Configurar ações** no fluxo de publicação); selecionar **Atualizar/Refresh** para consultar as ferramentas do gateway atual.
3. Conferir e **habilitar apenas** as novas ações sem argumentos: `cia_j1_rest_timer_status`, `cia_j1_rest_journal_summary`, `cia_j1_rest_sqlite_audit`. Não ampliar para shell, SQL genérico, credenciais, ordem ou escrita no banco; preservar as permissões financeiras anteriores. Salvar/publicar conforme o controle do espaço de trabalho.
4. Iniciar uma **nova conversa** (ou recarregar a sessão de app se o produto oferecer) e mencionar/selecionar o app `@Agente Financeiro VPS`. Pedir a chamada das três ações e verificar: timer `status=ok`; journal `status=pass`, 24/24, 50 candles novos, 48 GETs; SQLite `status=pass`, 2 contratos, 100 candles, 26 publicações, integridade/contiguidade/digests verdadeiros e `trading_enabled=false`.
5. Registrar retorno sanitizado na issue #532. **Só fechar #532 quando as três ações estiverem visíveis e tiverem sido chamadas com sucesso a partir do ChatGPT**. Se não aparecer a opção Atualizar, registrar a ausência de permissão/capacidade de gestão: não apagar ou recriar o plugin nem mudar permissões do gateway às cegas.

**Fonte oficial da atualização de ações:** https://help.openai.com/pt-br/articles/12584461-connecting-custom-mcp-servers-in-chatgpt

## Limites e continuidade

O agente ChatGPT atual possui ações para `mcp_health`, `host_status` e funções financeiras, mas **não** uma ação de editar/reconciliar o catálogo MCP de um app já instalado. O painel administrativo exige intervenção com a permissão apropriada. Não invocar `sync_approved_langgraph_main` como substituto; sincronizar o checkout de outro repositório não atualiza o snapshot de ferramentas do produto.

Após liberação dos três nomes no catálogo: repetir auditoria somente leitura pelo plugin e avançar J1 #319 (universo crypto-only) e J1 #429 (coleta supervisionada 24/7). Não iniciar nenhum novo canário REST nem alterar os diretórios/SQLite owner-only. Orçamento adicional: **R$ 0,00**.
