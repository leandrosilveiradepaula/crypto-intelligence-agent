# J1/D290 — supervisão de N50 sem duplicar writer e sem release

## Motivo

D289 comprovou N50 real com manifesto de 50 contratos, 1.200 candles iniciais e incremento de 50 candles para 1.250 e dois checkpoints; o job finito acabou. O próximo risco não é revalidar a coleta, mas **operar depois do job**, sem deixar um manifesto envelhecer e sem coletar e recensear simultaneamente numa janela de apenas 14 minutos.

## Plano executável somente como avaliação inerte

`crypto_intelligence_agent.j1_n50_supervision.plan_n50_supervision` recebe manifesto selado e auditoria independente do SQLite e retorna uma **decisão pura**, sem IO. Reutiliza validadores D287 e as fronteiras de relógio M1. A decisão pode ser:

- `bootstrap_new_empty_epoch`: primeiro journal de epoch somente se um operador externo verificar diretório novo, privado e vazio; não afirma que a auditoria está ausente porque banco sumiu.
- `run_existing_epoch_once`: apenas se journal owner passou auditoria independente, 50 contratos, 24h+incrementos sem gaps, digest de scope confirmado, HH:01..HH:15, sem retroagir publicação e com todos os flags de trading desabilitados.
- `none`: janela errada, mesma hora já publicada, scope inválido, gap, adulteração, latência ou estado não verificável.
- `serialize_rotation_to_new_epoch`: após 36h, antes do limite D287 de 48h; o censo D286 de ~372 GET consome boa parte da janela UTC. **Não executá-lo em paralelo** ao writer N50. Rotação deve ter novo manifesto, novo SQLite e nova coorte; preservar antigos e reconhecer eventual horário sem PIT em vez de falsificar dados.

A política requer `journal_scope_digest_sha256` **obtido de forma independente** da tabela `scope` pelo dono do banco, pois o auditor legado não o expõe. Na ausência dessa evidência, falha fechado — não inventa binding. Não concede autorização de systemd, network, migração, banco, publicação ou ordens.

## Próxima etapa operacional, separada

1. O auditor owner-only D290 agora devolve apenas o digest do scope quando o replay SQLite íntegro passa (sem símbolos), com proteção 0700/0600. Validar primeiro o contrato na VPS via leitura independente antes de qualquer uso operacional.
2. Implementar transição de epoch e lock global que impeçam colisão entre censo de 12 minutos e 50 GETs da coleta; executar teste fake clock cruzando 36/48h, restart, crash e rotações.
3. Somente após CI e gate de instalação, propor serviço N50 próprio; **não substituir timer N2** existente. Medir continuidade real de 24h e drift da população, sem proclamar elegibilidade de trading.

Esta PR é código e testes **offline**. Os dois jobs reais D289 já foram concluídos e não são reexecutados por este plano. J1 #429/#319 permanecem abertos; D290 não é operação contínua.
