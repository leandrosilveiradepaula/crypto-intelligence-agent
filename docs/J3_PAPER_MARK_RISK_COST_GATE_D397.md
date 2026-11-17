# J3 / D397 — gate causal de liquidação antes de exibir resultado PAPER

## Defeito de integração

A auditoria D393 é correta **para custos de fills declarados**,
mas expõe um resultado condicional sem confrontá-lo com a trajetória
de mark e a margem/alavancagem capturada na abertura. O motor de
replay J3/PRE16 já implementa o teste de condição de liquidação
com custos de entrada e manutenção em tiers; J3/PRE29 já o usa
para vetar resultados fictícios de runner.

**D397 reutiliza D393 + PRE16** numa consulta somente leitura
que não deixa uma realização aparente de lucro contornar
uma condição de liquidação, stop ou alvo anterior.

## Contrato financeiro conservador

`audit_paper_costs_with_prior_mark_risk` aceita um par de
journals locais PAPER AUTO2/AUTO4 e evidências typed
explicitamente fictícias. **Resultado numérico condicional
somente quando tudo abaixo acontece:**

1. AUTO2 e AUTO4 existem, têm hashes e contratos verificados
   pelo leitor `inspect_paper_position` com `mode=ro`
   e ambos concordam quanto à intenção OPEN e fills.
   Sem crosscheck AUTO2, não há resultado.
2. A posição Bybit PAPER foi encerrada por eventos FILL
   **persistidos**; nenhuma ordem pending/UNKNOWN, saldo,
   reserva sem reconciliação ou cancelamento pode
   produzir receita líquida.
3. Um comprovante imutável `PaperMarginIntentReceipt`,
   registrado na abertura, estabelece quantidade inicial,
   marca de referência, margem solicitada, moeda e
   alavancagem **naquela posição**. Não derivar 50x
   do parâmetro global atual.
4. O `SyntheticMarkReplayPlan` coincide exatamente
   com quantidade, lado, marca, notional, alavancagem,
   margem do receipt e taxas/slippage usados por D393.
5. Existem snapshots sintéticos PIT de manutenção de risco
   que precedem a entrada, com identidade do instrumento
   coerente e frescor limitado. Sem tiers explícitos,
   o resultado é `null`.
6. Há caminho causal de `SyntheticMarkTick` ordenado,
   sem gaps além do máximo configurado, terminando
   exatamente no último FILL. Todo evento FILL PAPER
   exige um trade tick com horário e preço idênticos
   ao recibo D393. Ticks sozinhos **não** criam fills.
7. D393 confirma a correspondência bijetiva dos
   preenchimentos e custos. PRE16 avalia cada mark
   em ordem cronológica, **liquidação antes de stop/alvo**.
   Qualquer primeiro terminal anterior ou simultâneo à
   realização bloqueia a apresentação de líquido:
   `conditional_net_after_risk_veto_quote=null`.
8. Releitura de AUTO2/AUTO4 após o cálculo detecta
   mudanças concorrentes no saldo PAPER e rejeita
   resultados obsoletos. A inspeção não grava bytes.

O gate é intencionalmente pessimista: PRE16 mantém o
**notional inteiro da abertura** durante o replay de marks,
mesmo que uma saída parcial tenha diminuído a exposição.
Isso pode gerar falsos vetos. Portanto, o resultado
`abstain_prior_mark_liquidation_proxy` significa
**condição de liquidação no proxy sintético**, NÃO
liquidação realmente ocorrida na Bybit.

## Testes reproduzíveis

```bash
python -m unittest discover -s tests \
  -p 'test_paper_mark_risk_cost_gate_d397.py' -v
```

Fixtures com abertura de 2 unidades a 100 e comprovante
de margem vinculado à ordem AUTO2; duas saídas PAPER
de 1 unidade cada, a 101 e 103 (LONG), com fills
registrados em AUTO4. A auditoria D393 aplicada à
posição encerrada retorna referência condicional
**+3,394 unidades fictícias após os custos declarados**.

- 50x, margem 4: mark adverso 97 antes do fechamento
  gera condição proxy de liquidação e o gate
  **retorna líquido nulo**, embora os fills
  posteriores aparentem lucro.
- 10x, margem 20: mesma trajetória não dispara
  condição de liquidação nos tiers sintéticos
  declarados; a referência +3,394 fica exposta
  **somente como cenário condicional**.
- Mark 100 sem condição terminal: em 50x o gate
  permite somente a referência condicionada.
- Stop/target anterior, preço de fill incorreto,
  gap temporal, snapshot PIT errado, recibo
  de margem ausente, ausência de crosscheck,
  posição não encerrada ou UNKNOWN: veto/abstenção.
- Casos LONG e SHORT, nenhuma ordem ou rede, e
  verificação de que os arquivos dos journals
  permanecem inalterados pela auditoria.

## Exclusões e lacunas

Não comprova margem/collateral verdadeiros, cap 50x
na região/conta/contrato, risco de ADL, liquidação
pela Bybit, execução de stop, calendário real de
funding, trajetórias intrabar entre dois ticks,
prioridade no book ou rentabilidade prospectiva.
O receipt AUTO2 é SHA local e **não autentica
a corretora**. Os tiers PIT são fornecidos
como fixtures; não vêm de instrumentos-info
ou da conta. Nem mesmo trajetória limpa
certifica sobrevivência, pelo risco entre ticks.

Não ativa WebSocket, REST, ordens, serviço VPS,
migrations, conta ou qualquer custo adicional.

**Próximos gates:** incorporar o gate à tela J5
sem apresentar resultado fictício como realizado,
testar cenários com parcial de-risking e margens
variáveis, coletar séries mark reais sem lookahead
pela J2/J1 e homologar prospectivamente na J6.
