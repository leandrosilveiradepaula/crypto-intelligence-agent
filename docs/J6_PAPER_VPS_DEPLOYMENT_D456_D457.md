# D456/D457 — Entrega 1: PAPER na VPS, estado operacional e artefato de ativação

## Entrega funcional em código

- D453 já mantém sucessivas sessões REST + dois canais WS públicos (kline/quote) e implementa contingência para posições PAPER existentes quando o N50 falha.
- D456 acrescenta `j5_resident_paper_status_d456.py`: reabre somente arquivo de estado D453 0600, verifica schema estrito, dados sanitizados, staleness/TTL, integridade básica do arquivo, não aceita alegações de stop, ordens reais ou cobertura contínua. `serve_j5_local_readonly.py` disponibiliza novo endpoint `/api/resident-paper-status` somente com opt-in e dono não-root; `web/app/resident-paper.js` apresenta o status em português e apaga o estado quando a leitura falha.
- O CLI D453 agora recebe SIGINT/SIGTERM e encerra depois da sessão atual, sem perder WAL/SQLite. Não há proteção nativa após o encerramento.
- D457 acrescenta preflight `scripts/preflight_j2_j4_paper_resident_d457.py` sem rede/mutações: exige usuário não-root, dois diretórios privados 0700 diferentes, política owner-only 0600 válida e import real de `websockets.sync.client`.
- Unidade de serviço **candidata desativada**, `deploy/systemd/cia-j2-j4-public-paper-resident.service.template`, separa caminhos J2/PAPER, só aceita `cia-probe`, aplica sandbox/memória/CPU/timeout, exige preflight e configura reconexões e status. Não está instalada nem autorizada para produção.
- Painel read-only candidato **também desativado**, `deploy/systemd/cia-j5-public-paper-owner-loopback.service.template`: o mesmo processo local J5 em 127.0.0.1:8765 exibe status residente e posições do diário, sem endpoint público. Deve **substituir**, e não competir na porta com eventual unidade J5 antiga. Não instalar sem gate.

## Evidência pública real feita na VPS (não equivale ao aplicativo instalado)

Em acesso administrativo restrito, requisições WSS públicas `wss://stream.bybit.com/v5/public/linear` tiveram HTTP 101, ACK pós-subscribe e 13 frames de `tickers.BTCUSDT`; WSS `kline.60.BTCUSDT` recebeu ACK e um frame de vela em formação, **zero closes confirmados na amostra curta**. Nenhum token, conta privada, ordem, gravação no journal, serviço instalado ou taxa adicional.

## Bloqueio real de instalação

O gateway administrativo retorna `runuser: cannot set groups: Operation not permitted` quando tenta executar como `cia-probe`. Apesar de `id -u = 0` no sandbox administrativo, ele não possui a capacidade de trocar para o UID do operador nem pode ler seu checkout privado: `PermissionError`. O Python de sistema não fornece `websockets.sync.client`; isso NÃO comprova ausência da dependência no venv owner. **Não** executar um daemon PAPER como root nem relaxar permissões J1 para contornar o gateway. A implantação real exige um método owner válido (SSH root host com capacidades de sistema, executor instalado no UID, ou broker com delegação autorizada), e release gate operacional.

## Aceite da Entrega 1

1. Após gate: instalar release de SHA exato sem tocar J1; criar um venv e diretórios PAPER próprios 0700/0600; rodar D457 como `cia-probe` com preflight PASS.
2. Executar a aplicação pública real J2/J4 em tempo limitado, registrar ACKs, candles fechados, N50 e cotações no journal, separando `confirmed:true` de frames em formação. Não aceitar apenas PING ou REST GET como integração completa.
3. Provocar reconexão/restart e verificar que posição PAPER existente continua monitorada; não duplicar FILLs, exits ou ordens.
4. J5 deve mostrar estado operacional verdadeiro, contador de sessões completas e fallback, marcando indisponível quando heartbeat expira. Status nunca comprova stop de corretora.
5. Somente após testes e aceite operacional: permitir instalar e ativar systemd de pesquisa PAPER. Não há negociações reais nem gasto novo.

## Próximo passo seguro

Completar CI Linux/Windows/mobile no SHA final; não reabrir J1. Assim que existir execução não-root efetiva na VPS, rodar trial público real com duração finita e coleta de evidências, sem transformar automaticamente em daemon. Manter PR #734 draft enquanto a integração de host não está demonstrada.
