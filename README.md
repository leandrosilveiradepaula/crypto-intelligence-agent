# Crypto Intelligence Agent

Plataforma de inteligência quantitativa para futuros perpétuos de criptomoedas: pesquisa de entradas, backtesting realista e gerenciamento de realizações parciais de posições vencedoras.

**Estado:** J0 documental concluída e J1 em desenvolvimento. A WU1 de dados foi integrada; a WU2 de persistência/backfill está em revisão. Ainda não há motor de sinais, estratégia de trading validada ou ordens reais.

## Documentação
- [Regras para agentes](AGENTS.md)
- [Produto](docs/PRODUCT_SPEC.md) e [decisões aprovadas](docs/DECISIONS.md)
- [Arquitetura](docs/ARCHITECTURE.md), [contrato de dados](docs/DATA_CONTRACT.md) e [estratégias](docs/STRATEGY_SPEC.md)
- [Validação](docs/VALIDATION_PLAN.md) e [jornadas](docs/JOURNEYS.md)
- [Status](docs/STATUS.md) e [estado operacional](docs/OPERATIONAL_STATE.md)

## Desenvolvimento
ChatGPT coordena GitHub, revisão, integração e continuidade; Codex executa work units. A J1/WU1 (#9) foi integrada pela [PR #12](https://github.com/leandrosilveiradepaula/crypto-intelligence-agent/pull/12); a WU2 está na [issue #13](https://github.com/leandrosilveiradepaula/crypto-intelligence-agent/issues/13) e adiciona SQLite local, replay e backfill offline. Isso não comprova cobertura histórica de produção nem conclui a J1.

## Testes locais, offline
```bash
python -m unittest discover -s tests -v
python scripts/check_docs.py
python -m compileall -q crypto_intelligence_agent tests
```

O GitHub Actions executa esses checks. Todos os testes usam fixtures, sem chamadas externas nem credenciais. Endpoints de 24h volume/contratos são atuais e NÃO autorizam reconstrução retroativa de universo histórico.

Custo operacional adicional autorizado: R$0. Repositório público: nunca publicar segredos, credenciais ou informações privadas de VPS.
