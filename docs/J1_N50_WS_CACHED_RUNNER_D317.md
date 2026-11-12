# J1/D317 — janela WS N50 a partir de manifesto e cache owner

## Objetivo / integração existente

D315 aceita em memória `DynamicN50WSAdmission`, `ranked_scope` e journal
WS para uma lease isolada de 50 perpétuos; D316 guarda o recibo D287+D314
e o reabre em horas seguintes sem repetir GET de metadados. D317 liga essas
duas unidades ao leitor de manifesto já existente e a um caminho WS privado.

`crypto_intelligence_agent.j1_n50_ws_cached_runner.run_cached_n50_ws_owner_window`:

1. Exige quatro capacidades de owner opt-in, POSIX não-root, diretórios
   distintos 0700, session factory injetada (não faz conexão real), clock
   verificado, e início entre 10 e 60 segundos **antes** do próximo
   fechamento UTC. Nunca usa o diretório fixo REST HALT N50 como saída.
2. Lê `load_private_ranked_scope` D287 no diretório de manifesto **existente**;
   reabre `load_n50_ws_dynamic_admission` D316, valida digest idêntico da
   coorte atual, TTL 48h, hash e replay integral de páginas D314.
3. Usa somente `ws-confirmed.sqlite` em diretório de saída WS separado.
   Arquivo existente precisa DAC owner 0600; arquivo ausente só pode ser
   criado por `allow_create_ws_journal=True`, via
   `SQLiteOfflineClosedStreamJournal.create` exclusivo, nunca sobrescrita.
   Não cria nem altera o SQLite REST, não mexe no HALT `epoch-1794492000000`.
4. Passa ao D315 a coorte única, journal, budget fechado, socket **injetado**,
   clock UTC real ou injetado e opções. D315 adquire flock de escritor antes
   de criar sessão, assina 50 tópicos com ACK e valida os candles
   `confirm=true`. A auditoria D313 só retorna hash da hora quando 50/50;
   se 49/50, mantém as linhas válidas e recomenda reconciliar lacuna,
   **não faz nenhum GET nem publica PIT REST**.
5. Relatório final de status, contagens, hash, horas UTC e flags fixas;
   `source_provenance=bybit_public_ws_confirmed` apenas quando houve
   comprovação local completa. Nenhuma lista de tickers, preços, payload,
   URLs, credenciais, ordens ou exceções impressas.

## Segurança e escopo

A biblioteca **não contém conector real**: `session_factory` é requisito
obrigatório e deve ser fornecido pelo executor após seu gate. Um CLI separado
`scripts.run_j1_n50_ws_owner_cached_once` apenas injeta a factory pública
`_real_session_factory` já existente, e somente se cinco flags explícitas
de owner, armazenamento privado, WebSocket público e pesquisa regional forem
fornecidas simultaneamente com usuário POSIX não-root; por padrão retorna
`owner_optin_required`, sem abrir rede/SQLite. Não instala
systemd, agenda, roda continuamente, faz REST de gap, aceita credenciais
ou envia ordens. Pode criar exclusivamente um novo SQLite WS privado se
receber opt-in específico. Não misturar a prova WS com `bybit_rest_closed_kline`
do banco HALT. `marketwide_top50_verified=false` mesmo em 50/50 porque
#319 (crypto-only independente) permanece em aberto.

## Testes / critérios de aceite

`tests/test_j1_n50_ws_cached_runner_d317.py` usa D287+cache D316 em
arquivos reais 0700/0600 e sessão fictícia sem rede: janela 50/50
comprovada, 49/50 e open update sem PIT, clocks fora de janela,
permissões e opt-ins, manifesto/cached metadata divergentes,
tamper do cache, journal ausente ou inseguro, proibição de usar
caminho HALT e ausência de GET/serviço/ordens. A suíte
`tests/test_j1_n50_ws_owner_cli_d317.py` bloqueia default/permissões
incompletas/root, e verifica a injeção do conector público sem realmente
conectá-lo. Linux/docs,
Windows/offline (POSIX-only skipped) e Chrome/PAPER no SHA final.

## Gates até N50 em funcionamento real

A interface owner de **rede pública está implementada em código somente**,
mas não foi executada na VPS nem validada contra o provedor nesta PR. Falta
gate operacional de rede e uma unidade de serviço/observabilidade com início antes do fechamento
e failback testado, a reconciliação REST sob quota e proveniência própria,
a renovação de coorte >=36h preservando digests de epochs e a certificação
de identidade crypto-only #319. Separar root release operacional: N2 ativo
e N50 REST HALT OFF até esse gate. Não declarar 24h verificadas nem
estratégia validada.

Custo adicional R$0; ordens reais zero.

## Captura inicial de metadados e ligação com o cache (ampliação D317)

O piloto D314 possuía um “GET owner” com até quatro páginas V5, mas retornava apenas um escopo tipado em memória; o gravador D316 exigia o recibo com páginas/cursores/timestamps originais. O D317 preserva esses três campos **somente em memória privada com `repr=False`** no sucesso de `DynamicN50WSMetadataCapture` e não modifica `sanitized_report()`. Falhas, inclusive quota `10006`, não transportam páginas.

A nova função `cache_current_n50_ws_metadata_once` (`j1_n50_ws_metadata_bootstrap.py`) compõe a leitura segura do manifesto D287 já selado, o cliente público D314 e o gravador D316 em UMA janela causal de até 15 minutos após observação do catálogo. Antes de qualquer GET exige dono POSIX não-root, diretórios distintos 0700, cinco flags de opt-in, cache ainda inexistente e lease exclusiva `flock` owner 0600. Metadados de TradFi, falhas de paginação, cache existente, vencimento do escopo e bloqueio de lock abortam; `10006` faz um único GET, sem retry, sem arquivo de cache e sem expor mensagens da corretora. Após validação completa, grava cache D316 0600 com O_EXCL e nunca sobrescreve.

O comando `scripts.cache_j1_n50_ws_metadata_owner_once` realiza essa única captura somente com suas cinco flags explícitas; sem flags não faz rede, serviço ou alterações no SQLite. O segundo comando `scripts.run_j1_n50_ws_owner_cached_once` é para a janela pré-fechamento e requer um cache D316 pré-existente. Nenhum dos dois foi instalado/executado na VPS nesta entrega.

Teste sintético `tests/test_j1_n50_ws_metadata_bootstrap_d317.py`: one-GET completo, replay do mesmo cache, recusa segunda captura, 10006, TryFi malicioso, locks concorrentes, flags ausentes e janela causal expirada; zero WS, GET kline REST, ordens e systemd.

### Limite causal de duração da lease

Mesmo iniciando apenas 10 segundos antes da virada, a função reduz o `WSRunBudget.max_seconds` efetivo para encerrar até aproximadamente 119 segundos após o fechamento, pois D313 rejeita recibos além de 120s. Um lease de 150s que partisse a 11s do fechamento ultrapassaria a janela de evidência sem essa proteção. O teto não aumenta requisições, não gera retries e não altera o relógio do candle. Teste com fake-clock cobre essa fronteira.
