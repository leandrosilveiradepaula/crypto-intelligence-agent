# J1/TOP50 — universo básico completo com 24h UTC fechadas (D249)

## Evidência de origem: VPS, 6 de novembro de 2026
O Product Owner executou no host `srv1319424` três verificações reais: SQLite histórico já existente íntegro (37.470 candles; 51 ativos distintos; 50 no último PIT; 2 PITs, mas nenhuma sequência final consecutiva), catálogo/tickers Bybit (930 instrumentos, 822 contratos com filtros técnicos `Trading+LinearPerpetual+USDT quote/settle` e 822 turnover móvel numérico), e teste de 50 candidatos (24 velas UTC fechadas por candidato, 1.200 candles; 52 GETs, 10/10 de interseção Top10 dentro dessa amostra). Nenhum dado real do último teste foi salvo. A validade de identidade independente e a cobertura dos outros 772 contratos **não** foram provadas.

## Objetivo técnico
`scripts/audit_bybit_marketwide_closed24h.py` implementa recenseamento integral **da amostra básica de contratos**. Uma observação registra a hora UTC de fechamento depois de 30 segundos, o censo completo de instrumentos em uma página terminal (`category=linear`, <=1000 registros) e o fingerprint da lista de contratos tecnicamente elegíveis. Um pequeno lote (padrão 60, máximo 120) baixa as últimas 24 velas 1h **fechadas para cada contrato elegível ainda não concluído** e valida sequência reversa estrita, OHLC positivo/coerente, volume base e turnover quote Decimal positivo/não-negativo, forma e identidade do contrato; não consulta API de ordens nem conta.

- Um cliente `BoundedBybitPublicClient` pré-existente impõe 1 GET a cada pelo menos 2 segundos; limite por invocação é no máximo **121 GETs** (1 catálogo + 120 candles), sem retries. A mesma janela UTC é reaproveitada nas execuções seguintes, com prazo máximo de 48 horas, sem avançar silenciosamente para outra hora e sem inventar carimbo PIT.
- Um novo banco privado `j1-marketwide-closed24h.sqlite` armazena **somente a pesquisa nova**, separado do histórico privado já validado. Pasta 0700, banco e lock 0600, `flock` de escritor único; transação por ativo com 24 linhas atômicas, replay e `PRAGMA integrity_check` antes da próxima coleta. GET/validação falha: nenhuma transação parcial daquele ativo. Reexecução não reconsulta candlesticks já completos; pode repetir somente o catálogo para comprovar que a lista básica não mudou.
- O JSON mostrado no console contém **contagens, fase de falha, janela UTC e digest**, não nomes de contratos, preços, URLs, segredos nem payloads; símbolos e OHLCV ficam apenas no SQLite do owner. O hash de ranking final resume o **Top50 entre contratos básicos**, calculado pela soma Decimal do campo `turnover` cotado em USDT de 24h UTC fechadas. Não deriva o ranking do ticker móvel.
- Estados `basic_market_24h_batch_partial_unverified` (exit 2), `basic_market_24h_closed_rank_complete_unverified` (exit 0) e `abstain` (exit 2). Falhas de censo, esquema, drift, relógio, integridade, erro HTTP/quota/10006 ou expiração **não provocam retry automático**.
- `marketwide_top50_verified=false`, `crypto_identity_independently_verified=false`, `continuous_collector_verified=false` e `orders_sent=false` invariantes. O censo básico não distingue com certeza independência de identidade cripto, possíveis instrumentos não cripto, nem substitui backtest e continuidade operacional.

## Execução: somente após CI, código conferido, pesquisa pessoal/região autorizadas
Em checkout de pesquisa íntegro, como usuário `cia-probe`, com diretório pai de pesquisa próprio 0700:
```bash
python -m scripts.audit_bybit_marketwide_closed24h \
  --directory /home/cia-probe/agent/j1-marketwide-closed24h-20261106 \
  --max-contracts 120 \
  --allow-public-network --allow-private-storage \
  --confirm-region-and-personal-research
```
Execute uma invocação de cada vez. O código **não** instala systemd/timer e não abre conexão de negociação. Repetir o comando somente após verificar que o estado é parcial, não após abstain/falha. Se o catálogo mudar ou o prazo expirou, não apagar o banco nem reutilizar esse escopo como novo PIT.

## Testes, aceite e limitações
Suíte `tests/test_j1_marketwide_closed24h.py`: 822 contratos ×24 candles em sete lotes, 829 GETs sintéticos (822 candles +7 catálogos), recuperação após falha, replay idempotente, corrupção persistida, drift, validade UTC, orçamento/owner/symlink, Decimal/ohlc e dados futuros. A CI Linux/docs, Windows/offline e Chrome/PAPER deve validar o SHA exato. O resultado live da VPS, se houver, deve ser reportado à issue #319/#502 sem prints de dados privados. **Não fechar #319 nem J1 #2** pela classificação de contratos básicos: ainda será necessária identidade crypto-only validada independentemente, ranking de todos os elegíveis e continuidade PIT/WS real.
