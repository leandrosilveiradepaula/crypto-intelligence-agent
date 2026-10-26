# Plano de execução verificável — Crypto Intelligence Agent

**Atualização inicial:** 2026-10-26 UTC. **Fonte de verdade:** este repositório, suas issues/PRs e CI.
**Objetivo final vigente (D77):** robô que identifica oportunidades e realiza ENTRADAS E SAÍDAS AUTOMÁTICAS de futuros perpétuos, com limites de risco, ordens e proteção reconciliadas, parciais, trailing, runner e interface PT-BR mobile. Binance USD-M e Bybit V5 linear são **candidatas**, não venues homologadas nem selecionadas. Orçamento extra autorizado **R$ 0,00**.

> **Importante:** código, CI verde e fixtures PAPER não comprovam lucros, segurança de 50x, acesso às corretoras ou autorização de ordens. Não estabelecer percentuais artificiais de conclusão ou datas fictícias. **Nenhuma negociação real/testnet, credencial, migração de produção ou deploy** decorre deste plano.

## Prioridade operacional e sequência

### 1. Finalizar a J6/PRE2-B — issue #200 / PR #202

**Objetivo:** persistir progresso do replay sintético de modo que OPEN PENDING e cursor do histórico sejam gravados na mesma transação do SQLite PAPER AUTO2, nunca em arquivo independente. A base AUTO4 continua distinta, sem atomicidade cross-file.

**Ações autorizadas:** revisar código e logs no SHA exato, executar e corrigir testes Linux/Windows/QA Chrome, documentar decisões, e integrar por squash **somente sem produção** após CI e revisão verdes. Validar bootstrap, no-signal, LONG/SHORT, risk denial, concorrência de instâncias, reinício, reescrita Decimal, mudanças de venue/quantidade/parâmetros, histórico deslocado, `UNKNOWN`, saúde AUTO8/AUTO9, SQLite ocupado/corrompido, rollback e interrupção de processo antes/depois do commit. Verificar que o leitor RO mantém o contrato rígido do AUTO2. Se alguma lacuna de atomicidade não for eliminável neste escopo, permanecer *fail-closed* e registrar bloqueio técnico em vez de declarar recuperabilidade.

**Aceite:** commit exato, teste de rollback comprovado, validação offline nos três jobs aplicáveis, sem envio de ordens e sem migração de produção; documentação e estado operacional registrados; eventual merge verificado em `main`. **A issue #200 só pode ser fechada se seus critérios estiverem cumpridos.** A épica J6 #7 continua aberta.

### 2. Desbloquear o caminho de dados reais — J1 #2

Esta é a **principal dependência externa e técnica da estratégia real**, não algo que possa ser substituído por mais sinais sintéticos. Reutilizar evidências das issues existentes, sem reabrir sondagens bloqueadas, contornar georrestrições ou atribuir unidades por analogia.

| Gate obrigatório | Questões / histórico | Evidência mínima para avançar |
| --- | --- | --- |
| Conectividade legal e acesso | #19; restrições observadas em Binance/Bybit | Captura mínima documentada por fonte legítima e ambiente permitido, sem proxy/VPN de evasão |
| Identidade e universo de contratos | #32, J1 #2 | Contratos realmente cripto, linear perpetual, status, filtros e universo Top50 ponto-no-tempo |
| Volume econômico e OHLCV | #36 (Kraken); #196 (Bybit) | Unidades BASE/QUOTE e origem de campos do endpoint exato, com timestamp e produto |
| Direitos, termos e utilização | #48 e docs/PROVIDER_RIGHTS.md | Permissão verificável para o cenário de uso do produto, distinguindo pesquisa privada de publicação |
| Qualidade histórica e persistência | J1 #2 e documentos de J1 | Candles fechados, UTC, gaps, backfill, unicidade, instrument mapping e histórico reproduzível |

**Ordem de trabalho:** (a) consolidar matriz das fontes que já foram verificadas, separando fatos, hipóteses e bloqueios; (b) identificar sem custo e com fontes primárias qual caminho de aquisição de candles/volume/contratos é realmente elegível; (c) escrever contrato e testes de qualidade do primeiro feed comprovado; (d) integrar coleta real somente depois dos gates e da autorização de acesso aplicáveis. **Se nenhuma fonte estiver comprovada, registrar bloqueio externo e avançar nos trabalhos independentes, sem declarar J1 concluída.** A exchange para negociação não precisa ser a mesma da fonte de pesquisa, mas exige mapeamento e risco específicos.

### 3. Validar entradas, backtest e risco — J2 #3 + J3 #4

