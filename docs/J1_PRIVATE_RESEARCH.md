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

O SQLite opt-in contém dois grupos independentes de registros: o `UniverseSnapshot` presente e o `kraken_research_prices` preço-only com observação temporal/recibos. O arquivo é privado e reutilizável entre execuções, com replay idempotente e detecção de conflitos; cada inserção é transacional. **A partir da WU43**, o comando de coleta `capture_private_research` grava universo e TODAS as páginas de preço da mesma sessão em **uma transação SQLite**: se uma página posterior falhar, nenhum dado novo dessa sessão permanece, inclusive em banco existente. A regra histórica da WU36/WU38 permitia estado parcial legítimo e foi substituída pela decisão D71. Os métodos individuais continuam atômicos apenas para suas próprias chamadas. O comando só relata sessão completa após todos os recibos e qualidade revalidados. Se o arquivo foi criado pela execução e ela falhar, tenta remover esse arquivo.

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
O mesmo comando LOCAL e opt-in agora recebe `--max-price-symbols N` com N inteiro de 1 a 5 (default 1, mantém BTC apenas). Para ampliar a cobertura do registro v2 já comprovado por 10 contratos **correntes** Kraken, combinar `--registry expanded-10 --max-price-symbols 3` com `--database` em diretório privado e ambas flags explícitas de autorização. O coletor usa BTC como âncora obrigatória e escolhe mais dois contratos na ordem **real** do ranking USD do snapshot atual. Não fixa ETH/SOL se o mercado mudar; caso menos de 3 estejam elegíveis, consulta somente os presentes. No máximo dois GETs de instruments+tickers e N GETs chart (máximo absoluto 7), sem retry nem GET de fonte externa. Todos os dados de preço são validados antes de escrever; a persistência no SQLite preserva o contrato individual por página, mas **o coletor multi-perp agora usa a transação atômica de sessão WU43**. Resumo sem símbolos, preço/volume, DB path ou payload. Nenhuma instalação/cron/VPS foi autorizada. O owner-only workflow de diagnóstico usa SQLite TEMP apagado ao término e não cria feed para terceiros; direito de distribuição e volume financeiro ainda não validados.

## Evidência real e limites após WU38
O run owner-only [#40242292478](https://github.com/leandrosilveiradepaula/crypto-intelligence-agent/actions/runs/40242292478) em 2026-10-25T22:53:58Z confirmou `--registry expanded-10 --max-price-symbols 3`: 10 contratos elegíveis no snapshot Kraken corrente, **3 selecionados por orçamento**, **9 candles de preço 1h fechados** em SQLite TEMP, 5 GETs totais, cobertura completa. O job eliminou o diretório temporário com trap. Nenhum arquivo foi gravado na VPS ou em espaço persistente do usuário. A sonda não imprimiu os nomes das duas moedas adicionais além do BTC, nem preços/volumes; não inferir identidades dessas páginas a partir do ranking de outro instante. A CLI continua disponível exclusivamente sob opt-in local, sem cron/trade/redistribuição. Contrato financeiro completo, rights, ranking Top50 e histórico longo permanecem gates abertos no plano J1.

## J1/WU41 — Janela histórica explícita (sem automação)
A CLI aceita a opção adicional `--price-hours 24` para coletar, com o mesmo GET de chart por contrato, 24 candles de preço 1h completamente fechados. Default 3, máximo 72, sempre um buffer de 1h entre a última abertura esperada e a hora corrente. A opção é apenas capacidade local com duplo opt-in e arquivo 0600 fora do checkout, não um comando executado na VPS neste PR. Se faltar qualquer 1h ou houver conflito histórico, a página é rejeitada; não preencher preços ou converter `volume` bruto de Kraken em base/quote. A coleta local não é um serviço programado e não libera direitos públicos/comerciais, funding ou `ClosedCandle` canônico. Run temporário de conformidade aprovado só pelo comentário owner-only em #130 após revisão/CI/merge.

## J1/WU43 — Atomicidade da sessão local (sem alterar mercado)
A API `SQLiteKrakenPriceOnlyArchive.commit_research_session(snapshot,pages)` exige 1..5 páginas previamente validadas, símbolos distintos presentes no universo, mesmo intervalo/janela UTC e observação em ordem, e executa `UniverseSnapshot`, cada page de preço e seus recibos em um `BEGIN IMMEDIATE` único. Qualquer `DuplicateCandleError`, erro de input ou SQL provoca `ROLLBACK` de toda a sessão; a operação antiga por página `commit_price_only` e a gravação avulsa `save_universe_snapshot` preservam seus contratos. Banco existente também é protegido de snapshots e primeiras páginas órfãs após conflito em outro contrato. Capturas HTTP GET ainda são realizadas ANTES da transação, sem ordens nem market data bruto nos logs. Não há migration, rede extra ou permissão de publicação. Isso melhora integridade PRICE-ONLY; volume financeiro, Top50 histórico e direitos Kraken #36/#32/#48 continuam não homologados.


## J1/WU48 — auditoria local opcional Bybit sem rede, sem credenciais

O projeto agora possui `scripts/audit_private_bybit_json.py`, mas **nenhuma amostra real do usuário foi recebida**. Não confundir este método com o coletor Kraken. Ele aceita três arquivos privados no computador POSIX do titular: `manifest.json`, `instrument.json`, `kline.json`. Os dois últimos, quando disponíveis de origem e uso legitimamente permitidos, devem preservar a resposta V5 original de instrumento linear exato e kline 1h, sem incluir chaves, conta, headers de autenticação, histórico privado, carteiras nem ordens. O primeiro contém exatamente: `symbol`, `interval` (somente `1h`), `registry_variant`, `start_open_ms`, `end_open_ms`, `capture_started_ms`, `instrument_received_ms`, `kline_received_ms`, `capture_finished_ms`. Esses horários são **alegados pelo titular**, não certificados. Janela 3..72h, captura alegada <=30s, registro point-in-time; não alterar as datas para forçar aprovação.

Somente leitura, exemplo de uso FUTURO no diretório POSIX privado com arquivos 0600 e pasta 0700 **fora do checkout público**:

```sh
python3 -m scripts.audit_private_bybit_json \
  --manifest /caminho/privado/manifest.json \
  --instrument /caminho/privado/instrument.json \
  --kline /caminho/privado/kline.json \
  --allow-private-offline-input
```

Não executar este exemplo no GitHub Actions, VPS pública ou chat; nunca enviar material bruto ao GitHub ou compartilhar credenciais. O resumo JSON mostra apenas status de conformidade, IDs de crypto e intervalo, unidades documentadas, contagem e SHA-256, sem preços/volumes/contas. `offline_schema_conformance_passed_origin_unverified` não demonstra origem real, 24h completo, Top50, direitos, feed operacional ou autorização de trading. A modalidade local POSIX e a restrição de não persistir a saída foram escolhidas para prevenir vazamento acidental; Windows requer revisão de ACL específica antes de usar arquivos privados.


## Qualidade #186 — execução privada Kraken requer POSIX

O comando de persistência privada Kraken é **intencionalmente suportado apenas em sistemas POSIX com verificações reais de diretório 0700/arquivo 0600**. No Windows o coletor recusa antes de qualquer chamada de rede; `chmod` e `stat.st_mode` em Windows não certificam ACLs equivalentes. A compatibilidade Windows da pesquisa privada necessita desenho/revisão específica de ACL, não é habilitada pelos testes gerais de domínio Windows. O auditor Bybit local possui restrição POSIX equivalente. Não use esse recurso Windows por meio de bypass, proxy ou credenciais e não copie dados para o checkout público.
