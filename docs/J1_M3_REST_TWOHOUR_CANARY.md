# J1/M3 — canário REST de duas horas consecutivas (OFF por padrão)

## Por que M3
M1/M2 (#527/#529) têm writer REST incremental e corte UTC; CI em fixtures NÃO demonstra ingestão real. M3 é um processo finito owner-only, duas chamadas ao worker na janela de UTC HH:02, com persistência isolada. Não instala timer, não opera ordens nem valida crypto-only/Top50. #429, #319 e #2 permanecem abertas.

## Contrato
- Sem três flags explícitas, nenhuma rede nem escrita. Exige usuário POSIX não root, diretório D264 privado e diretório PAI de output 0700 do owner.
- Output novo: `/home/cia-probe/agent/j1-rest-m3-private` (deve NÃO EXISTIR no início). É criado 0700 pelo processo; SQLite e lock 0600. Fonte D264 lida somente read-only e verificada por digest; não escrever no censo ou journal WS.
- Início no próximo fechamento HH:02 UTC. Cada rodada em [HH:01,HH:15]; duas horas consecutivas, sem tentativas extras. O worker tem dois GETs iniciais de 24h (2×24 candles), seguidos de dois GETs de uma hora (2 candles); a contagem exata depende do sucesso das respostas. Um erro aborta a segunda rodada.
- Auditor read-only: `PRAGMA integrity_check`, 2 linhas em `published_hour` para horários consecutivos, 50 candles no total, dois cursores até segunda decisão, digests de vela e contiguidade via replay compartilhado. `two_hour_canary_verified=true` somente sob esses critérios. Não equivale a 24/7 nem a registro temporal de identidade de mercado.
- O processo aguarda no máximo duas horas para a primeira janela e depois a segunda. Se a janela for perdida, falha sem recuperar retroativamente.
- Saída JSON resumida em stdout, sem símbolos, preços ou dados privados.

## Execução futura — gate operacional, não executada nesta PR
Operador deve conferir SHA exato do merge, checkout limpo, hostname, NTP, usuário `cia-probe`, integridade do snapshot D264 e a ausência do novo output. **Não executar o canário duas vezes no mesmo output.**

Exemplo de execução uma vez na VPS, por titular com acesso root, somente após gate da instalação/transient unit:

```bash
set -euo pipefail
REPO=/home/cia-probe/agent/repo
PY=/home/cia-probe/agent/ws-venv/bin/python
FROZEN=/home/cia-probe/agent/j1-global-closed24h-private/run
OUTPUT=/home/cia-probe/agent/j1-rest-m3-private

test "$(hostname)" = srv1319424
test "$(timedatectl show -p NTPSynchronized --value)" = yes
test -x "$PY"
test -d "$FROZEN"
test ! -e "$OUTPUT"
test ! -L "$OUTPUT"
runuser -u cia-probe -- test -r "$FROZEN"
runuser -u cia-probe -- git -C "$REPO" diff --quiet
runuser -u cia-probe -- git -C "$REPO" diff --cached --quiet
# Conferir SHA do merge verificado antes de substituir:
EXPECTED_SHA=<SHA_MERGE_CONFERIDO>
test "$(runuser -u cia-probe -- git -C "$REPO" rev-parse HEAD)" = "$EXPECTED_SHA"

systemd-run --unit=cia-j1-m3-rest-canary --collect \
  --property=User=cia-probe \
  --property=WorkingDirectory="$REPO" \
  --property=Type=oneshot \
  --property=TimeoutStartSec=10800 \
  --property=Restart=no \
  --property=UMask=0077 \
  --property=NoNewPrivileges=yes \
  --property=ProtectSystem=strict \
  --property=ReadWritePaths=/home/cia-probe/agent \
  "$PY" -m scripts.run_j1_rest_twohour_canary \
  --frozen-directory "$FROZEN" --output-directory "$OUTPUT" \
  --allow-public-network --allow-private-storage \
  --confirm-region-and-personal-research
```

O comando `systemd-run` cria **unidade transitória**, não um timer periódico nem um serviço permanentemente instalado. `--collect` pode remover metadados de unidade após terminar: o operador deve consultar o journal sem depender da unidade permanecer instalada. `ReadWritePaths` foi amplo para contemplar o arquivo de saída criado no mesmo diretório, não autoriza outras escritas; ajustar a um subdiretório pai privado e preexistente no endurecimento operacional se necessário.

Consulta read-only após disparo:

```bash
systemctl show cia-j1-m3-rest-canary.service -p ActiveState -p SubState -p Result -p ExecMainStatus || true
journalctl -u cia-j1-m3-rest-canary.service -n 30 --no-pager
```

Nenhuma prova VPS, instalação, journal, operação real ou custo foi produzida por esta entrega. Se o titular não puder iniciar a unidade, isso permanece um gate externo; o trabalho em J2/J3 offline pode continuar separadamente.
