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


## D458 — prova operacional real sem instalação permanente (21/11/2026)

O caminho correto de execução owner é `systemd-run --uid=cia-probe` (root sandbox sem CAP_SETUID não pode executar `runuser`, mas o PID1/systemd pode iniciar transiente como UID999). O ambiente isolado privado D458 foi preparado e a política de PAPER 50x/margem USDT5 carregada sem alterar J1. O preflight D457 passou em todos os itens. Os flows REST N50, kline público e ticker público foram executados em leases reais, com 3.390 ticks pós-ACK no teste de 18s e duas leases subsequentes completas com recuperação de journal. Ainda não há candle horário confirmado nessas janelas curtas; o operador não negociou nem completou 24h de warmup. Job finito auditável `093979aec3ad464b9143c3c95d9d7cc4` está `running` na consulta inicial, planejado para atravessar um fechamento, limitado 3480 segundos e recursos de host. Status futuro deve ser verificado por job ID antes de afirmar êxito. O servidor J5 local anterior responde em 127.0.0.1:8765 e ainda não tem endpoint `/api/resident-paper-status`, não houve troca/restart da versão em produção. Gate de release permanente separado e pendente.


## D459 — falha horária confirmada e correção de fallback

O job D458 de 3480s terminou sem candle confirmado, a primária não completou e a contingência terminou `degraded_no_held_coverage`. **O código** mostrava a falha inequívoca: fallback D453 exige <=180s, recebeu o budget da primária 3480s. D459 dá orçamento separado de até 180s ao fallback e grava relatório privado sanitizado `paper-last-public-lease-d459.json` com categorias kline/ticker e quantidades, mesmo quando a primária retorna degradada; não grava exceções nem payloads. Sem instalar como serviço, este conserto não altera o stage do trial concluído. Falta identificar se falha primária foi WebSocket, validação da vela, tempo ou outro; não repetir espera horária sem observabilidade.\n

## D464/D466 — teste REAL do fechamento horário e reparo focado (21/11/2026)

D464, execução pública owner-only 1608s, demonstrou histórico REST 50×24, WebSocket ticker 305.877 frames e 1 fechamento persistido XRPUSDT exatamente às 13h BRT, mas **kline terminou fail-closed após um append e antes do primeiro callback PAPER** (1 registrado, 0 callbacks). A primeira causa observável do código é o contrato inconsistente entre o ingester batch (permite 1 confirmado acompanhado de uma vela aberta) e o callback D450 (exigia `len(data)==1`). Reparado em D466: extrai exatamente 1 `confirm:true` da mensagem previamente validada e anexada, nunca move a aberta nem afrouxa o journal; regressão integrada com 50 membros na VPS aprovada, 9 tests no total. O payload bruto do momento não foi salvo; portanto é uma correção do defeito capaz de reproduzir o padrão, ainda pendente de prova com o feed ao vivo. Job finito D466 `f39fd7e3d2184468802d0e2d76bb695d` com SHA pinado `26bfdb33d2f34fb683e8f98d9626616598f6cb36` está em execução inicial, isolado, sem ordens e sem systemd permanente, observando o fechamento horário seguinte. Não instalar como produção sem gate.
