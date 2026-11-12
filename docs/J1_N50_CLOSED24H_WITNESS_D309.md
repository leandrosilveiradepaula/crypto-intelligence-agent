# J1/D309 — observador do N50 por 24 horas fechadas, sem assumir serviço saudável

## Necessidade operacional

D306 recuperou N50 em nova epoch após um HALT legítimo; em 12/11/2026, o primeiro fechamento da nova epoch foi auditado com integridade e N2 permaneceu desligado. D299 já faz replay completo do SQLite M1 de todas as epochs, valida PIT, horários, digests, o arquivo histórico HALT com D304 e conta as últimas 24 horas efetivamente publicadas. **Por desenho, D299 nunca altera a flag `continuous_collector_verified=false`.** Para a J1 progredir sem confundir um timer ativo com prova de dados reais, D309 acrescenta um testemunho explícito de 24 fechamentos e estado atual de isolamento, reutilizando D299. Não instala serviço.

## Entrega

- Função pura `evaluate_n50_24h_witness` exige o relatório D299 validado, janela de 24h com **24 PITs reais distintos**, último fechamento UTC esperado e registros sem divergências. Não inventa candles e não reinicia/ou reusa epochs.
- Consulta somente leitura a **quatro unidades systemd literais**, sem shell: `cia-j1-n50-managed.timer`, `cia-j1-n50-managed.service`, `cia-j1-rest-hourly.timer`, `cia-j1-rest-hourly.service`. Campos e enumerações são restritos e saída recebe limite de 2048 bytes e timeout de oito segundos. Não aceita unidade nem caminho de entrada do operador.
- Exige N50 timer `loaded/active/waiting/enabled`, N50 service último exit `success/0` e `inactive/dead`, N2 timer `loaded/inactive/disabled` e N2 service inativo. Durante serviço N50 em execução não há atestado prematuro.
- Em caso de failback, timers simultâneos, erro do serviço, checkpoint ausente/antigo ou integridade negada, a saída **não** afirma continuidade. Se menos de 24 fechamentos foram vistos, retorna `accumulating_24_closed_hours`.
- Após os 24 PITs fechados, `closed_24h_pit_verified=true` significa somente a janela PIT completa, **não** `continuous_collector_verified`, que segue `false` até o aceite mais amplo. A renovação causal >=36h ainda depende de observação material separada. Histórico HALT e lacunas anteriores fora da janela continuam contados no relatório; não são ocultados.
- Sem alertas persistentes nesta entrega: é instrumento de diagnóstico executado uma vez, ainda não um watchdog ativo. Não cria cron, systemd timer, job ou automação.
- Sem símbolos, candles, custos reais, segredos ou saída de `journalctl`. Zero alterações em SQLite, serviço, VPS, rede ou ordens.

## Invocação offline/owner (somente após CI e escolha do SHA revisado)

```sh
/home/cia-probe/agent/ws-venv/bin/python -m scripts.inspect_j1_n50_24h_witness_once --allow-private-readonly-audit --enable-closed24h-witness
```

O comando acima é **referência para execução futura** em checkout owner aprovado e íntegro; não foi disparado por esta PR na VPS. Rodar como `cia-probe`, não como root. Padrão sem flags retorna `owner_optin_required` sem acesso à base. O código usa raiz fixa privada D296, sem argumentos de caminho ou URL. `exit 0` significa observação classificada (inclusive janela ainda incompleta); **somente a flag específica** `closed_24h_pit_verified=true` atesta 24 fechamentos. Falha crítica dá exit 65.

## Evidências e gates

- Testes adversariais `tests/test_j1_n50_24h_witness.py` e `tests/test_j1_n50_24h_witness_cli.py`: 23 versus 24 PIT, fase UTC HH:00 e HH:01, missing current, relógio, ambiguidades de calendário, archived PIT gaps, N2 failback, timers concorrentes, serviço falho/em execução, retorno adulterado, systemctl com campos duplicados/extra, tipagem, path e opt-ins.
- CI Linux/docs, Windows/offline, Chrome/PAPER no SHA final, revisão e merge sem produção. **Não afirmar testes executados antes das evidências do Actions.**
- Depois da integração, D309 será executável na VPS apenas com atualização controlada do checkout de pesquisa e gates operacionais. Não fazer release, migrations nem alterações em unidades para usar este monitor.
- J1 #429 e #319 continuam abertas. Prova de 24h por si só não estabelece rotação >=36h, identidade crypto-only independente, rentabilidade ou ordens.

**Decisão D309:** provar completude horária real de modo independente do sucesso instantâneo do systemd, preservando o incidente histórico e evitando aumento de complexidade na coleta; estender para testemunho de rotação somente com evidência própria e revisão separada.
