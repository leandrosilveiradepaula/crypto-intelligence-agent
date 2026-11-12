# J1/D320 — instalação owner one-shot do N50 WebSocket, com retorno ao N2

Escopo: #585 (WS-first), #429 (coleta contínua), #319 (elegibilidade independente). O PO autorizou a **instalação do serviço WS N50 na VPS existente**. Esta entrega transforma os templates D318 em um processo único, fechado e auditável, com bootstrap de dados D287/D314 e troca reversível N2 → N50 WS. Sem ordens reais e sem custos adicionais.

## Constatação de acesso remoto (fatos)

A conexão atualmente disponível via MCP `Agente_Financeiro_VPS.vps_exec` executa como `uid=0(root),gid=985(agente-mcp)`, **mas não possui capacidades de DAC nem permissão para implantar systemd**:

- `test -w /etc/systemd/system`: exit 1.
- `test -x /home/cia-probe/agent`: exit 1.
- `runuser -u cia-probe -- id`: exit 1, `cannot set groups: Operation not permitted`.
- `systemctl show cia-j1-n50-ws.timer`: `LoadState=not-found`.
- Sistema operacional sincronizado via NTP e componentes antigos auditados somente em leitura.

Isto é **bloqueio efetivo do canal MCP**, não uma decisão de produto ou necessidade de mais testes financeiros. Nunca contornar os limites de permissões do broker com `systemd-run` privilegiado ou outro mecanismo lateral. O operador root na sessão SSH usual tem os direitos necessários, conforme execuções anteriores.

## Processo de instalação em apenas uma execução privilegiada

`deploy/vps/prepare_install_j1_n50_ws_d320_once.sh SHA40`:

1. Confirma root e hostname `srv1319424`, NTP sincronizado, N2 habilitado, N50 REST antigo disabled/inactive, SHA exato, Python owner existente; prepara **novo checkout do GitHub** privado 0700 como `cia-probe`, faz fetch e checkout do SHA exato, sem editar o diretório antigo `/home/cia-probe/agent/j1-n50-d306-main-code`.
2. Cria diretórios owner 0700 de **manifesto** e **journal/cache WS**, separados da epoch HALT REST. Espera apenas a janela horária causal de `HH:02:15..HH:02:30 UTC` (após o N2 das HH:02), verifica serviço N2 parado e roda o censo D287 completo para os top 50 perpétuos da hora. É uma coleta limitada por `timeout`, sem retry se houver `10006`; qualquer falha mantém N2 ativo e NÃO instala WS.
3. Com manifesto recém-selado, chama captura D314 de metadados de contratos com cursores e 1–4 GETs públicos, cache privado D316 imutável 0600. Rejeita drift de coorte, dado vencido, 10006 ou permissão inválida. Nenhuma vela REST do N50 HALT é tocada.
4. Somente após ambos PASS, `scripts.release_j1_n50_ws_owner_once` executa **preflight root sem alterações**: SHA e origin do checkout limpo, dono/mode 0700, revalidação owner do manifesto D287 e cache D316 50/50, NTP, hash exato de cinco units anteriores observado na VPS, N2 timer active/enabled e service inactive, REST N50 timer inactive/disabled e WS timer ausente.
5. Exige `--confirm-n50-ws-cutover --allow-systemd-modifications` no módulo de release. Cria **somente três units novos** (timer, service e fallback WS), `daemon-reload`, verifica os loads, desabilita reversivelmente N2, habilita WS timer. O `ExecStart` WS começará a `HH:59:30 UTC` e chamará D317 para o próximo fechamento, com dados/sockets protegidos e sem ordens.
6. Se houver falha depois do início do isolamento N2, rollback chama `systemctl disable --now cia-j1-n50-ws.timer` e `systemctl enable --now cia-j1-rest-hourly.timer`; não modifica as três units antigas REST nem apaga histórico. O serviço WS tem `OnFailure` próprio com o mesmo fallback.

O instalador não executa negociações e não altera `cia-j1-n50-managed.timer`, `cia-j1-n50-managed.service` ou o SQLite HALT (auditoria owner anterior: 1.203 candles, 1 PIT e 3 parciais salvos). Cada execução cria epoch nova; não reutilizar diretório parcial se quota ou rede falharem.

## Conferência e gates

O módulo Python `scripts.release_j1_n50_ws_owner_once` tem `preflight_pass_no_changes` por padrão, requer dois opt-ins para instalar e retorna relatório sanitizado de ativação/rollback sem tickers, paths nem segredos. `tests/test_j1_n50_ws_release_d320.py` cobre sem opt-in, preflight bloqueado, só três units novos, ordem do cutover, N2 restaurado mesmo com `systemctl disable` parcialmente falhado, caminhos e SHA inválidos, sem ordens.

CI Linux/docs, Windows/offline, Chrome/PAPER e review do SHA final exigidos antes de publicar o comando operacional pinado ao commit + checksum. **O merge ou CI não instala por si só na VPS**, e a conexão MCP não pode fazer a etapa privilegiada. Um único disparo root fora da sandbox executa as etapas sem pedir um `prossiga` por subetapa, se o provedor permitir os GETs de inicialização.

## Limites que permanecem após a instalação

- O primeiro resultado 50/50 WS real ocorre no fechamento seguinte ao bootstrap; 49/50 gera falha e retorna ao N2. Não declarar sucesso até verificar journal owner e `systemctl`.
- D316/D287 expiram em 48h. **A rotação automática depois de >=36h ainda não está implementada** e precisa de futura unidade de renovação de epoch; até lá o fail-close e fallback evitam tratar dados vencidos como atuais.
- Reconciliação REST estritamente de lacunas e prova de 24 PITs fechados reais e rotação 36h continuam abertas; não bloquear o piloto WS somente por #319, mas não declarar Top50 marketwide certificado por mera convenção USDT.

Custo adicional: R$0. Nenhuma ordem real.
