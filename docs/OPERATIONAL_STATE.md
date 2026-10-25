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
- WU6 #23 **concluída**: PR #24 merged, SHA `76490ac8790138642f34de710c5f2e4bb2cf3d09`; GitHub Actions run `40198042787` SUCCESS: GET independente Kraken Futures `/derivatives/api/v3/instruments` HTTP200 em 641ms, UTC `2026-10-25T13:32:08Z`, 231 instrumentos, 213 prefixos PI_/PF_ heurísticos, SEM comprovação de elegibilidade crypto-only. Inclui PF_AAPLXUSD tokenizado. 90 testes offline no merge.
- WU7 #25 **em desenvolvimento**: branch `research/j1-kraken-market-conformance`, pesquisa de schema `instruments` / `tickers` / `trade candles` em máximo 3 GETs, sem autenticação. Até PR/checks/merge e run owner-only, não marcar schema real validado.
- J2–J7: issues #3–#8 ainda dependem de J1, sem código de estratégia em produção.

### Limites e bloqueio verdadeiro
- Smoke GET live via GitHub Actions **tentado e bloqueado**: issue #19, comando exato `/run-readonly-smoke-v1` pelo proprietário, workflow run `40197499250` no commit `09617e0197c250e3b13c7486a60067791ed41a52`, 2026-10-25T13:24:57Z, HTTP **451** na primeira consulta pública. Sem candles, sem validação de preço/volume. Fluxo usual de testes GitHub Actions continua offline.
- A máquina local desta conversa não consegue resolver github.com por DNS; isso não é evidência sobre disponibilidade da API da Binance. Sem Codex diretamente acionável via ferramenta.
- Não declarar feed real, cobertura histórica extensa, snapshots ponto-no-tempo retrospectivos, ROI, VPS implantada ou J1 homologada.
- Nenhum gasto extra, credencial, ordem de trade ou release de produção.

### Próxima ação concreta
1. Conferir HEAD/PRs/issues antes de agir; não duplicar #19 (Binance bloqueada HTTP451), #23 (Kraken instrumentos GET200, encerrada) ou #25 (conformance em implementação).
2. Validar PR/CI/revisão da WU7 #25 no SHA exato e integrar apenas sem produção. Depois iniciar UMA sondagem da fonte independente com comentário owner-only `/probe-kraken-market-v1` na #25 e registrar GitHub Actions run, status, nomes de campos seguros e datas.
3. Antes de implementar novo adaptador, avaliar tipos de instrumentos, ativos tokenizados excluídos, volume cotado comparável e trajetória de fechamento dos candles, sem supor a lista Top50. Criar issue separada para adaptação somente após schema observado.
4. Se resposta 403/418/451 ou erro não recuperável, não tentar contorno; registrar evidências e avançar nas tarefas offline independentes. Atualizar STATUS/OPERATIONAL_STATE e manter J1 aberta.
5. Ao pedir "gere prompt para novo chat", produzir prompt completo de continuidade com repositório, regras, decisões, jornadas, evidências, issues/PRs/SHAs, testes, bloqueios e próxima ação autorizada.

### Erro de empacotamento no primeiro smoke WU7
- Run [40198556326](https://github.com/leandrosilveiradepaula/crypto-intelligence-agent/actions/runs/40198556326) FALHOU antes de acesso externo: `ModuleNotFoundError: No module named 'scripts'` ao executar script por caminho. **Zero requisições Kraken e nenhuma evidência nova de mercado.**
- Correção na branch `fix/j1-kraken-probe-module-entry`: executar `python3 -m scripts.probe_kraken_market_schema` a partir da raiz do repositório, com imports relativos à raiz disponíveis. Precisa PR/CI/merge antes de um único novo disparo owner-only. Não confundir falha de invocação com bloqueio de exchange.
