# J2/D308 — Watchlist descritiva N50, somente observação causal

## Problema e escopo

A J1/D306 retomou a coleta N50 com epoch nova; a janela de 24 fechamentos e a rotação ainda precisam de prova real. J2/D300 já disponibiliza **24 candles fechados por ativo** auditados, com retornos, ATR de 14 barras, turnover em USDT, rompimento relativo aos 23 candles anteriores e contexto BTC. D308 **não cria coletor, estratégia, ordens, entradas, PnL, ML ou outros dados**: apenas compõe uma lista descritiva verificável sobre D300 e a expõe como projeção privada.

## Contrato

- Fonte única: `audit_private_n50_research(..., include_private_symbols=True)` de D300, após checagem DAC owner, digest, SQLite, manifesto PIT, recibo e contiguidade 50 × 24h.
- Revalidação integral do contrato sanitizado D300: schema/status, 50 ativos distintos com sufixo USDT, 24 fechamentos, UTC, digest, BTC, força relativa exata, monotonicidade da ordenação, Decimal nativo textual finito, ausência de autorização de sinais/ordens e de writes.
- **Observação de alta**: fechamento acima da máxima das 23 barras anteriores, retorno observado 24h superior ao do BTC, turnover da última barra ≥ média das 23 anteriores e turnover total positivo.
- **Observação de baixa**: fechamento abaixo da mínima das 23 barras anteriores, retorno observado 24h inferior ao do BTC, mesmo filtro de intensidade de volume.
- Ranking de alta: maior força relativa vs. BTC; depois maior intensidade de turnover; depois maior turnover fechado; desempate lexical. Baixa: menor força relativa (mais negativa), mesmo desempate. No máximo cinco por grupo, sempre contagens completas.
- `ATR` e variação de 24h somente **contexto descritivo**, não calibração de stop, liquidação, alavancagem ou expectativa de ganho. Critérios são heurísticos fixos para observação, **sem otimização nem validação histórica de alpha**.
- Padrão do relatório sem símbolos; saída de símbolos requer `include_private_symbols=True` e confirmação explícita, em contexto owner.
- Resumo nunca contém preços brutos, identidades se não opt-in, endpoints, credenciais ou comandos. Não há chamada de rede nem writes.
- Recusa integral, sem listas parciais, se origem incompleta/corrompida/obsoleta, BTC ausente, volume desconhecido em dimensão obrigatória de ordenação, números inválidos, autorização de negociação inesperada, ordenação inconsistente ou clock irregular. Falta isolada de razão de turnover num ativo não fabrica volume; o ativo não recebe classificação.

## Aceite técnico

`tests/test_j2_n50_descriptive_watchlist.py` cobre ordenação/direção/desempate, abstenção, privacidade, ausência de sinais, 50 ativos, 24h, sufixo USDT, duplicação, mercado não certificado, origem, UTC, Decimal, volume/ATR, guardas de rede/escrita, e ausência de ordens. Rodar testes focalizados e suíte afetada em Linux e Windows, além de Chrome/PAPER já exigidos pelo repositório. CI verde + revisão + SHA exato antes do merge.

## Limites operacionais

- Não liberar live, alavancagem 50x ou qualquer posição. `approved_for_signals=false`, `approved_for_live_use=false`, `marketwide_top50_verified=false`, `orders_sent=false`.
- Registros são da amostra N50 privada selecionada, não um censo do mercado.
- D308 não altera systemd, código de coleta N50, base SQLite, VPS, credenciais nem orçamento.
- J1 #429/#319 continuam abertas até a prova real de supervisão 24h, rotação após 36h e identidade crypto-only independente.
- Só avaliar performance de regras em J3 depois de separar amostra, períodos de decisão, custos, intrabar e validação fora da amostra. Não confundir lista de observação com uma recomendação ou retorno esperado.

**Decisão D308:** priorizar pesquisa de observações causais aproveitando a coleta existente, em vez de esperar o fechamento de J1 ou fabricar evidência de mercado, preservando bloqueio de trading real.
