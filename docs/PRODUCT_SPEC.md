# Especificação do produto

## D529 — pesquisa retrospectiva longa (24/11/2026)

D528 integrado em 7ae59574b1b21e6a132e083fe729df0def874f52, CI 45510118117/45510118137 SUCCESS; 38,6 GB livres na VPS via host_status; coleta real ainda pendente, MCP sem acesso owner. D529 reusa hipóteses D526 e saídas D517 em modo REST retrospectivo separado: indicadores contínuos por sequência, reset nas lacunas, RSI somente veto, 1h/5m, 24/48/72h, matriz padrão 420 cenários por partição. Partições 60/20/20 sem cruzamento de trajetórias; holdout exige parâmetros congelados e não deve ser usado para ajuste. Métricas por mês e regime, hashes e cobertura; coorte sobrevivente, não N50 histórico. Não equivaler ao reseed D526, carteira ou liquidação. Ver docs/J3_LONG_REPLAY_D529.md. Código e testes candidatos; CI e execução real pendentes. Próximo: coleta owner 90d e expansão 365d, replay desenvolvimento após aceite, 5m e universo mais amplo. Sem alteração J1, perfil, serviço, ordens ou custo.


## D528 — prioridade: base histórica de 90/365/730 dias (24/11/2026)

PO autorizou ampliação substancial da base, mantendo 50x e RSI como confirmação, sizing D527 adiado. Base de pesquisa independente do horizonte de cada trade. Primeira entrega: armazenamento privado separado da J1, coorte D451 atual congelada de 50 ativos (sobrevivência explícita, NÃO Top50 histórico), páginas opt-in 1h/5m até 1000 velas, shards de 30 dias, clipping após launch, backfill/SQLite/checkpoints existentes, leitura exata entre shards, ranking causal dentro da coorte e relatório de cobertura. 90 dias primeiro, estender para 365 (390 planejados) e 730 sem baixar novamente janelas completas. Sem alegar mercado completo/deslistados. Limites de rede/disco, sem retry automático nem publicação. Ver docs/J3_LONG_HISTORY_D528.md e issue #4. Próxima etapa: coleta owner real, adaptador D526 de replay retrospectivo de várias janelas, horizontes 24/48/72h, métricas por regime/mês e validação cronológica fora da amostra. Não falsificar D461/WS, não voltar à J1.


## Prioridade vigente — pesquisa estratégica em 50x (24/11/2026)

Decisão expressa do PO: manter 50x nesta etapa; adiar integralmente a frente de banca, margem e dimensionamento. D527 permanece no rascunho #753 (head b8a395ad4076f3eefb9731d78116ec791c508a1c) sem integrar nem publicar. D526 integrado em `b25175f88e562642830a5c1413ff6690523abca2`, CI 45486116138/45486115445 SUCCESS, RSI apenas como confirmação/veto do sinal original. A grade existente suporta 20 estratégias × 7 stops (50, 75, 100, 125, 150, 200, 250 bps) = 140 cenários, com referência 50x. Não criar outro motor ou repetir D524. Comparar controles e vetos, qualidade das entradas, stops antes TP1, recuperação posterior, MAE/MFE e resultado líquido pré-funding. Depois estudar pullback/retomada, compressão e amostras/horizontes 24/48/72h. Stops 200/250 bps são contrafactuais sem liquidação modelada, não aprovação financeira. Não alterar perfil ativo, J1, serviços ou ordens reais. D525 repinado exclusivamente ao D526, não D527; exige CI, revisão e gate explícito de publicação. Endpoint privado retorna 404 e execução owner via MCP indisponível; pesquisa real D526 ainda não executada. A próxima ação concreta é executar a bateria isolada D526 no histórico existente com os sete stops e devolver resultados, sem esperar release. Ver docs/J3_RSI_VETO_D526.md e docs/PAPER_RELEASE_D525.md.


## D526 — RSI como veto separado do gatilho (24/11/2026)

