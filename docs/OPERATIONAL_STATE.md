# Estado operacional — checkpoint 2026-10-25 UTC

- **Missão:** inteligência quantitativa para futuros perpétuos, entradas e gerenciamento de realizações parciais; Product Owner decide produto, ChatGPT coordena execução técnica e Codex é preferencial se disponível.
- **Repositório:** `leandrosilveiradepaula/crypto-intelligence-agent`, PÚBLICO por decisão do usuário.
- **Autonomia:** ler AGENTS.md; não pedir "prossiga" para tarefas seguras dentro da jornada, não encerrar por microtarefas, merges não produtivos apenas com SHA/CI/revisão conferidos.
- **Gates:** gasto adicional R$0, sem ordens reais, release/migration de produção ou ampliação sensível de acesso.
- **J0:** concluída documentalmente, issue #1 encerrada, PRs #10 e #11 integradas.
- **Jornada atual:** J1 Dados, épica #2 ABERTA. Não declarar pronto só por CI verde.
- **WU1:** issue #9 fechada, PR #12 merged `c9bf70c3f8429b1474a9b68cc1aeb0a3cd209193`.
- **WU2:** issue #13 fechada, PR #14 merged `f3567eb063f0b7cfeffe40169ba0b8e9fce1da96`, CI 42 offline.
- **WU3:** issue #15 fechada, PR #16 merged `9631e4445678bc4c7067964b537da924b5b89a0b`, CI pós-merge run 40188838338 SUCCESS com 58 testes Python offline, compileall e 10 docs.
- **WU4:** issue #17 fechada, PR #18 merged `8fc2f75460e93ef898ae14e3c48ef0348692c857`, CI pós-merge run 40189235249 SUCCESS com 65 testes Python offline, compileall e 10 docs.
- **WU5:** issue #19 ABERTA, nenhuma PR de implementação ou sessão Codex comprovada. Objetivo: conformidade pública USD-M, diagnóstico de payload/relógio/limites/qualidade e smoke live estritamente opt-in, sem CI online.
- **J2–J7:** issues #3–#8 aguardando dependências. Fonte de verdade: GitHub ao vivo e decisões versionadas.

## Evidências e limitações
- WU3 e WU4 foram implementadas diretamente via GitHub + CI nesta sessão, sem Codex, gastos, deploy ou operações financeiras.
- Offline usa fixtures sintéticas e não comprova dados de mercado atuais.
- Tooling local nesta sessão não alcança github.com por DNS; este fato não prova indisponibilidade da API da exchange. Existe documentação pública do endpoint, mas não houve smoke GET live.
- Persistência SQLite é referência local; backup, desempenho em VPS, cobertura histórica, universo ponto-no-tempo amplo e valoração financeira ainda não homologados.

## Próxima ação concreta autorizada
1. Conferir HEAD, issues, PRs e CI no GitHub antes de agir; não duplicar #19.
2. Desenvolver as partes offline e revisáveis da WU5 com fixtures de conformidade, documentação e testes; obter prova de smoke live somente em executor com acesso público explícito e dentro dos limites gratuitos. Se rede bloqueada, registrar e prosseguir nas tarefas independentes.
3. Revisar a PR, corrigir regressões, integrar sem produção somente com CI/gates verdes e SHA exato; manter J1 aberta até cobertura/qualidade verificadas.
4. Ao pedir "gere prompt para novo chat", entregar prontamente missão, regras, decisões, jornada, entregas, issues/PRs/SHAs, testes, bloqueios e ação seguinte para retomada autônoma.
