# J2/D416 — diagnóstico de frescor real do N50 público Bybit

## Problema confirmado por prova na VPS

Em 18/11/2026 UTC, uma sessão D406 owner de 20 s (22,002 s totais)
usou o código já integrado SHA `73105a951917c3b32db7259f89bea772f071e8ea`.
A assinatura Bybit foi confirmada, 2.810 ticker callbacks pós-ACK foram
aceitos, 50/50 contratos tiveram ao menos uma cotação elegível, sem
`conflicting_replay`, porém somente **39/50** ainda estavam frescos ao
final (3.000 ms). A CLI encerrou com código 2, de forma correta. Isso
não demonstra falha de subscribe e não é cobertura simultânea.

## Implementação

D390 já tem um observador de mercado de memória finita, por sessão.
D416 amplia esse observador **apenas quando**
`diagnose_public_freshness=True` (D405 ativa; D410 não ativa, preservando
o JSON estrito da UI J5). O sumário D405/D406 traz somente contagens,
nunca símbolo, preço, identificador de posição, payload de WebSocket ou
conteúdo do diretório owner. As quatro categorias a seguir são **disjuntas**
e somam `requested_contracts`:

1. `never_received_validated_quote_contracts`: nenhum callback de
   ticker válido pós-ACK foi entregue para o contrato **nesta sessão**.
   Um snapshot em quarentena pré-ACK não é callback.
2. `received_no_eligible_quote_contracts`: callback validado entregue,
   mas nenhum satisfaz simultaneamente escopo PIT, idade de
   exchange na recepção <= 3 s e profundidade bid/ask positiva.
3. `eligible_quote_expired_at_end_contracts`: contrato teve quote
   elegível anteriormente, mas seu timestamp **da exchange** está
   além de 3 s no encerramento, não apenas a hora local de chegada.
4. `fresh_contracts_at_end`: pelo menos uma quote elegível e cujo
   horário da exchange ainda tem idade entre 0 e 3 s no fim.

`validated_quote_contracts` é a soma das categorias 2, 3 e 4;
`received_distinct_contracts` é a soma das categorias 3 e 4.

Como causa potencial sobreposta, o relatório inclui:
`exchange_lagged_quote_callbacks` e
`exchange_lagged_quote_contracts`: callbacks decodificados para os
quais o dado já tinha mais de 3 s de idade exchange→recepção. Não
representam todos os frames de rede rejeitados antes do callback.
A documentação não atribui causa a um contrato e **não prova** que os
11 anteriores deixaram de negociar, só que o limite de frescor do
observador não estava satisfeito.

O novo booleano
`freshness_evaluated_by_exchange_timestamp=true`
torna explícita a escolha do relógio. O D390 também usa a idade real
da exchange, e não só do recebimento, ao verificar a cobertura atual
para o modo `require_complete_fresh_scope_for_paper`; a política de
proteção D411 por ticker próprio e o gate fail-closed permanecem intactos.

**Reconexão:** todas as categorias, identificadores internos e contagens
voltam a zero. O relatório contempla somente a sessão final; frames
pré-ACK podem reconstruir snapshot após ACK, mas **não entram** no
observador nem nas cotações que acionam PAPER.

## Testes e proibições

Fixtures sem rede comprovam quatro classes disjuntas, mensagens tardias,
decodificação válida sem frescor, snapshot pré-ACK não contado, 50
ativos, isolamento em reconexão, e caso crítico em que o ticker chega
`+4 s` mas traz timestamp de exchange `+1,45 s`: elegível na
chegada, **expirado** no final `+5 s` (sem artificialmente renovar).
Testes D410/D411/J5 garantem que o novo relatório opcional não quebra
o validador estrito do aplicativo.

Comandos: `python -m unittest discover -s tests`,
`python -m compileall -q crypto_intelligence_agent scripts tests`.
O piloto owner só é elegível em tarball SHA pinado depois dos gates CI,
sem atualizar serviços J1, gravar dados privados ou instalar worker.

Limites: evidência de até 60 s é amostra, não supervisão 24×7,
marketwide Top50 certificado, backtest, stop real, book privado,
ordem financeira ou autorização para sinais/trading.
Custo adicional R$ 0,00.
