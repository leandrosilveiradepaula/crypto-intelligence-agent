# J1/OPS13 — Diagnóstico privado da janela WS de 24h e capacidade

Issue #444, associada a #429, #319, #2. Base GitHub verificada: `main=8e37e0e4e7bf78831f15cf9ba08ad92d6e755329`.

## Escopo entregue

`scripts.read_j1_ws_private_readiness` oferece uma única consulta **read-only, sem rede e sem ordens**, aceitando somente `--directory`. A implementação reutiliza `_safe_stat` (dono, modos 0700/0600 e não symlink), `_read_epoch_chain` (PIT), `_audit_epoch_chain` (SQLite snapshot read-only, integridade, 24 horas UTC fechadas e marcadores OPS12) e `read_owner_ws_health` (observação privada, jamais liveness). Relata só contagens: membros revisados, completos/ausentes nas últimas 24h, marcadores de lacuna, linhas ocupadas, linhas restantes, dias inteiros projetados pela cardinalidade revisada, warning com `<=7` dias, epoch count e estado do último health. Não publica símbolos, OHLC, volume, caminhos ou credenciais.

A projeção conservadora de capacidade é `remaining_rows // (reviewed_contracts * 24)`; com 52 membros e 100.000 linhas inteiras disponíveis equivale a **80 dias completos** com recepção de todas as 52 velas por hora. É uma previsão de volume de registros, não garantia de permanência por 80 dias ou validação da origem. Nenhuma retenção/limpeza foi ativada. Mesmo relatório completo diz `worker_running_verified=false`, `source_authenticated=false`, `marketwide_top50_verified=false`, `live_trading_authorized=false`.

O relatório falha fechado se o owner, permissões, timestamp UTC, PIT, escopo vencido, marcadores/linhas, integridade ou contagens não forem aceitos. A execução não lê o banco REST EXIT5, não escreve no SQLite WS e não inicia o serviço systemd. **Não é teste live OPS8 nem prova de soak 24h do processo**.

## Comandos para executor autorizado

`python -m unittest discover -s tests -p test_j1_ws_private_readiness.py -v`

Após CI/revisão, o operador com acesso owner-only poderá executar `python -m scripts.read_j1_ws_private_readiness --directory /caminho/privado/aprovado` como usuário proprietário do journal; sem flags de rede. Não executar comando em VPS sem verificar identidade, commit, autorizações e diretório real, nem adicionar o path ao GitHub público.

## Gates remanescentes

CI Linux/docs, Windows/offline, Chrome/PAPER no SHA final; revisão e merge sem deploy. Após merge, a VPS ainda precisa comprovar ACK/frames reais de 52 tópicos, observação de 24h, qualidade dos candles e eventual política de arquivamento auditável antes do teto. J1 #2, Top50 #319 e supervisão #429 seguem abertas. Custo R$0 adicional, sem ordens e sem migração.
