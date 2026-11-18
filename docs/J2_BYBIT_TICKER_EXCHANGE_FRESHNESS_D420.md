# J2/D420 — saúde da cotação depende do relógio da exchange

## Erro observado na VPS

Uma sessão real D418 de 62,107 segundos da Bybit (código main
`1322f17e207962080bac5605ff33f1d0f3272e22`, job VPS
`5065ef8a790f4e3dbac43f820d7293da`) processou 12.006 cotações,
reconheceu 50 instrumentos e registrou os dois ping/pong esperados, sem
reconexões. A mesma amostra trouxe:

- `last_fresh_quote_count=49` no resumo do livro de tickers D385/D386;
- `fresh_distinct_contracts_at_end=45` no observador causal D390/D416;
- 5 contratos anteriormente elegíveis expirados por horário da exchange.

**A diferença é um problema de classificação, não prova de falha da
Bybit.** O livro D385 considerava `now - received_at_ms <= 3.000`,
enquanto o observador D416 já comparava a hora gerada na exchange.
Uma mensagem que chega à VPS recentemente pode conter um timestamp
da exchange anterior e não deve ser declarada preço fresco.

## Correção e comportamento

`BybitPublicTickerBook.current()` agora exige, **ao mesmo tempo**,
idade de recepção dentro do limite, idade da exchange dentro do mesmo
limite, ambas não futuras em relação à consulta e profundidade
bid/ask positiva. Se uma das provas falhar, retorna `None` sem
fabricar um preço. O resumo `sanitized_report`, usado no contador
`last_fresh_quote_count` do supervisor, passa a compartilhar o
mesmo conceito causal de frescor final. Não altera o JSON de contrato,
nem o limite de 3 s, nem o comportamento do decodificador
snapshot/delta, reconexões, ordens ou posições PAPER.

O dado da exchange ligeiramente futuro (dentro do intervalo aceito
pelo parser) pode ser armazenado com cautela pelo decodificador, mas
**não deve ser oferecido como cotação atual antes da hora do evento**.

## Testes e limites

Regressões em `tests/test_bybit_public_ticker_state_d385.py`:

- timestamp de exchange `t-2.500ms` entregue à VPS no instante `t`:
  a cotação expira para consulta em `t+501ms`, embora a idade local
  de recepção seja apenas 501 ms;
- timestamp futuro `t+500ms`: frame é decodificado mas não há
  cotação utilizável até `t+500ms`;
- o relatório de saúde recusa computar as cotações acima como frescas
  precocemente.

Executar também os testes D386, D405, D418, D410/D411 de proteção PAPER
e full CI Linux/Windows/Chrome. Pilotos reais anteriores são
**evidência da falha**, não evidência de que o novo código já foi
implantado; não instalar serviço como parte dessa correção.

Feed público continua read-only, não homologado 24×7, sem autorização
para sinais/ordens reais. Custo adicional R$ 0,00.
