# D530 — próximas hipóteses de entrada e coleta longa

D529 real (25/11/2026 UTC), SHA f91de881a062c752b6e76adde922545a3645e300: 420/420 cenários completos, 56987/56987 slots elegíveis e cobertos em cada horizonte, 54 dias de desenvolvimento em base 90d, 0 positivos no cenário adverse_first 1h. Não generalizar para trajetória real, favorável, carteira ou holdout. 231 comparações pareadas RSI: 160 melhoraram, 71 pioraram. Melhor média adversa: BB reentry sem RSI, stop 250 bps, 72h, 216/372 positivos, -8.22 bps; SMA10/30 veto 250/72h -14.76; SMA20/50+Pivot veto 150/48h -16.83. Todos negativos. D526 e D529 diferem em amostra/resolução/horizonte/estado de indicadores, não atribuir mudança a um único fator. Não repetir 420 cenários horários. Relatório privado existente contém custos, cenário favorável, ambiguidades, MAE/MFE, recuperação, meses e regimes. Explorar esses campos sem novo replay.

D530 introduz 5 hipóteses parametrizáveis (SMA10/30, SMA20/50, EMA9/21 retomada; duas compressões BB20/2 com tendência SMA20/50), cada uma pareada sem/com RSI como veto. Pullback: tendência por ordem de MAs e fechamento além da lenta; aguarda correção fechada até rápida dentro da tendência, arma por janela e confirma em barra posterior com fechamento acima da rápida e máxima anterior (espelho SHORT). Squeeze: largura média recente antes do candidato vs baseline anterior, expansão atual, rompimento da banda anterior, tendência das MAs e volume; nenhum candle futuro. Sem RSI no gatilho. Parâmetros e presets JSON editáveis, apenas pesquisa D529, sem alterar contrato residente. Dez novos perfis + nove controles D526 = 19; 399 cenários com 3 horizontes e 7 stops. A grade comum pode ter warmup diferente, não comparar como amostra idêntica sem verificar manifestos. Executar desenvolvimento somente; validação e holdout reservados. Preferir 5m quando houver cobertura e mostrar ambos cenários de ordenação, custos e cobertura. Não presumir sobrevivência a 2/2,5% a 50x.

Coleta D528: 90d 1h 108000/108000, 365d solicitados (390 planejados) 395280/465609 antes da retomada. Retomada anual e 5m falharam com classe J1BybitCaptureError sem causa específica. Não assumir quota. CLI passa a reportar código sanitizado, retCode, quota quando disponíveis, GETs tentados; registra shards com lacuna. Pacing opcional 2..12s, manter mesma origem, sem retries automáticos, sem contornar acesso. Se erro de acesso/região/rate limit, interromper toda a aquisição, não tentar próxima fase. Priorizar 90d 5m, depois completar 365d 1h e estender 5m. Dados antigos preservados. Não publicar dados privados ou alterar J1/PAPER.

Comando de pesquisa quando código aprovado:

    python -m scripts.run_j3_long_replay_d529 --directory "$HISTORY" \
      --policy-file "$POLICY" --days 90 --partition development \
      --matrix-file docs/examples/d530_entry_controls_matrix.json \
      --entry-experiments-file docs/examples/d530_entry_experiments.json \
      --horizon-hours 24 48 72 --stop-grid-bps 50 75 100 125 150 200 250 \
      --resolution 5m --low-priority > "$REPORT"

Sem real orders, gastos, serviços ou mudança de perfil. Cobertura sobrevivente não N50 histórico. Sem funding/liquidação.

A opção --oldest-first altera somente a ordem dos jobs dos shards existentes: prioriza os dias de desenvolvimento (mais antigos) na coleta 90d 5m. Não muda cutoff, hash, identidade dos checkpoints ou conteúdo do plano. A cobertura de cada partição deve ser medida; ainda não usar holdout. O wrapper deve parar toda a aquisição diante de J1BybitCaptureError e nunca tentar outro endpoint para contornar o erro.
