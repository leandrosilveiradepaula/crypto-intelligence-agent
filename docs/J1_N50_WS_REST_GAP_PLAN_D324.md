# J1/D324 - REST somente para lacunas WebSocket verificadas

## Motivacao

Depois da falha real N50 com retCode 10006, a estrategia WS-first
deve evitar 50 GETs de candles a cada hora. D313 comprova 50/50
confirmados pela WebSocket; D324 planeja somente as requisicoes
necessarias para itens comprovadamente AUSENTES do SQLite WS.

## Contrato

A auditoria D313 agora produz, no MESMO snapshot SQLite de replay
completo de cada payload/digest/UTC, uma tupla privada dos simbolos
efetivamente ausentes no fechamento. A lista nunca entra no relatorio
sanitizado nem em repr do objeto.

A funcao pura plan_n50_ws_rest_gap_targets:
- exige manifesto D287 e scope WS de 50 contratos exatos,
  sem mercado global/identidade externa presumida;
- espera 3 a 15 minutos depois do fechamento UTC para nao confundir
  frames atrasados com lacuna permanente;
- se 50/50 confirmados, retorna ZERO GET REST planejado;
- se faltam 1, 2 ou 3, prepara somente 1, 2 ou 3 URLs de
  GET /v5/market/kline para a mesma hora fechada;
- se faltam 4 ou mais, ou os dados estao alterados, recusa
  qualquer GET automatico, preserva prova e pede diagnostico;
- nao executa GET, nao repete 10006, nao conecta WS, nao insere
  candles REST no journal WS, nao cria PIT, nao envia ordens.

URLs com simbolos ficam apenas em private_get_urls e nao sao
serializadas pelo sanitized_report(). Recebimentos REST futuros
PRECISAM ser separados dos WS confirmados e conter origem propria,
limites de quota e autorizacao owner independente.

## Validacao e implantacao

tests/test_j1_n50_ws_rest_gap_plan_d324.py cobre 50/50 zero GET,
49/50 um GET, 47/50 tres, 46/50 abstencao, hora exata,
invariante de privacidade, replay adulterado, futuro e bounds.
Regressoes: D313 e SQLite WS legado. CI Linux/docs,
Windows/offline, Chrome/PAPER no SHA final.

Esta entrega nao instala o D322 e nao fecha #585/#429/#319.
Nao colocar esta camada de planejamento no timer atual sem
integracao supervisionada e aceite de rede/quotas.
