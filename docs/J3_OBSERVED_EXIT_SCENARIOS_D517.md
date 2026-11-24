# D517 — Replay condicional das saídas configuradas

## Entrega
Laboratório D512 usa os parâmetros salvos de margem, alavancagem, stop, metas, percentuais de cada parcial (posição inicial ou saldo restante), residual e taxas/slippage. Usuário escolhe horizonte de 1 a 12 horas. Nenhum parâmetro operacional é editado. Sem replay solicitado, os resultados históricos anteriores permanecem iguais.

## Método e limites
- As regras de entrada D435/D512 recebem somente prefixos causais e coortes originais. Eventual aquecimento posterior D516 permanece rotulado retrospectivo.
- A referência de abertura é a abertura observada na próxima vela, ex post. A captura da decisão pode ter ocorrido depois dessa abertura; não alegar executabilidade.
- Caminhos de avaliação exigem uma sequência completa de arquivos originais horários, preço de sobreposição igual e presença do símbolo em cada arquivo. Se falta hora ou símbolo, resultado desconhecido. Nenhum preço futuro vem do suplemento.
- Para cada OHLC, executar duas ordenações explícitas: abertura, extremo adverso, extremo favorável; e abertura, extremo favorável, extremo adverso. Extremos não são timestamps de execução. Alvos não ultrapassam quantidade restante; PRE1 define frações e runner. Stop fecha o restante, inclusive runner. Em gap adverso do stop usa-se abertura observada; para alvos usa-se o nível, sem melhoria por gap. Residual sobrevivente é marcado no último fechamento com custo estimado de saída. Não simula trailing dinâmico.
- PRE2 calcula custos de entrada e saída ponderados pelo notional de cada fração; arredondamento do notional de saída agregado a 18 casas decimais. PnL condicional pré-funding; ambas alternativas são exibidas e nenhuma é escolhida como realizada. Não são limites matemáticos garantidos. Não usar soma de hipóteses independentes como patrimônio, retorno de carteira ou capacidade de abrir todas ao mesmo tempo. A perda >= margem é uma condição hipotética após custos, não cálculo de liquidação. Não pressupõe profundidade, lotes, execução, mark price, manutenção, funding ou validação OOS.
- O avaliador de caminhos aceita intervalos fechados 1m/5m/15m/1h, até 12h, mas esta integração fornece somente arquivos 1h; ainda não há coleta de intrabar em produção.

## API privada e CLI
GET existente: `/api/strategy-comparison?fast=10&mid=30&trend=60&horizon=4`. Para complemento D516, inserir `&retro=1` antes de horizon. A resposta inclui `exit_replay` com contagem de hipóteses, cobertura, ordenação sensível e dois cenários por estratégia. Sem horizon, exit_replay=null. CLI D516 aceita `--horizon-hours 4`; `--reuse` não consulta a rede. O painel é somente leitura de histórico nesta ação; não altera ordens.

## Gate
Testes cobrem LONG/SHORT, ambiguidade, percentuais iniciais/saldo restante, stop gap, residual, fechamento total, ausência de dados e preservação dos resultados D512. Exigir CI e revisão. Nenhuma evidência de execução sobre arquivos privados nesta entrega. D515 segue instalado; D516/D517 requerem gate de publicação. Sem ordens reais e custo adicional zero.
