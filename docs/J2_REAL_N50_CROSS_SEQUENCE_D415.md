# J2 D415 — Bybit N50 real: cross sequence estável com atualização posterior

## Evidência observada na VPS em 17/11/2026, 22h59 UTC

O operador executou D414 a partir de tarball pinado de GitHub SHA `30baedabe40832bd1b2ee6418fa5eb4034051771`, como `cia-probe`, sem tocar nos arquivos da J1.

| Prova real | BTCUSDT (D405) | N50 owner (D406) |
| --- | ---: | ---: |
| Assinatura pública reconhecida | 1 | 1 |
| Quadros recebidos | 68 | 314 |
| Quadros pré-ACK reidratados | 2 | 239 |
| Quadros ticker admitidos **pós-ACK** | **65** | **73** |
| Instrumentos distintos com quote validado | **1/1** | **33/50** |
| Preços frescos no encerramento | **1/1** | **33/50** |
| Falha de sequência | nenhuma | `conflicting_replay` |
| Estado do lease | `lease_completed`, exit 0 | `lease_abstained`, exit 2 |
| Solicitações de ordem, mutações J1 | 0 | 0 |

**BTCUSDT está operacional em uma sessão real de 10 segundos**, com ACK, 65 cotações pós-ACK, preço fresco e latência reportada p95/p99 na faixa 0–100ms. Para o N50, o bootstrap e as primeiras cotações reais também funcionaram, mas a sessão terminou antecipadamente quando **o mesmo contrato recebeu um segundo payload diferente com `cs` idêntico ao do evento anterior**. O relatório não traz o timestamp nem o contrato envolvidos; não assumir que a causa de mercado está comprovada. É hipótese técnica de contrato excessivamente estrito no cliente.

## Regra de protocolo

A documentação oficial V5 descreve `cs` como *cross sequence* e `ts` como timestamp gerado no sistema; no ticker linear, quadros `snapshot`/`delta` carregam mudanças parciais, preservando valores omitidos. Ela **não garante** que `cs` seja um ID exclusivo para cada evento de ticker. Fonte: https://bybit-exchange.github.io/docs/v5/websocket/public/ticker

O decodificador D385 tratava `cs` repetido **e payload diferente** como `ticker_same_sequence_conflicting_payload` mesmo que o timestamp da exchange tivesse avançado. D415 corrige somente essa distinção:

- **`cs` igual e `ts` maior:** uma atualização causal distinta pode ser validada normalmente, preservando regras existentes de schema, delta, preço decimal, BBO, tempo de recepção e idade máxima.
- **`cs` igual, `ts` igual, payload idêntico:** redelivery exata continua duplicada; não renova timestamp.
- **`cs` igual, `ts` igual, payload diferente:** ambiguidade real, continuar fail-closed (`conflicting_replay`); não inventar ordem dos eventos no mesmo milissegundo.
- **`cs` menor, `ts` menor ou tempo local regressivo:** continuar fail-closed, mesmo que preços aparentem razoáveis.
- Snapshot inicial, reconexão, integridade de JSON, pertinência à coorte e stop-first do PAPER não mudam. Nenhuma quote pré-ACK vira callback ou resultado financeiro.

Este ajuste mantém no livro o mesmo `cross_sequence` quando existe um novo timestamp causal, não incrementa artificialmente a sequência e não altera o diário AUTO4.

## Evidência exigida e limitação

Os testes D385 + D386 reproduzem atualizações legítimas da mesma sequência com timestamps crescentes, campos parciais e 50 contratos mais posição fora do ranking. Confirmam que o decodificador continua recusando payload diferente com **mesmo `cs` e mesmo `ts`**, sequência regressiva, replay idêntico como nova cotação, timestamp futuro/vencido e BBO incorreto.

```sh
python -m unittest discover -s tests -p 'test_bybit_public_ticker_state_d385.py' -v
python -m unittest discover -s tests -p 'test_bybit_public_ticker_supervisor_d386.py' -v
python -m unittest discover -s tests -p 'test_bybit_public_ws_operational_probe_d405.py' -v
```

**Próxima ação operacional:** depois de revisão e CI verde em commit exato, executar um *único* probe D406 real, de duração finita, em tarball temporário SHA pinado, sem alterar a coleta J1. O alvo é `status=lease_completed`, cobertura de 50 distintos e preço fresco suficiente, não apenas contagem de mensagens. Se persistir `conflicting_replay`, já ficará restrito a payload divergente com mesmo timestamp e sequência: não remover o bloqueio; implementar diagnóstico estrutural por categoria, sem símbolos/preços. Se a cobertura terminar inferior a 50, separar silêncio de tópico de validade/frescor. O feed 24×7 e execução PAPER de posições continuam **não homologados**, sem instalar serviço/ordens reais.

Custo adicional: R$ 0,00.