D524 revelou que o RSI integrado na transição de confluência multiplicou sinais e todos os 40 cenários com RSI avaliáveis foram negativos. Acrescentar hipótese separada de pesquisa, sem alterar perfil PAPER: RSI de Wilder somente após gatilho original e FR BTC aprovarem, podendo apenas vetar a entrada no mesmo instante. Controles pareados, 20 estratégias com rompimento e outras combinações, faixas de RSI configuráveis, contagens de sinais originais/vetados e respectivas coberturas, mesma grade de stops. Ver `docs/J3_RSI_VETO_D526.md`. Código D526 na branch `chatgpt/j3-rsi-veto-d526` (commit `a1662c5fd6ffc5fe73a50a194dfe7b8f96c0f5ea`), revisão/CI e execução real pendentes. A regra de confluência D523 permanece como hipótese distinta. Sem ordens, mudança J1, custo ou publicação; não atrasar a validação do instalador D525 por resultados desta nova hipótese.


## D524 — comparação simultânea de stops (24/11/2026)

A bateria swing D523 pode executar múltiplos stops em uma passagem de sinais e caminhos 5m, sem recalcular o motor para cada stop. Grid de 2..8 valores inteiros crescentes, editáveis; exemplos 50/75/100/125/150 bps. 18 estratégias × 5 stops = 90 cenários. CLI e painel/API privados reutilizam os dados e o perfil lido, sem gravá-lo, com a mesma cobertura e indicadores de qualidade D523. Não escolher vencedor nem alterar operação. Limites financeiros e temporais de D523 mantidos. `docs/J3_STOP_GRID_D524.md`.


## D523 — RSI do ativo e pesquisa swing (24/11/2026)

Pedido PO: RSI 14 independente da FR BTC, pesquisar melhor qualidade de entrada e stops mais largos para swing. RSI Wilder configurável (faixas LONG e espelho SHORT), opcional no motor D513, sem alterar perfis salvos. Matriz independente 18 estratégias (controles e pares RSI); stop de pesquisa independente do perfil, API/painel D522 e CLI; métricas stop antes TP1, primeira hora, toque posterior, positivos com stop e MAE/MFE de caminho integral. Detalhes e experimento em `docs/J3_SWING_RSI_D523.md`. Valores são hipóteses, não recomendação; 50x exige avaliação de liquidação e não permite pressupor que stop largo seja alcançável. Horizonte de vários dias e dados funding/mark/PIT/OOS continuam pendentes; não alterar J1, perfil ativo, serviço ou ordens reais.


## D522 — pesquisa por confluência acionável pelo painel

Permitir ao operador e ao agente executar a matriz exploratória de combinações sem alterar a estratégia em operação. Interface privada loopback existente, botão explícito para uma bateria com horizonte editável e relatório por combinação; padrão 25 estratégias. Reutilizar histórico complementar salvo, sem GET à Bybit. Uma execução por vez em processo separado, prioridade reduzida e timeout; manter o monitor de posições disponível. API com matriz validada opcional e cutoff explícito; sem comandos arbitrários ou ampliação de acesso. Resultado em memória, perde-se ao reiniciar ou iniciar nova bateria. Não confundir ordenação exploratória com vencedor financeiro; nenhuma ativação automática.


## D521 — Bandas de Bollinger configuráveis (24/11/2026)

Pedido explícito PO: acrescentar Bollinger ao motor de entrada e à pesquisa de combinações D520. Campo opcional `bollinger` em IndicatorSelection, desativado por padrão/ausente em perfis legados, período 2..120 (exemplo 20), multiplicador de desvio-padrão populacional 0,1..10 (exemplo 2, até seis casas decimais). Média central SMA dos fechamentos, bandas superior/inferior = SMA ± multiplicador × desvio-padrão populacional; somente velas fechadas. Dois modos selecionáveis: rompimento (LONG acima da superior, SHORT abaixo da inferior; neutro dentro); retorno (LONG quando o fechamento anterior estava abaixo da inferior anterior e o atual retorna para dentro das bandas atuais, SHORT simétrico a partir de cima; evento de uma barra). Bandas de largura zero não geram sinal. Confluência D513 exige concordância com EMA/SMA/Pivot ativos; não altera volume/cooldown/força relativa BTC nem regras de saída. Warmup apenas quando ativo, período+2 e limite de 122. Valores não são parâmetros otimizados. Compatibilidade: JSON antigo aceito sem mudanças; rollback a código anterior após salvar campo novo requer revisão do perfil.

