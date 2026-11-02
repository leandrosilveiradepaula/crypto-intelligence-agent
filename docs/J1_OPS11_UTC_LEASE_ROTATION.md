# J1/OPS11 — Rotação UTC protegida dos leases WebSocket

Issue #440, relacionada a #429, #319 e J1 #2. Sem acesso à VPS, rede nova, ordens ou deploy.

## Defeito e correção

O template anterior agendava leases de 3300 segundos com `RestartSec=30s` e `Restart=always`. Como os reinícios não eram alinhados ao fechamento UTC, poderiam coincidir com a transmissão de `confirm=true` e perder um candle definitivo de 1h. A OPS9 ampliou o limite de frames, mas não alterou essa rotação.

OPS11 cria `plan_post_close_lease(now_utc_ms, max_seconds=3590)`, função pura que não lê relógio, rede ou filesystem. O relógio UTC é injetado na borda do serviço. A duração preferencial termina 180s após a próxima hora fechada. Se o alvo estiver a menos de 300s ou além de 3590s, escolhe 300s de alinhamento. Para qualquer fase inteira do relógio em 0..3599 segundos, o fim agendado está entre 180 e 489 segundos após um fechamento UTC. Modo `--rotate-after-close` requer `--seconds 3590` e os quatro opt-ins owner-only já existentes; a modalidade legada sem opt-in permanece inalterada. O orçamento de frames é recalculado para a duração efetiva: `52 * effective_seconds + 4096`, sem exceder 200.000 frames.

O template off-by-default muda a linha `ExecStart` para `--seconds 3590 --rotate-after-close`, conserva `RestartSec=30s`, `StartLimitBurst=6`, `RestartPreventExitStatus=64 65 66 77 130`, `User` não-root e confinamento systemd. **Não instala, inicia nem habilita** qualquer serviço. O usuário não precisa executar comandos para a implementação ou CI.

## Provas, limites e gates

Testes com todas as 3.600 fases de início UTC, milissegundos fracionários, transição de hora, flags faltantes, relógio inválido, cap fora de 3590s, modo legado, ausência de consentimento, orçamento e renderização do template. Rodar:

- `python -m unittest discover -s tests -p test_j1_ws_utc_lease_rotation.py -v`
- `python -m unittest discover -s tests -p test_j1_ws_service.py -v`

CI Linux/docs, Windows/offline e Chrome/PAPER devem passar no SHA revisado; merge SHA-guarded sem produção e pós-merge verificado quando possível. **Um fim programado seguro não garante a chegada do frame**: queda do provedor, latência, reinício, relógio do host e limitações do journal ainda podem criar gaps. Somente autenticação e auditoria da VPS em operação real podem demonstrar entrega; OPS8, soak 24h, reconciliação incremental sem quota 10006, retenção do journal e Top50 marketwide continuam pendentes.

Não há mudança no SQLite REST EXIT5 (evidência histórica: 37.470 candles, dois PIT, retCode 10006 após 168 GETs). Nenhuma ordem ou credencial.
