# J2/J3 — registro privado de decisões e avaliação posterior WS (#644)

## Por que esta entrega muda a pesquisa

Com J2/WS-WATCH1 (#638) já calculamos observações LONG/SHORT de rompimento/força BTC/volume. Com J3/#640 já medimos, **em funções puras**, quanto uma observação se alinharia ao preço de fechamento 1h, 4h ou 8h depois, sob taxas, slippage e funding hipotéticos. A lacuna era operar em **dois instantes diferentes**, sem fornecer ao mesmo cálculo os dados passados e futuros para escolher a melhor entrada depois que ocorreu.

Esta entrega permite:

1. **Captura sob owner**: na hora UTC atual, após a coleta horária WS e com janela 50×24 auditada, chama **o leitor D624 existente**, gera watchlist privada J2 e lê o fechamento da última vela para os candidatos e BTC **do mesmo snapshot auditado**. Congela a seleção via `freeze_ws_watchlist_reference` com horário medido pela própria aplicação, sem parâmetro livre para backdating. Se ainda não houver janela, revalidação de epoch ou faltarem candles, retorna abstinência e **não grava registro artificial**.
2. **Registro local uma vez**: grava um `decision-<utc-end-ms>.json` privado em `/home/cia-probe/agent/j2-ws-prospective-private`, diretório 0700 sob proprietário não root, arquivo 0600 com escopo e digest de metadados. Escreve arquivo temporário em 0600, `fsync`, cria link final atomicamente com semântica **não sobrescrever** e sincroniza o diretório. A mesma hora não pode ser registrada de novo; não apaga, corrige nem sobrepõe uma decisão antiga. Nenhum preço ou símbolo sai do diretório owner. O código está no GitHub, **não executado nem instalado na VPS**.
3. **Avaliação posterior, somente leitura**: quando nova vela 1h, 4h ou 8h fechar, reexecuta o **mesmo leitor D624** para os 50×24 candles da **mesma epoch**, reconstrói a decisão privada original validando bytes canônicos, SHA de registro/decisão, DAC, inode, símbolos e datas, e chama o motor J3/#640 com premissas de custo explicitamente escolhidas. Se houver mudança de digest de escopo/metadados, falta de arquivo/vela, intervalo fora da janela ou arquivo adulterado, abstém. A resposta no stdout é **somente agregada**, com números de observações, comportamento direcional, referência BTC e custos *assumidos*. Nenhum preço/símbolo, ordem, stop ou posição.
4. **Sem ciclo artificial de 24h**: captura depende da janela real de 24 candles fechados da epoch ativa. Depois de uma rotação a cada 36h, há até cerca de 12h para maturação futura dentro da mesma coorte. Por isso, o CLI operacional suporta inicialmente **1/4/8 horas**, enquanto 24h futuro fica censurado até haver uma prova explícita de continuidade de dados entre cohorts. Não reinicia coleta, não faz backfill REST e não declara falha se a coorte girou.

## Contratos e comandos preparados (não executados na VPS)

- `crypto_intelligence_agent.j2_n50_ws_private_screen.observe_active_private_ws_n50_24closed(..., include_private_last_closes=True)`: opção privada adicional, requer também `include_private_symbols=True`, owner não root, opt-in de pesquisa; **default permanece false**. Dados derivam do replay 50×24 **já duplamente auditado**, não de um novo acesso SQL. As APIs públicas/loopback não ativam essa opção.
- `capture_owner_ws_decision_once(allow_private_readonly_research=True, allow_private_ledger_write=True)`: retorna resultado sanitizado com estado de captura e quantidade de candidatos, **sem modificar SQLite**. Usa o próprio relógio para rejeitar decisão tardia.
- `score_owner_ws_decision_once(horizon_bars=1|4|8, costs=ForwardCostAssumptions(...), allow_private_readonly_research=True, allow_private_ledger_read=True)`: somente leitura, não envia ordem.
- CLI preparado: `python -m scripts.research_j2_ws_prospective_once capture --allow-private-readonly-research --allow-private-ledger-write`. Para score: `python -m scripts.research_j2_ws_prospective_once score --allow-private-readonly-research --allow-private-ledger-read --horizon-bars 1 --notional 100 --entry-fee-bps 4 --exit-fee-bps 6 --entry-slippage-bps 2 --exit-slippage-bps 3`. **Os números são exemplos de hipótese**; não são taxas certificadas da Bybit nem recomendação de exposição ou ordens. Nenhum comando desta PR é implantado na VPS.

## Limites explícitos de evidência e de negociação

- Um SHA e arquivos owner 0600 indicam integridade **local** contra acidentes/duplicação no processo, mas o proprietário com acesso ao diretório pode modificar arquivos ou relógio. **Isso não é uma atestação independente de tempo de registro, ainda não prova OOS prospectivo, sinal, probabilidade, PnL líquido real ou lucro**, nem comprova identidade Top50 marketwide (#319).
- `prospective_registration_independently_verified=false`, `financial_backtest_approved=false`, `approved_for_signals=false`, `orders_sent=false`. Medidas de fechamento são preços referenciais ex-post, não fills. Não há mark price/liquidação, latência real, spread dinâmico, custos da corretora ou funding factual, salvo se obtidos/validados separadamente.
- O código não instala timer, cron, daemon, endpoint público, serviço ou proxy; não mexe em permissões de outros processos, não toca a VPS nem pede segredos. Para rodar continuamente depois do release gate será necessária uma decisão de operação de agendamento sob usuário owner, com gates existentes e observabilidade, sem contornar DAC. Operações reais continuam proibidas.

## Validação

- `tests/test_j2_n50_ws_private_screen.py`: última close privada só quando requisitada com duas opções verdadeiras, mantendo default sem preço ou símbolo.
- `tests/test_j2_ws_prospective_ledger.py`: captura/duplicação de hora única, dir 0700/arquivo 0600, persistência de digest de metadados, leitura posterior 1/4/8h, modificação do future sem mudar decisão, abstenção com escopo/meta rotacionados, fonte incompleta, BTC inválido, symlink/hardlink/arquivo 0644/digest adulterado, falhas de optin, custos explícitos, zero rede/SQL adicional/ordens. Windows executa apenas contratos de CLI sem FS owner POSIX.
- Executar compileall e CI Linux/docs + Windows/offline + PAPER/mobile no HEAD final. Rever diff financeiro e de arquivo privado antes de merge sem deploy.

**Próximo passo operacional real:** após homologação D323 sobre a janela efetiva da epoch atual, planejar execução owner em ambiente aprovado, **sem ordens**, para coletar decisões reais em horário de fechamento e observar outcomes. Não é necessária nova rodada de desenvolvimento do coletor para isso. 
