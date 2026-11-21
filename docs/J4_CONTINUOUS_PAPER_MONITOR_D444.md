# D444 — monitor contínuo de posições PAPER BTCUSDT (sem J1)

**Produto entregue no código:** o monitor passa a acompanhar todas as posições PAPER persistidas em ciclos sucessivos, reaproveitando D443/D425/D390/AUTO4. Entre uma sessão de ticker e a próxima, refaz REST de BTCUSDT, roteamento de cotação e reconciliação de reservas; erro transitório causa nova tentativa com backoff 2, 4, 8 ... até 60 segundos. Não cria posição, não executa fill ou ordem e não recria a J1.

## Comportamento

- Processo do owner POSIX não-root, iniciado explicitamente. `--max-cycles 0` mantém o loop ativo até sinal de parada; `--max-cycles N` permite uma execução finita. O orçamento por conexão é 45 segundos e a falha contínua encerra após 8 tentativas, com código de falha e estado terminal.
- Cada ciclo chama D443; D443 relê os PAPER routes do owner e obtém lock do journal, sem escrever em estado J1. O stop e as parciais que já foram reservados continuam no SQLite após reconnect/restart. Nenhum evento ticker vira fill confirmado.
- Entre ciclos não há conexão ou stop nativo. O estado `lease_started` não prova que o ticker está fresco. O arquivo de status persistido tem apenas contagens, atualização UTC, último lease saudável e flags negativas para fonte autenticada, stop nativo, preenchimento automático, ordens e continuidade ininterrupta.
- O diretorio de status 0700 deve ser separado do diretório PAPER 0700. Um lock owner exclusivo evita dois processos D444 sobre a mesma pasta de status. A escrita é atômica, 0600, com `fsync`, sem IDs de posição, símbolos, preços, credenciais ou PnL.
- Para rodar em modo público é necessário opt-in para rede pública, WS, pesquisa pessoal, elegibilidade regional, direitos de dados, reservas no diário PAPER e ativação do loop. Não presumir elegibilidade nem operar em produção enquanto o gate de release não estiver aprovado.

## Exemplo de comando de operador — NÃO executar automaticamente

```bash
python -m scripts.run_j4_continuous_paper_d444 \
  --private-paper-directory /OWNER/PAPER_PRIVADO \
  --status-directory /OWNER/STATUS_PRIVADO \
  --max-cycles 3 --lease-seconds 45 \
  --allow-public-network --allow-public-websocket \
  --confirm-personal-readonly-research --confirm-region-eligible \
  --confirm-public-data-rights --allow-private-paper-reservations \
  --enable-continuous-worker
```

Usar `--max-cycles 0` requer decisão operacional para rodar continuamente; nenhum serviço/systemd ou timer da VPS é instalado nesta entrega.

## Limites e próximos marcos

Implementado somente o ciclo contínuo de **até 50 posições PAPER USDT já persistidas**, não o universo completo N50, nem as posições fora desse universo. Lacunas para produto: agente que incorpora todos contratos admitidos, monitor compartilhado de posições abertas, J2 gerador de entrada validado, J3 realisticamente custeado por mark/funding/liquidação/OOS, e console móvel com estado do worker (sem renderizar como protegido quando está desconectado).

Testes de aceitação incluem recuperação automática de falha, preservação de contagens e reservas, teto de falhas, interrupção, status atômico e flags explícitas. Mesmo com CI verde, não afirmar execução WSS real ou cobertura 24×7 sem operar o processo continuamente em VPS e medir lacunas.

Estado de produto: componente de execução contínua preparado em código, não implantado; nenhum custo adicional ou ordem real autorizada.

## Status visível no console local J5

O console local recebe, sob autorização independente `--allow-paper-worker-loopback --paper-worker-directory`, somente o arquivo owner 0600 `paper-monitor-state.json` com contagens e fases. Endpoint `/api/paper-worker` é GET-only e loopback. `lease_started` é **tentativa de sessão**, não prova de stop ativo, e fases antigas perdem validade; estado terminal fica disponível por até 24 horas. O painel mobile diferencia reconexão, sessão iniciada, falha e parada. O navegador nunca recebe símbolos, posições, preços ou ordens.

## D445 — todas as posições existentes

Em D445, cada ciclo do worker D444 relê as rotas AUTO4 existentes e assina todos os contratos USDT ainda detidos, mesmo que tenham saído do N50. O scan REST paginado é uma validação estrutural de contrato de posição existente e não uma nova admissão J2 nem um feed N50. As reservas continuam no journal já existente, e os outros contratos não são desligados porque faltou uma quote em um contrato diferente. Uma sessão é classificada como degradada se todos os contratos detidos não estiverem frescos ao terminar.
