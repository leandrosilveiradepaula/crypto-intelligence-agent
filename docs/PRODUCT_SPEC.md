# Especificação do produto

## Objetivo
Plataforma de inteligência quantitativa que pesquisa entradas de alto potencial em futuros perpétuos e auxilia a captura progressiva de lucros em operações vencedoras. Nenhuma promessa de rentabilidade.

## Contratos principais
- Universo dinâmico de contratos elegíveis; usar volume comparável, filtros de liquidez e histórico de elegibilidade para evitar viés de sobrevivência.
- Alavancagem global padrão 50x; valor gravado ao abrir cada posição. Alterar a configuração só modifica novas posições.
- Margem por posição configurável; número de posições variável conforme oportunidades e capital, não uma meta de 20/50/100.
- Motor de sinais com múltiplas estratégias, regimes do BTC, força relativa, tendência, compressão, rompimento, correções, volume, volatilidade, liquidez e derivativos.
- Planejador de saídas parciais: porcentagens da posição inicial OU do saldo restante, definidas explicitamente; permitir runner residual.
- Acompanhar exposição, correlação, custos, funding, margem, liquidação, posições, ordens automáticas, fills e resultados.
- **Produto-alvo: execução AUTOMÁTICA de entradas e saídas** na venue escolhida (Binance USD-M ou Bybit V5 linear), com risco pré-ordem, stops, realizações parciais, trailing, runner, reconciliação de fills e kill-switch. **Nesta fase somente engenharia offline/paper, sem ordens reais**.
- Pesquisa reproduzível: candles fechados, trajetória intrabar, taxas, slippage, funding, manutenção e liquidação, walk-forward, benchmark e fora da amostra.
- ML somente se melhorar desempenho validado. LLM e LangGraph opcionais para contexto e explicação, nunca fonte primária de compra.
- Interface em PT-BR, simples no celular: oportunidades, bot ativo/pausado, posições/ordens/fills, parciais, resultados, alertas e kill-switch.

## Limites de implantação durante desenvolvimento
O modo `live` permanece desabilitado: nenhum POST de ordens com capital real antes de gate de segurança, risco, validação e autorização do Product Owner. Desenvolver primeiro em `offline_paper` e, após autorização específica, `testnet`. Sem dependência de serviços pagos ou credenciais reais nesta fase. Retorno líquido ajustado ao risco da carteira é mais importante que taxa de acerto ou percentual isolado sobre a margem. 50x é parâmetro de pesquisa, não garantia de segurança.


## Direitos de dados de mercado antes de lançar ou distribuir
A interface atual serve pesquisa e diagnóstico; a interface-alvo permitirá gestão de trading automático, o modo final de disponibilização (uso pessoal interno, painel privado para titular, acesso de terceiros ou serviço comercial) exige decisão do Product Owner quando for relevante para publicação. Acesso GET público/HTTP200 **não significa** autorização para redistribuir ou monetizar market data. O guia oficial Kraken informa que usos comerciais não pessoais de endpoints públicos requerem permissão prévia: https://docs-legacy.kraken.com/api/docs/guides/global-intro/#notices . Por padrão, **não lançar** produto público/comercial com dados Kraken nem exportar feeds/fixtures reais sem evidência de direitos aplicáveis e gate de release. Continuar desenvolvimento offline, com dados sintéticos, custo extra R$0 e sem ordens reais. Critérios: `docs/PROVIDER_RIGHTS.md`.


## Fronteira do protótipo matemático de saídas (J4/PRE1)
Existe um cálculo determinístico e sintético de fatias sobre quantidade inicial/saldo remanescente e piso residual. Isso não constitui conta, posição financeira, capacidade de ordem, trailing, execução nem corretagem homologada: as quantidades são abstratas e podem ser menores que o mínimo da exchange real. A regra geral de margem, alavancagem gravada na abertura e saídas **manuais** não foi alterada, nem o objetivo de capturar tendências. Nenhuma promessa de resultado ou J4 operacional aceita por essa entrega.


## Eventos manuais de saída: limite do protótipo de replay J4/PRE2
O replay de eventos atualmente é **apenas sintético e em memória**: contabiliza parcial de tranche somente quando há evento explícito, deduplica event_id idêntico em uma única execução e não simula preço de execução. Não identifica eventos duplicados com IDs diferentes ou falhas entre sessões; logo **não** constitui histórico auditável de posições reais, PnL, acompanhamento do usuário nem ordem manual enviada. Tais funções exigem transações, IDs confiáveis, preço, taxa, lotes, funding e risco aprovados. O produto continua com operações reais manuais e sem automação.


