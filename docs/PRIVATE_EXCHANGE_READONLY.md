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
