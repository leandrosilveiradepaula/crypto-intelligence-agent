# D519 — publicação única do laboratório histórico já alimentado

## Escopo e evidência
O código de produto D516–D518 já está integrado e a captura real em checkout isolado foi bem-sucedida. O recibo D518 RESEARCH PASS do proprietário demonstra recuperação de 56 séries de 122 velas, 15.396 candles de 5m em 55 símbolos e replay 4h. Veja o estado operacional e status para resultados e limitações. Não é necessário baixar de novo para esta atualização.

## Revisões e gate
- Origem instalada: D515 `4c3b123785318249c20b343ceb721dbf1a431f73`; ambos serviços PAPER e J1 ativos, overrides D507 90 e D515 91, working directory D515 igual nos dois serviços.
- Produto fixado: `549742a5f101359b26c18eee4a522f125e7b511e`, árvore idêntica ao head D518 aprovado com CI 45463718726/45463718338. O instalador D519 é revisionado separadamente e não muda a revisão de produto. Nunca trocar a pinagem para HEAD móvel.
- Baixar o roteiro D519 pelo commit do instalador revisado, conferir blob Git e bash -n. Executar apenas no host pinado e root; produto roda como owner.
- Preflight D505 e `--reuse` D516/D518, EMA 10/30/60 e 4h apenas smoke, zero novas GETs, nenhuma gravação. Se falhar, nenhuma troca. A confirmação interativa AUTORIZO CUTOVER PAPER é indispensável.
- Com lock de perfil e zero posições abertas, parar apenas os dois serviços PAPER e acrescentar override 92; manter 90/91, checkouts e dados. Nova página e contratos D515 são conferidos, e GET real da comparação 5m local usa suplementos. A janela é móvel: reportar cobertura observada, inclusive zero, sem inventar resultados ou exigir lucro. Start do motor só após essas verificações.
- Se houver falha, remover apenas override D519, restaurar D515; verificar o estado de rollback. Não editar perfil durante a operação. Não substituir diários, banco, configuração, J1 ou credenciais. Sem ordens reais.

## Aceite
`D519_RELEASE=PASS`, `D519_CODE_SHA=549742a5f101359b26c18eee4a522f125e7b511e`, `D519_OWNER_RESEARCH_REUSE=PASS`, `D519_RESEARCH_ENDPOINT=PASS`, readback de cobertura, serviços ativos e `D519_J1_UNTOUCHED=YES`. Não equivalem a backtest financeiro validado, funding, liquidação, OOS ou lucro. A captura D518 já foi executada; D519 ainda não. Nenhum custo adicional.
