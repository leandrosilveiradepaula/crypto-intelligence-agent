# J1/D327 - nao derrubar N50 WS por last-trade de candle aberto

## Evidencia real do incidente

D326 foi reativado no servidor 13/11/2026 04:39Z, com 5 testes offline
locais OK e timers WS/rotacao ativos; primeira execucao 04:59:31 -
05:00:02 terminou exit 65. Journal sanitizado coletado diretamente via
gateway, sem segredos: 569 frames, ACK=1, 50 mensagens pre-ACK descartadas,
zero fechamentos gravados e failure_category=ws_open_candle_clock_invalid.
OnFailure restaurou N2 e desabilitou WS/rotacao corretamente. D323 ainda
nao pode comprovar 50x24h ou rotacao >=36h.

## Interpretacao e decisao

O contrato oficial Bybit separa eventos provisórios confirm=false dos
candle definitivos confirm=true. O campo timestamp representa o instante
da ultima negociacao, enquanto ts indica quando o servidor montou o
snapshot. O codigo D313 exigia em todas as atualizacoes ABERTAS
timestamp dentro de start..end. Em uma virada UTC, esse campo pode
provisoriamente apontar fora da nova janela. O erro real prova a classe
open_candle_clock_invalid, mas NAO prova qual das condicoes internas foi
violada (nenhum payload bruto foi armazenado). Portanto uma correcao
conservadora mantem as validacoes do envelope, ACK, topico, intervalo
'60', start/end inteiros alinhados, OHLC e tipos; mas DESCARTA
apenas a atualizacao confirm=false quando seu ultimo timestamp
estiver fora de start..end, sem contabiliza-la como candle ou usá-la
como evidência.

O contador sanitizado ignored_open_trade_clock propaga-se do parser
de batches ao supervisor, owner e CLI; zero simbolos, precos ou payloads
sao emitidos. Todos os campos closed confirm=true mantem integralmente
os validadores D313/D326 (incluindo timestamp de negociacao dentro da
janela, sequencia, recebimento posterior ao fechamento, digests).
Qualquer envelope/intervalo/alinhamento ou candle confirmado inválido
continua falhando fechado e aciona N2.

## Provas e proximas acoes

tests/test_j1_n50_ws_open_trade_timestamp_d327.py testa timestamp
provisorio anterior/posterior ao candle, zero SQLite, nenhuma promocao,
candle confirmado invalido rejeitado, topico/grid/interval/ohlc falhando,
e sessao com anomalia de open seguida de 50 confirmacoes reais de
fixture, 50 linhas integros e contador sanitizado. Regressões D326,
D325, D313 e demais suites Linux/docs, Windows/offline e PAPER.

Nao executar nenhum GET para recuperar 50 membros, nao repetir
bootstrap D322. Apos CI/review/merge, fazer recovery root IN-PLACE
por script D326 de forma segura (D326 recovery original apenas aceitava
OLD_SHA D322 e precisa de variante pinada para o checkout D326 atual).
Validar primeiro fechamento REAL e preservar retorno automatico N2.
Sem ordens reais ou alegacao de lucro.
