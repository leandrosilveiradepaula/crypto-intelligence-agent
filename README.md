# Crypto Intelligence Agent

Plataforma de inteligência quantitativa para futuros perpétuos de criptomoedas: pesquisa de entradas e de saídas parciais com backtest realista. Interface PT-BR mobile planejada, ainda não implementada.

**Estado:** J0 documental concluída; J1 Dados em andamento. Work units WU1–WU4 integradas, WU5 [#19](https://github.com/leandrosilveiradepaula/crypto-intelligence-agent/issues/19) aberta para conformidade de feed público. **Nenhuma ordem real, lucro comprovado ou implantação em produção.**

## Documentação e governança

- [AGENTS.md](AGENTS.md): autonomia e gates
- [Produto](docs/PRODUCT_SPEC.md), [Decisões](docs/DECISIONS.md), [Arquitetura](docs/ARCHITECTURE.md)
- [Contrato de dados](docs/DATA_CONTRACT.md), [Estratégias](docs/STRATEGY_SPEC.md), [Validação](docs/VALIDATION_PLAN.md)
- [Jornadas](docs/JOURNEYS.md), [Status](docs/STATUS.md), [Estado operacional](docs/OPERATIONAL_STATE.md)

## Demo offline: somente fixtures sintéticas

```bash
python -m crypto_intelligence_agent
python -m crypto_intelligence_agent --max-symbols 2 --interval 1h --candles 3
python -m crypto_intelligence_agent --database /tmp/crypto-market-demo.sqlite3 --symbols BTCUSDT
```

A CLI cria um banco SQLite temporário (salvo quando `--database` é informado), utiliza fixtures **sintéticas**, não abre conexões de rede e fornece JSON de cobertura e auditoria. Dados sintetizados não servem para testar lucro, taxas ou liquidação.

Opcionalmente existe modo de **GET público** que exige as duas opções `--mode live --allow-public-network`. Não roda em CI e não é, por si só, uma homologação de cobertura ou licença para colocar em produção. O servidor de tempo da exchange é checado antes de coletar dados; `--max-clock-skew-ms 5000` controla a tolerância à diferença local/remota incluindo incerteza por latência.

## Testes offline

```bash
python -m unittest discover -s tests -v
python scripts/check_docs.py
python -m compileall -q crypto_intelligence_agent tests
```

CI após WU4: **65 testes Python offline**, compilação e 10 documentos aprovados. Testes usam fixtures sem API paga nem chaves.

O volume móvel atual de 24h não permite reconstruir o universo histórico. O banco SQLite é uma implementação local de referência, não um requisito de banco de produção.

**Custo adicional permitido:** R$0. Repositório público: nunca versionar segredos, credenciais, dados pessoais ou bancos capturados.

## Conformidade pública (WU5, ainda sem homologação live)

O adaptador rejeita HTTP 403/418 sem retentativa, limita HTTP 429 com `Retry-After` e trata payloads malformados como erro. A documentação em `docs/DATA_CONTRACT.md` explica os limites e a proveniência. A CLI live já requer `--mode live --allow-public-network`, mas não é executada automaticamente nem foi comprovada contra respostas reais nesta etapa. Testes CI usam fixtures sem acesso externo.
