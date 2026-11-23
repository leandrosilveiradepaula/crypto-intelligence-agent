# Jornadas — plano de execução

## D499–D500 — primeira operação automática PAPER concluída e exibida (2026-11-23)

**Entrega comprovada em dados públicos Bybit, sem ordens reais:** no fechamento horário de **15h BRT / 18:00 UTC**, o motor J2/J4 gerou sinal **ARBUSDT SHORT** e registrou AUTO2 PAPER `FILLED` hipotético de **437,1 ARB** com margem configurada **0,99999738 USDT** e alavancagem registrada **50x** (`opened_at_ms=1795456814788`). Em **15:23:50 BRT / 18:23:50 UTC**, o monitor intra-hora registrou reserva REDUCE_ONLY de **STOP** (`tranche_step=-1`) e preenchimento **hipotético** de **437,10 ARB** ao preço público de referência **0,11489 USDT**; diário AUTO4 agora: `initial=437.1`, `remaining=0.00`, `filled_exit=437.10`, **1 saída STOP FILLED**, nenhuma saída TARGET, nenhum saldo residual. Resultado condicional, calculado pelo modelo com taxas/slippage antes de funding não verificado: **-0,3349488558 USDT**; **não é PnL financeiro real**, não houve ordens reais nem execução na corretora. Esta é a primeira comprovação do fluxo automático **candle real → sinal → PAPER OPEN → ticker intra-hora → STOP → CLOSED**. Os dois alvos de ganho (50% + 50% sobre a posição inicial) ainda NÃO foram atingidos/demonstrados automaticamente, logo não declarar essa parte aprovada.

**Correção de degradação pós-abertura:** serviço D498 havia reiniciado repetidamente após `ticker_failure_category=paper_execution_callback_failed`. Uma reprodução independente com WebSocket público real em **cópia isolada 0700/0600 do diário**, sem alterar posição original, capturou **`DataGapError: PAPER quote router conflicting replay`**. Em SHA **`cc7bd8eae4d85912e2fba091471f723dbd0bd2a2`**, D449 e fallback held-only D453 descartam **somente** o evento de cotação não causal `DataGapError` com contagem de abstenções, sem derrubar a observação inteira; erro de validação financeira inesperado continua fail-closed. No fallback, contagem de callbacks financeiros positivos é necessária para declarar `held_paper_lease_completed`. **17 testes focados PASS** na VPS. Mesmo diário PAPER preservado; código aplicado por fast-forward no diretório de trabalho da VPS e `cia-paper-research-d498.service` reiniciado às **18:25:46 UTC**. Serviço `active/enabled`, `NRestarts=0` até **18:31:17 UTC**, heartbeat recente; não equivale a cobertura ininterrupta nem a stop nativo Bybit. J1, painel e BTC-DEMO permaneceram ativos.

**Interface e histórico básico** em SHA **`c769eacae9382f02ea63125e54fe5c89ecaefea9`**: `scripts/serve_paper_profile_lab_d487.py`, HTML/JS apresentam posições automáticas **OPEN/PARTIAL/CLOSED**, razão STOP ou TARGETS, quantidades, preço de stop e dois alvos, margem/alavancagem de entrada, resultado PAPER condicional antes funding, e distinguem demo BTC legada sem inventar margem. Smoke owner na VPS: **0 posições automáticas abertas, 1 encerrada (ARB STOP)**, resultado `-0.3349488558` e `orders_sent=false`; demo BTC separada permanece parcial. Serviço `cia-paper-config-d498.service` relançado com novo código; `/api/profile`, `/api/paper-session`, `/api/paper-demo`, `/api/paper-operator` retornaram **HTTP200** em `127.0.0.1:8766`. Painel ainda **local/privado**, sem acesso externo móvel publicado.

**Prioridade seguinte, jornada única:** (1) manter operação contínua e observar próximo fechamento real sem reinícios; (2) resolver **reutilização de símbolo após posição integralmente encerrada**, pois manifest D425/D448 preserva rota histórica e bloqueia nova posição da mesma moeda, mantendo histórico no SQLite sem ordens fictícias; (3) comprovar duas saídas parciais + encerramento automático num próximo sinal elegível, sem forçar candles ou alterar controles; (4) disponibilizar painel ao celular com autenticação e acesso mínimo, sujeito aos gates aplicáveis. Não voltar à J1 nem abrir frente paralela de indicadores/ML. PR de desenvolvimento #734 continua revisável; CI do commit final requer conferência antes de merge. **Nenhuma publicação de produção e nenhuma ordem real.**


## D495–D498 — jornada integrada PAPER operacional e reinício após boot (23/11/2026)

**Priorização de produto:** uma única experiência, **sinal após candle 1h confirmado → entrada PAPER → monitoramento intra-hora → stop/alvos/parciais → histórico no painel**, sem estratégias novas, ordens reais ou custo. O bloqueio reconhecido em D493 era a falta de supervisão contínua de futuras posições AUTO2 depois da lease horária. D453/D449 já possuem, no mesmo operador, roteamento de posições abertas com `enable_hypothetical_exit_fills=True` e fallback held-only na falha da pesquisa N50. Substituído o antigo timer independente `cia-d493-paper-hourly.timer` por **um único motor D453**, evitando dois escritores simultâneos no mesmo journal. O código é fixado no SHA **9399e9096306e34386205eeba38757d66bdda157**, perfil owner `strategy.json` validado, capital fictício 1 USDT por posição e alavancagem inicial 50x, perfil experimental Bybit público, sem real money, sem alteração em J1. Lease WSS de **3590s**, `--max-cycles 1`, `Restart=always` com 8s entre processos para ler NOVA configuração no início da lease seguinte; se pesquisa degradar, fallback de posições existentes por ticker público. Fonte de preço e fills permanecem **não verificados na corretora**; não alegar cobertura de stop nativo ou monitor ininterrupto.

**Tela J5 de pesquisa D497** (código SHA **ef15287c70e0ad7f779ac9189ca5bfe7a659279f**) passou a mostrar status fresco D456 do operador, intenções com status/fill, posições de diário owner D446 com unidades iniciais, restantes e já saídas, e em bloco separado a posição BTC demonstrativa D482. Permanece no **localhost 127.0.0.1:8766**, sem acesso público/mobile habilitado; o antigo J5 8765 não foi alterado. O endpoint `/api/paper-operator` usa o leitor D456 de TTL para não declarar conexão quando o status estiver expirado, e /api/paper-demo é rotulado **entrada inventada**, não sinal J2. UI não apresenta rentabilidade real.

**Persistência após reinício:** três unidades PAPER internas versionadas em `deploy/vps/paper_research/` (commit **4663c4eadcd3bf84e74bd175f9e7bd779f3c7bad**) foram conferidas com `systemd-analyze verify`, instaladas em `/etc/systemd/system` com owner UID999, `NoNewPrivileges`, CPU/memória limitados, `ProtectSystem=strict` e permissões owner. Unidades `cia-paper-research-d498.service`, `cia-paper-config-d498.service` e `cia-paper-btc-demo-d498.service` foram **enabled + active** às **16:50 UTC**, zero restarts e `Result=success`. O timer J1 permaneceu **active** e J5 preexistente 8765 respondeu HTTP200. HTTP200 também verificado para `/`, `/api/profile`, `/api/paper-session`, `/api/paper-demo` e `/api/paper-operator` na interface privada. O diário BTC separado mostrou **0,004085902003 BTC inicial**, **0,00204295100150 BTC residual (50%)** e `orders_sent=false`, a partir de fills hipotéticos do D483. O operador PAPER reportou `observing_public_lease`, heartbeat válido e `real_orders_sent=false`; **nenhuma nova posição automática estava preenchida**. Os três serviços estão configurados para subir após reboot; **reboot real ainda não foi testado** (não reiniciar VPS inteira apenas para prova).

**Próximo aceite funcional obrigatório:** concluir coorte pública das **14h BRT (17:00 UTC)** com o novo operador D498, registrar frames/hipóteses e eventuais intenções/fills, conferir que toda posição criada recebe cotações/saídas depois da hora, sem assumir resultados quando não houver sinal. Caso não haja sinal, aguardar próxima coorte e acompanhar integridade do operador; não adulterar candles, não forçar sinais para alegar sucesso. Próxima entrega de produto: disponibilizar acesso móvel seguro com controle de acesso e interface de histórico detalhado, sujeito ao gate aplicável para publicação externa. Não reiniciar J1, não publicar painel sem autenticação, não mudar parâmetros financeiros automaticamente.


## D445/D446 — positions multicontrato e interface ligada ao SQLite

O worker D444 passou de BTCUSDT para até 50 contratos de posições PAPER já mantidas (D445), mesmo que fora do ranking N50, usando scan REST paginado e o mesmo AUTO4. Para o usuário visualizar o resultado sem importar arquivos, D446 adiciona leitura owner-only do mesmo diário em transação SQLite ro e alimenta o console em português no loopback com saldos e reservas PAPER. O navegador continua separado das simulações locais e não envia ordens. Ainda falta colocar o worker em execução contínua na VPS, ampliar o motor de entrada J2 para o universo dinâmico N50 e provar retorno ajustado ao risco J3, sem transformar CI em comprovação de rentabilidade.


## D445 — múltiplas posições PAPER sem depender do N50 (20/11/2026)

Implementado código J4 capaz de acompanhar todos os contratos de posições existentes no arquivo AUTO4 (limite 50) numa mesma assinatura WS, inclusive aqueles fora do ranking corrente. A lista vem do manifesto privado D425 em cada ciclo; a elegibilidade de *monitorar posição já aberta* independe da classificação de oportunidades da J2. REST usa paginação limitada para verificar o instrumento, não per-symbol GET; D443 foi generalizada com compatibilidade do piloto BTC, e D444 chama a nova rotina multicontrato. Testes cobrem BTC e ETH simultâneos no mesmo SQLite com parcial, stop protetivo, nenhuma redução artificial por ticker, replay idempotente e caminho sem opt-ins. **Não implica nova posição, sinais autorizados nem cobertura comprovada.** Sem merge/deploy/VPS, sem J1 ou ordens reais. Próximo marco de desenvolvimento: seleção N50 dinâmica como fonte de *novas* oportunidades e J3 prospectivo/OOS com custos reais de pesquisa; worker de posições já não depende desse ranking.


## D444 — desenvolvimento de worker PAPER em ciclo contínuo (20/11/2026)

O código passou de sessões J4 finitas isoladas para um **worker de ciclo contínuo** com D443, reutilizando D425/D390/D391/AUTO4 e a posição PAPER persistida. Possui reconexão/backoff, orçamento por lease, limite de degradação, lock do worker e estado owner-only para interface futura, com CLI opt-in. A cada novo ciclo preserva journal/ordens PAPER; só declara último lease saudável quando há cotação pós-ACK válida. Limites: ainda BTCUSDT, não há serviço implantado, a operação real não foi demonstrada, e não há cobertura ininterrupta/ordem real. Nenhum diagnóstico ou mudança na J1. Próximo marco de produto: conectar worker às rotas de todas as posições existentes e seleção N50 dinâmica; depois interface J5 com estado terminal/stale e sinal J2/J3 validado. Documento `docs/J4_CONTINUOUS_PAPER_MONITOR_D444.md`.


## D443 — J4 PAPER persistido, cotação pública BTC, sem dependência da J1 (19/11/2026 UTC)

Entrega codificada na mesma branch/revisão draft de J2/J3/J4: D443 carrega rotas PAPER existentes via D425 e mantém o lock de exclusividade, valida BTCUSDT em REST D441 e usa D390/D385/D386 para alimentar apenas o D391/D389/AUTO4. Diferentemente da demonstração D442 que descarta a posição fictícia, D443 preserva o **arquivo de posição PAPER** e a reserva REDUCE_ONLY ao fim de uma sessão FINITA. Os testes verificam (em SQLite de teste) parcial, stop-first, ausência de fill por ticker e não duplicação no reinício. Sem diagnóstico/alteração da J1, ranking N50, fill real, lucro, proteção de stop nativo ou daemon 24x7. Os gates de CI para o HEAD final e uma futura captura pública real ainda precisam ser concluídos; PR permanece draft. CLI com cinco opt-ins em scripts/run_j4_held_btc_paper_d443_once.py. Prioridade seguinte: liveness/reconexão 24x7 J6, N50 dinâmico/posições fora do ranking, sinais J2 validados OOS e J3 custos/risco realista, sem autorizar ordens.


## J2→J3→J4 D442 — triagem de custos e margem no fluxo PAPER (19/11/2026)

Integração de **um único contrato de pesquisa** BTCUSDT, desacoplada da J1 e restrita a uma sessão pública finita: D441 REST para metadados atuais → D385/D386 ticker ACK/snapshot/delta → J3/PRE2 custos explícitos + veto de stop hipotético que já exauriria a margem → D426/D391/D389/AUTO4 para abertura declaradamente fictícia e reserva de saída automática sem FILL inferido. Sem nova estratégia, ranking N50, orders, testnet, mudanças VPS ou aceitação de retorno. CI/verificação e prova pública ainda são gates separados. Documento: `docs/J2_J3_J4_BTC_SHADOW_D442.md`.


