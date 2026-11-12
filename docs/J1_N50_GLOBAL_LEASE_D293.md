# J1/D293 — lease global owner-only para N50, censo e writer sem colisão

## Objetivo

D289 comprovou N50 real 2h com 1.250 candles; D290/D291/D292 organizaram auditoria, execução supervisionada e recuperação no próprio fechamento. Falta serializar a etapa D286 (censo de ~372 GETs, aproximadamente 12 minutos) e a persistência D291 (~50 GETs) para não ocorrerem simultaneamente em HH:01..HH:15. O lock de M1 é por journal, não entre epochs nem entre censo e writer.

D293 introduz **um lock global compartilhado por todos os comandos N50 coordenados** e uma claim imutável de ação/target por hora UTC. O estado é privado (diretório 0700, arquivos 0600), com flock non-blocking, O_EXCL, fsync, validação de symlink/owner, SHA do destino e rejeição de conflito. A claim é registrada antes de qualquer GET e permanece após falha. Tentativa idêntica na mesma hora pode retomar (D292 + idempotência de M1), mas ação diferente ou destino diferente são bloqueados. Assim não podemos capturar novo ranking e coletar outra coorte no mesmo fechamento por vias coordenadas.

## Uso explícito e limites

O CLI `python -m scripts.run_j1_n50_coordinated_once` oferece:
- `capture_seal`: requer `--lock-directory`, `--manifest-directory`, `--allow-public-network`, `--confirm-region-and-personal-research`, `--allow-private-manifest-write`, `--enable-coordinated-n50-once`. Delega ao D286/D287 já existente com 2s/GET e prazo HH:15.
- `hourly_writer`: mesmos lock e opt-ins de rede/pesquisa, além de `--output-directory`, `--allow-private-storage`, `--allow-private-manifest-read`, `--allow-private-readonly-audit`. Delega ao D291/D292/M1 existente, sem novo coletor.
- Em ambos: owner POSIX não-root, paths absolutos isolados, janela fechada HH:01..HH:15. Sem defaults de rede ou escrita. Nunca permite negociar.

**Não é daemon nem serviço instalado.** A coordenação só abrange comandos que usam *este mesmo* lock root. O timer N2 antigo, execuções diretas D287/M1 e jobs anteriores não passam por D293; não há garantia de exclusão com eles. Qualquer instalação de um serviço N50 precisa trocar seu ponto de entrada para este coordenador e passar por gate operacional separado, verificação de coortes, segurança e rollback. A renovação em 36h é decisão do D290 e exige novo manifesto/journal, sem sobrescrever epochs anteriores; D293 **não agenda nem inicia a rotação automaticamente**. Claims de horas passadas preservam a evidência de tentativa; não são PIT nem prova de continuidade.

## Critérios de validação

`tests/test_j1_n50_global_lease.py`: ações distintas bloqueadas na mesma hora, mesmo alvo idempotente com claim imutável, lock concorrente na mesma PID, claims adulteradas/symlink, 0600/0700, opt-ins sem I/O, clock fora da janela e path inválido. Regressão D287–D292 e CI Linux, Windows e Chrome/PAPER SHA exato. Merge sem deploy. Em VPS somente inspeções e, após gate, piloto controlado; nenhuma autorização de trading.
