# J1/OPS8 — Prova limitada de assinatura WebSocket linear com 52 tópicos

**Status de desenvolvimento:** ferramenta independente, somente leitura, desativada por padrão. **Questão de origem:** #429; dependência de universo #319; jornada J1 #2. **Custo extra:** R$ 0. Nenhuma ordem, credencial, REST ou escrita em SQLite.

## O que a sondagem comprova (e o que não comprova)

A Bybit V5 documenta o WebSocket público linear, a assinatura de múltiplos tópicos no mesmo pedido, um limite de 21.000 caracteres para o array `args`, heartbeat a cada 20 segundos e respostas de inscrição cujo `req_id` pode ser vazio. O tópico `kline.60` envia atualizações entre 1 e 60 segundos; `confirm=true` indica vela encerrada. Referências: https://bybit-exchange.github.io/docs/v5/ws/connect e https://bybit-exchange.github.io/docs/v5/websocket/public/kline.

O OPS8 oferece uma **única** sondagem real, opcional e curta para aferir se a Bybit aceita a inscrição agregada dos **52 nomes candidatos** do registro revisado, se chegam frames de mercado válidos e quantos tópicos distintos foram efetivamente observados. Não consulta o catálogo REST e **não presume** que os 52 nomes ainda estejam listados, que todos os tópicos foram entregues, que existe janela completa de 24 horas, que o Top50 cobre o mercado inteiro ou que o provedor está autenticado.

O resultado contém somente status categórico e contadores agregados: tópicos solicitados, ACK, frames, mercado após ACK, tópicos distintos vistos, eventos de candle fechado validados, tópicos distintos com fechamento e pongs. Não imprime símbolos, preços, volume, turnover, `req_id`, URL, tokens ou dados brutos. Nunca salva os frames. Mesmo com ACK aceito, `all_topics_delivered_verified=false` e `closed_24h_complete=false` permanecem.

## Segurança e orçamento

`crypto_intelligence_agent/bybit_ws_linear_live_probe.py` só abre um socket depois dos três opt-ins explícitos e de confirmar usuário POSIX **não-root**. A consulta ao registro local ocorre **depois** desses gates. A duração padrão é 35 segundos (máximo 90); orçamento padrão 8.192 frames (máximo 8.192); sem retry, sem backfill, sem GET e sem processo background. Só uma assinatura com todos os tópicos, req_id ausente/vazio/esperado no ACK. O frame de dados antes do ACK não é aceito como prova, e ACK duplicado, ID inesperado, tópico fora da lista, campo inválido ou dado temporal/financeiro inconsistente resultam em abstenção.

Para uma prova de fechamento é necessário atravessar um UTC boundary enquanto o socket recebe atualizações. A ausência de um `confirm=true` num teste de 35 segundos **não significa falha** da conexão, somente ausência de evidência de fechamento nessa janela.

## Invocação futura pelo proprietário, uma vez, com HEAD aprovado

O repositório mantém a CLI `python3 -m scripts.probe_bybit_ws_linear_live`. A invocação pública da CLI é:

```bash
python3 -m scripts.probe_bybit_ws_linear_live \
  --allow-public-network --allow-public-websocket \
  --confirm-region-and-personal-research \
  --seconds 45 --max-frames 8192
```

**Não executar como `root`, não instalar systemd e não misturar este probe com a coleta histórica.** Na VPS, deve ser usado o usuário não privilegiado da pesquisa e checkout no SHA aprovado da `main`. O operador deve validar primeiro a versão do Python e a presença da dependência `websockets`. A sondagem não exige nem cria diretório de dados, banco, pidfile ou configurações do sistema.

## Matriz de aceitação offline

Executar `python3 -m unittest discover -s tests -p test_j1_ws_linear_live_probe.py -v`: 52 tópicos num só request, ACK com `req_id` ausente/vazio/esperado, NACK, ACK duplicado, ID errado, frames antes do ACK, velas abertas/fechadas estritas, tópico desconhecido, frames malformados, pings/pongs, falha de socket, timeout, limites, opt-in negativo e usuário root. Prova de que testes offline não criam socket real nem fazem GET. CI Linux/docs, Windows/offline e Chrome/PAPER, revisão SHA e CI pós-merge são gates de engenharia; **não** equivalem a sucesso live.

## Próxima etapa operacional da #429

Após a CI no SHA exato e um resultado real sanitizado dessa sondagem: decidir se o socket/handshake de 52 tópicos foi aceito, corrigir o comportamento específico observado, executar um piloto finito owner-only de candles confirmados em diretório **novo e separado**, e só então discutir a instalação/ativação de supervisão `systemd` com teste de 24h. Se o resultado for bloqueio regional, erro de rede ou indisponibilidade, não criar retries nem improvisar PIT. O principal trabalho J1 #319 ainda requer cobertura independente de todos os perpétuos elegíveis.

