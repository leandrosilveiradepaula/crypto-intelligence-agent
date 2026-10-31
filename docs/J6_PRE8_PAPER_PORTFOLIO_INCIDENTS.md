# J6/PRE8 #403 — auditoria em lote de incidentes PAPER

## Problema e contrato

O observador PRE6 de uma única posição é rigoroso, mas repetir N leituras não produz uma observação da carteira no mesmo checkpoint. PRE8 reutiliza `inspect_paper_positions` para inspecionar **1–128 IDs de posição escolhidos explicitamente** em um único snapshot AUTO4 validado por `mode=ro` e `query_only`. A classificação foi extraída para `classify_inspected_paper_runner_incident`: função pura sobre um `PaperPositionInspection` já verificado, também reutilizada por PRE6. RUNNER2 continua opcional **apenas na API de posição única**; não há alegação de atomicidade entre arquivos.

`audit_selected_paper_portfolio_incidents(position_journal_path, position_ids, *, as_of_ms, max_checkpoint_age_ms, opening_order_path=None)` exige um cutoff UTC explícito e idade máxima de 1–604800000 ms (sete dias). IDs devem ser distintos, sem enumeração implícita ou wildcard. A seleção é imutável e sua ordem é conservada. Quando `opening_order_path` é fornecido, o auditor usa o cross-check AUTO2/AUTO4 existente (incluindo releitura para detectar drift observado). Uma falha em qualquer linha, versão, digest ou cross-check bloqueia o lote inteiro, sem retornar estados parciais ou dados privados.

Uma posição com checkpoint futuro ou antigo em relação ao cutoff é `BLOCKED` com `INSUFFICIENT_EVIDENCE` e `causal_fresh_checkpoint` ausente; não é falsa saúde operacional. A validação de frescor é **por posição**. Não há relógio do host, loop contínuo, timer, daemon ou cron.

## Relatórios

`paper_portfolio_incidents_v1` conserva só ordinal 1..N, código, severidade, checkpoint, necessidade de reconciliação e unidades de **cada posição**, sempre sem somá-las entre BTC, ETH ou outros instrumentos. A severidade global é o maior entre INFO, REVIEW e BLOCKED; um lote não validado tem `batch_block_code=INVALID_OR_INCONSISTENT_SELECTED_JOURNALS`, zero slots e `same_auto4_snapshot=false`. Todos os campos de segurança permanecem falsos: `orders_sent`, `native_stop_verified`, `live_trading_authorized`, `approved_for_live_use`, `financial_pnl_available`, `exchange_reconciliation_confirmed` e `portfolio_financial_totals_available`. Não existem preços mark, IDs de posições, símbolos, caminhos, credenciais ou PnL no JSON.

CLI: `python -m scripts.audit_selected_paper_portfolio_incidents --position-journal EXISTENTE --position-id ID --position-id ID2 --as-of-ms UTC_MS --max-checkpoint-age-ms 10000`. Opção `--opening-order-journal` exige um arquivo existente. O script só imprime JSON sanitizado e não aceita opções de trading.

## Validação e limitações

`tests/test_paper_portfolio_incident_audit.py` cobre mistura de dois instrumentos, contrato PRE6, dois tipos de severidade, UNKNOWN, cutoff futuro/stale, digest de um membro corrompido, AUTO2/AUTO4 ausente, seleção duplicada/fora do limite, Windows, snapshot sem mutação, ausência de rede e stdout seguro. Rodar regressão PRE6/PRE7 e toda a CI docs/Linux, Windows/offline, Chrome/PAPER no SHA final. Integrar somente se gates estiverem verdes e revisão de contratos concluída.

**Não é autorização para abertura/fechamento PAPER, nem execução de trading.** Não monitora feed prospectivo, não observa conta, não sincroniza exchanges, não garante consistência de STOP de corretora, não calcula exposição/PnL ou risco financeiro e não libera J1/J6. J1/Top50 owner-run na VPS permanece adiado pelo PO. Sem credentials, rede, migrations, produção ou gastos adicionais.
