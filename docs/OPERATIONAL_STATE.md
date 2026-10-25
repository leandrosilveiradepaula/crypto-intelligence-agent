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
- WU5 #19 permanece **ABERTA**; PR #20 merged no SHA `cddfc2535aac7c3b7ae9bc04fea160419344ee7f`; CI HEAD original `a616aa4161941c0cee57ed57883ded78cfed78e6` run 40189543705 SUCCESS; CI pós-merge run 40189603458 SUCCESS (78 unittest, compileall e 10 docs). Entregue somente conformance offline, HTTP 403/418, Retry-After limitado para 429, payloads públicos e auditoria de falhas.
- J2–J7: issues #3–#8 ainda dependem de J1, sem código de estratégia em produção.

### Limites e bloqueio verdadeiro
- Nenhuma execução live controlada comprovada nesta sessão. Testes GitHub Actions intencionalmente **offline**; CLI live exige `--mode live --allow-public-network`.
- A máquina local desta conversa não consegue resolver github.com por DNS; isso não é evidência sobre disponibilidade da API da Binance. Sem Codex diretamente acionável via ferramenta.
- Não declarar feed real, cobertura histórica extensa, snapshots ponto-no-tempo retrospectivos, ROI, VPS implantada ou J1 homologada.
- Nenhum gasto extra, credencial, ordem de trade ou release de produção.

### Próxima ação concreta
1. Conferir HEAD real da main, issues/PRs, AGENTS.md e docs antes de qualquer alteração; não duplicar #19.
2. Validar e integrar a PR documental/operacional da branch `chore/j1-explicit-live-smoke` (issue #19), com workflow GET público restrito a comentário exato do proprietário, CI offline e revisão no SHA. Somente após o workflow estar no `main`, acionar explicitamente um único smoke pelo comentário `/run-readonly-smoke-v1` na issue #19. Registrar link do run, status/timestamps/cobertura e erro real ou sucesso. O GitHub Actions padrão para repositório público não exige custo adicional. Sem secrets/trades.
3. Se não houver executor com rede, registrar gate live pendente e concluir qualquer outra validação offline útil. Não inferir sucesso real de testes de fixture.
4. Após evidências, revisar/ corrigir, integrar mudanças sem produção somente com CI/gates/SHA conferidos; atualizar STATUS e OPERATIONAL_STATE. Manter J1 aberta até aceite efetivo.
5. Ao pedir "gere prompt para novo chat", produzir prompt completo de continuidade com repositório, regras, decisões, jornadas, evidências, issues/PRs/SHAs, testes, bloqueios e próxima ação autorizada.
