# J1/OPS4 — Piloto WebSocket owner-only com catálogo limitado, escopo privado e estado de saúde

## Problema e decisão

Na VPS, a retomada EXIT5 foi interrompida em `retCode=10006` depois de 168 GETs na etapa de captura repetitiva do ranking de 24h, preservando **37.470 candles**, **2 PIT imutáveis**, **51 ativos históricos** e **50 no último PIT**; a auditoria read-only terminou com código zero e replay/SQLite íntegros. O terceiro PIT e o Top 50 de todo o mercado **não** foram comprovados. Não repetir backfill de 720h nem o procedimento que atingiu o limite REST.

A OPS2 criou cálculo local causal do ranking a partir de candles WebSocket `confirm=true`. A OPS3 criou um controlador WebSocket com sessões injetadas, múltiplas assinaturas, ACK correlacionado, ping/pong, reconexão limitada e lock exclusivo. **OPS4 prepara um piloto finito que já pode utilizar os transportes públicos existentes em um ambiente POSIX do titular, mas não é instalado, não é ativado, não envia ordens e não substitui a coleta histórica existente.**

## Contrato operacional

- Entrada: diretório **já existente e privado 0700** de titular POSIX, sem symlink. Código só atua após os quatro opt-ins explícitos `--allow-public-network`, `--allow-public-websocket`, `--allow-private-storage`, `--confirm-region-and-personal-research`. A ausência de qualquer um recusa **antes** de abrir SQLite, socket ou GET.
- Banco novo e separado `ws-confirmed.sqlite`: criação exclusiva, nunca abrir/escrever a SQLite REST do EXIT5. `exclusive_owner_ws_writer` segura `flock` durante leitura, ingestão e auditoria; não remove lockfile.
- No **primeiro** lease: até **4 GETs de `instruments-info`** com paginação, cursor validado e tempos por página. É a lista ampla de contratos; **não** faz 52 GETs de `closed_kline_24h`, nem chama ticker rolling. `scan_bybit_linear_instruments_offline` e `OfflineReviewedStreamScope.from_scan` exigem ao menos 50 contratos revisados elegíveis no registro `expanded-52` e dados contemporâneos. Em `10006`, recusa sem retry e sem iniciar WebSocket.
- Escopo de 50 a 52 contratos aceitos é salvo **uma única vez**, como `ws-reviewed-scope.json` 0600 em diretório 0700, com digest de integridade (não é assinatura de autenticidade). O próximo lease usa esse escopo sem novo GET. Alteração do registro, dados inválidos, arquivo adulterado/permissão insegura ou idade superior a 48h **bloqueiam** nova aquisição; não se promove uma mudança de universo sem reconciliação explícita de epochs/PIT.
- O lease WebSocket usa o controlador OPS3 com duração configurável (máximo 3.600s), até três tentativas/4096 frames por padrão, sem retry de dados inválidos ou lacunas. O único modo real de rede é o adaptador **público e sem credenciais** já existente, importado depois dos gates. A identificação da origem continua marcada não autenticada no modelo; nenhum trade/testnet.
- Depois do lease, `journal.audit` calcula as últimas **24 velas 1h fechadas** para todo o escopo. Se um dos candidatos faltar ou houver falha de assinatura/desconexão não recuperada, o status é `warming_up_abstain` ou `degraded_abstain`, **nunca** ranking parcial. Não atribuir PIT retroativo às horas perdidas. O journal WS não é disfarçado de página REST.
- Estado de saúde privado `ws-pilot-health.json`, atualizado por `os.replace` com arquivo temporário 0600: somente contadores/estado de última observação e horário UTC avaliado; `worker_running_verified=false`. Sem símbolos, preços, caminhos, payloads, tokens ou URLs. **Não é um serviço 24/7 e não prova execução atual.**

## Invocação futura em homologação owner-only (não executar até gate operacional)

O comando fica versionado no repositório para posterior homologação, **sem instalação ou execução automática em produção**:

```bash
python3 -m scripts.probe_bybit_ws_owner_pilot \
  --directory /CAMINHO/PRIVADO/WS-JOURNAL-SEPARADO \
  --allow-public-network --allow-public-websocket \
  --allow-private-storage --confirm-region-and-personal-research \
  --seconds 180
```

O diretório deve existir previamente com modo 0700 e pertencer a quem executa. A opção `--seconds` não ultrapassa 3600. Primeiro lease pode não cruzar fechamento da hora e, mesmo cruzando, **não terá 24h de janela WS após instalação**: sem warm-start causal verificado, abster durante o aquecimento em vez de inventar histórico. Esta implementação não deve ser acionada sobre a pasta do banco REST EXIT5 nem contra um serviço em produção.

## Matriz de aceitação

`python3 -m unittest discover -s tests -p test_j1_ws_owner_pilot.py -v` testa: opt-in negativo com zero I/O; catálogo de 52 candidatas em duas páginas; GET cap de 4, cursor duplicado, menos de 50 candidatas, 10006 sem retry; persistência owner 0700/0600; segundo lease sem GET; exclusão de diretórios/arquivos inseguros; escopo expirado; lock e journal separados; relatório de saúde sanitizado sem falsa prova de processo ativo. Integra-se às suítes pré-existentes de OPS2/OPS3 com verificação de ACK, vela confirmada, gap, replay idempotente e sincronismo UTC. CI Linux, Windows/offline e Chrome/PAPER no SHA final e pós-merge.

## Próximas partes da issue #429 — ainda NÃO concluídas

1. **Homologação owner-only real** de catálogo paginado + WS multilote na região do titular, especialmente se ACK da Bybit ecoa `req_id` em todas as assinaturas; documentar o comportamento observado sem divulgar símbolos ou credenciais.
2. **Warm-start causal com proveniência distinta** dos 37.470 candles REST anteriores ou aquecimento WS de 24h, sem misturar os dois bancos nem falsificar PIT; suporte versionado a refresh de escopo/epochs antes de vencer 48h.
3. Reconciliador REST apenas de lacunas pequenas dentro de orçamento de GET/tempo, **fail-stop em 10006**, sem tentativa de reconstruir 720h nem reescrever a SQLite REST.
4. Serviço POSIX/systemd **supervisionado**, com heartbeat, interrupção limpa, renovação de universo sob gate e painel de saúde PT-BR para celular. A ativação na VPS continua sujeita a aprovação operacional e não deve ser presumida por CI verde.
5. J1 #319: validar universo de **todos os contratos crypto-only elegíveis**, além das 52 bases revisadas; dados sintéticos e um ranking da amostra não são prova dos Top 50 do mercado nem de rentabilidade.

Custo adicional R$ 0,00, nenhuma ordem real, nenhuma migração/destruição ou acesso sensível novo nesta PR.