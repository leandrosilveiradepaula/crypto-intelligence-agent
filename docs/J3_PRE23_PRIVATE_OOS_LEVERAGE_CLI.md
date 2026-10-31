# J3/PRE23 — comparação OOS 1x vs Nx na CLI privada Vision

## Propósito e fonte
A CLI owner-only `scripts.replay_private_vision_dynamic` já aceita uma coleção de
2–50 manifests de ZIPs Vision privados, valida nomes, checksums, cobertura,
janelas comuns e limites antes de executar auditoria offline. PRE23 acrescenta
o opt-in **`--audit-oos-leverage-pair`** ao mesmo processo, sem criar nova
fonte, downloader ou parser. O motor `vision_stress_sensitivity` PRE22
faz o cálculo: mesma seleção causal, treino e histórico, com apenas duas
alavancagens hipotéticas comparadas.

## Contrato

O novo modo exige `--allow-personal-nonproduction-research`, ambiente POSIX,
`--audit-intrabar-stress` e **todos os termos stress** originais (margem,
alavancagem N, stop, alvo, manutenção, fees, slippage, funding e custo de
seleção). `--stress-leverage` N precisa ser inteiro entre **2 e 200**, senão
falha fechado. Não é permitido combinar com o modo de choques
`--audit-stress-sensitivity`. Sem `--audit-oos-leverage-pair`, o contrato
anterior não é alterado.

PRE23 cria `VisionStressAssumptions` para 1x e para N x, com a **mesma
margem sintética fixa**, mesmo `quote_currency` e os demais termos
idênticos. Somente a alavancagem e o nocional de entrada (margem ×
alavancagem) mudam. A comparação usa
`compare_costed_vision_oos_stress_scenarios` sobre os mesmos
`OfflineVisionMonth` verificados pelo leitor privado, sem reabrir
arquivos, trocar a regra mensal ou executar o motor de sinal em live.

O campo adicional de relatório é `hypothetical_oos_leverage_pair`, com
`schema_version=j3_pre22_oos_sensitivity_v1`, ordinais 1x/Nx (ordem
pré-definida, **não classificação**), todos os termos financeiros
declarados, estados condicionais adverso/favorável por fold e
`financial_backtest_approved=false`, `live_trading_authorized=false`,
`orders_sent=false`. Não inclui nomes de ativos, caminhos, preços brutos
ou PnL de corretora. Qualquer rejeição gera somente o JSON sanitizado
`private_vision_dynamic_replay_rejected` e exit code 1.

## Exemplo ilustrativo

Os parâmetros a seguir são **fixtures de teste**, não taxas reais,
recomendação de alavancagem ou fórmula de liquidação de venue:

```sh
python -m scripts.replay_private_vision_dynamic \
  --manifest MANIFEST_1 --manifest MANIFEST_2 \
  --allow-personal-nonproduction-research \
  --first-decision-ms UTC_INICIO --last-decision-ms UTC_FIM \
  --audit-intrabar-stress --audit-oos-leverage-pair \
  --stress-margin-quote 2 --stress-leverage 50 \
  --stress-stop-fraction 0.01 --stress-target-fraction 0.03 \
  --stress-maintenance-bps 0 --stress-fee-bps 0 \
  --stress-slippage-bps 0 --stress-funding-bps 0 \
  --stress-selection-cost-bps 0
```

## Evidência e limites
O teste `tests/test_replay_private_vision_dynamic.py` constrói dois
manifests sintéticos e verifica equivalência entre o relatório produzido
pela CLI e o PRE22 chamado diretamente; a leitura CLI não reinterpreta
dados, mantém modo legado, não usa rede e sanitiza até caminhos inválidos.
Testar no Linux/POSIX e validar skips POSIX em Windows/offline; Chrome/PAPER
não pode regredir. O CLI é proprietário local, sem qualquer intervenção
na VPS J1 e sem autorização para acesso a dados reais, conta ou trade.

J3 #4 segue em pesquisa: 50x é apenas cenário de fragilidade, não afirmação
de estratégia rentável ou capital protegido. Sem taxas/funding de exchange,
mark, fill, trajetória intrabar, stop nativo ou autorização testnet/live.
Orçamento adicional R$0. Usar resultados somente para decidir quais
validações financeiras independentes ainda faltam.
