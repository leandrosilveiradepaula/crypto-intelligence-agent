# D403 — Cotações públicas da Bybit em amostra REST no aplicativo

## O que a ferramenta passa a fazer

O console PT-BR web/app exibe, na seção Mercado, último preço, mark, melhor compra e melhor venda de até 50 contratos selecionados, com horário UTC e indicação de validade da amostra. A origem é um arquivo JSON gerado por uma única consulta pública HTTPS à Bybit. A tela não contata a corretora, não autentica a origem do arquivo, não usa preços para abrir posições ou executar stops e não envia ordens.

A captura reaproveita BoundedBybitPublicClient e tickers_url() do J1: origin HTTPS fixo, JSON exato, limite de resposta, ausência de redirect, timeout e zero retry em erro. Não introduz segundo cliente HTTP, novo ranking ou escritor SQLite.

Um GET de /v5/market/tickers?category=linear retorna o snapshot público da categoria linear. A captura apenas filtra os símbolos apresentados pelo chamador (1 a 50), sem supor que o sufixo USDT comprova crypto-only ou que já representam o Top50. Se qualquer membro estiver ausente, horário inválido, livro zerado ou invertido, campos de preços inválidos ou resposta inconsistente, não entrega números.

## Operação de pesquisa local

Exemplo em ambiente que já tenha o código e acesso autorizado:

    python -m scripts.capture_bybit_rest_price_pulse_d403 --symbols BTCUSDT,ETHUSDT --output /tmp/cia-bybit-public-price-sample.json

O operador fornece os contratos admitidos e destino de saída; arquivo NOVO com modo privado 0600, sem sobrescrever. Sem --output, emite JSON no stdout. O usuário pode importar o arquivo no seletor existente da interface J5. Erro de schema recusa o novo relatório sem apagar o anterior válido.

Na sessão de 17/11/2026, um GET público independente feito diretamente da VPS retornou retCode=0, lastPrice, markPrice, bid/ask e turnover24h para BTCUSDT. Esta observação de rede NÃO é uma execução do novo módulo na VPS, não prova WebSocket, ranking, conta ou elegibilidade regional.

## O que é e o que não é

- O relatório declara rest_snapshot_display_only, hora do servidor e hora local de captura. O coletor recusa dados mais antigos que 45 segundos ou mais de 5 segundos no futuro.
- A UI sinaliza amostra recente por até 30 segundos; depois marca AMOSTRA VENCIDA e mantém o horário, nunca afirma feed ao vivo.
- O importador exige schema e tipos exatos, string decimal finita, bid <= ask, profundidade positiva, quantidade e símbolos delimitados; rejeita chaves extras e qualquer flag de ordens/sinais.
- O arquivo é volátil em memória na UI; nunca se associa automaticamente à carteira simulada nem a stop, margem, alavancagem ou PnL.
- Fonte do arquivo importado é não autenticada. O relatório NÃO valida crypto-only, WebSocket 24x7, preços de execução, stop nativo, lucro ou liquidação real.

O produto final permanece automático para entradas e saídas depois de pesquisa e gates aplicáveis. Uma amostra REST não alimentará o motor de ordens.

## Evidências e próximo passo

Testes:

    python -m unittest discover -s tests -p 'test_public_rest_price_pulse_d403.py' -v
    python -m scripts.audit_j5_product_app_browser

Verificam um único GET via transporte injetado, até 50 contratos, rejeição de payload incompleto/símbolo repetido/livro inválido/clock ruim, contrato Node, e importação Chrome em 320–1280px com data de validade, fraude, persistência e rede externa proibida.

A próxima etapa de produto é o WebSocket público Bybit contínuo, observando Top50 e posições fora do ranking, medindo latência, perdas e disponibilidade em piloto read-only isolado sob gate operacional. Nenhum deploy, conta, credencial, ordem ou modificação de J1 faz parte desta entrega.
