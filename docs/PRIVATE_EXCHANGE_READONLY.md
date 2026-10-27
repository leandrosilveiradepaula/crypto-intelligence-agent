# AUTH1 — Diagnóstico privado de API somente leitura

A autorização do Product Owner em 26/10/2026 cobre **somente conexão read-only** das contas existentes na Binance e Bybit, utilizando a VPS já existente e sem gasto adicional. **Não** autoriza operações reais, configuração de permissões ampliadas, criação de API keys por terceiros, deploy de trading, testnet/live, saques ou migrações de produção.

## Estado de implementação

`scripts/probe_private_exchange_readonly.py` é um verificador **opt-in** com **um GET assinado por execução**:
- Binance USD-M: `GET https://fapi.binance.com/fapi/v1/positionSide/dual`. O retorno comprova somente autenticação e acesso a esse endpoint, **não** prova que a chave seja estritamente read-only.
- Bybit V5: `GET https://api.bybit.com/v5/user/query-api`. Só confirma sucesso se o retorno incluir `readOnly` igual ao inteiro 1; outras permissões da conta não são exploradas.

Sem flags, o programa **não acessa rede nem lê segredos**. Nenhuma requisição de ordens, carteira, saldo, posições, endpoint mutável ou dados de mercado. Não há host/URL customizável, retry, redirect, proxy, cookies ou exportação de payload. A saída JSON contém exclusivamente venue, categoria sanitizada e sinalizadores negativos de trading/ordens/dados públicos. HTTPS, janela temporal UTC 5s e timeout 8s. HTTP451/403 interrompe sem tentativa por outra região/rota.

## Operação privada (somente após gate de segurança)

A pessoa administradora do ambiente deve:
1. Confirmar a VPS existente, acesso, região e conformidade com termos de ambas as corretoras. A integração DigitalOcean consultada neste chat retornou **zero droplets visíveis**, logo instalação/probe real **não foram realizados**.
2. Criar chaves **específicas de leitura**, sem habilitar ordens, transferências ou saques; limitar IP se a exchange permitir e usar armazenamento de segredos local (nunca no GitHub público, logs, comando CLI, prints ou chat).
3. Em uma sessão privada na VPS, disponibilizar somente ao processo executor as variáveis `BINANCE_READONLY_API_KEY`, `BINANCE_READONLY_API_SECRET`, ou `BYBIT_READONLY_API_KEY`, `BYBIT_READONLY_API_SECRET`. Não salvar em repositório nem em shell history. Variáveis de ambiente continuam potencialmente observáveis a outros processos privilegiados; preferir um gerenciador de segredos local de escopo mínimo.
4. Primeiramente executar `python -m scripts.probe_private_exchange_readonly --venue binance` ou `--venue bybit`, comprovando `offline_network_disabled`. Para permitir uma consulta, acrescentar **ambas** `--allow-private-read --confirm-read-only-key` somente depois de verificar a configuração da chave na UI da exchange. Isso representa consentimento de execução local, **não gate de trading real**.
5. Examinar a categoria de status no terminal privado. Binance `authenticated_permissions_not_attested` não atesta ausência de permissões de trading; Bybit `authenticated_read_only_key_confirmed` atesta só o campo retornado nessa consulta. Falha ou região restrita não admite proxy/VPN/host alternativo.
6. Não publicar dados de conta, chaves, UID, IP, conteúdo de respostas ou arquivo `.env` em issues, PRs, ChatGPT ou logs do Actions. Enviar para revisão apenas status sanitizado sem identificadores.

**Nenhuma conexão privada foi feita neste desenvolvimento.** A validação CI usa transportes falsos e não possui chaves. Isso não resolve dados de mercado J1 #2 nem homologa execução automática J4/J6. A próxima etapa exige acesso efetivo, seguro e verificado à VPS do titular; manter `orders_sent=false`, `trading_enabled=false`.


## Ambiente confirmado: VPS Hostinger (26/10/2026 UTC)

**Confirmação do Product Owner:** a VPS existente é hospedada na **Hostinger**, não na DigitalOcean. O resultado anterior de zero droplets na integração DigitalOcean não constitui evidência de inexistência de VPS.

