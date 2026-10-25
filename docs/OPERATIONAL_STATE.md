# Estado operacional — WU12 em implementação, 2026-10-25 UTC

Projeto: Crypto Intelligence Agent. Repo PÚBLICO: `leandrosilveiradepaula/crypto-intelligence-agent`.
Missão: futuros perpétuos crypto, entradas quantitativas e saídas parciais; operação manual sem ordens reais nesta fase.
Autonomia: `AGENTS.md`; não pedir "prossiga", avançar em microtarefas seguras, usar GitHub como verdade. Nenhum custo adicional (R$0), permissão sensível, deploy/migration em produção ou trade sem gate humano.

## Jornada ativa: J1 Dados — épica #2 aberta
- J0 documental concluída (issue #1, PRs #10/#11).
- WU1 #9/PR12 SHA `c9bf70c3f8429b1474a9b68cc1aeb0a3cd209193`.
- WU2 #13/PR14 SHA `f3567eb063f0b7cfeffe40169ba0b8e9fce1da96`.
- WU3 #15/PR16 SHA `9631e4445678bc4c7067964b537da924b5b89a0b`.
- WU4 #17/PR18 SHA `8fc2f75460e93ef898ae14e3c48ef0348692c857`.
- WU5 #19 continua ABERTA. PRs #20, #21 e #22 integradas; a Binance retornou HTTP451 na primeira consulta pública, run `40197499250`, sem dados; retry desativado e restrição não contornada.
- WU6 #23 encerrada, PR #24 merged SHA `76490ac8790138642f34de710c5f2e4bb2cf3d09`. Run `40198042787`: 1 GET Kraken Futures `/derivatives/api/v3/instruments` HTTP200, 231 instrumentos, 213 candidatos PI_/PF_ **heurísticos**, 641ms, sem auth/custo.
- WU7 #25 encerrada, PR #26 merged SHA `effdca1c0464157ed7b297d942d98f81c654c93d` e #27 correção de entrypoint merged SHA `1c982eed74516ac70407c49ff5d2c98c2f88ee5b`. CI pós-merge 99 testes offline (run 40198730576). Primeiro smoke `40198556326` falhou com ModuleNotFoundError antes de GET; corrigido. Segundo smoke `40198745112` SUCCESS, UTC `2026-10-25T13:41:20Z`, 3 GETs Kraken HTTP200; 231 instrumentos/tickers, BTC `PF_XBTUSD` `tag=perpetual`, `volumeQuote=331016603.1374` (amostra), `pair=BTC:USD`, `type=flexible_futures`, `contractSize=1`, `tickSize=1`. 3 candles BTC com campos OHLC, `time`, `volume`, `more_candles`. Ex. `PF_AAPLXUSD` tokenizado igualmente `flexible_futures` e `tradeable=true`; prefixo/type NÃO são filtro crypto.
- WU8 #28 encerrada: PR #29 merged SHA `7e9b73bf3b5b19f5a56288326784d2280121c9d9`, CI pós-merge 102 testes offline (run 40199094267). Run `40199111677` SUCCESS, HTTP200, 231 instrumentos; `category=xStocks` para PF_AAPLXUSD, mas `tradfi=false`, igual BTC/ETH; BTC/ETH categoria ausente. Logo `tradfi=false` não é filtro crypto-only.
- WU9 #30 CONCLUÍDA, PR #31 merged SHA `82236f2ee5345277fb3ffc92391594fb9d01fa3f`, CI pós-merge run 40199470161 SUCCESS (115 testes offline, compileall, 10 docs). Seletor puro de Kraken exige `verified_crypto_bases` externo `frozenset` versionado, filtra xStocks e outras classes não cripto, volumeQuote positivo Decimal em USD, contratos ativos PF_/ticker perpetual; N até 50 variável. **Registro externo ainda não existe e nenhum universo real Top50 foi calculado.**
- WU10 #32 permanece ABERTA para obter fonte/licença de registro REAL: PR #33 merged SHA `6be53f170edb81656d43d8ebf6e25c4ecdaaa9ed`, CI pós-merge run 40200232080 SUCCESS (**135 testes offline + compileall + 11 docs**). Entregue manifesto SHA256 e referências independentes, histórico append-only/antiviés temporal, mas sem base real aprovada. CoinGecko/CoinPaprika free não dão direitos comerciais gerais; não importar dados silenciosamente.
- WU11 #34 encerrada: PR #35 merged SHA `a93f967cc4c5127e492f2878b62ccc9ce5f76428`, CI pós-merge run 40200619598 SUCCESS (149 unittest offline, compileall, 11 docs). `kraken_candle_validation.py` valida OHLC Decimal, UTC-ms, candle fechado, gaps sem inferir base_volume/quote_volume; sem internet ou armazenamento.
- WU12 #36 ativa: branch `research/j1-kraken-volume-units`. Script de pesquisa opcional e limitado a 2 GETs Kraken, 27 barras horários no máximo / 24 fechados e ticker BTC; unit_proof=false imutável. Ainda não declarar PR/CI/merge ou run de diagnóstico antes de confirmação.
- Documentação adicional `docs/CRYPTO_REGISTRY.md`: política de identidade, revisão, uso restrito interno, esquema e antiviés temporal. Sem consumo de API de terceiros na WU10.
- J2–J7 issues #3–#8 dependentes; sem motor de estratégias, backtest financeiro, VPS em produção ou operações reais.

## Próxima ação concreta
1. Conferir main e issue #36, concluir testes/PR/revisão de WU12, CI offline no SHA exato; integrar via merge apenas se gates verdes e sem produção.
2. Acionar uma única sondagem owner-only `/probe-kraken-volume-v1` na issue #36 após merge. Registrar URL do run, UTC, HTTP e agregados sanitizados; não inferir base_volume/quote_volume ou liquidez intrabar diretamente de um teste.
3. Pesquisar documentos oficiais Kraken sobre unidades de contratos/lot de PF_XBTUSD e de candles; se persistir ambiguidade, registrar gate de normalização e não liberar backtest/captura com volume fictício.
4. WU10 #32 permanece aberta por registro de ativos/licenças; manter #2 J1 aberta, Binance #19 bloqueada HTTP451 e J2 dependente até homologação de dados. Sem gastos, ordens, deploy ou secrets. Não repetir GET Binance que retornou HTTP451 nem tentar contornar política.
5. Se usuário pedir "gere prompt para novo chat", entregar continuidade completa com repositório, regras, decisões, jornada, evidências, issues/PRs/SHAs, testes e próxima ação autorizada.
