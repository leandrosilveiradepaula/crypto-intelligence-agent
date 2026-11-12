# J2/D300 — pesquisa observacional sobre 24 candles N50 realmente auditados

## Objetivo

Substituir a dependência exclusiva das fixtures sintéticas no **estágio de observação** por uma ponte read-only do journal N50 real D294, preservando a separação absoluta entre pesquisa descritiva, sinais de entrada, gestão de risco e negociação. Não modificar o cálculo sintético J2/PRE1–PRE5 nem atribuir aos dados da Bybit autenticação externa ou confirmação global do Top50.

O módulo `crypto_intelligence_agent.j2_n50_private_screen.audit_private_n50_research` lê somente como proprietário POSIX não-root, a partir da raiz privada N50 preparada no D297, e exige:
1. manifest D287 presente, causalmente válido e dentro de 48h, apontado pelo ponteiro D294 owner-only com digest idêntico;
2. journal M1 íntegro: auditor read-only D290/D292 replaya **todos os candles e cursores** da coorte de 50 antes de qualquer métrica;
3. checkpoint real `published_hour`, sem gaps históricos, HALT ou publicação parcial, estritamente dentro da janela observável (última publicação não mais antiga que 2h);
4. **24 candles 1h fechados e consecutivos por cada um dos 50 membros** no mesmo checkpoint UTC, consulta SQLite somente `mode=ro`, `query_only`, limite de 1.201 linhas, digest SHA256 e validação Decimal individual em cada uma das 1.200 linhas.

Não é permitido preencher períodos ausentes com candles futuros, consultar ticker móvel, carregar um universo retrospectivo, misturar dois epochs ou aceitar símbolos fora da coorte. Snapshot SQL após a auditoria confere ainda a última publicação contra o digest do manifest e revalida os digests dos 1.200 dados usados. A função é *opt-in* e desiste em caso de falha.

## Indicadores puramente descritivos

Cada série íntegra gera, na precisão Decimal de 50 dígitos:
- **retorno observado nas 24 barras** = último fechamento / abertura da primeira barra - 1, sem inferir retorno futuro;
- **mean true range nas 14 barras finais / fechamento** (ATR simples limitado a janela, sem marcação futura; não é sinal nem stop);
- **turnover USDT total** em 24 candles, e turnover da última barra sobre a média das 23 precedentes;
- fechamento acima da máxima das 23 barras anteriores, abaixo da mínima anterior, ou dentro delas — observação do *último candle já fechado*, não sugestão de operar o rompimento;
- diferença de retorno do ativo frente ao BTCUSDT **dentro da mesma janela e coorte**. Se BTCUSDT não estiver presente, `btc_context_missing_research_only` e nenhuma força relativa atribuída.

A ordenação em `research_rows` é pelo retorno passado, do maior para o menor, **não por probabilidade de valorização, lucro esperado nem prioridade de ordens**. O digest da janela é derivado de registros já persistidos e serve somente à reprodutibilidade.

## Saídas e privacidade

CLI: `python -m scripts.observe_j2_n50_private_once --allow-private-readonly-audit`. O default reporta apenas resumo sem símbolos nem preços. Para inspeção privada explícita, acrescentar `--include-private-symbols`; nunca executar em serviço público, dashboard sem autenticação ou logs de produção. Não há chamadas de rede, INSERT/UPDATE, arquivos novos, trading, credenciais ou compras.

Status `descriptive_research_ready` exige BTC e os 50 históricos íntegros; `btc_context_missing_research_only` permite somente descrição sem comparativo. Mesmo em sucesso, `approved_for_signals=false`, `approved_for_live_use=false`, `marketwide_top50_verified=false`, `crypto_identity_independently_verified=false`, `source_authenticated=false`, `orders_sent=false`.

**Não conectar automaticamente à J2 de sinais ou à J4 de execução**. Pesquisa futura deve usar um portão separado de dados autenticados/recência, custos, estatísticas OOS e aprovação do Product Owner antes de qualquer uso operacional de sinais. 50x é parâmetro de pesquisa; esta etapa não calcula risco ou ordens.

## Testes e evidências

`tests/test_j2_n50_private_screen.py` executa SQLite owner-mode 0700/0600 com 50 contratos × 24 velas de fixtures, digests reais, scope/pointer e replay J1 verdadeiro, além de adulteração, BTC ausente, relógio velho, sem primeiro checkpoint, controle de acesso e causalidade. VPS executou **10 testes PASS** no worktree candidato `e77430033b5dfba5e3e9c44027e78d105d4ea2d8`; isso valida implementação offline, NÃO produção nem desempenho da estratégia.

A primeira captura real N50 da VPS foi `epoch_started` às 04:13:28 UTC de 12/11/2026, com 372 GETs e **zero candles**; só após o primeiro writer efetivo a ponte pode retornar métricas reais. Monitor de continuidade D299 permanece independente. Gate final: CI Linux/Windows/PAPER HEAD SHA + revisão + merge sem deploy; chamar CLI owner somente leitura após o checkpoint comprovado.
