# J1/OPS1 — Observabilidade privada e fail-closed da retomada EXIT5

## Contrato da primeira entrega da issue #429

O worker owner-only da J1/EXIT5 já grava três artefatos JSON no mesmo diretório privado: `exit5-resume.log`, `exit5-result.json` e `exit5-audit.json`. O observador `scripts.observe_private_j1_exit5` lê **somente esses três arquivos**, não abre o SQLite e não cria sockets, tarefas, timers, processos ou transações. Não depende do terminal ou da conversa para **registrar** o resultado do worker: o próprio worker continua sendo responsável pelos artefatos. O observador permite uma leitura normalizada e sanitizada da evidência **após ela existir**, sendo o primeiro contrato para um futuro painel PT-BR e alertas locais.

Exemplo owner-only, **após o código ser integrado e com um diretório real previamente autorizado**:

```bash
python3 -m scripts.observe_private_j1_exit5 \
  --directory /CAMINHO/ABSOLUTO/PRIVADO/DA/COLETA \
  --allow-private-readonly-status
```

Requisitos: POSIX, titular do diretório e dos três arquivos, diretório 0700, arquivos 0600 e sem symlinks/hardlinks. Limites de leitura: log 1 MiB/2000 linhas; JSONs 64 KiB. Falhas de tamanho/permissão/estrutura retornam somente erro sanitizado, **sem echo de path, tokens, símbolos, OHLC, preço, URLs ou payload de mercado**. A ausência de um arquivo é um estado válido de **pendência**, não prova de que um PID segue vivo.

## Máquina de decisão e níveis de evidência

1. `sem_resultado_final`: não há recibo de conclusão; não significa worker executando.
2. `progresso_informado_sem_resultado`: existe progresso JSON, mas sem recibo final.
3. `aguardando_proximo_fechamento_informado`: o log contém a fase de espera. **Não é atestado de PID ativo**; o próximo candle ainda não foi auditado.
4. `falha_registrada_pelo_worker`: ao menos um exit code terminou diferente de zero; mantém histórico e exige diagnóstico, sem retry automático.
5. `resultado_inconsistente_sem_aceite`: código de saída zero sem todas as outras evidências; impede promoção indevida.
6. `concluido_amostra_revisada_auditada`: somente se `resume_exit_code=0`, `audit_exit_code=0`, status final do worker `private_j1_two_distinct_updates_verified_not_top50`, **e** auditoria read-only independente apresentar integridade/replay/720h originais positivos, mínimo de 720 horas armazenadas por ativo, >=3 PITs, pelo menos 1 par de PITs consecutivos, 50 ativos selecionados e >=36000 candles. Churn permite 50-52 ativos armazenados e total maior de candles.

Apenas o próprio observador usa o status acima; a decisão de **homologar a J1 #2** continua condicionada à prova de mercado completo #319. Os seguintes flags **nunca** viram verdade automaticamente: `marketwide_top50_verified`, `live_trading_authorized`, `worker_running_verified`. Portanto sucesso de 50 membros revisados não é prova de Top50 global, licença, PnL ou ordens. Não se afirma que a origem do log atesta o provedor; arquivos são evidência local owner-only.

## Plano de evolução da issue #429 (ainda NÃO implementado)

- Serviço supervisor processado na VPS, com lock de escritor e inicialização por sistema, sem dupla captura e sem migração de dados atuais.
- Fluxo WebSocket contínuo, validado por `bybit_public_ws_once`, `bybit_ws_offline_pipeline` e `bybit_closed_stream_cache`; extensão controlada a vários símbolos, resubscribe/heartbeat, zero persistência de vela aberta.
- Reconciliação REST compacta somente para lacunas, orçamento/rate-limit, sem retry em `10006`, preservação de PIT real e monitor de defasagem por símbolo.
- Visualização PT-BR dos estados de saúde e alertas locais deduplicados, sem divulgar dados privados. Serviço deploy/enable e qualquer acesso live necessitam gates específicos; código e testes CI, por si, não constituem serviço 24/7 em produção.

## Testes e implantação

`python3 -m unittest discover -s tests -p 'test_j1_ops_status.py' -v` exercita arquivos inexistentes, eventos incompletos, recibos de sucesso/falha, auditoria divergente, churn, JSON adulterado, symlink/hardlink, permissões, limites e exclusão de campos sensíveis. Windows executa skips POSIX esperados. A publicação do código **não altera** PID, paths, SQLite, cron/systemd, backend, nenhuma credencial ou worker atual. Não executar uma nova coleta para testar status.