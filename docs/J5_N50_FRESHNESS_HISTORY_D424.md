# D424 — Histórico local de frescor N50 (sem ampliar release)

## Motivação real (18/11/2026 UTC)
O monitor D423 já está instalado na VPS e apresenta dados públicos Bybit no loopback. O piloto automático começou com 35/50 frescos e outros ciclos oscilaram; a checagem real em 03:22 UTC recebeu 42/50 frescos, 8 expirados, 10.854 frames, 0 reconnect e HTTP 200. A idade máxima continua 3 s por timestamp da exchange e recebimento. Nunca arredondar frescor ou aumentar TTL para ocultar degradação.

## Mudança no produto
O painel local J5 mantém até 24 **amostras distintas** da rota existente `/api/n50-public-health` somente nesta aba. Cada amostra exibe timestamp UTC, ativos frescos/esperados e expirados. O resumo apresenta mínimo/máximo de frescor e conta intervalos acima de 180 s entre amostras visíveis; reinício da aba apaga o histórico. Não grava arquivo, storage ou journal e não cria nova requisição de rede. Poll permanece 30 s com idade máxima da amostra 180 s.

Uma mesma amostra reenviada é idempotente. Amostra com mesmo instante e conteúdo divergente, ou amostra retroativa, é recusada; quando a fonte falha, desaparece o estado corrente e o histórico identifica indisponibilidade, sem alegar que houve conexão contínua. Importação manual continua prioritária e oculta o histórico automático até recarregar a aba.

## Aceite e limites
- Regressão Node/Python: limite de 24 amostras, duplicação, conflito, reordenação, lacuna, 503/clear e prioridade manual; validação estrutural D421 permanece.
- Nenhum símbolo/preço, credencial, dado financeiro privado, websocket do browser, API nova, timer, serviço novo, migração ou ordem.
- Não é relatório histórico completo nem prova de uptime 24×7; intervalos acima de 180 s são observados apenas entre amostras mantidas e não atribuem culpa à rede/venue. A ausência de cotações frescas de alguns ativos não implica necessariamente erro de transporte.
- CI Linux/docs, Windows e Chrome + revisão SHA antes do merge. Merge sem deploy; o release D423 da VPS fica pinado no SHA anterior até novo gate.
- Nenhuma alteração J1, J4 ou PAPER. Entradas continuam não autorizadas, e a gestão real de posições permanece fora do escopo.
