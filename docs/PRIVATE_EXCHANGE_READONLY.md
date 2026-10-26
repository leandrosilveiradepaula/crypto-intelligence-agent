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
