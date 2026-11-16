# J2 / D390 — conector opt-in Bybit V5 somente leitura

## Entrega

`crypto_intelligence_agent/bybit_public_ticker_optin_d390.py`
liga o supervisor de sessão pública D386 à **fábrica de transporte
WebSocket pública já existente da J1**, reaproveitando o endpoint fixo
`wss://stream.bybit.com/v5/public/linear` e o `websockets.sync`.
D390 não introduz segunda biblioteca de rede, novo daemon,
escrita em SQLite, conta ou credenciais.

A função `run_readonly_bybit_ticker_lease` oferece **execução
finita** (padrão 35 segundos, 2.048 quadros, 1 sessão) com orçamentos
estritamente limitados pelo D386. Exige três flags booleanas
**explicitamente verdadeiras** antes de construir qualquer transporte:
`allow_public_websocket`,
`confirm_personal_readonly_research`, `confirm_region_eligible`.
Sem opt-in, responde `owner_opt_in_required_no_network`.

Para testes unitários, aceita um `session_factory` injetado, além
de relógios e sleeper controlados. Com dados válidos,
`BybitPublicTickerBook` valida snapshot/delta, sequência,
last/mark/BBO e stale sem expor preços. O relatório é
**somente agregado**, marca todas as proteções financeira/ordens como
`false` e não garante N50 completo. ACK sem nenhum frame de ticker
é `public_market_frames_not_verified`, nunca sucesso de mercado.

Ao encerrar a lease, o estado de cotações é invalidado;
**a conexão está fechada** e não oferece fonte contínua
para posições ou execução. Isso evita confundir teste finito com
monitoramento 24×7.

## Evidências exigidas

`python -m unittest discover -s tests -p 'test_bybit_public_ticker_optin_d390.py' -v`

Casos: gates incompletos sem importação/conexão,
Gates com tipos inválidos, contrato público de uma
inscrição e snapshot válido, ACK sem dados, símbolos não
admitidos antes de abrir o socket. Nenhum teste usa internet,
conta, credencial ou dinheiro.

## Próximas tarefas em #677 e J6

1. Medir a interface de rede com opt-in em ambiente autorizado e
   isolado, incluindo carga 50 + posições, latência e assinaturas
   sob stress e reporte sanitizado.
2. Definir operador de sessões longas 24×7 e reavaliação do
   Top50 sem dois escritores da mesma J1; revisar política de
   health/backpressure e recuperação de falhas.
3. Integrar à coordenação PAPER de saídas #676, com
   critério de stale por posição e replay causal J3.
4. Não habilitar serviço, credenciais, ordens, testnet/live ou
   publicação sem gate próprio. J1 D384 depende de comando
   operacional na VPS e não é alterada por este PR.
