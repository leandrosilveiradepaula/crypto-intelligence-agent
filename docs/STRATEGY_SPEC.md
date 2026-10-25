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


## Pré-trabalho J2/PRE1 — features causais com candles exclusivamente sintéticos (#66)
O módulo puro `synthetic_feature_engine.py` recebe a estrutura `ClosedCandle` já existente, porém exige **somente** `quality=synthetic_fixture`, mercado `linear_perpetual`, série de um único exchange/símbolo/intervalo, timestamps UTC contíguos alinhados e velas fechadas até `decision_at_ms - close_safety_ms`. No máximo 10.000 candles e períodos explícitos de 2 a 500; não usa rede, storage, outro ativo, cache, lookahead, alavancagem ou ordens.

Definições matemáticas configuráveis e determinísticas (Decimal com contexto interno 50 dígitos):
- **EMA(close, N):** primeiras N-1 saídas são `None`; valor inicial é SMA dos N primeiros closes; a seguir `EMA_t = EMA_(t-1) + (2/(N+1))*(close_t-EMA_(t-1))`. Não iniciar EMA artificialmente em close[0].
- **TR e ATR Wilder (N):** `TR_0=high_0-low_0`; de t>=1, `TR_t=max(high-low, abs(high-close_(t-1)), abs(low-close_(t-1)))`. `ATR_(N-1)=mean(TR_0..TR_(N-1))`; depois `ATR_t=((N-1)*ATR_(t-1)+TR_t)/N`.
- **Extremos anteriores (N):** `preceding_high_t=max(high_(t-N)..high_(t-1))` e mínimo análogo, nunca incluem a vela atual. Sem N candles anteriores, `None`.
- **Atividade de volume (N):** `quote_volume_t / mean(quote_volume_(t-N)..quote_volume_(t-1))`, sem incluir a barra atual na base. Se a média anterior for zero ou houver aquecimento insuficiente, `None` (não inventar divisão/volume).
- **Retorno simples:** `close_t/close_(t-1)-1`; primeiro retorno `None`. Volume cotado é comparável **somente dentro da mesma série e unidade**, não entre venues ou moedas. Nenhuma probabilidade, score ou regra buy/sell é produzida.

A linha de features mantém o instante do candle e propriedades de aprovação de sinal sempre `false`; a série guarda `quality=synthetic_fixture` e `approved_for_live_use=false`. Esta implementação é uma **pré-condição técnica independente**, não o início operacional ou aceite da J2. Para quaisquer dados reais, ainda serão exigidos gate J1, licença, qualidade, reconstrução point-in-time, provas quantitativas e J3. Nenhuma parametrização sugere rentabilidade.