Matriz exploratória D520 mantém as 15 hipóteses originais e adiciona oito: Bollinger isolado com FR (rompimento/retorno), SMA 20/50 + Bollinger, SMA 20/50 + Pivot + Bollinger (fatores 2 e 2,5), EMA 9/21 + Bollinger com/sem Pivot e SMA 20/50 + Bollinger retorno. Total 23 novas hipóteses + 2 controles, comparadas na mesma amostra 5m e mesmos custos. Nenhum parâmetro em produção alterado, sem OOS, funding/liquidação validados ou ordem real.


## D520 — pesquisa de combinações por confluência (24/11/2026)

Pedido explícito do PO: o agente deve propor e executar baterias de backtests de indicadores combinados (exemplo SMA 20/50 + força relativa + Pivot SuperTrend), medir frequência e direção de entradas, exemplos e resultados após custos, em vez de limitar-se a testar um indicador isolado. Reusar D435/D512/D517/D518 e a amostra congelada; não alterar o perfil PAPER. Matriz de hipóteses editável, inicialmente 15 combinações novas e dois controles de estratégia, não parâmetros hardcoded operacionais. Todos os candidatos usam volume/cooldown e força relativa 24h contra BTC; varia-se a família/periodicidade das médias, Pivot e intensidade da força relativa. A regra D513 de confluência na transição permanece; FR é filtro na hora da transição, não um gatilho posterior. Resultado após custos nos dois cenários 5m, cobertura comum, contagem LONG/SHORT, exemplos cronológicos, média e total, positivos/negativos, stop/parciais e perda >= margem. Ordenação descritiva por resultado médio no cenário adverso, separando amostras pequenas ou incompletas (mínimo inicial 20 trajetórias e 70% de cobertura, editáveis). Não é significância estatística nem escolha de vencedor. A amostra de 24h já foi vista e só serve à exploração; futuras hipóteses devem ser congeladas e avaliadas cronologicamente fora da amostra, incluindo funding, liquidação e riscos de carteira antes de qualquer conclusão financeira. Sem ordens reais.


## D513 — indicadores independentes por escolha do Product Owner (24/11/2026)

EMA, SMA e Pivot Point SuperTrend devem ser opções independentes e parametrizáveis na interface PAPER. O usuário pode ligar/desligar cada uma das três médias EMA e cada uma das três médias SMA, configurar os períodos (2..120 velas de 1h) e ativar/desativar Pivot SuperTrend, com período do pivô (1..50), período ATR (1..120) e fator ATR (0,1..100). Valores iniciais 10/30/60 e Pivot 2/10/3 são exemplos editáveis, não uma otimização nem uma recomendação. O modo personalizável `indicator_combo` é opt-in; perfis antigos `breakout` e `ema_cross` não são reinterpretados. Desligar todas as opções no modo personalizável suspende novas entradas, sem desativar a gestão de posições existentes. Salvar só vale para próximas sessões PAPER, não altera posição aberta, margem, alavancagem, stop ou ordem. J1 permanece intocada, sem trading real ou custo adicional.


## D487 — configuração PAPER pelo usuário, sem estratégia hardcoded (23/11/2026)

