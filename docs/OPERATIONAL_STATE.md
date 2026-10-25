# Estado operacional — checkpoint pós-WU2, 2026-10-25 UTC

- Missão: inteligência quantitativa para futuros perpétuos, oportunidades, backtesting realista e gerenciamento de realizações parciais. Ver PRODUCT_SPEC.md/DECISIONS.md.
- Repositório: leandrosilveiradepaula/crypto-intelligence-agent, PÚBLICO por decisão do Product Owner.
- Autonomia: ler AGENTS.md. Não pedir "prossiga", não interromper após microtarefas. Merges seguros sem produção com checks/revisão/SHA verificados.
- Custos: R$0 adicional; sem APIs pagas, ordens reais ou releases de produção.
- J0: fundação concluída, issue #1 fechada e PRs #10/#11 integradas.
- Jornada atual: J1 Dados, épica #2 aberta.
- WU1: issue #9 fechada, PR #12 merged, SHA c9bf70c3f8429b1474a9b68cc1aeb0a3cd209193.
- WU2: issue #13 fechada, PR #14 merged, HEAD revisado 9ac750ff3f92d56189ce55a670391292d3716ec2, SHA de merge f3567eb063f0b7cfeffe40169ba0b8e9fce1da96.
- Validação WU2: CI na PR run 40168249829 SUCCESS no HEAD exato, 42 testes offline, compileall e 10 docs; CI pós-merge run 40168285079 SUCCESS no SHA de integração.
- Correções revisadas WU2: checkpoints não pulam lacunas, linhagem de fonte/versão, transações atômicas, contrato histórico imutável, alinhamento semanal UTC e contagem de conflitos não medida sem falsos zeros.
- J1/WU3: issue #15 aberta, sendo implementada diretamente pelo ChatGPT na branch `feat/j1-wu3-readonly-pipeline`, sem disparo Codex. CLI offline por padrão, transporte de fixture, proveniência e auditoria local SQLite; não declarar PR/CI/merge concluídos sem verificação.
- J2–J7: issues #3–#8, dependências ainda não satisfeitas. Não declarar J1 ou produto prontos.
- Entregas NÃO comprovadas: feed live homologado, histórico ponto-no-tempo amplo, implantação VPS, serviço contínuo, estratégias lucrativas e ordens reais.
- Sem disparador direto Codex nesta sessão. Isto NÃO impede execução direta de tarefas permitidas com Github + CI. Nenhum gasto adicional, deploy, ordem real ou validação live.

## Próxima ação concreta
1. Confirmar main, a issue #15, docs e PRs em GitHub; não duplicar trabalho.
2. Concluir código/testes/documentação da WU3 nesta branch, abrir PR vinculada à #15 e à #2, revisar e corrigir CI no SHA exato.
3. Executar merge seguro da PR WU3 somente quando checks e revisão estiverem verdes, sem publicação em produção.
4. Registrar evidências e preparar a próxima work unit da J1 sem pedir "prossiga".
5. Se o usuário disser "gere prompt para novo chat", produzir PROMPT DE CONTINUIDADE OPERACIONAL com missão, repo, regras, decisões, jornada, SHAs, issues/PRs, testes, bloqueios e próxima ação.
