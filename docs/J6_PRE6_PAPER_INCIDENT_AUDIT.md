# J6/PRE6 #399 — auditoria de incidentes do runner PAPER

`audit_paper_runner_incident` lê exclusivamente um AUTO4 existente e uma posição `fixture_...` explicitamente indicada. RUNNER2 é opcional, mas quando selecionado exige caminho, política e cutoff UTC completos. O CLI `python -m scripts.audit_paper_runner_incident` só emite JSON sanitizado; não aceita destino de arquivo, descoberta de bancos, rede, credenciais, ordem, migração ou escrita.

A visualização mobile existente `scripts.inspect_paper_positions` pode receber `--incident-position-id` para acrescentar o cartão da auditoria à mesma tela PAPER, desde que a posição já esteja selecionada. Não cria dashboard paralelo, botões de operação ou chamadas externas; o cartão torna explícitos severidade, código, motivo, quantidades PAPER, necessidade de reconciliação e ausência de stop nativo.

O contrato `paper_runner_incident_audit_v1` tem códigos estáveis, severidade `INFO`/`REVIEW`/`BLOCKED`, checkpoint, quantidades Decimal serializadas, necessidade de reconciliação, evidências presentes/ausentes e motivo. Mantém incondicionalmente `orders_sent=false`, `native_stop_verified=false`, `live_trading_authorized=false`, `approved_for_live_use=false` e `financial_pnl_available=false`.

Estados observados incluem parciais incompletas, runner confirmado não protegido, trailing fictício não ativado/em acompanhamento/gatilho hipotético, reserva PENDING/UNKNOWN, parcial/cancelada e encerramento somente PAPER. AUTO4 com reserva residual é `RUNNER_CHECKPOINT_SUPERSEDED`: a divergência do fingerprint RUNNER2 antigo é consequência esperada da reserva, não corrupção; o auditor não tenta rearmar nem reler RUNNER2 nessa fase. Journal ausente, schema/digest inválido ou evidência incompatível retorna bloqueio fail-closed, sem caminho local, preço, símbolo, conta, ID ou PnL no JSON.

Os dois SQLite continuam sem transação cruzada. O relatório descreve replay local sintético, não reconciliação de exchange, stop nativo, fill real, posição real ou prontidão financeira. J1 owner-only/VPS permanece adiada; testnet, live, deploy e gastos não fazem parte desta entrega.
