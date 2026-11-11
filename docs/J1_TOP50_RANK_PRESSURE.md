# J1/#319 — pressão de ranking por dominância, sem presumir identidade

## Problema real

O censo Bybit privado de 06/11/2026 tem 822 contratos básicos, 819 séries com 24 velas de 1h completas, 3 séries curtas e snapshot separado de 297 indícios TradFi contemporâneos. Isso **não** fornece 50 identidades cripto aprovadas nem classificação histórica PIT. Os 298 vetos de pesquisa posteriores não formam um catálogo completo de não-cripto.

Não precisamos rever os 819 instrumentos para iniciar o trabalho de identidade. Precisamos rever, em ordem decrescente de volume, os que podem entrar no Top 50; contratos desconhecidos que certamente ficam abaixo do 50º aprovado não deslocam o ranking.

## Redutor puro

`j1_top50_rank_pressure.pressure_from_closed_turnover` recebe:

- `catalog_symbols`: conjunto **exaustivo e auditado** de perpétuos USDT básicos do mesmo snapshot;
- `closed_turnover_usdt`: soma Decimal de **exatamente 24 horas UTC fechadas**, na mesma janela para cada símbolo medido, já conferida pelo pipeline D256;
- `positively_reviewed_crypto`: conjunto com identidade cripto e derivativo da venue **realmente comprovados**, não apenas referências antigas, tickers ou links propostos;
- `independently_excluded_noncrypto`: conjunto de exclusões verificadas para o instante certo, não mera ausência de indicador TradFi.

A função não autentica nenhuma dessas entradas, por isso entrega **somente um teste matemático condicional**. Se houver 50 positivos medidos, só pendências que venceriam o 50º positivo por `(-turnover, symbol)` exigem resolução imediata; qualquer instrumento não medido e não excluído continua bloqueando conclusão. Se houver menos de 50 positivos medidos, selecionar os próximos desconhecidos de maior turnover para revisão iterativa. A saída padrão omite símbolos e valores, conservando contagens e SHA256. `include_public_symbols` é opt-in para pesquisa local.

O caso de empate é determinístico e rigoroso: símbolo alfabeticamente menor precede no empate de turnover. Valores negativos, floats, NaN, Infinity, exponentes, símbolos duplicados, classificações conflitantes e membros de catálogo desconhecidos são rejeitados. Nenhum GET, escrita de DB ou envio de ordens.

## Critério de promoção futuro

Para declarar Top50 do mercado é obrigatório, além da dominância:

1. catálogo paginado integral e vigente, consistência de venue `LinearPerpetual/Trading/USDT`, exclusões verificáveis;
2. 24 velas 1h fechadas na **mesma hora UTC** por cada concorrente plausível; contratos curtos e faltantes não podem virar zero;
3. evidência de identidade positiva independente, específica do símbolo da venue e do ativo canônico, no instante PIT;
4. classificação negativa igualmente verificável e temporal, sem aplicar o snapshot TradFi contemporâneo retroativamente;
5. replay imutável de data, escopo, custos e ranking; repetição numa nova hora demonstra renovação real.

O redutor **não** é autorizador de trade. `conditional_mathematical_dominance` pode ser verdadeiro apenas com hipóteses fornecidas pelo chamador, enquanto `marketwide_top50_verified=false`, `identity_pit_authenticated=false`, `source_authenticated=false`, `trading_enabled=false` permanecem invariavelmente falsos.

## Integração prevista, sem replicar coletor

Reutilizar censo SQLite D256, snapshot privado D264, registro `CryptoRegistryHistory`, dossiês D266 e `j1_rest_incremental_owner`. Não rebaixar gates, backfill ou recriar tabelas. O próximo passo é um adaptador **somente leitura** que agregue contagens e volumes dos 819 membros, derive a fila e aceite dossiês verificáveis. Dados privados ficam na VPS; não escrever símbolo/valor financeiro ou JSON privado em issues/CI.

## Validação

Testes sintéticos: 50 positivos com unknown abaixo, rival acima, empate nas duas ordens, menos de 50 positivos, dados não medidos, positivo não medido, high-volume negativo, duplicatas, floats e NaN, nenhuma rede/ordem, digests determinísticos, flags de certificação falsas. CI Linux/docs, Windows/offline, Chrome/PAPER no SHA final; revisão, merge sem produção apenas após gates verdes.

Issue de produto: #319; diligência de identidades: #517; OPS1 independente: #429.