Decisão do Product Owner: períodos de indicadores, entradas e metas de saída são **parâmetros editáveis**, não decisões definitivas do ChatGPT. Preferir ciclos de produto completos (sinal → intenção PAPER → posição → parciais → encerramento), não mais ajustes de limiar sem resultado operacional. Modo de entrada continua **exclusivamente por vela de 1h confirmada**, com monitor de saída intra-hora. Na versão D487, **editor local e privado**, na porta loopback 8766, alterável por interface responsiva em português: EMA/ATR/extremos/volume/compressão/cooldown e perfil experimental explícito; margem/alavancagem para novas posições; stop, alvos e duas tranches, expressos na interface em retorno bruto sobre margem e convertidos em distância de preço de acordo com a alavancagem. Permite somar 100% em parciais e runner=0, ou reter parcela residual sem vencimento.

API D487 aceita alterações apenas com ação local explícita, POST same-origin e validação da política owner D453, diretório 0700, arquivo 0600, revisão SHA com bloqueio de conflito e troca atômica. Nenhuma operação de corretora, migração, execução de trading ou hot-edit de posição; perfil salvo é lido por **sessões PAPER futuras**. Tela inclui preview com pesquisa pública **REST já congelada** 50x24, usando o mesmo avaliador existente e filtro BTC, sem confundir pesquisa histórica com novo sinal WS/ordem. **Limite declarado:** EMA acima do histórico carregado (por exemplo 30/60 com apenas 24h) deve abster em vez de inventar candles. Cruzamento simultâneo de EMA 10/30/60 não é regra ativa ainda; sua integração deve usar histórico suficiente e o motor J2 existente, não outro gerador paralelo. O J5 instalado D423 permanece intacto (read-only, porta 8765); D487 é prévia separada, sem publicação pública. Não alegar utilização no app até serviço D487 efetivamente iniciado, testado e acessível.


## D482 — demonstração PAPER durável com preço público real (23/11/2026)

O Product Owner autorizou **explicitamente testar a gestão abrindo uma operação fictícia sem esperar o sinal horário**; a estratégia de entradas reais/PAPER não deve ser relaxada silenciosamente. `scripts/run_j4_persistent_public_demo_d482.py` abre, com opt-ins específicos, **uma** posição LONG/SHORT `BTCUSDT` etiquetada `EXPLICIT_PAPER_DEMO_NOT_J2_SIGNAL`: valida contrato público REST, recebe apenas cotação ticker Bybit após ACK WSS, aplica J3 custos e buffer mínimo de margem, ancora um **FILL totalmente fabricado** via AUTO4 D426, persiste o diário e manifesto owner-only 0600, valida restauração D425 e leitura J5 D446. **Nenhum sinal quantitativo aprovado, conta, ordem, dinheiro, fill de corretora, stop nativo ou prazo fixo de permanência.** Diretório deve estar vazio 0700 e owner não-root. Não desabilitar risco financeiro para forçar demonstração; caso mercado não ofereça cotação elegível, registrar abstenção. Seguir demonstrando monitoração intra-hora com o mesmo D444/D445 e saída reduzida PAPER; tudo isolado da J1 e do operador de pesquisa D453. A prova com dados públicos reais e a monitoração devem ser documentadas após executar este SHA, nunca inferidas do teste offline.


## D481 — escopo fechado de operação PAPER horária + gestão intra-hora (decisão do Product Owner em 23/11/2026)

**Entradas:** identificar e classificar novas oportunidades exclusivamente após o fechamento confirmado de cada vela de **1h** da Bybit para o universo elegível dinâmico N50, usando contexto BTC, estratégia e risco. A avaliação pode consumir ticks subsequentes para verificar preço, spread, profundidade, custo, margem e registrar uma entrada PAPER elegível, mas **não recalcula nem descobre novas hipóteses intra-hora**. A análise horária deve ter um resultado visível no aplicativo: candidatos/entradas elegíveis ou **nenhuma oportunidade** com estado e critérios de abstenção; não transformar ausência de sinal em falha nem forçar operações.