A Hostinger documenta acesso pelo **hPanel → VPS → Gerenciar → Web Console** (em interfaces anteriores, “Terminal do navegador”), sem serviço adicional: https://www.hostinger.com/support/how-to-use-the-web-console-in-hostinger/ . O console usa a sessão autenticada do titular; não há, nesta conversa, sessão de controle remoto, SSH ou credenciais dessa VPS. A integração pesquisada no ChatGPT é “Hostinger Mail” e **não** controla VPS: não instalar esse plugin por engano.

### Roteiro mínimo e controlado

1. **Conexão à VPS:** usar somente sessão autenticada do titular no hPanel da Hostinger, ou acesso SSH já existente, sem compartilhar IP, senha, API key, token SSH ou captura com credenciais no chat/GitHub. Uma sessão Hostinger aberta no navegador do usuário não equivale automaticamente a acesso de execução do agente nesta conversa.
2. **Levantamento local não destrutivo:** confirmar SO/Python/repositório, usuário da aplicação, relógio UTC, conexão permitida à internet e estratégia de gerenciamento de segredos do ambiente **sem alterar** firewall, serviços, Docker, aplicações, backups, chaves ou configurações de produção. Preferir conta de aplicação sem privilégios administrativos. Não executar código do repositório automaticamente no `root`.
3. **Entregar código aprovado:** somente após CI/revisão, sincronizar o SHA específico de `main` em um diretório privado de trabalho não produtivo. Primeiro executar os testes unitários e o diagnóstico **sem flags** para verificar `offline_network_disabled`, sem acesso a contas.
4. **Credenciais de leitura:** se o usuário já tiver chaves com permissão de trading, **não reutilizá-las** nesse probe. Criar/usar credenciais distintas estritamente read-only e sem saques, sob controle do titular e sujeitas a controles regionais das corretoras. Os segredos devem entrar no processo a partir de armazenamento privado da VPS; nunca pela conversa, repositório ou logs. Não usar shell history para comandos com segredos.
5. **Uma consulta deliberada por corretora:** na VPS privada, com relógio e direitos de acesso corretos, usar `python -m scripts.probe_private_exchange_readonly --venue bybit --allow-private-read --confirm-read-only-key` ou `--venue binance` após revisar chaves/termos. Não há tentativa automática, repetição ou fallback de host. O processo retorna somente o código sanitizado.
6. **Critério de resultado:** Bybit só apresenta `authenticated_read_only_key_confirmed` com `readOnly=1` inteiro. Binance pode apresentar `authenticated_permissions_not_attested`: prova autenticação do endpoint, **não** prova que a chave não possui direitos de trading. Sem confirmação independente na UI e escopo mínimo, não considerar o acesso apto a qualquer ampliação.
7. **Acesso negado:** HTTP403/451, restrições regionais, rate limit, falta de chave ou erro de relógio são bloqueios a registrar; não tentar proxy, VPN, mudança de DNS ou domínio de fallback. Falhas exigem revisão local, não mais endpoints.
8. **Saída e estado:** registrar em documento de evidências apenas `venue`, classe sanitizada, SHA validado, UTC e flags negativas. Não versionar API key, UID, IP, saldos, corpo bruto, ID de VPS, logs de terminal ou outros detalhes privados.

O consentimento concedido é **read-only nas duas contas**, não aprovação de software para dar ordens, nem teste com capital real, nem autorização de gastos ou mudanças administrativas da VPS. **Nenhuma instalação ou prova de acesso real à Hostinger ocorreu até este checkpoint.**

**Dependência operacional:** esta conversa dispõe de GitHub e de acesso de leitura a abas conectadas, mas não de ferramenta para controlar o Web Console da Hostinger. Para executar sem que o usuário transcreva comandos, abrir uma jornada em **ChatGPT Work**, com a sessão Hostinger devidamente autenticada e as permissões adequadas; o operador deve preservar a confidencialidade dos segredos e solicitar confirmação apenas nos gates sensíveis. Não afirmar que a Work já executou algo.


### Checkpoint AUTH1 offline validado na Hostinger — 26/10/2026 UTC

O Product Owner instalou a revisão `3dd2980eb8d1ddb93c8d8928a3336f8aac53c00b` do repositório na pasta isolada sob `cia-probe`. A execução sem flags retornou exatamente `offline_network_disabled` para **Binance e Bybit**, com `orders_sent=false` e `trading_enabled=false`. Evidência fornecida pelo titular; a equipe não controlou a sessão SSH nem viu credenciais. Isso demonstra somente o caminho offline instalado, **não acesso autenticado**, volume, licenças ou homologação J1/J6.

