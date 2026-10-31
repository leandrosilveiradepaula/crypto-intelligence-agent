# J3/PRE24 — Trilha causal OOS e fragilidade por fold

## Lacuna e invariantes
A igualdade de contagens de exposições e abstenções não demonstra que duas simulações usaram o mesmo ativo ou sinal. PRE24 gera SHA-256 separado por fold e agregado com evento canônico `["j3-pre24-decision-v1", fold, index, series_manifest_sha256, previous_direction, selected_rule, action]` para **cada barra OOS**, inclusive abstenções. O identificador da série é o manifesto opaco já usado no laboratório Vision; não representa assinatura de exchange, direitos ou autenticidade. Os dados brutos e símbolos nunca aparecem no output. O evento é independente de alavancagem, taxa, funding, stop, alvo ou OHLC contemporânea. Mudança de ativo/regra/direção é detectada mesmo quando todas as contagens permanecem iguais.

## Contrato
`vision_stress_oos.VisionStressFoldAudit.decision_fingerprint_sha256` e `VisionStressOOS.decision_fingerprint_sha256` são aditivos. O digest financeiro PRE21 histórico continua calculado a partir do fold legado sem esse campo. PRE22 compara o par de fingerprints e a cobertura por fold entre todos os cenários; divergência => `DataValidationError`, não publicar comparação. PRE22/PRE23 expõem os mesmos fingerprints sanitizados, drawdown prefixo condicional quote e maior perda hipotética de uma barra relativa à margem por cenário e fold, sem classificação de vencedor.

## Validação e limitações
Testar 1x/50x com mesma trilha, permutação de ativos, cenário mock alterando apenas fingerprint com contagens idênticas, seleção passada alterada, OHLC atual isolada, determinismo, no-network e outputs sem símbolos/paths. CI Linux/docs, Windows/offline e Chrome/PAPER no SHA final, revisão e merge apenas sem deploy. Nada de dados canônicos, trajetória intrabar conhecida, mark/funding/fills reais, fórmula de liquidação homologada, ROI, Top50 marketwide, stop nativo, ordem ou live. Flags negativas e custo R$0.
