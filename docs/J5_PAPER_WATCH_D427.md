# D427 — Situação PAPER no painel (última sessão, sem falsa proteção)

## Qual funcionalidade muda para o usuário

O painel local J5 já mostra saúde das cotações N50, mas **saúde de mercado não comprova que uma posição PAPER foi acompanhada**. D427 acrescenta uma seção própria "Acompanhamento das posições PAPER". Depois de uma execução autorizada do operador D425, mostra **quantas rotas estavam configuradas**, cotações realmente encaminhadas ao motor AUTO4, eventos recusados, **novas reservas fictícias** e **eventos** que exigiram reconciliação.

O número de eventos de reconciliação NÃO é número de posições ou de ordens distintas. O estado aparece sempre como **"última sessão encerrada"**, jamais "stop ativo", "protegido" ou "trading ligado". Sem evidência disponível, após erro de leitura ou após 180 segundos, mostra **"Sem supervisão PAPER ativa"**. O resultado de uma sessão nunca comprova vigilância contínua 24×7, disponibilidade de stop nativo, execução, FILL, posição verdadeira, PnL ou lucro.

## Integração mínima com o motor existente

- **Produtor:** o CLI já existente `scripts.run_j4_current_paper_ws_once_d425` ganhou o par opcional `--allow-local-paper-watch-output --paper-watch-directory /diretorio/owner`. Continua exigindo todos os cinco opt-ins de acesso privado/WS/pesquisa/PAPER. Apenas no final da **sessão finita**, a partir do relatório D410/D391 já sanitizado, escreve `latest-paper-watch.json` em diretório existente POSIX 0700 do mesmo usuário não root. O arquivo owner 0600 é substituído atomicamente com `fsync`; não contém símbolos, IDs, preços, ordens ou caminhos. Uma exceção na sessão gera relatório novo **falha-fechada** sem dados financeiros nem alegar rollback de reservas. Sem o par de opções não existe nova leitura ou escrita.
- **Leitor:** `j5_paper_watch_d427.py` aplica checagem estrita de schema, tipos, counts, temporalidade, flags negativas, dono 0700/0600 e `O_NOFOLLOW` (incluindo inode após abrir o diretório). Desconhecido/expirado/symlink/hardlink/malicioso = rejeitar.
- **Loopback J5:** `scripts.serve_j5_local_readonly` pode expor **somente** `GET /api/paper-watch` via `127.0.0.1:8765`. Essa função é **desligada por padrão** e exige `--allow-paper-watch-loopback --paper-watch-directory /diretorio/owner`. Respostas 503/404/403/405 conforme ausência, permissão, host/origem/método. Não há CORS, endpoint de escrita, SQL, abertura de journal PAPER ou solicitação à Bybit.
- **Navegador:** `paper-watch.js` busca o JSON estritamente local até a cada 30 s, apenas no servidor local com host permitido, sem storage, WebSocket próprio, HTML arbitrário ou dados identificáveis. Falha ou expiração apaga a última amostra da tela; o histórico N50 segue independente.

Exemplos de flags (apenas **depois de gate operacional**, não instruções de deploy da VPS D423):

```sh
python -m scripts.run_j4_current_paper_ws_once_d425 \
  --state-directory /owner/j1-active \
  --private-paper-directory /owner/paper \
  --seconds 30 --max-sessions 1 --max-frames 100000 \
  --allow-private-pointer-read --allow-public-websocket \
  --confirm-personal-readonly-research --confirm-region-eligible \
  --allow-synthetic-paper-reservations \
  --allow-local-paper-watch-output --paper-watch-directory /owner/watch
```

```sh
python -m scripts.serve_j5_local_readonly \
  --allow-loopback-readonly-http \
  --allow-paper-watch-loopback --paper-watch-directory /owner/watch
```

Pastas PAPER e watch devem existir e ser **separadas do writer J1**. Nenhum comando deve ser executado pela conexão administrativa limitada ou como root. No momento não existe no serviço instalado um supervisor PAPER permanente. O recurso acima **não cria** timer, daemon, rota HTTP remota, chave de corretora, publicação, stop real, entrada nova, ordem ou FILL; mantém o custo R$0.

## Verificações e aceite

`tests/test_j5_paper_watch_d427.py`: rejeição de claims privilegiados, números falsos, campos extras, símbolos/IDs de dados originais, clock expirado, falhas de direitos POSIX/symlink/hardlink, substituição atômica de status de falha, endpoint loopback com host/origem/método e par de flags, navegação mobile Node com perda de conexão e invalidação imediata de estado antigo.

CI Linux + Windows + navegador precisa passar no SHA exato antes de integração no GitHub. Merge seguro é permitido sem deploy. **Release J5/J4 em VPS exige gate separado** e um operador não root com diretório aprovado; a conexão atual não pode executar como `cia-probe` e isso não será contornado. J1, monitor D423 e o SHA de serviço instalado não são modificados.

## Próxima fronteira funcional

Depois do status de última sessão, homologar supervisor de posições PAPER com janela contínua, reentrada/reconciliação segura e **liveness confiável por posição mantida**, com limiares de atraso, alertas reais e reconciliação de intents persistidas. Sem uma fonte persistente assim, nenhuma interface deve exibir "posição protegida". Evoluir J3 com taxas, spread, slippage, funding, exposição e liquidação, e avaliar retorno líquido ajustado ao risco; os thresholds artificiais usados na prova D426 jamais entram numa estratégia produtiva.
