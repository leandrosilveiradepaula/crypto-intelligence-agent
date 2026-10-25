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
- WU8 #28 ABERTA: branch `research/j1-kraken-asset-taxonomy`, probe Kraken de 1 GET para observar `category`, `tradfi`, `tags` em BTC/ETH/AAPLx com contagens sanitizadas. **Ainda não declarar PR, CI, merge ou run real até confirmar.**
- J2–J7 issues #3–#8 dependentes; sem motor de estratégias, backtest financeiro, VPS em produção ou operações reais.

## Próxima ação concreta
1. Verificar estado vivo de main, issue #28 e PRs. Completar teste offline, docs e PR WU8; revisar diff/CI/SHA; merge seguro sem publicação em produção.
2. Acionar exatamente uma sondagem owner-only na #28 com comentário `/probe-kraken-taxonomy-v1`, somente depois do workflow integrado; observar categorias reais de cripto versus ativos tokenizados, sem credenciais/trades.
3. Se tags/categorias permitirem classificação confiável, criar work unit de normalização de contrato e volume, mantendo armazenamento e backfill existentes; nenhuma troca silenciosa de venue. Se ambígua, registrar limites e propor solução de pesquisa, não inventar universo Top50.
4. Registrar URL de run, UTC, schema, SHA, testes e próximo passo; J1 permanece aberta até dados elegíveis, cobertura e qualidade aceitos. Não repetir GET Binance que retornou HTTP451 nem tentar contornar política.
5. Se usuário pedir "gere prompt para novo chat", entregar continuidade completa com repositório, regras, decisões, jornada, evidências, issues/PRs/SHAs, testes e próxima ação autorizada.