## OPS14 — correção de truncamento da prova de 52 tópicos (02/11/2026)

Com 52 tópicos e até 90s, o antigo teto de 512/1.024 frames era insuficiente para a cadência máxima documentada de cerca de um frame por tópico por segundo. O orçamento passa a 8.192 frames, limitado a uma única sessão de no máximo 90s, sem gravação, GET, retry, ordens, credenciais ou serviço de fundo. Esgotamento de frames antes do deadline agora retorna `ws_frame_budget_exhausted_abstain` com categoria `frame_budget`, nunca `ws_ack_with_market_frames_unverified` como se a observação houvesse terminado normalmente. O default da CLI acompanha o teto. Testes de saturação e orçamento de 52×90 foram adicionados. A prova operacional real continua pendente de executor owner-only na VPS; CI não a substitui.

## OPS15 — prova pública descartável via GitHub Actions (owner-only)

Quando SSH da VPS não está disponível, o workflow
`.github/workflows/j1-ops8-ws52-one-shot.yml` permite uma **única sessão por
comentário exato**, exclusivamente em issue #429 por usuário proprietário e
`github.actor` correspondentes. Só o comentário literal
`/probe-j1-ws52-github-once-v1` dispara o job. Nenhum push, PR, cron,
`workflow_dispatch`, segredo ou token privado dispara a sondagem. O runner é
descartável, o checkout não persiste credenciais, o único pacote adicional
é `websockets==15.0.1`, a sessão é de 45 segundos com até 8192 frames,
no máximo três minutos por job, e apenas JSON sanitizado segue aos logs.
Não há artefatos de frames, banco, REST GET, execução de ordens ou deploy.

O teste comprova o **caminho do runner GitHub**, que pode ter rota, IP e
bloqueios distintos da VPS. ACK aceito não prova existência/entrega dos
52 contratos, fluxo 24h, Top50 marketwide, credenciais de corretora ou serviço
ativo na VPS. Um erro de transporte no runner também não prova falha na VPS.
Qualquer resultado real deve ser interpretado com esse escopo e registrado
sem inventar conclusões. Os nomes do registro revisado em 29/10/2026
expiram para essa sonda em 05/11/2026 15:27:39 UTC; não estender validade sem
nova revisão causal versionada. O job NÃO é uma ativação da coleta e
não altera as exigências do piloto finito/soak owner-only na VPS.


## Evidência executada — runner GitHub, 02/11/2026

