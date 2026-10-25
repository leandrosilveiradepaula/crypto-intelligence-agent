# Estado operacional — checkpoint pós-WU5 offline (2026-10-25 UTC)

Projeto: Crypto Intelligence Agent
Repo: `leandrosilveiradepaula/crypto-intelligence-agent` (público, decisão do PO).
Missão: motor quantitativo de oportunidades e gerenciamento de realizações parciais em futuros perpétuos; sem negociação automática real.
Gates: custo adicional R$0; sem trade/ordens reais, upgrades pagos, destruição, migrations ou releases de produção sujeitos a autorização.
Autonomia: AGENTS.md; não pedir "prossiga" por microtarefas, manter GitHub como fonte da verdade e registrar evidências/SHAs verdadeiros.

### Jornada e entregas
- J0 concluída: issue #1 fechada, PRs #10/#11 integradas.
- **J1 em andamento, épica #2 aberta**.
- WU1 #9, PR #12 merged no SHA `c9bf70c3f8429b1474a9b68cc1aeb0a3cd209193`.
- WU2 #13, PR #14 merged no SHA `f3567eb063f0b7cfeffe40169ba0b8e9fce1da96`.
- WU3 #15, PR #16 merged no SHA `9631e4445678bc4c7067964b537da924b5b89a0b`; CI pós-merge run 40188838338 SUCCESS (58 testes offline).
- WU4 #17, PR #18 merged no SHA `8fc2f75460e93ef898ae14e3c48ef0348692c857`; CI pós-merge run 40189235249 SUCCESS (65 testes offline).
- WU5 #19 permanece **ABERTA**; PRs #20/#21/#22 integradas. #20: `cddfc2535aac7c3b7ae9bc04fea160419344ee7f` (78 testes offline). #21: `09617e0197c250e3b13c7486a60067791ed41a52` (81 testes offline, workflow owner-only). #22: `32c63d0beccdf4734cf06d0f37d04f9ae833fc1f` (CI pós-merge verde com 81 testes), erro 451 classificado fail-closed e evidência real versionada.
- WU6 #23: pesquisa de fonte independente Kraken Futures, branch `research/j1-kraken-public-feasibility`; probe de 1 GET de instrumentos, sem autenticação, testes offline, disparo por comentário owner-only. Ainda não executar nem afirmar resultado antes de PR/checks/merge.
- J2–J7: issues #3–#8 ainda dependem de J1, sem código de estratégia em produção.

### Limites e bloqueio verdadeiro
- Smoke GET live via GitHub Actions **tentado e bloqueado**: issue #19, comando exato `/run-readonly-smoke-v1` pelo proprietário, workflow run `40197499250` no commit `09617e0197c250e3b13c7486a60067791ed41a52`, 2026-10-25T13:24:57Z, HTTP **451** na primeira consulta pública. Sem candles, sem validação de preço/volume. Fluxo usual de testes GitHub Actions continua offline.
- A máquina local desta conversa não consegue resolver github.com por DNS; isso não é evidência sobre disponibilidade da API da Binance. Sem Codex diretamente acionável via ferramenta.
- Não declarar feed real, cobertura histórica extensa, snapshots ponto-no-tempo retrospectivos, ROI, VPS implantada ou J1 homologada.
- Nenhum gasto extra, credencial, ordem de trade ou release de produção.

### Próxima ação concreta
1. Conferir HEAD/PRs/issues antes de agir, inclusive #19 (bloqueada por 451 no GitHub runner) e #23 (fonte independente em avaliação). Não recriar trabalhos.
2. Concluir teste offline, revisão, CI e integração segura da work unit #23. Somente depois do merge, acionar uma única sondagem GET de `futures.kraken.com` via comentário exato do proprietário na issue #23; registrar status e run. O workflow não é parte da CI de push/PR.
3. Se a fonte responder com sucesso, validar quantidade/tipo de contratos e metadados e planejar adaptador desacoplado como issue nova. Se responder 403/418/451, falhar sem retry/contorno e pesquisar outros provedores independentes permitidos.
4. Atualizar STATUS e OPERATIONAL_STATE com evidências, e manter J1 aberta até aceite efetivo de dados live/históricos.
5. Ao pedir "gere prompt para novo chat", produzir prompt completo de continuidade com repositório, regras, decisões, jornadas, evidências, issues/PRs/SHAs, testes, bloqueios e próxima ação autorizada.
