# J1/D276 — sensibilidade do corte dos 50 no censo congelado

Data: 11/11/2026 UTC. Issues #319/#517. Foco: priorizar provas da identidade e do contrato, não refazer coleta.

## Evidência real antes de implementar

Uma execução **owner-only somente leitura** em `cia-probe` sobre D256 + snapshot negativo D264 (frozen end `1793970000000`, 819 séries de 24 candles, 3 séries incompletas, 298 exclusões contemporâneas/documentais entre as séries completas) reconstituiu a ordenação dos candidatos. A função interna de teste utilizou `_replay` do SQLite, `_load_private` do D264, `_dec` e Decimal com contexto `_MATH`: nenhuma solicitação HTTP, alteração do DB ou ordem.

Três cenários, **exclusivamente condicionais**:

| Cenário de pesquisa | Contratos novos no Top50 da fronteira após exclusões | Consequência |
|---|---|---|
| D264 original | 0 | 50 candidatos retrospectivos, não autenticados PIT |
| Remover `XAUTUSDT` (ouro tokenizado) | 1: `LYNUSDT` na posição 50 | A política sobre ouro muda a fronteira |
| Remover também os quatro com colisão (`LITUSDT`, `ARIAUSDT`, `BIRBUSDT`, `CLANKERUSDT`) | 5: `LYNUSDT`, `DOTUSDT`, `ICNTUSDT`, `ELSAUSDT`, `AEROUSDT`, posições 46–50 | É obrigatório investigar substitutos abaixo do corte |

Nenhuma exclusão de `XAUT` ou dos quatro ambíguos foi determinada nesta entrega. `CLANKER` tem pesquisa primária posterior, mas identidade histórica da D261 ainda é colidida. Os novos candidatos também são **apenas hipóteses**, não ativos aprovados automaticamente. O candidato na posição 51 pode deslocar o universo se qualquer posição dos 50 for excluída. Séries com 24h incompletas não recebem turnover zero nem podem ser consideradas competidores ausentes por definição.

## Código e execução

`crypto_intelligence_agent/j1_top50_cutoff_sensitivity.py` implementa três cenários determinísticos sobre a **ordem já validada de 24 candles fechados da mesma hora UTC**. O módulo não usa volume monetário, dados privados, ticker aberto ou endpoint. Verifica tipos, unicidade, formato e quantidade de símbolos; retorna contagens, SHA256 de cada ordenamento e sinalização dos concorrentes incompletos. O algoritmo não autentica a ordenação fornecida pelo chamador.

`scripts.j1_d264_private_metadata_snapshot.replay_private_snapshot` agora anexa `conditional_cutoff_sensitivity` após validar SQLite, censo, snapshot D264 e digest da ordenação. Em modo padrão, nomes e valores **não aparecem**; com `--include-private-symbols`, somente os nomes públicos, posições, próximos 10 e substituições são exibidos no terminal privado owner. O SQLite e snapshot congelados permanecem intactos.

Executar na VPS apenas via usuário `cia-probe` autorizado:

```bash
/home/cia-probe/agent/ws-venv/bin/python -m scripts.j1_d264_private_metadata_snapshot --directory /home/cia-probe/agent/j1-global-closed24h-private/run
```

O `cwd` é `/home/cia-probe/agent/repo`. A execução precisa usar executor owner auditável, não o conector de operações limitado que não consegue assumir o usuário.

## Interpretação e gates

É **incorreto** transformar a fronteira D264 em universo de 50 cripto elegíveis: filtros de 08/11 são retrospectivos sobre 06/11, e o registro arquivado não autentica identidades. O ranking é de **819 contratos com candles completos**, não prova exaustiva de volumes de todos os 822: os 3 incompletos são rivais possíveis até resolução. `marketwide_top50_verified=false`, `identity_pit_authenticated=false`, `trading_enabled=false` sem exceção.

Testes: exclusões de 1 e 5 membros, novos candidatos, empates de ordem assumida, contagem de incompletos, privacidade, falha segura com input malformado, ausência de rede/DB, replay SQLite D264 com fixtures. CI Linux/docs Windows/offline Chrome/PAPER no SHA final antes de merge sem deploy.

**Próxima tarefa substantiva:** investigar os 5 substitutos mais próximos e classificar suas identidades independentes/PIT em lote. Isso reduz o risco de resolver 50 instrumentos e depois descobrir que a exclusão de um deles invalida o corte.