## Pré-condição de registro de posição (J4/PRE3 — não operacional)
A opção de alavancagem global 50x e margens configuráveis agora possui um **contrato sintético imutável**: cada abertura fictícia copia o valor de alavancagem da configuração daquele instante, preservando o passado. Os valores de margem são abstratos e não implicam qualquer moeda, exposição, liquidação ou corretora real. Eventos fictícios de saída são vinculados à posição de pesquisa pelo ID, mas a deduplicação ainda funciona somente dentro do mesmo replay; não existem usuários, conta, ordens, ledger financeiro nem posição manual homologada. A UI/execução reais seguem fora do escopo até os gates J1/J3/J4.


## Pré-validação aritmética de lotes (J4/PRE4)
Existe um verificador para conferir se tranches e preenchimentos fictícios respeitam **passos e quantidades mínimas hipotéticas** informadas como fixtures. Ele não altera o plano nem arredonda valores para caber em lotes, e não deduz tamanho de contrato, mínimo notional, moeda do colateral, preço de execução, taxa ou direitos de distribuição. Mesmo uma saída `arithmetically_compatible` não é autorização de operar ou gerar alertas live. Dados reais e contratos por instrumento ainda dependem de validação externa, risco e J1/J3/J4.


## Pré-trabalho de trajetória intrabar J3/PRE1 — pesquisa, não backtest homologado
Um candle OHLC informa o intervalo do preço, mas não a ordem do extremo high e low. Um cenário que toca stop e target (ou liquidação hipotética) no mesmo candle não é contado como vitória, mesmo quando o candle fecha acima do target para uma posição LONG. Gaps de abertura não garantem execução no preço limite. O detector de pesquisa usa exclusivamente fixtures sintéticas, registra ambiguidade e não calcula risco financeiro, liquidacão real, custos, funding ou retorno. Critérios de aceite J3 (trajetória intrabar verificável, mark/liquidação, custo líquido e walk-forward) continuam pendentes.


## Pré-trabalho de custos financeiros J3/PRE2 — não representa retorno
Uma calculadora sintética separa **taxas**, **slippage adverso** e **funding assinado** em unidades abstratas de quote, com notionals e bps fornecidos explicitamente. Nenhum preço de preenchimento, moeda de margem real, alavancagem de corretora, contrato, troca cambial ou PnL foi definido. Um valor total negativo indica apenas possível crédito hipotético de funding acima de custos, não ganho financeiro. Dados reais, horários/tiers corretos de funding, impacto de mercado, liquidação e validação de risco deverão entrar na J3 operacional somente após J1/J2 aprovadas.