A pesquisa sintética atual permite formular hipóteses, mas não escolher uma estratégia de lucro. Preservar isolamento temporal: regime BTC, tendências, rompimentos, compressão, correções, volume, liquidez, volatilidade e derivativos devem ser avaliados sem informação futura.

**Depois da aprovação de dados J1:** testar instrumentos/períodos elegíveis, composição histórica do universo e execução com taxa, slippage, spread, funding, marcação, liquidação e trajetória intrabar; walk-forward e fora da amostra; robustez por regime, drawdown, exposição agregada e retorno líquido ajustado ao risco. Alavancagem inicial configurável 50x **somente parâmetro de pesquisa**; limites de venue e risco podem recusá-la. ML somente se melhorar resultados verificáveis. Rejeitar resultados insuficientes, em vez de promover hipóteses.

**Enquanto J1 estiver bloqueada:** continuar testes matemáticos e de causalidade **claramente rotulados como sintéticos**, sem inventar desempenho real ou vender acertos.

### 4. Integrar motor automático e produto — J4 #5 + J5 #6

Após gates de J1/J2/J3, consolidar o `OrderExecutionEngine` com idempotência, confirmação/reconciliação de fills, reduce-only, stops nativos verificados, saídas parciais, trailing, runner residual, funding/custos, kill-switch e risco por posição/carteira. Configuração de alavancagem só afeta novas posições; cada posição guarda o valor usado; margem por posição configurável; sem número fixo de operações.

Interface PT-BR mobile-first deve mostrar posições, ordens, níveis de proteção, resultados, alertas e pausa/emergência. O painel atual de fixtures é **somente demonstração**. Gate: invariantes de segurança testados, controles observáveis e fluxos de erro reconciliados; nenhuma UI habilita ordens sem autorização.

### 5. Homologar e obter autorização específica — J6 #7, depois J7 #8

Executar PAPER prospectivo com dados reais autorizados, observabilidade, replays de incidentes, reconciliação, restauração e documentação. Testnet requer opt-in e requisitos de acesso/credenciais; live requer gate **novo e explícito** do Product Owner para capital real, após evidências, segurança operacional, licenças, risco e rollback. Não ativar testnet/live por merge, CI, configuração padrão ou existência de conta Binance/Bybit. J7 (derivativos avançados/ML/contexto) fica condicionada a evidência incremental.

## Regras de execução e comunicação

- Executar trabalhos seguros/reversíveis autonomamente, inclusive revisar PRs, corrigir CI, registrar issues, documentar e integrar PR **não produtiva** quando gates, revisão e SHA estiverem verificados. Não pedir `prossiga` para operações rotineiras.
- Nunca alegar acesso ao Codex/Factory ou executor contínuo sem prova. Usar Codex quando disponível dentro do orçamento; caso contrário, fazer implementação segura com ferramentas acessíveis e registrar limites.
- Publicar em `docs/OPERATIONAL_STATE.md` e `docs/STATUS.md`: jornada, etapa, issues, PRs, SHA, testes, bloqueios e próxima ação comprovável. Manter DECISIONS/VALIDATION_PLAN/ARCHITECTURE junto de código.
- Gate humano: gasto, mudança material de produto, acesso sensível, migração ou release de produção, ordens testnet/live e destruição de dados. Não criar credenciais, contornar restrições de acesso ou alterar posições reais.
- Se uma dependência externa bloquear J1, **não inventar confirmação**; trabalhar em segurança, matemática, contratos e validação offline ainda elegíveis. O sucesso da engenharia não substitui eficácia financeira.

## Checkpoint de criação do plano (a confirmar após mudanças)

- Base `main`: `4011812f33fec643f7dbe402f03457c046aa07f1` (PR #201 integrada).
- PR #202 / issue #200: branch `work/issue-200-j6-durable-paper-cursor`; checkpoint de CI verde no SHA `db9bbad0ec3efa9d050f162a6934cd2af931a722` (**1.043 testes** Linux/Windows; Windows registra skips POSIX; QA mobile Chrome verde). **Ainda sem merge na criação deste plano**.
- Dependências J1 #2/#19/#32/#36/#48/#196 permanecem abertas, sem feed real homologado. Sem trades reais, receita comprovada ou deploy.
- **Próxima ação imediata:** revisar o contrato de recuperação da PR #202 contra todos os critérios de #200, corrigir/testar o SHA final, fazer squash merge seguro se elegível e verificar pós-merge. Depois priorizar matriz de fontes da J1, sem repetir GET/POST restritos.
