# J1/OPS2 — Ranking horário local por 24 velas fechadas WebSocket

## Objetivo e limite operacional

A execução real EXIT5 na VPS (01/11/2026) encerrou em `10006` após 168 GETs. A auditoria independente confirmou 37.470 candles, 51 ativos armazenados, 50 membros atuais, 2 PITs, SQLite/replay íntegros e nenhuma ordem. O erro **não autoriza** nova captura cega nem inferência de cooldown. É necessário retirar o ranking recorrente de 24h do caminho de consultas REST.

O contrato J1/OPS2 (parte da issue #429) cria `replay_offline_ws_closed_hour(...)`, que recebe frames já coletados de `kline.60` com carimbo de recebimento, valida o ACK de inscrição, ignora velas abertas e anexa somente velas fechadas ao journal SQLite WS offline existente. Após cada hora UTC, a função chama **o auditor já existente** do journal para calcular a janela móvel de **24 velas 1h fechadas**. O auditor expõe as pontuações ordenadas somente em memória privada, sem trocar a lógica de somatório, integridade ou digest e sem exibir símbolos/valores no relatório sanitizado.

O novo status `offline_reviewed_hour_ready_not_marketwide` exige 24 velas completas para **todos** os componentes do universo revisado, mesmo quando só os 50 maiores serão selecionados entre 52 candidatos. Um candidato ausente poderia entrar no Top50; portanto falha como `offline_closed_hour_incomplete_abstain` sem ranking parcial. O filtro e a identidade dos candidatos vêm de um `OfflineReviewedStreamScope` causal versionado. Nenhum ticker rolling-24h substitui o somatório de candles fechados.

O cálculo retorna um ranking interno para consumidores de pesquisa offline, com `max_assets` entre 1 e 50. `sanitized_report()` contém apenas contagens, status, digests e `network_requests=0`; nunca revela símbolos, preços, turnover, payloads nem nomes de arquivos. Sem ordem, segredo ou rede. Frames inválidos, ACK ausente, stale confirm, lacuna, replay conflitante, registro anacrônico e contrato alterado falham fechados. O journal WS permanece **separado** da SQLite REST owner-only; não copiar dados entre os dois nem rebatizá-los como uma origem autenticada.

## O que esta entrega NÃO faz

- **Não instala nem inicia** coletor WebSocket 24/7, systemd, cron, reconciliação REST ou endpoint de trading. A integração live será uma etapa revisável futura da issue #429, com transporte/controlador supervisionado e gates explícitos.
- Não recupera os 720h históricos do banco REST existente, não cria PIT de horas perdidas, não elimina a necessidade de descobrir/revalidar contratos e não comprova o Top50 do mercado inteiro (#319).
- Não garante disponibilidade do WebSocket nem que o limite REST `10006` deixará de existir. Em caso de lacunas não supridas, o motor não emitirá ranking.

## Validação reproduzível

- `python3 -m unittest discover -s tests -p test_j1_ws_hourly_research.py -v`
- `python3 -m compileall -q crypto_intelligence_agent tests`
- `python3 scripts/check_docs.py`
- CI Linux/docs, Windows/offline e Chrome/PAPER no SHA revisado, e pós-merge no SHA de integração.

As fixtures simulam 24h iniciais, três fechamentos horários posteriores, 52 membros revisados com um membro ausente, recuperação causal com velas efetivamente registradas, alteração da liderança do ranking sem GET, replays idempotentes, lacunas, ACK ausente, vela aberta e temporização indevida. Nenhuma amostra sintética vira evidência da VPS, prova de marketwide ou premissa de lucro.

## Próxima etapa autorizada

Projetar o supervisor/reconexão e o adaptador WebSocket real **por trás de permissão explícita**, usando o pipeline e o journal existentes, com exclusão mútua de escritores, limite de frames e verificação de último candle UTC. Restabelecer lacunas com REST GET incremental limitado, mas nunca fazer retry automático em `10006` ou alterar o banco REST original sem migração/gate. A instalação/ativação na VPS exige verificação operacional antes de mudar o serviço em execução.