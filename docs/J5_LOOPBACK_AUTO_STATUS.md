# J5/APP-SYNC1 — atualização automática N50 exclusivamente em loopback

## Resultado visível no aplicativo
O aplicativo `web/app/index.html` (J5/MVP1) mantém os fluxos PAPER locais e o importador de JSON, mas, quando é servido em **`http://127.0.0.1:8765/`** ou **`http://localhost:8765/`**, consulta `GET /api/n50-progress` na **mesma origem**, no carregamento, no botão "Atualizar dados locais" e a cada 60 segundos. O backend chama **apenas** o log do serviço N50 já existente, lê uma janela limitada e invoca `export_n50_journald_progress` (#628) para produzir `j5-n50-ws-log-progress-v1`, que já tem validação na tela. Nada de preço/símbolo/digest na resposta. Se falhar, a tela zera a contagem exibida e sinaliza "Fonte local indisponível" (não mantém dado antigo como se fosse atual).

**A prévia `file://` continua 100% offline**: não chama endpoint, não abre rede, permite importar manualmente e manter cenários PAPER no `localStorage`. Na sessão com servidor local, importar manualmente um relatório N50 assume prioridade até recarregar o aplicativo. A importação J2 também continua manual; estratégia ou sinal automático não foi adicionado.

## Segurança e limites de acesso
- `scripts/serve_j5_local_readonly.py`: servidor de biblioteca padrão Python, **somente opt-in em primeiro plano**, bind fixo `127.0.0.1:8765`, sem flags de rede pública. Refusa `Host` não correspondente e `Origin` remoto para dificultar DNS rebinding; não adiciona CORS/cookie. Sem POST/PUT/DELETE/OPTIONS, sem endpoint de ordens.
- Rotas permitidas: `/`, `/index.html`, `/app.js`, `/engine.js`, `/style.css`, `/api/n50-progress`. Sem listagem de diretório, path variável, symlink ou arquivos em diretórios privados.
- HTTPS público, portas externas, login, credenciais, proxy reverso e integração com exchange **não** são instalados. HTTP sem TLS é **apenas loopback**, não deve ser exposto via firewall, URL pública ou bind 0.0.0.0. Acesso do celular fora desse host exige um canal privado autenticado **aprovado separadamente**, como um túnel administrado pelo titular. Usar a interface não cria esse túnel.
- Somente `journalctl` (argv fixo, unidade WS, últimos 26h, até 128 mensagens, timeout 6s, volume total <= 1MiB); stderr e erros do sistema nunca são mostrados. `GET` só exporta contagens e horas UTC, nunca dados completos da coleta. Sem rede de saída, SQLite, ordem, migração, systemctl, agendamento, alterações na VPS ou gastos.
- CSP do aplicativo permite `connect-src 'self'` **apenas** para o GET no mesmo loopback; o JS confere protocolo HTTP, porta 8765 e hostname 127.0.0.1/localhost antes de buscar. O fluxo `file://` continua sem requisições.

## Operação local futura (não realizada nesta entrega)
Depois de instalar um checkout aprovado em ambiente autorizado que possa **ler os logs**, o operador inicia no terminal foreground:

```bash
python -m scripts.serve_j5_local_readonly --allow-loopback-readonly-http
```

A URL local é `http://127.0.0.1:8765/`. No computador do operador, isso é utilizável diretamente se o processo rodar no mesmo computador; se o processo rodar na VPS, `127.0.0.1` refere-se **à VPS**, portanto o celular/computador do titular **não** terá acesso diretamente. Não liberar publicamente nem tentar operar esse código na VPS sem gate de release e de acesso. Falta de permissão de journald = 503 e zero dados falsos. O script não instala timer, serviço ou tarefas em segundo plano.

## Testes e aceite
- `tests/test_j5_local_readonly_server.py`: subprocess único com argv fixo, sem shell nem stdout privado; 24 slots do projetor existente, auditoria D323 false, falha 503, Host spoof/DNS rebinding, métodos de escrita 405, paths não permitidos 404 e CSP/CORS desabilitado.
- `tests/test_j5_product_app_mvp.py`: contrato de CSP e fetch limitado ao hostname/porta local, aritmética PAPER preservada.
- `scripts/audit_j5_product_app_browser.py`: preserva QA `file://` em quatro viewports sem rede, mais browser Chromium em loopback mockado com primeiro GET 2/24, refresh e falha da fonte sem estado stale. Sem feed de exchange ou dados privados em CI.
- CI Linux/docs, Windows/offline e PAPER/mobile, SHA exato, PR/merge sem deploy. J1 D323 24h, rotação 36h e identidade crypto-only permanecem gates independentes.

**Status de produto:** desenvolvimento de integração local, não entrega de aplicativo móvel remoto/hospedado, não habilita entradas ou saídas reais. Custo adicional R$ 0,00. Issue #630, parent J5 #6.
