# J1/D323 - Verificacao owner de 24 horas N50 WebSocket

## Resultado

Depois da instalacao D322 autorizada na VPS, o novo auditor le o pointer D321,
o manifesto D287, o cache D314/D316 e o SQLite WS separado da antiga REST.
Exige as ultimas 24 velas fechadas de cada um dos mesmos 50 contratos, com
1200 registros no minimo, horario UTC, confirmacao, identidade, digests e
lacunas revisados no mesmo snapshot SQLite read-only. Confere a ultima hora
50/50 e o estado atual dos timers WS e rotacao (ativos), N2 e REST N50
(inativos). Nenhum GET, abertura de socket, escrita, sistema modificado ou ordem.

Resultado positivo: ws_24h_local_evidence_verified. O escopo e local e
observacional. Nao prova origem autenticada, elegibilidade cripto marketwide,
continuidade do processo em cada segundo, rotação real de 36h nem estrategia
lucrativa. Manter #585, #429 e #319 abertas ate provas reais separadas.

## Uso posterior ao cutover

Como usuario cia-probe nao root, em HH:03:00 ate HH:58:59 UTC:

    python -m scripts.audit_j1_n50_ws_24h_once \
      --allow-private-readonly-audit --enable-ws-24h-witness

O comando nao e requisito de deploy. Ele so funciona depois do WS estar
instalado e ter acumulado dados reais. Devolve diagnostico sanitizado:
somente contagens, hashes e indicadores negativos de risco/trading, nunca
simbolos, payload de mercado ou preco.

## Validacao offline

tests/test_j1_n50_ws_24h_witness_d323.py testa 50x24, 49/50, amostra
insuficiente, failback N2, servico WS falho, timer de rotacao desligado,
types/digests adulterados, clock, owner e opt-in. As validacoes D313
existentes testam SQLite e closed frames reais em fixtures, nao network.
Exigir CI Linux/docs, Windows/offline e Chrome/PAPER no SHA da PR.
Codigo nao instala nada na VPS e nao encerra a J1 isoladamente.
