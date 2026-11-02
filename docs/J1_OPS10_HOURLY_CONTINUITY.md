# J1/OPS10 — Gate de continuidade horária WS (issue #429)

Este gate é **offline, read-only e fail-closed**. Não inicia WebSocket, não consulta REST, não altera SQLite e não opera ordens. Reutiliza o relatório tipado de `SQLiteOfflineClosedStreamJournal.audit`, que já valida digest, cronologia, PIT e a grade de 24 candles fechados por contrato. Não substitui o auditor do journal.

`checkpoint_from_audit` exige contagem exata de contratos completos + ausentes, janela UTC fechada e timestamp de observação posterior ao fechamento. `compare_closed_hours` exige duas decisões UTC consecutivas, ambas completas, escopo com mesma identidade de contratos PIT validada pelo fingerprint privado, mesma cardinalidade e rank digests presentes; qualquer ausência, salto, reversão ou mudança de cardinalidade implica abstenção.

**Limites:** o fingerprint compara especificações contratuais revisadas, mas não certifica origem de rede nem substitui verificação dos snapshots PIT; os digests não autenticam o provedor; dois checkpoints não demonstram entrega ininterrupta em todos os segundos, PID ativo ou Top50 marketwide. O próximo incremento deve comparar fingerprints de escopo e integração com lease real, testando rotação antes de promover qualquer flag de serviço saudável. Nenhuma homologação VPS ocorreu aqui.

Testes offline: `python -m unittest discover -s tests -p test_j1_ws_hourly_continuity.py -v`. Exigir CI Linux, Windows e Chrome/PAPER, revisão do SHA e merge sem deploy antes de qualquer teste owner-only real. J1 #2, #319 e #429 permanecem abertas.

## Integração OPS10 ao piloto owner-only

O `run_owner_ws_pilot` reaproveita os relatórios de auditoria antes/depois do lease e, apenas quando a decisão fechada avança exatamente 1h, calcula `local_two_hour_continuity` pelo gate tipado. O campo é falso por padrão, inclusive para ACKs, execução sem velas, janela incompleta e ausência de rotação horária. Ele aparece no relatório sanitizado/health de último evento, sem alterar o estado operacional existente. Não executa auditorias REST adicionais e não liga serviço algum.

O rótulo positivo é estritamente **continuidade local entre duas decisões de auditoria** com mesmo fingerprint contratual. Não prova daemon 24/7, cobertura de todas as horas intermediárias de um soak, Top50 do mercado, dados autenticados nem capacidade de negociar. A saúde exposta por `j1_ws_service_health.py` continua unverified para liveness real.

Testes adicionais: `python -m unittest discover -s tests -p test_j1_ws_owner_pilot.py -v`. Revisão e CI completas obrigatórias no SHA final, sem produção.
