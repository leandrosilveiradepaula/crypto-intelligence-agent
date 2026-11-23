# D447 — Hipótese observada J2 → pré-voo J3 → intenção PAPER durável J4

A ponte `j2_observed_paper_entry_d447.py` conecta os contratos existentes D434/D435 (candles públicos Bybit fechados) ao ticker D385, aos custos estimados J3/PRE2, às condições de margem PRE11 e ao RiskGate/saúde AUTO8. Quando todos os filtros passam, reserva apenas uma intenção `OPEN PENDING` no diário AUTO2 existente. Não cria fill, posição AUTO4, stop nativo, ordem real ou autorização de sinal.

## Fluxo de entrada
1. Exige opt-in `allow_hypothetical_paper_open=True`, uma série pública cronológica fechada e a hipótese LONG/SHORT do último fechamento (D435); nenhuma conversão para `synthetic_fixture`.
2. Exige ticker Bybit posterior à vela, fresco simultaneamente pelos relógios da corretora e de recebimento (até 3s); janela de pesquisa da hipótese inicialmente até 120s. Símbolo, marcação PAPER, cotação, contrato e direção devem corresponder.
3. Um filtro determinístico com Decimal calcula custos hipotéticos de entrada/saída (taxas e slippage declarados), ganho líquido do primeiro alvo parcial e margem remanescente após o stop assumido. A entrada é vetada se alvo líquido ou folga de margem não forem estritamente positivos.
4. PRE11 valida tamanho e incremento hipotéticos, limite de alavancagem e alavancagem da nova posição. AUTO8/RiskGate/AUTO2 revalidam sob transação de reserva as posições, PENDING/UNKNOWN, risco e kill-switch; a chave estável de símbolo+hora impede nova intenção para a mesma hipótese após reinício.
5. Resultado versionado `j2-j3-paper-entry-d447-v1` indica apenas intenção PAPER pendente, sem preços de mercado, fills, conta ou métricas financeiras reais.

## Limites importantes
A fonte pública não é autenticada; um objeto de ticker pode ser fornecido somente por um chamador controlado, e esta ponte por si só não prova captura pública real. Não há simulação de execução BBO posterior, nem funding, margem de manutenção, liquidação, gap, stop executável ou custo verificado da Bybit. O filtro de stop presume execução integral no preço hipotético, logo é necessário, mas não suficiente. O operador residente D444 ainda acompanha somente posições AUTO4 já abertas; D447 **não foi ligada ao worker** e não produz uma posição. Nenhuma alteração J1/VPS/release/credencial/POST, custo R$0.

## Testes e próximos gates
`tests/test_j2_observed_paper_entry_d447.py` cobre LONG/SHORT persistidos, receipt de margem, bloqueio de replay, ausência de hipótese/opt-in, quote pré-close/velha/futura, identidade/BBO, custos, stop, kill-switch e origem de candle adulterada. CI Linux/Windows/mobile no SHA exato e revisão devem ser comprovadas antes de merge. A etapa seguinte é integrar a coorte dinâmica J2 a essa reserva, acompanhamento PAPER e fills explicitamente simulados, com avaliação J3 fora da amostra; nada disso autoriza ordens reais.