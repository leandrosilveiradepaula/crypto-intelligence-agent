# J1/D275 — Fila única de diligência dos 50 candidatos da D264

**Objetivo:** trabalhar os 50 símbolos existentes da fronteira D264 como **um lote completo**, em vez de criar uma PR de pesquisa para cada símbolo. Sem refetch de 819 séries.

## Reuso causal e privacidade

`scripts.j1_d264_private_metadata_snapshot.replay_private_snapshot` já abre o banco D256 em leitura, valida replay dos 24 candles fechados, confere digests, valida o snapshot contemporâneo de vetos D264 e calcula uma fronteira de 50 **candidatos de pesquisa**. Agora o replay também usa `j1_top50_frontier_worklist.frontier_review_worklist` para anexar `frontier_identity_review_worklist` a essa mesma evidência.

Para **cada um dos 50**, preservando sua posição na fronteira, a função associa a categoria de pesquisa, o próximo trabalho de identidade, hipóteses históricas D261/D265, e eventual evidência primária posterior D273/D274. Ela exige 50 símbolos únicos, calendário válido, bases históricas normalizadas e rejeita qualquer negativo documentado que tenha escapado à filtragem.

A resposta padrão contém **somente contagens agregadas, digest da fila e zero símbolos**. A opção existente `--include-private-symbols`, apenas em execução como proprietário, exibe os nomes e links públicos de pesquisa; **não há volume financeiro, endereço privado ou credencial** na saída. Os dados continuam armazenados na VPS; não copiar lista completa ou dados financeiros ao GitHub público.

## Diferenças que não podem ser apagadas

- **Arquivo de referência**: registro BTC/ativo antigo é evidência arquivada, não revisão atual e não identidade PIT autenticada.
- **Hipótese de token**: ticker com link CoinGecko não vincula automaticamente o contrato Bybit ao token.
- **Colisão**: CLANKER/LIT/ARIA/BIRB exigem conferência explícita do instrumento e endereço, mesmo com publicações primárias existentes.
- **Tokenização/ouro**: XAUT requer decisão de escopo, não é elegível por omissão.
- **Desconhecido**: exige Bybit primário, vínculo canônico e segunda origem independente.
- **Fonte primária D273/D274**: datas de publicação anteriores não equivalem à revisão/autenticação no snapshot 06/11/2026.

**O lote não promove ninguém a crypto aprovado.** `identity_approved_count=0`, `identity_review_pending_count=50`, `marketwide_top50_verified=false` e `trading_enabled=false` são invariantes. A fronteira com vetos D264 é retrospectiva e **não** é Top50 global crypto-only. Os 3 contratos com 24h incompletas continuam concorrentes potenciais em gate posterior.

## Gate de integração

CI Linux/docs e Windows/offline, Chrome/PAPER, revisão e SHA exato. Sem mudança de banco, timer, VPS, backend de execução, chamadas Bybit ou ordem.

Acesso direto ao censo: o MCP VPS responde, porém o executor restrito não consegue mudar para `cia-probe` (`runuser: cannot set groups: Operation not permitted`) nem ler seu diretório 0700 (`Permission denied`). Esses retornos são **limite de acesso**, não justificativa para alterar permissões. A fila real deve ser obtida por um executor owner já autorizado e auditável; não elevar privilégios no MCP financeiro nem publicizar os 50 símbolos por suposição.

### Próximo resultado concreto

Executar `python -m scripts.j1_d264_private_metadata_snapshot --directory <private-dir> --include-private-symbols` **no contexto owner já habilitado** e revisar o lote de 50, usando a fila agregada para distribuir pesquisas independentes de identidade e fechar o Top50 apenas após a autenticação de ao menos 50 elegíveis mais todos os rivais que poderiam ultrapassar o corte. Nenhuma re-coleta é necessária.
