# Estado operacional — checkpoint WU8 em desenvolvimento, 2026-10-25 UTC

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
- WU9 #30 em desenvolvimento: branch `feat/j1-kraken-fail-closed-universe`, seletor puramente offline com registro externo verificável de bases cripto como argumento obrigatório, exclusões categorias não cripto e volumeQuote USD Decimal. Sem PR/CI/merge confirmados até verificação.
- J2–J7 issues #3–#8 dependentes; sem motor de estratégias, backtest financeiro, VPS em produção ou operações reais.

## Próxima ação concreta
1. Conferir estado vivo de main, issue #30 e PRs. Validar seletor Kraken WU9 com testes offline para tokenizados, categorias faltantes, duplicatas, volumeQuote e limites; abrir PR, conferir revisão/CI/SHA e merge seguro sem produção.
2. Não executar nova sondagem live desnecessária: evidência de taxonomia já existe na run 40199111677. Não assumir universo Top50 real sem registro crypto-only confiável e avaliação de cobertura histórica.
3. Depois da WU9, especificar fonte/verificação e versionamento do registro de ativos criptográficos (não presumir que PF_ e category/tradfi bastam); criar trabalho subsequente de adaptador Kraken read-only reutilizando storage/backfill apenas com contratos financeiramente coerentes.
4. Atualizar URLs de PR, SHAs, testes e próximo passo no GitHub; manter J1 aberta até aceite dos dados, sem ordens reais. Não repetir GET Binance que retornou HTTP451 nem tentar contornar política.
5. Se usuário pedir "gere prompt para novo chat", entregar continuidade completa com repositório, regras, decisões, jornada, evidências, issues/PRs/SHAs, testes e próxima ação autorizada.
