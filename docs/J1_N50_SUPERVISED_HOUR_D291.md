# J1/D291 — execução owner supervisionada de uma hora N50 (OFF por padrão)

## Contrato

D289 comprovou duas horas reais e 1.250 velas, mas não instalou um supervisor permanente. D290 trouxe auditoria owner com binding SHA do journal e política de relógio/renovação. D291 entrega **um único ponto de execução de pesquisa** reutilizando exatamente `run_current_ranked_epoch_once` (D287/M1), sem refazer a lógica de GET, cursor, SQL, digest ou single-writer.

`crypto_intelligence_agent.j1_n50_supervised_once.run_supervised_n50_once` verifica seis opt-ins, usuário non-root e paths separados, lê manifesto privado D287, e:
- Com journal existente, executa auditoria owner-only e exige resultado D290 `run_existing_epoch_once`, sem gap, scope drift, ou horário duplicado.
- Sem journal, aceita bootstrap **apenas** num diretório 0700 novo, comprovadamente vazio e não-symlink; não confunde corrupção ou lock abandonado com primeiro uso.
- Se o manifesto precisar ser renovado após 36h, bloqueia coleta e orienta renovação serializada em novo epoch. Não roda censo simultâneo ao writer e não substitui o journal.
- Quando autorizado, chama SOMENTE o writer D287/M1, que revalida escopo, hora, quota e lock; resultado do wrapper nunca certifica mercado, identidade, supervisão 24/7 ou ordens.

CLI: `python -m scripts.run_j1_n50_supervised_hour_once --manifest-directory /CAMINHO/SCOPE --output-directory /CAMINHO/NOVO-JOURNAL --allow-private-manifest-read --allow-private-readonly-audit --allow-public-network --allow-private-storage --confirm-region-and-personal-research --enable-n50-research-once`.

**Nenhuma unidade systemd, timer, instalação ou job VPS é criada por este código**. Automação/rotação, proteção global entre epoch e captura D286 e liberação operacional são próximas tarefas de #429. Coletor N2 existente deve permanecer intacto. Nenhuma ordem, credencial ou API privada.

Testes `test_j1_n50_supervised_once.py`: seis opt-ins, POSIX owner, caminhos separados, journal adulterado, falha de digest, bootstrap vazio, lock abandonado, delegação ao M1, flags inseguras, número de GETs e negação de trading, offline.
