# D439 — operador de host para piloto público finito Bybit (J2/D437/D438)

Este procedimento usa a sessão root **do host** `srv1319424` somente para preparar/verificar a execução; o programa Python de rede roda **exclusivamente** como `cia-probe` não-root. O gateway MCP atual não tem capacidade de trocar de usuário e portanto NÃO pode substituir o terminal root do host. Não ampliar as permissões do gateway.

## Preflight (sem rede, sem escrita)

Script versionado: `deploy/vps/j2_public_kline_owner_d439_once.sh`. Conferir SHA completo do PR draft #734, baixar a versão por URL GitHub RAW pinada nesse SHA por HTTPS, executar `bash -n`, depois `bash SCRIPT --preflight SHA`. Não usar `main` ou URL móvel. O modo preflight exige host exato, shell root host, `runuser` funcional, NTP, owner POSIX, ambiente `ws-venv`, biblioteca `websockets.sync.client`, checkout J1 existente e ponteiro privado ativo `j1-n50-ws-epochs/active` revalidável. **Nenhum WebSocket é aberto no preflight; nenhuma gravação deve acontecer.**

Exemplo genérico (substituir o SHA de 40 caracteres pelo HEAD verificado do PR):

```bash
set -euo pipefail
SHA='COLOCAR_SHA40_DO_HEAD'
TMP="$(mktemp)"
trap 'rm -f -- "$TMP"' EXIT
curl --fail --location --silent --show-error --proto '=https' --proto-redir '=https' --tlsv1.2 --max-time 60 --output "$TMP" \
  "https://raw.githubusercontent.com/leandrosilveiradepaula/crypto-intelligence-agent/$SHA/deploy/vps/j2_public_kline_owner_d439_once.sh"
bash -n "$TMP"
bash "$TMP" --preflight "$SHA"
```

Comprovante necessário: `D439_HOST_PREFLIGHT=PASS_NO_NETWORK_NO_WRITES` e `D439_PUBLIC_WS=NOT_STARTED`. Qualquer `D439_BLOCKED=...` encerra a etapa: não executar o piloto, não relaxar proteção, relatar apenas categoria sanitizada.

## Piloto finito (gates humanos explícitos)

Somente após preflight aprovado e **revisão efetiva** da elegibilidade regional, dos termos aplicáveis a pesquisa pessoal e dos direitos de uso dos dados, executar no host a mesma versão pinada com `--capture SHA`, estabelecendo quatro variáveis de consentimento como `YES`: `CIA_D439_CONFIRM_PERSONAL_RESEARCH`, `CIA_D439_CONFIRM_REGION_ELIGIBLE`, `CIA_D439_CONFIRM_DATA_RIGHTS` e `CIA_D439_CONFIRM_PUBLIC_WS`. Não preencher por suposição e não simular IP/região ou usar VPN para contornar restrições. Estes são compromissos operacionais do operador, não detectáveis pelo código.

```bash
CIA_D439_CONFIRM_PERSONAL_RESEARCH=YES \
CIA_D439_CONFIRM_REGION_ELIGIBLE=YES \
CIA_D439_CONFIRM_DATA_RIGHTS=YES \
CIA_D439_CONFIRM_PUBLIC_WS=YES \
bash "$TMP" --capture "$SHA"
```

O processo cria SOMENTE diretório de pesquisa owner 0700 em `/home/cia-probe/agent/j2-d439-public-XXXXXXXX`, faz clone/fetch pinado em SHA e verifica HEAD/limpeza, valida a coorte N50 J1 novamente, então inicia `python -m scripts.run_j2_public_kline_session_d437_once` com 240s, 24.000 frames e 1 sessão (via timeout externo 300s). O script não instala daemon/timer, não altera J1, não acessa conta privada, não envia ordem, não instala dependências ou pacote pago. Dados brutos e journal ficam privados; stdout expõe só contagens sanitizadas.

**Interpretação dos resultados:** ACK de inscrição prova somente ACK; atualizações de vela aberta não comprovam fechamento, e um `closed_events_appended > 0` confirma no máximo evento público observado não autenticado, não histórico suficiente para estratégia ou comercial. Um teste de quatro minutos pode terminar antes do fechamento da vela horária: isso **não significa falha da Bybit** e não autoriza gerar candle artificial. Falhas e exceções mantêm abstenção. Nem CI verde, nem WSS real, nem 50 membros provisórios equivalem a feed N50 contínuo 24x7/PAPER homologado.

Antes do piloto, confirmar também que a source de uso é permitida para a região/conta (e, se necessário, usar o domínio regional oficial aplicável; o contrato implementado está pinado em `stream.bybit.com`, não escolher outro host automaticamente). O endpoint oficial da Bybit para linear é `wss://stream.bybit.com/v5/public/linear`; mudanças exigem decisão e testes.

## Limitações atuais

- O conector VPS vigente executa como root restrito sob `agente-mcp` e `runuser` nele falhou `cannot set groups: Operation not permitted`; **não é executor de host**.
- A coorte owner atual pode estar ausente, expirada, rotacionando ou sem BTCUSDT. Nesse caso, o script retorna categoria `BLOCKED` e deixa J1 intacta.
- Não interpretar uma captura finita como monitoramento contínuo de posições, nem fazer merge do PR draft #734 antes da prova pública real e revisão operacional.
- Fonte de verdade: issue #677, PR #734 e `docs/OPERATIONAL_STATE.md`.
