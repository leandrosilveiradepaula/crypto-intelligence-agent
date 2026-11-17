# J3 / D398 — risco após saídas parciais com quantidades efetivamente confirmadas em PAPER

## Correção do excesso de conservadorismo do D397

O gate D397 **corretamente bloqueia** um aparente lucro quando o mark
indica condição de liquidação *antes* da saída. Porém seu proxy
PRE16 conserva o **notional de abertura inteiro** até o fim,
mesmo depois de uma parcial PAPER registrada. Ele pode vetar
trajetórias que, num modelo de quantidade remanescente, não
chegariam a uma condição discreta de liquidação.

D398 adiciona um **segundo teste de pesquisa**, nunca substitui
o D397: primeiro executa o gate D397 completo; só então pode
refinar um veto de `abstain_prior_mark_liquidation_proxy` se
o ledger comprovar que uma parcela saiu **antes** do mark adverso.
Veto por stop ou alvo anterior continua absoluto.

## Fluxo e fonte de verdade

`audit_paper_partial_derisk_mark_risk` reutiliza exclusivamente:
- **AUTO2/AUTO4 e o leitor mode=ro D397:** a abertura contém
  comprovante imutável de margem/alavancagem **daquela
  posição**; a posição precisa ter fills explícitos,
  todos reconciliados, e estar fechada sem UNKNOWN.
- **D393:** preços e timestamps dos recibos de FILL
  conferem 1:1 com eventos persistidos; custo total
  calculado com o motor já existente.
- **PRE16:** valida sequência de marks/trades, lacunas,
  horários, contrato de parâmetros, tiers de manutenção
  sintéticos PIT e viabilidade do replay de risco;
  seu cenário original de exposição total permanece
  registrado como baseline conservador.
- **PRE2 / `evaluate_synthetic_costs`:** taxas e
  slippage de entrada cobrados **uma única vez** no
  notional inicial; saída paga taxa/slippage somente
  das unidades preenchidas; funding tem sinal LONG/SHORT
  e notional fornecido por evento, validado por D393.
- **`maintenance_for_mark`:** a exigência de manutenção
  usa a quantidade ainda aberta vezes o mark observado;
  não reinventa tiers, tabelas de risco ou fórmula venue.

O procedimento em cada tick é, nesta ordem:
1. Reconstituir o caixa hipotético inicial, PnL
   já realizado, taxas/slippage incorridos e funding
   do período anterior ao tick.
2. Calcular patrimônio sintético marcado **nas unidades
   ainda abertas** e exigência de manutenção tierada.
3. **Testar liquidação, stop ou target antes de aplicar
   qualquer FILL do mesmo timestamp.**
4. Só depois de passar os testes, aplicar um eventual
   FILL de quantidade positiva, registrado no AUTO4 e
   com recibo D393/TICK correspondente.
5. No último tick, exigir posição restante zero e
   reconciliação **exata** do resultado de referência
   com o cálculo financeiro já existente em D393.

Nenhum fill fictício é inferido de mark, alvo, OHLC,
BBO ou reconexão de WebSocket. Nenhuma parcial cria
margem adicional ou altera retroativamente a alavancagem
da entrada. Mudança de checkpoint entre a consulta
de risco e a entrega do relatório falha fechado.

## Evidência reproduzível

```bash
python -m unittest discover -s tests \
  -p 'test_paper_partial_derisk_risk_gate_d398.py' -v
```

Fixture LONG em 50x: abertura PAPER confirmada de 2
unidades a 100, margem solicitada 4, parciais explícitas
1 unidade a 101 e 1 unidade a 103. Taxa 10 bps por ponta,
slippage adverso 5 bps por ponta e tiers sintéticos de
manutenção de 50 bps.

- **Mark 97 ANTES da primeira parcial:** o risco ocorre
  com as 2 unidades originais e o resultado é `null`.
- **Mark 97 DEPOIS da primeira parcial:** o baseline
  D397 ainda acusa liquidação no proxy integral; o
  cenário D398 avalia **apenas 1 unidade ainda aberta**
  e pode produzir referência condicional +3,394
  unidades sintéticas após custos, sem certificar
  que isso aconteceria realmente.
- **Mark 97 EXATAMENTE no tick do primeiro FILL:** a
  verificação utiliza as 2 unidades anteriores,
  e o resultado fica `null`.
- **Mark 95 depois da primeira parcial:** o novo
  modelo também encontra risco de liquidação,
  logo o resultado permanece `null`.
- Em SHORT a direção se inverte, com mesma exigência
  de fills registrados e custos. Em 10x, o caso
  mark 97 é somente referência condicional.
- Funding positivo/negativo é debitado/creditado
  com as regras PRE2 e reduz/aumenta o resultado
  condicional do cenário; discrepâncias de notional,
  timestamps, tiers, recibos, stop ou target anterior
  nunca geram número válido.

## Restrições de interpretação

Um segundo cenário que não detectou liquidação
**não demonstra proteção real**, porque todos os
ticks, fills, execução e tiers são sintéticos. A
trajetória entre observações é desconhecida, e
abertura/fechamento em preços hipotéticos podem
ter ocorrido de outra maneira ou nem ter ocorrido.
Um cálculo baseado em quantidade remanescente pode
ser menos pessimista do que o full-notional D397,
mas também pode ser otimista se pressupuser fills
que um mercado real não proporcionaria.

O algoritmo **não** gerencia colateral de conta,
variação de margem isolada/cross, fundos resgatados,
liquidação Bybit, risco de fila, ADL, partial margin
release, ou liquidez/impacto. Nunca configurar o
resultado como PnL realizado ou sinal de ordem.

É código **offline PAPER somente leitura**. Não
altera VPS, J1, serviços, WS, APIs reais, contas,
SQL de produção, credenciais, ordens ou custos.

O próximo gate para J3/J6 é validar trajetórias de
mark, custos, funding e snapshots PIT com fontes
autorizadas e enfrentar ordens não executadas e
stress intrabar. J5 deve exibir separadamente
`veto conservador`, `cenário pós-parcial` e
`P&L verificado` (sempre não disponível nesta fase).
