# Decisões do produto

Estas decisões foram confirmadas pelo Product Owner e não podem ser alteradas silenciosamente.

- D01: mercado inicial de futuros perpétuos de criptomoedas. Universo dinâmico, referência inicial nos 50 contratos elegíveis de maior volume.
- D02: alavancagem global inicial 50x, configurável. Mudanças afetam apenas novas posições; cada posição preserva a alavancagem de abertura.
- D03: margem configurável por posição; US$ 1 a US$ 5 são exemplos, não limites. Quantidade de posições é variável, sem meta fixa.
- D04: núcleo de decisões quantitativo/estatístico. Regimes, BTC, tendência, rompimentos, compressão, correções, força relativa, volume, liquidez, volatilidade e derivativos.
- D05: saídas fragmentadas configuráveis sobre posição inicial ou saldo remanescente; manter parcela residual para tendências longas.
- D06: entradas e saídas reais executadas manualmente na primeira versão; não implementar ordens automáticas.
- D07: custo adicional autorizado R$ 0. Sem serviços pagos ou APIs pagas. Créditos Codex existentes são permitidos nos limites da conta.
- D08: interface responsiva, simples, mobile-first e em português.
- D09: engenharia começa pelo Codex direto; ChatGPT coordena. Factory somente após comprovação de autonomia.
- D10: autonomia por jornada, sem pedidos repetidos de "prossiga"; merges de PRs sem produção podem ocorrer após gates verdes e SHA verificado.
- D11: GitHub é a fonte de verdade; contexto deve sobreviver a novos chats por documentos, issues, PRs e estado operacional.
- D12: validação rigorosa com trajetória intrabar, custos, funding, slippage, liquidação, walk-forward e teste fora da amostra.
- D13: repositório público, por decisão expressa do Product Owner em 25/10/2026. Jamais publicar credenciais ou informações privadas.

Hipóteses ainda não aprovadas: parâmetros dos sinais, seleção final de tecnologia, percentuais ótimos de realização, gatilhos de trailing e modelos de ML. Cada decisão nova deve receber justificativa e evidência.

## D14 — Adaptador público read-only e testes por fixture (J1/WU1)

O primeiro adaptador implementado atende apenas endpoints públicos de futuros USD-M e não possui qualquer capacidade de autenticação ou envio de ordens. O domínio conserva `Decimal` e UTC em milissegundos; o transporte HTTP é injetável para que CI e regressões usem fixtures offline. Throttling recebe no máximo duas novas tentativas, com backoff exponencial configurável, antes de falhar explicitamente. O provedor é uma implementação inicial substituível, não uma escolha definitiva de fonte histórica nem uma validação de disponibilidade/cobertura gratuita.

## D15 — Integridade temporal e validação Python na CI (J1/WU1)
Decisão técnica: rejeitar OHLC/volume inválidos, timestamps truncados, durações incoerentes, duplicatas de ticker divergentes e horários de observação impossíveis. Não permitir rotular dados atuais de metadados ou volume móvel de 24 horas como snapshots históricos. Testes Python offline passam a integrar o gate obrigatório da CI para PRs que modificarem código Python. Limitação: histórico genuíno ponto-no-tempo ainda depende de persistência futura.
