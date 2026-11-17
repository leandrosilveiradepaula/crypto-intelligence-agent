# D405 — diagnóstico público WebSocket real em sessão finita, sem ordens

## Capacidade nova para a ferramenta

Uma execução **finita** poderá conectar o WebSocket público Bybit V5 linear (`wss://stream.bybit.com/v5/public/linear`), assinar `tickers.{symbol}` para uma lista fornecida, receber snapshots/deltas validados por D385/D386/D390 e produzir um relatório operacional **somente de contagens**, sem preços, símbolos ou IDs financeiros exportados.

O retorno distingue evidências úteis:
- conexões/sessões tentadas, ACKs recebidos, mensagens totais e quadros de ticker aceitos;
- número de contratos distintos que entregaram cotação causal de livro positivo, inclusive posições fora da lista principal;
- cobertura observada alguma vez **na última sessão** versus cobertura que ainda tinha preço fresco ao encerrar a amostra (máximo 3 segundos);
- histogramas de atraso de exchange→recebimento (P95/P99 por faixa, nunca latência exata), PING/PONG e reconexões;
- estado de falha/suspensão e booleans explícitos negando coleta 24×7, ranqueamento auditado, ordens e prontidão de negociação.

O callback de observação é limitado aos **100 contratos monitorados** pelo estado existente. Após reconexão, os contadores da sessão anterior são apagados e uma posição fora do ranking que não apresentar preço invalida a cobertura, mesmo que todos os outros contratos respondam. O relatório não considera ACK equivalente a preço e não confunde 50 snapshots históricos com preço fresco ao final.

## Operação condicionada — NÃO realizada na VPS nesta entrega

**Somente** após verificação de elegibilidade regional e permissão de pesquisa pública e liberação de um executor seguro, pode-se executar o exemplo read-only abaixo em ambiente autorizado, com checkout do SHA revisado e dependência `websockets` já existente:

```sh
python -m scripts.probe_bybit_public_ws_once_d405 \
  --symbols BTCUSDT --seconds 20 --sessions 1 --max-frames 12000 \
  --allow-public-websocket \
  --confirm-personal-readonly-research \
  --confirm-region-eligible
```

Este exemplo testa **um único instrumento**, não um Top50. Para o universo completo, o orquestrador precisa fornecer uma lista pré-auditada de 50 contratos em `--symbols` e todas as posições abertas em `--positions`. A ferramenta não constrói ranking por sufixo USDT, não lê account/REST privado, não toma nenhuma decisão de trade e não exporta nomes dos contratos fornecidos.

Orçamento máximo por execução: 60 segundos, até 100.000 frames e duas tentativas de sessão; padrão 20 segundos, 12.000 frames, 1 sessão. O transport é o `websockets.sync` J1 já existente, com URL fixa pública, TLS, timeout, max_size e desativação de proxy; D390 exige três flags booleanas **true** antes de abrir o socket. Ausência das flags implica zero rede e status `explicit_network_and_region_optin_required`.

Retorno 0 na CLI somente quando todos os contratos fornecidos tiveram cotação causal válida e fresca ao fim da sessão; retorno 2 para amostra incompleta; retorno 65 para configuração/execução recusada. **Mesmo retorno 0 não prova serviço contínuo 24×7, ranking cripto validado, liquidação, acerto, PnL ou proteção das posições em produção.**

## Evidências verificadas e bloqueio atual

A documentação oficial confirma o endpoint público linear, o topic ticker, snapshot/delta e o heartbeat `ping`: https://bybit-exchange.github.io/docs/v5/ws/connect e https://bybit-exchange.github.io/docs/v5/websocket/public/ticker.

Na sessão do ChatGPT de 17/11/2026, houve um teste HTTP sem upgrade contra o host WS na VPS: certificado TLS verificado com êxito e resposta HTTP 400. **Essa resposta não demonstra handshake/ACK nem frame real**; serve exclusivamente como verificação de alcance TLS. O executor administrativo acessível permitiu `curl`, mas bloqueou `python -m` e `python -c` por `exec_unavailable`. Não se deve contornar o bloqueio nem declarar que este teste real foi executado.

## Testes para integrar

```sh
python -m unittest discover -s tests -p 'test_bybit_public_ws_operational_probe_d405.py' -v
python -m unittest discover -s tests -p 'test_bybit_public_ticker_optin_d390.py' -v
python -m unittest discover -s tests -p 'test_bybit_public_ticker_coverage_d396.py' -v
```

CI com transporte/relógio **falsos**, nunca rede Bybit; cobertura de um contrato e 50, posição fora do ranking sem preço, reconexão que invalida cobertura anterior, leituras antigas, zero ordem e proibição da CLI sem flags. Documentar a conclusão com HEAD, resultado e gates.

## Próximo incremento de produto

Após obter as **primeiras evidências reais de ACK/frames**, medir cobertura com os 50 ativos PIT admitidos + posições, carga CPU/RSS, perdas, janelas stale, latência e recuperação. Só então desenhar operador 24×7 isolado para acionar o gestor PAPER entre horas, com gate separado de release/privacidade e sem dois escritores da J1. Nenhuma ativação real de ordem, testnet ou chave foi autorizada.
