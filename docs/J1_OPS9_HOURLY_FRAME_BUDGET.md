# J1/OPS9 — Orçamento de frames por duração do lease 52-topic WS

**Issue:** #429. **Jornada:** J1 (perpétuos, pesquisa, read-only). **Sem deploy/SSH/GET/ordens.**

## Problema real

O supervisor WebSocket OPS3 utilizava `WSRunBudget(max_frames=4096)` por padrão. O serviço de 55 minutos OPS6 construía `WSRunBudget(max_seconds=3300)`, mantendo silenciosamente esse default. Com 52 contratos `kline.60`, na cadência documentada de até uma atualização por segundo por tópico, 4.096 frames podem esgotar em aproximadamente 79 segundos. Isso causaria rotação prematura, dezenas de segundos offline por reinício e risco de perder o `confirm=true` de um candle fechado. A CI verde do piloto de 180s não é evidência de duração real.

## Correção limitada, segura e verificável

- O orçamento de **pesquisa finita** continua por padrão em 4.096 frames, sem alteração da CLI OPS4/OPS8, e ainda tem `max_seconds=180`.
- Apenas o adaptador de **serviço off-by-default** em `scripts/run_j1_ws_service.py` configura `max_frames = 52 * seconds + 4096`. Para 3300 segundos: **175.696 frames**, maior que o envelope de 171.600 frames de mercado em frequência 1s. O teto absoluto da classe sobe de 20.000 para **200.000**, com limites de duração e sessões inalterados. `seconds` segue restrito a 300..3590. Na duração máxima o orçamento é 190.776 frames; não é ilimitado.
- Estouro de frames **antes da duração** passa a resultar em `ws_frame_budget_exhausted_abstain` e categoria fixa `frame_budget_exhausted`, distinta da conclusão normal por tempo. `run_owner_ws_pilot` também marca degradação mesmo quando ACK foi recebido. O adaptador de serviço classifica a anomalia como **exit 66** (parar/abster, `RestartPreventExitStatus` existente); nunca sinalizar continuidade operacional sadia após o teto.
- Reutiliza controle causal das velas confirmadas, mutex, SQLite WS separado, contador de heartbeat/pong, processamento de até um frame por vez e limites globais, sem solicitar klines REST nem descartar o banco EXIT5.
- Um ACK para 52 tópicos **não comprova que todos entregaram frames**, nem 24h de candles completos, Top50 marketwide, sinal ou funcionamento na VPS.

## Testes

`python -m unittest discover -s tests -p test_j1_ws_supervisor.py -v`
`python -m unittest discover -s tests -p test_j1_ws_service.py -v`

Exercitar: limite de 4.096 da pesquisa permanece; serviço 300/3300/3590s recebe envelope de frames correto; 200.000 teto global; confirmação ACK seguida de 6 mensagens de controle com teto 6 resulta em abstenção e 0 candles; código 66 não é reiniciado automaticamente pelo template; opt-ins negativos não executam socket; suíte completa Windows/Linux/Chrome/PAPER, `compileall` e documentação. Toda alteração é offline, sem executar serviço real.

## Dependências e bloqueios restantes

A correção remove um fator de reinício prematuro **mas não garante coleta 24/7**. É necessário homologar ACK/tópicos reais (OPS8), proteger o fechamento UTC durante rotação de leases, adicionar detecção/recuperação limitada de lacunas, validar throughput/memória e operar o serviço na VPS com gates aplicáveis. O journal tem teto de 100.000 linhas, que em universo 52x1h corresponde a pouco mais de 80 dias; rotação/arquivo de histórico com proveniência será outro requisito de longevidade. A renovação de PITs também tem limite 64. O Top50 marketwide permanece pendente (#319), e J1 #2 aberta. Nenhuma negociação foi autorizada.