**Saídas:** para posições PAPER existentes, escutar **continuamente cotações públicas por WebSocket dentro da hora**, independentemente de elas continuarem no ranking N50, e avaliar stop-loss, take-profit, múltiplas realizações parciais, trailing e runner residual, inclusive entre os fechamentos de 1h. Um gatilho local não equivale a fill ou proteção nativa Bybit: exigir cotação posterior, latência e condições simuladas de BBO, manter idempotência, posição e custos. Enquanto o serviço estiver parado/degradado, não alegar cobertura de stop.

**Prioridade de entrega:** concluir um único caminho J2 → J3 → J4 → J5 com candles reais, entradas após a hora, ordens/fills **hipotéticos** e acompanhamento intrahora no aplicativo. **Proibido expandir agora** o escopo para rastreador de novas oportunidades em 1m/5m/15m, trades, livro profundo, ML ou novo motor alternativo. Não reabrir J1 nem trocar Bybit. A meta final continua automação de entradas e saídas após gates, sem ordens reais nem publicação permanente não autorizada.


## Objetivo
Plataforma de inteligência quantitativa para futuros perpétuos. **Produto-alvo: robô que detecta oportunidades, abre, acompanha e encerra posições automaticamente, sem confirmação manual a cada operação**, incluindo saídas parciais e residual; interface móvel para acompanhar, configurar e pausar. Desenvolvimento atual em PAPER, ordens reais somente após gate específico. Nenhuma promessa de rentabilidade.

## Contratos principais
- Universo dinâmico de contratos elegíveis; usar volume comparável, filtros de liquidez e histórico de elegibilidade para evitar viés de sobrevivência.
- Alavancagem global padrão 50x; valor gravado ao abrir cada posição. Alterar a configuração só modifica novas posições.
- Margem por posição configurável; número de posições variável conforme oportunidades e capital, não uma meta de 20/50/100.
- Motor de sinais com múltiplas estratégias, regimes do BTC, força relativa, tendência, compressão, rompimento, correções, volume, volatilidade, liquidez e derivativos.
- Planejador de saídas parciais: porcentagens da posição inicial OU do saldo restante, definidas explicitamente; permitir runner residual.
- Acompanhar exposição, correlação, custos, funding, margem, liquidação, posições, ordens automáticas, fills e resultados.
- **Produto-alvo D383: execução AUTOMÁTICA de entradas e saídas exclusivamente na Bybit V5 linear (perpétuos cripto USDT elegíveis)**, com risco pré-ordem, stops, realizações parciais, trailing, runner, reconciliação de fills e kill-switch. Binance e outras venues são apenas histórico de pesquisa; não implementar segundo executor. **Nesta fase somente engenharia offline/paper, sem ordens reais**.
- Pesquisa reproduzível: candles fechados, trajetória intrabar, taxas, slippage, funding, manutenção e liquidação, walk-forward, benchmark e fora da amostra.
- ML somente se melhorar desempenho validado. LLM e LangGraph opcionais para contexto e explicação, nunca fonte primária de compra.
- Interface em PT-BR, simples no celular: oportunidades, bot ativo/pausado, posições/ordens/fills, parciais, resultados, alertas e kill-switch.
- **Tempo de decisão/execução:** velas de 1h para contexto e pesquisa NÃO limitam entradas, monitoramento, stops ou saídas à virada da hora. O produto final usa dados intrahorários/mercado em tempo real, eventos de ordens e de posições, proteção nativa na venue quando homologada e motor automático orientado a eventos. Não prometer fills imediatos nem segurança com 50x; testar atraso, perdas de feed e custos em PAPER antes de live.

## Limites de implantação durante desenvolvimento
O modo `live` permanece desabilitado: nenhum POST de ordens com capital real antes de gate de segurança, risco, validação e autorização do Product Owner. Desenvolver primeiro em `offline_paper` e, após autorização específica, `testnet`. Sem dependência de serviços pagos ou credenciais reais nesta fase. Retorno líquido ajustado ao risco da carteira é mais importante que taxa de acerto ou percentual isolado sobre a margem. 50x é parâmetro de pesquisa, não garantia de segurança.