## J1/WU47 — Binance/Bybit como candidatas de execução manual (26/10/2026 UTC)
O Product Owner informou que tem contas na Binance e na Bybit. **Isso não é evidência de acesso a futuros, habilitação regional de API, qualidade de OHLCV, alavancagem, ou autorização para usar credenciais.** Ambas são **candidatas**, nenhuma foi selecionada. O produto mantém execução **manual**, sem endpoints de ordens, chaves ou conexão à conta. Fonte de pesquisa não precisa coincidir com a venue de eventual execução, mas um sinal só poderá ser considerado executável após reconciliação de preço, símbolo, contrato, quote/settle, lot/step/min notional, funding, taxas, liquidez, limites de risco e disponibilidade na venue específica. Kraken price-only é pesquisa auxiliar e não certifica Binance/Bybit.
Binance USD-M já tem adaptador/fixtures offline, mas o run real anterior foi bloqueado HTTP451 (#19). Bybit linear V5 possui parser documentado de volume BASE/turnover QUOTE em USDT/USDC, porém o único run real foi restrito no primeiro GET (WU44, 0 candles). Não repetir nem contornar restrições. O relatório `scripts/j1_readiness_report.py` distingue as duas candidatas com flags `account_access_verified=false`, `live_signal_approved=false`, `manual_plan_approved=false`, `order_execution_enabled=false`. Essa enumeração não concede direitos de dados, não escolhe venue nem homologa J1 #2, #32, #36 ou #48. Custo adicional R$0; sem credenciais, dados de conta, ordens, deploy ou feed público.


## Correção explícita do requisito — D77, 26/10/2026 UTC
**Execução AUTOMÁTICA de entradas E de saídas é requisito obrigatório do produto final.** Substitui afirmações antigas de que o Product Owner executaria ordens manualmente. Binance USD-M e Bybit V5 linear são candidatas sem seleção final; não assumir que suas APIs são acessíveis pela infraestrutura atual nem que a conta tenha futuros habilitados. O robô deve controlar posicionamento, risco, ordens, confirmação de fills, stops, parciais sobre inicial ou remanescente, trailing, runner e encerramentos. O painel permite acompanhar/pausar e conferir decisões, não é necessário clicar em cada entrada/saída. `50x` continua configurável como parâmetro inicial de pesquisa e só será permitido em instrumentos/risco adequados. **Esta decisão de produto NÃO ativa ordens reais**: `offline_paper` por padrão, testnet condicionada, `live` desabilitado até autorização específica. O detalhamento normativo prevalente está em `docs/AUTOMATED_EXECUTION_SPEC.md`; parágrafos anteriores de protótipos J4 e WU47 que mencionam 'manual' descrevem o passado.


## J5/PRE1 #161 — primeira tela demonstrativa, não aplicativo homologado
Uma prévia mobile-first em `web/paper-demo.html`, PT-BR e inteiramente offline, expõe um único roteiro PAPER com indicadores de estado/ordens/parciais e ressalvas de fonte fictícia. Não requer conexão ou confirmação por operação — o produto FINAL continua sendo de entradas/saídas automáticas (D77) — mas esta tela **não controla um robô, não instala stops, não autentica posição, não executa kill-switch real e não permite negociação**. Nenhum PnL financeiro, cotação verdadeira, conta Binance/Bybit ou senha. A J5 somente poderá obter aceite depois de UI operacional integrada a dados/ordens legitimamente disponíveis, segurança, acessibilidade e homologação J6; não tomar a demo estática como release.


## J5/PRE2 #164 — HTML de leitura derivado de resultados PAPER, sem trading
O usuário poderá gerar um documento local pelo comando `python3 -m scripts.render_paper_dashboard --output /tmp/crypto-paper-view.html`. Ele lê **somente** o replay sintético em processo para as candidatas Binance USD-M/Bybit V5 e preenche os números da tela mobile PT-BR existente. Não consome mercado real, não recebe JSON externo, não possui ações/ordens, login, JavaScript, servidor ou rede. Um contrato versão `paper_dashboard_snapshot_v1` rejeita `live`/testnet, exposição de PnL, fonte que alegue mercado real, flags de envio de ordem, mudança de venue e totais inconsistentes. O arquivo exportado não é o dashboard operacional final nem prova de rentabilidade; J5 só poderá ser aceita após integração de dados financeiros e execução segura homologada.


## J5/PRE3 #166 — navegação por teclado no painel fictício
O protótipo de leitura `web/paper-demo.html` e a exportação HTML de PRE2 adicionam link de salto para conteúdo principal, tabela de saídas com foco por teclado, nome acessível e instruções de rolagem horizontal para telas estreitas. Conteúdo, cores, numeração fictícia e banner SIMULADO não representam sinais, saldos, lucro nem decisões reais. Melhorias de acessibilidade **não conferem** integração operacional a Binance/Bybit nem aceite J5; testes futuros em celulares e leitores de tela ainda são necessários.


## J5/PRE4 #168 — primeira inspeção de posição PAPER persistida, não painel de conta
A consulta explícita `--journal ... --position-id fixture_...` lê um arquivo SQLite de simulação **existente** em `mode=ro`, sem inicialização/DDL/conta. O exportador JSON/HTML versionado mostra abertura confirmada por fills, total de saídas preenchidas, reservas pendentes (inclusive UNKNOWN), saldo confirmado, quantidade ainda não reservada e piso residual, por posição individual e com hora UTC. Uma abertura somente é cotejada com AUTO2 se `--opening-order-journal` for fornecido; divergência bloqueia exportação. Ausência dessa opção é destacada; não misturar outras contas/venues por inferência. Não há PnL, preço de mercado, exposição financeira, negócio real, dados de conta, API, ordens ou controle de execução. J5 e J6 seguem sem aceite operacional até dados homologados, observabilidade, privacidade, segurança e integração de trading automático autorizada.


## J5/PRE5 #170 — seleção explícita de múltiplas posições fictícias
Uma tela em português pode apresentar várias posições PAPER provenientes de **um mesmo snapshot SQLite de leitura**, mantendo venue, símbolo e lado separados. Cada cartão e linha expõe seus próprios fills, reservas/UNKNOWN, saldo e checkpoint UTC. É incorreto somar unidades de contratos diferentes; a tela e o JSON não produzem número agregado de posições financeiras, lucro, alavancagem ou risco de carteira. A seleção exige IDs específicos, jamais varredura pública de contas. Não se trata de monitoramento financeiro prospectivo e a J5 #6 continua aberta até que existam fontes legítimas, autenticação, privacidade e conexão segura com execução automática aprovada.
