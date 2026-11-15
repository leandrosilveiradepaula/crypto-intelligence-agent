# J2/J3 OPS-PROSPECTIVE1 — Preflight sem escrita para ledger WS (#656)

## O que mudou (código, não implantação)

A J1 foi aprovada para **pesquisa** em D360 (#2/#319), sem autorizar ordens.
A watchlist J2 já está integrada (#638/PR #639), avaliação posterior J3
(#640/PR #641) e o ledger owner de decisões ex-ante (#644/PR #645).
A #656 não duplica a coleta N50, a seleção nem o motor financeiro.

`python -m scripts.research_j2_ws_prospective_once preflight --allow-private-readonly-research`
executa **uma auditoria somente leitura**. Antes de acessar a epoch WS,
verifica: usuário POSIX não root, UID real/efetivo, DAC do diretório
pai (e ledger opcional), relatório OS `NTPSynchronized=yes` obtido
por `/usr/bin/timedatectl` com timeout, janela UTC estrita do
fechamento atual `HH:03:00` inclusivo até `HH:59:00` exclusivo.
Reusa o único leitor privado `_private_source` de D348/D624, que
exige 50 × 24 velas fechadas, ponteiro ativo imutável durante duas
leituras, integridade do journal, metadados e digests da mesma epoch.

A saída JSON tem chaves explícitas **somente de estado/contagem/tempo**,
sem símbolo, preço, path do owner, payload WS ou decisão. `status`
`owner_preflight_ready_no_capture` e exit 0 indicam apenas que
pode ser tentada a chamada `capture` separada **naquela janela**, não
que ela aconteceu ou terá sucesso. Em outro estado, exit 65 e nenhum
registro. O preflight não cria pasta, não abre SQLite em modo de escrita,
não chama HTTP/WS, não marca carteira, não inicia serviço/timer nem envia
ordens. Uma pasta de ledger ainda ausente é permitida se o diretório pai
for seguro; só o `capture` explicitamente habilitado poderá criá-la.

## Procedimento operacional preparado (NÃO executar nesta PR)

1. **Pré-release:** revisão do SHA exato, CI Linux/Windows/PAPER, checagem
   read-only das units/health N50 e owner `cia-probe`, confirmação de
   `timedatectl` sincronizado e permissões. O checkout de pesquisa deve
   ser isolado e não trocar código, timers, epoch ou SQLite da N50.
2. **Com gate de implantação aprovado:** executar o `preflight`
   sob owner não root após HH:03 UTC, com `--allow-private-readonly-research`;
   se falhar, **abster**, sem repetição agressiva e sem backfill inventado.
3. **Uma captura por hora, separada da N50:** somente se preflight PASS
   e horário ainda válido, executar
   `python -m scripts.research_j2_ws_prospective_once capture --allow-private-readonly-research --allow-private-ledger-write`.
   O ledger usa arquivo privado 0600, diretório 0700, hash e commit
   atômico sem overwrite. Resultado duplicado/ausente é abstinência.
   Não executar capture em esta PR nem alegar evidência antes do job real.
4. **Depois de 1h, 4h e 8h reais:** executar uma única avaliação por
   horizonte com
   `python -m scripts.research_j2_ws_prospective_once score --allow-private-readonly-research --allow-private-ledger-read --horizon-bars 1 --notional 100 --entry-fee-bps 4 --exit-fee-bps 6 --entry-slippage-bps 2 --exit-slippage-bps 3`
   (trocar apenas `--horizon-bars` para 4 ou 8). Esses números são
   **cenário hipotético de custo**, não dados de corretora. O score exige
   arquivo original e vela posterior auditada da mesma coorte; na rotação,
   gap, clock drift ou falta de dados abstém. 24h entre epochs não está
   homologado.
5. **Revogação/rollback:** desabilitar apenas o agendador *novo*, caso
   futuramente aprovado e instalado. Nunca apagar/regravar decisões já
   capturadas, reiniciar o N50 nem restaurar epoch antiga para forçar score.

## Evidências que ainda faltam

- Captura prospectiva real e seu registro de horário verificável sem hindsight.
- Maturação real posterior 1/4/8h sem mudança de coorte e auditoria de custos.
- Agendamento/observabilidade operacional autorizados, sem abrir serviço web
  público, porta ou credencial. O relógio da própria máquina + SHA local
  **não são testemunha independente de tempo**.
- Avaliação estatística OOS, custos reais, slippage, funding, liquidação,
  liquidez, estabilidade e condições para sinal: todas **não aprovadas**.

Gates permanecem falsos: `prospective_registration_independently_verified`,
`financial_backtest_approved`, `marketwide_top50_verified`,
`approved_for_signals`, `live_trading_authorized`. R$ 0,00 adicional.

## Testes

`python -m unittest discover -s tests -p test_j2_ws_owner_preflight.py -v`
(sem rede e sem precisar de dados privados). Conferir que:

- falta de opt-in, UID errado, DAC inseguro e `timedatectl` incerto abstêm;
- limites HH:03/HH:59 e saltos do relógio não admitem escrita tardia;
- epoch ausente ou incoerente falha com saída sanitizada, sem símbolos;
- pasta 0700 existente não é alterada; pasta ausente não é criada;
- CLI executa somente preflight sem acionar capture/score.
