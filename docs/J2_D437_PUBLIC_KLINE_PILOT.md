# D437 — piloto finito público Bybit (pesquisa isolada)

**Estado em 18/11/2026:** comando de operador versionado; nenhuma sessão pública foi executada nesta entrega. A issue #677 exige feed contínuo N50 e não é concluída por este piloto.

## Gates e limites

- BTCUSDT kline.60 exclusivamente; WebSocket público linear, sem credenciais, ordens, PAPER, alterações de J1, timer, serviço ou release.
- Quatro flags explícitas obrigatórias: `--allow-public-network --allow-public-websocket --confirm-personal-readonly-research --confirm-region-eligible`. A elegibilidade regional e de uso pessoal deve ser verificada pelo operador. Não presumir por ser cliente Bybit.
- Executar com owner POSIX não-root; diretório privado 0700, manifesto 0600, sem links simbólicos, JSON duplicado ou decimal em float.
- O manifesto de escopo é fornecido e revisado localmente, exige `registry_variant=expanded-13`, hash de registro conferido, instante não futuro e idade máxima de sete dias. A estrutura do manifesto não prova que os dados foram obtidos da exchange. Não derivá-lo da fixture histórica de demonstração para fazer uma alegação real.
- Orçamento padrão de 240 segundos, 4096 frames, uma sessão sem reconnect. Os parâmetros são limitados pelo WSRunBudget.

## Comando (modelo, não autorização para executar)

```bash
python -m scripts.run_j2_public_kline_session_d437_once \
  --scope-file /CAMINHO/PRIVADO/manifest.json \
  --output-dir /CAMINHO/PRIVADO \
  --allow-public-network --allow-public-websocket \
  --confirm-personal-readonly-research --confirm-region-eligible
```

O arquivo precisa ser um snapshot de pesquisa revisado, atual e privado, não um sample fabricado. Os diretórios devem ser de pesquisa isolada do owner. O programa cria um diretório novo, um journal SQLite separado e uma projeção J5 privada terminal. A ausência de candle confirmado/ACK mantém abstenção. Não preencher as 24 horas exigidas com dados fictícios.

## Evidências e próximos passos

- Commit inicial confirmado `fcb34fe7b308d313990f5c68d0c80b9721fe3fa8` na branch `codex/issue-677-public-kline-session`.
- CI, revisão de código e demonstração real ainda precisam ser comprovadas; nenhum merge por inferência.
- Gateway MCP da VPS respondeu, mas a leitura do checkout `/home/cia-probe/agent/repo` retornou `Permission denied`; sem execução pública e sem modificação dos serviços da J1.
- Para autorizar piloto: obter evidência da origem e frescor do escopo, conferir direitos/elegibilidade regional, acesso do owner a área isolada, testar o comando e registrar somente resumo sanitizado com SHA exato e horário UTC.
- Próximo valor real do produto: ticker intrahorário e N50 dinâmico persistente, monitor de posições fora do N50, PAPER orientado a eventos e avaliação J6. O piloto finito não substitui isso.
