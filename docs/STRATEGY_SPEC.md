# Estratégias e gestão de vencedores

## Entradas: hipóteses, não promessas
- A: expansão depois de compressão de volatilidade, com validação de volume, liquidez e contexto.
- B: continuação de tendência após correção e retomada.
- C: força relativa frente ao Bitcoin e demais ativos.
- D: recuperação após falso rompimento como experimento posterior.

O regime de mercado deve modular elegibilidade e decisão. Dados de derivativos são candidatos a adicionar valor, não confirmação automática. Scores não podem ser tratados como probabilidades calibradas.

## Alavancagem e posições
Padrão global 50x; cada posição registra leverage_at_open e margem, e não é alterada retroativamente quando a configuração muda. Não impor número fixo de operações.

## Saídas
- INITIAL_POSITION: o percentual incide sobre quantidade inicial; soma das realizações não ultrapassa 100%.
- REMAINING_BALANCE: o percentual incide sobre o saldo de posição imediatamente anterior. Exemplo: 50%, 60% e 70% sucessivos deixam 6% da quantidade inicial.
- Runner opcional para movimentos prolongados, com trailing e invalidação baseados em regras testáveis.
- Ordem e tamanho das saídas precisam respeitar precisão e mínimos de contrato; nunca supor que uma parcial de tamanho arbitrário seja executável.

## Avaliar
PnL líquido, risco e drawdown da carteira, MAE/MFE, taxa de liquidação, sobrevivência a recuos, eficiência de captura e estabilidade fora da amostra. Não usar máximos futuros para decidir no presente; distinguir marcação de preço e preço negociado.
