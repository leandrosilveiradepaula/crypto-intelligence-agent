# J1/OPS31 — timer único para shadow público sem persistência (#482)

## Evidências de entrada

Na `main=6bf647aa354abfe5228a34be0a84a5ff687ca0f3`, OPS30 #480/PR #481 já tem CI pré-merge (Linux/docs+Windows/offline run 41862514463 e Chrome/PAPER 41862514409) e pós-merge (Linux/docs+Windows/offline run 41907975747 e Chrome/PAPER 41907975790) SUCCESS. Código OPS30 mede apenas contagens in-memory, sem REST, SQLite ou ordens. A última evidência do checkout da VPS ainda é `229969952c3c0bcd06b35f7b828eac21c9bd1498`; não presumir sincronização. Três claims antigos devem permanecer intactos em `ops23-claims`, `ops25-retest2-claims` e `ops26-retest3-claims`. OPS22 WS×REST já teve 6/6 em uma hora BTCUSDT, mas permanece apenas corroboração do mesmo provedor.

## D237 — uma única observação separada, sem retries

`j1_ops31_shadow_timer.py` implementa supervisor owner-only que se inicia **60 segundos antes** de uma hora UTC exata e libera até **180 segundos** de observação (`--frames 1024`, duas subscriptions `BTCUSDT` e `ETHUSDT` em um único WS, zero REST), cobrindo a virada UTC sem agendar novas horas. `target_utc` deve ser `YYYY-MM-DDTHH:00:00Z`; SHA de 40 hex e árvore limpa obrigatórios. Antes de qualquer rede: relógio NTP sincronizado, non-root, instante dentro de 15s após horário de lançamento, serviços e timers concorrentes conhecidos não ativos e pasta state POSIX 0700 própria do owner, fora do repo. Um `O_EXCL|O_NOFOLLOW` cria claim privado `ops31-shadow-one-shot-attempt.claim` (0600) **antes** do subprocesso; claim consumida nunca é resetada, inclusive em falha/timeout. Nenhum retry, `Restart=no`, `Persistent=false`.

O subprocesso é sempre `scripts.observe_j1_ws_shadow_once` do OPS30, com opt-ins públicos explícitos, dois tópicos fixos, non-root, `--seconds 180 --frames 1024`; orçamento do subprocesso no máximo 205s e timeout systemd 225s. O launcher não grava dados de mercado, não executa SQLite/REST, não reinicia a sonda OPS22 e só escreve o marker em pasta privada. Saída ao journald é **apenas** `ShadowLaunchResult.sanitized_report()`; não repassar stdout/stderr brutos. Validação cruza status allowlisted, retorno do subprocesso, limites de cada contador, bandas de fechamento e de atualização aberta, flags falsas de autenticação/ingestão/Top50/trading e zero REST/writes/ordens. Anomalia/ausência de ACK/erro de estrutura/limites retornam abstenção; nenhuma medida permite liberar feed 24h.

`scripts.render_j1_ops31_shadow_timer` apenas **renderiza** templates de `deploy/systemd`; não instala/ativa timer. Unit `cia-j1-ops31-shadow-once.service` com `User=cia-probe`, `ProtectSystem=strict`, `ReadWritePaths` apenas do state, sem restart. Timer `cia-j1-ops31-shadow-once.timer` absoluto, `AccuracySec=1s`, `RandomizedDelaySec=0`, `Persistent=false`. Nomes de units e marcador **não são reutilizados** de OPS22/OPS25/OPS26.

## Checklist de ativação owner-only, não automática

1. Antes de qualquer comando na VPS: conferir PR/CI pós-merge SHA exato, NTP, proprietário `cia-probe`/venv e espaço, árvore Git limpa, ausência de coletores e timers conflitantes, três claims antigos presentes. Nunca aceitar SHA unverified/branch divergente.
2. Escolher próxima janela UTC com espaço suficiente para preflight, sem instalação em cima da virada. Criar state novo `/home/cia-probe/agent/ops31-shadow-claims` com mode 0700 e owner `cia-probe`; novo alvo exato UTC e units diferentes, renderer executado como `cia-probe` e `systemd-analyze verify` sob root, sem `enable` antes de todas gates.
3. **Somente** com gate operacional proprietário e rede pública Bybit permitida regionalmente, instalar e habilitar **exatamente o timer novo**, sem ligar serviço contínuo. Nenhum GET REST, backfill 720h, reset, cron novo ou ordens. Terminal pessoal pode fechar depois de agenda aprovada.
4. Após fechamento mais 3 minutos, verificar `systemctl show` (`Result`, `ExecMainStatus`, timestamps), `journalctl` sanitizado e claim. Desabilitar timer consumido `systemctl disable --now cia-j1-ops31-shadow-once.timer`; preservar claim, journald, SQLite REST e todos marcadores anteriores. Registrar status/histogramas na #482 e #429.
5. Se `shadow_observed_quarantined` com closed timestamp overrun, **não** corrigir `timestamp` do parser nem iniciar 24h. Se abstenção, categorizar e investigar offline sem reexecução automática. Única sonda não certifica 50 ativos, replay histórico, 24h ou trading.

## Aceite/limites

Testes offline `test_j1_ops31_shadow_timer.py`: target/lead, SHA/NTP/owner/concurrency, state symlink/permissions, claim exclusiva, exatamente 1 subprocesso, timeout, retorno sanitizado e contadores, templates sem recorrência, injeção de path, falhas não dão retry. CI Linux/docs + Windows/offline + Chrome/PAPER pré e pós-merge no SHA final. A aceitação **de código** não é a evidência real da VPS. OPS1 #429, J1 #2 e Top50 #319 permanecem abertas; sem ordens e sem habilitar collector 24/7.
