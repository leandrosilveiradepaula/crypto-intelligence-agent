# J5/OPPORTUNITIES — watchlist J2 WebSocket no painel mobile (#642)

## Entrega ao usuário

A J2/D345 já identifica observações de alta e baixa em `j2-n50-ws-descriptive-watchlist-v1` depois de validar os **50×24 candles WS fechados por ativo** na epoch ativa. O painel PAPER passa a reconhecer **esse relatório específico** pelo importador JSON que já existia, sem novo coletor, REST, endpoint, servidor, serviço, permissão ou publicação na VPS.

Na seção "Mercado N50", um painel de observações J2 mostra a hora UTC da última vela, quantidade de observações de alta e de baixa e número de ativos cuja razão de turnover é desconhecida. Quando o operador **explicitamente** importa JSON de símbolos privados produzido pelo CLI owner J2 #638, são exibidos até cinco candidatos LONG observacionais e cinco SHORT com símbolo, direção, força relativa ao BTC e razão de volume. O arquivo fica **somente na memória da página** até recarregar, sem upload e sem persistência no `localStorage`.

Quando o snapshot veio com contagens apenas, o painel mostra essas contagens e a ausência de símbolos; **não inventa candidatos**. Um snapshot histórico recebe o selo "Histórico · não atual". Os cards não possuem links, botões de execução ou pré-preenchimento automático de posições PAPER.

## Segurança, causalidade e validade do importador

`validateWatchlist` exige: schema/status `ws_descriptive_watchlist_ready`, qualidade correta, replay `ws_journal_integrity_replayed=true`, 50 membros/24 barras, contexto BTC presente, SHA256 da janela, relógio UTC alinhado e não futuro, 0 intenções/requests/mutações, todas as flags de ordens, sinais, autorização de trading, D323 formal, Top50 global e backtest financeiro falsas.

Contagens são inteiros limitados, sem listas parciais. Cada candidato privado deve ter símbolo `[A-Z0-9]{1,28}USDT` único, direção consistente com rompimento, força relativa BTC com sinal adequado, volume nominal positivo, razão de turnover ≥ 1, ATR não negativo e números como strings decimais exatas. Ranking/desempates são novamente verificados com **BigInt**, evitando erros de arredondamento do navegador. O renderer usa somente `textContent`, não `innerHTML`, HTML da corretora ou código recebido. A CSP e `connect-src 'self'` permanecem; o app não faz nenhuma nova chamada HTTP por causa da watchlist.

O botão de importação distingue `j5-n50-ws-log-progress-v1`, `j2-ws-n50-descriptive-24closed-v1` e a nova watchlist. Nenhum relatório externo controla `state.positions`, margem, alavancagem, runner, saldo ou ordens. A J2 não constitui prova de ganho, probabilidades de acerto, sinal autorizado ou alocação de capital.

## Como obter evidência legítima (futuro, com gate owner)

O CLI já existe em `scripts.research_j2_n50_ws_watchlist_once`: com leitura privada e `--enable-descriptive-watchlist` produz **somente contagens** por padrão; símbolos exigem `--include-private-symbols --confirm-private-symbol-output` em ambiente owner autorizado. O usuário importa o JSON localmente no aplicativo, sem publicação de símbolos no GitHub. **Nenhum comando de owner, instalação, rede ou auditoria D323 é executado por esta PR.** Quando não há 50×24 de mesma epoch, a J2 se abstém; a interface não finge dados. O endpoint loopback antigo `/api/j2-research` permanece agregado e não expõe a watchlist privada.

## Validação

- `tests/test_j5_product_app_mvp.py`: IDs, HTML sem transporte novo, contrato de importação e renderização por `textContent`.
- `scripts.audit_j5_product_app_browser`: Chromium real, quatro ou mais resoluções móveis/desktops, importa JSON privado com alta/baixa, exige cartões/contagens, verifica overflow, depois JSON sem nomes e rejeita símbolo malicioso com HTML/XSS, preservando posições PAPER e zero solicitações externas.
- CI docs/Linux, Windows/offline e QA PAPER/mobile, SHA exato, revisão e merge sem deploy.

Gates de produto continuam: J1/D323 #585 e Top50 marketwide #319; J3 resultados posteriores/riscos #640. Interface não é execução real nem acesso remoto do celular à VPS. Custo adicional autorizado R$ 0,00.
