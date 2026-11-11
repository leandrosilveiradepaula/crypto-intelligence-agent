# J1/D274 — CLANKERUSDT: resolver o ativo subjacente sem promover o Top 50

Revisão de pesquisa em **11/11/2026 UTC**, issue #517, #319.

## Provas primárias verificadas

1. [Bybit Learn, 29/04/2025](https://www.bybit.com/en/learn/ai/what-is-clanker-tokenbot) identifica explicitamente **tokenbot (CLANKER)**, diz que o protocolo funciona na Base e que a Bybit listou o perpétuo **CLANKERUSDT**, até 20x. É uma afirmação nominal da venue sobre seu próprio instrumento.
2. [Binance Futures, 12/11/2025](https://www.binance.com/en/support/announcement/detail/15f01e2861ac46e2b698212cb220f4d7) identifica o subjacente **tokenbot (CLANKER)** e publica o endereço **0x1bc0c42215582d5a085795f4badbac3ff36d1bcb**, com liquidação USDT para seu próprio contrato CLANKERUSDT. Esse anúncio é evidência primária independente sobre o token, não autenticação da negociação na Bybit.

A referência canônica *de pesquisa* `coingecko:tokenbot-2` permanece hipótese, não se confunde com `coingecko:clanker`. O anúncio Binance evidencia o contrato **dela** e o token; a fonte Bybit comprova a identidade nominal de **seu** perpétuo. Não afirmar que a Binance certificou o instrumento Bybit.

## Gate temporal e de classificação

As páginas foram publicadas antes da janela congelada em 06/11/2026, mas a revisão documental ocorre em **11/11/2026**. Logo o histórico **não ganha autenticação PIT retroativa**, mesmo que exista prova antiga no domínio público. Manter a categoria da D261 `ticker_collision_unresolved` até dossiê autenticado em sua própria janela; **não** resolver a colisão pela simples adição de uma pista sem exame de contratos e proveniência. O módulo D274 oferece evidência da hipótese favorecida, e **não** altera `research_category`, `NEGATIVE_EVIDENCE`, `eligible_top50` ou `marketwide_top50_verified`.

A execução é estritamente offline: novos registros estáticos de fontes públicas, testes unitários de origem/domínio, URL sem credenciais, endereço de 40 hex, cronologia, concorrência com a categoria histórica e nenhuma operação financeira. A alteração no validador de URLs aceita apenas Bybit Learn/Announcements como fonte da venue e Gate/Binance announcements como segunda fonte; não admite domínios arbitrários.

## Próxima ação

Utilizar a posição real do símbolo na fila de contratos com 24 horas fechadas da D256 e a lista D264 de indicadores TradFi **somente na VPS owner**. Se CLANKER competir pelo corte do 50º, abrir revisão independente temporal e de endereço, sem assumir que já era aprovado em 06/11. Não fazer nova coleta nem ativação de trading.

## Integração ao ranking efetivo sem novo coletor

O módulo puro `j1_top50_research_priorities.annotate_raw_rank_research` consome **somente o ranking que já foi conferido pelo replay D256**. O `j1_top50_private_pressure.audit_private_top50_pressure` agora acrescenta ao seu resultado `raw_rank_research_annotations` com contagens das categorias antigas e das pesquisas primárias D273/D274.

- Conta, sem aprovar: `identity_unresolved`, `ticker_collision_unresolved`, candidatos hipotéticos, vetos TradFi documentados e interseções com as duas fichas de pesquisa primária.
- `primary_crosswalk_not_pit_count` é explícito; a presença das fontes **não muda** `positively_reviewed_crypto` (continua vazio).
- Por padrão **nenhum símbolo aparece** no relatório. A opção owner explícita `--include-public-symbols`, já existente, também exibe categoria de pesquisa dos primeiros 50 contratos do ranking bruto, somente no terminal privado. Nenhum valor de turnover sai.
- O ranking bruto, que inclui ativos TradFi, **não** é o Top50 cripto elegível nem substitui a fronteira de pesquisa filtrada D264. Não usar contagens para inferir os 10 símbolos privados unresolved.

Novos testes unitários cobrem casos mistos DGAI, CLANKER, FARTCOIN, LIT, BZ, desconhecidos e entradas inválidas; teste SQLite do bridge comprova que as categorias ficam disponíveis na leitura owner-only, sem rede ou atualização do banco.