## J5/J6 D432 — projeção local sem importação manual

Uma execução offline pode publicar o relatório integrado para o Console loopback já existente, que o lê automaticamente com `fetch` somente em `127.0.0.1`. O artefato é uma projeção de leitura, owner-only e fail-closed; não transforma a demo em supervisão contínua nem em PAPER prospectivo.

## J5/J6 — leitura do ciclo PAPER integrado

O Console J5 pode importar o artefato sanitizado da demo J6 PRE9 (`j6_full_offline_paper_lifecycle_v1`) e expor em PT-BR o ciclo de abertura, parciais, runner, reinício e a falha de proteção. A tela é uma projeção local, sem writer, sem WebSocket, sem PnL financeiro e sem alegação de supervisão contínua.

| Jornada | Entrega verificável | Dependências | Issue |
| --- | --- | --- | --- |
| J0 Fundação | Especificações, decisões, arquitetura, backlog e CI documental | Repositório | #1 |
| J1 Dados | Coleta de perpétuos, histórico, qualidade, persistência e conformance | J0 | #2 |
| J2 Entradas | Indicadores, regimes, estratégias e seleção causal; projeto de gatilhos intrahorários automáticos após validação | J1 | #3 |
| J3 Pesquisa | Backtest, funding, slippage, alavancagem, liquidação e validação | J1 e J2 | #4 |
| J4 Winner Management/Execução | Ledger de ordens/fills, entradas/saídas automáticas durante a hora, parciais, stops, trailing, runner e reconciliação orientada a eventos | J2 e contratos de J3 | #5 |
| J5 Produto | Interface PT-BR, posições, histórico, alertas, estado do bot e kill-switch | J2 e J4 | #6 |
| J6 Homologação | Paper trading contínuo, testnet autorizada, incidentes e gates de eventual live, sem ordens reais na homologação inicial | J1–J5 | #7 |
| J7 Evolução | ML e contexto ampliado, somente com melhoria validada | J3 e J6 | #8 |

**Venue operacional D383 (16/11/2026): Bybit V5 linear como fonte primária e destino exclusivo de ordens automáticas.** O N50 WS de 1h D381 continua isolado; J2 #677 adicionará feed público contínuo sem tocar o journal owner e J4 #676 desenvolverá saídas automáticas PAPER intrahorárias. Testnet/live sempre sujeitos a gates próprios e autorização explícita. Ver `docs/BYBIT_V5_ARCHITECTURE_D383.md`.

## J1 — Work units
- WU1 #9 / PR #12: adaptador read-only e contratos, integrada.
- WU2 #13 / PR #14: backfill e SQLite com integridade, integrada.
- WU3 #15 / PR #16: pipeline CLI e auditoria offline, integrada.
- WU4 #17 / PR #18: relógio remoto e gate de diferença, integrada.
- WU5 #19: conformance Binance e evidência de HTTP 451, permanece aberta sem feed live homologado.
- WU6 #23 / PR #24: Kraken Futures independente, GET instrumentos HTTP200 (run 40198042787), 231 instrumentos e 213 candidatos heurísticos; concluída, sem troca de venue.
- WU7 #25 / PR #26/#27: schema real instrumentos/tickers/candles BTC Kraken, run 40198745112 SUCCESS, 3 GET200; encerrada, ainda sem Top50 crypto.
- WU8 #28 / PR #29: taxonomia Kraken observada em run 40199111677 (xStocks com tradfi=false), concluída.
- WU9 #30 / PR #31: seletor Kraken crypto-only fail-closed por registro versionado externo, Decimal USD, CI 115 testes, integrada; não produz Top50 real sem registro.
- WU10 #32 / PR #33: infraestrutura de registro de identidade/sha256 e point-in-time integrada, CI 135 testes; issue aberta para fonte/licença de ativos reais.
- WU11 #34 / PR #35: parser Kraken OHLC fechado UTC, volume bruto não verificado, integrado com 149 testes offline.
- WU12 #36 / PRs #37/#38: diagnóstico real do volume/ticker, run #40201868577 (2 GET HTTP200, 24 barras fechadas); **unidade base/quote ainda não comprovada**, issue aberta.
- WU13 #39 / PR #40: parser Decimal exato compartilhado para volume bruto documentado int64/real decimal-string, integrada, 169 testes offline, run live #40201868577, issue encerrada.
- WU14 #42 / PR #43: gate de 50x global versus cap por instrumento/exposição agregada Kraken, integrado SHA `3f1e829467ada401e607ab6d857751f75ae2903d`, CI 185 testes; só pesquisa.
- WU15 #44 / PR #45: Decimal exato desde JSON e seletor de ticker Kraken sem float financeiro, integrado SHA `c1d2c714d30daefe76804d1ed8d1792b919f8fee`, CI 197 testes offline.
- WU16 #46 / PR #47: cliente Kraken público opt-in GET-only, Decimal/exclusão xStocks, OHLC staging fechado, integrado SHA `6d5b37aba154b0fb6a950fbffa4ba3e18d01410e`, CI 213 testes offline/11 docs.
- WU17 #48 / PR #49: matriz de direitos de dados Kraken e gate de release integrada SHA `4d06ce7fee2ddb459fbf08a7efa98d6d2bff4997`, CI 213 testes/12 docs; issue permanece aberta para eventual permissão externa aplicável.

- WU18 #50 / PR #51: parser Bybit V5 linear de OHLCV sintético com volume-base e turnover USDT/USDC, integrado SHA `6f147844a514f2b83b29084fb3bc5d4b2377355d`, 229 testes offline/12 docs; nenhum GET ou direito comercial adquirido.

- WU19 #52 / PR #53: gate técnico de finalidade/provedor/dataset integrado, merge `f19ce8b854bd024e22ccaf6bc6b0d276b70efec2`; CI #40205837293 SUCCESS, 240 testes offline segundo revisão.
- WU20 #54 / PR #55: relatório offline conservador de prontidão J1 integrado SHA `7c0642d2d2769a8d12f5651af3f7280fce06ed88`, CI #40209121605 SUCCESS; nenhum Top50 real ou OHLCV canônico aprovado.
- WU21 #56 / PR #58: validador offline de proveniência, digest, tempo e unidade cotada por provedor integrado SHA `c73817ddda007355696ed0649b43c6ca59da9fcf`, CI #40212786207 SUCCESS; nenhuma alegação de dados live, direito ou unidade se torna prova.

- WU22 #60 / PR #61: parser OKX V5 SWAP offline, volumes contratos/base/quote + confirm documentados, integrado SHA `ee8c36d09a90192cbf5220c10ec28b876852508c`, CI PR #40214317197 SUCCESS (279 testes e 12 docs). Nenhuma identidade crypto-only, licença de redistribuição, feed live ou troca de venue validada.

- WU23 #63 / PR #64: manifesto Vike keyless validado no run real `40215045758` job `121234257255` SUCCESS (SHA256 `9329c928aba6fc710a981ee9f985a75006af61147ac887bd960a544a6812ce7a`), issue fechada para diligência de manifesto. Parquet, licença upstream e Top50 não validados.

- WU24 #69 / PR #70: pesquisa de contrato nativo Hyperliquid /info, perps e candles somente por fixtures, integrada SHA `49458f5db870651035d77c2470fe62386cfab652`; CI PR #40217228473 SUCCESS (338 testes offline/12 docs). Não comprova unidade de volume, licença, 5.000 candles reais, identidade crypto-only ou execução. Não muda venue operacional; issue encerrada.

- WU25 #72 / PR #73: run real `40218132668` job `121243633007` FAILURE após primeiro POST /info, `invalid_provider_schema`/1 request; nenhum candleSnapshot executado. Origem do desvio não demonstrada sem corpo de resposta, issue segue aberta sem repetir sondagem.

- WU26 #75 / PR #76: audit read-only de 54 runs issue_comment do GitHub Actions, recuperados IDs/logs originais de Vike e Hyperliquid; CI #40219481048 SUCCESS (378 tests, 12 docs), auditoria #40219481021 SUCCESS, merged SHA `9d20a34404146f3ee7a8290542cd46d519dfb7c7`, issue encerrada. Nenhum novo GET/POST de mercado ou permissão de escrita.

- WU27 #78 / PR #79: correção offline de potencial falso negativo estrutural ao validar metadata nativa Hyperliquid. Integrada SHA `da62b41f69596c756d04cc5188b755bfaa97f862`, CI #40221224643 SUCCESS (387 testes/12 docs), issue encerrada; BTC estrito, outros instrumentos inertes, diagnóstico seguro. Causa do run #72 não comprovada, nenhum novo POST autorizado.

## Preparação independente de J2 (J1 permanece aberta)
- J2/PRE1 #66 / PR #67: motor matemático offline de indicadores causais somente para `ClosedCandle` sintéticos, integrado SHA `cf1c4cacffa4f5b46475a73dcc6bc9f5631b2e5d`, CI #40216432146 SUCCESS (315 testes, 12 docs). Sem habilitar estratégias, backtest, negociação ou antecipar aceite J1/J2; issue encerrada.

## Preparação independente de J3 (J1/J2/J3 operacionais ainda não homologadas)
- J3/PRE1 #94 / PR #95: detector de toques de barreiras em OHLC SINTÉTICO, com gaps/ambiguidade e liquidação hipotética, integrada SHA `3a30150268d6ead7daabe16884827b655b5b1e7c`, CI #40229271296 SUCCESS (**548 testes offline**, 12 docs); issue encerrada, J3 #4 segue sem aceite.
- J3/PRE2 #96 / PR #97: custo hipotético de fees, slippage e funding assinado em quote ABSTRATA, integrada SHA `ea13ea60c617eb57973a6b6e708b06fc325afc96`, CI #40229681278 SUCCESS (**577 testes offline, compileall, 12 docs**), issue encerrada. Resultado NÃO é PnL, taxas reais ou backtest validado; J3 #4 permanece aberta.

## Preparação matemática independente de J4 (J1/J2/J3 e J4 operacional permanecem abertos)
- J4/PRE1 #81 / PR #82: percentuais INITIAL_POSITION/REMAINING_BALANCE e runner em unidades sintéticas, código integrado SHA `c4f6b94fd5a89724185b9a486818a6c8fa84adf0`, CI #40223997038 SUCCESS (**414 testes offline, 12 docs**). Issue encerrada; sem ledger, PnL ou ordens.
- J4/PRE2 #83 / PR #84: replay offline de eventos manuais FICTÍCIOS com IDs idempotentes apenas em memória, progresso de tranche, timestamp e controle de overfill; código integrado SHA `f051ab5c681bb9b4bd15e0384fb779a142330475`, CI #40224464764 SUCCESS (443 testes offline, 12 docs), issue encerrada. Não é contabilidade financeira real, preço de execução, ordem ou aceite J1/J3/J4.

- J4/PRE3 #86 / PR #87: posição fictícia com leverage_at_open e replay PRE2 vinculado, merged SHA `afb034d3435162402af673a8946bb2d747950326`, CI #40225049332 SUCCESS (473 testes offline, 12 docs), issue concluída. Não atesta posições reais.
- J4/PRE4 #88 / PR #89: auditoria de step/min-exit/residual por regras Decimal **hipotéticas** em planos e fills PRE1/PRE2/PRE3, integrada SHA `677f0c299cbfc1b0dc772f6d5d110a63c277dea9`, CI #40225440872 SUCCESS (**502 testes offline**, 12 docs), issue encerrada. Nunca arredondar nem indicar executabilidade na venue. J4 #5 segue aberta, sem aceite operacional.

- J1/WU28 #91 / PR #92: auditoria fail-closed do escopo documental Kraken Futures PF_ versus Kraken Spot OHLCVT e Derivatives US CME/Bitnomial, integrada SHA `d3af3088088c7e7f638cb745ca5848ddbb2b9a43`, CI #40227134838 SUCCESS (515 testes offline/12 docs). Issue encerrada, sem resolver fonte independente crypto-only, unidade de volume ou licença. J1 #2 e #32/#36/#48 permanecem abertas.

- J1/WU29 #99 / PR #100: proteção fail-closed de inconsistência entre símbolo PF_ e base/pair Kraken com alias oficial XBT→BTC, merged SHA `2fcc768ea878ce1a78060fbb9abb5be7bbffb97a`, CI #40231112282 SUCCESS (**591 testes offline**, 12 docs), issue fechada. Não prova registro crypto-only, volume financeiro ou Top50 real.

- J1/WU30 #101 / PR #102: `CryptoRegistryHistory.append` revalida manifesto v1 e SHA/evidence derivados mesmo para dataclass direta, merged SHA `e7f62a5fd56d1cc30ee84238cb313d18a029d9d1`, CI #40231467471 SUCCESS (**610 testes offline**, 12 docs), issue fechada. Autenticidade externa/Top50 permanecem bloqueados; J1 #2/#32/#36/#48 abertas.