A execução explícita **real** do workflow owner-only [#41492753422](https://github.com/leandrosilveiradepaula/crypto-intelligence-agent/actions/runs/41492753422) no SHA `ed1f3235445741e82a82b68e7cb3f43aec5e0797` concluiu SUCCESS: `topics_requested=52`, `subscription_acks=1`, `frames_received=1069`, `pre_ack_market_frames=52`, `valid_market_frames=1014`, `distinct_topics_seen=52`, `validated_closed_events=0`, `distinct_closed_topics=0`, `failure_category=null`. Flags de dados armazenados, HTTP GET, ordens, autenticação de origem, liberação marketwide e cobertura 24h permanecem false. Os 52 tópicos revisados transmitiram frames válidos **na rede do GitHub** durante 45s; nenhuma vela fechada foi observada na janela, o que não significa falha do socket. Isso **não é homologação da VPS** nem prova de lista Top50 por volume. Registro de 52 bases continua sujeito ao vencimento PIT de 05/11/2026 15:27:39 UTC. Repetir a mesma sondagem de protocolo não é requisito de aceite; próximo teste necessário é closed candle e soak owner-only na VPS, sob gate.


## OPS16 — prova isolada de fechamento UTC sem novo coletor

Para interpretar o `validated_closed_events=0` do teste público 41492753422 (45s fora de fechamento), o workflow `.github/workflows/j1-ops16-ws-closed-once.yml` aceita apenas o comentário literal `/probe-j1-ws52-closed-once-v1` na issue #429, escrito pelo proprietário. Um planejamento determinístico tenta a **próxima hora UTC**, inicia 30s antes, descarta a execução se o runner estiver a mais de 20min da janela ou acordar fora de 5s de tolerância. Realiza no máximo um WebSocket de 90s e 8192 frames; reporta apenas contagens válidas e fechamentos. Se não observar `confirm=true`, registrar ausência de evidência e não forçar retry; podem existir atrasos/correções posteriores. Sem GET, SQLite, credenciais, ordens, serviço, produção, artefatos ou custo adicional. O teste verifica a rede do runner GitHub, **não** a VPS, nem completude 24h, ranking Top50 ou autenticidade da origem. Requer CI/revisão/merge no SHA exato antes do comando. Não executar se validade PIT do registro 52 tiver expirado.


## OPS16 — resultado real de fechamento UTC e OPS17

O workflow GitHub owner-only [#41505630514](https://github.com/leandrosilveiradepaula/crypto-intelligence-agent/actions/runs/41505630514) iniciou exatamente 2026-11-02 **18:59:30 UTC**, cruzou o fechamento e abortou com erro de validação às **19:00:00.429 UTC**: 52 tópicos candidatos, ACK=1, 448 frames, 393 válidos pós-ACK, 52 distintos, **0** eventos confirm=true validados e falha `ws_frame_invalid_abstain`/`validate`. Isso não é prova de candle fechado, e o comportamento não foi atribuído ainda a um campo específico. A OPS17 adiciona classificação **sanitizada** por allowlist para erro de grid, último timestamp, relógio servidor/local, OHLC ou confirmação, sem expor dados de mercado e sem relaxar o contrato. Uma nova prova requer resultado de CI e gate finito separado; nenhuma ordem real ou VPS foi acessada.


## OPS18 — quarentena diagnóstica de timestamps na virada UTC

Duas provas reais UTC (runs #41505630514 e #41514590636) rejeitaram frame no instante do fechamento; a segunda identificou `failure_category=clock_trade_stamp`. O código exige que o `timestamp` da última negociação permaneça entre `start` e `end`, mas os logs seguros não registram o valor, a direção da violação nem `confirm`. Não extrapolar origem do erro. A sonda passa a identificar em classes fixas (`clock_trade_stamp_before_open`, `clock_trade_stamp_after_open`, `clock_trade_stamp_before_closed`, `clock_trade_stamp_after_closed`) sem revelar preço, símbolo, horário exato ou payload. Modo normal continua fail-closed na primeira rejeição. **Somente** a flag `--diagnose-trade-stamps`, opt-in pela mensagem literal `/probe-j1-ws52-stamp-diagnostic-once-v1` na issue #429, pode contabilizar o frame inválido como quarentena, descartar todo o frame e observar os seguintes até o deadline de 90s; não aprova closes rejeitados e devolve status `ws_timestamp_diagnostic_unverified`. O runner continua descartável; nenhuma persistência, GET, credencial, VPS, ordem ou serviço. Falhas fora de `ws_clock_trade_stamp_invalid` continuam interrompendo o teste. A ingestão real não ganha tolerância. Revisar/validar CI e merge antes de cogitar outra execução. Esse modo não fornece Top50 marketwide, validação de 24h nem prova VPS.


## OPS19 — validade completa do diagnóstico por frame

A OPS18 acrescentou a quarentena de trade stamp apenas à sonda, mas um `break` após o primeiro row inválido poderia mascarar uma segunda falha presente na mesma mensagem. A OPS19 exige que a revalidação das demais condições de cada row continue (OHLC, decimais, `confirm`, relógios, tipagem), mesmo quando timestamp viola o intervalo. O frame inteiro somente entra em quarentena depois de todas as linhas examinadas; quaisquer outras falhas produzem abstenção, sem aprovação, dados persistidos ou payload emitido. A opção de suprimir um único predicado é **somente diagnóstico**, desabilitada por padrão e nunca usada pelo coletor, parser SQLite ou cálculo financeiro. Testes específicos cobrem corrupção após primeira linha e corrupção simultânea no próprio row. A execução previamente iniciada #41521829843 usa o SHA anterior; não pressupor que esses checks foram aplicados a ela.


## OPS20 — faixas anônimas de excedente temporal no rollover

Após OPS18 `41521829843` observar 52 eventos confirmados e 2 abertos com `timestamp>end`, a classe direcional é insuficiente para permitir qualquer tolerância: excesso pode ser 1ms ou muito maior. OPS20 acrescenta à prova `--diagnose-trade-stamps` faixas **agregadas** `1ms`, `2_to_1000ms`, `1001_to_5000ms`, `over_5000ms` por open/closed, contabilizadas **por frame** e somente após as demais validações se manterem íntegras. Nenhum timestamp exato ou dado financeiro é registrado, nenhum frame em quarentena é validado ou persistido e o parser/ingestor offline permanecem restritivos. Sem inferir que o comportamento da Bybit é garantido ou compatível com a especificação. Próximo experimento, se necessário, único e owner-only após CI e revisão SHA.
