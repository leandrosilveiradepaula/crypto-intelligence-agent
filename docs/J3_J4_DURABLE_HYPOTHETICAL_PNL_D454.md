# D454 — resultado condicionado de posições PAPER a partir dos próprios FILLs

## Evolução concreta do motor

A partir desta mudança, novos eventos `FILL` sintéticos AUTO2 (abertura D448) e AUTO4 (saída D394) podem carregar **o preço BBO hipotético efetivamente usado no cálculo do preenchimento**. Este atributo é persistido no **mesmo evento financeiro canônico** do journal existente, sem outro livro de operações e sem migration: eventos legados permanecem byte a byte com a serialização antiga e não recebem um preço fabricado.

`conditional_paper_pnl_from_existing_fills` reabre, em modo somente leitura, os journals AUTO2/AUTO4, confere consistência do OPEN e de seu receipt PRE11, carrega a política D448 imutável e exige que todos os eventos FILL usados tenham preços persistidos. Para saídas parciais ou completas, calcula resultado bruto por direção LONG/SHORT, taxas de entrada/saída e slippage adverso declarados usando o motor de custos J3. O resultado é reproduzível após restart e preserva a alavancagem individual de cada posição. Não depende do valor da última vela como preço fictício de execução.

O objeto de resultado mostra **resultado condicional antes de funding**, quantidade fechada e custos atribuídos às parcelas. Também mostra explicitamente `funding_settlement_unknown=true`, `true_realized_net_pnl_available=false`, `venue_fill_verified=false`. Não declara lucro nem perda reais e não autoriza negociação. Se uma posição antiga não tem preços completos, a leitura se abstém de valor numérico em vez de preencher com zero.

## Restrições que permanecem

- BBO público não prova posição executada na corretora, fila do book, slippage efetivo, taxas cobradas, liquidação ou margem real.
- Funding liquidado e seu calendário ainda não estão persistidos com recibos obrigatórios. Por isso o resultado **não substitui** o limite diário de perda no RiskGate D452, nem desbloqueia automaticamente novas posições.
- AUTO8 continua conservador enquanto não houver proteção comprovada; múltiplos contratos/posições são suportados pelo livro e monitor, mas nova abertura simultânea requer autorização de risco coerente.
- A UI J5 precisa expor esses dados como condicionais, sem alterar `financial_pnl_available=false` no contrato de resultados comprovados. Nenhuma release real/serviço systemd foi realizada.
- O operador D453 continua atendendo posições existentes em fallback N50, com saídas D391/D394 em dois quotes causais.

## Validação

`tests/test_j4_paper_conditional_pnl_d454.py` cobre serialização retrocompatível, preço hipotético positivo e exclusivamente FILL, LONG/SHORT, abertura a BBO pós-latência, parcial a BBO posterior, custo com Decimal, releitura após reinício e flags obrigatórias de funding desconhecido. Exigir CI Linux/Windows/mobile no SHA final e evidência J3 OOS antes de dizer que o produto sabe gerar lucro líquido. Custo adicional R$0 e J1 intocada.
