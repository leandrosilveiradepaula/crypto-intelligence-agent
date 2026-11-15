# J2/WS-WATCH1 — watchlist N50 por velas WebSocket fechadas (#638)

## Decisão e valor para o produto

A J2 não precisa aguardar outra jornada de desenvolvimento nem uma nova fonte REST para estudar entradas. O motor D308 já faz a triagem de **rompimentos de alta e baixa**, vantagem relativa ao BTC e aumento do turnover USDT com uma regra reprodutível. A fonte D308, porém, era o journal REST antigo D300. Esta integração usa **o leitor WS J2/WS-READ1 existente** sem modificar sua lógica de auditoria.

O resultado fornece à futura tela de oportunidades uma **watchlist observacional**: quantas observações cumpriram critérios de alta/baixa e, apenas com opção privada explícita, até cinco representantes de cada direção. **Não é um sinal de entrada, probabilidade, indicação de compra/venda ou autorização de ordens.** A J3 deverá medir resultados líquidos OOS e o risco intrabar antes de qualquer uso operacional.

## Contrato do adaptador

`crypto_intelligence_agent.j2_n50_ws_descriptive_watchlist.build_ws_descriptive_watchlist(source, now_ms=..., include_private_symbols=False)` é função pura e não acessa o banco. Exige:

1. Relatório WS `j2-ws-n50-descriptive-24closed-v1` em `ws_n50_descriptive_24h_ready`, produzido por `j2_n50_ws_private_screen` **após** reexecutar o journal `ws-confirmed.sqlite` da epoch ativa.
2. `ws_journal_integrity_replayed=true`; exatamente 50 membros distintos `USDT`, 24 velas fechadas por ativo, três digests SHA256 válidos (janela, escopo, metadados). BTCUSDT presente uma única vez; retorno BTC e relativo recalculados em Decimal **sem floats**. A lista deve estar ordenada pelo retorno passado e ter ranks 1..50; contagens up/down/inside devem bater com as linhas.
3. Decisão em fronteira UTC, após 3 minutos do fechamento e antes da próxima janela de fechamento; retorno futuro, scope misturado, dados insuficientes ou mudança do ponteiro levam a abstenção. O adaptador não pode transformar `50 appends` em `50x24 verificados`.
4. Flags de ordens, sinais, marketwide, autenticação externa, D323, 24/7, fundos, systemd ou mutações inesperadamente positivas são recusadas. Este módulo **não promove** `formal_d323_24h_verified` a verdadeiro.
5. Reutilizar **as mesmas funções puras D308** para validação de cada linha, filtro e ranking, sem duplicar cálculos de indicadores. Alta exige último fechamento acima da máxima das 23 barras anteriores, desempenho relativo BTC positivo, turnover final ao menos igual à média anterior e total >0; baixa é simétrica. Desempates: vantagem relativa, intensidade de turnover, valor nominal fechado, símbolo. São heurísticas de observação, não parâmetros calibrados.

Saída `j2-n50-ws-descriptive-watchlist-v1`: contagens totais, quantidade sem razão de volume, digest da janela e horário, `up_breakout_watchlist=[]` e `down_breakout_watchlist=[]` **por padrão**. Caso `include_private_symbols=True`, até 5 linhas em cada direção incluem símbolo, variação passada, volatilidade observada e turnover textual. Nunca inclui ordem, quantidade de contrato, exposição, stop, preço ou probabilidade de lucro.

## Operação owner read-only e interface

`observe_active_ws_n50_descriptive_watchlist` usa a função existente `observe_active_private_ws_n50_24closed`, que resolve e **revalida** o ponteiro D321 da epoch ativa antes/depois do replay, com owner/DAC já existentes. Dois opt-ins exigidos para habilitar pesquisa; para exportar símbolos privados exige também confirmação independente. O CLI preparado, **sem instalação na VPS nesta PR**, é:

```bash
python -m scripts.research_j2_n50_ws_watchlist_once --allow-private-readonly-research --enable-descriptive-watchlist
```

Não publicar o resultado privado contendo símbolos em GitHub, endpoint público ou logs compartilhados. Depois da janela real e do gate de instalação, o painel J5 poderá consumir somente as contagens do relatório sob contrato separado (ainda não feito nesta PR). O navegador móvel permanece PAPER, localhost-only, sem ordens.

## Testes e aceite

`tests/test_j2_n50_ws_descriptive_watchlist.py` cobre determinismo, 50×24 e BTC, simetria das watchlists REST/WS sob os mesmos dados, ranking/empate, símbolos privados em opt-in, denominadores de volume, falsificação de hash/provenance, 49/50, violação UTC, reordenação, BTC ausente/duplicado, flags adversariais, e ausência de rede/banco/escrita na função pura. As suítes já existentes D308 e D624 devem permanecer verdes em Linux/Windows; QA móvel PAPER também é gate.

**Limites reais:** logs N50 na VPS tinham 18 fechamentos consecutivos 50/50 de uma coorte observados em 15/11/2026 até 09:00 UTC; isso não prova `ws-confirmed.sqlite` 50×24 nem a identidade cripto Top50. D323 e #319 continuam gates J1 autônomos. Esta PR não executa auditoria real, estratégia ao vivo, release, ordens nem API de corretora. Custo adicional R$0.

**Próximo incremento J2 após esta ponte:** mensurar a taxa histórica de observações e seu desempenho subsequente no J3 com universo PIT, custo/slippage/funding e períodos fora da amostra. Não escolher parâmetros olhando os resultados.
