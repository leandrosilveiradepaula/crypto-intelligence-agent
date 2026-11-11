# J1/D286 — Top 50 provisório pelas 24 velas 1h fechadas atuais

## Por que esta mudança

Em 11/11 a varredura pública D279 encontrou 370 candidatos técnicos de futuros perpétuos lineares USDT. Somente **44 dos 50** instrumentos no grupo histórico D264 continuavam nesse conjunto, portanto NÃO podemos simplesmente passar max-assets 2 para 50 no serviço existente. D281 tinha 24h históricas para 370, mas eram de 06/11, não representavam ranking corrente.

## Algoritmo reutilizando funções existentes

O owner-only **scripts.run_j1_auto_closed24h_rank_once** executa apenas Bybit V5 GET, sem escrita, rede privada, conta ou ordens. Flags obrigatórias: --allow-public-network e --confirm-region-and-personal-research; POSIX não-root; início HH:01..HH:02 UTC.

1. Varredura paginada íntegra do catálogo linear (D279), filtros automáticos de tipo perpétuo, Trading, USDT e vetos TradFi. Não presume USDT como certificação de cripto.
2. Admite de 50 a 400 candidatos com orçamento de 450 GETs. Estima limite de 2 segundos por GET ANTES de iniciar os klines; exige conclusão até HH:15, sem qualquer retry em erro/rate limit/10006.
3. Obtém exatamente 24 velas **1h fechadas** da mesma janela UTC para cada candidato. Reutiliza validadores de OHLCV/turnover Decimal, sem usar rolling ticker turnover24h. Mantém só valores em memória e não recria D256.
4. Varre o catálogo novamente após toda a captura. Só segue se os candidatos e as contagens de exclusões forem iguais antes/depois, com relógio dentro da janela.
5. Reutiliza rank_auto_candidates_closed24h_offline, ordena por turnover quote USDT e publica contagem, digest e status sanitizado. Só revela símbolos de instrumentos públicos mediante --include-public-symbols; jamais retorna preços ou dados privados.
6. A saída é SEMPRE research-only, marketwide_top50_verified=false, current_crypto_identity_independently_verified=false, live_trading_authorized=false, orders_sent=false. Falta de candles, drift, quota ou prazo estourado → abstenção sem ranking.

## Testes

tests/test_j1_auto_current_closed24h_once.py contém fake de catálogo + 50 séries 24h (52 GETs simulados), ranking por turnover e digest, duplo catálogo, short listing sem imputação, drift de membership, rate limit sem retry, deadline UTC, budget >400 e no-optin zero IO. CI Linux/docs, Windows e Chrome/PAPER, revisão e merge sem deploy.

## Limites de produto

É o ranking das 24h atuais **no conjunto provisório filtrado**, não prova de identidade cripto independente nem a troca dinâmica e persistente do universo. Não muda o timer M1 N2 em produção ou seu DB, nem autoriza ordens. A etapa seguinte deve persistir 370 séries recentes num journal de epochs/churn seguro e conectar o Top 50 validado. Não repetir os dossiês manuais de moedas. Se o tempo de coleta real ultrapassar HH:15, o processo aborta sem resultado; nunca inventa candles ou PIT.
