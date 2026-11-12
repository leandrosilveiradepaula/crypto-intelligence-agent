# J1/D299 — auditor owner-only de N50 gerenciado e lacunas PIT reais

## Finalidade

Após a substituição controlada N2→N50 de 12/11/2026 (D297/D298) o timer N50 está ativo, porém não há prova de execução contínua até passarem as janelas reais. A J1 precisa de uma leitura única, independente e repetível do estado dos epochs para não confundir censo, backup histórico e hora realmente publicada.

O comando `python -m scripts.audit_j1_n50_managed_epochs --allow-private-readonly-audit`, executado apenas como proprietário não-root `cia-probe`, lê **somente** a raiz N50 pinada `/home/cia-probe/agent/j1-n50-managed-d296-private`. Não aceita caminhos SQL arbitrários no CLI. Verifica diretórios owner 0700, manifesto D287 0600 por epoch, validade causal do scope, ponteiro ativo D294 e seu digest, presença do journal M1 e **auditoria read-only completa D290/D292** de todos os dados do SQLite antes de contar publicações. Faz consultas apenas `mode=ro`, `query_only=ON`. Não retorna símbolos, candles, volumes ou preços.

## Contratos de saída e aceite

A saída JSON count-only expõe estados `awaiting_first_epoch`, `awaiting_first_writer`, `verified_epoch_history`, `verified_with_missing_pit`, `stale_active_publication` ou `blocked`. Inclui epochs observados, candles e checkpoints **realmente gravados**, timestamp UTC da última publicação, cobertura dos últimos 24 fechamentos elegíveis e lacunas internas reais entre publicações, incluindo mudanças de epoch. Nenhum horário faltante é sintetizado e nenhuma troca de coorte é considerada automática só pela presença do timer.

O campo `owner_integrity_verified=true` vale apenas para journals materialmente existentes e integralmente replayados. Ele **não** equivale a `continuous_collector_verified`, que permanece sempre falso nesse auditor; este status exige avaliação independente de ≥24 fechamentos horários reais e rotação posterior a 36h. Os campos de trading, rede, mutação SQLite e sistema permanecem falsos/zero.

A validação offline `tests/test_j1_n50_managed_health.py` cobre inicialmente nenhum epoch, captura sem writer, 1 publicação sem declarar 24h, gap real entre checkpoints, scope/pointer adulterados, banco symlink, auditor independente negado, idade da última publicação e opt-in antes de qualquer leitura.

## Limites

O código não modifica service/timer, não faz GET de mercado e não instala cron, daemon ou release. Os snapshots N2 D256/D264 e o backup D297 permanecem preservados. O auditor é executado pontualmente pelo operador/automação autorizada; não substitui watchdog de sistema externo. A implantação N50 já foi comprovada separadamente por systemd, mas o produto segue sem ordens reais e #429/#319 continuam condicionadas a evidências futuras.

### Estados transitórios durante o próprio job N50

Enquanto o censo D286/D287 está coletando o Top50 para um epoch ainda **não promovido**, pode existir a pasta `epoch-<UTC>` antes de haver ponteiro ativo, ou uma pasta nova além do ponteiro antigo durante a rotação. O auditor aceita apenas a pasta do **fechamento UTC presente, dentro de HH:01..HH:15, owner 0700, journal vazio e scope vazio ou somente manifesto 0600**. Nesses casos retorna `capture_in_progress_unverified` ou `rotation_in_progress_unverified` com `owner_integrity_verified=false`, sem confiar em qualquer PIT até a promoção atômica. Fora dessa janela, arquivos inesperados bloqueiam.

Durante o primeiro writer M1, o SQLite existe antes da primeira linha `published_hour`. O auditor owner D292 distingue `unpublished_bootstrap_resume_ready` (subset íntegro de símbolos com 24 candles) de journal ainda sem transação. O observador retorna `partial_first_writer` ou `in_progress_unverified`, nunca afirma corrupção prematuramente nem publica um checkpoint inexistente. Após HH:15, estado não validado retorna `blocked`. Isso permite watchdog somente leitura durante o censo e no próprio fechamento sem falsos alarmes.
