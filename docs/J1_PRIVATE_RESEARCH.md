# J1/WU36 — Coleta privada local Kraken Futures (sem ordens)

## Propósito e estado
A J1 validou dois componentes com dados realmente observados em 25/10/2026: 3 candles fechados de **preço** Kraken PF_XBTUSD/1h em SQLite TEMP (run [40238058772](https://github.com/leandrosilveiradepaula/crypto-intelligence-agent/actions/runs/40238058772)) e seleção corrente com registro BTC/ETH real, 2 elegíveis em 231 instrumentos (run [40238374774](https://github.com/leandrosilveiradepaula/crypto-intelligence-agent/actions/runs/40238374774)). Os bancos TEMP desses experimentos foram apagados; eles **não** fornecem histórico cumulativo.

A WU36 implementa o próximo estágio: `capture_private_research` / CLI `scripts.collect_private_kraken_research` reutilizam os componentes **já existentes** para guardar um pequeno conjunto no MESMO SQLite local. O código não é um serviço implantado; execução é somente com duplo opt-in expresso, sem coleta automática, sem credenciais ou ordens. **Não executá-lo em produção até que o gate aplicável seja liberado.**

## Operação local futura, somente ambiente privado autorizado
Escolher **fora do checkout do GitHub** um diretório absoluto cuja permissão POSIX seja 0700 (somente titular) e um arquivo `.sqlite` ainda inexistente ou 0600. Nenhuma chave Binance/Kraken e nenhum dado real deve ser enviado ao repositório público. Exemplo ilustrativo, não executado como parte da WU36:

```sh
mkdir -m 700 "$HOME/crypto-private"
python3 -m scripts.collect_private_kraken_research \
  --database "$HOME/crypto-private/market.sqlite" \
  --allow-public-network --allow-private-persistence
```

Esse fluxo atual faz **no máximo 3 GETs Kraken Futures**: 1 instruments + 1 tickers + 1 chart de PF_XBTUSD, sem retry/POST/ordens ou métodos de autenticação. Confere se BTC está no registro real BTC/ETH validado há no máximo 7 dias, se o contrato é perp/linear USD ativo, se o ticker `volumeQuote` é Decimal, se a janela de mercado é contemporânea e se há 3 candles de preço 1h totalmente fechados. Se BTC for inelegível ou dados insuficientes, a coleta falha fechada e não cria banco novo. Não backdateia o registro.

O SQLite opt-in contém dois grupos independentes de registros: o `UniverseSnapshot` presente e o `kraken_research_prices` preço-only com observação temporal/recibos. O arquivo é privado e reutilizável entre execuções, com replay idempotente e detecção de conflitos; cada inserção é transacional. Uma interrupção entre a gravação dos dois grupos pode deixar captura **parcial válida** no DB existente; o comando só relata sessão completa se ambas forem gravadas e relidas com qualidade completa. Não declarar atomicidade única do conjunto e não tratar captura parcial como ready. Quando cria banco novo e a execução de persistência falha, tenta eliminar esse novo arquivo.

## Limites de contrato (regras firmes)
- Registro positivo cobre apenas BTC e ETH. Até 2 elegíveis não são os 50 maiores históricos; 229 exclusões na amostra de uma execução não provam 229 ativos não cripto.
- A Kraken **não comprovou unidade financeira de `trade candle.volume`**: não inventar `base_volume`, `quote_volume`, `ClosedCandle` canônico ou funding. Não usar para avaliação de retornos líquidos financeiros, liquidação real ou sinais públicos.
- O snapshot contém valor monetário de ticker em USD, mas só no SQLite **privado**; logs nunca expõem preço, volume, caminho completo do DB, URL com credenciais ou payload.
- A Kraken pode restringir localização, licenças e usos. HTTP200 não concede redistribuição; direitos externos #48 e uso público/comercial continuam bloqueados. Nenhum cron ou serviço/VPS foi ativado; release/migration/trades reais requerem gate do Product Owner.
- `--database` é obrigatório, absoluto, extensão `.sqlite/.sqlite3/.db`, fora do GitHub e diretório privado POSIX 0700. Falta de qualquer opt-in resulta em zero rede/arquivo.
- Sem dependências pagas. A amostra de uma sessão é pequena; uma estratégia validada precisa de cobertura contínua de muitos períodos, dados completos de derivativos, preços de marcação, funding, custos e backtest intrabar.

## Testes e evidências
A CI roda testes offline de clock real/injetado, manifesto point-in-time e expirado, xStocks, ausência de BTC, três candles, volume opaco, arquivo seguro 0600, SQLite persistente e replay cross-session, falha de provedor sem retry, recusa de gravação dentro do repo, import da CLI e ausência de operações reais. Fluxo live histórico comprovado apenas nas WU34/WU35; a WU36 entrega **código local**, não uma execução da VPS.

## Opção WU37: expandir o registro local sem simular ativos
Depois de observar/revisar o manifesto v2 `crypto-bases-10-20261025-v2.json`, a mesma CLI local da WU36 aceita `--registry expanded-10` junto das demais flags opt-in; a opção é restrita às revisões internas `btc-eth` ou `expanded-10`, sem aceitar URL externa, input livre ou conteúdo baixado. A identidade passa a cobrir até **10 bases**, mas o coletor de candles continua capturando somente três preços 1h do BTC, em SQLite privado. A seleção de `UniverseSnapshot` reflete somente os contratos realmente presentes/ativos e com USD quote nas consultas Kraken. O default `btc-eth` permanece para reproduzir os checkpoints anteriores. Nenhuma execução da VPS, histórico Top50, direitos comerciais, API CoinGecko ou conversão de volume canônico foi autorizada.

## WU38: múltiplos contratos perp de preço-only com teto de leitura
O mesmo comando LOCAL e opt-in agora recebe `--max-price-symbols N` com N inteiro de 1 a 5 (default 1, mantém BTC apenas). Para ampliar a cobertura do registro v2 já comprovado por 10 contratos **correntes** Kraken, combinar `--registry expanded-10 --max-price-symbols 3` com `--database` em diretório privado e ambas flags explícitas de autorização. O coletor usa BTC como âncora obrigatória e escolhe mais dois contratos na ordem **real** do ranking USD do snapshot atual. Não fixa ETH/SOL se o mercado mudar; caso menos de 3 estejam elegíveis, consulta somente os presentes. No máximo dois GETs de instruments+tickers e N GETs chart (máximo absoluto 7), sem retry nem GET de fonte externa. Todos os dados de preço são validados antes de escrever; a persistência no SQLite mantém transações por grupo e por página, não é uma sessão atômica única. Resumo sem símbolos, preço/volume, DB path ou payload. Nenhuma instalação/cron/VPS foi autorizada. O owner-only workflow de diagnóstico usa SQLite TEMP apagado ao término e não cria feed para terceiros; direito de distribuição e volume financeiro ainda não validados.
