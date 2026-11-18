# J5/D422 — leitura automática da saúde pública do N50, sem importação manual

## Objetivo concreto

A J1 coleta velas fechadas na VPS. D418/D421 já comprovaram em duas
sessões reais, cada uma com N50 owner revalidado, a recepção pública de
cotações Bybit e a publicação de um **único arquivo privado** de
saúde agregada: `latest-n50-public-health.json`. Até D421, o painel J5
precisava que o usuário importasse esse arquivo manualmente.

D422 liga o **servidor local de leitura existente** ao mesmo painel,
sem adicionar um segundo coletor ou uma nova fonte de ranking.

## Caminho de dados

`D418 (WebSocket público Bybit, owner N50 J1)` →
`D421 (amostra finita validada, arquivo 0600)` →
`D422 (GET loopback mesmo proprietário)` →
`J5/paper-ws-health.js (atualiza a cada 30 segundos)`.

O servidor `scripts/serve_j5_local_readonly.py` oferece
`GET /api/n50-public-health` somente quando iniciado com
`--allow-loopback-readonly-http --allow-private-health-loopback
--private-health-directory <diretório-proprietário>`.
As duas opções de saúde são independentes de acesso REST ou de consulta
de research. O diretório **precisa existir previamente**, ser absoluto,
não ser link simbólico, pertencer ao usuário não root do servidor e
ter modo `0700`; a amostra precisa ser arquivo normal único `0600`,
também do mesmo proprietário, aberto via `dir_fd` e `O_NOFOLLOW`.
Nenhuma opção padrão habilita esse endpoint.

O leitor valida o contrato D421 integralmente: chaves exatas, números,
partição 50–100, ACK, ping/pong, timestamp da amostra, flags de nenhuma
ordem/sinal/trading, e modo `real_public_websocket`. Uma amostra deve
ter sido escrita no máximo **180 segundos** antes, sem relógio ou mtime
inconsistente. Falha, symlink, arquivo parcial, privacidade incorreta,
`source_unavailable` ou amostra antiga retornam **HTTP 503**, sem dado
anterior nem detalhes de erros privados.

O navegador só consulta automaticamente
`http://127.0.0.1:8765` ou `http://localhost:8765` e envia
`GET /api/n50-public-health` com `credentials: omit`,
`cache: no-store`, `redirect: error`; nunca chama Bybit, não abre
WebSocket, não persiste preço, conta, saldo ou ordens. O JavaScript
revalida o mesmo contrato e idade, atualiza a cada 30 segundos e **apaga
o último estado automático** quando fonte ou contrato falha. Uma
importação manual continua tendo prioridade até o reload da página.

## Limites importantes

A API é **LOOPBACK-ONLY** e não pode ser alcançada pelo celular por
outra rede sem um canal de acesso remoto apropriado. Não instalar
proxy, domínio, exposição pública, token improvisado ou acesso remoto
sem gate específico de autenticação/release. O ZIP offline local
permanece desconectado; não solicitar ao Product Owner que importe
relatórios para operar o sistema.

O arquivo é um **resumo de amostra finita**, não um ticker atual.
Mesmo quando 50/50 estavam frescos no encerramento, o relatório
envelhece e **não autoriza entradas**. Não avalia stops PAPER, posição,
marcação de resultado ou execução real. J1 continua com seu único
escritor, e D421 não é instalado como serviço por esta mudança.

## Evidências de qualidade

`tests/test_j5_local_public_health_d422.py`: código nativo Python e
HTTP local, permissões, symlink, byte budget, Host/Origin, relógio,
contagens hostis, flags, mock de falha e preservação da importação
manual no navegador. D417/D412/D421 e testes legados do servidor
local são regressões. CI Linux/Windows/Chrome deve ficar verde no SHA
final; somente então merge sem produção. Após merge, piloto
**temporário** com usuário owner, amostra real D421 e HTTP 127.0.0.1
é elegível sem alterar systemd. O próximo bloco de produto é
acesso mobile autenticado e supervisão PAPER, com release gate próprio.

Custo adicional R$ 0,00.
