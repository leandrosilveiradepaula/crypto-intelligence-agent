# J6 D430 — Observador externo de um ensaio PAPER finito

## Objetivo e limite

O monitor D429 detecta silêncio do ticker da posição enquanto o receptor WebSocket está vivo, mas não detecta o travamento do próprio receptor quando ele não retorna ao callback. O D430 adiciona **um processo pai separado** que executa exatamente um ensaio finito já disponível em D428, aplica limite rígido de tempo e examina o retorno **junto com o arquivo owner D427**. Falhas não reiniciam o filho nem reemitem intenções financeiras. O arquivo D427 é colocado preventivamente em `finite_paper_lease_failed_closed` antes de iniciar o filho.

A implementação utiliza `subprocess.run` com módulo/argumentos fixos e `shell=False`; stdin não é compartilhado, stdout é validado no limite de 8192 bytes e stderr não é divulgado. O subprocesso tem timeout máximo `max_total_seconds + 10`. Em caso de timeout o Python encerra e espera o processo direto; não constitui um watchdog de toda árvore de processos ou do sistema operacional.

## Segurança

- Oito opções booleanas explícitas: as sete já existentes em D428 + `--allow-child-process-watchdog`; sem todas, nenhum socket ou escrita é iniciada.
- Apenas usuário não root em POSIX, diretórios owner pré-existentes separados; não utilizar gateway administrativo para trocar UID nem contornar DAC.
- Sem signer, conta, credencial, ordem, fill, liquidação, live, testnet, migração, cron, serviço, timer, mudança da J1 ou instalação na VPS.
- O pai **não inspeciona SQLite**, não altera os journals AUTO4, não implementa backoff/restart e jamais afirma que posições estão protegidas.
- Para classificar um ensaio finito como encerrado é necessário retorno zero, JSON válido count-only com lease count esperado, flags financeiras false e confirmação do **mesmo timestamp** no relatório owner D427 recente, com posições acompanhadas e cotação encaminhada.
- Timeout/crash/retorno incoerente/documento terminal faltante ou inconsistente → D427 fail-closed atômico 0600. Se essa publicação falhar, retorna `failclosed_publication_unavailable` e o leitor J5 existente degrada após expiração (até 180s).
- Se **o processo pai** morrer, D430 não consegue publicar; por isso a próxima etapa J6 é watchdog OS independente (systemd ou equivalente), detecção por heartbeat/progresso persistente, política de alarme e reconciliação UNKNOWN. Nenhuma garantia 24×7.

## Testes e aceite

`tests/test_j6_paper_child_watchdog_d430.py` valida configuração e JSON estrito, tentativa sem opt-in, crash, timeout, erro de spawn, exit zero com saída falsa e arquivo terminal incompatível, com mocks sem rede. Exigir CI Linux/docs/Python e Windows/PAPER/Chrome conforme contratos e revisar SHA. Não executar real na VPS sem gate operacional de piloto separado. Nenhuma operação financeira.

## Exemplo de operação *somente após* gate proprietário

```bash
python -m scripts.run_j6_paper_child_watchdog_d430 \
  --state-directory /owner/j1-active \
  --private-paper-directory /owner/paper \
  --paper-watch-directory /owner/paper-watch \
  --max-leases 3 --lease-seconds 20 --max-total-seconds 90 \
  --allow-private-pointer-read --allow-public-websocket \
  --confirm-personal-readonly-research --confirm-region-eligible \
  --allow-synthetic-paper-reservations --allow-multiple-finite-leases \
  --allow-paper-watch-output --allow-child-process-watchdog
```

Os caminhos acima são ilustrativos e não autorizam execução. O objetivo do D430 é validar que **um processo externo percebe falhas do filho**, não prometer proteção financeira. Custo adicional R$0.
