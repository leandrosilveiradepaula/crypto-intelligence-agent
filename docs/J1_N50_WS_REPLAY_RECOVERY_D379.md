# J1 / D379 — auditoria count-only do conflito WS às 09:00 UTC

## Evidência real e decisão
Em 16/11/2026, WS 08:00 UTC confirmou 50/50 da epoch nova; WS 09:00 UTC registrou
`closed_events_appended_to_ws_journal=50` e depois falhou com
`ws_journal_closed_replay_conflict`, sem evidência final no relatório.
O OnFailure desabilitou WS+rotação e habilitou REST, cuja execução às 12:02
UTC retornou `catchup_exceeds_48h_owner_review`, sem GET.
Portanto a J1 histórica D360 está aprovada para pesquisa, mas o serviço
corrente **não está coletando continuamente**.

## Script somente leitura
`python -m scripts.audit_j1_n50_ws_replay_count_d379_once --closed-hour-end-ms 1794819600000 --allow-private-owner-read`
somente no owner `cia-probe` da VPS autorizada, depois de conferir a hora
alvo com UTC. O valor é exemplo da janela 09:00 UTC de 16/11/2026;
se o relógio passou de 48h, o próprio preflight abstém.

A CLI carrega o pointer ativo através do validador existente, examina o
SQLite com `mode=ro` e `BEGIN`, valida `PRAGMA integrity_check`, schema
e conta registros em dois fechamentos. Nunca mostra símbolos, OHLCV, preço,
payload, path, segredo ou operação em mercado. Não cria diretórios, muda
timers nem apaga/atualiza registros.

**Interpretação limitada:** `count_only_not_content_verified` comprova
somente a integridade estrutural e contagens do snapshot observado; não
comprova natureza da divergência, autenticidade da fonte, classificação
crypto-only, causalidade ou qualidade dos 50 registros. A verificação
de conteúdo/epoch completa deve usar os validadores owner existentes.

## Política de recuperação
Não alterar `append()` nem tratar fechamento duplicado como benigno sem
evidência. Se `received_ms` for o único campo mutável, projetar contrato
de repetição de valores financeiros imutáveis e preservar primeira recepção;
qualquer preço, turnover, volume, escopo, mudança temporal inesperada ou
reprocessamento incompatível continuará fatal. Escrever testes antes da
mudança de semântica. Reativação dos timers N50 e instalação J2/J3 são
gates operacionais separados; nunca retomar REST alargando arbitrariamente
a janela 48h.

## Validação
`python -m unittest discover -s tests -p test_j1_n50_ws_replay_count_d379.py -v`.
Todos os testes são offline, sem conexão com a VPS.

## D380 — regra de repetição do fechamento e evidência da VPS
Em 16/11/2026 auditoria real como `cia-probe` com job
`a26605d332994bfdbc542b2f315d5877` retornou integridade SQLite
`True`, epoch ativa `True`, 50 linhas às 08h, 50 às 09h,
250 no total. A falha foi **posterior** à persistência da hora.
O conteúdo do frame rejeitado não foi salvo, portanto não se afirma
qual dos campos variou na mensagem real.

O código D380 muda somente a **classificação de uma repetição** já
previamente validada: retém o primeiro payload quando todos os campos
não temporais coincidem e `received_ms/server_ms/trade_ms` são
monotônicos. Repetição com alteração de preço, volume, turnover,
identidade ou timestamps regressivos segue rejeitada com `DataGapError`.
É proibido substituir o primeiro recebimento; contagens auditáveis não
são lucro, nem atestado de fonte ou de continuidade futura.

Testes: `test_j1_n50_ws_economic_replay_d380.py` e atualização da
regressão D331 para divergência econômica genuína. A alteração não é
implantação: apenas após CI, revisão e gate de recuperação no VPS
considerar religar WS/rotação e observar um fechamento fresco.