A J1 só termina com aceite e evidência; testes sintéticos, CI verde ou ausência de erros de código não comprovam dados live confiáveis nem lucro. Seguir AGENTS.md: avançar sem pedir "prossiga" por microtarefas.


- J1/WU31 #104 — defesa OFFLINE contra variantes textuais de categorias TradFi no seletor Kraken, sem aceitação positiva de crypto-only; PR/CI pendentes nesta etapa, J1 bloqueada por #32/#36/#48.

- J1/WU32 #107 — experimento mínimo privado de conformidade OKX BTC perp, reutilizando parser WU22 com até dois GETs e três candles fechados, sem direitos para release, identidade cripto aprovada ou `ClosedCandle` canônico. PR #108 integrada SHA `9b66a359d1fa1d7a3ce83f66e1e002aa825de354`, CI #40236541641 SUCCESS (626 testes). Primeiro owner-run #40236605217 falhou antes de GET por import no entrypoint; fix módulo em andamento, J1 não homologada. Não concluir J1 por um único BTC.


- J1/WU33 #110 — PR #111 merged squash SHA `9f364a244bedba42803ca9803585023777813bb1`, CI #40237458174 SUCCESS (**633 testes offline, compileall, 12 docs**); seed BTC/ETH real com duas referências por ativo, revisão documental assistida por IA, sem Top50/rights.


- J1/WU34 #112 CONCLUÍDA como preço OHLC real de pesquisa: PR #113 merged `87b3f96653f97ef05798e918686b7fbe951622c2`; correção inclusive-`to` PR #114 merged `e7a5c21c639b14917216dc30df001daa083cfe0f`, CI #40237998812 SUCCESS (652 testes), **owner-run #40238058772 SUCCESS**, 1 GET e 3 candles preço PF_XBTUSD/1h válidos em SQLite TEMP com cobertura completa. Sem volume canônico nem retenção de dados/rights. Issue #112 fechada.

- J1/WU35 #115 CONCLUÍDA como seleção corrente BTC/ETH com dados REAIS Kraken: PR #116 merged squash SHA `7d54f5b13a1430d94cc9344781d8a63035bafbce`, HEAD revisado `01fa73fe2b88b2ecd74fb68b3c194268e0b523c0`, review #5645560006, CI PR #40238326403 SUCCESS (**663 testes offline, compileall, 12 docs**) e pós-merge #40238366580 SUCCESS. Owner-run #40238374774/job #121304703192 SUCCESS: 2 GETs, 231 instrumentos observados, 2 elegíveis BTC/ETH e 229 excluídos; snapshot atual SQLite TEMP roundtrip, sem dados retidos ou publicados. Issue #115 fechada, não é Top50 nem OHLCV.
- J1/WU36 #117 CONCLUÍDA apenas como desenvolvimento local: PR #118 merged `4d6ba02ea61ceeb64fe65ae4ea04c37d0972ea6d`, HEAD `6c286d302b92757bfe0339badfe5d5671cd10859`, review #5645586105, CI PR #40238785901 SUCCESS (**675 testes offline**, compileall, 12 docs), pós-merge #40238834784 SUCCESS. CLI privada integra GET-only Kraken BTC/ETH e 3 candles BTC price-only no mesmo SQLite LOCAL fora do Git e sem cron; nenhuma execução combinada live ou VPS realizada, duas provas anteriores separadas #40238058772/#40238374774 continuam evidências. Registro para no máximo duas bases, direitos/volume e Top50 histórico ainda bloqueados; J1 #2/#32/#36/#48 abertas.


- J1/WU37 #120 CONCLUÍDA: PR #121 merged SHA `c967d244c4ce289387a8c381f331e51dcfaf292c`, HEAD revisado `1a555238d8209cf9e8c65716e271fbd5c1af56fb`, review #5645747468, CI #40241827002 SUCCESS (**685 testes offline**, compileall, 12 docs), CI pós-merge #40241879286 SUCCESS. Owner-run real #40241888934/job #121315259119 SUCCESS 2026-10-25T22:48:27Z: 2 GETs Kraken, 231 instrumentos, **10 elegíveis, 221 excluídos**, SQLite TEMP roundtrip; zero market data retido. Registro SHA `a95179a342289833f3b14f0c2442163acdcb32f1ca0c9569fa01adeaa3534746`; issue #120 fechada. J1 #2/#32/#36/#48 abertas.
- J1/WU38 #122 CONCLUÍDA como conformance REAL de três páginas price-only em uma sessão: PR #123 merged SHA `42887e8338bc45e65cc58f5f32cf0ccbf8034d6b`, revisão HEAD `8ed058a27f230e80e142fa2c4721aab3de5e471f`/review #5645766424, CI #40242225054 SUCCESS (**692 testes offline**, compileall/12 docs), pós-merge #40242283400 SUCCESS. Owner-run #40242292478/job #121316477151 SUCCESS às 2026-10-25T22:53:58Z: 5 GETs Kraken, 3 contratos crypto elegíveis escolhidos (BTC e 2 pelo ranking real), 9 candles 1h fechados price-only em SQLite TEMP, qualidade completa, nenhum volume financeiro canônico. Issue #122 fechada; sem VPS/release/Top50 histórico/direitos comerciais/trading; J1 #2/#32/#36/#48 abertas.

- J1/WU39 #125 CONCLUÍDA só como validação OFFLINE de instrumento+kline Bybit com volumes documentados (base/quote em USDT/USDC linear), sem `ClosedCandle`: PR #126 merged SHA `bb3ecaf02f392bc8a1d06702a412d979b6ef1712`, HEAD `dca9326df8d675ea857bcd284470db9cda0875f1`, review #5645815578, CI #40243415573 SUCCESS (**706 testes offline**, compileall, 12 docs), pós-merge #40243468762 SUCCESS. Zero GET/live Bybit; licença não comprovada e restrições API; volume Kraken #36, rights #48, Top50 #32 e épica J1 #2 ABERTAS.

- J1/WU41 #130 CONCLUÍDA como janela price-only Kraken de 3..72h (default3): PR #131 merged SHA `e2b7db5d30864ba57c5ab5b6c438049ae35dc488`, review #5646098358, CI PR #40247855472 SUCCESS (**730 testes offline**, compileall, 12 docs), pós-merge #40247914420 SUCCESS. Owner-run #40247946123/j #121333418424 SUCCESS: 3 GETs, 24 BTC candles reais 1H contíguos em SQLite TEMP, 10 elegíveis/221 excluídos nos metadados correntes. 72h validada offline e NÃO executada live. WU40 dYdX #128/PR #129 não entregou candle por restrição de origem. J1 #2/#32/#36/#48 ainda ABERTAS sem direitos, volume canônico, Top50 histórico ou ordem.


- J1/WU42 #133 CONCLUÍDA SOMENTE como código candidato CandleFeed Free: PR #134 merged SHA `dcdaf90a07c36c5db044a31f041dd3ae2e08b2ea`, review #5646551100, CI PR #40255910737 SUCCESS (**744 testes offline**, compileall 12 docs), pós-merge #40255988914 SUCCESS. Nenhuma conta/key/GET CandleFeed, fonte Free 5 símbolos/30 dias, origem Binance com USD agregado não equivale a USDT settlement. Direitos upstream continuam gate, `ClosedCandle` financeiro false.
- J1/WU43 #135 CONCLUÍDA no escopo de integridade local: PR #136 merged `8e2a61d352bd4f0d40a4b1de86bfccf039cad4cb`, HEAD `f55e2da431561a913bf34f6bb295ec135476637f`, review #5646590380, CI PR #40256399524 SUCCESS (**750 testes offline**, compileall, 12 docs), pós-merge #40256467576 SUCCESS. Universo Kraken e 1..5 páginas preço-only gravados atomicamente no SQLite, rollback garantido também em DB existente sob conflito tardio; APIs individuais compatíveis, sem novo schema/rede/ordem. WU42 CandleFeed Free código entregue sem LIVE/conta, J1 #2/#32/#36/#48 abertas.

- J1/WU44 #138 CONCLUÍDA como investigação de acesso com sonda REAL BLOQUEADA: PR #139 merged `61566e2d9377f7565579c1516d738f1f7748ecae`, HEAD `4077b5101c7d543694567d40afe8526765ed1285`, review #5646635581, CI PR #40257293302 SUCCESS (**760 offline**, compileall 12 docs), pós-merge #40257371491 SUCCESS. Único real run #40257405663/j #121362109826: 1 GET metadados BTCUSDT Bybit e acesso restrito; 0 candles, sem bypass/retry. Por documentação Bybit volumes BASE BTC e turnover QUOTE USDT, mas sem conformance REAL no runner. Matriz `docs/J1_SOURCE_GATES.md` contém gates comparativos; Kraken 24h price-only real não se converte em OHLCV. J1 #2/#32/#36/#48 continuam ABERTAS.


## D77 — mudança material aprovada para o destino das jornadas
O requisito final é **trading automatizado** com entradas e saídas (stops/parciais/trailing/runner), diferentemente dos protótipos anteriores descritos como "manuais". O histórico de WUs e PRs não é reescrito: continuam implementações sintéticas, não ordens reais. Acrescentar simulador de intenções/fills e reconciliação a J4, monitor de estado/kill-switch a J5, paper prospectivo/testnet condicionada e release gate separado a J6. J1 continua ativa e bloqueada por dados/rights; nenhum salto direto a `live`. Fonte: `docs/AUTOMATED_EXECUTION_SPEC.md` e issue #147.


## Checkpoint de implementação — 26/10/2026 UTC
J4 tem AUTO1–AUTO6 como **componentes de simulação** (incluindo posições/ordens/fills/risco transacional PAPER); não é negociação real nem aceite da jornada #5. J5 recebeu apenas PRE1 #161/PR #162, tela `web/paper-demo.html` estática PT-BR para o roteiro fictício; não é UI operacional nem aceite #6. J1 segue bloqueada e não homologada; J2/J3/J6 sem validação necessária para produção. CI pós-J5/PRE1 #40300735438 SUCCESS (848 testes offline, 14 docs), sem evidência de lucro, direitos de mercado ou permissão de ordens.


## J5/PRE2 — exportação do replay fictício (26/10/2026 UTC)
Após PRE1 com página estática, J5/PRE2 #164 cria uma interface local em HTML obtida de snapshots `paper_dashboard_snapshot_v1` **gerados e validados em processo** de fixtures J4/AUTO5. Sem rede, sem live e sem sobrescrita de arquivos de usuário; entrega em validação. J5 permanece **não homologada** até ter UI operacional, provas visuais/acessibilidade e dados/ordens legítimos. J1/J2/J3/J4/J6 seguem com seus gates independentes, sem qualquer autorização de dinheiro real.


## J5/PRE3 #166 — acessibilidade e testes de browser, não homologação
PRE3 preserva a tela PAPER mobile PT-BR, acrescenta navegação por teclado e fluxo horizontal de tabela acessível, com auditoria de seis larguras em Chrome mediante workflow de CI, sem APIs ou market data real. J5 #6 só será aceita após produto conectado com dados legítimos, revisão visual e de acessibilidade ampla em dispositivos reais, automação segura de ordens e homologação J6. Teste browser verde não é demonstração de rentabilidade, trading ou direitos J1.


## J5/PRE4 #168 — visualização RO de posição fictícia persistida (26/10/2026 UTC)
Após o demonstrador PRE1/PRE2 e o QA visual PRE3, a PRE4 acrescenta exportação por ID explícito de um único agregado SQLite PAPER existente, com quantidade preenchida/reservada e status UNKNOWN distinguíveis. A posição e o journal opcional de abertura são lidos somente via `mode=ro`; nenhum schema é criado/migrado. Render HTML mobile em PT-BR e JSON v1 são locais e demonstrativos, sem dados de exchange ou opção live. J5 #6 continua não homologada; futuros passos incluem múltiplas posições, privacidade/autenticação e dados/ordens reais somente após gates J1/J6.


## J5/PRE5 #170 — visão multi-posição PAPER em pesquisa
A etapa adiciona seleção explícita de várias posições fictícias num mesmo snapshot SQLite read-only, em cartão/table mobile PT-BR e JSON, sem somar ativos ou sugerir valor financeiro. PRE4 foi integrada com QA de Chrome e 875 testes offline; PRE5 continua sujeita a PR/CI/QA. J5 #6 ainda não aceita; dados, lucro, risco de carteira e ordens reais dependem de J1/J2/J3/J4/J6, sem autorização de live.



## J2/PRE2 #172 — primeira hipótese de entrada sintética

Após J2/PRE1 #66 / PR #67 (features matemáticas), J2/PRE2 introduz avaliação determinística LONG/SHORT para compressão ATR em duas janelas **anteriores** ao candle + rompimento estrito de máxima/mínima passada + EMA e volume confirmatórios. Não é estratégia homologada, recomendação, engine de ordens ou evidência de lucro. O próximo aceite J2 requer dados financeiramente canônicos J1, avaliação de parâmetros sem overfitting e backtest/out-of-sample J3; #3 continua aberta. Foco de produto segue robô automático D77 após gates.



