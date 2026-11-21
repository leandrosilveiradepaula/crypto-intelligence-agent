# D446 — painel PAPER com posições persistidas no SQLite

A interface mobile agora pode mostrar **as posições PAPER efetivamente persistidas no diário AUTO4** sem importar manualmente um JSON. O servidor local reutiliza o leitor `inspect_paper_positions` em uma só transação SQLite de leitura, a seleção explícita do manifesto D425 e o contrato de UI `paper_positions_snapshot_v1` D407. Nenhuma posição é criada nem alterada por uma leitura.

Para habilitar em ambiente owner não-root, o servidor loopback `scripts.serve_j5_local_readonly` precisa das opções independentes `--allow-loopback-readonly-http --allow-owner-paper-positions-loopback --owner-paper-positions-directory /PASTA_OWNER_PRIVADA`. Sem opt-in, endpoint `GET /api/owner-paper-positions` devolve 503 sem tocar nos dados. Não há GET de internet, cookies, CORS ou endpoint de ordem.

A página, quando aberta no mesmo `127.0.0.1:8765`, consulta a projeção a cada 15s com `credentials: omit`, no-cache e sem redirects, e valida todos os saldos e flags de segurança usando o verificador D407 já existente. A importação manual continua funcionando quando o servidor não está habilitado. Dados são em memória da aba, nunca enviados para serviços externos ou usados para tomar decisões de trading.

Limitações: loopback exige acesso local/túnel privado separadamente autorizado; o site não expõe um console remoto na internet; dados são do jornal PAPER, não de conta da Bybit. O worker D444/D445 pode criar reservas PAPER, mas a página nunca chama métodos de escrita ou altera posições. Não há prova de stop nativo, saldo real, funding, retorno ou cobertura 24×7.

Testes: dois contratos (BTC/ETH) selecionados pelo manifesto owner, journal 0600 e pasta 0700, rejeição de permissões/symlink, endpoint GET-only, host allowlist, falha indisponível sem segredos, browser JS sem storage e importação manual preservada.
