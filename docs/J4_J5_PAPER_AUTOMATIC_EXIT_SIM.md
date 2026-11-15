# J4/J5 — Saídas automáticas PAPER com mark hipotético (#650)

## Resultado de produto

O painel local em português agora permite ativar uma política de saídas simuladas **ao criar** uma posição PAPER. No cartão da posição, a pessoa informa um preço de fechamento **hipotético** e clica em **Simular próximo fechamento PAPER**. O aplicativo aplica o próximo gatilho automaticamente, sem exigir cliques separados de parcial ou encerramento. Não há dados de mercado recebidos por esse controle nem ordens.

**Escopo deliberado:** é uma simulação de gestão de saídas **no navegador**, com entrada de preço totalmente fictícia. O motor J4 Python de intenções, risco e reservas duráveis continua separado; esta funcionalidade não transforma o navegador em executor de ordens, não faz reconciliação, não instala stop e não valida qualquer estratégia.

## Política por posição

- Opt-in na abertura: alvo 1 (movimento favorável), alvo 2 (movimento favorável superior), stop (movimento adverso) e porcentagem a realizar **do saldo restante** em cada alvo. Percentuais em basis points inteiros e BigInt; valores iniciais da UI `1%, 2%, 1%, 50%` são **exemplos**, configuráveis por posição e sem garantia de segurança. A configuração é **imutável após a abertura**. A alavancagem de 50x continua apenas configuração de pesquisa.
- O motor rejeita target2 menor ou igual a target1, alvo e stop superiores/iguais a 100%, parcial nula ou plano impossível com a reserva mínima do runner. Antes de criar a posição, valida por duas chamadas de ensaio do mesmo `partialExit`, sem registrar eventos.
- `applyAutoPaperStep(position, mark, step)`: aceita apenas posição aberta e com `auto` v1, mark positivo decimal-string com até 8 casas, e passo inteiro exatamente `lastStep+1`. Cada clique representa **um novo passo hipotético de usuário**, não uma vela de exchange ou timestamp verificável.
- Prioridade: se o preço cruza o stop, o motor usa `closeRunner` para encerrar todo o saldo fictício (inclusive o residual). Caso contrário, se cruza o próximo alvo, usa `partialExit` com `REMAINING_BALANCE`. Quando a mesma marca ultrapassa os dois alvos de uma vez, aplica **no máximo uma** parcial por passo (não presume duas execuções). Após dois alvos, runner continua aberto e pode ser fechado manualmente ou por stop hipotético.
- Sinal LONG: preços `>= entrada*(1+alvo)` nos alvos, `<= entrada*(1-stop)` no stop. SHORT inverte a direção dos comparadores. Compara produtos BigInt para não arredondar limiares.
- Se o próximo alvo for incompatível com parcial manual já executada ou o piso de runner, `partialExit` recusa antes de mutar; o passo não avança. Em mark inválido/duplicado, nada muda.
- Cada ação escreve **um único evento** PAPER existente (`PARTIAL_PAPER` ou `CLOSE_PAPER`) com metadados opcionais `autoStep`, `autoAction = TARGET_1|TARGET_2|STOP`; cada marca sem gatilho apenas avança `lastStep` local. Os eventos continuam sendo lançamentos fictícios de quantidade, **não fills com preço/taxa**.
- `validateState` protege `hits`, `lastStep`, sequência e tipo de eventos (STOP só pode acompanhar CLOSE, TARGET apenas PARTIAL com percentBps e REMAINING_BALANCE). Exportação e restauração v1 aceitam novos campos **opcionais exatos** e continuam aceitando cenários antigos sem `auto`. Arquivos malformados continuam recusados.

## Exemplo causal do simulador

Posição LONG de entrada US$ 100, margem fictícia US$ 3, 50x, quantidade inicial 1,5, runner mínimo 6%, alvos +1% e +2%, stop −1%, parcial 50% do saldo:

1. Mark hipotético 101, passo 1: alvo 1, resta 0,75 unidade;
2. Mark hipotético 102, passo 2: alvo 2, resta 0,375 unidade (runner ainda aberto);
3. Mark hipotético 99, passo 3: stop, encerra 0,375 unidade **fictícia**. NÃO significa execução no preço 99, PnL realizado nem stop instalado.

SHORT usa as mesmas regras com marcas 99/98/101. Mark inválido não avança. A decisão e os eventos permanecem no JSON local após recarregar; duplicar o mesmo `step` por API falha.

## Limites e segurança

**Não** calcula execução de ordens, fees, funding, slippage, bid/ask, spread, mark real, taxa de manutenção, margem de liquidação, trajetória intrabar, gap, posição real, lucro líquido ou equity. Com **50x**, uma liquidação pode ocorrer antes de qualquer stop fictício; exibir um fechamento PAPER não constitui proteção. O preço hipotético nunca deve ser confundido com N50/J2 ou ordem autorizada. Nenhum hook automático usa watchlist J2, navegador remoto, WebSocket, endpoint de exchange, timer VPS, chave ou rede adicional.

**Não executar deploy nesta PR.** O modo `offline_paper` continua único e não autorizado para testnet/live. A entrega J4 completa requer o motor Python de risco/reservas, fills reconciliados, mark/liq de venue e gates J1/J3/J6, separados deste laboratório.

## QA e aceite

- Node/BigInt: LONG e SHORT, stop prioritário, dois alvos, runner preservado, mark inválido, target/step duplicado, alvo fora de ordem, plano impossível com runner, campo auto ausente legado, tamper de `hits` ou tags.
- Browser Chromium mobile 320 px: opt-in, aplicar primeiro alvo, reload, impedir marca inválida, aplicar segundo alvo, encerrar stop, reload e verificar histórico; manter o fluxo legado 390 px de parciais manuais/export/restore/N50/J2, testar 768/1280, no-fetch e overflow zero.
- CI Linux/docs, Windows/offline e PAPER/Chrome com SHA exato, revisão e merge **sem deploy**. D323 #585 e Top50 #319 continuam gates distintos. Custo adicional R$ 0,00.
