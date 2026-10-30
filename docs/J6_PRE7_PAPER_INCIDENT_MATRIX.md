# J6/PRE7 #401 — matriz offline de incidentes e prontidão PAPER

`python -m scripts.demo_paper_incident_matrix` executa uma matriz finita e determinística em SQLite temporário. Ela reutiliza AUTO4, RUNNER2, PRE4 e o auditor PRE6; não cria ledger paralelo, relógio real, cron, daemon, credencial, rede, ordem, stop nativo ou arquivo persistente.

Cada cenário produz `paper_incident_matrix_v1`, com expectativa, observação, status `PASS` ou `BLOCKED_EXPECTED`, checkpoint, código PRE6 e flags negativas. A saída não contém caminho, símbolo, preço, conta, credencial, identificador de infraestrutura ou PnL. O laboratório cobre ciclo saudável com restart/FILL de fixture, pré-reserva, UNKNOWN, parcial+cancelamento, reserva concorrente, política incompatível, digest corrompido e arquivo AUTO4 ausente. Bloqueios são resultado correto, não falha.

Uma corrida pode perder o preview por drift depois de outro processo confirmar a reserva; isso é fail-closed. A matriz exige que exista uma única reserva persistida e que o auditor a classifique como checkpoint RUNNER2 superado, nunca como autorização de novo envio.

## Prontidão J6

Comprovado somente offline: replay/persistência/restart PAPER, idempotência e lock local, conservação das reservas e classificação conservadora de UNKNOWN/parcial/cancelamento. Pendente: feed prospectivo e PAPER de 24h+, dados reais com qualidade, custos/slippage/funding/liquidação de venue e recuperação operacional real. Bloqueado: reconciliação de exchange, stop nativo, testnet/live e qualquer uso de credencial, até gates e autorização humana próprios. CI verde não transforma fixtures em homologação financeira.
