# J1/OPS5 — renovação causal do catálogo de WebSocket sem apagar o histórico

**Issue:** #429. **Base verificada:** `main=3828fefa02b8ee00f145f357423e03ea95381d20` (01/11/2026). **Objetivo:** impedir que o piloto owner-only fique permanentemente bloqueado após 48 horas, sem repetir a coleta histórica, fabricar volumes/PIT, nem aceitar mudanças de contratos silenciosamente.

## Implementação

- `bybit_ws_owner_pilot.py` continua opt-in, finito, owner-only POSIX, com lock exclusivo sobre o journal WS separado da SQLite REST original. Nenhum processo em VPS é iniciado por esta alteração.
- O primeiro catálogo validado permanece em `ws-reviewed-scope.json`, arquivo **imutável** com digest, proprietário e modo `0600`, dentro de diretório owner-only `0700`. Ao completar mais de 48 horas desde a última revisão, e **somente nesse caso**, executar uma nova varredura de `instruments-info` por até quatro GETs com cliente novo, sem consultar `kline`, `ticker`, ordens ou API privada. A classificação de `10006` mantém o fail-stop, sem retry.
- O novo resultado é aceito apenas se a mesma revisão de registro, os mesmos símbolos, tipos/valores dos contratos, launch-time e parâmetros relevantes forem identificados pelo fingerprint versionado existente. Membros novos, removidos, invalidados, tick/step/leverage alterado ou mudança de registro **não** são carregados por cima do journal antigo: o piloto se abstém e exige um epoch/journal separado, com gate e trabalho próprio.
- Uma renovação aceita cria, de forma exclusiva e sem sobrescrita, `ws-reviewed-epochs/scope-<observed_at_ms>.json` (diretório `0700`, arquivo `0600`). Cada arquivo é validado contra checksum, identidade, relógio, nome, modos e inode em cada retomada. Não remover arquivos antigos nem alterar timestamps passados.
- A auditoria passa a usar a sequência PIT real, limitada a 64 epochs, e **somente snapshots que existiam até o fechamento da hora avaliada**. Se a atualização ocorrer durante a hora atual, seu novo epoch só pode ser considerado no fechamento seguinte. A hora anterior não recebe uma identidade futura. O relatório pode retornar `ws_pilot_scope_refreshed_waiting_next_closed_hour`, que indica refresh bem-sucedido sem aprovação fictícia de ranking.
- Em leases seguintes com catálogo não expirado, novos GETs de catálogo continuam **zero**. Saída de relatório agrega somente contadores, flags negativas de live/marketwide e estado; não revela símbolos, preços, paths nem finge confirmar PID em execução.

## Testes de regressão

`python3 -m unittest discover -s tests -p test_j1_ws_owner_pilot.py -v` e suíte completa da CI Linux/docs, Windows/offline e Chrome/PAPER:

- duas páginas do catálogo com 52 candidatos; primeiro lease + segundo lease com zero GET;
- 49 candidatos, paginação cíclica, `10006` sem retry, gate de quatro opt-ins;
- expiração após 49 horas: no máximo duas páginas reconsultadas, epoch novo, primeira revisão íntegra/imutável e posterior reutilização com zero GET;
- metadata churn 52→51: falha fechada, sem segundo epoch/WS; erro de modo, arquivo adulterado, nome de epoch inválido recusado antes de GET;
- auditoria causal antes e depois da virada horária: nenhum snapshot futuro altera um ranking passado; zero compras, ordens ou modificação da SQLite REST.

## Limites e próxima etapa

A suite é **offline e sintética**; não prova feed da Bybit em VPS, Top50 de todos os perpétuos elegíveis, disponibilidade de 24h de candles, retorno financeiro ou serviço 24/7 habilitado. O registro de 52 bases fixado em outubro também exige **revisão e nova versão** antes de expirar a política de idade de 7 dias; OPS5 **não** contorna esse gate nem renomeia candidatos não revisados como elegíveis. Rotação com churn demanda um journal/epoch separado com ponte causal apropriada. Uma execução real owner-only permanece sujeita a controles operacionais e de acesso, sem deploy automático e sem chaves.

Próxima implementação elegível de #429: preparação de supervisor de processo (`systemd`) inativo por padrão, CLI de saúde em português, renovação causal do registro de elegibilidade e estudo de reconciliador REST somente para lacunas específicas. Issue #319 mantém o denominador Top50 marketwide como requisito não concluído. Evidência histórica da execução EXIT5: 37.470 candles, dois PIT imutáveis e `10006` em 168 GETs; banco preservado e nunca regravado por este trabalho.