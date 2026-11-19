# D437 — piloto finito público Bybit (pesquisa isolada)

**Estado em 18/11/2026:** comando de operador versionado; nenhuma sessão pública foi executada nesta entrega. A issue #677 exige feed contínuo N50 e não é concluída por este piloto.

## Gates e limites

- **Pesquisa somente de BTCUSDT**, assinando os 50 tópicos `kline.60` da seleção N50 atual da J1 já revalidada; WebSocket público linear, sem credenciais, ordens, PAPER, alterações de J1, timer, serviço ou release. A inscrição N50 não prova cobertura de mercado.
- Quatro flags explícitas para rede e pesquisa: `--allow-public-network --allow-public-websocket --confirm-personal-readonly-research --confirm-region-eligible`; mais `--allow-private-pointer-read` para leitura exclusiva do owner J1. A elegibilidade regional e de uso pessoal deve ser verificada pelo operador. Não presumir por ser cliente Bybit.
- Executar com owner POSIX não-root; saída privada 0700 fora da árvore de estado J1, journal isolado, sem alterar arquivos/timers J1.
- D438 carrega o **escopo tipado existente** da coorte N50 J1: valida pointer e cache owner, digests, timestamps, exatamente 50 instrumentos, presença de BTCUSDT e estabilidade da revisão do epoch. Não consulta REST nem reclassifica ativos. Isso é origem local provisória, **não autenticação independente da exchange**.
- Um manifesto manual pode continuar sendo validado em testes offline, mas `--scope-file` **não autoriza rede** no piloto; evita capturas artificiais/fictícias.
- Orçamento padrão de 240 segundos, 24.000 frames, uma sessão sem reconnect. Os parâmetros são limitados pelo WSRunBudget.

## Comando (modelo, não autorização para executar)

```bash
python -m scripts.run_j2_public_kline_session_d437_once \
  --state-directory /CAMINHO/ESTADO-OWNER-J1 \
  --output-dir /CAMINHO/PRIVADO-SEPARADO \
  --allow-private-pointer-read \
  --allow-public-network --allow-public-websocket \
  --confirm-personal-readonly-research --confirm-region-eligible
```

O escopo vem da própria coorte atual já revalidada da J1, sem arquivo manual de metadados. Os diretórios de saída e de estado J1 devem ser disjuntos. O programa cria um diretório novo, um journal SQLite separado e uma projeção J5 privada terminal. Um ACK genuíno sem fechamento produz somente `public_subscription_ack_observed_unverified`; com atualizações abertas, `public_open_updates_observed_unverified`; um close só é declarado quando o supervisor conclui a sessão sem erro. Falhas posteriores a closes causam `public_session_abstained`. Nenhuma dessas evidências equivale a fonte autenticada ou sinal autorizado. Não preencher as 24 horas exigidas com dados fictícios.

## Evidências e próximos passos

- Commit inicial confirmado `fcb34fe7b308d313990f5c68d0c80b9721fe3fa8` na branch `codex/issue-677-public-kline-session`.
- Commit anterior `b5c4f2e4c93ea4b8d6fd4bdec1df05bbca2f344f`: CI Linux 3.403 OK, Windows 3.403 OK (558 skips), mobile/Chrome SUCCESS. A integração D438 exige repetir CI e revisão de SHA exato; o piloto público real permanece pendente.
- Gateway MCP da VPS respondeu, mas a leitura do checkout `/home/cia-probe/agent/repo` retornou `Permission denied`; sem execução pública e sem modificação dos serviços da J1.
- Para autorizar piloto: revalidar a origem/frescor da coorte owner J1, conferir direitos/elegibilidade regional, acesso do owner à VPS e diretório de pesquisa isolado, executar os gates explícitos e registrar somente resumo sanitizado com SHA exato e horário UTC.
- Próximo valor real do produto: ticker intrahorário e N50 dinâmico persistente, monitor de posições fora do N50, PAPER orientado a eventos e avaliação J6. O piloto finito não substitui isso.