## J3/PRE3 #174 — planejamento walk-forward, não aceite J3

Após J3/PRE1 (barreiras intrabar hipotéticas) e PRE2 (custos assinados hipotéticos), PRE3 prepara janelas train/gap/teste em candles fechados **sintéticos** com disponibilidade causal, sem testes OOS duplicados. Isso não é resultado de backtest nem comprova generalização estatística. J3 #4 continua exigindo histórico de J1, custo/liquidação e validação prospectiva/fora da amostra. A arquitetura D77 de operação automática continua sujeita a gates.


## J4/AUTO7 #188 — conexão causal J2 e PAPER (26/10/2026)

Ao lado dos módulos J4/AUTO1–AUTO6, introduz-se uma ligação de **pesquisa sintética** entre hipótese LONG/SHORT recém-calculada pela J2 e a reserva `PENDING` de abertura PAPER atômica. Não existe circuito que use os outcomes ex-post de PRE5/PRE7 para abrir posição, e nenhum fill é criado automaticamente. Sem sinal/risco, não há registro de OPEN. A janela de decisão exige último candle fechado, idade e limites explícitos; ID estável impede reprocessamento da mesma hipótese em venue candidata diferente. Entrega isolada não conclui J2 #3, J3 #4 ou J4 #5; evolução posterior para PAPER prospectivo dependerá de seleção de fonte e segurança, e testnet/live permanecem sujeitos a gates distintos.

## J4/AUTO8 #190 — travar OPEN após FILL não reconciliado

AUTO8 fecha uma lacuna entre o diário de ordens e a reserva de posições PAPER: qualquer FILL OPEN requer vínculo local íntegro com uma posição antes de uma nova entrada. O único plano hoje disponível é sintético, portanto recebe estado `PROTECTED_HYPOTHETICAL_ONLY`, nunca a alegação de stop real; novas OPEN continuam travadas até existir capacidade de proteção/reconciliação própria, enquanto REDUCE_ONLY simulado não é removido. A entrega não conclui J4 #5, não promove PAPER a prospectivo e não altera os gates de testnet/live.


**Review de integração AUTO8:** a nova etapa revalida estados de abertura AUTO2 e reserva a próxima OPEN sob o mesmo lock `BEGIN IMMEDIATE`, para que um FILL de outro escritor não atravesse o intervalo entre auditoria e INSERT. AUTO4 permanece uma base RO independente, sem alegar proteção native stop nem snapshot atômico cross-db. A verificação pura RO isolada é diagnóstico, não condição suficiente para autorizar outra abertura. Gates J1/J2/J3/J4/J6 intactos.


## J4/AUTO9 #192 — retomada de sinais PAPER após saída integral

AUTO9 acrescenta `CLOSED_FLAT_HYPOTHETICAL_ONLY` para permitir uma nova intenção somente quando a posição anterior tiver fechado completamente por fills REDUCE_ONLY explícitos e antes da nova decisão. Parcial, STOP hipotético, runner residual e UNKNOWN permanecem bloqueados. O risco e a identidade do journal AUTO6 continuam em vigor. Não equivale à autorização de negociação real, lucro, execução na Binance/Bybit ou conclusão de J4 #5.


## J1/WU49 #194 — pesquisa multipágina de elegibilidade Bybit V5, unidade de ticker pendente

WU49 acrescenta a auditoria OFFLINE de respostas de instrumentos `linear` paginadas e ticker `turnover24h` como métrica numérica bruta de unidade NÃO comprovada, com filtros positivos crypto-only/USDT, idade de captura declarada e desempate estável. Nenhum ranking representa Top50 econômico/comparável, pois ticker não fornece unidade explícita na página oficial; KLINE fornece unidade BASE/QUOTE apenas para candles. Não foi feito GET real, conta, credencial ou trade. J1 #2 e os bloqueios de acesso/volume/direitos não foram liberados. O objetivo automático D77 continua futuro, condicionado aos gates completos.


## J1/WU50 #196 — distinguir evidência da UI de contrato REST ticker

Diligência em fontes oficiais Bybit (REST tickers, WebSocket, Kline, instrumentos e interface de negociação) registra legibilidade de `24H Turnover(USDT)`/`24H Volume(BASE)` em páginas de perpétuos, mas nenhuma declaração explícita da unidade dos nomes `turnover24h` e `volume24h` da rota REST V5 linear. O relatório de prontidão J1 registra `bybit_ticker_24h_units=blocked`, separando a moeda QUOTE documentada do instrumento de uma unidade TICKER ainda não atestada. O draft de pergunta ao fornecedor não foi enviado e nenhum feed ou trading foi acionado; J1 #2 e direitos permanecem bloqueados.


## J6/PRE1 #198 — integração de replay em ordem temporal com AUTO7/8/9

O percurso de pesquisa incremental recebe apenas candles artificiais como prefixo fechado, exige uma nova barra por decisão e rejeita reescrita, saltos e uso de futura observação. A reserva PAPER que resultar do sinal passa pelos gates já existentes de risco/posição, sem criar fills ou stops automaticamente. O checkpoint é in-memory e não constitui recuperação após restart nem feed prospectivo verdadeiro; J6 #7 segue aberta para observabilidade real, incidentes, dados e autorização futura. Nenhum trade, conta, API ou gasto.


### J6/PRE2-A #200 — pré-requisito de integridade offline (26/10/2026 UTC)

Foi acrescentado contrato puro de selo determinístico SHA-256 para prefixos sintéticos completos e contexto versionado, com escala Decimal preservada e extensão de exatamente uma barra. É uma preparação verificável para recuperação futura, **não** checkpoint durável, transação conjunta com AUTO2, proteção de exchange, stream prospectivo ou homologação. A issue #200 permanece aberta: próximo passo é integrar cursor e reserva/no-signal na MESMA transação AUTO2, com crash tests e auditoria do schema RO, ou manter fail-closed se inviável. AUTO4 continua sem snapshot atômico cruzado. Nenhuma rede, ordem real, migration produtiva ou custo.


### J6/PRE2-B #200 — cursor transacional de fixture em AUTO2 (26/10/2026 UTC)

O módulo `offline_paper_durable_cursor.py` acrescenta API offline explícita com cursor SHA-256 e inventário de OPENs em metadado opcional do próprio banco AUTO2, sem migração de schema ou produção. Um único `BEGIN IMMEDIATE` verifica prefixo/versão, saúde AUTO8/AUTO9 e risco AUTO6, reserva intenção PENDING e atualiza cursor; no-signal e risco negado também registram progresso. A recuperação compara integralmente prefixo e contexto e rejeita replay, saltos, mudança de venue/quantidade/limites e OPEN legada sem cursor. AUTO4 continua arquivo independente, sem snapshot comum. `OfflinePaperForwardSession` PRE1 permanece in-memory. Nenhuma fonte de mercado real, rede, credencial, execução, deploy ou gasto. PR/CI e fault injection de processo ainda precisam ser validados; não declarar J6 homologada.



## J6/PRE3 #234 — batch automatico FINITO de pesquisa PAPER, sem ordens reais (27/10/2026 UTC)

Entrega: `crypto_intelligence_agent/offline_paper_batch.py` reutiliza PRE2-B `step_durable_offline_paper` e `recover_durable_offline_paper` (mesmo SQLite AUTO2 e seus contratos), nao cria segundo ledger/cursor. Recebe candles ClosedCandle exclusivamente `quality=synthetic_fixture`, observacoes de risco PAPEL explicitamente ficticias e alinhadas por candle, configuracao J2/limites e journals existentes. Valida TODA a serie/identidade/horario antes do primeiro write, processa no maximo 64 candles novos por chamada, registra por passo resultado PENDING/recusa/no-signal sem produzir FILL, em `BEGIN IMMEDIATE` existente, e recupera restart comparando integralmente hash do prefixo, estrategia, venue, lot e inventario das OPENs. Novamente sobre dados totalmente processados = nenhuma nova escrita. Prefixo alterado, historico curto, risco com venue/tempo errado, metadata ou OPEN inconsistente: fail closed. Crash entre passos deixa somente commits completos, que sao retomados de maneira auditavel. O kill-switch PAPER D116 bloqueia novas OPENs sem esconder motivos de recusa nem retroemitir sinais antigos apos resume.

Comando demonstravel: `python3 -m scripts.demo_durable_offline_paper_batch` ou com `--demonstrar-pausa`. Ele cria candles inventados e sqlite TEMP, executa automaticamente uma sequencia de barras, simula reinicializacao do processo mediante reabertura do mesmo journal, completa o restante, verifica reexecucao sem duplicidade e remove os arquivos ao terminar. A saida e resumo em portugues de contagens/flags; nenhum dado bruto de mercado, chave, arquivo real ou ordem. Esta demonstracao NAO e daemon, fonte em tempo real, live feed, fluxo testnet, estrategia validada, resultado financeiro, exchange-native stop ou permissão de usar 50x. Nenhum job/cron/deploy foi ativado; custo adicional R$0.

Tests: primeiras 5 barras, abertura PAPER ficticia na sexta, checkpoint/OPEN pendente, reinicio, 0 duplicatas, pausa persistida, resume sem recuperar trade passado, limitacao de batch, validacao de todas observacoes, escala Decimal, alteracao retroativa de prefixo, falha entre passos, CLI e ausencia de rede. Aceite restrito a CI Linux/docs, Windows-offline, Chrome/PAPER no SHA exato de PR #235 (HEAD 9ae1097a71d0541c5dc56c04e04abaab76b0ddfb, integrada em e09ec9f5c9d9bb264def3c744303e929c8b5c2f8; CI pré/pós 3/3 SUCCESS), e revisao. J6 #7 permanece sem homologacao por falta de J1 canônico/licenciado, feed prospectivo verdadeiro, reconciliacao financeira, monitoramento continuo e seguranca de ordens reais; D77 destino automatico permanece.



## J5/UI #236 — tela local somente leitura com estado persistente PAPER (27/10/2026 UTC)

Problema: o dashboard de demonstração J5 mostrava apenas duas posicoes sinteticas fabricadas e NAO permitia ver se o kill-switch D116 e o cursor J6 PRE3 estavam de fato persistidos no journal em uso. Sem mudar o dashboard anterior, adicionar `crypto_intelligence_agent/paper_operator_status.py` e `scripts/render_paper_operator_status.py` com CLI `python3 -m scripts.render_paper_operator_status --journal /privado/orders.sqlite [--format html|json] [--output /caminho/novo.html]`. O leitor usa `_read_database` SQLite `mode=ro`/`PRAGMA query_only`, verifica esquema, meta keys, digest de cursor, identidade/inventario de OPENs, recupera pausa `paper_operator_kill_switch_v1` e compara o numero de OPENs pendentes/UNKNOWN pelo replay do journal. Falha fechada se houver corrupcao, chave desconhecida, caminho ausente, incongruencia de contagem ou dados de origem inesperada. So mostra estado deste arquivo AUTO2; NAO consulta conta, corretora nem posicoes AUTO4, e nao prova stop instalado. Nenhum endpoint HTTP ou credencial.

A pagina HTML offline em PT-BR apresenta um cabeçalho visivel 'SOMENTE SIMULACAO', estado de pausa de NOVAS OPENs PAPER, sequencia/horario UTC, contador de candles ficticios processados, quantidade de OPENs locais e UNKNOWN que precisa reconciliar. Layout responsivo sem overflow concebido para viewport 280..390px; CSS inline, sem script, rede, formulario ou botao que sugira dar ordens. CLI pode exibir JSON estrito ou HTML, opcionalmente criar arquivo novo com modo exclusivo sem sobrescrever. Leitura nao altera SQLite. O usuario que precisar alterar a pausa usa o controle local previamente homologado #232, nao a pagina. Nao mencionar 'robô ativo em producao' quando a pausa esta desligada: os outros gates financeiros seguem obrigatorios.

Testes: journal vazio, cursor com 6 candles e OPEN PENDING, restart, pausa/resume, UNKNOWN, checksum/meta corrompidos, arquivo ausente, HTML estatico/viewport/sem links de rede, sem leaks de caminhos/valores, JSON tipado, output exclusivo e no-network. J5 #6 continua sem produto online ou automacao de mercados; J1 #2 e J6 #7 ainda bloqueadas para dados reais/monitoramento. Nenhum release, migração, trading, acesso de conta, nova despesa nem VPS. Patch revisto; PR #237 (HEAD d38b7f6bd085e9e7cd668b72464d00743d237ac2) integrada em 4cdf6a8c51bd33a186a60a958bb3093a4280957f; CI pré e pós merge 3/3 SUCCESS no SHA exato. Nenhum review independente registrado.


## J1/HIST — primeira captura privada real BTCUSDT 1h (28/10/2026 UTC) — marco parcial da J1

