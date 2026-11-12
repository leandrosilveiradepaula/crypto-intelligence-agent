# J3/D305 — estudo observacional posterior à interrupção, sem live e sem fills

## Objetivo

O N50 real conseguiu três publicações horárias consecutivas antes do HALT de 12/11/2026 às 08:01 UTC. A auditoria forense D304 confirmou, sem GET, a integridade dos 1.306 candles, 3 checkpoints e 6 candles parciais da hora não publicada. D302, corretamente, bloqueava uma pesquisa que tentasse tratar um journal halted como coleta saudável. D305 adiciona um **opt-in distinto, apenas de leitura histórica**, para não desperdiçar os checkpoints validados e sem contornar a barreira de risco.

## Novo contrato

`evaluate_n50_expost_marks(..., allow_archived_halted_research=True)` exige o opt-in owner de auditoria e usa D304 `audit_halted_n50_epoch`: HALT válido e persistente, digest de manifesto exato, 50 contratos, candles/cursos/recibos revalidados, sem lacunas históricas e sem permissão de retomada. A seleção usa exclusivamente os 24 candles conhecidos em `t`; o resultado da hora seguinte `t+1h` só é comparado depois da sua publicação real. As 6 linhas da hora interrompida não entram em cálculo nenhum. A expiração de TTL do manifesto limita novas capturas, mas **não** a leitura dos dados históricos (validar na última observação permitida pelo TTL). O caminho D302 original permanece estrito por padrão, sem aceitar journals halted ou velhos inadvertidamente.

A CLI `python -m scripts.evaluate_j3_n50_halted_archive_once --allow-private-readonly-audit --enable-archived-halted-research` é fixa à pasta owner privada N50 e divulga somente contagens e referências monetárias arredondadas a 2 casas (sem tickers, preços, sinais ou ordens), com status `archived_halted_expost_reference_only`. O resultado permanece `financial_backtest_approved=false`, `approved_for_signals=false`, `out_of_sample_results_validated=false`, `number_of_profitable_fills_verified=0`, `network_requests=0`, sem dados de funding, fills, liquidação ou execução.

## Evidência VPS read-only — 12/11/2026 UTC

Pesquisa executada como `cia-probe` no código candidato D305 com arquivo imutável da epoch `epoch-1794456000000`, sem alteração de SQLite, gateway ou systemd. Retorno `archived_halted_expost_reference_only`, `halted_archive_source_verified=true`, 50 contratos × 25 candles, marcação entre checkpoint UTC `1794463200000` e `1794466800000`, digest de snapshot `03ab4b566f7a454ff736f2ffca88e6f7484662d9dde502d6dfa966e729d38368`. Cenário fixo hipotético de US$ 100 de referência por contrato, taxas totais de 12 bps + slippage de 6 bps (18 bps; US$ 0,18 por ativo):
- Cinco maiores retornos passados (LONG), soma de marcação líquida ex post: **+US$ 24,72**.
- Cinco menores retornos passados (SHORT), soma: **−US$ 5,19**.
- Todos os 50 contratos hipoteticamente LONG, soma: **+US$ 13,00**.

Esses números **não são PnL, execução, previsão nem evidência de rentabilidade**: somente uma transição horária descritiva e custos presumidos, sem validação OOS/walk-forward, funding real, microestrutura, liquidação ou slippage realizado.

## Aceite e limitações

Testes D302 de fluxo normal mantidos; D305 adiciona fixture real-layout com 3 publicações/6 parciais e verifica gate archived separado, recusa padrão, suporte ao TTL expirado, digest adulterado, opt-in, status sanitizado e ausência de símbolos na CLI. Revisão CI Linux/docs Windows/offline Chrome/PAPER no SHA final e merge **sem deploy**. J1 #429 permanece HALT/provedor em revisão e N2 como fallback, #319 identidade USDT independente não certificada, J3 #4 ainda pesquisa sem negociação. Não reiniciar N50 por causa desse estudo.