## Direitos de dados de mercado antes de lançar ou distribuir
A interface atual serve pesquisa e diagnóstico; a interface-alvo permitirá gestão de trading automático, o modo final de disponibilização (uso pessoal interno, painel privado para titular, acesso de terceiros ou serviço comercial) exige decisão do Product Owner quando for relevante para publicação. Acesso GET público/HTTP200 **não significa** autorização para redistribuir ou monetizar market data. O guia oficial Kraken informa que usos comerciais não pessoais de endpoints públicos requerem permissão prévia: https://docs-legacy.kraken.com/api/docs/guides/global-intro/#notices . Por padrão, **não lançar** produto público/comercial com dados Kraken nem exportar feeds/fixtures reais sem evidência de direitos aplicáveis e gate de release. Continuar desenvolvimento offline, com dados sintéticos, custo extra R$0 e sem ordens reais. Critérios: `docs/PROVIDER_RIGHTS.md`.


## Fronteira do protótipo matemático de saídas (J4/PRE1)
Existe um cálculo determinístico e sintético de fatias sobre quantidade inicial/saldo remanescente e piso residual. Isso não constitui conta, posição financeira, capacidade de ordem, trailing, execução nem corretagem homologada: as quantidades são abstratas e podem ser menores que o mínimo da exchange real. **Contexto histórico PRE1:** o cálculo não executava saídas; D77/D383 prevalecem para o produto final: saídas automáticas, alavancagem preservada por posição e captura de tendências. Nenhuma promessa de resultado ou J4 operacional aceita por essa entrega.


## Eventos manuais de saída: limite do protótipo de replay J4/PRE2
O replay de eventos atualmente é **apenas sintético e em memória**: contabiliza parcial de tranche somente quando há evento explícito, deduplica event_id idêntico em uma única execução e não simula preço de execução. Não identifica eventos duplicados com IDs diferentes ou falhas entre sessões; logo **não** constitui histórico auditável de posições reais, PnL, acompanhamento do usuário nem ordem manual enviada. Tais funções exigem transações, IDs confiáveis, preço, taxa, lotes, funding e risco aprovados. **Contexto histórico PRE2:** aquele replay não tinha executor; não representa o produto final. D77/D383 exigem operação automática, mantendo ordens reais bloqueadas até os gates autorizados.


## Pré-condição de registro de posição (J4/PRE3 — não operacional)
A opção de alavancagem global 50x e margens configuráveis agora possui um **contrato sintético imutável**: cada abertura fictícia copia o valor de alavancagem da configuração daquele instante, preservando o passado. Os valores de margem são abstratos e não implicam qualquer moeda, exposição, liquidação ou corretora real. Eventos fictícios de saída são vinculados à posição de pesquisa pelo ID, mas a deduplicação ainda funciona somente dentro do mesmo replay; não existem usuários, conta, ordens, ledger financeiro nem posição manual homologada. A UI/execução reais seguem fora do escopo até os gates J1/J3/J4.


## Pré-validação aritmética de lotes (J4/PRE4)
Existe um verificador para conferir se tranches e preenchimentos fictícios respeitam **passos e quantidades mínimas hipotéticas** informadas como fixtures. Ele não altera o plano nem arredonda valores para caber em lotes, e não deduz tamanho de contrato, mínimo notional, moeda do colateral, preço de execução, taxa ou direitos de distribuição. Mesmo uma saída `arithmetically_compatible` não é autorização de operar ou gerar alertas live. Dados reais e contratos por instrumento ainda dependem de validação externa, risco e J1/J3/J4.


## Pré-trabalho de trajetória intrabar J3/PRE1 — pesquisa, não backtest homologado
Um candle OHLC informa o intervalo do preço, mas não a ordem do extremo high e low. Um cenário que toca stop e target (ou liquidação hipotética) no mesmo candle não é contado como vitória, mesmo quando o candle fecha acima do target para uma posição LONG. Gaps de abertura não garantem execução no preço limite. O detector de pesquisa usa exclusivamente fixtures sintéticas, registra ambiguidade e não calcula risco financeiro, liquidacão real, custos, funding ou retorno. Critérios de aceite J3 (trajetória intrabar verificável, mark/liquidação, custo líquido e walk-forward) continuam pendentes.


