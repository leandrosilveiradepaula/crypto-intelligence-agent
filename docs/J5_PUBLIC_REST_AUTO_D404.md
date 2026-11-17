# J5 D404 — atualizações automáticas de preços REST públicos no painel privado

## Ganho funcional

O mesmo console em português que já exibe N50, pesquisa e cenários PAPER pode agora **atualizar a amostra pública da Bybit automaticamente**, mas somente quando aberto pelo servidor existente em `http://127.0.0.1:8765/` e quando seu administrador **optar explicitamente** por acesso REST público.

Ao carregar a tela, e depois a cada 60 segundos, o navegador pede `GET /api/bybit-public-price` ao servidor na mesma origem. O servidor executa no máximo **uma consulta HTTPS pública à Bybit por minuto** para todos os navegadores atendidos, independente de quantos clientes peçam atualização, e usa o cliente REST existente D403/J1. Mostra último preço, mark, melhor compra/venda de 1 a 50 contratos definidos previamente, mais timestamp de cada amostra. Nunca consulta endpoints de conta ou ordens.

**Não é streaming WebSocket nem motor de stops.** Preços não alimentam automaticamente o gestor PAPER, não alteram exposição, saldo, lucro, alavancagem ou planos de saída; nenhuma execução financeira é permitida.

## Ativação local explícita (não implantada nesta entrega)

Exemplo de inicialização *em primeiro plano* de um checkout aprovado, somente no próprio computador do operador:

```sh
python -m scripts.serve_j5_local_readonly --allow-loopback-readonly-http --allow-public-rest-samples --market-symbols BTCUSDT,ETHUSDT
```

O comando não instala daemon, timer nem proxy. O servidor continua ouvindo **apenas** `127.0.0.1:8765`, com Host/Origin allowlist e CSP já existentes. `file://` permanece completamente offline; uma porta remota, origin externo, POST, path não allowlisted ou requisição sem as flags de opt-in não habilitam acesso à corretora. Os símbolos devem ter sido admitidos separadamente: um sufixo USDT não comprova crypto-only nem Top50.

Sem `--allow-public-rest-samples`, o novo endpoint retorna HTTP 503 sem usar a rede. A opção de habilitar REST sem `--market-symbols` válidos aborta **antes do bind HTTP**. Não é possível apontar uma URL arbitrária ou escolher endpoint de ordens: o único caminho remoto permanece `GET https://api.bybit.com/v5/market/tickers?category=linear` via transporte já controlado.

## Proteções e falha

- Limite global por instância do servidor: uma tentativa pública a cada 60 segundos, sem retries em erro. Caso várias abas façam GET, a amostra recente em cache é reaproveitada.
- Um cache tem no máximo 45 segundos de idade; após isso o endpoint retorna 503 e **não apresenta a amostra como atual**. O navegador marca qualquer amostra com mais de 30 segundos como `Amostra REST vencida` mesmo antes desse limite.
- Em HTTP 503, JSON inválido ou falha de fonte, o painel limpa a última leitura automática e mostra `Fonte REST indisponível`; nunca mantém cotação falha como se fosse nova.
- Um JSON manual importado pelo usuário recebe prioridade até reload, inclusive durante uma requisição automática pendente. Importação não persiste em localStorage.
- JSON da corretora é reduzido à allowlist de schema público D403, sem credenciais, identificadores privados nem metadados extras; preço nunca é convertido para float binário no validador JS.
- Não há conexões originadas pelo browser ao domínio Bybit; o servidor local não fica acessível fora do host sem canal privado autenticado e gate de acesso separado.
- J1 coleta 1h não é alterada. O JSON REST não substitui a auditoria SQLite, validação crypto-only, lista PIT dinâmica, cobertura de 50 e posições abertas ou piloto de WebSocket 24×7.

## Aceite e verificação

```sh
python -m unittest discover -s tests -p 'test_j5_local_readonly_server.py' -v
python -m unittest discover -s tests -p 'test_public_rest_price_pulse_d403.py' -v
python -m scripts.audit_j5_product_app_browser
```

Os testes usam exclusivamente fornecedores/fonte falsos, sem HTTP externo: verificam ausência de opt-in, impedimento de DNS rebinding, schema limitado, uma consulta por minuto, cache e 503 ao vencer, falha sem vazamento, proibição de métodos de escrita, página local com atualização, erro que apaga cotação e prioridade de importação manual.

**Estado desta implementação:** código preparado/validado em CI; **nenhuma inicialização foi realizada na VPS**. A comunicação HTTPS pública da VPS foi verificada em sessão anterior por consulta direta independente, mas não valida este endpoint ativo nem configura 24×7. O próximo ganho material permanece obter WebSocket público longitudinal de 50 + posições com métricas reais, sob gate de release operacional; ordens reais continuam proibidas.
