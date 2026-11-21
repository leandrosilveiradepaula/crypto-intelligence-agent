# D451/D452 — N50 dinâmico direto da Bybit e risco PAPER dos diários reais

## Entrega funcional

O ponto de entrada run_dynamic_public_paper_lease_once (j2_j4_dual_public_supervisor_d450.py) integra uma coleta REST pública, o diário de candles isolado J2, o risco AUTO2/AUTO4 e os supervisores WebSocket públicos de ticker e kline. Funciona somente para pesquisa + simulação PAPER; nenhuma ordem para a corretora, assinatura ou API privada é usada.

### Atualização automática do universo — D451

- Captura todo o catálogo paginado de /v5/market/instruments-info?category=linear usando o cliente GET limitado já existente, seguido por /v5/market/tickers?category=linear.
- Confere cadeia de cursores, duplicação, relógios e cobertura; admite apenas LinearPerpetual Trading, USDT quote/settle, com histórico mínimo de 24h, filtros de lote/preço/alavancagem, e descarta explicitamente contratos TradFi, pré-listagem, futuros e instrumentos malformados.
- Ordena o conjunto apto por turnover24h móvel público, com Decimal, e seleciona 50 instrumentos. BTCUSDT sempre integra a coorte para contexto: caso fique fora dos 50 maiores, a pesquisa considera os 49 primeiros mais BTC (isso NÃO é um Top50 estritamente puro).
- O volume móvel não representa 24 velas UTC fechadas nem prova identidade criptográfica/financeira de ativos. A lista é PROVISÓRIA e só gera hipóteses PAPER, sem sinais aprovados.
- Converte maxOrderQty (unidades BASE) em limite hipotético de notional USDT usando o mark da cotação posterior; sem assumir que essas regras de exchange sejam uma autorização de negociação.

### Histórico contínuo sem misturar épocas

A captura REST atualiza o ranking a cada novo lease. pin_dynamic_public_n50_epoch mantém um ponteiro local owner-only do conjunto de símbolos e filtros. Oscilações de turnover que alteram apenas a ORDEM não mudam a identidade da coorte: a mesma pasta J2 e o mesmo SQLite de candles são preservados após reinício. Mudanças de membro ou especificação, origem do ambiente (replay→público) ou expiração do epoch criam NOVO journal, deixando o anterior intacto, sem relabel, merge ou backfill implícito. O histórico só fica pronto depois de 24 fechamentos horários confirmados para TODOS os membros da coorte mantida. Um universo que muda exige novo warmup.

Pasta J2: diretório 0700 owner POSIX não-root, arquivos 0600, ponteiro com integridade, rotatividade sob flock e retenção de históricos antigos. Não ler ou reabrir arquivos da J1.

### Risco PAPER persistido — D452

DurablePaperRiskSource usa leituras read-only de todos os intents/eventos AUTO2 e de todas as posições AUTO4, com replay, validação de integridade, vínculo de receipts e check de órfãos. Cotações pós-ACK D385/D386 são usadas para calcular exposição bruta de posições ainda abertas e são invalidadas na reconexão. O número de aberturas pendentes e o kill-switch vêm do diário AUTO2, não de constantes inventadas nos testes.

Se existe fill sem contabilidade real de custo ou PnL, o risco de perda realizada NÃO pode ser afirmado como zero; a abertura de novas posições passa a ser bloqueada até reconciliação de resultado/custos. Com diário comprovadamente virgem, zero realizado é constatável, não presumido. Cotações de posições mantidas precisam estar frescas. É uma limitação consciente: o atual AUTO2/AUTO4 grava quantidade/eventos, não preço líquido de execução, funding ou liquidação. Esse comportamento não impede os stops e parciais PAPER já acompanhados pela J4.

### Sessão e operação

O operador D450 usa dois WebSockets públicos separados e concorrentes, um para kline.60 confirmado pós-ACK/pós-append, outro para ticker BBO pós-ACK. Para qualquer nova abertura, D449/D447/D448 exigem coorte completa da mesma hora, força relativa ao BTC, custos/margem/risk gate, intenção AUTO2 PENDING, depois tick causal para fill EXPLICITAMENTE SIMULADO. Esse fill cria AUTO4 e integra a posição às rotas D425 lidas pelo acompanhamento e J5. Posições já abertas continuam com prioridade de saída mesmo se a coorte não estiver completa.

Toda captura REST + WSS exige opt-ins explícitos de rede pública, pesquisa pessoal, elegibilidade regional, direitos de dados e uso PAPER. O runner termina ao fim do lease e NUNCA se anuncia como daemon instalado/proteção contínua.

## O que ainda falta

O software não foi instalado na VPS nesta mudança. Ainda é necessário homologar um período público real, habilitar serviço owner persistente com reinício e acompanhamento J6 sob gate de release, validar direitos/eligibilidade, e criar contabilidade de preço/custos/funding/liquidação e backtest J3 walk-forward/OOS. O histórico REST NÃO é falsamente transformado em candle confirmado do WS. A alavancagem 50x é parâmetro de pesquisa de risco alto, não segurança ou retorno garantido. Sem negociação real ou custo extra.

## Testes

- tests/test_j2_dynamic_public_n50_d451.py: paginação, BTC, rejeição de TradFi e dados malformados, origem GET limitada, limites do contrato, revisão de turnover sem recomeçar epoch, rotação de membros, ponteiro adulterado.
- tests/test_j4_durable_paper_risk_d452.py: zero somente no livro virgem, pending AUTO2, exposição AUTO4 após FILL, kill-switch, bloqueio por PnL desconhecido, reinício sem recuperar cotação como se fosse fresca.
- tests/test_j2_j4_dual_public_supervisor_d450.py: operação PAPER com fonte D452 conectada aos dois callbacks públicos simulados.
- tests/test_j2_j4_dynamic_public_paper_lease_d452.py: seleção REST dinâmica e duas sessões WSS de protocolo injetadas em duas horas, preservando o mesmo jornal e rejeitando iniciação sem opt-ins.
- Rodar todas as suítes Linux (owner não-root), Windows offline e navegador no SHA exato. Dados injetados não constituem captura real da Bybit.
