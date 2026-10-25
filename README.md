# Crypto Intelligence Agent

Plataforma em desenvolvimento de inteligência quantitativa para futuros perpétuos de criptomoedas: identificação de oportunidades, pesquisa estatística e futuras saídas parciais de vencedores. **Sem execução automática real e sem promessa de lucro.**

## Situação
- J0 documental concluída.
- J1 Dados em andamento: WU1 (#12), WU2 (#14), WU3 (#16) e WU4 (#18) integradas; parte offline da WU5 (#20) integrada. [Issue #19](https://github.com/leandrosilveiradepaula/crypto-intelligence-agent/issues/19) continua aberta aguardando evidência real de API pública.
- CI pós-WU5: **78 testes Python offline**, compilação e dez documentos aprovados. Não equivale a feed live homologado.

## Documentação
[Regras para agentes](AGENTS.md) · [Produto](docs/PRODUCT_SPEC.md) · [Arquitetura](docs/ARCHITECTURE.md) · [Decisões](docs/DECISIONS.md) · [Contrato de dados](docs/DATA_CONTRACT.md) · [Estratégias](docs/STRATEGY_SPEC.md) · [Validação](docs/VALIDATION_PLAN.md) · [Jornadas](docs/JOURNEYS.md) · [Status](docs/STATUS.md) · [Estado operacional](docs/OPERATIONAL_STATE.md)

## Demonstração offline — fixtures sintéticas, nenhuma rede
```bash
python -m crypto_intelligence_agent
python -m crypto_intelligence_agent --max-symbols 2 --interval 1h --candles 3
python -m crypto_intelligence_agent --database /tmp/crypto-market-demo.sqlite3 --symbols BTCUSDT
```

O banco SQLite é temporário por padrão; `--database` cria armazenamento local explicitamente indicado. O JSON registra fontes, timestamps, endereços de endpoints, resultados, status de coleta e cobertura. **Os dados offline são sintéticos e não servem para medir rentabilidade.**

O modo live é estritamente read-only e precisa das duas opções `--mode live --allow-public-network`. Uma verificação limitada, quando houver executor autorizado com rede, usa `--max-symbols 1 --candles 3`. HTTP 403/418 não é retentado automaticamente, HTTP 429 respeita espera limitada, e desvio de relógio excessivo bloqueia a captura. Nenhuma consulta live foi comprovada nesta etapa.

## Testes de engenharia
```bash
python -m unittest discover -s tests -v
python scripts/check_docs.py
python -m compileall -q crypto_intelligence_agent tests
```

CI roda somente testes offline com fixtures e sem chaves. O volume atual de 24h não é fonte de universo histórico retrospectivo. SQLite é backend local de referência, não decisão de banco de produção.

**Custo adicional autorizado: R$0.** Repositório público: nunca versionar segredos, chaves, credenciais, dados pessoais ou bancos capturados.

## Verificação read-only via GitHub sob comando do proprietário

A validação **live** não é executada em CI automática. O workflow `.github/workflows/public-feed-smoke.yml` aceita apenas um comando explícito `/run-readonly-smoke-v1` publicado pelo dono do repositório na [issue #19](https://github.com/leandrosilveiradepaula/crypto-intelligence-agent/issues/19). É restrito a 1 símbolo, 3 candles, GET público e três minutos num runner padrão de repositório público; sem secrets, ordens, gastos adicionais, deploy ou agendamento. O job gera logs sanitizados, mas um sucesso pontual não substitui a homologação completa da J1.
