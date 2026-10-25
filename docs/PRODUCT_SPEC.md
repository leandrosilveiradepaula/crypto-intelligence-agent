# Especificação do produto

## Objetivo
Plataforma de inteligência quantitativa que pesquisa entradas de alto potencial em futuros perpétuos e auxilia a captura progressiva de lucros em operações vencedoras. Nenhuma promessa de rentabilidade.

## Contratos principais
- Universo dinâmico de contratos elegíveis; usar volume comparável, filtros de liquidez e histórico de elegibilidade para evitar viés de sobrevivência.
- Alavancagem global padrão 50x; valor gravado ao abrir cada posição. Alterar a configuração só modifica novas posições.
- Margem por posição configurável; número de posições variável conforme oportunidades e capital, não uma meta de 20/50/100.
- Motor de sinais com múltiplas estratégias, regimes do BTC, força relativa, tendência, compressão, rompimento, correções, volume, volatilidade, liquidez e derivativos.
- Planejador de saídas parciais: porcentagens da posição inicial OU do saldo restante, definidas explicitamente; permitir runner residual.
- Acompanhar exposição, correlação, custos, funding, margem, liquidação, posição, operações manuais e resultados.
- Execução manual das entradas e saídas pelo usuário nesta fase; o agente emite alertas e planos, mas não envia ordens reais.
- Pesquisa reproduzível: candles fechados, trajetória intrabar, taxas, slippage, funding, manutenção e liquidação, walk-forward, benchmark e fora da amostra.
- ML somente se melhorar desempenho validado. LLM e LangGraph opcionais para contexto e explicação, nunca fonte primária de compra.
- Interface em PT-BR, simples no celular: oportunidades, posições/saídas, resultados e alertas.

## Não objetivos iniciais
Sem execução automática de ordens reais, sem dependência de serviços pagos ou credenciais de negociação. Retorno líquido ajustado ao risco da carteira é mais importante que taxa de acerto ou percentual isolado sobre a margem. 50x é parâmetro de pesquisa, não garantia de segurança.


## Direitos de dados de mercado antes de lançar ou distribuir
A interface inicialmente serve pesquisa/alertas/execução manual; o modo final de disponibilização (uso pessoal interno, painel privado para titular, acesso de terceiros ou serviço comercial) exige decisão do Product Owner quando for relevante para publicação. Acesso GET público/HTTP200 **não significa** autorização para redistribuir ou monetizar market data. O guia oficial Kraken informa que usos comerciais não pessoais de endpoints públicos requerem permissão prévia: https://docs-legacy.kraken.com/api/docs/guides/global-intro/#notices . Por padrão, **não lançar** produto público/comercial com dados Kraken nem exportar feeds/fixtures reais sem evidência de direitos aplicáveis e gate de release. Continuar desenvolvimento offline, com dados sintéticos, custo extra R$0 e sem ordens reais. Critérios: `docs/PROVIDER_RIGHTS.md`.


## Fronteira do protótipo matemático de saídas (J4/PRE1)
Existe um cálculo determinístico e sintético de fatias sobre quantidade inicial/saldo remanescente e piso residual. Isso não constitui conta, posição financeira, capacidade de ordem, trailing, execução nem corretagem homologada: as quantidades são abstratas e podem ser menores que o mínimo da exchange real. A regra geral de margem, alavancagem gravada na abertura e saídas **manuais** não foi alterada, nem o objetivo de capturar tendências. Nenhuma promessa de resultado ou J4 operacional aceita por essa entrega.


## Eventos manuais de saída: limite do protótipo de replay J4/PRE2
O replay de eventos atualmente é **apenas sintético e em memória**: contabiliza parcial de tranche somente quando há evento explícito, deduplica event_id idêntico em uma única execução e não simula preço de execução. Não identifica eventos duplicados com IDs diferentes ou falhas entre sessões; logo **não** constitui histórico auditável de posições reais, PnL, acompanhamento do usuário nem ordem manual enviada. Tais funções exigem transações, IDs confiáveis, preço, taxa, lotes, funding e risco aprovados. O produto continua com operações reais manuais e sem automação.


## Pré-condição de registro de posição (J4/PRE3 — não operacional)
A opção de alavancagem global 50x e margens configuráveis agora possui um **contrato sintético imutável**: cada abertura fictícia copia o valor de alavancagem da configuração daquele instante, preservando o passado. Os valores de margem são abstratos e não implicam qualquer moeda, exposição, liquidação ou corretora real. Eventos fictícios de saída são vinculados à posição de pesquisa pelo ID, mas a deduplicação ainda funciona somente dentro do mesmo replay; não existem usuários, conta, ordens, ledger financeiro nem posição manual homologada. A UI/execução reais seguem fora do escopo até os gates J1/J3/J4.
