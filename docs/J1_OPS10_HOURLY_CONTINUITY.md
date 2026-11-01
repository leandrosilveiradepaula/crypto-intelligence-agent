# J1/OPS10 — Gate de continuidade horária WS (issue #429)

Este gate é **offline, read-only e fail-closed**. Não inicia WebSocket, não consulta REST, não altera SQLite e não opera ordens. Reutiliza o relatório tipado de `SQLiteOfflineClosedStreamJournal.audit`, que já valida digest, cronologia, PIT e a grade de 24 candles fechados por contrato. Não substitui o auditor do journal.

`checkpoint_from_audit` exige contagem exata de contratos completos + ausentes, janela UTC fechada e timestamp de observação posterior ao fechamento. `compare_closed_hours` exige duas decisões UTC consecutivas, ambas completas, escopo de mesma cardinalidade e rank digests presentes; qualquer ausência, salto, reversão ou mudança de cardinalidade implica abstenção.

**Limites:** a mesma cardinalidade não prova identidade PIT imutável; os digests não autenticam o provedor; dois checkpoints não demonstram entrega ininterrupta em todos os segundos, PID ativo ou Top50 marketwide. O próximo incremento deve comparar fingerprints de escopo e integração com lease real, testando rotação antes de promover qualquer flag de serviço saudável. Nenhuma homologação VPS ocorreu aqui.

Testes offline: `python -m unittest discover -s tests -p test_j1_ws_hourly_continuity.py -v`. Exigir CI Linux, Windows e Chrome/PAPER, revisão do SHA e merge sem deploy antes de qualquer teste owner-only real. J1 #2, #319 e #429 permanecem abertas.
