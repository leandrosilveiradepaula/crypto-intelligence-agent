# J1 D256 — auditoria offline, privada e somente leitura do censo de 24h

## Objetivo e limites
A prova owner VPS de 06/11/2026 encerrou a inspeção de 822/822 contratos técnicos do catálogo Bybit, mas deixou 3 short (6 candles) e não demonstrou identidade cripto independente nem coletor contínuo. O registro privado tem 819 contratos com 24h completas / 19.656 candles e digest exploratório `b4e4884d28e4a4b385c94ea521201006242d449828d575a56f01cb2b70b8faaa`. **Esta prova não cria Top50 negociável**.

A auditoria `scripts/audit_j1_marketwide_checkpoint.py` não usa rede, não reconsulta contratos, não cria novas tabelas ou muda candles. SQLite é aberto com `mode=ro` e `PRAGMA query_only=ON`; POSIX exige owner não-root, diretórios 0700, lock e banco 0600 e tenta lock compartilhado não bloqueante. São auditados `PRAGMA integrity_check`, único `scope`, 24 linhas contíguas por contrato completo, Decimal OHLCV, todos os short 0..23 com digest e escopo, e recomputado o Top50 apenas dos **completos**. O relatório é sanitizado, sem símbolos, valores, URLs ou material privado; falhas produzem `abstain`.

## Discrepância da trilha, não dos candles
A saída D254 tinha 715 contratos inspecionados; a saída final D255 tinha 822, diferença 107. A última chamada indicou 48 GETs, sendo 1 catálogo, logo suporta **no máximo 47 novos contratos** naquela invocação. Se essas foram execuções adjacentes, faltam **no mínimo 60 inspeções com proveniência de sessão não documentada**. Uma execução intermediária não exibida é hipótese, não fato. O banco de candles não contém um journal de chamadas HTTP e não pode provar como as 60 inspeções foram realizadas.

O auditor aceita `--previous-inspected 715 --last-run-requests 48` como **duas alegações externas** e calcula `minimum_unattributed_inspections=60`; elas não alteram o banco nem demonstram origem dos candles. `request_trace_complete_verified=false` permanece sempre falso, mesmo quando a aritmética fecha. Reconciliar somente com registros de execução já existentes, sem gravar dados privados no GitHub e sem repetir 822 GETs.

## Execução owner-only na VPS, somente quando SHA revisado e CI verde
```bash
runuser -u cia-probe -- /home/cia-probe/agent/ws-venv/bin/python \
  -m scripts.audit_j1_marketwide_checkpoint \
  --directory /home/cia-probe/agent/j1-global-closed24h-private/run \
  --previous-inspected 715 --last-run-requests 48
```

Executar a partir do checkout `/home/cia-probe/agent/repo`; jamais usar root diretamente como auditor. A ausência de log intermediário deve permanecer registrada como lacuna documental, não como falha demonstrada do conteúdo do SQLite. Não ativar timer, supervisor ou ordens.

## Aceite
Testes adversariais offline com 60 contratos: 57 completos + 3 short; digest comparado ao coletor; 60 completos sem promoção cripto; adulteração de candle, hash, short e scope; operador malformado; symlink e owner; bytes do banco inalterados; sem dependência de rede. CI Linux/docs, Windows/offline e Chrome/PAPER no head exato. A PR pode ser integrada sem deploy se gates estiverem verdes. #319, #429 e J1 #2 permanecem abertas.
