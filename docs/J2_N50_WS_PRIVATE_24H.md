# J2/WS-READ1 — pesquisa N50 sobre journal WebSocket auditado (#624)

## Problema que esta integração resolve
A coleta N50 operacional passou a usar o journal privado `ws-confirmed.sqlite` da J1/D313, enquanto a pesquisa privada J2/D300/D308 depende do journal N50 REST gerenciado anterior. Por isso, obter 24 horas de WS **não** faz o pesquisador REST antigo funcionar por si só.

## API offline e causal
`crypto_intelligence_agent/j2_n50_ws_private_screen.py` fornece `research_private_ws_n50_24closed(...)`. O chamador owner deve selecionar **antes** os objetos atuais:
- manifesto D287 `ranked_scope` validado em `observed_at_ms`;
- escopo WS D314/D316 `OfflineReviewedStreamScope`, com exatamente os mesmos 50 símbolos e metadados imutáveis;
- `SQLiteOfflineClosedStreamJournal` da epoch apropriada, em arquivo `ws-confirmed.sqlite` owner 0600 e parent 0700; somente `mode=ro`, `PRAGMA query_only=ON`, `BEGIN`.

Exige opt-in `allow_private_readonly_research=True`; por padrão é `owner_optin_required`. Exige usuário owner não root (o override `owner_ok` é somente para fixture/testes). Não adivinha paths privados nem escolhe a epoch por conta, não cria cliente de rede, não acessa REST, não coleta velas, não escreve em nenhum banco e não envia ordens.

A decisão UTC exata representa o último fechamento de candle e só é elegível entre **+3min e menos de +59min** depois da hora. Leitor exige 50 × 24 candles fechados consecutivos na mesma coorte; hash, recibos, unidade de volume BASE/turnover USDT, vínculo à instrumentação WS e ausência de dados futuros são validados usando `_validated_payload` e **duas auditorias independentes `SQLiteOfflineClosedStreamJournal.audit`** ao redor de um snapshot SQL readonly, comparando digests de journal/ranking/última hora e contagem. Registros futuros no journal relativos ao `observed_at_ms` causam abstenção. Arquivo sem owner/DAC, symlink, scope divergente, gap, 49/50, schema ou payload inválido é rejeitado.

## Métricas e privacidade
Reutiliza **diretamente** `j2_n50_private_screen._metrics` para 24 barras: retorno em 24 candles, ATR % da janela final de 14, razão de turnover da última vela e rompimento comparado à faixa das 23 anteriores. Se BTCUSDT integra a coorte, mede também força relativa vs BTC. Ordenação de pesquisa descritiva por retorno, empate alfabético (não é score de execução).

Sem opt-in de símbolos, o relatório `j2-ws-n50-descriptive-24closed-v1` retorna somente contagens up/down/inside, 50 auditados, status e SHA de janela, com `research_rows=[]`; os símbolos e indicadores detalhados ficam exclusivamente em memória no retorno do opt-in `include_private_symbols=True` (nunca em logs GitHub). `ws_journal_integrity_replayed` prova apenas que a cópia local de 24h foi reproduzida, **não** o witness D323 completo, que também verifica o estado operacional. Flags `formal_d323_24h_verified`, `continuous_collector_verified`, `rotation_36h_live_verified`, `marketwide_top50_verified`, `crypto_identity_independently_verified`, `source_authenticated`, `approved_for_signals`, `approved_for_live_use`, `financial_backtest_approved` e `orders_sent` são sempre falsas.

## Homologação antes de usar
`tests/test_j2_n50_ws_private_screen.py` cria 1.200 linhas WS inteiramente sintéticas em journal SQLite privado 0600. Comprova 50×24, BTC e as métricas D300, privacy-by-default, ausência de sinais/ordens, 49/50, adulteração hash, data futura, UTC, time drift, path symlink/nome REST, fonte inválida e desvio entre auditorias. CI Linux/docs, Windows/offline e PAPER/mobile no SHA final; merge seguro sem deploy. A **VPS D336 continua intocada**. Instalação/uso owner real requer gate posterior e esperar 24 horas de candles WS; a primeira hora pós-D336 em 13/11/2026 18:00 UTC foi auditada 50/50, mas o ciclo de 24h ainda não foi comprovado. Custo adicional R$0,00.

O leitor J2 é um adaptador de pesquisa; conectar watchlist D308 ou estratégias automáticas requer contratos adicionais, validação prospectiva e os gates J1/J3/J4/J6. Não se publica nenhuma recomendação financeira nem ordem real.
