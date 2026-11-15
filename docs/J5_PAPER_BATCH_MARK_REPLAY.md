# J5/J6 — Replay em lote de fechamentos PAPER hipotéticos (#652)

## Uso no produto

A posição PAPER com gatilhos automáticos (D351/#650) já processa um preço manual por clique. O próximo incremento permite preencher **de 1 a 24 preços de fechamento fictícios, um por linha**, e clicar uma única vez em **Reproduzir cenário PAPER**. O aplicativo percorre o cenário em ordem usando **o mesmo** `CIAEngine.applyAutoPaperStep` — nenhum segundo motor de estratégia, stop, parcial ou saldos foi criado.

Isso ajuda a observar o comportamento do plano após uma sequência hipotética: alvos, reserva de runner, stop e o histórico dos eventos. **O usuário já conhece todos os preços quando escolhe esse cenário**, portanto o replay não constitui validação prospectiva, walk-forward OOS, previsão, preço de mercado atual ou PnL.

## Contrato de processamento e atomicidade

1. Aceita somente `marks` como array de **1 a 24 strings decimais positivas exatas** (até 8 casas, sintaxe de `fixed()` já existente); a UI limita o textarea a 512 caracteres e separa apenas por linhas. Não há consulta a API, feed ou importação J2/N50.
2. Antes de qualquer movimento, **valida TODAS as marcas**. Em seguida cria **cópia integral** da posição, de sua política `auto` e dos eventos. Cada marca processada é um novo passo fictício monotônico; usa `applyAutoPaperStep`, que prioriza stop e aplica no máximo uma parcial por passo.
3. Em caso de erro em um passo posterior — por exemplo, um target conflitando com parcial manual/runner — descarta a cópia. O registro original (`status`, `remainingUnits`, `events`, `auto.lastStep/hits`) fica **idêntico**. A UI não chama `save()` nesse erro.
4. Se o STOP fechar o saldo antes do fim da lista, não age em marcas posteriores. O relatório conta `processedSteps`, `skippedAfterClose`, `targetEvents` e `stopTriggered`. Todas as entradas, inclusive as ignoradas após stop, precisam ter sintaxe válida antes do processamento.
5. Somente após conclusão sem erros, copia `remainingUnits/status/events/auto` de volta à posição e persiste o estado uma vez com `save()`. O export/restore PAPER v1 continua compatível: os novos passos usam exatamente a política e as tags `autoStep/autoAction` já versionadas em D351.

## Exemplos de pesquisa

LONG, entrada 100, alvo1 +1%, alvo2 +2%, stop −1%, parcial 50% de saldo e runner mínimo 6%:

- Cenário `101\n102\n99\n98`: processa 3 passos, registra dois targets e STOP, descarta um preço depois do fechamento. Não declara fill real a 99 ou PnL.
- Cenário `101\n102\nNaN`: rejeita **todo** o lote e não registra nem o primeiro target.
- Com parcial manual anterior, o segundo target pode atingir indevidamente o piso de runner. O lote inteiro deve ser rejeitado, sem commit parcial.
- SHORT inverte comparação de preços por meio do **mesmo** motor #650, sem nova lógica própria.

## Limites invioláveis

Modo `offline_paper` apenas. O fluxo não executa ordens, não acessa corretora, não coleta candles reais e não certifica que um stop seria executável antes de liquidação, especialmente a 50x. Sem taxas/funding/slippage, preço mark real, alavancagem permitida pela venue, distância de liquidação, fills ou conta do usuário. Não há cron, execução contínua, ativação em VPS, websocket, endpoint, banco ou segredo.

O replay em lote serve para homologar **o funcionamento do simulador**. J4/J5/J6 e J1 D323/Top50 continuam com critérios de aceitação distintos; nenhuma rentabilidade foi demonstrada. Custo extra R$ 0.

## Evidências exigidas

Node: marca inválida ao final e falta de runner na segunda parcial não deixam eventos parciais, limite 1..24, LONG/SHORT, STOP antes do último preço, reinício e posição manual rejeitada. Chromium nos tamanhos habituais: em 768px, um lote fecha ficticiamente o saldo, histórico sobrevive ao reload, não há request nem overflow; preservar os testes 320px de um passo e 390px de mark/backup/N50/J2. CI docs/Linux, Windows/offline e PAPER/Chromium verdes no SHA exato antes de merge sem publicação.
