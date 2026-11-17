# J5 / D399 — painel móvel de risco J3 ligado ao relatório PAPER D398

## Resultado para o usuário

O console responsivo em português `web/app` já permitia
configurar posições PAPER, margens, alavancagens e saídas
simuladas. A tela possuía um choque **bruto** de 2%,
mas não interpretava os novos resultados J3 de
risco de liquidação, custo e de-risking por parciais.

D399 acrescenta **um painel J3 de auditoria PAPER** à
seção de posições, separado do simulador local e do
saldo das posições do navegador. O usuário pode
importar, pelo seletor JSON já existente, o retorno
`PaperPartialDeriskRiskResult.sanitized_report()`
produzido pela D398, schema
`paper-partial-derisk-risk-d398-v1`.

O painel mostra:
- alavancagem capturada na abertura PAPER;
- quantidade de observações de mark e FILLs confirmados
  avaliados no cenário hipotético;
- se o baseline de exposição total D397 teve veto;
- a causa da abstenção em português, ou
  **referência líquida sintética** quando todos os
  filtros permitem;
- aviso permanente de que não existe lucro real,
  stop nativo, plano de risco de corretora ou
  sobrevida a 50x comprovada.

**Relatório J3 externo não é vinculado automaticamente
a nenhuma posição criada pelo navegador.** Não
soma valores em moedas diferentes, não altera
histórico e não redefine margem nem alavancagem.
Um valor positivo continua sendo condicional e
não equivale a resultado realizado.

## Segurança do importador

O validador puro de Node/navegador
`CIAEngine.validatePaperPartialRiskReport` exige
**exatamente** as chaves públicas do retorno D398,
sem campos privados ou extras. Só aceita estados
de abstenção definidos pelo motor, ou
`conditional_closed_after_observed_partial_derisk_proxy`.

Exige booleans estritos:
- `liquidation_checked_before_same_tick_fill` e
  `partial_derisking_applies_after_explicit_fill_only`
  devem permanecer verdadeiros;
- `orders_sent`, `net_pnl_verified`,
  `venue_liquidation_verified`,
  `approved_for_live_use` e todas as demais flags
  de segurança do D398 devem ser **false**;
- em qualquer estado de abstenção, a referência
  líquida **é obrigatoriamente null**;
- no estado condicional, a referência deve ser
  texto decimal finito, com limites, e precisam
  existir fills e ticks contabilizados; não pode
  haver terminal discreto;
- contagens, alavancagem e flags de veto têm
  limites exatos. JSON com `NaN`, campos extras,
  flags de autorização ou indicador de lucro real
  é rejeitado sem substituir o relatório anterior.

A implementação atualiza o DOM com `textContent`,
não usa `innerHTML`, APIs privadas ou execução de
scripts importados. O arquivo entra **somente na
memória desta sessão**; nunca é persistido em
`localStorage`, enviado à VPS ou exportado com
os cenários locais. A importação pré-existente de
N50, watchlist, prospectivo e backup continua
isolada e inalterada.

## Validação

```bash
python -m unittest discover -s tests \
  -p 'test_j5_partial_risk_import_d399.py' -v
```

O teste Python verifica DOM, labels acessíveis,
identificadores únicos, status visível, CSS móvel,
ausência de rede, separação do estado persistido
e integração com o importador existente. Node
valida um relatório condicional 50x, relatório
veto por possível liquidação, ausência de margem
e ausência de reconciliação, além de numerosas
entradas malformadas ou inseguras. A CI padrão
valida o app no Chrome/PAPER e o restante
do projeto em Linux/Windows.

## Pendências de produto

D399 **não cria o arquivo JSON por conta própria**:
a simulação J3 ainda precisa de um orquestrador
PAPER read-only que produza o retorno D398 de
forma rastreável. Não há conexão com Bybit,
identificação automática da posição, execução
de ordem, cálculo de liquidação real, autorização
para capital real ou novo serviço.

Próxima tarefa J5/J6: ligação autenticada a uma
API local read-only do relatório de risco, com
origem explicitamente demonstrada e sem expor
contas/preços privados. J1 N50 e J2 feed
contínuo seguem gates independentes.
