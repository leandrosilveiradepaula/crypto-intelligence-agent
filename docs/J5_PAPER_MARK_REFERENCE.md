# J5/PAPER-MARK1 — mark hipotético nas posições locais (#646)

## Objetivo
Permitir que o titular faça uma pergunta prática ao laboratório: **se eu digitar um mark hipotético diferente do preço de entrada, qual é a variação bruta da quantidade PAPER ainda aberta?**

O motor do app já fornecia `grossMarkPnlCents(position, mark)` com BigInt e a mesma carteira local mantém `leverageAtOpen` e `remainingUnits` após cada parcial. Esta entrega somente expõe o cálculo no cartão de cada posição ABERTA; não desenvolve outro motor financeiro.

## Contrato
- Campo por posição denominado **Mark hipotético (US$)**, preenchido inicialmente com o preço fictício de abertura, com 8 casas e sem dependência de relógio/fonte.
- Resultado inicialmente zero: **PnL bruto hipotético**. Editar o campo recalcula exclusivamente com `CIAEngine.grossMarkPnlCents`, respeitando LONG/SHORT e quantidade remanescente após parciais.
- Falha de parsing mostra **Mark inválido** e remove o valor calculado anterior da tela. Preço sem sinal, não numérico, zero ou fora do intervalo não valida.
- O mark **não** entra em `state.positions`, `localStorage`, exportação JSON, eventos de fill ou HTTP. Ao renderizar novamente o cartão, volta à referência inicial, sem alegar preço corrente.
- Posição CLOSED não tem mark para reavaliação retroativa; encerramentos PAPER continuam somente registros de quantidade, não fills reais.
- Texto permanente diferencia **variação bruta referencial** de PnL financeiro. Não incorpora fee, funding, spread, slippage, taxa de manutenção, caminho intrabar, margin call/liquidação ou conta real. Não usa `markPrice` de exchange.
- O aplicativo continua local/offline PAPER, sem websocket, fetch adicional, ordens ou credenciais; sem alteração no coletor N50, scripts J2/J3 ou VPS.

## Casos de regressão
1. LONG: margem fictícia US$ 3, alavancagem 50x, entrada US$ 100, quantidade 1,5. Mark 101 => **+US$ 1,50 bruto**; 99 => **-US$ 1,50**.
2. Após parciais 50%, 60% e 70% do saldo restante, resta 0,09 unidade; mark 101 => **+US$ 0,09 bruto**. A referência respeita parciais mas não inventa realização ou taxas.
3. Mark malformado, `NaN` e 0 devem negar cálculo; não manter texto favorável anterior.
4. Alterar mark não cria posição, não altera ledger nem alavancagem; a pausa continua funcional.
5. Testes Python/Node e navegador Chromium nos tamanhos 320, 390, 768 e 1280 px; restrições de rede/CSP, sem overflow.

## Gates
CI docs/Linux, Windows/offline e PAPER/Chrome **no SHA final**, inspeção do diff, merge seguro sem deploy. A auditoria J1 D323 e o Top50 #319 permanecem independentes; nenhuma performance financeira, liquidação ou estratégia foi validada por esta UI. Custo extra R$0.
