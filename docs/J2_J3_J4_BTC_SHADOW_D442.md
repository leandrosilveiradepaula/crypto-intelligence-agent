# D442 — integração J2/J3/J4: preço público → custo declarado → saídas PAPER

## Entrega funcional

Não criar outro coletor J1, outro ranking N50, uma segunda contabilidade de posições ou mecanismo paralelo de parciais. A integração única usa D441 (REST público para BTCUSDT específico), D385/D386 (ticker WSS com ACK/snapshot/delta), PRE2 (custo Decimal de entrada e saída hipotéticas), D426 (cenário ephemeral com FILL **explicitamente fabricado**), D391/D389/AUTO4 (reservas automáticas de stop/target intrahorárias). Isto aproxima J2, J3 e J4 no mesmo ciclo, em uma única conexão FINITA e com banco descartável.

## Contratos e ordem causal

1. Cinco opt-ins explícitos e usuário não-root no acesso real. Testes com socket injetado mantêm `injected_offline_protocol_replay` e nunca afirmam observação pública. A execução D442 **não acessa nem modifica arquivos, ponteiro, ranking, banco ou serviços J1**; utilitários legados importados transitivamente não são chamados para ler estado J1.
2. Um GET público só do contrato BTCUSDT deve validar `LinearPerpetual`, `Trading`, quote/settle USDT, filtros e relógio. O BTC é apenas prova de transporte; a seleção crypto-only N50 exige identidade PIT própria.
3. O supervisor recebe `tickers.BTCUSDT`, exige ACK e snapshot, preserva marca temporal, descarta eventos pré-ACK para o consumidor e falha fechado por relógio/lag/reconexão.
4. Ao primeiro mark próprio e recente, executa **duas triagens J3/PRE2** antes da abertura: (a) retorno bruto hipotético da **primeira parcial de 30%** superior aos custos declarados e (b) perda hipotética ao stop da posição inteira **mais taxas/slippage** estritamente inferior à margem de pesquisa configurada. Se falhar qualquer uma, **não fabrica abertura PAPER**. O stop pressupõe execução imediata ao preço informado, e portanto não prova proteção ou liquidação evitada. Funding, risco de gap, tiers e colateral reais continuam desconhecidos.
5. Somente para simulação, o D426 cria posição e FILL claramente artificiais em SQLite temporário; eventos POSTERIORES à abertura passam pelo AUTO4 existente. O mesmo quote que abriu não serve para fechar; stop tem prioridade sobre target, reservas não viram FILL e 50% residual permanece não realizado.
6. Se o contrato mantido ficar sem cotação válida por mais de três segundos, o supervisor falha fechado, ainda que o ACK tenha ocorrido. Sem serviço residente, não há proteção contínua ou ordens reais.

## Limites

- Custos/funding/liquidação e resultados são **cenários**. Margem, alavancagem e níveis não equivalem a conta, garantia de 50×, lot step da Bybit ou fill executável.
- O retorno sanitizado publica apenas contagens, decisões, flags de abstenção; jamais símbolo, ticks, preço, credenciais, posições financeiras ou PnL de conta.
- Não há live trading, testnet, endereços privados, reuso de estado J1 ou escrita fora do diretório temporário. R$ 0 adicional.
- A CLI `python -m scripts.run_j2_j3_j4_btc_shadow_d442_once` exige valores explícitos de custos e os cinco opt-ins. Sem flags ou fora do usuário POSIX, não abre transporte.
- Escopo de pesquisa J2/J3/J4 desta fatia: **BTCUSDT, uma única sessão, entrada e fill fictícios, saídas como intenções PAPER**. Próximas capacidades exigidas são feed N50/posições 24×7, RiskGate para sinais validados, custos/funding/tiers e marcação OOS com dados causais, e J6 liveness e reconciliação de fills. Nunca interpretar essa fatia como homologação.

## Aceite

Teste integrado com ACK + quote + quote seguinte, LONG/SHORT, custo inviável, stop-first, sem quote, silêncio após abertura, limite de alavancagem observado, dedup/replay e falta de opt-in. CI Linux/Python/docs, Windows e browser da branch no SHA exato. Sem deploy e sem merge condicionado à evidência do piloto público D441.
