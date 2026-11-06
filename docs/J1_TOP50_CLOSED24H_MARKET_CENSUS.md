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


## Evidência real D250 e causa ausente

Na execução real owner de 06/11/2026 a varredura parou após 6 GETs, quatro contratos completos e 96 velas persistidas; o quinto GET falhou no estágio kline com `provider_ret_code=null`. Uma auditoria read-only subsequente confirmou 4 contratos íntegros, nenhum parcial, escopo de 822 e SQLite íntegro. O código antigo suprimia a categoria detalhada da exceção, portanto **não existe prova se houve falta de 24 candles, falha de transporte, HTTP, schema ou OHLCV**. D250 acrescenta `failure_category` e `failure_code` com códigos estritamente allowlisted no JSON para a próxima ocorrência; jamais logar mensagem arbitrária, símbolo ou payload. Não repetir automaticamente GET em erro nem zerar histórico. Uma ausência real de 24h implica abstenção e decisão explícita de critério de elegibilidade, não exclusão silenciosa de membro.


## D251 — lexical Decimal científico, com validação fail-closed

A re-prova real D250 retornou `invalid_candle_decimal` em `kline` após 2 GETs, mas não registrou qual dos seis campos causou rejeição nem seu texto. Isso pode decorrer de notação científica textual, porém **a hipótese não foi confirmada**. O parser D251 aceita Decimal TEXT ASCII `1.2E-8` e `0e-8` de forma exata, limitada a 30 dígitos inteiros, 24 fracionários, expoente absoluto até 48 e no máximo 96 caracteres; continua rejeitando NaN, infinito, negativos, números com sinal ou representações malformadas. OHLC e volumes permanecem sujeitos aos mesmos gates. O texto do provider fica inalterado no armazenamento owner-only e é revalidado no replay; o console informa apenas `invalid_decimal_field` limitado a seis nomes fixos quando `failure_code=invalid_candle_decimal`. Não expor o valor bruto, não manipular identidade ou excluir um contrato para completar o ranking. Realizar no máximo um lote `--max-contracts 1` depois de CI/merge, só para classificar resultado subsequente.


## D252 — interoperabilidade catálogo e URL de kline

O censo real no SHA D251 avançou a 20/822 e 480 velas, então parou com `invalid_kline_window` local após 16 GETs. O builder de URL para klines exige forma de símbolo `[A-Z0-9]{2,24}USDT`, mais estreita que os contratos técnicos admitidos por `_catalog`. A correção D252 harmoniza o **formato de requisição** com bases de 1..28 ASCII alfanuméricas mais USDT (símbolo completo de 5..32 caracteres). Isto não torna uma base `crypto-only`, não estende a prova a mercados além da Bybit e não garante que o 21º símbolo tenha sido o causador sem novo teste. Continua proibido aceitar caracteres especiais, saltar membros incompatíveis ou recomeçar janela sem aprovação; os 20 contratos salvos ficam preservados.


## D253 — survey integral sem imputação de histórico inexistente

Se um contrato retorna **0..23 candles UTC 1h fechados contíguos mais recentes**, a execução armazena em `incomplete` do banco privado (não no histórico legado): símbolo interno, `launchTime` do catálogo apenas como hint, quantidade observada, linhas financeiras reais validadas (inclusive 0) e digest. Na próxima chamada, `PRAGMA integrity_check`, fingerprint de universo e replay do short são exigidos antes de novos GETs. O contrato permanece explicitamente no denominador básico, porém sem 24h completas; não se inventa turno de cotação, não se aplica total zero e não se classifica no Top50 global. Dados com buracos internos, preço inválido, 24h incompletas com horários inconsistentes, mensagem inválida ou provider error 10006 interrompem. O censo pode terminar com `basic_market_24h_survey_complete_with_incomplete_unverified`, cujo exit 0 significa somente que todos os contratos foram **inspecionados**; `full_basic_contract_24h_ranking_complete=false`, `marketwide_top50_verified=false`. O ranking `top50_complete_subset_digest_sha256` serve somente para pesquisa não homologada. A janela UTC 2026-11-06 13:00, 822 candidatos e validade de 48 horas seguem congeladas. É proibido inferir listagem nova a partir de short sem prova independente do launchTime e data.
