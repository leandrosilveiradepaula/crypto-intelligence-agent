# J1 D263 — metadados atuais Bybit: identificação negativa sem refazer 24h

## Situação e objetivo

O censo congelado de 06/11/2026 13:00 UTC foi aceito no escopo técnico da issue #502: 822 contratos básicos inspecionados, 819 séries de 24 candles fechados validados, 3 curtas (ações TradFi recém-listadas), 0 pendentes. A issue foi fechada como **censo técnico e auditoria**; identidade crypto-only #319, operação contínua #429 e J1 #2 permanecem ABERTAS. A prova D262 owner na VPS aprovou 25/25 testes, digest bruto `b4e4884d28e4a4b385c94ea521201006242d449828d575a56f01cb2b70b8faaa`, sem chamadas de rede, DB writes ou ordens.

Pelo contrato oficial Bybit V5 de instrumentos lineares, `marketRegion` indica o calendário de mercado da origem do subjacente para TradFi, e `underlyingTicker` identifica o ticker/código nativo do subjacente. Documentação primária:
- https://bybit-exchange.github.io/docs/v5/market/instrument
- https://bybit-exchange.github.io/docs/changelog/v5 (27/08/2026 introduziu campos)
- https://bybit-exchange.github.io/docs/v5/market/instrument-summary

**Decisão:** usar somente sinal NEGATIVO atual da corretora para triagem, jamais inferir que `marketRegion=""`, `underlyingTicker=""` ou ausência de entrada no cadastro negativo provam criptomoeda. Metadados obtidos **depois** da janela congelada NÃO são identidade ponto-no-tempo válida para 06/11 13:00 UTC.

## Contrato entregue

`scripts/audit_j1_bybit_current_metadata_negative.py` é **OFF por default**, restrito a POSIX owner non-root, pasta privada 0700 e DB/lock 0600. Executa inicialmente replay/integração SQLite D256 em `mode=ro`, `query_only`, `PRAGMA integrity_check` com lock não bloqueante. Somente depois desse gate aceita um único GET público `/v5/market/instruments-info?category=linear&limit=1000`, via cliente Bybit já existente: origem fixa HTTPS, 8s, sem redirecionar/proxy, sem retry para quota, região ou bloqueio. Se `nextPageCursor` não vazio, responde `abstain`; **não** pagina silenciosamente nem apresenta denominador parcial como completo. A captura anterior permanece intacta. Falha de relógio, esquema, linha inválida, duplicidade, mudança de escopo, metadados inesperados e falha de rede são sanitizadas e não ativam qualquer saída financeira.

O relatório imprime **somente contagens e timestamps**, sem símbolos, preços, turnover, identidade de usuário, URLs sensíveis ou payload. Compara membros básicos atuais com os 822 congelados, conta atuais com evidência TradFi por `marketRegion`/ `underlyingTicker`, membros antigos ainda presentes, membros novos e ausentes, sobreposição com negativas documentais D259 e campos de metadados ausentes. Mesmo quando 1.000 linhas bastarem, `provider_negative_catalog_complete_for_market=false` e `marketwide_top50_verified=false`: catálogo atual pode ser parcial, campos podem faltar, e falta crosswalk de IDs e prova independente.

## Testes e limites

Fixtures offline: um catálogo de 60 contratos inclui `BTCUSDT`, `SOXLUSDT`, `XAUUSDT`; metadados atuais indicam 2 instrumentos TradFi. SQLite original não é modificado; 0 GET por default, 1 em caso opt-in; duplicata, cursor extra, campo inesperado e tempo futuro abstêm; falta de `marketRegion`/ `underlyingTicker` fica desconhecida, não crypto; churn atual não muda escopo congelado. Resultado verde em CI não significa que probe real executou ou que a Bybit autenticou os 822 atuais.

## Gate real, somente owner e uma execução

Após merge sem produção e SHA exato, na VPS `srv1319424` sob `cia-probe` e checkout clean verificado:

```bash
/home/cia-probe/agent/ws-venv/bin/python -m scripts.audit_j1_bybit_current_metadata_negative \
 --directory /home/cia-probe/agent/j1-global-closed24h-private/run \
 --allow-public-network --confirm-region-and-personal-research
```

Chamada de rede explícita, no máximo 1 GET após replay privado. Não repetir em loop, não baixar OHLCV, não usar credenciais, não publicar dados ou instalar serviços. Em caso de `abstain`, parar e manter falha. Não projetar o censo passado como inventário vivo nem liberar trading. Próximo bloco elegível após prova owner: ampliar cobertura negativa atual e realizar diligência independente de identidade da fronteira atual #319, preservando as fases PIT e supervisão #429.
