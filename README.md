# Crypto Intelligence Agent

Plataforma de inteligência quantitativa para futuros perpétuos de criptomoedas: pesquisa de entradas, backtesting realista e gerenciamento de realizações parciais de posições vencedoras.

**Estado:** J0 documental concluída; J1 em desenvolvimento. WU1 e WU2 integradas. A aplicação ainda não possui motor de sinais, estratégia financeira validada ou ordens reais.

## Documentação
- [Regras de agentes](AGENTS.md)
- [Produto](docs/PRODUCT_SPEC.md) e [decisões](docs/DECISIONS.md)
- [Arquitetura](docs/ARCHITECTURE.md), [contrato de dados](docs/DATA_CONTRACT.md) e [estratégias](docs/STRATEGY_SPEC.md)
- [Plano de validação](docs/VALIDATION_PLAN.md) e [jornadas](docs/JOURNEYS.md)
- [Status](docs/STATUS.md) e [estado operacional](docs/OPERATIONAL_STATE.md)

## Engenharia e testes
ChatGPT coordena GitHub, testes, revisão, integração e continuidade; Codex executa work units de engenharia. J1/WU1: [PR #12](https://github.com/leandrosilveiradepaula/crypto-intelligence-agent/pull/12). J1/WU2: [PR #14](https://github.com/leandrosilveiradepaula/crypto-intelligence-agent/pull/14). Próxima: [issue #15](https://github.com/leandrosilveiradepaula/crypto-intelligence-agent/issues/15), J1/WU3.

Comandos offline:
```bash
python -m unittest discover -s tests -v
python scripts/check_docs.py
python -m compileall -q crypto_intelligence_agent tests
```

CI pós-WU2: 42 testes Python offline, compilação e documentação aprovados. Este projeto ainda não foi homologado com dados reais nem implantado.

Os dados de volume móvel 24h e contratos atuais não constituem histórico de universo ponto-no-tempo. SQLite local é referência, não decisão de banco de produção.

**Custo operacional adicional autorizado:** R$0. Repositório público: não versionar segredos, credenciais ou bancos capturados.

## Demonstração operacional J1/WU3 (sem acesso à rede)

Por padrão, a CLI roda **apenas fixtures sintéticas**. Não utiliza APIs, credenciais, ordens ou serviços pagos.

```bash
python -m crypto_intelligence_agent
python -m crypto_intelligence_agent --max-symbols 2 --interval 1h --candles 3
python -m crypto_intelligence_agent --database /tmp/crypto-market-demo.sqlite3 --symbols BTCUSDT
```

A saída é um JSON com origens de endpoints, hora de captura, símbolos, cobertura e auditoria. Um banco não informado é temporário e removido ao fim do comando; bancos locais são ignorados pelo Git. O modo offline representa **dados sintéticos**, sem validade para pesquisas de rentabilidade.

O modo de rede requer duas opções deliberadas: `--mode live --allow-public-network`, usa apenas GETs públicos da Binance USD-M e nunca é disparado em CI. Consulte `docs/DATA_CONTRACT.md` para limitações e não use isso como autorização de implantação ou negociação.