A coleta histórica de pesquisa ganhou um primeiro conjunto **REAL privado**, não somente fixtures: duas saídas JSON trazidas pelo operador da VPS confirmaram captura de dois meses BTCUSDT USD-M 1h, 1.464 candles, quatro GETs, manifesto SHA-256 igual no capturador e auditor read-only, dois sidecars e continuidade [2026-08-01, 2026-10-01) UTC. Código executado em `main=46e394462b2e3141f675225c5bd1c682ec7384ec` (PR #304); saída de mercado bruta permaneceu privada. **Aceite somente da subetapa de retenção histórica para pesquisa pessoal não produtiva**, não de toda J1 #2. A J1 ainda requer elegibilidade da fonte para trading live, histórico Top50 ponto-no-tempo, qualidade multiativo e persistência canônica; Bybit rights #217 aberta. Sem ordens reais ou lançamento.


## J1/PIT1 #306 — ampliação técnica multiativo sem aprovação histórica Top50

Após marco real de BTCUSDT ago/set 2026 (1.464 candles), a J1 agrega contrato que audita 1..50 manifestos de pesquisa privados existentes e compara relógios/cobertura sem download ou escrita; outro contrato ranqueia 2..50 séries sintéticas/fornecidas por volume quote USDT das 24 velas fechadas antes do instante de decisão. É **ranking da amostra**, não universo elegível completo/Top50. O primeiro conjunto real ainda contém apenas BTCUSDT; faltam status/listing point-in-time, registro crypto-only contemporâneo, mercado completo, USD comparável, direitos live e dados multivenue. J1 #2 e #32 não homologadas, nenhuma ordem ou deploy.


## Checkpoint J1 — 29/10/2026 UTC, transição para Top50

- [x] J1/EXIT #310: captura owner-only real Bybit com 30 dias, dois contratos, persistência privada local, recuperação após erros 10006/clock, dois PIT horários distintos e auditoria read-only final de 1446 velas, 26 páginas, 3 PIT, dois ativos x 723h; `RESUME_EXIT_CODE=0`, CI pós-merge PR #318 verde. Concluída para **amostra de dois ativos**; manter os dados privados na VPS.
- [ ] J1/TOP50 #319: provar (não presumir) identidade crypto-only de ativos elegíveis fora do registro positivo atual de 13 bases, validar universo completo da exchange, ranking dinâmico em volume **USDT de 24 horas FECHADAS**, 30d/qualidade e causalidade PIT para até 50 contratos; continuar J1 #2 ABERTA.
- Primeira entrega #319 é censo owner-only de identidade no catálogo completo (sem OHLC, escrita, ordem ou Top50 aprovado); não há novo gate humano para desenvolvimento offline, somente para execução owner-only na VPS.


## D177 — desbloqueio de pesquisa independente do gate de trading real (30/10/2026)

**Decisão fechada:** Bybit continua candidata preferencial para feed prospectivo, usando WS/REST/cache local, sem considerar `10006` resolvido. Binance Vision previamente retido pelo titular fica restrito à pesquisa pessoal offline não produtiva, sem alimentação de sinais/live. J1 #319/#217 permanecem gates operacionais de dados/identidade/direitos. A execução automática permanece objetivo final (D77), mas nenhuma ordem live, testnet, deploy ou credencial foi ativada. J2/J3 podem pesquisar offline sem esperar homologação integral do Top50 de produção. Não exigir novo `prossiga` para tarefas seguras em sessão.

A biblioteca `vision_dynamic_replay.py` reutiliza candles já auditados por `offline_vision_month` e `offline_vision_series`, e gera replay determinístico de decisões com volume de cotação USDT em 24h FECHADAS para uma amostra de até 50 contratos, por prefixos, em até 720 decisões. Flags de Top50 de mercado, origem autenticada, direitos live, backtest financeiro aprovado e ordens continuam negativas. Testes de alinhamento, relógio, duplicata, determinismo, não-lookahead e recursos. **Não é autenticação de fonte ou universo histórico global.**


## J2/J3 #357 — avaliação causal mensal de hipótese líquida, somente pesquisa (30/10/2026)

`vision_costed_oos.costed_vision_monthly_oos` reutiliza séries de meses Vision previamente inspecionadas, alinha múltiplos ativos e ranqueia pela soma das últimas 24h de volume cotado fechado. Regra fixa de tendência/contratendência é selecionada exclusivamente no histórico anterior, com alternativa de permanecer em caixa se não houver valor líquido hipotético positivo; o mês atual nunca treina sua própria escolha. Entrada hipotética no open do candle seguinte, saída no close, taxa/slippage hipotética agregada em bps por lado, benchmark buy-long e drawdown proxy. Não incorpora mark, funding, intrabar, slippage reais, liquidação, alavancagem, fills executáveis, custos de portfólio nem valida edge; `financial_backtest_approved=false` sempre. Não encaminhar a sinal real, ordens ou conta. Amostra restrita ao dataset local; sem autenticação de fonte, direitos de live ou Top50 de mercado. Sem downloads, storage, deploy ou novos gastos.


## J3/STRESS1 #359 — limites intrabar OHLC condicionais (30/10/2026)

`vision_intrabar_stress.py` introduz estresse matemático estritamente offline para uma barra Vision, com margem sintética, alavancagem fixa por avaliação, stop, target, limiar de liquidação proxy por equity e manutenção hipotética, funding assinado e custos Decimal por lado. Como OHLC não informa a ordem dos eventos, retorna **dois limites condicionais**: downside (liquidação/stop antes de target) e upside (target antes de stop), marcando ambiguidade e toques simultâneos. A marcação e a fórmula de liquidação reais da corretora NÃO são inferidas. Não há integração com execução nem estimativa de perda garantida. `financial_backtest_approved=false`, nenhuma ordem, rede, licença, dado canônico ou homologação Top50. Testes de 50x/1x, long/short, ambiguidade, taxa, funding e corrupção. A integração com seleção OOS mensal e CLI é **pendência da issue #359**, não alegar entrega completa.

## J3/PRE21 #407 — decisão causal única, envelope por mês

Conclui a integração de pesquisa offline entre seleção mensal OOS e estresse intrabar condicional, sem liberar J3. O próximo gate continua sendo revisão independente e CI no SHA da PR; dados canônicos, mark/funding/liquidação de venue, execução e rentabilidade permanecem fora do escopo.


## J3/PRE17 #369 — pesquisa de risco por snapshots PIT

Work unit J3 de replay sintético: faixas de maintenance e deduções contínuas por nocional de mark; snapshots versionados conhecidos causalmente; comportamento legado intacto e teste adversarial de gaps/funding. Referência `docs/J3_PRE17_PIT_RISK_TIERS.md`. Requer CI e merge antes de registrar integração. Não substitui dependências J1/J2, não aprova fórmula da exchange ou ordens reais.


## J3/PRE18 #371 — calendário de funding com cobertura obrigatória opt-in

Validador offline de timestamps hipotéticos de funding; cada horário exige evento com taxa/notional declarado e não aceita tick simultâneo. Acopla-se opcionalmente ao replay de mark/trade sem alterar caminhos legados. Regressões e docs em `docs/J3_PRE18_FUNDING_CALENDAR.md`. Gate CI/merge pendente; não homologa eventos do provedor, ordens ou lucro.


## J3/PRE19 #373 — replay de carteira sintética

Agregação multi-leg com relógio UTC comum, margem isolada, exposure gross/signed por mark, funding via módulos existentes, stop/target condicionais sem duplicação e PnL desconhecido após liquidação sem fill. Drawdown de prefixo e correlação descritiva, não previsão ou carteira com risco financeiro homologado. Contrato `docs/J3_PRE19_PORTFOLIO_REPLAY.md`. Gate CI/merge obrigatório antes de conclusão da work unit.


## J3/PRE20 #375 — limites globais de risco para carteira sintética

Reutilização do replay de carteira PRE19 para avaliar margem total/por leg, exposição gross/abs net por marcação, maior instrumento, concentração e drawdown causal, com bloqueio fail-closed quando PnL de liquidação é desconhecido. Exige testes, CI e merge sem produção; ver `docs/J3_PRE20_PORTFOLIO_RISK_LIMITS.md`. Não equivale a risco homologado da corretora nem autoriza ordens.


## J1/EXIT2 #377 — fechar bloqueios de captura privada dos 50 candidatos

Comportamento alvo: 52 identidades crypto-base revisadas disponíveis no registro → censo pre/post completo → 24 velas fechadas por elegível → 50 maiores do conjunto revisado → 720 candles por ativo em banco SQLite **novo** sem sobrescrever histórico anterior. Guardas de 6min, manifesto 52, falha antes de criar DB se faltar cobertura, CI e replay garantem preparo técnico. O proprietário executará pesquisa pessoal na VPS somente após CI/merge, preservando direitos e limitações de dados live. A J1 épica #2 e o censo de todos contratos #319 exigem aceitação real posterior, sem inventar ranking marketwide.


## J1/EXIT3 #379 — PIT multiativo 50 sem intervenção entre horas

O CLI owner-only permite operação autônoma de pesquisa privada por uma única invocação: coletar ranking 24h fechado de 52 revisados, backfill exato 50×720h em novo SQLite e duas novas atualizações horárias de 50 membros se identidades permanecerem estáveis. Critério de engenharia: 3 PIT reais quando executado na VPS, integridade 36.100 candles e relatório privado. Diferenças de membros, rate limit e janelas perdidas abortam sem reescrever o histórico. Avaliação Top50 marketwide exige censo real com identidade integral; não inventar confiança com fixtures.


## J1/EXIT4 #381 — universo dinâmico sem perder histórico

Requisito de J1: Top50 muda a cada hora de decisão conforme as 24h fechadas; alteração do conjunto não invalida dados já persistidos nem obriga recapturar 720h de membro retornante. Entrantes recebem backfill exato desde T0-720h, ex-membros permanecem cacheados e a auditoria lê cada snapshot imutável PIT no seu contexto. Pesquisa pessoal offline com um único owner-run, sem comportamento live. Aceite de engenharia depende de testes e CI; aceite de J1 mercado depende de coleta real e denominador completo.


## J4/RUNNER1 #383 — monitoramento read-only de runner confirmado

O módulo separado PAPER observa mark em série causal após todas as parciais do journal e emite estado de trailing LONG/SHORT, sem ordens, alteração de stop na venue ou PnL. O estado não é durável após restart: requisito futuro de J4/J6 continua pendente. Contrato `docs/J4_RUNNER1_PAPER_TRAILING.md` e testes no repositório. J1 owner-run na VPS ficou estacionado por solicitação do usuário; outras jornadas podem continuar sem ele.


## J5/PRE14 #385 — runner móvel sem prometer proteção

A tela PAPER de posições selecionadas passa a identificar o runner residual a partir dos fills e reservas do próprio journal, com quatro estados PT-BR e `trailing_stop_active=false` sempre. A confirmação do runner exige que não haja UNKNOWN/reserva pendente; mesmo confirmado não comprova que existe stop nativo na corretora. Sem dependência da VPS/J1 e sem controle de ordens reais. Testes e gate CI antes de integrar.


## J4/RUNNER2 #387 — replay durável de trailing PAPER

O estado de trailing pode ser reconstruído após reinício por marks sintéticos duráveis em journal **separado**, sem recalcular extremos somente de uma janela truncada. A posição de runner permanece ancorada a um checkpoint validado e ao policy hash; mudanças na posição ou política falham sem rearmar silenciosamente. Estados hipotéticos terminais não são fills nem stops da exchange. J1 continua pendente na VPS por solicitação do proprietário, mas J4 progride offline.


## J6/PRE8 #403 — auditoria simultânea de posições PAPER selecionadas (31/10/2026)

A triagem PRE6 por uma posição não fornece fotografia simultânea de várias posições. PRE8 reutiliza o leitor `inspect_paper_positions` para um snapshot AUTO4 único de até 128 posições explicitamente escolhidas, classificando o incidente PRE6 por item, cutoff UTC e staleness, com bloqueio do lote inteiro se qualquer diário for inválido. Não agrega posições em carteira financeira ou conta de exchange, não ativa ordens, stop, feed real ou live. Gates e documentação em `docs/J6_PRE8_PAPER_PORTFOLIO_INCIDENTS.md`.


## J6/PRE9 #405 — identidade causal da entrada em fluxo PAPER completo

Uma intenção OPEN gerada pelo motor quantitativo J2/RiskGate deve permanecer a mesma ao ser confirmada por FILL de fixture em AUTO2 e registrada em AUTO4; somente depois as parciais, trailing e runner podem afetar saldo sintético. PRE9 integra os componentes existentes em uma demo finita com checkpoints/read-only PRE8, sem implicar execução, stop nativo ou homologação de dados/conta. Ver `docs/J6_PRE9_FULL_OFFLINE_LIFECYCLE.md`.



## J3/PRE22 #409 — fragilidade OOS sob parâmetros financeiros, sem otimização ex post

Um único histórico mensal e uma única regra OOS de seleção causal podem ser comparados sob 2–6 hipóteses de alavancagem, margem, taxa, slippage, funding e manutenção. A API PRE22 reusa PRE21 para todo cálculo e bloqueia qualquer variação de cobertura mensal por cenário, sem ranking da melhor configuração, ROI de capital, autorização de 50x ou ordem de exchange. Critérios e decisão D199 em `docs/J3_PRE22_OOS_STRESS_SENSITIVITY.md`. A dependência de evidência VPS J1 permanece externa e PRE22 não aciona sondagem/coleta.


## J3/PRE23 #411 — sensibilidade OOS acessível por CLI owner-only

Sem abrir novas fontes, a CLI Vision de pesquisa pessoal poderá computar uma grade de dois cenários (1x e Nx, N 2–200) com a mesma margem e seleção causal OOS, a partir de manifests locais auditados. Exige opção positiva, preserva comportamento legado sem o opt-in e mantém todos os gates de live/ordens falsos. A J1 Top50/VPS não é utilizada nem resolvida. Aceite exige CI, regressões POSIX e revisão da PR; D200/PRE23.


## J3/PRE24 #413 — integridade de decisões OOS, 31/10/2026

Partindo de main 97a990c2f62fa6888e80c1c509df1ab453da7d8d (PRE23/PR #412 integrada, zero PRs abertas), PRE24 corrige a insuficiência de comparações por contagem: fingerprints de decisões OOS por fold e global permitem detectar seleção diferente com exposição igual; PRE22 falha fechado quando houver discrepância. Relatório aditivo inclui drawdown e perda máxima por margem, preservando digest financeiro PRE21. Branch work/j3-pre24-oos-decision-fingerprint-risk; issue #413. Testes/CI/revisão/merge dependem de evidência de execução, sem alegação antecipada. J1 #2/#319: worker agendado às 15:00:15 UTC, conclusão não verificável pelo GitHub, sem reiniciar. Sem dados reais, VPS, ordens, credenciais, deploy ou custo.


## J3/PRE25 #415 — benchmark LONG pareado por exposição, 31/10/2026

Base `main=fea791dfd6dfb565a5254e4bb6dbb137cc2762ca` com PRE24 #413/PR #414 integradas, todos gates pre/postmerge verdes. PRE25 adiciona LONG contrafactual nos **mesmos** ativos/barras de exposição da estratégia, reutilizando envelope LONG já calculado, sem substituir LONG integral, sem retreinar regra OOS, alterar fingerprints PRE24 ou digest financeiro legado PRE21. O relatório por fold/agregado e em PRE22/PRE23 inclui exposições, ambiguidade, toques stop/alvo/liquidação proxy, riscos condicionais e deltas adverso/favorável; não confundir deltas com alpha, fills, retorno composto ou vantagem comprovada. Testes de tendências sintéticas, LONG, reversão SHORT, abstenção, custo 1x/50x, privacidade. Issue #415 e branch `work/j3-pre25-exposure-matched-oos-benchmark`. CI/revisão/merge sujeitos a comprovação; J1 #319 worker VPS continua sem resultado verificado, sem coleta ou acesso remoto novo. Sem ordens, contas, testnet/live, deploy ou gasto adicional.


## J6/PRE10 #417 — matriz integrada de interrupção causal PAPER (31/10/2026)

Base confirmada `main=87f6221c82c4f38a6307a2daaf023ed26aeb21e8`, zero PRs abertas antes da tarefa. A demo existente `scripts.demo_full_offline_paper_lifecycle` agora usa auditoria AUTO8 e PRE8, operador AUTO6 e ramo AUTO4 descartável com FILL divergente para afirmar bloqueio nas fronteiras J2/AUTO2/AUTO4/REDUCE_ONLY/runner sem alterar caminho de sucesso. Sete checkpoints sanitizados `interruption_checks`; testes de determinismo, contadores, travas de native stop/live e auditor adulterado. Issue #417; branch `work/j6-pre10-causal-interruption-matrix`. CI, PR, revisão e merge somente após evidências no SHA exato, sem promessas antecipadas. J1 #319: worker VPS agendado no último registro mas sem resultado privado verificado, não reiniciar/coletar. Sem conta, rede, ordens, deploy ou gastos.


## J6/PRE11 #419 — cutoff causal e recuperação em PAPER, 31/10/2026

Base verificada `main=97840c8f4245ed7692b372d06ed68b611c50cbab` (J6 PRE10/PR #418 integrada, CI pós-merge verde, zero PRs abertas). PRE11 implementa fail-closed em snapshot futuro AUTO2 cursor/pause no status de operador e recuperação; runner-close PENDING/FILLED com cutoff antigo; classificação de incidente RUNNER2 com AUTO4 posterior ao cutoff. Testes adversariais de instante anterior/igual, recusa de leitura retrocausal e imutabilidade do diário. Issue #419 branch `work/j6-pre11-causal-recovery-cutoff`. CI, revisão e merge dependem de evidência verificável. J1 #319 permanece sem resultado auditado da tentativa VPS; sem novo GET, restart, trade, credenciais, release, deploy ou gasto.


## J6/PRE12 #421 — sanidade temporal completa de eventos AUTO2, 31/10/2026

Base real `main=386e364eeebfb70583b7f38bedac87444a71829d` com PRE11 #419/PR #420 integrada, testes Linux/Windows/Chrome verdes e zero PRs abertas no início. PRE12 fecha lacuna em `paper_operator_status`: cursor e pausa estavam limitados pelo cutoff, mas o scan de OPEN/REDUCE_ONLY ainda aceitava snapshots de FILL/eventos futuros. O scan agora valida `created_at_ms` e `snapshot.as_of_ms` de **todas** as intenções AUTO2 sob a mesma transação read-only, antes de calcular pendência. O modo sem cutoff permanece compatível. Recuperação anterior usa o novo bloqueio e a demonstração PAPER acrescenta dois checkpoints de impossibilidade retrocausal (abertura e runner). Testes com SQLite, abstinência de rede, sem writes e saídas sanitizadas. Issue #421 e branch `work/j6-pre12-auto2-event-causal-cutoff`. CI e merge ainda exigem evidências; nenhuma VPS, coleta J1, conta, ordem, testnet/live, release, migration ou gasto.


## J3/PRE26 #423 — diagnóstico adversarial OOS/risco multicenário, 31/10/2026

Base observada `main=bdb7fcdd7474a842e46eeb2c71249ec933b1bf95`, zero PRs abertas; J6 PRE12/PR #422 integrada e CI pós-merge verde. PRE26 introduz política tipada com limites de amostra, liquidação proxy, ambiguidade, perda por barra, drawdown e ramo adverso por fold **para cada cenário** PRE22, sem aceitação por média ou cenário melhor. Verificações de integridade cruzam contagens OOS, matched LONG e fingerprints. CLI privada reutiliza grid 1x/Nx já calculada, com opt-in e limites obrigatórios; sem novo acesso a arquivos privados. Testes para 1x/50x, tendencia sintética, flat/zero exposição, taxas, permutação, falsificação de fingerprint, limites inválidos e privacidade. Issue #423, branch `work/j3-pre26-robustness-oos-screen`. CI, revisão e merge não presumidos; J1 #319 sem resultado verificável VPS. Sem mercado, ordem, testnet/live, migration, release, deploy ou gasto.


## J3/PRE27 + J6/PRE13 — caminhos intrabar e stop ausente (#425), 01/11/2026

Base verificada `main=5c59103fa0718ed80e8e4bcb29daa40c6825eee1`, 0 PRs abertas; PRE26 #423/PR #424 integrado, Linux/Windows/Chrome verdes. PRE27 adiciona simulação determinística e explicitamente condicional em dois caminhos intrabar e dois estados hipotéticos de STOP, com custos, margem, funding e limiar de liquidação proxy PRE21. Agrega por fold/scenario nas decisões causalmente congeladas PRE22 (fingerprint e contagens validados), mede diferença frente ao pior envelope PRE21, sem trocar estratégia. Novo opt-in no replay privado `--audit-oos-path-outage` só com par 1x/Nx, sem novos arquivos. J6/PRE13 adiciona contrafactual isolado à demo PAPER sem injetar ordens/fills de execução. Testes LONG/SHORT, ambiguidade, piora por outage, 1x/50x, custos, permutação e integridade OOS. Issue #425 e branch `work/j3-pre27-stop-outage-intrabar-paper`. Aguardar CI e revisão SHA antes de merge; J1 #2/#319 permanece sem evidência privada de execução VPS, nunca reiniciar. Nenhum GET de mercado, trading real, testnet/live, credenciais, deploy, migração ou gasto.


## J1/EXIT5 #427 — recuperação da prova VPS de 50 ativos (01/11/2026)

Fatos comprovados: o usuário rodou diagnóstico read-only na VPS; `capture_exit_code=1`, `audit_exit_code=0`, 50 ativos, 36.000 candles 1h, 720h cada, 50 páginas, PIT único `2026-10-31 15:00 UTC`, `sqlite_integrity_passed=true`, `private_page_replay_passed=true`. Erro factual: `provider_rate_limit_no_retry`, retCode `10006`, etapa `closed_kline_24h`, após 157 GETs, captura já encerrada. A VPS estava no checkout `c852c4002b84b74be24b1dd986154c242971d09e`. Nenhuma mutação/GET foi executada nesta sessão pelo assistente. O caminho antigo `resume_private_bybit_j1` suporta apenas 13 ativos, então EXIT5 amplia para 50 dentro de `expanded-52` e catch-up de janelas 1..72h, preservando 720h iniciais. Dados existentes, ranking, flags live, e PIT atual não são presumidos marketwide. Issue #427, branch `work/j1-exit5-resume50-bounded`. CI e revisão obrigatórias antes do merge, sem deploy automático remoto. J1 #319 ainda aberta até 2 PIT posteriores reais confirmados pelo auditor VPS.


## J1/OPS1 #429 — continuidade operacional e observação confiável

Primeira entrega: observador read-only do worker EXIT5, sucesso apenas se recibo e auditoria forem coerentes, sem alegar que PID permanece ativo. A VPS original não foi tocada por esta PR. Faltam supervisor de serviço 24/7, WS confirmado, reconciliação compacta de lacunas e UI PT-BR; #319 segue indispensável para Top50 global. Contrato `docs/J1_OPS1_STATUS.md`, D209.


## J1/OPS2 #429 — janela causal móvel de 24 candles WS (offline)

Incremento técnico independente do worker VPS: ingestão de velas já fornecidas e validadas pelo pipeline WS offline, ranking local de 24h fechadas, abstenção para candidato ausente e PIT sem lookahead. A issue #429 permanece aberta para supervisor 24/7, persistência de fluxo real e recuperação limitada de gaps, preservando J1 #319 como gate marketwide. Evidências e limites: `docs/J1_OPS2_LOCAL_WS_24H.md`, D210.


## J1/OPS3 #429 — controlador WS e exclusão mútua

Novo controlador limitado com sessões injetadas, subscribe multicandidato, ACK, heartbeat, fail-stop de dados inválidos, reconexão bounded e lease POSIX de escritor. Implementação sem rede nem serviço 24/7 ativado; requisitos e evidências em docs/J1_OPS3_WS_SUPERVISOR.md, D211. J1 #2/#319 seguem abertas.


## J1/OPS4 #429 — ponte de catálogo para piloto WS owner-only

Adicionar piloto finito de supervisão WS com catálogo completo paginado limitado, escopo revisado privado reutilizável, lock de escritor, journal separado e relatório de saúde. Sem substituição da coleta REST histórica, sem serviço contínuo instalado e sem ordens; Top50 global #319 ainda não comprovado. Ver docs/J1_OPS4_OWNER_WS_PILOT.md e D212.


## J1/OPS5 #429 — renovação PIT de escopo sem perder dados

Adicionar renovação opt-in do catálogo após 48h somente se os contratos mantiverem a mesma identidade; acrescentar epochs imutáveis owner-only e auditar apenas snapshots causalmente admissíveis. Churn bloqueia a continuação até migração/journal revisado; nenhuma recaptura 720h, ativação 24/7 ou ordem. Contrato `docs/J1_OPS5_CAUSAL_CATALOG_RENEWAL.md`, D213. J1 #2/#319 permanecem abertas.


## J1/OPS6 #429 — gerenciador de execução preparado, não ativado

Adicionar lease finito de serviço, códigos de falha que bloqueiam reinício em quota/corrupção/permissão, template systemd isolado desativado, renderizador não mutante e leitor de saúde owner-only. Software não demonstra serviço real contínuo. Próximas dependências: ACEITE de conexão real, gaps, denominador Top50 marketwide #319 e implantação supervisionada com gate; detalhes D214 e `docs/J1_OPS6_SERVICE_SUPERVISION.md`.


## J1/OPS7 #429 — compatibilidade ACK sem rede real

Assinatura única de até 52 tópicos permite correlacionar com segurança ACK público linear cujo `req_id` pode vir vazio/ausente, mantendo abstenção em falhas, integridade e replay do journal. OPS6 segue modelo de serviço desativado; próxima etapa é teste owner-only real e homologação de continuidade. D215 / `docs/J1_OPS7_SINGLE_ACK.md`.


## J1/OPS8 #429 — homologação gradual de WebSocket linear

Preparar sonda opcional curta e sem persistência para evidenciar ACK e entrega de frames dos 52 candidatos, sem copiar SQLite REST ou emitir ordens. Separar contrato de protocolo de prova de 24h e de implementação da supervisão contínua; guardas de opt-in/owner e CI antes de homologação VPS. Ver D216 e `docs/J1_OPS8_LINEAR_HANDSHAKE_PROOF.md`.


## J1/OPS9 #429 — orçamento de serviço versus piloto

Separar limite pequeno da sonda de pesquisa (4.096 frames) do lease de coleta de 52 tópicos por 55 minutos (até 175.696 mensagens), com teto explícito 200.000 e erro de cap tratado como falha de continuidade, não como feed saudável. D217 e `docs/J1_OPS9_HOURLY_FRAME_BUDGET.md`. Serviços ainda desativados, sem homologação de 24h; #319 marketwide aberta.


## J1/OPS33 — candidato Binance USD-M para contrato causal verificável

OPS33 #486 cria um observador sombra finito Binance WS após D238/OPS32, sem permitir fonte canônica nem trocar venue. Reutiliza validação Decimal/UTC, ACK, corte de `x=true` e cronologia, no máximo dois ativos, claim exclusivo e timer systemd não-recorrente off por padrão. Prova live é separada da aprovação do código; TOP50/24h ficam pendentes. Ver D239 e `docs/J1_OPS33_BINANCE_FINITE_SHADOW.md`.


## J1/OPS34 — vínculo causal Binance, identidade contrato e Top50

OPS34 #488 implementa etapa de pesquisa **offline** após shadow OPS33 na VPS: confirma formato PERPETUAL/TRADING/USDT/COIN no catálogo capturado e revalidado PIT, registro de identidade cripto independente existente, completude de 24 candles fechados para cada contrato revisado elegível e rank por coluna quote turnover USDT. A captura e o registro não autenticam o universo inteiro nem direitos, e o código não grava nem negocia. D240; ver `docs/J1_OPS34_BINANCE_CONTRACT_PIT_TOP50.md`.


## J1/OPS35 — auditor metadata-only com observabilidade sem dados brutos

OPS35 #490 implementa observador único e opt-in de `/fapi/v1/exchangeInfo` para verificar catálogo Binance e lacuna de identidade revisada sob D241, com dois GETs no máximo e guardas de região/root/registry PIT, sem ordens, candles ou cache. A validação offline do código e uma futura execução na VPS são evidências distintas; Top50/24h permanece pendente. Ver `docs/J1_OPS35_BINANCE_METADATA_ONCE.md`.


## J1/OPS35 D242 — censo de metadados não é aprovação de ativo

Pesquisa Binance recebe modo de censo estritamente observacional, sem registro PIT nem símbolos de saída, útil mesmo quando registro de identidade expira, mas incapaz de autorizar contrato USD-M, ranking Top50, persistência ou negociação. Modo padrão de identidade continua exigindo revisão fresca durante toda a operação. Testar ambos e CI antes de integração. Issue #490.


## J1/OPS36 — integração offline das provas OPS32 e OPS34

A OPS36 #493 reúne em 24 epochs sintéticos o contrato causal x=true/ACK Binance e metadados de instrumentos + revisão PIT; agrega turnover `k.q` e distingue estritamente amostra revisada de Top50 global. Não implanta coletor, não transforma 2 fechamentos reais da OPS33 em histórico e não aprova 24h reais, mercado, execução ou rentabilidade. VPS permanece pendente por indisponibilidade do titular; CI GitHub é independente. Ver D243 e `docs/J1_OPS36_BINANCE_WS_24H_OFFLINE.md`.

J1/OPS37 #495: classificar falhas OPS35 com enums sanitizados para prova futura, nao repetir one-shot original, nao autorizar Top50/USD-M, persistencia ou ordens com base em classificacao. D244.


## J1/OPS1 D245 — primeira camada de observabilidade sem VPS

Auditor offline SQLite de amostra PIT/24h + CLI nonroot read-only; #429 continua aberta, pois supervisor persistente, conectividade, recuperacao de falhas e homologacao real ainda nao foram entregues. Gate #319 separado. Testes/CI e evidencia na PR vinculada; sem deploy, ordem, coleta ou Top50 confirmado. Ver docs/J1_LOCAL_HEALTH_READONLY.md.


## J1/OPS1 D246 — validação dos valores armazenados

A PR de integridade SQLite adiciona inspeção de OHLCV Decimal e checkpoint duplicado ao observador read-only D245; NAO adiciona novo supervisor, pois `bybit_ws_supervisor`, `bybit_ws_owner_lock`, `j1_ws_service` e `j1_ws_multihour_soak` ja existem. Esperar CI e SHA antes de integrar. A issue #429 segue aberta pela homologação real do coletor continuo, e a #319 pela prova independente Top50.


## J1/OPS1 D247 - observador do segundo SQLite (WS)

O monitor D246 do SQLite historico nao inspeciona o journal de fechamentos WebSocket. Um observador owner-only distinto usa `SQLiteOfflineClosedStreamJournal.audit` e leitura imutavel da cadeia PIT, sem novo coletor/servico. So resultados de amostra local, NAO aprova worker 24/7, feed, autenticacao, timestamp>end ou marketwide Top50. #429/#319/#2 abertas. Ver D247.


## J3/PRE28 #500 — risco causal de co-perda sintética

Bloco independente enquanto J1 depende de prova real da VPS: gate de correlação incremental de retornos mark assinados por direção, baseado nos validadores PRE19/PRE20, sem alterar contratos de execução ou estado real. Veto conservador para correlação alta, flat, histórico insuficiente ou liquidação. Evidência de código exige testes e CI da PR; J3 #4/J1 #2 permanecem abertas.


## J1/TOP50 #502 — ranking UTC fechado de universo basico

Depois da prova real de 50 candidatos/1200 candles, desenvolver captura de todos os 822 perpétuos USDT tecnicamente elegíveis em lotes privados retomáveis, sem rebaixar universo revisado anterior. A conta de 822 não é prova de 822 criptomoedas; ranking de 24h UTC fechado da lista basica também não é por si só homologação J1. Gates #319/#429/#2 seguem abertos até evidências em VPS, revisão independente crypto-only e continuidade. D249.

## J4/J5 AUTO-PAPER1 #650 — entrega integrada entre gestão e mobile (15/11/2026 UTC)

Próximo incremento de produto: criar cenários PAPER com regras configuradas de dois alvos e stop acionados por preço **hipotético digitado**, usando as funções locais BigInt já existentes e respeitando runner, com identificação e replay dos eventos automáticos no navegador/backup. A interface não se conecta a exchange nem se apropria dos observáveis J2 como ordens; não substitui o motor J4 Python de risco, reservas e reconciliação. Código em branch `work/issue-650-j4-j5-paper-auto-exits` aguardando review/CI/merge sem deploy. A aceitação J4/J5 e negociação automática real permanecem gates distintos.

## J5/J6 #652 — replay automático transacional de fixtures no celular (15/11/2026 UTC)

Incremento de uso local após os gatilhos J4/J5 #650: o operador pode colar até 24 preços de fechamento **sintéticos** e executar o cenário inteiro em uma ação, com rollback integral em caso de erro tardio e contagens após STOP. É um teste de lógica, não coleta, backtest OOS, order engine ou trading. Branch `work/issue-652-j5-paper-batch-marks` sob PR/CI; sem deploy. Acesso a dados reais, RiskGate da corretora e execução continuam separados.

## J1/D360 — aceite técnico da coleta/ranking Top50 para pesquisa (15/11/2026, 20:24 UTC)

**PIT real final comprovado:** na VPS, D359 job `484e99fb820b435e8096c471ec2dfc8a` status `completed`, exit 0, `D359_POOL_COMPLETENESS=PASS_RESEARCH_ONLY`, horário de captura 19:01:30–19:13:54 UTC e 24h fechadas até 19:00 UTC (`1794769200000`). **370/370 candidatos elegíveis técnicos da pool D279 tinham histórico fechado completo**, 0 incompletos, 0 zeros, catálogo pré/pós estável, 372 consultas, seleção selada de 50 com digests (pool `115eb222184de24706f585143d343d9064d52f2d2e0e329de45730e37c231c96`, rank `72141c142897c7fff84c001a1945490d3453ff3b20e5d75c756553d95fa98de8`, scope `3e41cce27e68fa0c9c267fa5adeb240161657fbe04bb1575b48b4e1f75f99258`), `orders_sent=false`, `database_modified=false`. Registros reais anteriores: D286 11/11 370/370 com janela PIT própria; rotação D321 14/11 com nova epoch e antiga preservada; D323 15/11 aprovou 24×50 e 1.200 registros SQLite WS da epoch 14/11. **Não confundir snapshots diferentes** ou promover retrospectivamente a completude da seleção 14/11.

**Código e validação:** PR #654 D357 (`dd6aab6d02de8452346b236b3c1f3ff4e28d7869`) e PR #655 D359 (`b75124c2efbfa1a2a5d1b2c38f0f597c397e2d90`) integradas. PR #655 head revisado `852646205dfa5a7bcedfccbdfcf9dd8eedf2502b`, 3/3 CI Linux/docs, Windows/offline, PAPER/Chrome verdes, 32 regressões owner locais PASS. Auditor foi instalado em checkout privado **isolado**, não houve atualização do código do serviço WS/rotador, SQL write, mudança systemd, ordem ou gasto. Timers WS/rotação permanecem ativos/habilitados na verificação de 20:23 UTC. A automação de 16:20 BRT não publicou o resultado, portanto o próprio executor reconsultou e gravou a evidência no GitHub (issue #319 D360), que foi **CLOSED/completed em 20:24:48 UTC**.

**Decisão de aceite:** J1 é aprovada **no escopo de fundação de dados e seleção dinâmica de Top50 técnico de perpétuos USDT para pesquisa pessoal**, com ingestão/read-only, histórico UTC fechado, qualidade, persistência, integridade WS, rotação e seleção PIT causal auditados. O aceite não implica catálogo crypto-only global independente, fonte autenticada para ordens, garantia de feed ininterrupto futuro, revisão de todos fornecedores Kraken/Binance, homologação operacional 24/7 para produção, rentabilidade ou execução financeira. `marketwide_top50_verified=false`, `crypto_identity_independently_verified=false`, `approved_for_signals=false`, `live_trading_authorized=false` **permanecem obrigatoriamente false**. Issues J1 auxiliares de refinamento (#429 supervisão/health avançado, #525 cenários 48h, #585 reconciliação REST de gaps) podem permanecer abertas para evolução e J6; **não reabrir a coleta/24h já comprovadas**. O produto J2/J3/J4/J5/J6 permanece em desenvolvimento e não está pronto para ordens reais.


## J2/J3 #656 — transição controlada de código para observação prospectiva (15/11/2026)

Com aceite J1 D360 para pesquisa, reutilizar watchlist WS J2 #638, avaliação J3 #640 e ledger ex-ante J2/J3 #644. Incremento #656 só adiciona preflight local read-only de owner, DAC, horário sincronizado e epoch 50×24 antes de qualquer captura. CI/PR não são registro prospectivo real. A execução na VPS e eventual agendamento são gates separados, com abstenção em mudança de epoch e nenhuma ordem. `docs/J2_WS_PROSPECTIVE_PREFLIGHT_656.md`.


## J2/J3 #658 D362 — iniciar observação prospectiva real sem refazer J1

Aprimoramento operacional após J1 D360 e J2/J3 D348: script em checkout owner separado para preflight OS somente leitura, captura de uma decisão J2 no fechamento UTC após provas privadas de 50x24 e avaliação 1/4/8h em tempos distintos. O código e CI não significam release. Implantação e captura reais demandam gate expresso, sem alterar timers e dados da J1. Ver `docs/J2_OWNER_PROSPECTIVE_PILOT_D362.md`.

## J3/J5 #661 — distinguir decisão, observação e posição PAPER
A interface local distingue: (a) observações registradas antes do resultado; (b) resultados J3 posteriores, se existirem; (c) posição simulada J4, que não deriva de nenhuma captura J2. Sem transição implícita de pesquisa para ordem ou PnL, sem backend público, sem mudança N50.

## J2 #663 — construção de histórico prospectivo sem hindsight
Implementação offline de tentativa de captura J2 periódica, idempotente por hora, com limites POSIX/UTC e validator da mesma coorte N50. Agendamento de produção sujeito a gate específico; rotacionar epoch N50 não implica resetar decisões privadas e uma abstenção não vira sinal. O score futuro continua separado.

## J4/J5 #665 — observabilidade de risco em PAPER
A evolução J4/J5 distingue marca hipotética de cotação real: impacto bruto na margem configurada (alavancagem individual imutável), alerta visual de perda >= 100%, sem estimativa de margem de manutenção, liquidação real, fill de corretora ou execução. Não ativa J4 automático em live.

## J3 #667 — validação periódica sem hindsight ou execução real
Após código J2 #663 de captura recorrente, preparar J3 owner **somente leitura** para avaliar decisões congeladas antes das 1/4/8h futuras, sem preencher registros ausentes nem cruzar coorte rotacionada. Resultado de zero candidatos é abstenção, não lucro zero. Renderer de timer HH:17 UTC em SHA40 pinado não instala nem habilita serviço; release separado obrigatório. Ver `docs/J3_OWNER_FORWARD_SCORING_D372.md`.

## J4 / D387 — incremento automático intrahorário, sem reabrir J1

Issue #676: `paper_intrahour_target_step_d387.py` utiliza o journal J4/AUTO4 existente para reservar saídas parciais automaticamente quando o bid (LONG) ou ask (SHORT) satisfaz nível explícito e a cotação é válida. Não exige clique nem novo candle 1h e **não inventa fill**; componentes PAPER previamente implementados de posições, reservas e runner são reutilizados. Próximas tarefas J4 na mesma issue: stop antes dos alvos, trailing/runner integrado, reconciliação de proteção e feed #677; depois testnet/live sob gates. Não confundir esta primeira implementação com execução em produção.


## Evolução funcional J4/J5 — D407

Consumir no aplicativo, em modo volátil, relatório de posições PAPER persistidas exportado pelo leitor existente AUTO4 (sem leitor novo). Exibir por posição reconciliação, quantidades e runner com aviso permanente de que não são fills de corretora, e rejeitar arquivos que tentem alegar modo live/stop nativo/PnL real. O fluxo é de importação manual read-only até existir operador de feed intrabar e acesso privado autorizado. Evidências em `docs/J5_PERSISTED_PAPER_MOBILE_D407.md`.


## J2/J4 D410 — escopo automático e gate de segurança do monitor PAPER

O monitor finito liga a coorte dinâmica N50 já mantida na J1 ao socket público e ao router AUTO4, incluindo posições externas ao ranking. Exige cobertura ACK+snapshot válida e recente de todo o escopo antes de qualquer nova reserva de saída PAPER; mantém os mesmos journals e a política stop-first. Testes offline provam bloqueio com 49/50 e manutenção do UNKNOWN, sem atribuir confiabilidade 24×7 ou vantagem estatística. Código ainda não liberado para execução na VPS. `docs/J2_J4_CURRENT_N50_PAPER_SCOPE_GATE_D410.md`.


## J2/J4 D411 — isolamento da proteção de posições

A saúde completa do N50 orienta seleção/monitoramento de oportunidades, não bloqueia proteção hipotética de posições existentes. O motor PAPER recebe apenas ticker próprio pós-ACK e recente, com stop antes de parcial e idempotência no AUTO4. A avaliação de cobertura ampla segue separada e degradada se qualquer instrumento do N50 estiver ausente. Testes offline; feed real e 24×7 não homologados. `docs/J2_J4_POSITION_EXIT_VS_N50_HEALTH_D411.md`.


## J5 D412 — interface móvel de diagnóstico da sessão de preços

A tela do aplicativo passa a importar o relatório sanitizado da ponte pública N50 → PAPER de D410/D411, mostrando qualidade do universo e processamento de posições separadamente. Sempre rotula a origem como declaração de arquivo não autenticada, sem atualizar posições automaticamente ou afirmar feed 24×7. Proíbe a importação de alegações de stop/ordem/resultado real. Evidência em `docs/J5_PAPER_WS_HEALTH_D412.md`.


## J2/J4 D414 — reconstrução segura após ACK no feed público Bybit

A primeira sessão real de teste comprovou que snapshots/deltas podem chegar antes da resposta de confirmação: BTC 7 e N50 263 quadros pré-ACK, ACK=1 e delta posterior sem snapshot local. Corrigir supervisor D386 com quarentena estritamente limitada em memória, reidratação causal *somente* após ACK e nenhum callback de pré-ACK, mantendo a função do diário AUTO4 intacta. Testes sintéticos verificam contratos e limites, mas homologação real depende de nova sessão em VPS autorizada. `docs/J2_REAL_WS_ACK_SNAPSHOT_REHYDRATION_D414.md`.


## J2 D415 — validar cruzamento de sequência e timestamp da Bybit

BTCUSDT em feed público verdadeiro recebeu 65 quotes frescas pós-ACK; N50 recebeu 73 quotes para 33 instrumentos, interrompido em `conflicting_replay`. Para não confundir sequência de matching engine com identificador exclusivo de atualização parcial, D385 passa a aceitar `cs` estável apenas com avanço inequívoco de `ts`, preservando idempotência e fail-closed no mesmo instante, na ordem temporal regressiva ou sem snapshot. Regressões offline + teste real owner curto antes de alegar monitor 50/50 ou J6. Ver `docs/J2_REAL_N50_CROSS_SEQUENCE_D415.md`.
## J4/J6 D433 — fills PAPER causais opcionais integrados no código

PR #730 integrada em `main` SHA `74008194a4ab07af70e7de3837bbc9b5a2e50d39` após CI Linux/Windows/Chrome verde. O roteador D391 pode aplicar política D394 a reservas de saída AUTO4 usando ticks posteriores e hipóteses explícitas de latência e liquidez; não há fill de exchange, sinal prospectivo, feed live continuamente acoplado ou release VPS. A jornada J4/J6 continua incompleta: próximas capacidades verificáveis incluem operador PAPER event-driven isolado, recuperação/UNKNOWN, feed Bybit público com frescor e observabilidade J5 temporal sem demo fixa, com gate operacional para qualquer instalação. Ver issues #676, #677 e #7.


## J2/J6 D434 — candles Bybit confirmados alcançam fronteira J2 de pesquisa

A PR #731 foi integrada à main SHA `cd54ea7ed8e720d6214f41f83cefe899c774547b` após CI Linux/Windows/Chrome verde. Reutiliza parser e journal Bybit de closes confirmados, entrega `ClosedCandle` de qualidade pública **não verificada** e mesma transação auditada, com proteção contra gaps, replay inconsistente e concorrência. **Aceite parcial de integração de dados** apenas: sem autorização de sinais, sem RiskGate/AUTO2, sem operador PAPER prospectivo conectado ao WS, sem implantação ou ordem real. Próximo marco nas issues #677 e #676: pesquisa J2 causal sobre dados observados + feed público isolado, depois integração de PAPER sob gates próprios.

## J2 D435 — pesquisa sobre candles públicos confirmados

A avaliação causal de hipóteses sobre dados observados D434 foi integrada pela PR #732, SHA `caf9fcfc688434b0b2f47d0ae1fc67b933f48503`, CI Linux/Windows/Chrome verde no HEAD `66aa214d65d64e9929b46624ce676ab10c634d91`. Evidencia LONG/SHORT/abstenção e matemática J2 sem permissão de sinal, ordem ou PnL. **Não prova receptor Bybit prospectivo nem serviço PAPER.** Próximo marco #677: execução finita real/isolada do feed confirmado para pesquisa e cronologia end-to-end; somente após gates técnicos e financeiros permitir cenário PAPER, sem ordens reais.

## J2 #677 / D436 — composição do close confirmado até a hipótese de pesquisa

O operador D436 reutiliza os contratos de close confirmado, journal e D434/D435. Cada lote com ACK persiste no SQLite próprio, é reauditorado e atualiza a hipótese do último candle fechado ou uma abstenção sanitizada. `python -m scripts.demo_j2_prospective_bybit_research_d436` não importa JSON, cria/remove o journal temporário e demonstra LONG não autorizado. Não chama RiskGate/AUTO2/AUTO4, não cria posição/PnL, não usa rede, J1 owner ou VPS. Próximo passo: callback no lease WebSocket opt-in e projeção J5; sem alegar observação pública real ou serviço contínuo antes do gate.

## J2/J5 D436 — sessão WS finita de pesquisa e terminal no Console

O D436 está preparado para processar frames públicos Bybit modelados durante uma sessão supervisionada com transporte injetável, sem ordens. Callback pós-ACK/pós-append publica no J5 um relatório versionado e não autorizante; ao término a interface deve mostrar “Sessão encerrada”, expirar dados e bloquear hipóteses antigas. Prova de fake socket + journal D434 + D435, regressões backend/browser e CI Linux/Windows/Chrome **aprovadas** na PR #733, merge SHA `4ca5f3db8417771154e28341e1636405a148d782` (HEAD de CI `7c41d285ceb14ba6c7c0d8945e0d39a0320665be`). A observação real/operador PAPER contínuo J6 **não está** aceito por esta entrega; #677 permanece aberta.


## J2 → J3 → J4 / D447 — entrada observada até intenção PAPER

**Implementação da fronteira, ainda sem homologação:** série de candles públicos confirmados D434/D435 pode produzir hipótese LONG/SHORT pesquisada; ticker D385 fresco posterior ao close, filtro J3/PRE2 de alvo líquido e risco hipotético, margem PRE11 e AUTO8/RiskGate determinam se uma intenção OPEN PENDING é reservada no AUTO2, com alavancagem da nova entrada em receipt. Repetição é bloqueada transacionalmente, sem um fill ou posição inventados. A jornada de produto ainda depende de escopo dinâmico N50, entrada integrada ao worker D444, execução PAPER honesta, validação J3 OOS e prova operacional J6; no momento nada foi implantado na VPS e a PR #734 segue draft. Contrato `docs/J2_J3_PAPER_ENTRY_D447.md`.


## J2/J3/J4/J5 D448 — percurso PAPER integrado, sem ordens

D436 recebe closes confirmados no journal J2; D435 pesquisa hipótese causal; D447 passa por custos/risco e só cria OPEN PENDING; D448 exige BBO posterior e condições conservadoras para FILL de **simulação** no AUTO2. O mesmo evento e receipt alimentam AUTO4 e o plano de stops/parciais; o manifesto D425 alimenta o monitor D444/D445 e a consulta J5/D446. Falhas no meio das gravações podem ser retomadas sem novas intenções/quantidades. Demonstração determinística LONG/SHORT com parser de frames D436, SQLite real, parcial D391 e J5: `scripts.demo_j2_j4_observed_paper_cycle_d448`. O ciclo ainda não tem fonte N50 real contínua, prova de fill/liquidação ou serviço PAPER implantado; J3 OOS e J6 permanecem gates, sem negociação real.


## J2/J3/J4/J5 — D449/D450: integração de dois feeds públicos a PAPER

D449 recebe closes J2 auditados dos contratos da mesma hora (1..50), compara com BTC e conduz a hipótese D435 às telas de custo J3 e risco D447, intenção PAPER AUTO2, BBO posterior D448 e posição AUTO4 com plano de saídas J4. Prioriza o ticker das posições mantidas para stops e parciais, independentemente da disponibilidade dos 49 demais ativos. D450 usa supervisores de kline.60 e tickers.* existentes em paralelo, sob opt-ins e lease finito. A coorte dinâmica real e os dados de risco/fees/funding/liquidação ainda não foram conectados como serviço na VPS, logo não há trading real ou produto 24x7. A prova atual é protocol replay com 50 membros, sem websocket genuíno nesta unidade.


## D451/D452 — evolução contínua de J2 e J4 sem reiniciar J1

J2 obtém N50 **provisório** a partir de Bybit instruments-info paginado e ticker rolling turnover24h, com BTC sempre como contexto. Persistência de coorte por membros e filtros protege o histórico de 24h contra reset de ranking e impede misturar epochs; atualizações de composição criam novo journal e precisam de novo warmup. J4 substitui observação sempre-zero de tests pela reconstrução de risco dos diários AUTO2/AUTO4 e mark público posterior. A ligação D450 seleciona ranking, abre duas streams públicas em paralelo e conduz hipóteses D435/D447/D448 a PAPER e à tela J5. Ainda sem serviço VPS, captura pública contínua, PnL líquido validado, funding/liquidação ou ordens. Ver docs/J2_DYNAMIC_PUBLIC_N50_PAPER_D451_D452.md.


## J2/J4/J6 — entrega D462/D463 (21/11/2026)

**Implementado no GitHub:** seleção dinâmica N50, 50×24h histórico REST selado, unificação somente no leitor com última hora WS confirmada, D435→D447/PRE11/RiskGate/PAPER, renovação assíncrona de contratos com cotação pós-GET, e parâmetro de aquecimento REST automático no candidato de serviço J6. **Comprovado até aqui:** D461 1.200 candles históricos reais e 9 hipóteses de pesquisa reproduzíveis; D462 ensaio integrado offline com 50 WS `confirm:true` e coorte pesquisada. **Não comprovado:** última vela de 1h WS real no código D462/D463, abertura PAPER dinâmica real, reinício com posição nova, serviço/painel publicado ou resultado líquido validado. Foco da continuação: trial ao vivo finito como `cia-probe`, fechamento verificável, testes de metadados pós-GET, saída de posições PAPER no J5; não reabrir J1.