### AUTH1/TYY1 — captura efêmera e privada por terminal

O entrypoint `python3 -m scripts.run_private_exchange_readonly_tty` acrescenta entrada oculta `getpass` de **uma chave HMAC dedicada estritamente read-only e seu secret**, com ambas as flags explícitas `--allow-private-read --confirm-read-only-key`. O programa exige terminal interativo, falha se o terminal não permitir ocultar a digitação, rejeita parâmetros CLI desconhecidos sem reproduzir seu valor e entrega o par diretamente ao `diagnose` através de dicionário **somente em memória** (não por argv, variável de ambiente global, `.env`, shell history ou disco). A memória do processo não é eliminada criptograficamente; como em qualquer execução local, root/depuradores ainda podem acessá-la. Não usar terminal com gravação de sessão, `set -x`, streaming, clipboard compartilhado ou extensões que capturem entrada.

A chave da **Bybit** deve ser de HMAC gerada pelo sistema, marcada na interface como **Read Only** e sem permissão de saque/transferência/ordem. A API oficial `GET /v5/user/query-api` atesta `readOnly=1` (https://bybit-exchange.github.io/docs/v5/user/apikey-info). A chave da **Binance USD-M** deve ter `Enable Reading` e **nenhuma** permissão de trading/futures trading, transferência ou saque habilitada; a consulta autenticada `GET /fapi/v1/positionSide/dual` não informa esse escopo. Ver configuração efetiva na interface da conta antes de executar (https://www.binance.com/en/support/faq/detail/360002502072). Não reutilizar credenciais com permissão de trading nem insistir após HTTP 403/451. Chaves RSA/Ed25519 NÃO são suportadas por este diagnóstico HMAC; não converter manualmente.

Após CI e merge de revisão verificada, atualizar o checkout isolado sob o dono `cia-probe` usando `git fetch --no-tags origin main` e `git checkout --detach <SHA-aceito>`, sem mudanças de serviços. Iniciar uma consulta por vez, em SSH privado, sem mostrar qualquer credencial:

```bash
runuser -u cia-probe -- sh -c 'cd /home/cia-probe/agent/repo && python3 -m scripts.run_private_exchange_readonly_tty --venue bybit --allow-private-read --confirm-read-only-key'
runuser -u cia-probe -- sh -c 'cd /home/cia-probe/agent/repo && python3 -m scripts.run_private_exchange_readonly_tty --venue binance --allow-private-read --confirm-read-only-key'
```

As duas entradas são solicitadas invisivelmente em cada execução. Somente o JSON com status sanitizado pode ser comunicado. **Jamais** copiar key, secret, UID, cabeçalhos, respostas brutas, IP/hostname ou captura do terminal. Autenticar não valida dados de mercado nem habilita ordens ou deploy de trading.

### AUTH1 — resultados owner-run na Hostinger (27/10/2026 UTC)

O titular realizou a primeira autenticação real **somente leitura** com o launcher TTY revisado: Bybit V5 `authenticated_read_only_key_confirmed`, com todos os indicadores de ordem, saldo e trading negativos. Esse status resulta da verificação do campo inteiro `readOnly=1` pelo diagnóstico em uma única GET assinada. A evidência foi apresentada como JSON sanitizado pelo titular, **sem controle SSH direto por esta conversa**. Uma chave Bybit que apareceu em captura de tela foi reportada como excluída; o diagnóstico bem-sucedido utilizou credenciais posteriores, nunca incluídas no repositório.

Na Binance USD-M, o titular reportou configuração HMAC de **leitura apenas**, permissões de trading/saque desativadas e IP da VPS autorizado; a tentativa real retornou **`access_or_region_restricted`**. O programa unifica erros HTTP 401, 403, 418 e 451 nessa classe, portanto **não é possível determinar a causa nem alegar autenticação válida**. Não repetir ou contornar o bloqueio; a autorização de conexão permanece limitada a leitura privada. A issue #205 documenta as duas evidências e continua aberta.

O êxito da autenticação privada **não** constitui prova de acesso ao endpoint público de mercado, de licença de dados, qualidade/histórico do feed, execução automática ou segurança para negociar. `scripts/j1_readiness_report.py` discrimina os resultados datados, sem revalidar chaves nem habilitar gates financeiros.
