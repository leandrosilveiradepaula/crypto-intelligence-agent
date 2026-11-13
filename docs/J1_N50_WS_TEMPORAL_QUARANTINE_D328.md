# J1/D328 — Temporalmente invalido NUNCA e candle; nao derrubar 50 WS

## Incidente real 13/11/2026 11:00 UTC

O terceiro lease real da coorte N50 (apos D327) terminou exit 65:
ACK 1; 412 frames; 2 snapshots confirm=false com ultimo timestamp fora
da janela ignorados, como projetado; 0 candles fechados persistidos;
failure_category ws_closed_temporal_invalid. OnFailure desligou WS e
rotacao e restaurou N2 com sucesso. Nenhuma ordem, HTTP GET ou perda REST.
A condicao temporal EXATA nao e conhecida porque frames privados nao
sao logados. Nenhum diagnostico inventado.

## Correcao

D313/D326 continua sendo a UNICA autoridade para aceitar candle
confirm=true em SQLite. O novo modulo puro de triagem local identifica
somente tres classes de snapshot CLOSED sem prova:
- timestamp da ultima negociacao fora de [start,end];
- confirmacao recebida ou gerada pelo servidor ANTES da fronteira UTC;
- confirmacao de candle antigo entregue mais de 120s depois da fronteira.

Para devolver a classificacao, todo o restante deve estar correto:
origem/topic 60 pertencente aos 50, estrutura, campos, UTC/grade,
OHLC e volume validos, servidor nao adiantado nem atrasado mais de
30s, escopo e lancamento do contrato causais. Nessas tres situacoes
nenhuma linha entra no SQLite, nenhuma vela e aprovada ou fabricada,
mas o coletor pode continuar aguardando os 50 fechamentos verdadeiros.
O teto de tres descartes por contrato por lease impede ocultar uma
falha sistemica; excedeu o teto, retorno nao-zero e N2 restaurado.
Falhas de envelope, OHLC, servidor/escopo ou membro indevido seguem
fail-closed. A janela de ate 120s e todos os requisitos de D323
permanecem iguais.

Relatorio sanitizado mostra apenas contagens por classe:
discarded_closed_trade_clock, discarded_closed_preclose,
discarded_closed_stale. Nao registra nomes, precos, timestamps,
payload ou mensagens originais. O maximo de tres classes permite
decidir com evidencias se o incidente se repetir.

## Validação e liberação

tests/test_j1_n50_ws_temporal_quarantine_d328.py inclui eventos
confirm=true invalidos e rejeitados pelo parser original; teste
direto de descarte sem gravacao, sessao completa de 50 confirmados
apos evento stale e negativa para OHLC, topico e relogio adulterados.
test_j1_n50_ws_recovery_release_d328.py confere preflight,
testes VPS e rollback; regressoes D313/D326/D327/D325 e CI 3/3.

Root recovery D328 somente DEPOIS de CI/revisao/merge; atualiza checkout
ja instalado do SHA D327 para SHA novo revisado, nao repete D322 ou
os 372 GETs, nao mexe em epoch/REST HALT e preserva N2 em falha.
Aprovar timer NAO certifica 50x24h, rotacao real 36h, trading ou Top50.

## Opt-in restrito ao owner ativo

O novo comportamento de descarte de CLOSED e **OFF por padrao** em `ingest_offline_ws_batch`, `supervise_ws_research`, `run_n50_ws_owner_hour_once` e `run_cached_n50_ws_owner_window`. Apenas `scripts/run_j1_n50_ws_owner_active_once.py`, servico supervisionado com lock e fallback N2, passa `allow_temporal_discard=True` explicitamente. Assim, fixtures e chamadas offline legadas continuam rejeitando temporal invalido imediatamente. Esta separacao foi adicionada apos CI inicial detectar duas regressoes legadas, preservando a seguranca nos consumidores antigos.
