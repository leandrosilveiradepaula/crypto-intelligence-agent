# J1/D325 - N50 WS continua com ate tres lacunas explicitamente registradas

## Defeito corrigido

A instalacao D322 ativa OnFailure para voltar ao timer N2 sempre que o
servico WS retorna diferente de zero. A captura de 49/50 por uma unica
hora tinha status de incomplete_no_pit e retorno 65, desligando N50
antes da proxima hora. Mesmo depois de reiniciar, uma falta entre
candles do mesmo simbolo causava erro de contiguidade no journal.

D325 muda SOMENTE o caminho de servico owner ativo D321, mantendo
CLI/runner de pesquisa tradicionais estritos por default:

- Escrita de lacunas WS passa a ser explicitamente permitida no
  runner do servico, sempre com marcador SQLite de hora faltante.
  Nao ha preenchimento sintetico ou retrocesso de proveniencia.
- Se houver ACK, owner lock, replay/auditoria completos, nenhum GET,
  47..49 confirmacoes e 1..3 faltantes, o servico retorna 0
  para manter o timer WS. O JSON continua com status
  ws_owner_hour_incomplete_no_pit, sem digest 50/50.
- Com 46 ou menos confirmados, perda de ACK, integridade violada,
  falta de opt-in, timeout grave ou erro de socket, retorna 65
  e preserva o OnFailure que restaura N2.
- Uma hora posterior completa volta a produzir 50/50 da propria
  hora, mas NAO conserta a hora perdida. D323 24h continua exigindo
  24 horas consecutivas completas e a politica de proveniencia
  REST / WS permanece separada.
- D324 pode planejar consulta REST somente para 1..3 ausentes,
  porem este codigo nao executa GET REST nem altera o timer existente.

## Provas

tests/test_j1_n50_ws_degraded_continuation_d325.py inclui predicado
fail-closed e CLI systemd de 49/50, 46/50, flags e registros, e tres
horas simuladas 50 -> 49 -> 50 em journal imutavel com um marcador
de lacuna e 149 candles reais, nunca 150 fabricados.

Regressoes D315, D317, D313, D324 e CI Linux/docs,
Windows/offline, Chrome/PAPER no SHA final.
Sem deploy, ordens, live trading ou Top50 global validado.
