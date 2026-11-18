# D428 — acompanhamento PAPER em sessões consecutivas, sem daemon e sem ordens

## Resultado funcional desejado

D425 já observa posições persistidas durante **uma única sessão pública de até 60 segundos**. O AUTO4 evita que um stop pendente gere reservas duplicadas; o D427 torna as contagens dessa sessão visíveis no painel local. O passo seguinte precisa distinguir uma ligação efetiva de um acompanhamento interrompido, preservar o mesmo estado PAPER entre reconexões e interromper o ensaio quando não houver evidência atual do contrato mantido.

D428 executa **2 a 4 sessões finitas consecutivas**, cada uma com **10 a 60 segundos**, sob **um único lock do diário AUTO4** `exclusive_paper_operator_lock` já existente. A duração total é limitada a no máximo 300 segundos. Não cria novo ledger, sinais, feed N50, estratégia, posição, ordem, fill ou native stop. Não instala serviço, cron, timer, processo 24×7 ou túnel. Não lê conta nem dados privados da Bybit; usa o mesmo WS público D410/D390/D386 e o owner J1 apenas leitura.

O **mesmo roteador D391 permanece na memória entre leases**, incluindo o watermark de tempo da exchange. Uma nova conexão precisa repetir subscribe ACK + snapshot; replays retroativos depois de uma reconexão não são aceitos. Todas as intenções AUTO4 permanecem no diário original, inclusive reserva desconhecida: **ACK de assinatura ou tick público nunca vira FILL ou cancelamento de reserva**. O lock impede que outra execução D425 escreva no mesmo diário no intervalo entre leases.

## Proteção fail-closed que o teste verifica

- Se faltar opt-in, não lê owner, não cria lock, não toca PAPER, não abre socket nem publica watch.
- Antes da primeira conexão, publica estado privado D427 `finite_paper_lease_failed_closed` para impedir reutilizar um resumo de sessão anterior como se fosse atual.
- A cada lease, o status público é validado com o projetor D427. Os contadores D391 são **cumulativos** porque o roteador permanece vivo; D428 calcula a diferença por lease antes de publicá-los, sem reiniciar o estado financeiro. Contagens regressivas, claims live ou formatos desconhecidos abortam.
- A validade de uma posição é independente da saúde das demais altcoins N50. Porém para aprovar a **própria lease de pesquisa**, **todos os contratos PAPER configurados precisam ter cotação própria pós-ACK recente (≤3 s)** ao seu fim. Uma cotação que ocorreu há 20 segundos não satisfaz acompanhamento atual, mesmo com muitos frames no começo. Isso não atesta que não houve lacuna intermediária.
- Sem cotação recente de algum contrato mantido, erro de socket, erro de SQLite, rotação da epoch owner, clock regressivo, contador incompatível, intervalo entre leases maior que o limiar ou orçamento temporal esgotado: interrompe e publica **falha fechada**, sem criar novas ordens, negar débito ou repetir uma intenção desconhecida. Se até a publicação falhar, a leitura J5 expira o arquivo por idade e nunca afirma proteção.
- Cada sessão terminada é apenas uma amostra **FINITA** de cobertura PAPER, observável no D427. A tela diz **“última sessão encerrada”**; não há etiqueta “robô protegido” nem liveness financeiro positivo. Alertas nessa etapa são estados **de falha, lacuna ou reconciliação**, não confirmação de execução.

## CLI para homologação futura — NÃO é um comando para rodar no gateway atual

Requer usuário não root da própria pasta de posições, J1 e watch em POSIX, pastas 0700 do mesmo owner, **três diretórios separados**, arquivo de regras D425 já preenchido e posição PAPER existente. Diretórios J1 e AUTO4 **não recebem o arquivo watch**. Requer autorização de pesquisa/WS público e privacidade regional, sete opt-ins independentes:

```sh
python -m scripts.run_j4_paper_bounded_trial_d428 \
  --state-directory /owner/j1-active \
  --private-paper-directory /owner/paper \
  --paper-watch-directory /owner/paper-watch \
  --max-leases 3 --lease-seconds 20 --max-total-seconds 90 \
  --max-gap-ms 5000 --max-frames-per-lease 25000 \
  --allow-private-pointer-read \
  --allow-public-websocket \
  --confirm-personal-readonly-research \
  --confirm-region-eligible \
  --allow-synthetic-paper-reservations \
  --allow-multiple-finite-leases \
  --allow-paper-watch-output
```

Saída stdout contém apenas `leases_attempted`, `leases_with_fresh_position_quotes`, `quotes_forwarded_to_paper`, `synthetic_exit_reservation_events`, `reconciliation_required_events`, `largest_interlease_gap_ms`, `public_ws_reconnect_events`, `last_terminal_watch_at_ms` e flags **permanentemente false** para ordens, contas, proteção, cobertura contínua e aprovação de live. Não há símbolos, preços, IDs, chaves ou caminhos. O D427 continua consumindo `latest-paper-watch.json` com expiração de 180s e GET 127.0.0.1 protegido por flags próprias.

## Testes e critérios de aceite

`tests/test_j4_paper_bounded_trial_d428.py` usa relatório D410 fake e o **lock D425 real** em diretórios temporários POSIX, sem qualquer socket real. Verifica o mesmo roteador em leases sucessivas, impossibilidade de obter segundo flock durante toda a jornada, diferença correta de contadores acumulados, contingência de stop/reconciliação sem falso FILL, rejeição de contratos stale no fim, desconexão, mudança da coorte J1, lacuna interlease e rollback proibido. Testa sete opt-ins antes de qualquer recurso e bloqueio de watch dentro de pasta financeira. Um teste específico do D391 verifica que o contador de contratos mantidos frescos cai a zero após uma sessão WS nova, sem transportar snapshot antigo.

Para aceitar integração: CI Linux/docs/Python, Windows/offline e navegador no SHA exato, revisão e merge sem release. **Não executar na VPS produtiva sem gate de piloto com o owner real**: o gateway administrativo atual não pode trocar UID para `cia-probe`. O release de supervisor periódico é diferente deste merge e continua bloqueado. Não implantar serviços por tentativa de resolver permissões. Nenhuma ordem real e custo adicional **R$0**.

## O que ainda falta para um supervisor real

D428 tem poucos minutos de cobertura e **não** garante proteção durante a troca de socket, lacunas intralease, reinício do processo, queda da VPS ou fora do teste. Para um serviço PAPER 24×7 é necessário liveness por posição ao longo de todo o tempo, indicadores de disponibilidade com SLO, alerta de parada independente, política segura de reinício/lock único, reconciliação explícita de intents UNKNOWN, circuit-breaker de novas entradas, teste de custos/slippage/funding/liquidação no J3 e gate operacional J6. A autorização de ordens financeiras reais é **outro gate futuro**, nunca implicado por PAPER.
