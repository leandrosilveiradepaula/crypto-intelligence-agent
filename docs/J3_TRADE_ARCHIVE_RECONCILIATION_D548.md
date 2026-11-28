# D548 — validação isolada de arquivo diário de negócios Bybit

## Contexto e decisão técnica

D547 integrado e instalado em c227a797fa3a44e3762b84c996229fe8a8bcb3ab.
Campanha trade-5m-365 de 27/11/2026 17:05:43–19:00:27 UTC terminou
exit 1, retCode 10006, sem cabeçalho de quota, sem retry. Em 28/11/2026
14:05:46 UTC, coverage-365 offline terminou com 1.990.120/5.245.798
velas trade-5m, ganho 408.080 desde baseline e 24.280 no lote interrompido,
faltam 3.255.678. Funding 648/648 consultas, mark-5m 0/5.587.323
no plano 390d. Automação de acompanhamento desativada; issue #4,
comentário 7240419064. Não recomeçar coleta após bloqueio.

Fontes: documentação oficial de negócios
https://bybit-exchange.github.io/docs/v5/market/recent-trade aponta para
https://www.bybit.com/en/derivative-activity/history-data; catálogo oficial
https://public.bybit.com/trading/BTCUSDT/ lista CSV.gz diários de negócios.
A disponibilidade de candles de trade e mark 5m para toda a coorte/período
não está demonstrada pelo portal. Negócios arquivados não são mark price.
A reconstrução pode divergir do OHLCV/turnover REST (ordem, exclusões,
precisão, gaps). Não presumir equivalência ou direitos de uso, nem usar
outro endpoint como forma de contornar uma restrição de quota.

## Entrega candidata (issue #771)

`crypto_intelligence_agent.j3_trade_archive_reconciliation_d548` recebe
um CSV diário local e referência ClosedCandle D528. Esquema candidato
exige timestamp decimal em segundos, symbol, size, price e trdMatchID;
colunas adicionais não participam do cálculo. Ainda NÃO foi validado
contra bytes de um arquivo oficial real. Agrega em Decimal OHLC, volume
base e soma price*size em quote nos 288 intervalos UTC de 5m. Não presume
ordem do arquivo; empate de timestamp nos extremos com preços diferentes
invalida match daquela barra. Não preenche vela sem negócio nem corrige
arredondamento. Rejeita trade duplicado, símbolo/horário inválido, dados
não finitos, schema/linha inválidos e referências com proveniência
diferente. Conta pares exatos, campos divergentes, ausentes e ambíguos;
exige todos os 288 pares para exact_day_match. Mesmo esse resultado não
aprova equivalência geral.

`scripts.reconcile_j3_trade_archive_d548` compara somente um arquivo local
já autorizado, privado 0600, com nome SYMBOLYYYY-MM-DD.csv.gz, em
diretório privado 0700, owner não-root. Exige flags explícitas de pesquisa
e direitos, plano D528 real congelado e dia dentro do contrato. Lê
SQLite existente por read_window sob lock owner, sem gravar candles.
Gzip em streaming sem extração, tamanho comprimido <=512 MiB, expandido
<=2 GiB, linha <=4096 bytes, até 3 milhões de negócios/IDs por dia
(limite de memória; arquivo maior deve ser recusado, não truncado).
SHA256 do arquivo e do plano; saída agregada sem preços, IDs ou dados
brutos. Exit 0 = igualdade exata do dia; 2 = divergência/gap; 1 = falha.
Nenhum GET, importação para D528, replay, alteração de perfil ou serviço.
Sem alteração da unidade/broker/instalação VPS; CLI apenas candidato de
pesquisa independente. Não habilitar downloader ou operar após 10006.

## Aceite

Testes sintéticos para ordem reversa, precisão submilissegundo, empate
de extremos vs interior, gaps, volume/turnover, duplicidade, schema,
limites e gzip corrompido. CI e revisão do SHA exato antes de integrar.
Próximo gate real, separado: disponibilidade e direitos do arquivo local,
comparação em dia completo já existente com liquidez representativa,
vários contratos e dias em estratos pré-definidos; conferir o volume e
formato reais. Igualdade de amostra não prova cobertura geral, trajetória
de mark, funding, liquidação, mercado histórico completo ou OOS.
A falta de mark histórico continua bloqueando D547 anual 5m; não
repetir anual 1h. Não aprovar estratégia por esta entrega.
