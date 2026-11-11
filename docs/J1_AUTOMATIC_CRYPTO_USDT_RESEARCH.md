# J1 — seleção automática de candidatos a futuros cripto USDT (pesquisa)

Data: 2026-11-11. Issues #319, #517, #2. Direção do produto: parar de exigir investigação manual de todos os tickers antes de gerar um **universo de pesquisa**.

## Decisão

Um ticker terminado em \`USDT\` identifica a moeda de cotação, **não** prova que o subjacente seja criptomoeda. A categoria linear da Bybit contém ações e commodities. Em vez de usar somente um registro positivo de dezenas de tokens manualmente revisados para até mesmo pesquisar mercados, o novo filtro puro \`j1_auto_usdt_perp\`:

1. Recebe catálogo completo \`instruments-info category=linear\`, com cursores completos, timestamps causais, deduplicação e limite de recursos; não realiza GET.
2. Exige \`LinearPerpetual\`, \`Trading\`, \`quoteCoin=settleCoin=USDT\`, \`symbol=baseCoin+"USDT"\`, não-prelisting e sem vencimento.
3. Recusa negativos TradFi documentados, marcadores \`marketRegion\`/\`underlyingTicker\`/\`symbolType\` não vazios, nomes claramente associados a ações/ETF/petróleo e tags especiais não compreendidas. Ausência de marcadores significa **candidato provisório**, não cripto verificado.
4. Produz pool **automático para pesquisa**, sem exigir cadastro positivo individual; acrescenta contagens por motivo, hash e opção controlada para imprimir apenas símbolos públicos.
5. Recebe turnovers de candles 1h **já fechados**, em unidade USDT documentada pelo contrato upstream, exige timestamps consecutivos e 24 linhas completas para classificar por soma; ativos com série incompleta não recebem turnover zero; ausência de liquidez positiva é contada em separado; ranking mantém no máximo 50.
6. Não envia ordens, acessa rede, modifica SQLite, habilita trading, autentica payloads live ou altera o Top50 oficial de execução. A integração read-only com o censo privado D256 / D264 será trabalho subsequente; não há replay owner real desta nova rotina nesta PR.

## Distinção obrigatória de três estados

- **Excluído**: contrato fora do produto exigido, marcador TradFi, fonte negativa documentada ou inconsistência.
- **Candidato automático à pesquisa**: passou nos filtros técnicos e não apresentou indicador conhecido de TradFi; pode ainda ser instrumento não cripto.
- **Cripto verificado e elegível à negociação**: exige evidências adicionais de instrumento/identidade, liquidez, histórico, risco e gates operacionais. Esta PR **nunca** produz este estado.

Essa separação permite desenvolver J2/J3/J4 e estudar o universo com classificação automática sem criar um bloqueio por dezenas de PRs individuais, mas protege contra confundir \`BZUSDT\` (petróleo) com \`BTCUSDT\` (cripto).

## Validação

- Testes: \`tests/test_j1_auto_usdt_perp.py\`, com casos BTC/ETH/novo token, TradFi, petróleo, contrato com expiração, pré-listagem, sinais inválidos, paginação, duplicação, relógio, candle ausente e Decimal malformado.
- Executar CI Linux/docs, Windows/offline, Chrome/PAPER, conferir HEAD e revisar antes de merge.
- Não refazer histórico nem alterar o banco existente. Zero custo adicional.
- Próximo bloco: adaptar o replay de 819 séries e o overlay D264 **somente leitura** para usar este pool automático e produzir ranking exploratório, conservando a classificação de identidade pendente.
