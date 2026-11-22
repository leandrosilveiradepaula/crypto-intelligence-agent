# Crypto Intelligence Agent — regras para agentes

## Responsabilidades
O Product Owner decide o produto. ChatGPT coordena engenharia, backlog, GitHub, revisão, testes e continuidade. Codex é executor preferencial de implementações complexas. Factory passa a ter configuração de projeto versionada em `.factory/` (D473), com um Droid especializado em entregar o primeiro ciclo PAPER funcional. A presença de arquivos Factory **não** significa que a CLI esteja instalada/autenticada ou que uma missão foi executada; nenhuma cobrança adicional é autorizada.

## Autonomia por jornada — obrigatória
Uma jornada aprovada cobre todas as tarefas seguras e reversíveis de seu escopo.

**Proibido encerrar a sessão simplesmente porque uma microtarefa terminou.** Após cada ação concluída, identificar e executar a próxima tarefa elegível na mesma jornada. Não solicitar "prossiga", "continue" ou aprovações repetitivas. Fazer investigação, issues, branches, PRs, revisão, testes, correção de falhas, documentação e merges operacionais elegíveis sempre que as ferramentas permitirem.

Antes de encerrar, verificar e registrar: (a) existe outra tarefa segura e acessível? (b) houve bloqueio real, com causa e alternativa analisadas? (c) as tarefas independentes já foram executadas? (d) o estado no GitHub e a próxima ação estão registrados? Só encerrar por conclusão substancial da jornada, gate humano real, bloqueio inevitável ou limite efetivo da sessão/ferramenta. Relatar conclusão parcial com precisão, sem inventar trabalho futuro.

**Sem execução assíncrona fictícia:** após o fim da resposta não há continuidade automática sem executor/automação real.

## Gates humanos
Exigem autorização: mudança material de produto; gastos adicionais; ampliação sensível de acesso; exclusão/perda de dados; migrations e releases de produção sujeitos a gate; ativação de negociação real ou execução de ordens. Merges sem produção podem ser executados autonomamente depois de revisão, CI/aceite e head SHA exato verificados. Não habilitar auto-merge indiscriminado.

## Fonte de verdade e continuidade
GitHub, não o histórico do chat. Antes de alterar algo, consultar AGENTS.md, PRODUCT_SPEC.md, DECISIONS.md, OPERATIONAL_STATE.md, issues, PRs, HEAD e evidências reais. Alterar documentação junto com código. Cada falha relevante deve ganhar teste de regressão.

Quando o usuário solicitar "gere prompt para novo chat", gerar prompt operacional com: missão/repositório, regras e limites, decisões vigentes, jornada/tarefa, entregas comprovadas, issues/PRs/branches/SHAs, testes, bloqueios e próxima ação concreta autorizada. Novo chat deve verificar GitHub e retomar trabalho elegível sem pedir "prossiga".

## Requisitos invariantes
- Mercado inicial: futuros perpétuos. Universo dinâmico, referência inicial top 50 ativos por volume elegível.
- Alavancagem global inicial 50x, configurável apenas para novas posições; registrar alavancagem de abertura em cada posição.
- Margem por posição configurável. US$ 1–5 são exemplos. Sem quantidade fixa ou meta de posições.
- Entradas quantitativas: regimes, BTC, tendências, rompimentos, compressão, correções, força relativa, volume, liquidez, volatilidade e derivativos.
- Saídas fragmentadas sobre posição inicial ou saldo restante, trailing e parcela residual para tendências longas.
- Posições com margem, exposição, correlação, funding, custos, liquidação e PnL. Backtest intrabar com taxas, slippage, funding, liquidação, walk-forward e fora da amostra.
- ML somente quando melhorar resultados validados; LLM/LangGraph opcionais para contexto, jamais decisor primário.
- UI PT-BR simples, responsiva e mobile-first. **Alvo: entradas e saídas automáticas**, incluindo stops, parciais, trailing e runner, após validação. Desenvolvimento offline/paper por padrão; **ordens reais desativadas até autorização explícita e gates de produção**.
- 50x é parâmetro de pesquisa, não garantia de segurança. Medir retorno líquido ajustado ao risco de carteira, não percentuais isolados sobre margem.

## Restrições de custo e segurança
Custo adicional autorizado R$ 0,00. Usar ferramentas livres, APIs gratuitas, VPS já existente. Créditos Codex da conta permitidos sem compra ou consumo adicional cobrado. Repositório PÚBLICO por decisão do Product Owner: jamais versionar chaves, tokens, credenciais, identificadores privados da infraestrutura ou dados pessoais.

## Engenharia e validação
Cada work unit para Codex deve incluir objetivo, contexto, escopo e exclusões, critérios de aceite, testes e evidências. Preferir issues duráveis e PRs revisáveis; não pedir implementação do projeto inteiro num prompt. Evitar duplicações, hardcodes de parâmetros configuráveis, regressões e alteração fora de escopo. Validar contratos e cálculos financeiros. CI verde não demonstra rentabilidade nem prontidão completa. Registrar decisões no docs/DECISIONS.md e estado em docs/OPERATIONAL_STATE.md.


## Decisões vigentes D77/D383 — automação e venue Bybit

**D383 (16/11/2026): Bybit V5 linear de futuros perpétuos cripto USDT é a venue operacional escolhida pelo Product Owner.** Usar as APIs Bybit REST para snapshots/história, ordens e proteções (autenticadas somente após gate); WebSocket público para feed 24×7 e privado para estado de ordens/fills/posições. Não reabrir escolha entre Binance/Bybit nem desenvolver executor paralelo por conveniência. Velas horárias J1 não são feed contínuo de posições; manter J1 funcionando enquanto validar componente novo. Ler `docs/BYBIT_V5_ARCHITECTURE_D383.md` antes de implementar integração de mercado ou ordens. **PAPER default, zero ordens reais sem gate autorizado e sem inserir chaves no repositório.**

## Decisão vigente D77 — automação de trading como objetivo
A correção explícita do Product Owner em 26/10/2026 substitui a diretriz antiga de operação manual como estado FINAL. Construir motor quantitativo + `OrderExecutionEngine` com simulação, controle de risco, reconciliação, idempotência, stops, saídas parciais, trailing, runner e kill-switch. A seleção final entre Binance USD-M e Bybit V5 linear está pendente. **Não enviar ordens reais nem configurar credenciais/deploy sem gate humano próprio.** Modos distintos `offline_paper` (default), `testnet` (opt-in autorizado), `live` (travado até aceite). Exigências e critérios em `docs/AUTOMATED_EXECUTION_SPEC.md`. Trechos históricos de J4 ou WU47 sobre operação MANUAL descrevem somente o escopo anterior e não anulam D77.

**Regra anti-regressão D382 (16/11/2026):** nunca apresentar alertas e confirmação manual como destino do produto; D77 já determina entradas e saídas totalmente automáticas. A coleta pública N50 de candles fechados em 1h é insumo de contexto/pesquisa, NÃO o único relógio para operar: sinais e supervisão de posições, stops e parciais devem funcionar intrahora em arquitetura orientada a eventos e com feeds/ordens reconciliados, sob rigoroso gate de risco. Durante desenvolvimento, automatizar decisões e gestão em PAPER sem exigir cliques por trade; testnet e live exigem autorização de ativação distinta. Antes de explicar o funcionamento, verificar esta regra, D77 e `docs/AUTOMATED_EXECUTION_SPEC.md`.
