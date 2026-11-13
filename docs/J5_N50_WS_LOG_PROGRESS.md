# J5/PROGRESS1 — acompanhamento preliminar N50 por hora, offline

## Problema de produto
O painel mobile privado D330 exibe `0/24` até a auditoria D323 comprovar integralmente 50 contratos durante 24 horas seguidas. É correto como **homologação**, porém não informa de forma legível ao operador o andamento intermediário das sessões WS.

## Solução e fonte
`j5_n50_ws_hour_progress.py` produz projeção **exclusivamente local/offline**, a partir de até 4096 registros já sanitizados da forma `{"finished_at_ms": integer_utc_ms, "report": owner_window_report}`. Não abre journalctl, banco, serviço ou WebSocket. Apenas projeta 24 horários UTC encerrados e separa:
- `ok`: `ws_owner_hour_50_observed_local_only` + `confirmed_contracts=50`, `missing_contracts=0`, `expected_contracts=50`, digest SHA256 de auditoria, origem WS confirmada, ACK positivo, sem REST GET nem ordens;
- `failed`: falha/abstenção explícita, inclusive quando **50 eventos foram gravados mas `confirmed_contracts=0`**;
- `missing`: nenhum relatório válido atribuído a essa hora UTC;
- `duplicate`: dois ou mais relatórios disputam a mesma hora, mesmo se um parecer sucesso.

O último fechamento só entra na janela **a partir de três minutos depois de HH:00 UTC**; antes disso a hora anterior permanece como final elegível para evitar falso `missing` durante a execução. Falha sem timestamp de fechamento só é atribuída ao instante HH:00 se conclusão ocorrer até 180 segundos após o horário. Fora do prazo a avaliação falha fechada. Não contar ACK, gravação ou timer como 50/50.

`project_n50_ws_log_progress` informa `observed_50_of_50_hours`, `consecutive_recent_observed_hours`, falhas, ausências, duplicatas e estado de cada slot. Não emite símbolos, preços, caminhos, OHLC, digests ou payloads privados. **Sempre** `owner_d323_24h_audit_verified=false`, `rotation_36h_live_verified=false`, `continuous_collector_verified=false`, `marketwide_top50_verified=false`, `orders_sent=false`. Mesmo 24 sucessos do log não promovem homologação formal de SQLite/journal; é necessário o D323 owner-only já existente.

## Interface móvel e acesso seguro
`render_n50_ws_log_progress_html` retorna HTML PT-BR estático, 24 células UTC, layout responsivo, sem JavaScript/form/requisições. CSP `default-src 'none'`, sem credenciais ou valores financeiros. Não foi disponibilizado na internet. CLI offline:

```bash
python -m scripts.render_j5_n50_ws_log_progress_once \
  --allow-sanitized-stdin-read --format json < n50-count-only-input.json
```

Para HTML usar `--format html`. O stdin deve conter o envelope **previamente sanitizado** `{"schema_version":"j5-n50-ws-count-only-input-v1","now_ms":<UTC ms>,"events":[...]}` e ter no máximo 1 MiB. A CLI não coleta journalctl nem conhece caminhos de owner e não cria arquivo: redirecionamento deve ser feito em local privado pelo operador, quando autorizado. Sem flag, não lê stdin e falha fechado. É uma capacidade offline opcional, **não** um deployment na VPS ou painel público.

## Aceite
Testes de 50/50 real em relatório vs 50 appends sem auditoria, 24 logs sem D323, hora faltante, duplicatas conflitantes, relógios, buffer de três minutos, limites de input, tipos inválidos, JSON com duplicata, saída sem dados privados, HTML acessível sem script, ausência de rede/banco/ordens. CI Linux/docs, Windows/offline, PAPER/mobile; merge sem deploy. J1 #585 e #619 continuam medidos pela auditoria owner D323 e pela evidência de rotação, não pelo progresso J5. Custo adicional R$0.