## Pré-trabalho de custos financeiros J3/PRE2 — não representa retorno
Uma calculadora sintética separa **taxas**, **slippage adverso** e **funding assinado** em unidades abstratas de quote, com notionals e bps fornecidos explicitamente. Nenhum preço de preenchimento, moeda de margem real, alavancagem de corretora, contrato, troca cambial ou PnL foi definido. Um valor total negativo indica apenas possível crédito hipotético de funding acima de custos, não ganho financeiro. Dados reais, horários/tiers corretos de funding, impacto de mercado, liquidação e validação de risco deverão entrar na J3 operacional somente após J1/J2 aprovadas.


## J1/WU47 — histórico pré-D77/D383: candidatas de execução manual (26/10/2026 UTC)
**Nota:** esta seção descreve a hipótese abandonada de outubro; a decisão vigente D383 escolhe Bybit como venue única e D77 exige operação automática. Não usar o texto a seguir como requisito atual.
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


### J5/D301 — exibição de pesquisa, distinta do robô de ordens

A tela privada opcional de mercado N50 mostra exclusivamente métricas já observadas (retorno anterior, true range, volume, contexto BTC e rompimento da última barra) em PT-BR no celular. Nunca converter variação histórica em sinal/ordem ou misturar com posições PAPER. HTML sem rede/script e com aviso explícito de dados provisórios e 0 ordens. A futura interface do robô com contas/posições/execução continua exigindo J4/J6, autenticação e gate de produção separado.


## Entrega J5/MVP1 — console interativo local
Primeiro produto navegável real em `web/app/index.html`, responsivo e PT-BR: dashboard com estado de fonte explícito (offline até importação sanitizada), histórico N50 count-only, pesquisa J2 descritiva e gestão de posições PAPER hipotéticas em BigInt. Margem e leverage global inicial 50x afetam somente novos cenários; percentuais de saída podem tomar base inicial/saldo e runner reservado. Histórico PAPER local exportável e trava local não constituem ordens, stop nativo, liquidação provada nem kill-switch de produção. O produto final D77 continua automático; J5/MVP1 é laboratório/configuração, sem rede e sem deploy. `docs/J5_PRODUCT_APP_MVP.md`.


## J5/APP-SYNC1 — status de coleta com refresh local
O aplicativo PAPER já oferece atualização N50 em loopback (`127.0.0.1:8765`), somente se o servidor local read-only for iniciado explicitamente. A consulta usa o exportador sanitizado do journalctl e 24 slots; feedback de falha desconecta o indicador sem fingir sincronização. A abertura local `file://` permanece offline. Isto não equivale a aplicativo publicado, acesso autenticado pelo celular fora da VPS, sinal ou execução real; esses próximos passos exigem release e controle de acesso. `docs/J5_LOOPBACK_AUTO_STATUS.md`.

## J4 D388 — proteção PAPER de emergência como requisito de gestão automática (16/11/2026)

A J4 precisa oferecer stop automático **antes de atingir qualquer alvo** e preservar saídas parciais em tempo intrahorário. D388 introduz uma reserva `REDUCE_ONLY` PAPER de **saldo confirmado integral** (marcada `tranche_step=-1` no journal AUTO4 existente), disparada por `markPrice` Bybit, com segurança de ledger sob UNKNOWN/replays e sem preço de fill inventado. O stop possui precedência lógica sobre alvos; caso exista saída anterior não reconciliada, nova reserva é bloqueada e a proteção é declarada **não comprovada**. A implementação não representa stop nativo na corretora; antes de negociação real, provar proteção Bybit efetiva, modo de posição, latência e recuperação de desconexão. Detalhes em `docs/J4_PAPER_EMERGENCY_STOP_D388.md`.
