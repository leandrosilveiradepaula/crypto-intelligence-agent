# J1/OPS1 — Auditoria local estritamente read-only de 24 horas (D245)

## Objetivo
A issue #429 exige observabilidade sem intervenção horária. Este bloco entrega **somente o observador** do banco SQLite existente; não implanta worker, timer, serviço, rede, banco novo ou ordem. Não substitui o coletor contínuo, nem a validação de elegibilidade e abrangência global da #319.

## Contrato
- `crypto_intelligence_agent/j1_local_health.py`: lê o banco já existente por URI SQLite `mode=ro`, `PRAGMA query_only` e transação de leitura; nunca instancia `SQLiteMarketDataStore`, porque suas leituras inicializam esquema/abrem `BEGIN IMMEDIATE`.
- Seleciona último snapshot point-in-time não futuro, com escopo opcional de `source` e versão; rejeita dois snapshots simultâneos ambíguos, snapshot vencido, JSON malformado ou duplicado, ranks inválidos e número maior que 50 membros.
- Examina exatamente as últimas 24 velas de 1h **fechadas** após margem temporal de 60s, para cada membro, dentro de `exchange` e `market` específicos; confere horários, deduplicação, número de barras e cobertura dos checkpoints.
- `collection_events` informa apenas a última ocorrência já gravada, sem provar que um worker esteja ativo. Resultado `sample_window_complete_unverified` indica somente estrutura local íntegra e amostra completa. Top50 global, revisão de identidade, proveniência, direitos, execução contínua e trading continuam **false**.
- Saída somente JSON sanitizado: contagens, idades, estado e timestamps; nenhum símbolo, preço, endereço de infraestrutura, token ou corpo de API. Sem HTTP, env secrets ou writes.
- CLI `scripts/j1_local_health.py` retorna exit 0 apenas para amostra local estruturalmente completa; 2 para outros estados. Sem habilitar systemd e com gate nonroot POSIX.

## Exemplo local (não executar em produção automaticamente)
```bash
python scripts/j1_local_health.py --db /caminho/privado/existente.sqlite --exchange bybit --snapshot-source nome-da-fonte
```
Ajustar o `exchange` à grafia realmente gravada. Não usar este comando como prova de Top50. Nunca criar arquivo de banco vazio para produzir saída saudável.

## Aceite e limites
Testes offline `python -m unittest discover -s tests -p test_j1_local_health.py -q`; regressões de armazenamento; compileall; CI Linux/docs, Windows/offline e Chrome/PAPER no SHA exato. Nenhuma dependência de VPS para validação de código. A prova operacional da #429 continua aberta e a #319 continua exigindo cobertura real e identidade independente. D245 registra a separação entre **saúde da amostra** e **homologação da J1**.
