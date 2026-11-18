# J2/J5 D421 — ciclos públicos finitos e saúde N50 no celular

## Problema do produto

O monitor Bybit D418 já funcionou **na VPS real** em uma sessão de
62,107 segundos, 12.006 tickers pós-ACK, 50/50 contratos observados,
sem reconexões e com pings/pongs 2/2. Entretanto, somente 45/50
contratos tinham cotações frescas ao final; cinco expiraram pelo
relógio da exchange. A correção D420 eliminou a contagem excessivamente
otimista do livro por relógio de recepção. A J1 continua coletando
velas fechadas de 1h separadamente.

O usuário precisa observar evolução sem invocar manualmente uma nova
lista de ativos, sem fingir que uma amostra finita virou feed 24×7 ou
que a ausência de cotações não afeta o risco.

## Entrega técnica

`j2_public_n50_health_cycles_d421.py` executa de **um a 24 ciclos**
limitados e independentes do operador D418. Cada ciclo faz nova leitura
protegida da epoch owner J1, assina a coorte em sessão pública Bybit,
mede frescor pela exchange, revalida epoch ao fechar, e projeta
APENAS números agregados para um novo contrato:
`j2-public-n50-finite-health-d421-v1`.

O contrato inclui relógio UTC da amostra, contratos solicitados,
observados, frescos no encerramento, expirados, nunca recebidos,
inelegíveis, ACKs, ping/pong, frames aceitos, reconexões e flags
explícitas de proibição. **Não inclui símbolos, preços, diretores
privados, conta, saldos, hashes do ranking ou payloads WebSocket.**

- Se um ciclo falhar ou o relatório D418 quebrar o contrato, a última
  amostra é **substituída** por `source_unavailable`, não por um status
  saudável antigo. Persistência com substituição atômica e `fsync`
  de um arquivo count-only no diretório privado proprietário `0700`
  (conteúdo `0600`). Lock exclusivo não bloqueante impede dois
  observadores locais sobre o mesmo destino.
- Nenhum journal, símbolo e preço da J1 ou diário PAPER é alterado.
  Não cria ticker ranker nem abre conexão privada, nem serviço/timer.
  A forma de invocação é o CLI
  `scripts.observe_j2_public_n50_health_cycles_d421`, com opt-ins
  separados para leitura owner, rede pública, pesquisa pessoal,
  elegibilidade regional e gravação local do resumo.
- O módulo `web/app/paper-ws-health.js` (J5) agora importa o
  mesmo JSON sanitizado pelo seletor local existente, o valida campo
  a campo e mostra 45/50 + cinco expirados, sinal indisponível,
  horário da amostra e ausência de vínculo com stops/posições PAPER.
  Não altera `app.js`, não usa `fetch`/WebSocket para o monitor e
  não depende da VPS enquanto o usuário abre o ZIP offline.

## Limitações honestas

**Isto não instala um supervisor 24×7.** O limite de 24 ciclos e a
emissão de um arquivo ao fim de cada lease constituem a etapa
intermediária **sem release**. Mesmo quando os 50 estavam frescos
ao ENCERRAR uma amostra, esse fato pode ficar obsoleto segundos depois.
Não habilita entradas, coloca stops, emite ordens, consulta contas
nem altera os controles de 50x ou margem.

A continuidade operacional real exige uma jornada posterior de
serviço isolado, watchdog, renovação de sessão com cuidado de posições,
telemetria de desatualização durante a sessão e canal de leitura privado
para o aplicativo móvel. Um endpoint de acesso remoto exige
autenticação, privacidade e gate de produção específico. Não iniciar
serviço ou expor HTTP na VPS só porque os testes passaram.

## Testes e aceitação

`tests/test_j2_public_n50_health_cycles_d421.py`: síntese 45/50,
50/50, ausência de dados, substituição do último status, conteúdo
privado atômico 0600, flock, symlink, directory 0700, flags e contagens
adulteradas, importação móvel via Node e tratamento de arquivo
desconhecido. Node não instalado na VPS owner; a auditoria completa
GitHub deve executá-lo. Testes originais D417 (importação JSON) e
D418 (lease público) são regressões.

Prova real D418 e auditoria J1 D323 estão registradas nas issues
operacionais; esta entrega D421 **não se apresenta como prova 24×7**.
Custo adicional R$ 0,00.
